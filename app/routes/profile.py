"""
Маршруты профиля пользователя
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models import User, ProxyKey, LoginAttempt
from app.forms import ProfileForm

profile_bp = Blueprint('profile', __name__)


@profile_bp.route('/', methods=['GET', 'POST'])
@login_required
def edit():
    """Редактирование профиля"""
    form = ProfileForm(original_email=current_user.email)
    
    if request.method == 'GET':
        form.email.data = current_user.email
    
    if form.validate_on_submit():
        # Проверка текущего пароля если меняется пароль
        if form.new_password.data:
            if not current_user.check_password(form.current_password.data):
                flash('Неверный текущий пароль', 'danger')
                return render_template('admin/profile/edit.html', form=form)
            
            current_user.set_password(form.new_password.data)
            flash('Пароль успешно изменён', 'success')
        
        # Изменение email
        new_email = form.email.data.lower().strip()
        if new_email != current_user.email:
            # Проверяем уникальность
            if User.query.filter_by(email=new_email).first():
                flash('Этот email уже используется', 'danger')
                return render_template('admin/profile/edit.html', form=form)
            
            current_user.email = new_email
            flash('Email успешно изменён', 'success')
        
        db.session.commit()
        return redirect(url_for('profile.edit'))
    
    # Статистика пользователя
    user_stats = {
        'keys_count': ProxyKey.query.filter_by(user_id=current_user.id).count(),
        'active_keys': ProxyKey.query.filter_by(
            user_id=current_user.id, 
            is_active=True, 
            is_blocked=False
        ).count(),
        'total_traffic': sum(
            k.total_traffic for k in ProxyKey.query.filter_by(user_id=current_user.id).all()
        ),
        'last_login': current_user.last_login,
        'created_at': current_user.created_at
    }
    
    # Форматируем трафик
    user_stats['total_traffic_formatted'] = format_bytes(user_stats['total_traffic'])
    
    # Последние входы
    recent_logins = LoginAttempt.query.filter_by(
        email=current_user.email
    ).order_by(LoginAttempt.timestamp.desc()).limit(5).all()
    
    return render_template('admin/profile/edit.html', 
        form=form, 
        user_stats=user_stats,
        recent_logins=recent_logins
    )


@profile_bp.route('/my-keys')
@login_required
def my_keys():
    """Мои ключи (для обычных пользователей)"""
    keys = ProxyKey.query.filter_by(user_id=current_user.id).order_by(
        ProxyKey.created_at.desc()
    ).all()
    
    from app.models import Settings
    server_domain = Settings.get('server_domain', 'localhost')
    mtg_port = Settings.get('mtg_port', 443)
    
    return render_template('admin/profile/my_keys.html', 
        keys=keys,
        server_domain=server_domain,
        mtg_port=mtg_port
    )


@profile_bp.route('/sessions')
@login_required
def sessions():
    """История сессий/входов"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    attempts = LoginAttempt.query.filter_by(
        email=current_user.email
    ).order_by(LoginAttempt.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return render_template('admin/profile/sessions.html', attempts=attempts)


def format_bytes(bytes_count):
    """Форматирование байтов"""
    if bytes_count is None or bytes_count == 0:
        return '0 Б'
    
    for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
        if bytes_count < 1024:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024
    
    return f"{bytes_count:.2f} ПБ"