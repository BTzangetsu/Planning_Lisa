from flask import Blueprint, request, jsonify, session
from models import db, Manager

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/api/auth/login', methods=['POST'])
def login():
    """
    Connexion ou création d'un manager par pseudo.
    Retourne is_new=True si c'est la première fois — le front
    redirige alors vers la config des services.
    """
    data = request.get_json()
    pseudo = (data.get('pseudo') or '').strip()

    if not pseudo:
        return jsonify({'error': 'Pseudo requis'}), 400
    if len(pseudo) > 80:
        return jsonify({'error': 'Pseudo trop long (80 caractères max)'}), 400
    print("i start de squery")
    manager = Manager.query.filter_by(pseudo=pseudo).first()
    print("finish the query")
    is_new = manager is None

    if is_new:
        manager = Manager(pseudo=pseudo)
        db.session.add(manager)
        db.session.commit()

    session.permanent = True
    session['manager_id'] = manager.id
    session['manager_pseudo'] = manager.pseudo

    return jsonify({
        'manager': manager.to_dict(),
        'is_new':  is_new,
    })


@auth_bp.route('/api/auth/me', methods=['GET'])
def me():
    """
    Vérifie si une session est active.
    Utilisé au chargement de l'app pour éviter de redemander le pseudo.
    """
    manager_id = session.get('manager_id')
    if not manager_id:
        return jsonify({'authenticated': False}), 401

    manager = Manager.query.get(manager_id)
    if not manager:
        session.clear()
        return jsonify({'authenticated': False}), 401
    session['manager_pseudo'] = manager.pseudo

    return jsonify({
        'authenticated': True,
        'manager': manager.to_dict(),
    })


@auth_bp.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})