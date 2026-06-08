from flask import Blueprint, render_template, redirect, url_for, session

main_bp = Blueprint('main', __name__)


def require_auth():
    """Redirige vers login si pas de session."""
    if not session.get('manager_id'):
        return redirect(url_for('main.login'))
    return None


@main_bp.route('/')
def index():
    if session.get('manager_id'):
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))


@main_bp.route('/login')
def login():
    if session.get('manager_id'):
        return redirect(url_for('main.dashboard'))
    return render_template('login.html')


@main_bp.route('/dashboard')
def dashboard():
    redir = require_auth()
    if redir: return redir
    return render_template('dashboard.html',
                           active_page='dashboard',
                           manager_pseudo=session.get('manager_pseudo', ''))


@main_bp.route('/team')
def team():
    redir = require_auth()
    if redir: return redir
    return render_template('team.html', active_page='team')


@main_bp.route('/settings')
def settings():
    redir = require_auth()
    if redir: return redir
    return render_template('settings.html', active_page='settings')


@main_bp.route('/planning/<string:week_start>')
def planning(week_start):
    redir = require_auth()
    if redir: return redir
    return render_template('planning.html',
                           active_page='dashboard',
                           week_start=week_start)


@main_bp.route('/admin/feedbacks')
def admin_feedbacks():
    return render_template('admin_feedbacks.html')