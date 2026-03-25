"""
Маршруты управления ключами прокси
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import ProxyKey, User, Settings
from app.forms import CreateKeyForm, EditKeyForm, ConfirmActionForm
from app.services.key_generator import KeyGenerator
from app.services.mtg_service import get_mtg_service
from app.services.traffic_monitor import TrafficMonitor

keys_bp = Blueprint('keys', __name__)


@keys_bp.route('/')
@login_required
def list_keys():
    """Список ключей"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    # Администратор видит все ключи, пользователь - только свои
    if current_user.is_admin:
        query = ProxyKey.query
    else:
        query = ProxyKey.query.filter_by(user_id=current_user.id)
    
    # Фильтры
    status_filter = request.args.get('status', 'all')
    if status_filter == 'active':
        query = query.filter_by(is_active=True, is_blocked=False)
    elif status_filter == 'blocked':
        query = query.filter_by(is_blocked=True)
    elif status_filter == 'inactive':
        query = query.filter_by(is_active=False)
    
    keys = query.order_by(ProxyKey.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    # Получаем настройки сервера для ссылок
    server_domain = Settings.get('server_domain', 'localhost')
    mtg_port = Settings.get('mtg_port', 443)
    
    return render_template('keys/list.html', 
        keys=keys,
        status_filter=status_filter,
        server_domain=server_domain,
        mtg_port=mtg_port
    )


@keys_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_key():
    """Создание нового ключа (минимальная форма)"""
    # Проверка лимита ключей для обычных пользователей
    if not current_user.is_admin:
        max_keys = Settings.get('max_keys_per_user', 5)
        user_keys_count = ProxyKey.query.filter_by(user_id=current_user.id).count()
        if user_keys_count >= max_keys:
            flash(f'Достигнут лимит ключей ({max_keys}). Обратитесь к администратору.', 'warning')
            return redirect(url_for('keys.list_keys'))
    
    form = CreateKeyForm()
    
    if form.validate_on_submit():
        # Генерируем секрет FakeTLS
        secret, domain = KeyGenerator.generate_secret()
        
        # Создаем ключ
        key = ProxyKey(
            name=form.name.data.strip(),
            secret=secret,
            fake_tls_domain=domain,
            user_id=current_user.id if not current_user.is_admin else None,
            is_active=True
        )
        
        db.session.add(key)
        db.session.commit()
        
        # Обновляем конфигурацию MTG
        mtg_service = get_mtg_service()
        if mtg_service.get_status()['running']:
            mtg_service.reload_config()
        
        flash(f'Ключ "{key.name}" успешно создан', 'success')
        return redirect(url_for('keys.key_detail', key_id=key.id))
    
    return render_template('keys/create.html', form=form)


@keys_bp.route('/<int:key_id>')
@login_required
def key_detail(key_id):
    """Детальная информация о ключе"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Проверка доступа
    if not current_user.is_admin and key.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('keys.list_keys'))
    
    # Получаем настройки для генерации ссылок
    server_domain = Settings.get('server_domain', 'localhost')
    mtg_port = Settings.get('mtg_port', 443)
    
    # Генерируем ссылки
    links = KeyGenerator.generate_proxy_links(key.secret, server_domain, mtg_port)
    
    # Информация о секрете
    secret_info = KeyGenerator.get_secret_info(key.secret)
    
    # Статистика трафика
    traffic_monitor = TrafficMonitor()
    traffic_stats = traffic_monitor.get_key_stats(key_id, 'day')
    hourly_stats = traffic_monitor.get_hourly_stats(key_id, 24)
    
    # Владелец ключа
    owner = User.query.get(key.user_id) if key.user_id else None
    
    return render_template('keys/detail.html',
        key=key,
        links=links,
        secret_info=secret_info,
        traffic_stats=traffic_stats,
        hourly_stats=hourly_stats,
        owner=owner,
        server_domain=server_domain,
        mtg_port=mtg_port
    )


@keys_bp.route('/<int:key_id>/edit', methods=['GET', 'POST'])
@login_required
def key_edit(key_id):
    """Редактирование ключа"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Проверка доступа (только админ может редактировать)
    if not current_user.is_admin:
        # Обычный пользователь может редактировать только имя своего ключа
        if key.user_id != current_user.id:
            flash('Доступ запрещён', 'danger')
            return redirect(url_for('keys.list_keys'))
    
    form = EditKeyForm(obj=key)
    
    if request.method == 'GET':
        # Заполняем форму текущими значениями
        form.name.data = key.name
        form.fake_tls_domain.data = key.fake_tls_domain
        form.user_id.data = key.user_id or 0
        form.is_active.data = key.is_active
        form.notes.data = key.notes
        
        # Лимит трафика
        if key.traffic_limit:
            form.traffic_limit_enabled.data = True
            # Конвертируем байты в удобные единицы
            limit_bytes = key.traffic_limit
            if limit_bytes >= 1024**4:
                form.traffic_limit_value.data = int(limit_bytes / (1024**4))
                form.traffic_limit_unit.data = 'TB'
            elif limit_bytes >= 1024**3:
                form.traffic_limit_value.data = int(limit_bytes / (1024**3))
                form.traffic_limit_unit.data = 'GB'
            else:
                form.traffic_limit_value.data = int(limit_bytes / (1024**2))
                form.traffic_limit_unit.data = 'MB'
            form.traffic_limit_period.data = key.traffic_limit_period or 'month'
        else:
            form.traffic_limit_enabled.data = False
    
    if form.validate_on_submit():
        key.name = form.name.data.strip()
        
        # Только админ может менять эти поля
        if current_user.is_admin:
            # Смена домена FakeTLS требует перегенерации секрета
            if form.fake_tls_domain.data != key.fake_tls_domain:
                new_secret, new_domain = KeyGenerator.generate_secret(form.fake_tls_domain.data)
                key.secret = new_secret
                key.fake_tls_domain = new_domain
                flash('Секрет перегенерирован с новым доменом FakeTLS', 'info')
            
            key.user_id = form.user_id.data if form.user_id.data != 0 else None
            key.is_active = form.is_active.data
            key.notes = form.notes.data
            
            # Лимит трафика
            if form.traffic_limit_enabled.data and form.traffic_limit_value.data:
                # Конвертируем в байты
                multipliers = {'MB': 1024**2, 'GB': 1024**3, 'TB': 1024**4}
                limit_bytes = form.traffic_limit_value.data * multipliers.get(form.traffic_limit_unit.data, 1024**2)
                key.set_traffic_limit(limit_bytes, form.traffic_limit_period.data)
            else:
                key.traffic_limit = None
                key.traffic_limit_period = None
                key.traffic_reset_at = None
        
        db.session.commit()
        
        # Обновляем конфигурацию MTG
        mtg_service = get_mtg_service()
        if mtg_service.get_status()['running']:
            mtg_service.reload_config()
        
        flash('Ключ обновлён', 'success')
        return redirect(url_for('keys.key_detail', key_id=key.id))
    
    return render_template('keys/edit.html', form=form, key=key)


@keys_bp.route('/<int:key_id>/regenerate', methods=['POST'])
@login_required
def key_regenerate(key_id):
    """Перегенерация секрета ключа"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Проверка доступа
    if not current_user.is_admin and key.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('keys.list_keys'))
    
    # Генерируем новый секрет с тем же доменом
    new_secret, domain = KeyGenerator.generate_secret(key.fake_tls_domain)
    key.secret = new_secret
    db.session.commit()
    
    # Обновляем конфигурацию MTG
    mtg_service = get_mtg_service()
    if mtg_service.get_status()['running']:
        mtg_service.reload_config()
    
    flash('Секрет перегенерирован. Старые ссылки больше не работают.', 'warning')
    return redirect(url_for('keys.key_detail', key_id=key.id))


@keys_bp.route('/<int:key_id>/toggle', methods=['POST'])
@login_required
def key_toggle(key_id):
    """Переключение активности ключа"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Только админ может переключать
    if not current_user.is_admin:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('keys.list_keys'))
    
    key.is_active = not key.is_active
    db.session.commit()
    
    # Обновляем конфигурацию MTG
    mtg_service = get_mtg_service()
    if mtg_service.get_status()['running']:
        mtg_service.reload_config()
    
    status = 'активирован' if key.is_active else 'деактивирован'
    flash(f'Ключ {status}', 'success')
    return redirect(url_for('keys.key_detail', key_id=key.id))


@keys_bp.route('/<int:key_id>/block', methods=['POST'])
@login_required
def key_block(key_id):
    """Блокировка ключа"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Только админ может блокировать
    if not current_user.is_admin:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('keys.list_keys'))
    
    key.is_blocked = True
    db.session.commit()
    
    # Обновляем конфигурацию MTG
    mtg_service = get_mtg_service()
    if mtg_service.get_status()['running']:
        mtg_service.reload_config()
    
    flash('Ключ заблокирован', 'success')
    return redirect(url_for('keys.key_detail', key_id=key.id))


@keys_bp.route('/<int:key_id>/unblock', methods=['POST'])
@login_required
def key_unblock(key_id):
    """Разблокировка ключа"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Только админ может разблокировать
    if not current_user.is_admin:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('keys.list_keys'))
    
    key.is_blocked = False
    db.session.commit()
    
    # Обновляем конфигурацию MTG
    mtg_service = get_mtg_service()
    if mtg_service.get_status()['running']:
        mtg_service.reload_config()
    
    flash('Ключ разблокирован', 'success')
    return redirect(url_for('keys.key_detail', key_id=key.id))


@keys_bp.route('/<int:key_id>/reset-traffic', methods=['POST'])
@login_required
def key_reset_traffic(key_id):
    """Сброс счётчика трафика"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Только админ может сбрасывать
    if not current_user.is_admin:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('keys.list_keys'))
    
    key.traffic_used = 0
    if key.traffic_limit_period:
        from datetime import datetime, timedelta
        if key.traffic_limit_period == 'day':
            key.traffic_reset_at = datetime.utcnow() + timedelta(days=1)
        elif key.traffic_limit_period == 'week':
            key.traffic_reset_at = datetime.utcnow() + timedelta(weeks=1)
        elif key.traffic_limit_period == 'month':
            key.traffic_reset_at = datetime.utcnow() + timedelta(days=30)
    
    db.session.commit()
    
    flash('Счётчик трафика сброшен', 'success')
    return redirect(url_for('keys.key_detail', key_id=key.id))


@keys_bp.route('/<int:key_id>/delete', methods=['POST'])
@login_required
def key_delete(key_id):
    """Удаление ключа"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Проверка доступа
    if not current_user.is_admin and key.user_id != current_user.id:
        flash('Доступ запрещён', 'danger')
        return redirect(url_for('keys.list_keys'))
    
    key_name = key.name
    db.session.delete(key)
    db.session.commit()
    
    # Обновляем конфигурацию MTG
    mtg_service = get_mtg_service()
    if mtg_service.get_status()['running']:
        mtg_service.reload_config()
    
    flash(f'Ключ "{key_name}" удалён', 'success')
    return redirect(url_for('keys.list_keys'))


@keys_bp.route('/<int:key_id>/stats')
@login_required
def key_stats_api(key_id):
    """API для получения статистики ключа"""
    key = ProxyKey.query.get_or_404(key_id)
    
    # Проверка доступа
    if not current_user.is_admin and key.user_id != current_user.id:
        return jsonify({'error': 'Access denied'}), 403
    
    period = request.args.get('period', 'day')
    
    traffic_monitor = TrafficMonitor()
    stats = traffic_monitor.get_key_stats(key_id, period)
    
    if period == 'day':
        detailed = traffic_monitor.get_hourly_stats(key_id, 24)
    else:
        detailed = traffic_monitor.get_daily_stats(key_id, 30)
    
    return jsonify({
        'stats': stats,
        'detailed': detailed
    })