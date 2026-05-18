# MTProxy Manager - Agent Guidance

## What This Project Is
Flask web panel for managing [MTG](https://github.com/9seconds/mtg) (Telegram MTProto proxy) instances on Debian servers. Each instance = 1 secret key = 1 systemd service (`mtg@<instance_id>.service`). Multi-instance architecture with Prometheus-based traffic monitoring, traffic limits, backup/restore, and secure script runner.

## Running the App

**Development:**
```bash
python3 run.py
# or with custom config
FLASK_CONFIG=development FLASK_DEBUG=true python3 run.py
```

**Production:**
```bash
# Uses gunicorn (defined in systemd service)
systemctl start mtproxy-manager

# Manual: gunicorn -w 4 -b 127.0.0.1:5000 run:app
```

## Key Directories
- `app/routes/` — Flask blueprints (auth, admin, keys, users, backup, scripts, profile)
- `app/services/` — Business logic (mtg_service, traffic_monitor, backup_service, key_generator, system_monitor)
- `app/models.py` — SQLAlchemy models (User, ProxyInstance, ProxyKey, TrafficLog, LoginAttempt, Settings, BackupRecord)
- `app/forms.py` — WTForms (LoginForm, RegistrationForm, ProfileForm, CreateKeyForm, EditKeyForm, SettingsForm, BackupForm, ScriptRunForm, etc.)
- `app/templates/` — Jinja2 templates (base.html + admin/ + auth/ subdirectories)
- `app/static/` — `css/style.css` (custom, ~2100 lines) and `js/main.js` (vanilla JS, ~417 lines)
- `app/migrations/versions/` — Alembic migrations (2 migrations)
- `app/deploy/systemd/` — systemd template unit for MTG
- `mtg/instances/<id>.toml` — Per-instance MTG configs (TOML format with Prometheus stats section)
- `data/` — SQLite database
- `logs/` — Application logs (rotated, 10MB each, 10 backups)
- `backups/` — tar.gz backup archives
- `scripts/` — User-defined scripts for script runner

## Required Setup (Debian)
```bash
# Full install (requires root)
sudo MTG_SHA256=<sha256> bash install.sh

# Initialize DB and admin user
sudo bash init_app.sh
# or: sudo ADMIN_EMAIL=x ADMIN_PASSWORD='x' bash init_app.sh

# CLI admin management
cd /opt/mtproxy-manager && source .venv/bin/activate && python create_admin.py --create admin@example.com

# Check service
sudo systemctl status mtproxy-manager
```

## Key Environment Variables
See `.env.example` for full list:
- `FLASK_CONFIG` — `development` or `production`
- `SECRET_KEY` — Required for production (auto-generated from os.urandom if not set)
- `DATABASE_URL` — SQLite only (e.g., `sqlite:////opt/mtproxy-manager/data/mtproxy.db`)
- `SYSTEMCTL_USE_SUDO=true` — Allow app to manage `mtg@*.service` via sudoers
- `MANAGER_BIND_HOST`, `MANAGER_BIND_PORT` — Server binding
- `MTG_BINARY_PATH` — Path to mtg binary (default: `/usr/local/bin/mtg`)
- `MTG_STATS_PORT` — Default stats port offset (default: 3129)
- `SCRIPT_ALLOWLIST` — Comma-separated allowed script names
- `SCRIPT_TIMEOUT_SECONDS` — Script execution timeout (default: 300)
- `LOGIN_ATTEMPTS_LIMIT` — Failed attempts before lock (default: 5)
- `LOGIN_BLOCK_TIME` — Lock duration in seconds (default: 900)
- `PYTHON_BINARY_PATH` — Python for script runner (default: python3)
- `MAX_KEYS_PER_USER` — Max instances per user (default: 5)
- `SERVER_DOMAIN` — Domain for proxy links
- `MTG_SHA256` — SHA256 checksum for MTG binary verification

## Database Migrations
Uses Flask-Migrate (`flask db` commands). Existing migrations in `app/migrations/versions/`:
1. `20261001_add_proxy_instances.py` — creates proxy_instances table, migrates active proxy_keys
2. `20261002_add_proxy_instance_limits.py` — adds traffic limit columns to proxy_instances

After code updates:
```bash
flask db upgrade
# or: python3 -c "from app import create_app; from flask_migrate import upgrade; app = create_app(); with app.app_context(): upgrade()"
```

## Important Notes
- **Never leave the project folder** — all work must stay within the repository
- **Update structure.md** after any file/folder changes (add, remove, rename)
- No test suite exists — verify changes manually or in a VM
- This is a **server-side deployment tool**, not a frontend app
- Requires systemd and sudoers configuration for MTG management
- Uses CSRF protection (Flask-WTF), rate limiting (Flask-Limiter)
- Background jobs run via APScheduler:
  - Traffic stats update: every 1 minute
  - Traffic limit checks: every 5 minutes
  - Auto-backup: daily at 3:00
- Frontend uses custom CSS (no framework) and vanilla JS (no jQuery)
- All UI text in Russian, but code comments/documentation in Russian too
- **Two model systems coexist**: `ProxyInstance` (new multi-instance) and `ProxyKey` (legacy single-key model). New development should use `ProxyInstance`.
- Password hashing uses Werkzeug `scrypt` method
- CLI tool `create_admin.py` for admin management outside web UI

## Update Procedure
```bash
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart mtproxy-manager
```

## Architecture Notes
- **App factory**: `app/__init__.py` creates Flask app, initializes extensions, registers blueprints, sets up scheduler
- **Config**: `config.py` has `Config`, `DevelopmentConfig`, `ProductionConfig` classes with env-based overrides
- **Dual-key models**: `ProxyKey` (legacy, for `TrafficLog` FK) and `ProxyInstance` (active development for multi-instance)
- **MTG config format**: TOML with `secret`, `bind-to`, and `[stats.prometheus]` section
- **Traffic monitoring**: scrapes `http://127.0.0.1:<stats_port>/metrics` Prometheus endpoint of each MTG instance
- **Script runner**: only admin, only allowlist, basename-only (no user paths), audit log, timeout
- **Backup**: tar.gz containing `data/mtproxy.db`, `mtg/mtg.toml`, `scripts/` with safe-extract path traversal protection
