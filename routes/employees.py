from flask import Blueprint, request, jsonify, session
from models import db, Employee, Manager

employees_bp = Blueprint('employees', __name__)


def get_current_manager():
    manager_id = session.get('manager_id')
    if not manager_id:
        return None
    return Manager.query.get(manager_id)


@employees_bp.route('/api/employees', methods=['GET'])
def list_employees():
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    employees = (Employee.query
                 .filter_by(manager_id=manager.id, is_active=True)
                 .order_by(Employee.role, Employee.name)
                 .all())

    return jsonify([e.to_dict() for e in employees])


@employees_bp.route('/api/employees', methods=['POST'])
def create_employee():
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    data  = request.get_json()
    error = _validate(data)
    if error:
        return jsonify({'error': error}), 400

    employee = Employee(
        name=data['name'].strip(),
        role=data['role'],
        hours_per_week=float(data['hours_per_week']),
        manager_id=manager.id
    )
    db.session.add(employee)
    db.session.commit()

    return jsonify(employee.to_dict()), 201


@employees_bp.route('/api/employees/<int:employee_id>', methods=['PUT'])
def update_employee(employee_id):
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    employee = Employee.query.filter_by(
        id=employee_id, manager_id=manager.id, is_active=True
    ).first()
    if not employee:
        return jsonify({'error': 'Employé introuvable'}), 404

    data  = request.get_json()
    error = _validate(data)
    if error:
        return jsonify({'error': error}), 400

    employee.name           = data['name'].strip()
    employee.role           = data['role']
    employee.hours_per_week = float(data['hours_per_week'])
    db.session.commit()

    return jsonify(employee.to_dict())


@employees_bp.route('/api/employees/<int:employee_id>', methods=['DELETE'])
def delete_employee(employee_id):
    """Soft delete — conserve l'historique des plannings."""
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    employee = Employee.query.filter_by(
        id=employee_id, manager_id=manager.id, is_active=True
    ).first()
    if not employee:
        return jsonify({'error': 'Employé introuvable'}), 404

    employee.is_active = False
    db.session.commit()

    return jsonify({'success': True})


# ------------------------------------------------------------------ #
#  Validation partagée create / update                                #
# ------------------------------------------------------------------ #
def _validate(data):
    name  = (data.get('name') or '').strip()
    role  = data.get('role')
    hours = data.get('hours_per_week')

    if not name:
        return 'Nom requis'
    if len(name) > 100:
        return 'Nom trop long (100 caractères max)'
    if role not in ('manager', 'assistant', 'employee'):
        return 'Rôle invalide'
    try:
        h = float(hours)
        if h <= 0 or h > 60:
            raise ValueError
    except (TypeError, ValueError):
        return 'Heures invalides (entre 1 et 60)'
    return None