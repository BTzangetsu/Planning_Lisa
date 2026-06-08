from flask import Blueprint, request, jsonify, session
from models import db, Feedback, Manager

feedbacks_bp = Blueprint('feedbacks', __name__)


def get_current_manager():
    manager_id = session.get('manager_id')
    if not manager_id:
        return None
    return Manager.query.get(manager_id)


# ------------------------------------------------------------------ #
#  POST /api/feedbacks                                                #
#  Un manager soumet un retour depuis la page d'accueil.             #
# ------------------------------------------------------------------ #
@feedbacks_bp.route('/api/feedbacks', methods=['POST'])
def create_feedback():
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    data    = request.get_json()
    message = (data.get('message') or '').strip()

    if not message:
        return jsonify({'error': 'Message requis'}), 400
    if len(message) > 2000:
        return jsonify({'error': 'Message trop long (2000 caractères max)'}), 400

    feedback = Feedback(manager_id=manager.id, message=message)
    db.session.add(feedback)
    db.session.commit()

    return jsonify(feedback.to_dict()), 201


# ------------------------------------------------------------------ #
#  GET /api/feedbacks/mine                                            #
#  Un manager consulte ses propres retours et leur statut.           #
# ------------------------------------------------------------------ #
@feedbacks_bp.route('/api/feedbacks/mine', methods=['GET'])
def my_feedbacks():
    manager = get_current_manager()
    if not manager:
        return jsonify({'error': 'Non authentifié'}), 401

    feedbacks = (Feedback.query
                 .filter_by(manager_id=manager.id)
                 .order_by(Feedback.created_at.desc())
                 .all())

    return jsonify([f.to_dict() for f in feedbacks])