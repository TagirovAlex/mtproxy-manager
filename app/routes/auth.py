"""
Маршруты аутентификации
"""

from datetime import datetime
from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash

from app import db, limiter
from app.models import User, LoginAttempt
from app.forms import LoginForm, RegistrationForm

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    """Главная страница"""
    if current_user.is_authenticated:
        if current_user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('keys.list_keys'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute")
def login():
    """Страница входа"""
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))
    
    form = LoginForm()
    
    if form.validate_on_submit():
        ip_address = request.remote_addr
        user_agent = request.headers.get('User-Agent', '')[:500]
        email = form.email.data.lower().strip()
        
        # Проверка блокировки IP
        if LoginAttempt.is_ip_blocked(ip_address):
            flash('Слишком много попыток входа. Попробуйте позже.', 'danger')
            
            # Логируем попытку
            attempt = LoginAttempt(
                ip_address=ip_address,
                email=email,
                success=False,
                user_agent=user_agent
            )
            db.session.add(attempt)
            db.session.commit()
            
            return render_template('auth/login.html', form=form)
        
        user = User.query.filter_by(email=email).first()
        
        # Проверка существования пользователя
        if user is None:
            flash('Неверный email или пароль', 'danger')
            
            # Логируем неудачную попытку
            attempt = LoginAttempt(
                ip_address=ip_address,
                email=email,
                success=False,
                user_agent=user_agent
            )
            db.session.add(attempt)
            db.session.commit()
            
            return render_template('auth/login.html', form=form)
        
        # Проверка блокировки аккаунта
        if user.is_locked():
            remaining = (user.locked_until - datetime.utcnow()).seconds // 60
            flash(f'Аккаунт временно заблокирован. Попробуйте через {remaining} минут.', 'danger')
            return render_template('auth/login.html', form=form)
        
        # Проверка пароля
        if not user.check_password(form.password.data):
            user.increment_failed_login()
            flash('Неверный email или пароль', 'danger')
            
            # Логируем неудачную попытку
            attempt = LoginAttempt(
                ip_address=ip_address,
                email=email,
                success=False,
                user_agent=user_agent
            )
            db.session.add(attempt)
            db.session.commit()
            
            return render_template('auth/login.html', form=form)
        
        # Проверка статуса пользователя
        if user.is_blocked:
            flash('Ваш аккаунт заблокирован. Обратитесь к администратору.', 'danger')
            return render_template('auth/login.html', form=form)
        
        if not user.is_approved:
            flash('Ваш аккаунт ожидает подтверждения администратором.', 'warning')
            return render_template('auth/pending.html')
        
        # Успешный вход
        user.reset_failed_login()
        user.last_login = datetime.utcnow()
        db.session.commit()
        
        login_user(user, remember=form.remember_me.data)
        
        # Логируем успешную попытку
        attempt = LoginAttempt(
            ip_address=ip_address,
            email=email,
            success=True,
            user_agent=user_agent
        )
        db.session.add(attempt)
        db.session.commit()
        
        flash('Вы успешно вошли в систему', 'success')
        
        # Перенаправление на запрошенную страницу или на главную
        next_page = request.args.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        
        if user.is_admin:
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('keys.list_keys'))
    
    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per hour")
def register():
    """Страница регистрации"""
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))
    
    form = RegistrationForm()
    
    if form.validate_on_submit():
        email = form.email.data.lower().strip()
        
        # Проверка существующего пользователя
        if User.query.filter_by(email=email).first():
            flash('Этот email уже зарегистрирован', 'danger')
            return render_template('auth/register.html', form=form)
        
        # Создание нового пользователя
        user = User(email=email)
        user.set_password(form.password.data)
        
        # Первый пользователь становится администратором и сразу подтверждается
        if User.query.count() == 0:
            user.is_admin = True
            user.is_approved = True
            flash('Вы зарегистрированы как администратор!', 'success')
        else:
            user.is_approved = False
            flash('Регистрация успешна! Ожидайте подтверждения администратором.', 'success')
        
        db.session.add(user)
        db.session.commit()
        
        return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', form=form)


@auth_bp.route('/logout')
@login_required
def logout():
    """Выход из системы"""
    logout_user()
    flash('Вы вышли из системы', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/pending')
def pending():
    """Страница ожидания подтверждения"""
    return render_template('auth/pending.html')