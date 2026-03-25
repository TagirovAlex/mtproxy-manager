"""
Маршруты панели администратора
"""

from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import User, ProxyKey, Settings, LoginAttempt
from app.forms import SettingsForm, UserManageForm, ConfirmActionForm
from app.services.mtg_service import get_mtg_service
from app.services.system_monitor import SystemMonitor
from app.services.traffic_monitor import TrafficMonitor

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    """Декоратор для проверки прав администратора"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Необходимо войти в систему', 'warning')
            return redirect(url_for('auth.login'))
        if not current_user.is_admin:
            flash('Доступ запрещён. Требуются права администратора.', 'danger')
            return redirect(url_for('keys.list_keys'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Главная страница панели администратора"""
    # Статистика системы
    system_stats = SystemMonitor.get_full_stats()
    system_health = SystemMonitor.check_system_health()
    
    # Статус MTG
    mtg_service = get_mtg_service()
    mtg_status = mtg_service.get_status()
    
    # Статистика трафика
    traffic_monitor = TrafficMonitor()
    traffic_stats = traffic_monitor.get_total_stats()
    
    # Статистика пользователей
    users_stats = {
        'total': User.query.count(),
        'approved': User.query.filter_by(is_approved=True).count(),
        'pending': User.query.filter_by(is_approved=False, is_blocked=False).count(),
        'blocked': User.query.filter_by(is_blocked=True).count(),
        'admins': User.query.filter_by(is_admin=True).count()
    }
    
    # Статистика ключей
    keys_stats = {
        'total': ProxyKey.query.count(),
        'active': ProxyKey.query.filter_by(is_active=True, is_blocked=False).count(),
        'blocked': ProxyKey.query.filter_by(is_blocked=True).count(),
        'with_limit': ProxyKey.query.filter(ProxyKey.traffic_limit.isnot(None)).count()
    }
    
    # Последние попытки входа
    recent_logins = LoginAttempt.query.order_by(
        LoginAttempt.timestamp.desc()
    ).limit(10).all()
    
    return render_template('admin/dashboard.html',
        system_stats=system_stats,
        system_health=system_health,
        mtg_status=mtg_status,
        traffic_stats=traffic_stats,
        users_stats=users_stats,
        keys_stats=keys_stats,
        recent_logins=recent_logins
    )


@admin_bp.route('/mtg/start', methods=['POST'])
@login_required
@admin_required
def mtg_start():
    """Запуск MTG Proxy"""
    mtg_service = get_mtg_service()
    success, message = mtg_service.start()
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/mtg/stop', methods=['POST'])
@login_required
@admin_required
def mtg_stop():
    """Остановка MTG Proxy"""
    mtg_service = get_mtg_service()
    success, message = mtg_service.stop()
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/mtg/restart', methods=['POST'])
@login_required
@admin_required
def mtg_restart():
    """Перезапуск MTG Proxy"""
    mtg_service = get_mtg_service()
    success, message = mtg_service.restart()
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/mtg/reload', methods=['POST'])
@login_required
@admin_required
def mtg_reload():
    """Перезагрузка конфигурации MTG"""
    mtg_service = get_mtg_service()
    success, message = mtg_service.reload_config()
    
    if success:
        flash('Конфигурация перезагружена', 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@admin_required
def settings():
    """Настройки приложения"""
    form = SettingsForm()
    
    if request.method == 'GET':
        # Заполняем форму текущими значениями
        form.server_domain.data = Settings.get('server_domain', 'localhost')
        form.mtg_port.data = Settings.get('mtg_port', 443)
        form.max_keys_per_user.data = Settings.get('max_keys_per_user', 5)
        form.auto_backup_enabled.data = Settings.get('auto_backup_enabled', False)
        form.auto_backup_interval.data = Settings.get('auto_backup_interval', 'daily')
    
    if form.validate_on_submit():
        try:
            Settings.set('server_domain', form.server_domain.data, 'string')
            Settings.set('mtg_port', str(form.mtg_port.data), 'int')
            Settings.set('max_keys_per_user', str(form.max_keys_per_user.data), 'int')
            Settings.set('auto_backup_enabled', str(form.auto_backup_enabled.data).lower(), 'bool')
            Settings.set('auto_backup_interval', form.auto_backup_interval.data, 'string')
            
            flash('Настройки сохранены', 'success')
            
            # Перезагружаем конфигурацию MTG если изменился порт
            mtg_service = get_mtg_service()
            if mtg_service.get_status()['running']:
                mtg_service.reload_config()
                flash('Конфигурация MTG обновлена', 'info')
            
            return redirect(url_for('admin.settings'))
            
        except Exception as e:
            flash(f'Ошибка сохранения настроек: {str(e)}', 'danger')
    
    return render_template('admin/settings.html', form=form)


@admin_bp.route('/users')
@login_required
@admin_required
def users_list():
    """Список всех пользователей"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Фильтры
    status_filter = request.args.get('status', 'all')
    
    query = User.query
    
    if status_filter == 'pending':
        query = query.filter_by(is_approved=False, is_blocked=False)
    elif status_filter == 'approved':
        query = query.filter_by(is_approved=True, is_blocked=False)
    elif status_filter == 'blocked':
        query = query.filter_by(is_blocked=True)
    elif status_filter == 'admin':
        query = query.filter_by(is_admin=True)
    
    users = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/users.html', 
        users=users, 
        status_filter=status_filter
    )


@admin_bp.route('/users/<int:user_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def user_manage(user_id):
    """Управление пользователем"""
    user = User.query.get_or_404(user_id)
    form = UserManageForm(obj=user)
    
    if form.validate_on_submit():
        # Нельзя снять права админа с самого себя
        if user.id == current_user.id and not form.is_admin.data:
            flash('Вы не можете снять права администратора с себя', 'danger')
            return redirect(url_for('admin.user_manage', user_id=user_id))
        
        # Нельзя заблокировать самого себя
        if user.id == current_user.id and form.is_blocked.data:
            flash('Вы не можете заблокировать себя', 'danger')
            return redirect(url_for('admin.user_manage', user_id=user_id))
        
        user.is_approved = form.is_approved.data
        user.is_admin = form.is_admin.data
        user.is_blocked = form.is_blocked.data
        
        db.session.commit()
        flash('Данные пользователя обновлены', 'success')
        return redirect(url_for('admin.users_list'))
    
    # Ключи пользователя
    user_keys = ProxyKey.query.filter_by(user_id=user_id).all()
    
    return render_template('admin/user_manage.html', 
        user=user, 
        form=form,
        user_keys=user_keys
    )


@admin_bp.route('/users/<int:user_id>/approve', methods=['POST'])
@login_required
@admin_required
def user_approve(user_id):
    """Быстрое подтверждение пользователя"""
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f'Пользователь {user.email} подтверждён', 'success')
    return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/block', methods=['POST'])
@login_required
@admin_required
def user_block(user_id):
    """Быстрая блокировка пользователя"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Вы не можете заблокировать себя', 'danger')
        return redirect(url_for('admin.users_list'))
    
    user.is_blocked = True
    db.session.commit()
    flash(f'Пользователь {user.email} заблокирован', 'success')
    return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/unblock', methods=['POST'])
@login_required
@admin_required
def user_unblock(user_id):
    """Быстрая разблокировка пользователя"""
    user = User.query.get_or_404(user_id)
    user.is_blocked = False
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()
    flash(f'Пользователь {user.email} разблокирован', 'success')
    return redirect(url_for('admin.users_list'))


@admin_bp.route('/users/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def user_delete(user_id):
    """Удаление пользователя"""
    user = User.query.get_or_404(user_id)
    
    if user.id == current_user.id:
        flash('Вы не можете удалить себя', 'danger')
        return redirect(url_for('admin.users_list'))
    
    # Отвязываем ключи пользователя
    ProxyKey.query.filter_by(user_id=user_id).update({'user_id': None})
    
    email = user.email
    db.session.delete(user)
    db.session.commit()
    
    flash(f'Пользователь {email} удалён', 'success')
    return redirect(url_for('admin.users_list'))


@admin_bp.route('/api/system-stats')
@login_required
@admin_required
def api_system_stats():
    """API для получения статистики системы (для AJAX обновления)"""
    system_stats = SystemMonitor.get_full_stats()
    system_health = SystemMonitor.check_system_health()
    
    mtg_service = get_mtg_service()
    mtg_status = mtg_service.get_status()
    
    return jsonify({
        'system': system_stats,
        'health': system_health,
        'mtg': mtg_status
    })


@admin_bp.route('/api/traffic-stats')
@login_required
@admin_required
def api_traffic_stats():
    """API для получения статистики трафика"""
    traffic_monitor = TrafficMonitor()
    
    period = request.args.get('period', 'day')
    stats = traffic_monitor.get_all_keys_stats(period)
    total = traffic_monitor.get_total_stats()
    
    return jsonify({
        'keys': stats,
        'total': total
    })