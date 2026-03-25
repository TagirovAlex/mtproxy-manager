import os
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    return [x.strip() for x in raw.split(",") if x.strip()]


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

    MTG_BINARY_PATH = os.environ.get("MTG_BINARY_PATH", "/usr/local/bin/mtg")
    MTG_CONFIG_PATH = os.path.join(BASE_DIR, "mtg")
    MTG_SERVICE_NAME = os.environ.get("MTG_SERVICE_NAME", "mtg-proxy")
    MTG_STATS_PORT = _env_int("MTG_STATS_PORT", 3129)

    # Multi-instance MTG management via systemctl from app
    SYSTEMCTL_USE_SUDO = _env_bool("SYSTEMCTL_USE_SUDO", True)

    # Script runner hardening defaults
    PYTHON_BINARY_PATH = os.environ.get("PYTHON_BINARY_PATH", "python3")
    SCRIPT_TIMEOUT_SECONDS = _env_int("SCRIPT_TIMEOUT_SECONDS", 300)
    SCRIPT_ALLOWLIST = _env_list(
        "SCRIPT_ALLOWLIST",
        [
            # Пример: "healthcheck.sh", "rotate_logs.sh"
        ],
    )

    LOGIN_ATTEMPTS_LIMIT = _env_int("LOGIN_ATTEMPTS_LIMIT", 5)
    LOGIN_BLOCK_TIME = _env_int("LOGIN_BLOCK_TIME", 900)


class DevelopmentConfig(Config):
    DEBUG = True
    SESSION_COOKIE_SECURE = False
    SYSTEMCTL_USE_SUDO = _env_bool("SYSTEMCTL_USE_SUDO", False)


class ProductionConfig(Config):
    DEBUG = False


config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}