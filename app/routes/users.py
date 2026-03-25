"""
Маршруты для работы с пользователями (для админа)
Дополнительные функции управления пользователями
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps

from app import db
from app.models import User, ProxyKey, LoginAttempt

users_bp = Blueprint('users', __name__)


def admin_required(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('keys.list_keys'))
        return f(*args, **kwargs)
    return decorated_function


@users_bp.route('/')
@login_required
@admin_required
def index():
    """Перенаправление на список пользователей в админке"""
    return redirect(url_for('admin.users_list'))


@users_bp.route('/<int:user_id>/keys')
@login_required
@admin_required
def user_keys(user_id):
    """Список ключей пользователя"""
    user = User.query.get_or_404(user_id)
    
    keys = ProxyKey.query.filter_by(user_id=user_id).order_by(
        ProxyKey.created_at.desc()
    ).all()
    
    return render_template('admin/users/keys.html', user=user, keys=keys)


@users_bp.route('/<int:user_id>/assign-key', methods=['POST'])
@login_required
@admin_required
def assign_key(user_id):
    """Привязка существующего ключа к пользователю"""
    user = User.query.get_or_404(user_id)
    key_id = request.form.get('key_id', type=int)
    
    if not key_id:
        flash('Не указан ключ', 'danger')
        return redirect(url_for('admin.user_manage', user_id=user_id))
    
    key = ProxyKey.query.get_or_404(key_id)
    key.user_id = user_id
    db.session.commit()
    
    flash(f'Ключ "{key.name}" привязан к пользователю {user.email}', 'success')
    return redirect(url_for('admin.user_manage', user_id=user_id))


@users_bp.route('/<int:user_id>/unassign-key/<int:key_id>', methods=['POST'])
@login_required
@admin_required
def unassign_key(user_id, key_id):
    """Отвязка ключа от пользователя"""
    key = ProxyKey.query.get_or_404(key_id)
    
    if key.user_id != user_id:
        flash('Ключ не принадлежит этому пользователю', 'danger')
        return redirect(url_for('admin.user_manage', user_id=user_id))
    
    key.user_id = None
    db.session.commit()
    
    flash(f'Ключ "{key.name}" отвязан от пользователя', 'success')
    return redirect(url_for('admin.user_manage', user_id=user_id))


@users_bp.route('/<int:user_id>/login-history')
@login_required
@admin_required
def login_history(user_id):
    """История входов пользователя"""
    user = User.query.get_or_404(user_id)
    
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    attempts = LoginAttempt.query.filter_by(email=user.email).order_by(
        LoginAttempt.timestamp.desc()
    ).paginate(page=page, per_page=per_page, error_out=False)
    
    return render_template('admin/users/login_history.html', user=user, attempts=attempts)


@users_bp.route('/<int:user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def reset_password(user_id):
    """Сброс пароля пользователя (генерация временного)"""
    import secrets
    
    user = User.query.get_or_404(user_id)
    
    # Генерируем временный пароль
    temp_password = secrets.token_urlsafe(12)
    user.set_password(temp_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()
    
    flash(f'Временный пароль для {user.email}: {temp_password}', 'warning')
    return redirect(url_for('admin.user_manage', user_id=user_id))


@users_bp.route('/api/search')
@login_required
@admin_required
def api_search():
    """API поиска пользователей"""
    query = request.args.get('q', '').strip()
    
    if len(query) < 2:
        return jsonify([])
    
    users = User.query.filter(
        User.email.ilike(f'%{query}%')
    ).limit(10).all()
    
    return jsonify([
        {
            'id': u.id,
            'email': u.email,
            'status': u.get_status(),
            'is_admin': u.is_admin
        }
        for u in users
    ])


@users_bp.route('/api/unassigned-keys')
@login_required
@admin_required
def api_unassigned_keys():
    """API получения непривязанных ключей"""
    keys = ProxyKey.query.filter_by(user_id=None).order_by(
        ProxyKey.created_at.desc()
    ).all()
    
    return jsonify([
        {
            'id': k.id,
            'name': k.name,
            'status': k.get_status()
        }
        for k in keys
    ])