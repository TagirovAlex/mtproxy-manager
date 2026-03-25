"""
Маршруты управления резервными копиями
"""

import os
from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, send_file, current_app
from flask_login import login_required, current_user

from app.forms import BackupForm
from app.services.backup_service import BackupService, get_backup_service

backup_bp = Blueprint('backup', __name__)


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


@backup_bp.route('/')
@login_required
@admin_required
def index():
    """Список резервных копий"""
    backup_service = get_backup_service()
    
    backups = backup_service.get_all_backups()
    settings = backup_service.get_backup_settings()
    
    form = BackupForm()
    
    return render_template('backup/index.html',
        backups=backups,
        settings=settings,
        form=form
    )


@backup_bp.route('/create', methods=['POST'])
@login_required
@admin_required
def create():
    """Создание резервной копии"""
    form = BackupForm()
    
    if form.validate_on_submit():
        backup_service = get_backup_service()
        
        success, message, filepath = backup_service.create_backup(
            notes=form.notes.data,
            backup_type='manual'
        )
        
        if success:
            flash(message, 'success')
        else:
            flash(message, 'danger')
    else:
        flash('Ошибка валидации формы', 'danger')
    
    return redirect(url_for('backup.index'))


@backup_bp.route('/<int:backup_id>/download')
@login_required
@admin_required
def download(backup_id):
    """Скачивание резервной копии"""
    backup_service = get_backup_service()
    
    filepath = backup_service.download_backup(backup_id)
    
    if filepath is None:
        flash('Файл бэкапа не найден', 'danger')
        return redirect(url_for('backup.index'))
    
    return send_file(
        filepath,
        as_attachment=True,
        download_name=os.path.basename(filepath)
    )


@backup_bp.route('/<int:backup_id>/restore', methods=['POST'])
@login_required
@admin_required
def restore(backup_id):
    """Восстановление из резервной копии"""
    backup_service = get_backup_service()
    
    success, message = backup_service.restore_backup(backup_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('backup.index'))


@backup_bp.route('/<int:backup_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete(backup_id):
    """Удаление резервной копии"""
    backup_service = get_backup_service()
    
    success, message = backup_service.delete_backup(backup_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('backup.index'))


@backup_bp.route('/<int:backup_id>/info')
@login_required
@admin_required
def info(backup_id):
    """Информация о резервной копии"""
    backup_service = get_backup_service()
    
    backup_info = backup_service.get_backup_info(backup_id)
    
    if backup_info is None:
        flash('Бэкап не найден', 'danger')
        return redirect(url_for('backup.index'))
    
    return render_template('backup/info.html', backup=backup_info)


@backup_bp.route('/settings', methods=['POST'])
@login_required
@admin_required
def update_settings():
    """Обновление настроек автобэкапа"""
    enabled = request.form.get('auto_backup_enabled') == 'on'
    interval = request.form.get('auto_backup_interval', 'daily')
    
    if interval not in ['daily', 'weekly', 'monthly']:
        interval = 'daily'
    
    backup_service = get_backup_service()
    
    if backup_service.update_backup_settings(enabled, interval):
        flash('Настройки бэкапа сохранены', 'success')
    else:
        flash('Ошибка сохранения настроек', 'danger')
    
    return redirect(url_for('backup.index'))