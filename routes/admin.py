from flask import Blueprint, request, jsonify, session
from models import db, Feedback
import os

admin_bp = Blueprint('admin', __name__)


def _check_admin():
    """
    Authentification admin minimaliste par token statique
    passé en header : X-Admin-Token.
    La valeur est définie dans la variable d'env ADMIN_TOKEN.
    """
    token = request.headers.get('X-Admin-Token', '')
    admin_token = os.environ.get('ADMIN_TOKEN', '')
    if not admin_token or token != admin_token:
        return False
    return True


# ------------------------------------------------------------------ #
#  GET /api/admin/feedbacks                                           #
#  Liste tous les feedbacks, optionnellement filtrés par statut.     #
#  ?status=unread|refused|in_progress|integrated                     #
# ------------------------------------------------------------------ #
@admin_bp.route('/api/admin/feedbacks', methods=['GET'])
def list_feedbacks():
    if not _check_admin():
        return jsonify({'error': 'Non autorisé'}), 403

    status = request.args.get('status')
    query  = Feedback.query.order_by(Feedback.created_at.desc())

    if status:
        if status not in ('unread', 'refused', 'in_progress', 'integrated'):
            return jsonify({'error': 'Statut invalide'}), 400
        query = query.filter_by(status=status)

    feedbacks = query.all()

    return jsonify({
        'feedbacks': [f.to_dict() for f in feedbacks],
        'counts': {
            'unread':      Feedback.query.filter_by(status='unread').count(),
            'refused':     Feedback.query.filter_by(status='refused').count(),
            'in_progress': Feedback.query.filter_by(status='in_progress').count(),
            'integrated':  Feedback.query.filter_by(status='integrated').count(),
        }
    })


# ------------------------------------------------------------------ #
#  PUT /api/admin/feedbacks/<id>                                      #
#  Change le statut d'un feedback.                                   #
# ------------------------------------------------------------------ #
@admin_bp.route('/api/admin/feedbacks/<int:feedback_id>', methods=['PUT'])
def update_feedback(feedback_id):
    if not _check_admin():
        return jsonify({'error': 'Non autorisé'}), 403

    feedback = Feedback.query.get(feedback_id)
    if not feedback:
        return jsonify({'error': 'Feedback introuvable'}), 404

    data   = request.get_json()
    status = data.get('status')

    if status not in ('unread', 'refused', 'in_progress', 'integrated'):
        return jsonify({'error': 'Statut invalide'}), 400

    feedback.status = status
    db.session.commit()
    return jsonify(feedback.to_dict())


# ------------------------------------------------------------------ #
#  DELETE /api/admin/feedbacks/<id>                                   #
#  Supprime définitivement un feedback.                              #
# ------------------------------------------------------------------ #
@admin_bp.route('/api/admin/feedbacks/<int:feedback_id>', methods=['DELETE'])
def delete_feedback(feedback_id):
    if not _check_admin():
        return jsonify({'error': 'Non autorisé'}), 403

    feedback = Feedback.query.get(feedback_id)
    if not feedback:
        return jsonify({'error': 'Feedback introuvable'}), 404

    db.session.delete(feedback)
    db.session.commit()
    return jsonify({'success': True})