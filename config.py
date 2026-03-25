import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # Безопасность
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = 3600
    
    # База данных
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'data', 'mtproxy.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Сессии
    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # MTG Proxy
    MTG_BINARY_PATH = '/usr/local/bin/mtg'
    MTG_CONFIG_PATH = os.path.join(basedir, 'data', 'mtg.conf')
    MTG_STATS_PATH = os.path.join(basedir, 'data', 'stats')
    MTG_PORT = 443
    MTG_STATS_PORT = 2398
    
    # Пути
    SCRIPTS_PATH = os.path.join(basedir, 'scripts')
    BACKUP_PATH = os.path.join(basedir, 'backups')
    DATA_PATH = os.path.join(basedir, 'data')
    
    # Лимиты безопасности
    LOGIN_ATTEMPTS_LIMIT = 5
    LOGIN_BLOCK_TIME = 900  # 15 минут
    
    # Бэкап
    AUTO_BACKUP_ENABLED = True
    AUTO_BACKUP_INTERVAL_HOURS = 24
    BACKUP_RETENTION_DAYS = 30


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}