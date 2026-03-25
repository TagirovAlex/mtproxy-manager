#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/opt/mtproxy-manager}"
VENV_DIR="${APP_DIR}/.venv"
DB_PATH="${APP_DIR}/data/mtproxy.db"

ADMIN_EMAIL="${ADMIN_EMAIL:-admin@example.com}"
ADMIN_PASSWORD="${ADMIN_PASSWORD:-ChangeMeStrong123!}"

cd "${APP_DIR}"
source "${VENV_DIR}/bin/activate"

echo "[1/4] Ensure SQLite schema (limit columns)"
sqlite3 "${DB_PATH}" <<'SQL'
ALTER TABLE proxy_instances ADD COLUMN traffic_limit_bytes BIGINT;
ALTER TABLE proxy_instances ADD COLUMN traffic_limit_period VARCHAR(10) DEFAULT 'none';
ALTER TABLE proxy_instances ADD COLUMN period_started_at DATETIME;
ALTER TABLE proxy_instances ADD COLUMN period_baseline_bytes BIGINT DEFAULT 0;
ALTER TABLE proxy_instances ADD COLUMN period_used_bytes BIGINT DEFAULT 0;
ALTER TABLE proxy_instances ADD COLUMN paused_by_limit BOOLEAN DEFAULT 0;
ALTER TABLE proxy_instances ADD COLUMN limit_exceeded_at DATETIME;
SQL

echo "[2/4] Validate columns"
sqlite3 "${DB_PATH}" "PRAGMA table_info(proxy_instances);" | grep -E "traffic_limit|period_|paused_by_limit|limit_exceeded_at" || true

echo "[3/4] Create/update admin user"
python - <<PY
from app import create_app, db
from app.models import User
app = create_app("production")
with app.app_context():
    u = User.query.filter_by(email="${ADMIN_EMAIL}").first()
    if not u:
        u = User(email="${ADMIN_EMAIL}", is_admin=True, is_approved=True, is_blocked=False)
        u.set_password("${ADMIN_PASSWORD}")
        db.session.add(u)
    else:
        u.is_admin = True
        u.is_approved = True
        u.is_blocked = False
        u.set_password("${ADMIN_PASSWORD}")
    db.session.commit()
    print("admin ready:", u.email)
PY

echo "[4/4] Restart service"
systemctl restart mtproxy-manager
systemctl status mtproxy-manager --no-pager | sed -n '1,20p'

echo "Init complete."