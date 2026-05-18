mtproxy-manager/
├── app/
│   ├── __init__.py               # Flask app factory, extensions, scheduler, error handlers
│   ├── models.py                 # SQLAlchemy models: User, ProxyKey, ProxyInstance, TrafficLog, LoginAttempt, Settings, BackupRecord
│   ├── forms.py                  # WTForms: Login, Registration, Profile, CreateKey, EditKey, UserManage, Settings, Backup, ScriptRun, ConfirmAction
│   ├── routes/
│   │   ├── __init__.py           # Blueprint imports
│   │   ├── auth.py               # Login, register, logout with rate limiting
│   │   ├── admin.py              # Dashboard, MTG control, settings, users list/manage, API endpoints
│   │   ├── keys.py               # CRUD for ProxyInstance, start/stop/restart/toggle/block
│   │   ├── users.py              # Admin: user keys, assign/unassign, login history, password reset
│   │   ├── profile.py            # Profile edit, my keys, sessions history
│   │   ├── scripts.py            # Secure script runner with allowlist and audit
│   │   └── backup.py             # Backup create/download/restore/delete, settings
│   ├── services/
│   │   ├── __init__.py           # Service imports
│   │   ├── mtg_service.py        # MTG binary, systemd unit management, config generation
│   │   ├── traffic_monitor.py    # Prometheus metrics scraping, traffic limits logic
│   │   ├── backup_service.py     # tar.gz backup creation/restore with safe-extract
│   │   ├── key_generator.py      # FakeTLS secret generation/validation/decoding
│   │   └── system_monitor.py     # CPU, RAM, disk, network, processes, uptime
│   ├── templates/
│   │   ├── base.html             # Layout with sidebar navigation
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   ├── register.html
│   │   │   └── pending.html
│   │   └── admin/
│   │       ├── dashboard.html
│   │       ├── setting.html
│   │       ├── users.html
│   │       ├── user_manage.html
│   │       ├── users/
│   │       │   ├── keys.html
│   │       │   └── login_history.html
│   │       ├── keys/
│   │       │   ├── list.html
│   │       │   ├── create.html
│   │       │   ├── edit.html
│   │       │   └── detail.html
│   │       ├── errors/
│   │       │   ├── 403.html
│   │       │   ├── 404.html
│   │       │   ├── 429.html
│   │       │   └── 500.html
│   │       ├── scripts.html
│   │       ├── script_view.html
│   │       ├── script_history.html
│   │       ├── scripts_result.html
│   │       ├── backup/
│   │       │   ├── index.html
│   │       │   └── info.html
│   │       └── profiles/
│   │           ├── edit.html
│   │           ├── my_keys.html
│   │           └── sessions.html
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css         # Custom CSS (~2100 lines, no framework)
│   │   └── js/
│   │       └── main.js           # Vanilla JS (~417 lines, no jQuery)
│   ├── migrations/
│   │   └── versions/
│   │       ├── 20261001_add_proxy_instances.py
│   │       └── 20261002_add_proxy_instance_limits.py
│   └── deploy/
│       └── systemd/
│           └── mtg@.service      # systemd template unit for MTG instances
├── data/
│   └── mtproxy.db                # SQLite database
├── logs/                         # Application logs (rotated)
├── backups/                      # tar.gz backup archives
├── scripts/                      # User-defined audit scripts + script_audit.log
├── mtg/
│   └── instances/                # Per-instance TOML configs
├── run.py                        # Entry point
├── config.py                     # Config classes with env-based overrides
├── requirements.txt              # Python dependencies
├── install.sh                    # Full Debian installation script
├── mtg_install.sh                # MTG runtime-only installer
├── init_app.sh                   # DB schema + admin user init
├── create_admin.py               # CLI admin management tool
├── .env.example                  # Environment variables template
├── AGENTS.md                     # AI agent operational guidance
├── structure.md                  # This file
└── README.md                     # Project overview and documentation
