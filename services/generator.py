import random
from datetime import time
from models import (
    db, Schedule, Shift, Employee, ServiceConfig,
    ServiceSlot, PlanningConstraint
)


# ================================================================== #
#  POINT D'ENTRÉE PRINCIPAL                                           #
# ================================================================== #

def generate(schedule_id: int) -> dict:
    """
    Génère un planning complet pour un schedule donné.
    Retourne un dict avec :
      - shifts   : liste des shifts générés (pas encore persistés)
      - anomalies: liste de messages d'anomalie détectés
      - success  : bool
    Lève ValueError si les données sont insuffisantes.
    """
    schedule  = Schedule.query.get(schedule_id)
    if not schedule:
        raise ValueError(f"Schedule {schedule_id} introuvable")

    manager_id = schedule.manager_id
    employees  = Employee.query.filter_by(manager_id=manager_id, is_active=True).all()
    configs    = (ServiceConfig.query
                  .filter_by(manager_id=manager_id)
                  .all())

    if not employees:
        raise ValueError("Aucun employé actif")
    if not configs:
        raise ValueError("Aucune configuration de service définie")

    constraints = PlanningConstraint.query.filter_by(schedule_id=schedule_id).all()

    ctx = _build_context(employees, configs, constraints)

    MAX_ATTEMPTS = 50
    for attempt in range(MAX_ATTEMPTS):
        shifts = _run(ctx)
        anomalies = _validate(shifts, ctx)
        # On accepte le planning même avec anomalies mineures (heures légèrement
        # hors quota). On réessaie uniquement si un service est sans
        # manager/assistant.
        critical = [a for a in anomalies if a['level'] == 'critical']
        if not critical:
            break
    else:
        # Après 50 essais on retourne quand même le dernier résultat
        # avec toutes ses anomalies plutôt que rien.
        pass

    return {
        'shifts':    shifts,
        'anomalies': anomalies,
        'success':   True,
        'attempts':  attempt + 1,
    }


def persist(schedule_id: int, shifts: list) -> None:
    """
    Supprime les anciens shifts du planning et insère les nouveaux.
    À appeler après que le manager a validé le planning généré.
    """
    Shift.query.filter_by(schedule_id=schedule_id).delete()
    for s in shifts:
        db.session.add(Shift(
            schedule_id=schedule_id,
            employee_id=s['employee_id'],
            day_of_week=s['day_of_week'],
            start_time=s['start_time'],
            end_time=s['end_time'],
            slot_id=s.get('slot_id'),
        ))
    db.session.commit()


# ================================================================== #
#  CONSTRUCTION DU CONTEXTE                                           #
# ================================================================== #

def _build_context(employees, configs, constraints):
    """
    Pré-calcule toutes les structures utiles pour la génération.
    """
    # Index des configs par (day, service_type)
    config_map = {(c.day_of_week, c.service_type): c for c in configs}

    # Jours actifs (jours pour lesquels au moins une config existe)
    active_days = sorted(set(c.day_of_week for c in configs))

    # Contraintes par employé
    emp_constraints = {}  # employee_id -> list[PlanningConstraint]
    for c in constraints:
        emp_constraints.setdefault(c.employee_id, []).append(c)

    # Heures cibles par employé (contrat + override éventuel)
    target_hours = {}
    for emp in employees:
        base = float(emp.hours_per_week)
        override = _get_hours_override(emp_constraints.get(emp.id, []))
        target_hours[emp.id] = base + (override or 0)

    return {
        'employees':     employees,
        'config_map':    config_map,
        'active_days':   active_days,
        'constraints':   emp_constraints,  # par employee_id
        'target_hours':  target_hours,
        'all_configs':   configs,
    }


# ================================================================== #
#  PASSE 1 + 2                                                        #
# ================================================================== #

def _run(ctx):
    """
    Exécute une tentative complète de génération.
    Retourne une liste de dicts représentant les shifts.
    """
    shifts   = []                    # liste finale
    assigned = {}                    # (employee_id, day) -> list[shift]
    worked   = {e.id: 0.0 for e in ctx['employees']}  # heures cumulées

    # --- PASSE 1 : jours forcés & slots ouverts/closes imposés ---
    for emp in ctx['employees']:
        for c in ctx['constraints'].get(emp.id, []):
            if c.constraint_type == 'forced' and c.day_of_week is not None:
                shift = _make_shift(
                    emp.id, c.day_of_week,
                    c.forced_start, c.forced_end,
                    slot_id=None
                )
                shifts.append(shift)
                assigned.setdefault((emp.id, c.day_of_week), []).append(shift)
                worked[emp.id] += _hours(c.forced_start, c.forced_end)

    # --- PASSE 2 : attribution aléatoire sous contraintes ---
    days = ctx['active_days']

    for emp in ctx['employees']:
        # Jours déjà assignés (forcés)
        forced_days = {day for (eid, day) in assigned if eid == emp.id}

        # Jours indisponibles
        unavail = _unavail_days(ctx['constraints'].get(emp.id, []), days)

        # Jours disponibles restants
        available = [d for d in days if d not in forced_days and d not in unavail]

        # Calcul du nombre de jours travaillés nécessaires
        target = ctx['target_hours'][emp.id]
        avg_shift_h = _estimate_avg_shift(ctx['config_map'], days)
        needed_days = min(len(available), max(0, round(target / avg_shift_h)))

        # Au moins 2 jours de repos (préférence jours consécutifs)
        max_work_days = len(days) - 2
        needed_days   = min(needed_days, max_work_days)

        # Sélection des jours travaillés (consécutifs si possible)
        work_days = _pick_work_days(available, needed_days, days)

        for day in work_days:
            day_shifts = _assign_day(emp, day, ctx, worked)
            for s in day_shifts:
                shifts.append(s)
                assigned.setdefault((emp.id, day), []).append(s)
                worked[emp.id] += _hours(s['start_time'], s['end_time'])

    return shifts


def _assign_day(emp, day, ctx, worked):
    """
    Attribue un ou plusieurs services à un employé pour un jour donné.
    Retourne une liste de shifts (0, 1 ou 2 selon coupure possible).
    """
    result     = []
    exc        = _excluded_services(ctx['constraints'].get(emp.id, []), day)
    config_map = ctx['config_map']

    services = []
    if (day, 'morning') in config_map and 'morning' not in exc:
        services.append('morning')
    if (day, 'evening') in config_map and 'evening' not in exc:
        services.append('evening')

    if not services:
        return result

    # Décide aléatoirement si l'employé fait une coupure (matin + soir)
    # Probabilité de coupure : 20 % si les deux services sont dispos
    do_both = (len(services) == 2 and random.random() < 0.20)
    chosen  = services if do_both else [random.choice(services)]

    for stype in chosen:
        cfg = config_map[(day, stype)]
        start, end, slot_id = _pick_slot(cfg, emp, ctx, day)
        if start and end:
            result.append(_make_shift(emp.id, day, start, end, slot_id))

    return result


def _pick_slot(cfg, emp, ctx, day):
    """
    Choisit les horaires de début/fin pour un service donné.
    Tient compte des slots ouverture/close et des arrivées/départs possibles.
    """
    slots  = cfg.slots
    stype  = cfg.service_type

    # Slots ouverture (soir uniquement)
    opening_slots = [s for s in slots if s.slot_type == 'opening']
    close_slots   = [s for s in slots if s.slot_type == 'close']
    arrival_slots = [s for s in slots if s.slot_type == 'arrival']
    depart_slots  = [s for s in slots if s.slot_type == 'departure']

    start = cfg.open_time
    end   = cfg.close_time
    slot_id = None

    if stype == 'evening' and opening_slots and random.random() < 0.3:
        # Affecte l'employé à l'ouverture (il reste pour tout le service)
        sl     = random.choice(opening_slots)
        start  = sl.start_time
        slot_id = sl.id
    elif stype == 'evening' and arrival_slots:
        sl    = random.choice(arrival_slots)
        start = sl.start_time

    if stype == 'evening' and close_slots and random.random() < 0.3:
        sl     = random.choice(close_slots)
        end    = sl.end_time or cfg.close_time
        slot_id = slot_id or sl.id
    elif stype == 'evening' and depart_slots:
        sl  = random.choice(depart_slots)
        end = sl.start_time

    # Sécurité : si end <= start on prend les horaires du service entier
    if end <= start:
        start   = cfg.open_time
        end     = cfg.close_time
        slot_id = None

    return start, end, slot_id


# ================================================================== #
#  VALIDATION                                                         #
# ================================================================== #

def _validate(shifts, ctx) -> list:
    """
    Vérifie les règles après génération.
    Retourne une liste d'anomalies avec level='critical' ou 'warning'.
    """
    anomalies = []
    config_map = ctx['config_map']
    employees  = {e.id: e for e in ctx['employees']}

    # Index : (day, service_type) -> [employee_ids présents]
    service_staff = {}
    for s in shifts:
        # Détermine le service_type du shift (matin ou soir) à partir des configs
        stype = _guess_service_type(s['day_of_week'], s['start_time'], config_map)
        key   = (s['day_of_week'], stype)
        service_staff.setdefault(key, []).append(s['employee_id'])

    DAY_NAMES = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche']
    SVC_NAMES = {'morning': 'matin', 'evening': 'soir'}

    for (day, stype), cfg in config_map.items():
        present_ids  = service_staff.get((day, stype), [])
        present_emps = [employees[eid] for eid in present_ids if eid in employees]

        # Règle critique : au moins 1 manager ou assistant manager
        has_manager = any(e.role in ('manager', 'assistant') for e in present_emps)
        if not has_manager:
            anomalies.append({
                'level':   'critical',
                'message': (f"{DAY_NAMES[day]} {SVC_NAMES[stype]} — "
                            f"aucun manager ou assistant manager")
            })

        # Règle warning : effectif insuffisant
        if len(present_ids) < cfg.required_staff:
            anomalies.append({
                'level':   'warning',
                'message': (f"{DAY_NAMES[day]} {SVC_NAMES[stype]} — "
                            f"{len(present_ids)}/{cfg.required_staff} personnes requises")
            })

    # Warning heures hors quota (tolérance ±2h)
    worked = {}
    for s in shifts:
        h = _hours(s['start_time'], s['end_time'])
        worked[s['employee_id']] = worked.get(s['employee_id'], 0) + h

    for emp in ctx['employees']:
        target  = ctx['target_hours'][emp.id]
        actual  = worked.get(emp.id, 0)
        delta   = actual - target
        if abs(delta) > 2:
            sign = '+' if delta > 0 else ''
            anomalies.append({
                'level':   'warning',
                'message': (f"{emp.name} — {actual:.1f}h planifiées "
                            f"(contrat {target:.1f}h, {sign}{delta:.1f}h)")
            })

    return anomalies


# ================================================================== #
#  HELPERS                                                            #
# ================================================================== #

def _make_shift(employee_id, day_of_week, start_time, end_time, slot_id=None):
    return {
        'employee_id': employee_id,
        'day_of_week': day_of_week,
        'start_time':  start_time,
        'end_time':    end_time,
        'slot_id':     slot_id,
    }


def _hours(start: time, end: time) -> float:
    """Durée en heures entre deux objets time (même jour)."""
    if not start or not end:
        return 0.0
    s = start.hour * 60 + start.minute
    e = end.hour   * 60 + end.minute
    return max(0.0, (e - s) / 60)


def _unavail_days(constraints, all_days) -> set:
    """Retourne l'ensemble des jours indisponibles d'un employé."""
    days = set()
    for c in constraints:
        if c.constraint_type == 'unavailable':
            if c.day_of_week is None:
                return set(all_days)   # absent toute la semaine
            days.add(c.day_of_week)
    return days


def _excluded_services(constraints, day) -> set:
    """Retourne les service_types exclus pour cet employé ce jour."""
    excluded = set()
    for c in constraints:
        if c.constraint_type == 'exclude_service':
            if c.day_of_week is None or c.day_of_week == day:
                if c.exclude_service_type:
                    excluded.add(c.exclude_service_type)
    return excluded


def _get_hours_override(constraints) -> float:
    """Retourne le delta d'heures (override) si défini, sinon 0."""
    for c in constraints:
        if c.hours_override is not None:
            return float(c.hours_override)
    return 0.0


def _estimate_avg_shift(config_map, days) -> float:
    """Estime la durée moyenne d'un shift à partir des configs."""
    durations = []
    for (day, stype), cfg in config_map.items():
        if day in days:
            durations.append(_hours(cfg.open_time, cfg.close_time))
    if not durations:
        return 4.0
    return sum(durations) / len(durations)


def _pick_work_days(available: list, needed: int, all_days: list) -> list:
    """
    Sélectionne `needed` jours dans `available`.
    Favorise les blocs consécutifs pour que les jours de repos soient groupés.
    """
    if needed <= 0 or not available:
        return []
    if needed >= len(available):
        return available[:]

    # Essaie de trouver un bloc consécutif de taille `needed`
    available_set = set(available)
    for start_idx in range(len(all_days)):
        block = []
        for d in all_days[start_idx:]:
            if d in available_set:
                block.append(d)
            if len(block) == needed:
                # Vérifie que les repos forment au moins un bloc de 2
                rest = [d for d in available if d not in block]
                if _max_consecutive(rest) >= 2:
                    return block

    # Fallback : sélection aléatoire
    result = random.sample(available, needed)
    return sorted(result)


def _max_consecutive(days: list) -> int:
    """Retourne la longueur de la plus longue séquence consécutive."""
    if not days:
        return 0
    days = sorted(days)
    max_run = run = 1
    for i in range(1, len(days)):
        if days[i] == days[i-1] + 1:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 1
    return max_run


def _guess_service_type(day, start_time, config_map) -> str:
    """
    Détermine si un shift appartient au service matin ou soir
    en cherchant la config la plus proche par horaire d'ouverture.
    """
    candidates = {
        stype: cfg
        for (d, stype), cfg in config_map.items()
        if d == day
    }
    if not candidates:
        return 'morning'
    if len(candidates) == 1:
        return next(iter(candidates))

    # Choisit le service dont l'heure d'ouverture est la plus proche
    best, best_diff = 'morning', float('inf')
    start_min = start_time.hour * 60 + start_time.minute
    for stype, cfg in candidates.items():
        open_min = cfg.open_time.hour * 60 + cfg.open_time.minute
        diff = abs(start_min - open_min)
        if diff < best_diff:
            best, best_diff = stype, diff
    return best