from flask import Blueprint, request, jsonify, session
from models import db, Manager, Schedule, Shift, PlanningConstraint, Employee, ServiceConfig
from datetime import date, timedelta

schedules_bp = Blueprint('schedules', __name__)


def get_current_manager():
    manager_id = session.get('manager_id')
    if not manager_id:
        return None
    return Manager.query.get(manager_id)


# ------------------------------------------------------------------ #
#  GET /api/schedules                                                 #
#  Liste tous les plannings du manager (sans les shifts).            #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules', methods=['GET'])
def list_schedules():
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedules = (Schedule.query
                 .filter_by(manager_id=manager.id)
                 .order_by(Schedule.week_start.desc())
                 .all())

    return jsonify([s.to_dict() for s in schedules])


# ------------------------------------------------------------------ #
#  GET /api/schedules/<week_start>                                    #
#  Retourne le planning complet d'une semaine avec ses shifts.       #
#  week_start : format YYYY-MM-DD (doit être un lundi).              #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>', methods=['GET'])
def get_schedule(week_start):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    parsed = _parse_monday(week_start)
    if not parsed:
        return jsonify({'error': 'Format de date invalide (YYYY-MM-DD, lundi)'}), 400

    schedule = Schedule.query.filter_by(
        manager_id=manager.id, week_start=parsed
    ).first()

    if not schedule:
        return jsonify(None), 200  # pas de planning cette semaine : réponse vide

    data = schedule.to_dict(with_shifts=True)

    # Enrichit chaque shift avec le nom de l'employé pour le front
    employees = {e.id: e for e in Employee.query.filter_by(
        manager_id=manager.id).all()}
    for shift in data['shifts']:
        emp = employees.get(shift['employee_id'])
        shift['employee_name'] = emp.name if emp else '?'
        shift['employee_role'] = emp.role if emp else '?'

    return jsonify(data)


# ------------------------------------------------------------------ #
#  POST /api/schedules                                                #
#  Crée un nouveau planning vide (draft) pour une semaine.           #
#  Option copy_previous=true : copie les shifts de la semaine d'avant#
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules', methods=['POST'])
def create_schedule():
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    data  = request.get_json()
    parsed = _parse_monday(data.get('week_start'))
    if not parsed:
        return jsonify({'error': 'week_start invalide (YYYY-MM-DD, lundi)'}), 400

    if parsed <= date.today():
        return jsonify({'error': 'Impossible de créer un planning dans le passé'}), 400

    existing = Schedule.query.filter_by(
        manager_id=manager.id, week_start=parsed
    ).first()
    if existing:
        # Si c'est un draft sans shifts, on le réutilise silencieusement
        if existing.status == 'draft' and len(existing.shifts) == 0:
            db.session.commit()
            return jsonify(existing.to_dict(with_shifts=True)), 200
        return jsonify({'error': 'Un planning existe déjà pour cette semaine'}), 409

    schedule = Schedule(manager_id=manager.id, week_start=parsed)
    db.session.add(schedule)
    db.session.flush()

    if data.get('copy_previous'):
        prev_monday = parsed - timedelta(weeks=1)
        prev = Schedule.query.filter_by(
            manager_id=manager.id, week_start=prev_monday
        ).first()
        if prev:
            for s in prev.shifts:
                db.session.add(Shift(
                    schedule_id=schedule.id,
                    employee_id=s.employee_id,
                    day_of_week=s.day_of_week,
                    start_time=s.start_time,
                    end_time=s.end_time,
                    slot_id=s.slot_id,
                ))

    db.session.commit()
    return jsonify(schedule.to_dict(with_shifts=True)), 201


# ------------------------------------------------------------------ #
#  PUT /api/schedules/<week_start>/publish                           #
#  Publie un planning (draft → published).                           #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>/publish', methods=['PUT'])
def publish_schedule(week_start):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedule = _get_schedule_or_404(manager, week_start)
    if isinstance(schedule, tuple):
        return schedule

    schedule.status = 'published'
    db.session.commit()
    return jsonify(schedule.to_dict())


# ------------------------------------------------------------------ #
#  DELETE /api/schedules/<week_start>                                #
#  Supprime un planning draft (et ses shifts en cascade).            #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>', methods=['DELETE'])
def delete_schedule(week_start):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedule = _get_schedule_or_404(manager, week_start)
    if isinstance(schedule, tuple):
        return schedule

    if schedule.status == 'published':
        return jsonify({'error': 'Impossible de supprimer un planning publié'}), 403

    db.session.delete(schedule)
    db.session.commit()
    return jsonify({'success': True})


# ================================================================== #
#  SHIFTS                                                             #
# ================================================================== #

# ------------------------------------------------------------------ #
#  POST /api/schedules/<week_start>/shifts                           #
#  Ajoute un shift manuellement sur un planning.                     #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>/shifts', methods=['POST'])
def add_shift(week_start):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedule = _get_schedule_or_404(manager, week_start)
    if isinstance(schedule, tuple):
        return schedule

    if _is_past_week(schedule.week_start):
        return jsonify({'error': 'Modification impossible sur une semaine passée'}), 403

    data  = request.get_json()
    error = _validate_shift(data, manager.id)
    if error:
        return jsonify({'error': error}), 400

    shift = Shift(
        schedule_id=schedule.id,
        employee_id=int(data['employee_id']),
        day_of_week=int(data['day_of_week']),
        start_time=_parse_time(data['start_time']),
        end_time=_parse_time(data['end_time']),
        slot_id=data.get('slot_id'),
    )
    db.session.add(shift)
    db.session.commit()
    return jsonify(shift.to_dict()), 201


# ------------------------------------------------------------------ #
#  PUT /api/schedules/<week_start>/shifts/<shift_id>                 #
#  Modifie un shift existant.                                        #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>/shifts/<int:shift_id>', methods=['PUT'])
def update_shift(week_start, shift_id):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedule = _get_schedule_or_404(manager, week_start)
    if isinstance(schedule, tuple):
        return schedule

    if _is_past_week(schedule.week_start):
        return jsonify({'error': 'Modification impossible sur une semaine passée'}), 403

    shift = Shift.query.filter_by(id=shift_id, schedule_id=schedule.id).first()
    if not shift:
        return jsonify({'error': 'Shift introuvable'}), 404

    data  = request.get_json()
    error = _validate_shift(data, manager.id)
    if error:
        return jsonify({'error': error}), 400

    shift.employee_id = int(data['employee_id'])
    shift.day_of_week = int(data['day_of_week'])
    shift.start_time  = _parse_time(data['start_time'])
    shift.end_time    = _parse_time(data['end_time'])
    shift.slot_id     = data.get('slot_id')
    db.session.commit()
    return jsonify(shift.to_dict())


# ------------------------------------------------------------------ #
#  DELETE /api/schedules/<week_start>/shifts/<shift_id>              #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>/shifts/<int:shift_id>', methods=['DELETE'])
def delete_shift(week_start, shift_id):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedule = _get_schedule_or_404(manager, week_start)
    if isinstance(schedule, tuple):
        return schedule

    if _is_past_week(schedule.week_start):
        return jsonify({'error': 'Modification impossible sur une semaine passée'}), 403

    shift = Shift.query.filter_by(id=shift_id, schedule_id=schedule.id).first()
    if not shift:
        return jsonify({'error': 'Shift introuvable'}), 404

    db.session.delete(shift)
    db.session.commit()
    return jsonify({'success': True})


# ================================================================== #
#  CONTRAINTES                                                        #
# ================================================================== #

# ------------------------------------------------------------------ #
#  POST /api/schedules/<week_start>/constraints                      #
#  Ajoute ou remplace les contraintes d'un employé pour ce planning. #
#  Envoie la liste complète des contraintes de l'employé → remplace  #
#  tout ce qui existait.                                             #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>/constraints', methods=['POST'])
def set_constraints(week_start):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedule = _get_schedule_or_404(manager, week_start)
    if isinstance(schedule, tuple):
        return schedule

    data        = request.get_json()
    employee_id = data.get('employee_id')
    constraints = data.get('constraints', [])

    if not Employee.query.filter_by(id=employee_id, manager_id=manager.id).first():
        return jsonify({'error': 'Employé introuvable'}), 404

    # Supprime les anciennes contraintes de cet employé sur ce planning
    PlanningConstraint.query.filter_by(
        schedule_id=schedule.id, employee_id=employee_id
    ).delete()

    for c in constraints:
        ctype = c.get('constraint_type')
        if ctype not in ('unavailable', 'forced', 'exclude_service'):
            return jsonify({'error': f'constraint_type invalide : {ctype}'}), 400

        db.session.add(PlanningConstraint(
            schedule_id=schedule.id,
            employee_id=employee_id,
            constraint_type=ctype,
            day_of_week=c.get('day_of_week'),
            forced_start=_parse_time(c.get('forced_start')),
            forced_end=_parse_time(c.get('forced_end')),
            exclude_service_type=c.get('exclude_service_type'),
            hours_override=c.get('hours_override'),
        ))

    db.session.commit()
    return jsonify({'success': True})


# ================================================================== #
#  Helpers privés                                                     #
# ================================================================== #
def _parse_monday(value):
    """Parse YYYY-MM-DD et vérifie que c'est bien un lundi."""
    try:
        d = date.fromisoformat(value)
        return d if d.weekday() == 0 else None
    except (TypeError, ValueError):
        return None


def _is_past_week(week_start):
    """True si la semaine est entièrement passée."""
    return week_start + timedelta(days=6) < date.today()


def _get_schedule_or_404(manager, week_start_str):
    parsed = _parse_monday(week_start_str)
    if not parsed:
        return jsonify({'error': 'week_start invalide'}), 400
    schedule = Schedule.query.filter_by(
        manager_id=manager.id, week_start=parsed
    ).first()
    if not schedule:
        return jsonify({'error': 'Planning introuvable'}), 404
    return schedule


def _parse_time(value):
    from datetime import datetime
    if not value:
        return None
    try:
        return datetime.strptime(value, '%H:%M').time()
    except ValueError:
        return None


def _validate_shift(data, manager_id):
    try:
        day = int(data.get('day_of_week'))
        if day not in range(7):
            return 'day_of_week invalide (0=lun, 6=dim)'
    except (TypeError, ValueError):
        return 'day_of_week invalide'

    if not data.get('start_time') or not data.get('end_time'):
        return 'start_time et end_time requis'

    emp = Employee.query.filter_by(
        id=data.get('employee_id'), manager_id=manager_id, is_active=True
    ).first()
    if not emp:
        return 'Employé introuvable'

    return None


# ================================================================== #
#  GÉNÉRATION                                                         #
# ================================================================== #

# ------------------------------------------------------------------ #
#  POST /api/schedules/<week_start>/generate                         #
#  Lance la génération automatique. Ne persiste pas encore —         #
#  le manager valide ou relance depuis le front.                     #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>/generate', methods=['POST'])
def generate_schedule(week_start):
    from services.generator import generate
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedule = _get_schedule_or_404(manager, week_start)
    if isinstance(schedule, tuple):
        return schedule

    if _is_past_week(schedule.week_start):
        return jsonify({'error': 'Génération impossible sur une semaine passée'}), 403

    try:
        result = generate(schedule.id)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    # Sérialise les objets time en HH:MM pour le front
    for s in result['shifts']:
        s['start_time'] = s['start_time'].strftime('%H:%M')
        s['end_time']   = s['end_time'].strftime('%H:%M')

    return jsonify(result)


# ------------------------------------------------------------------ #
#  POST /api/schedules/<week_start>/generate/confirm                 #
#  Le manager valide le planning généré : on persiste les shifts.    #
# ------------------------------------------------------------------ #
@schedules_bp.route('/api/schedules/<string:week_start>/generate/confirm', methods=['POST'])
def confirm_generated(week_start):
    from services.generator import persist
    from datetime import datetime
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    schedule = _get_schedule_or_404(manager, week_start)
    if isinstance(schedule, tuple):
        return schedule

    data   = request.get_json()
    shifts = data.get('shifts', [])
    if not shifts:
        return jsonify({'error': 'Aucun shift à persister'}), 400

    # Reconvertit HH:MM en objets time
    parsed = []
    for s in shifts:
        parsed.append({
            'employee_id': s['employee_id'],
            'day_of_week': s['day_of_week'],
            'start_time':  datetime.strptime(s['start_time'], '%H:%M').time(),
            'end_time':    datetime.strptime(s['end_time'],   '%H:%M').time(),
            'slot_id':     s.get('slot_id'),
        })

    persist(schedule.id, parsed)
    return jsonify(schedule.to_dict(with_shifts=True))