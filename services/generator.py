"""
generator.py — Algo de génération de planning pizzeria
=======================================================
Stratégie en 3 passes :
  1. Pré-calcul : contraintes, jours dispos, cibles heures
  2. Attribution des jours de travail (répartis pour éviter
     que tout le monde soit en repos le même jour)
  3. Attribution des services (matin / soir) avec règles
     ouverture, managers, coupures prioritaires
"""
import random
from datetime import time as Time
from models import db, Schedule, Shift, Employee, ServiceConfig, ServiceSlot, PlanningConstraint

DAYS = list(range(7))  # 0=lun … 6=dim
WEEKEND = {5, 6}       # sam, dim


# ================================================================== #
#  POINT D'ENTRÉE                                                     #
# ================================================================== #

def generate(schedule_id: int) -> dict:
    schedule = Schedule.query.get(schedule_id)
    if not schedule:
        raise ValueError(f"Schedule {schedule_id} introuvable")

    manager_id = schedule.manager_id
    employees  = Employee.query.filter_by(manager_id=manager_id, is_active=True).all()
    configs    = ServiceConfig.query.filter_by(manager_id=manager_id).all()

    if not employees:
        raise ValueError("Aucun employé actif")
    if not configs:
        raise ValueError("Aucune configuration de service")

    constraints_raw = PlanningConstraint.query.filter_by(schedule_id=schedule_id).all()
    ctx = _build_context(employees, configs, constraints_raw)

    MAX = 100
    best_result   = None
    best_critical = 9999

    for attempt in range(MAX):
        shifts    = _run(ctx)
        anomalies = _validate(shifts, ctx)
        critical  = sum(1 for a in anomalies if a['level'] == 'critical')

        if critical < best_critical:
            best_critical = critical
            best_result   = (shifts, anomalies, attempt + 1)

        if critical == 0:
            break

    shifts, anomalies, attempts = best_result
    return {'shifts': shifts, 'anomalies': anomalies, 'success': True, 'attempts': attempts}


def persist(schedule_id: int, shifts: list) -> None:
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
#  CONTEXTE                                                           #
# ================================================================== #

def _build_context(employees, configs, constraints_raw):
    config_map = {(c.day_of_week, c.service_type): c for c in configs}
    active_days = sorted(set(c.day_of_week for c in configs))

    # Slots par config
    for c in configs:
        _ = c.slots  # force le chargement SQLAlchemy

    # Contraintes par employé
    emp_constraints = {}
    for c in constraints_raw:
        emp_constraints.setdefault(c.employee_id, []).append(c)

    # Cible heures (contrat + override)
    target_hours = {}
    for emp in employees:
        base     = float(emp.hours_per_week)
        override = next((float(c.hours_override) for c in emp_constraints.get(emp.id, [])
                         if c.hours_override is not None), 0.0)
        target_hours[emp.id] = base + override

    # Indispos par employé
    unavail = {}
    for emp in employees:
        days = set()
        for c in emp_constraints.get(emp.id, []):
            if c.constraint_type == 'unavailable':
                if c.day_of_week is None:
                    days = set(active_days)
                    break
                days.add(c.day_of_week)
        unavail[emp.id] = days

    # Exclusions de service par (employee_id, day)
    excl_svc = {}
    for emp in employees:
        for c in emp_constraints.get(emp.id, []):
            if c.constraint_type == 'exclude_service' and c.exclude_service_type:
                key = (emp.id, c.day_of_week)
                excl_svc.setdefault(key, set()).add(c.exclude_service_type)

    # Jours forcés par employé
    forced = {}
    for emp in employees:
        for c in emp_constraints.get(emp.id, []):
            if c.constraint_type == 'forced' and c.day_of_week is not None:
                forced.setdefault(emp.id, []).append(c)

    # Managers et assistants
    managers   = [e for e in employees if e.role in ('manager', 'assistant')]
    is_manager = {e.id: e.role in ('manager', 'assistant') for e in employees}

    return {
        'employees':   employees,
        'managers':    managers,
        'is_manager':  is_manager,
        'config_map':  config_map,
        'active_days': active_days,
        'target_hours':target_hours,
        'unavail':     unavail,
        'excl_svc':    excl_svc,
        'forced':      forced,
    }


# ================================================================== #
#  PASSE PRINCIPALE                                                   #
# ================================================================== #

def _run(ctx):
    shifts  = []
    worked  = {e.id: 0.0 for e in ctx['employees']}
    # worked_days[emp_id] = set of days already assigned (matin ou soir compte comme 1)
    worked_days = {e.id: set() for e in ctx['employees']}

    # --- Étape 1 : jours forcés ---
    for emp in ctx['employees']:
        for c in ctx['forced'].get(emp.id, []):
            s = _make_shift(emp.id, c.day_of_week, c.forced_start, c.forced_end)
            shifts.append(s)
            worked_days[emp.id].add(c.day_of_week)
            worked[emp.id] += _hours(c.forced_start, c.forced_end)

    # --- Étape 2 : attribution des jours travaillés ---
    # On répartit pour que tout le monde n'ait pas les mêmes repos
    _assign_work_days(ctx, worked_days, worked)

    # --- Étape 3 : attribution des services ---
    shifts += _assign_services(ctx, worked_days, worked)

    return shifts


# ================================================================== #
#  ATTRIBUTION DES JOURS DE TRAVAIL                                   #
# ================================================================== #

def _assign_work_days(ctx, worked_days, worked):
    """
    Détermine quels jours chaque employé travaille.
    Objectif : éviter que tout le monde soit en repos le même jour.
    Min 2 jours de repos consécutifs si possible.
    """
    days      = ctx['active_days']
    n_days    = len(days)

    # Calcule le nb de jours de travail cible pour chaque employé
    avg_shift = _avg_shift_hours(ctx['config_map'], days)

    for emp in ctx['employees']:
        if worked_days[emp.id]:
            continue  # déjà des jours forcés, on complétera après

        target = ctx['target_hours'][emp.id]
        unavail = ctx['unavail'][emp.id]
        available = [d for d in days if d not in unavail and d not in worked_days[emp.id]]

        n_work = min(len(available), max(1, round(target / max(avg_shift, 1))))
        n_rest = n_days - n_work
        # Au moins 2 jours de repos
        if n_rest < 2:
            n_work = max(1, n_days - 2)

        # Choisit les jours de repos en bloc consécutif
        rest_days = _pick_consecutive_rest(available, n_days - n_work, days)
        work_days = [d for d in available if d not in rest_days][:n_work]

        for d in work_days:
            worked_days[emp.id].add(d)


def _pick_consecutive_rest(available, n_rest, all_days):
    """
    Choisit n_rest jours de repos en favorisant un bloc consécutif.
    Essaie toutes les fenêtres glissantes de taille n_rest.
    """
    if n_rest <= 0:
        return set()
    avail_set = set(available)

    # Fenêtres glissantes sur all_days (circulaire)
    candidates = []
    doubled = all_days + all_days  # pour gérer la circularité lun-dim
    for start in range(len(all_days)):
        window = doubled[start:start + n_rest]
        # Score : combien de jours de la fenêtre sont disponibles
        score = sum(1 for d in window if d in avail_set)
        candidates.append((score, start, window))

    # Trie par score desc, puis par position aléatoire pour la variété
    random.shuffle(candidates)
    candidates.sort(key=lambda x: -x[0])

    best = candidates[0][2] if candidates else []
    return set(best) & avail_set


# ================================================================== #
#  ATTRIBUTION DES SERVICES                                           #
# ================================================================== #

def _assign_services(ctx, worked_days, worked):
    """
    Pour chaque jour de travail de chaque employé,
    attribue matin, soir, ou coupure (matin+soir).
    Règles :
      - Prioriser coupure pour économiser l'effectif
      - Ouverture soir : 1 manager/assistant + 1 coéquipier min
      - Week-end : plus de managers le soir
      - 2e manager le soir → arrivée la plus tardive possible
    """
    shifts     = []
    config_map = ctx['config_map']
    is_mgr     = ctx['is_manager']

    # Traitement jour par jour pour gérer les contraintes inter-employés
    for day in ctx['active_days']:
        day_workers = [e for e in ctx['employees'] if day in worked_days[e.id]]
        if not day_workers:
            continue

        has_morning = (day, 'morning') in config_map
        has_evening = (day, 'evening') in config_map

        # Sépare managers et employés disponibles ce jour
        mgr_workers  = [e for e in day_workers if is_mgr[e.id]]
        emp_workers  = [e for e in day_workers if not is_mgr[e.id]]

        random.shuffle(mgr_workers)
        random.shuffle(emp_workers)

        # --- SERVICE SOIR ---
        evening_assigned = set()  # employee_ids assignés au soir ce jour

        if has_evening:
            cfg_eve = config_map[(day, 'evening')]
            slots   = cfg_eve.slots

            opening_slots  = [s for s in slots if s.slot_type == 'opening']
            arrival_slots  = sorted([s for s in slots if s.slot_type == 'arrival'],
                                    key=lambda s: s.start_time)
            departure_slots= [s for s in slots if s.slot_type == 'departure']

            # -- OUVERTURE --
            # 1 manager + au moins 1 coéquipier dès l'ouverture
            opening_start = opening_slots[0].start_time if opening_slots else cfg_eve.open_time
            opening_end   = opening_slots[0].end_time   if opening_slots and opening_slots[0].end_time else None
            slot_id_open  = opening_slots[0].id if opening_slots else None

            # Choisit le manager de l'ouverture (reste toute la soirée)
            avail_mgrs = [e for e in mgr_workers
                          if 'evening' not in ctx['excl_svc'].get((e.id, day), set())]
            if not avail_mgrs:
                avail_mgrs = mgr_workers  # fallback

            mgr_opener = avail_mgrs[0] if avail_mgrs else None

            # Choisit un coéquipier pour l'ouverture
            avail_emps = [e for e in emp_workers
                          if 'evening' not in ctx['excl_svc'].get((e.id, day), set())]
            emp_opener = avail_emps[0] if avail_emps else None

            # Assigne le manager à l'ouverture → fin de soirée
            eve_end = cfg_eve.close_time
            if mgr_opener:
                end_time = eve_end
                # Si départ possible pour le manager
                if departure_slots and day not in WEEKEND:
                    end_time = departure_slots[0].start_time  # départ le plus tôt
                shifts.append(_make_shift(
                    mgr_opener.id, day, opening_start, end_time, slot_id_open))
                worked[mgr_opener.id] += _hours(opening_start, end_time)
                evening_assigned.add(mgr_opener.id)

            # Assigne le coéquipier à l'ouverture → fin de soirée (ou départ)
            if emp_opener:
                end_time = eve_end
                if departure_slots:
                    end_time = random.choice(departure_slots).start_time
                shifts.append(_make_shift(
                    emp_opener.id, day, opening_start, end_time, slot_id_open))
                worked[emp_opener.id] += _hours(opening_start, end_time)
                evening_assigned.add(emp_opener.id)

            # -- MANAGERS SUPPLÉMENTAIRES --
            # Week-end : on peut avoir plusieurs managers le soir
            # Le 2e manager arrive le plus tard possible
            remaining_mgrs = [e for e in avail_mgrs
                              if e.id not in evening_assigned]
            is_weekend_day = day in WEEKEND

            for i, mgr in enumerate(remaining_mgrs):
                if worked[mgr.id] >= ctx['target_hours'][mgr.id] - 0.5:
                    continue  # déjà à quota

                # Heure d'arrivée : la plus tardive si possible
                if arrival_slots:
                    arr_slot = arrival_slots[-1]  # le plus tard
                    start_t  = arr_slot.start_time
                    slot_id  = arr_slot.id
                else:
                    start_t = cfg_eve.open_time
                    slot_id = None

                end_time = eve_end
                if departure_slots and not is_weekend_day:
                    end_time = departure_slots[-1].start_time

                shifts.append(_make_shift(mgr.id, day, start_t, end_time, slot_id))
                worked[mgr.id] += _hours(start_t, end_time)
                evening_assigned.add(mgr.id)

                # 1 seul manager supplémentaire sauf week-end
                if not is_weekend_day:
                    break

            # -- EMPLOYÉS SOIRÉE (hors ouverture) --
            remaining_emps = [e for e in avail_emps if e.id not in evening_assigned]
            required = cfg_eve.required_staff or 3
            current_count = len(evening_assigned)

            for emp in remaining_emps:
                if current_count >= required:
                    break
                if worked[emp.id] >= ctx['target_hours'][emp.id] - 0.5:
                    continue

                # Heure d'arrivée aléatoire parmi les slots
                if arrival_slots:
                    arr_slot = random.choice(arrival_slots)
                    start_t  = arr_slot.start_time
                    slot_id  = arr_slot.id
                else:
                    start_t = cfg_eve.open_time
                    slot_id = None

                end_time = eve_end
                if departure_slots:
                    end_time = random.choice(departure_slots).start_time

                shifts.append(_make_shift(emp.id, day, start_t, end_time, slot_id))
                worked[emp.id] += _hours(start_t, end_time)
                evening_assigned.add(emp.id)
                current_count += 1

        # --- SERVICE MATIN ---
        if has_morning:
            cfg_mor  = config_map[(day, 'morning')]
            required = cfg_mor.required_staff or 3

            # Priorité : ceux qui travaillent déjà le soir ce jour (coupure)
            # → économise l'effectif
            couture_candidates = [e for e in day_workers
                                  if e.id in evening_assigned
                                  and 'morning' not in ctx['excl_svc'].get((e.id, day), set())
                                  and worked[e.id] + _hours(cfg_mor.open_time, cfg_mor.close_time)
                                      <= ctx['target_hours'][e.id] + 2.0]

            # Puis ceux qui ne sont pas encore assignés ce jour
            fresh_candidates = [e for e in day_workers
                                 if e.id not in evening_assigned
                                 and 'morning' not in ctx['excl_svc'].get((e.id, day), set())]

            # 1 manager en priorité le matin
            morning_assigned = set()
            mgr_morning = next((e for e in couture_candidates + fresh_candidates
                                if is_mgr[e.id]), None)
            all_morning  = couture_candidates + [e for e in fresh_candidates
                                                  if e not in couture_candidates]

            count = 0
            for emp in ([mgr_morning] if mgr_morning else []) + \
                       [e for e in all_morning if e != mgr_morning]:
                if count >= required:
                    break
                if emp is None:
                    continue
                if worked[emp.id] + _hours(cfg_mor.open_time, cfg_mor.close_time) \
                        > ctx['target_hours'][emp.id] + 2.0:
                    continue

                shifts.append(_make_shift(
                    emp.id, day, cfg_mor.open_time, cfg_mor.close_time))
                worked[emp.id] += _hours(cfg_mor.open_time, cfg_mor.close_time)
                morning_assigned.add(emp.id)
                count += 1

    return shifts


# ================================================================== #
#  VALIDATION                                                         #
# ================================================================== #

def _validate(shifts, ctx) -> list:
    anomalies  = []
    config_map = ctx['config_map']
    employees  = {e.id: e for e in ctx['employees']}
    is_mgr     = ctx['is_manager']

    # Index shifts par (employee_id, day)
    shift_idx = {}
    for s in shifts:
        key = (s['employee_id'], s['day_of_week'])
        shift_idx.setdefault(key, []).append(s)

    # Index présents par (day, service_type)
    service_staff = {}
    for s in shifts:
        stype = _guess_service_type(s['day_of_week'], s['start_time'], config_map)
        service_staff.setdefault((s['day_of_week'], stype), []).append(s['employee_id'])

    DAY_NAMES = ['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche']
    SVC_NAMES = {'morning': 'matin', 'evening': 'soir'}

    for (day, stype), cfg in config_map.items():
        present_ids  = service_staff.get((day, stype), [])
        present_emps = [employees[eid] for eid in present_ids if eid in employees]

        # Critique : pas de manager/assistant
        if not any(is_mgr[e.id] for e in present_emps):
            anomalies.append({
                'level':   'critical',
                'message': f"{DAY_NAMES[day]} {SVC_NAMES[stype]} — aucun manager ou assistant",
            })

        # Warning : effectif insuffisant
        if len(present_ids) < (cfg.required_staff or 2):
            anomalies.append({
                'level':   'warning',
                'message': (f"{DAY_NAMES[day]} {SVC_NAMES[stype]} — "
                            f"{len(present_ids)}/{cfg.required_staff} personnes"),
            })

    # Warning : heures hors quota (tolérance ±2h)
    worked = {}
    for s in shifts:
        h = _hours(s['start_time'], s['end_time'])
        worked[s['employee_id']] = worked.get(s['employee_id'], 0) + h

    for emp in ctx['employees']:
        target = ctx['target_hours'][emp.id]
        actual = worked.get(emp.id, 0)
        delta  = actual - target
        if abs(delta) > 2:
            sign = '+' if delta > 0 else ''
            anomalies.append({
                'level':   'warning',
                'message': (f"{emp.name} — {actual:.1f}h planifiées "
                            f"(contrat {target:.1f}h, {sign}{delta:.1f}h)"),
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


def _hours(start: Time, end: Time) -> float:
    if not start or not end:
        return 0.0
    s = start.hour * 60 + start.minute
    e = end.hour   * 60 + end.minute
    return max(0.0, (e - s) / 60)


def _avg_shift_hours(config_map, days) -> float:
    durations = [_hours(cfg.open_time, cfg.close_time)
                 for (day, stype), cfg in config_map.items() if day in days]
    return sum(durations) / len(durations) if durations else 4.0


def _guess_service_type(day, start_time, config_map) -> str:
    candidates = {stype: cfg for (d, stype), cfg in config_map.items() if d == day}
    if not candidates:
        return 'morning'
    if len(candidates) == 1:
        return next(iter(candidates))
    start_min = start_time.hour * 60 + start_time.minute
    best, best_diff = 'morning', float('inf')
    for stype, cfg in candidates.items():
        diff = abs(start_min - (cfg.open_time.hour * 60 + cfg.open_time.minute))
        if diff < best_diff:
            best, best_diff = stype, diff
    return best