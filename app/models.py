from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from sqlalchemy import UniqueConstraint
from app import db
import secrets
import json
import uuid


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_approved = db.Column(db.Boolean, default=False)
    is_blocked = db.Column(db.Boolean, default=False)

    failed_login_attempts = db.Column(db.Integer, default=0)
    locked_until = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    keys = db.relationship("ProxyKey", backref="owner", lazy="dynamic", foreign_keys="ProxyKey.user_id")
    instances = db.relationship("ProxyInstance", backref="owner", lazy="dynamic", foreign_keys="ProxyInstance.owner_user_id")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method="scrypt")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def is_locked(self):
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    def increment_failed_login(self, max_attempts=5, block_time=900):
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.locked_until = datetime.utcnow() + timedelta(seconds=block_time)
        db.session.commit()

    def reset_failed_login(self):
        self.failed_login_attempts = 0
        self.locked_until = None
        db.session.commit()

    def get_status(self):
        if self.is_blocked:
            return "Заблокирован"
        if not self.is_approved:
            return "Ожидает подтверждения"
        if self.is_admin:
            return "Администратор"
        return "Активен"


class ProxyKey(db.Model):
    __tablename__ = "proxy_keys"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    secret = db.Column(db.String(256), unique=True, nullable=False, index=True)
    fake_tls_domain = db.Column(db.String(255), default="www.google.com")

    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    is_blocked = db.Column(db.Boolean, default=False)

    traffic_limit = db.Column(db.BigInteger, nullable=True)
    traffic_limit_period = db.Column(db.String(20), nullable=True)
    traffic_used = db.Column(db.BigInteger, default=0)
    traffic_reset_at = db.Column(db.DateTime, nullable=True)

    total_traffic = db.Column(db.BigInteger, default=0)
    last_activity = db.Column(db.DateTime, nullable=True)
    connection_count = db.Column(db.Integer, default=0)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)

    traffic_logs = db.relationship("TrafficLog", backref="key", lazy="dynamic", cascade="all, delete-orphan")

    def generate_secret(self):
        random_bytes = secrets.token_bytes(31)
        self.secret = "ee" + random_bytes.hex()
        return self.secret

    def get_tg_link(self, server_host, server_port=443):
        return f"tg://proxy?server={server_host}&port={server_port}&secret={self.secret}"

    def get_https_link(self, server_host, server_port=443):
        return f"https://t.me/proxy?server={server_host}&port={server_port}&secret={self.secret}"

    def get_qr_data(self, server_host, server_port=443):
        return self.get_tg_link(server_host, server_port)

    def check_traffic_limit(self):
        if self.traffic_limit is None:
            return False
        return self.traffic_used >= self.traffic_limit

    def reset_traffic_if_needed(self):
        if self.traffic_reset_at is None or self.traffic_limit_period is None:
            return
        now = datetime.utcnow()
        if now >= self.traffic_reset_at:
            self.traffic_used = 0
            self.traffic_reset_at = self._calculate_next_reset()
            db.session.commit()

    def _calculate_next_reset(self):
        now = datetime.utcnow()
        if self.traffic_limit_period == "day":
            return now + timedelta(days=1)
        if self.traffic_limit_period == "week":
            return now + timedelta(weeks=1)
        if self.traffic_limit_period == "month":
            return now + timedelta(days=30)
        return None

    def set_traffic_limit(self, limit_bytes, period):
        self.traffic_limit = limit_bytes
        self.traffic_limit_period = period
        self.traffic_used = 0
        self.traffic_reset_at = self._calculate_next_reset()
        db.session.commit()

    def add_traffic(self, bytes_count):
        self.traffic_used += bytes_count
        self.total_traffic += bytes_count
        self.last_activity = datetime.utcnow()
        db.session.commit()

    def get_status(self):
        if self.is_blocked:
            return "Заблокирован"
        if not self.is_active:
            return "Неактивен"
        if self.check_traffic_limit():
            return "Лимит превышен"
        return "Активен"

    @staticmethod
    def format_traffic(bytes_count):
        if bytes_count is None:
            return "—"
        for unit in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
            if bytes_count < 1024:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024
        return f"{bytes_count:.2f} ПБ"


class ProxyInstance(db.Model):
    __tablename__ = "proxy_instances"
    __table_args__ = (
        UniqueConstraint("bind_ip", "bind_port", name="uq_proxy_instances_bind"),
        UniqueConstraint("stats_port", name="uq_proxy_instances_stats_port"),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(100), nullable=False)
    secret = db.Column(db.String(256), unique=True, nullable=False, index=True)
    fake_tls_domain = db.Column(db.String(255), default="www.google.com", nullable=False)

    bind_ip = db.Column(db.String(64), default="0.0.0.0", nullable=False)
    bind_port = db.Column(db.Integer, nullable=False)
    stats_port = db.Column(db.Integer, nullable=False)

    owner_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    is_enabled = db.Column(db.Boolean, default=True)
    is_blocked = db.Column(db.Boolean, default=False)

    total_traffic = db.Column(db.BigInteger, default=0)
    traffic_used = db.Column(db.BigInteger, default=0)
    connection_count = db.Column(db.Integer, default=0)
    last_activity = db.Column(db.DateTime, nullable=True)

    # Лимиты для multi-instance
    traffic_limit_bytes = db.Column(db.BigInteger, nullable=True)  # None = без лимита
    traffic_limit_period = db.Column(db.String(10), default="none")  # none/day/week/month

    period_started_at = db.Column(db.DateTime, nullable=True)
    period_baseline_bytes = db.Column(db.BigInteger, default=0)
    period_used_bytes = db.Column(db.BigInteger, default=0)

    paused_by_limit = db.Column(db.Boolean, default=False)
    limit_exceeded_at = db.Column(db.DateTime, nullable=True)

    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def unit_name(self):
        return f"mtg@{self.id}.service"

    @property
    def status_label(self):
        if self.is_blocked:
            return "Заблокирован"
        if not self.is_enabled:
            return "Отключен"
        if self.paused_by_limit:
            return "Остановлен по лимиту"
        return "Активен"

    def get_tg_link(self, server_host):
        return f"tg://proxy?server={server_host}&port={self.bind_port}&secret={self.secret}"

    def get_https_link(self, server_host):
        return f"https://t.me/proxy?server={server_host}&port={self.bind_port}&secret={self.secret}"

    def _period_seconds(self):
        if self.traffic_limit_period == "day":
            return 86400
        if self.traffic_limit_period == "week":
            return 7 * 86400
        if self.traffic_limit_period == "month":
            return 30 * 86400
        return None

    def reset_limit_period_if_needed(self, current_total: int, now: datetime) -> bool:
        if not self.traffic_limit_bytes or self.traffic_limit_period == "none":
            self.period_started_at = None
            self.period_baseline_bytes = 0
            self.period_used_bytes = 0
            self.limit_exceeded_at = None
            return False

        sec = self._period_seconds()
        if not sec:
            return False

        if self.period_started_at is None:
            self.period_started_at = now
            self.period_baseline_bytes = current_total
            self.period_used_bytes = 0
            return False

        elapsed = (now - self.period_started_at).total_seconds()
        if elapsed >= sec:
            self.period_started_at = now
            self.period_baseline_bytes = current_total
            self.period_used_bytes = 0
            self.limit_exceeded_at = None
            return True

        return False

    def update_period_usage(self, current_total: int):
        if not self.traffic_limit_bytes or self.traffic_limit_period == "none":
            self.period_used_bytes = 0
            return
        used = current_total - (self.period_baseline_bytes or 0)
        if used < 0:
            self.period_baseline_bytes = current_total
            used = 0
        self.period_used_bytes = used

    def is_limit_exceeded(self) -> bool:
        if not self.traffic_limit_bytes or self.traffic_limit_period == "none":
            return False
        return (self.period_used_bytes or 0) >= self.traffic_limit_bytes


class TrafficLog(db.Model):
    __tablename__ = "traffic_logs"

    id = db.Column(db.Integer, primary_key=True)
    key_id = db.Column(db.Integer, db.ForeignKey("proxy_keys.id"), nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    bytes_in = db.Column(db.BigInteger, default=0)
    bytes_out = db.Column(db.BigInteger, default=0)
    connections = db.Column(db.Integer, default=0)


class LoginAttempt(db.Model):
    __tablename__ = "login_attempts"

    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(45), nullable=False, index=True)
    email = db.Column(db.String(120), nullable=True)
    success = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_agent = db.Column(db.String(500), nullable=True)

    @classmethod
    def get_failed_attempts(cls, ip_address, minutes=15):
        since = datetime.utcnow() - timedelta(minutes=minutes)
        return cls.query.filter(
            cls.ip_address == ip_address,
            cls.success.is_(False),
            cls.timestamp >= since,
        ).count()

    @classmethod
    def is_ip_blocked(cls, ip_address, max_attempts=10, minutes=15):
        return cls.get_failed_attempts(ip_address, minutes) >= max_attempts


class Settings(db.Model):
    __tablename__ = "settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False, index=True)
    value = db.Column(db.Text, nullable=True)
    value_type = db.Column(db.String(20), default="string")
    description = db.Column(db.String(255), nullable=True)

    @classmethod
    def get(cls, key, default=None):
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            return default
        if setting.value_type == "int":
            return int(setting.value)
        if setting.value_type == "bool":
            return setting.value.lower() in ("true", "1", "yes")
        if setting.value_type == "json":
            return json.loads(setting.value)
        return setting.value

    @classmethod
    def set(cls, key, value, value_type="string", description=None):
        setting = cls.query.filter_by(key=key).first()
        if setting is None:
            setting = cls(key=key)
        setting.value = json.dumps(value) if value_type == "json" else str(value)
        setting.value_type = value_type
        if description:
            setting.description = description
        db.session.add(setting)
        db.session.commit()

    @classmethod
    def init_defaults(cls):
        defaults = [
            ("server_domain", "localhost", "string", "Домен сервера"),
            ("max_keys_per_user", "5", "int", "Максимум инстансов на пользователя"),
            ("auto_backup_enabled", "false", "bool", "Автоматический бэкап"),
            ("auto_backup_interval", "daily", "string", "Интервал бэкапа"),
            ("instance_port_start", "10000", "int", "Стартовый порт инстансов"),
            ("instance_stats_port_start", "31000", "int", "Стартовый stats-порт"),
        ]
        for key, value, vtype, desc in defaults:
            if cls.query.filter_by(key=key).first() is None:
                cls.set(key, value, vtype, desc)


class BackupRecord(db.Model):
    __tablename__ = "backup_records"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    size = db.Column(db.BigInteger, default=0)
    backup_type = db.Column(db.String(20), default="manual")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)