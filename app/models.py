from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from app import db
import secrets
import json


class User(UserMixin, db.Model):
    """Модель пользователя"""
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)
    
    # Защита от брутфорса
    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)
    
    # Связи
    keys = db.relationship('ProxyKey', backref='owner', lazy='dynamic',
                          foreign_keys='ProxyKey.user_id')
    
    def set_password(self, password):
        """Установка хэша пароля"""
        self.password_hash = generate_password_hash(password, method='scrypt')
    
    def check_password(self, password):
        """Проверка пароля"""
        return check_password_hash(self.password_hash, password)
    
    def is_locked(self):
        """Проверка блокировки аккаунта"""
        if self.locked_until and self.locked_until > datetime.utcnow():
            return True
        return False
    
    def increment_failed_login(self, max_attempts=5, block_time=900):
        """Увеличение счетчика неудачных попыток входа"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = datetime.utcnow() + timedelta(seconds=block_time)
        db.session.commit()
    
    def reset_failed_login(self):
        """Сброс счетчика неудачных попыток"""
        self.failed_login_attempts = 0
        self.locked_until = None
        db.session.commit()
    
    def get_status(self):
        """Получение статуса пользователя"""
        if self.is_blocked:
            return 'Заблокирован'
        if not self.is_approved:
            return 'Ожидает подтверждения'
        if self.is_admin:
            return 'Администратор'
        return 'Активен'
    
    def __repr__(self):
        return f'<User {self.email}>'


class ProxyKey(db.Model):
    """Модель ключа прокси"""
    __tablename__ = 'proxy_keys'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    secret = db.Column(db.String(64), unique=True, nullable=False, index=True)
    fake_tls_domain = db.Column(db.String(255), default='www.google.com')
    
    # Привязка к пользователю
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    
    # Статусы
    is_active = db.Column(db.Boolean, default=True)
    is_blocked = db.Column(db.Boolean, default=False)
    
    # Лимиты трафика (в байтах)
    traffic_limit = db.Column(db.BigInteger, nullable=True)  # None = без лимита
    traffic_limit_period = db.Column(db.String(20), nullable=True)  # day, week, month
    traffic_used = db.Column(db.BigInteger, default=0)
    traffic_reset_at = db.Column(db.DateTime, nullable=True)
    
    # Статистика
    total_traffic = db.Column(db.BigInteger, default=0)
    last_activity = db.Column(db.DateTime, nullable=True)
    connection_count = db.Column(db.Integer, default=0)
    
    # Метаданные
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    # Связи
    traffic_logs = db.relationship('TrafficLog', backref='key', lazy='dynamic',
                                   cascade='all, delete-orphan')
    
    def generate_secret(self):
        """Генерация секрета для FakeTLS (32 байта = 64 hex символа)"""
        # Для FakeTLS секрет должен начинаться с 'ee' (тип dd для FakeTLS)
        random_bytes = secrets.token_bytes(31)
        self.secret = 'ee' + random_bytes.hex()
        return self.secret
    
    def get_tg_link(self, server_host, server_port=443):
        """Генерация ссылки tg://"""
        return f"tg://proxy?server={server_host}&port={server_port}&secret={self.secret}"
    
    def get_https_link(self, server_host, server_port=443):
        """Генерация HTTPS ссылки"""
        return f"https://t.me/proxy?server={server_host}&port={server_port}&secret={self.secret}"
    
    def get_qr_data(self, server_host, server_port=443):
        """Данные для QR кода"""
        return self.get_tg_link(server_host, server_port)
    
    def check_traffic_limit(self):
        """Проверка превышения лимита трафика"""
        if self.traffic_limit is None:
            return False
        return self.traffic_used >= self.traffic_limit
    
    def reset_traffic_if_needed(self):
        """Сброс счетчика трафика при необходимости"""
        if self.traffic_reset_at is None or self.traffic_limit_period is None:
            return
        
        now = datetime.utcnow()
        if now >= self.traffic_reset_at:
            self.traffic_used = 0
            self.traffic_reset_at = self._calculate_next_reset()
            db.session.commit()
    
    def _calculate_next_reset(self):
        """Вычисление времени следующего сброса"""
        now = datetime.utcnow()
        if self.traffic_limit_period == 'day':
            return now + timedelta(days=1)
        elif self.traffic_limit_period == 'week':
            return now + timedelta(weeks=1)
        elif self.traffic_limit_period == 'month':
            return now + timedelta(days=30)
        return None
    
    def set_traffic_limit(self, limit_bytes, period):
        """Установка лимита трафика"""
        self.traffic_limit = limit_bytes
        self.traffic_limit_period = period
        self.traffic_used = 0
        self.traffic_reset_at = self._calculate_next_reset()
        db.session.commit()
    
    def add_traffic(self, bytes_count):
        """Добавление использованного трафика"""
        self.traffic_used += bytes_count
        self.total_traffic += bytes_count
        self.last_activity = datetime.utcnow()
        db.session.commit()
    
    def get_status(self):
        """Получение статуса ключа"""
        if self.is_blocked:
            return 'Заблокирован'
        if not self.is_active:
            return 'Неактивен'
        if self.check_traffic_limit():
            return 'Лимит превышен'
        return 'Активен'
    
    def format_traffic(self, bytes_count):
        """Форматирование трафика в читаемый вид"""
        if bytes_count is None:
            return '—'
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if bytes_count < 1024:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.2f} ПБ"
    
    def __repr__(self):
        return f'<ProxyKey {self.name}>'


class TrafficLog(db.Model):
    """Лог трафика для статистики"""
    __tablename__ = 'traffic_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    key_id = db.Column(db.Integer, db.ForeignKey('proxy_keys.id'), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    bytes_in = db.Column(db.BigInteger, default=0)
    bytes_out = db.Column(db.BigInteger, default=0)
    connections = db.Column(db.Integer, default=0)
    
    def __repr__(self):
        return f'<TrafficLog {self.key_id} at {self.timestamp}>'


class LoginAttempt(db.Model):
    """Логирование попыток входа"""
    __tablename__ = 'login_attempts'
    
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=True)
    success = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_agent = db.Column(db.String(500), nullable=True)
    
    @classmethod
    def get_failed_attempts(cls, ip_address, minutes=15):
        """Получение количества неудачных попыток с IP за период"""
        since = datetime.utcnow() - timedelta(minutes=minutes)
        return cls.query.filter(
            cls.ip_address == ip_address,
            cls.success == False,
            cls.timestamp >= since
        ).count()
    
    @classmethod
    def is_ip_blocked(cls, ip_address, max_attempts=10, minutes=15):
        """Проверка блокировки IP"""
        return cls.get_failed_attempts(ip_address, minutes) >= max_attempts


class Settings(db.Model):
    """Настройки приложения"""
    __tablename__ = 'settings'
    
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), default='string')  # string, int, bool, json
    description = db.Column(db.String(255), nullable=True)
    
    @classmethod
    def get(cls, key, default=None):
        """Получение значения настройки"""
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            return default
        
        if setting.value_type == 'int':
            return int(setting.value)
        elif setting.value_type == 'bool':
            return setting.value.lower() in ('true', '1', 'yes')
        elif setting.value_type == 'json':
            return json.loads(setting.value)
        return setting.value
    
    @classmethod
    def set(cls, key, value, value_type='string', description=None):
        """Установка значения настройки"""
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            setting = cls(key=key)
        
        if value_type == 'json':
            setting.value = json.dumps(value)
        else:
            setting.value = str(value)
        
        setting.value_type = value_type
        if description:
            setting.description = description
        
        db.session.add(setting)
        db.session.commit()
    
    @classmethod
    def init_defaults(cls):
        """Инициализация настроек по умолчанию"""
        defaults = [
            ('server_domain', 'localhost', 'string', 'Домен сервера'),
            ('mtg_port', '443', 'int', 'Порт MTG прокси'),
            ('auto_backup_enabled', 'false', 'bool', 'Автоматический бэкап'),
            ('auto_backup_interval', 'daily', 'string', 'Интервал бэкапа'),
            ('max_keys_per_user', '5', 'int', 'Максимум ключей на пользователя'),
        ]
        
        for key, value, vtype, desc in defaults:
            if cls.query.filter_by(key=key).first() is None:
                cls.set(key, value, vtype, desc)


class BackupRecord(db.Model):
    """Записи о бэкапах"""
    __tablename__ = 'backup_records'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    size = db.Column(db.BigInteger, default=0)
    backup_type = db.Column(db.String(20), default='manual')  # manual, auto
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    
    def __repr__(self):
        return f'<BackupRecord {self.filename}>'