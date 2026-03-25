import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(32).hex()

    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL") or f"sqlite:///{os.path.join(BASE_DIR, 'data', 'mtproxy.db')}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PERMANENT_SESSION_LIFETIME = timedelta(hours=24)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = True

    BASE_DIR = BASE_DIR
    DATA_PATH = os.path.join(BASE_DIR, "data")
    LOGS_PATH = os.path.join(BASE_DIR, "logs")
    BACKUPS_PATH = os.path.join(BASE_DIR, "backups")
    SCRIPTS_PATH = os.path.join(BASE_DIR, "scripts")

    MTG_BINARY_PATH = "/usr/local/bin/mtg"
    MTG_CONFIG_PATH = os.path.join(BASE_DIR, "mtg")
    MTG_SERVICE_NAME = "mtg-proxy"
    MTG_STATS_PORT = 3129

    LOGIN_ATTEMPTS_LIMIT = 5
    LOGIN_BLOCK_TIME = 900


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}