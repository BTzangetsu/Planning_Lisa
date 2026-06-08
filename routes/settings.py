from flask import Blueprint, request, jsonify, session
from models import db, Manager, ServiceConfig, ServiceSlot
from datetime import datetime

settings_bp = Blueprint('settings', __name__)


def get_current_manager():
    manager_id = session.get('manager_id')
    if not manager_id:
        return None
    return Manager.query.get(manager_id)


# ------------------------------------------------------------------ #
#  GET  /api/settings                                                 #
#  Retourne toute la config services du manager (tous les jours).    #
# ------------------------------------------------------------------ #
@settings_bp.route('/api/settings', methods=['GET'])
def get_settings():
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    configs = (ServiceConfig.query
               .filter_by(manager_id=manager.id)
               .order_by(ServiceConfig.day_of_week, ServiceConfig.service_type)
               .all())

    return jsonify([c.to_dict() for c in configs])


# ------------------------------------------------------------------ #
#  POST /api/settings                                                 #
#  Crée ou remplace toute la config d'un (jour, service_type).       #
#  Utilisé à l'onboarding et depuis la page Settings.                #
# ------------------------------------------------------------------ #
@settings_bp.route('/api/settings', methods=['POST'])
def save_settings():
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    data  = request.get_json()
    error = _validate_config(data)
    if error:
        return jsonify({'error': error}), 400

    day          = data['day_of_week']
    service_type = data['service_type']

    # Upsert : on supprime l'ancienne config si elle existe
    existing = ServiceConfig.query.filter_by(
        manager_id=manager.id,
        day_of_week=day,
        service_type=service_type
    ).first()
    if existing:
        db.session.delete(existing)
        db.session.flush()

    config = ServiceConfig(
        manager_id=manager.id,
        day_of_week=day,
        service_type=service_type,
        open_time=_parse_time(data['open_time']),
        close_time=_parse_time(data['close_time']),
        required_staff=int(data.get('required_staff', 2)),
        break_start=_parse_time(data.get('break_start')),
        break_end=_parse_time(data.get('break_end')),
    )
    db.session.add(config)
    db.session.flush()  # récupère l'id avant d'ajouter les slots

    for slot_data in data.get('slots', []):
        slot_error = _validate_slot(slot_data)
        if slot_error:
            db.session.rollback()
            return jsonify({'error': f'Slot invalide : {slot_error}'}), 400

        slot = ServiceSlot(
            service_config_id=config.id,
            slot_type=slot_data['slot_type'],
            start_time=_parse_time(slot_data['start_time']),
            end_time=_parse_time(slot_data.get('end_time')),
            required_staff=slot_data.get('required_staff'),
        )
        db.session.add(slot)

    db.session.commit()
    return jsonify(config.to_dict()), 201


# ------------------------------------------------------------------ #
#  DELETE /api/settings/<id>                                          #
#  Supprime une config de service (et ses slots en cascade).         #
# ------------------------------------------------------------------ #
@settings_bp.route('/api/settings/<int:config_id>', methods=['DELETE'])
def delete_settings(config_id):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    config = ServiceConfig.query.filter_by(
        id=config_id, manager_id=manager.id
    ).first()
    if not config:
        return jsonify({'error': 'Config introuvable'}), 404

    db.session.delete(config)
    db.session.commit()
    return jsonify({'success': True})


# ------------------------------------------------------------------ #
#  Helpers                                                            #
# ------------------------------------------------------------------ #
def _parse_time(value):
    """Convertit une string 'HH:MM' en objet datetime.time, ou None."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%H:%M').time()
    except ValueError:
        return None


def _validate_config(data):
    if data.get('day_of_week') not in range(7):
        return 'day_of_week invalide (0=lun, 6=dim)'
    if data.get('service_type') not in ('morning', 'evening'):
        return 'service_type invalide'
    if not data.get('open_time') or not data.get('close_time'):
        return 'open_time et close_time requis'
    try:
        staff = int(data.get('required_staff', 2))
        if staff < 1 or staff > 20:
            raise ValueError
    except (TypeError, ValueError):
        return 'required_staff invalide (entre 1 et 20)'
    return None


def _validate_slot(slot):
    if slot.get('slot_type') not in ('opening', 'arrival', 'departure', 'close'):
        return 'slot_type invalide'
    if not slot.get('start_time'):
        return 'start_time requis'
    return None