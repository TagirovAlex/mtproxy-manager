# MTProxy Manager — Project Map

## 1. Security Audit

### 1.1 Найденные уязвимости и замечания

#### 🔴 HIGH — Open Redirect в `auth.py`

| Файл | Строка | Проблема |
|------|--------|----------|
| `app/routes/auth.py` | 127-129 | `next_page.startswith('/')` пропускает `//evil.com` |

Проверка `next_page.startswith('/')` не защищает от атак типа `//evil.com` — значение начинается с `/`, но браузер интерпретирует `//` как протокол-относительный URL и перенаправляет на внешний сайт.

**Исправление:** `urllib.parse.urlparse(next_page).netloc == ''` или `not next_page.startswith('//')`.

#### 🟡 MEDIUM — SECRET_KEY генерируется при каждом рестарте

| Файл | Строка | Проблема |
|------|--------|----------|
| `config.py` | 32 | `SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(32).hex()` |

Если `SECRET_KEY` не задан в `.env`, при каждом рестарте gunicorn генерируется новый ключ, что инвалидирует все активные сессии пользователей.

**Исправление:** Убрать fallback на `os.urandom`, требовать явного указания `SECRET_KEY` в production.

#### 🟡 MEDIUM — Rate limiting только на auth

| Эндпоинты | Проблема |
|-----------|----------|
| CRUD ключей, админ-настройки, скрипты, бэкапы | Не защищены rate limit'ом |

Атака на форму создания инстанса (`/keys/create`) или запуск скриптов (`/scripts/run`) не ограничена по частоте.

**Исправление:** Добавить `@limiter.limit()` на mutation-эндпоинты.

#### 🟡 MEDIUM — Дублирование `admin_required` декоратора

| Файлы | Проблема |
|-------|----------|
| `admin.py`, `users.py`, `scripts.py`, `backup.py` | Один и тот же декоратор скопирован 4 раза |

Нарушение DRY, при изменении логики проверки прав нужно менять в 4 местах.

**Исправление:** Вынести в `app/decorators.py`.

#### 🟢 LOW — `SESSION_COOKIE_SECURE = False`

`config.py:40` — в production за HTTPS флаг должен быть `True`. В DevelopmentConfig это ок, но ProductionConfig наследует без переопределения.

#### 🟢 LOW — Нет валидации `status_filter`

`keys.py:33`, `admin.py:171` — параметр `status` из URL передаётся напрямую в `filter_by()`. SQLAlchemy параметризует запросы (SQLi нет), но возможна передача произвольных значений.

#### 🟢 LOW — Legacy `ProxyKey` модель всё ещё используется

`profile.py` и `create_admin.py` используют `ProxyKey` вместо `ProxyInstance`. `TrafficLog` FK привязан к `ProxyKey`. При удалении пользователя отвязываются только ключи, не инстансы.

#### 🟢 LOW — `check_traffic_limits` пустая

`mtg_service.py:261` — функция `check_traffic_limits(app)` вызвается из scheduler каждые 5 минут, но тело пустое (`return`). Лимиты проверяются только через `traffic_monitor.update_instance_counters()` раз в минуту.

### 1.2 Что проверено — рисков нет

| Категория | Результат |
|-----------|-----------|
| XSS (`.render_template_string`, `Markup`) | Не используется — все шаблоны через `render_template` с autoescaping |
| SQL injection | Нет сырых SQL-запросов — везде SQLAlchemy ORM |
| Command injection (subprocess) | `_run_cmd` и `_run_script` — аргументы из конфига/кода, не из пользователя |
| Path traversal (scripts) | `os.path.basename` + `_safe_realpath` с проверкой `startswith(base)` |
| Path traversal (backup) | `_safe_extract` проверяет `startswith(base + os.sep)` |
| Unsafe deserialization | Нет `pickle`, `yaml.load` — только `json.loads` |
| CSRF | Включена глобально через `CSRFProtect`, нет `csrf.exempt` |
| Session management | Flask-Login с `session_protection = "strong"`, нет прямого доступа к `session` |
| Password storage | Werkzeug `scrypt` (memory-hard hashing) |
| Sudoers | Строго ограниченный набор команд `systemctl` для `mtg@*.service` |
| Экранирование в шаблонах | Jinja2 autoescaping |
| IP-блокировка | `LoginAttempt` считает неудачные попытки по IP |

---

## 2. Import-граф (зависимости модулей)

```
                       config.py  [leaf]
                          │
                          ▼
                    app/__init__.py  (central hub)
                   /    |    |    \
                  ▼     ▼    ▼    ▼
            models.py forms.py  services/
               │                  ├── key_generator.py  [leaf]
               │                  ├── system_monitor.py [leaf]
               │                  ├── mtg_service.py
               │                  ├── traffic_monitor.py
               │                  └── backup_service.py
               │
          routes/
          ├── auth.py  —> models + forms
          ├── admin.py —> models + forms + mtg_service + traffic_monitor + system_monitor
          ├── keys.py  —> models + forms + mtg_service + traffic_monitor
          ├── users.py —> models
          ├── profile.py —> models + forms
          ├── scripts.py —> forms ONLY (+ прямой доступ к ФС)
          └── backup.py  —> forms + backup_service

    create_admin.py  —> app.create_app + models (lazy)

    run.py  —> app.create_app
```

**Ключевые наблюдения:**
- **`app/__init__.py`** — центральный хаб: владеет всеми расширениями (`db`, `login_manager`, `csrf`, `limiter`, `scheduler`)
- **`app/models.py`** — хаб данных: 6 из 7 роутов и 3 из 5 сервисов импортируют модели
- **Leaf-модули** (не импортируют проект): `config.py`, `key_generator.py`, `system_monitor.py`
- **Самый изолированный роут**: `scripts.py` — импортирует только `app.forms.ScriptRunForm`
- **Циклических зависимостей нет** — все потенциальные циклы разорваны lazy-импортами

### Дублирование кода

| Фрагмент | Количество копий | Файлы |
|----------|-----------------|-------|
| `admin_required` декоратор | 4 | `admin.py`, `users.py`, `scripts.py`, `backup.py` |
| `format_bytes` | 3 | `models.py:150`, `traffic_monitor.py:47`, `profile.py:113` |

---

## 3. Карта файлов (File Map)

### 3.1 Корневые файлы

#### `run.py` — точка входа
```
Функции: нет (модуль верхнего уровня)
Импорты: app.create_app
Что делает: создаёт Flask-приложение через фабрику, запускает dev-сервер
            для разработки. В production запускается через gunicorn.
```

#### `config.py` — конфигурация
```
Классы:
  - Config          — базовый класс, все настройки из env
  - DevelopmentConfig  — DEBUG=True, SYSTEMCTL_USE_SUDO=False
  - ProductionConfig   — DEBUG=False

Хелперы: _env_bool, _env_int, _env_list
Словарь: config = {"development": ..., "production": ..., "default": ...}

Что делает: читает переменные окружения, формирует настройки приложения.
            Определяет пути: DATA_PATH, LOGS_PATH, BACKUPS_PATH, SCRIPTS_PATH.
            Настройки MTG, systemd, script runner, лимитов логина.
```

#### `requirements.txt` — 15 зависимостей Python

#### `create_admin.py` — CLI-инструмент
```
Функции:
  create_app_context()     — создаёт контекст приложения
  list_admins()           — список всех админов
  create_admin()          — создание/обновление админа
  change_password()       — смена пароля
  promote_admin()         — назначение админом
  demote_admin()          — снятие прав
  reset_user()            — сброс блокировки
  delete_user()           — удаление пользователя
  get_password_interactive() — интерактивный ввод пароля
  main()                  — парсер аргументов
```

#### `install.sh` — установщик (8 шагов)
```
Шаги:
  1. apt-get install пакетов (python3, git, curl, jq, sqlite3, ...)
  2. Создание пользователя/группы mtproxy
  3. git clone/репозитория в /opt/mtproxy-manager
  4. Python venv + pip install -r requirements.txt
  5. Создание директорий (data, logs, backups, scripts, mtg/instances)
  6. Установка MTG (Secure: SHA256 verification)
  7. systemd units (mtg@.service, mtproxy-manager.service) + sudoers
  8. chown + permissions + enable --now сервиса
  Опционально: Nginx reverse proxy + certbot
```


#### `uninstall.sh` — удаление (7 шагов)

---

### 3.2 `app/__init__.py` — Фабрика приложения

```
Объекты на уровне модуля:
  db            — SQLAlchemy
  migrate       — Migrate (Alembic)
  login_manager — LoginManager
  csrf          — CSRFProtect
  limiter       — Limiter
  scheduler     — BackgroundScheduler

Функции:
  create_app(config_name)         — фабрика: инициализирует расширения,
                                    настраивает логирование, регистрирует
                                    blueprints, создаёт таблицы БД,
                                    запускает scheduler, регистрирует
                                    обработчики ошибок, контекстные процессоры
  register_blueprints(app)        — регистрирует 7 blueprints
  setup_logging(app)              — RotatingFileHandler (10MB, 10 backups)
  setup_scheduler(app)            — 3 задачи:
                                    - traffic stats: interval 1min
                                    - traffic limits: interval 5min
                                    - auto backup: cron 3:00
  register_error_handlers(app)    — 404, 403, 500, 429
  register_context_processors(app) — app_name, app_version
  load_user(user_id)              — @login_manager.user_loader

Зависимости: config, models, routes.* (lazy), services.* (lazy)
```

---

### 3.3 `app/models.py` — Модели данных

#### `User` (таблица `users`)
```
Поля:
  id, email, password_hash, is_admin, is_approved, is_blocked
  failed_login_attempts, locked_until
  created_at, updated_at, last_login

Связи:
  keys       — ProxyKey (owner)
  instances  — ProxyInstance (owner)

Методы:
  set_password(password)         — scrypt hashing
  check_password(password)       — проверка пароля
  is_locked()                    — проверка блокировки по времени
  increment_failed_login()       — +1 попытка, блокировка при превышении
  reset_failed_login()           — сброс счётчика
  get_status()                   — текст статуса
```

#### `ProxyKey` (таблица `proxy_keys`) — **LEGACY**
```
Поля: id, name, secret, fake_tls_domain, user_id
      is_active, is_blocked
      traffic_limit, traffic_limit_period, traffic_used, traffic_reset_at
      total_traffic, last_activity, connection_count
      created_at, updated_at, notes

Связи: traffic_logs — TrafficLog

Методы: generate_secret, get_tg_link, get_https_link, get_qr_data,
        check_traffic_limit, reset_traffic_if_needed,
        _calculate_next_reset, set_traffic_limit, add_traffic,
        get_status, format_traffic (static)
```

#### `ProxyInstance` (таблица `proxy_instances`) — **активная модель**
```
Поля: id (UUID), name, secret, fake_tls_domain
      bind_ip, bind_port, stats_port
      owner_user_id, is_enabled, is_blocked
      total_traffic, traffic_used, connection_count, last_activity
      traffic_limit_bytes, traffic_limit_period
      period_started_at, period_baseline_bytes, period_used_bytes
      paused_by_limit, limit_exceeded_at
      notes, created_at, updated_at

Уникальность: (bind_ip, bind_port), stats_port

Свойства:
  unit_name   — "mtg@{id}.service"
  status_label — текст статуса (Активен/Отключен/Заблокирован/Остановлен по лимиту)

Методы:
  get_tg_link, get_https_link — ссылки для подключения
  _period_seconds             — длительность периода в секундах
  reset_limit_period_if_needed — сброс периода лимита при истечении
  update_period_usage         — расчёт использованного трафика за период
  is_limit_exceeded           — проверка превышения лимита
```

#### `TrafficLog` (таблица `traffic_logs`)
```
Поля: id, key_id (FK→proxy_keys), timestamp, bytes_in, bytes_out, connections

Связана с ProxyKey, НЕ с ProxyInstance.
```

#### `LoginAttempt` (таблица `login_attempts`)
```
Поля: id, ip_address, email, success, timestamp, user_agent

Методы:
  get_failed_attempts(ip, minutes) — количество неудачных попыток
  is_ip_blocked(ip, ...)           — проверка блокировки по IP
```

#### `Settings` (таблица `settings`)
```
Поля: id, key (unique), value, value_type, description

Методы:
  get(key, default)            — чтение с type coercion
  set(key, value, type, desc) — upsert
  init_defaults()              — 6 настроек по умолчанию:
                                 server_domain, max_keys_per_user,
                                 auto_backup_enabled/interval,
                                 instance_port_start, instance_stats_port_start
```

#### `BackupRecord` (таблица `backup_records`)
```
Поля: id, filename, filepath, size, backup_type, created_at, notes
```

---

### 3.4 `app/forms.py` — WTForms

| Форма | Назначение | Валидаторы |
|-------|-----------|------------|
| `LoginForm` | Вход | Email, DataRequired |
| `RegistrationForm` | Регистрация | Email, Length(min=8), EqualTo, уникальность email |
| `ProfileForm` | Редактирование профиля | Current password check, уникальность email |
| `CreateKeyForm` | Создание инстанса | Уникальность порта, лимит МБ |
| `EditKeyForm` | Редактирование инстанса | Уникальность порта (кроме себя), лимит МБ |
| `UserManageForm` | Управление пользователем | — |
| `SettingsForm` | Настройки | Domain, NumberRange, валидация интервала |
| `BackupForm` | Создание бэкапа | Length(max=500) |
| `ScriptRunForm` | Запуск скрипта | HiddenField с DataRequired |
| `ConfirmActionForm` | Подтверждение | HiddenField |

---

### 3.5 `app/routes/` — Blueprints

#### `auth.py` — Аутентификация
```
Blueprint: auth (без префикса)
Роуты:
  GET/POST  /            — index: редирект на dashboard или keys
  GET/POST  /login       — login: rate limit 10/min, IP-block, lock check
  GET/POST  /register    — register: rate limit 5/hour, первый юзер — admin
  GET       /logout      — logout
  GET       /pending     — страница ожидания подтверждения

Зависимости: app (db, limiter), models (User, LoginAttempt), forms (LoginForm, RegistrationForm)
```

#### `admin.py` — Админ-панель
```
Blueprint: admin (префикс /admin)
Роуты:
  GET       /dashboard       — дашборд со статистикой
  POST      /mtg/start       — запуск всех MTG инстансов
  POST      /mtg/stop        — остановка всех
  POST      /mtg/restart     — перезапуск всех
  POST      /mtg/reload      — перезагрузка конфига
  GET/POST  /settings        — настройки приложения
  GET       /users           — список пользователей
  GET/POST  /users/<id>      — управление пользователем
  POST      /users/<id>/approve — подтверждение
  POST      /users/<id>/block   — блокировка
  POST      /users/<id>/unblock — разблокировка
  POST      /users/<id>/delete  — удаление
  GET       /api/system-stats   — JSON системные метрики
  GET       /api/traffic-stats  — JSON трафик по инстансам

Декоратор: admin_required (local)
Зависимости: app (db), models (4), forms (2), services (mtg_service, system_monitor, traffic_monitor)
```

#### `keys.py` — Управление инстансами MTG
```
Blueprint: keys (префикс /keys)
Роуты:
  GET       /                 — список инстансов (с фильтром, пагинацией)
  GET/POST  /create           — создание инстанса
  GET       /<key_id>         — детали инстанса (ссылки, трафик, статус)
  GET/POST  /<key_id>/edit    — редактирование
  POST      /<key_id>/regenerate   — перегенерация secret
  POST      /<key_id>/start        — запуск systemd unit
  POST      /<key_id>/stop         — остановка
  POST      /<key_id>/restart      — перезапуск
  POST      /<key_id>/toggle       — вкл/выкл
  POST      /<key_id>/block        — блокировка
  POST      /<key_id>/unblock      — разблокировка
  POST      /<key_id>/delete       — удаление (остановка, disable, удаление конфига)

Хелперы: _can_access, _mb_to_bytes (local)
Зависимости: app (db), models (ProxyInstance, Settings), forms (CreateKeyForm, EditKeyForm),
             services (mtg_service, traffic_monitor)
```

#### `users.py` — Управление пользователями (админ)
```
Blueprint: users (префикс /users)
Роуты:
  GET       /                       — редирект на admin.users_list
  GET       /<id>/keys              — инстансы пользователя
  POST      /<id>/assign-key        — привязка инстанса
  POST      /<id>/unassign-key/<key_id> — отвязка
  GET       /<id>/login-history     — история входов
  POST      /<id>/reset-password    — сброс пароля (админ)
  GET       /api/search             — поиск пользователей (JSON)
  GET       /api/unassigned-keys    — непривязанные инстансы (JSON)

Декоратор: admin_required (local, дубль)
Зависимости: app (db), models (User, ProxyInstance, LoginAttempt)
```

#### `profile.py` — Профиль пользователя
```
Blueprint: profile (префикс /profile)
Роуты:
  GET/POST  /          — редактирование профиля (email, пароль)
  GET       /my-keys   — свои ключи (для user, не admin)
  GET       /sessions  — история входов

Хелпер: format_bytes (local)
Зависимости: app (db), models (User, ProxyKey, LoginAttempt, Settings[lazy]), forms (ProfileForm)
```

#### `scripts.py` — Безопасный запуск скриптов
```
Blueprint: scripts (префикс /scripts)
Роуты:
  GET       /                 — список скриптов из allowlist
  GET       /<name>           — просмотр кода скрипта
  POST      /run              — выполнение скрипта
  GET       /history          — аудит-лог запусков

Хелперы:
  admin_required       (local, дубль)
  _scripts_dir         — путь к директории скриптов
  _safe_realpath       — защита от path traversal (basename + realpath check)
  _load_allowlist      — загрузка allowlist из config/env/авто-детект
  _build_command       — формирование команды (.sh → /bin/bash, .py → python3)
  _run_script          — subprocess.run с таймаутом
  _append_audit_line   — запись в script_audit.log

Зависимости: app.forms (ScriptRunForm) — самый изолированный роут
```

#### `backup.py` — Управление бэкапами
```
Blueprint: backup (префикс /backup)
Роуты:
  GET       /                   — список бэкапов
  POST      /create             — создание бэкапа
  GET       /<id>/download      — скачивание
  POST      /<id>/restore       — восстановление
  POST      /<id>/delete        — удаление
  GET       /<id>/info          — информация о бэкапе
  POST      /settings           — настройки автобэкапа

Декоратор: admin_required (local, дубль)
Зависимости: app.forms (BackupForm), app.services.backup_service
```

---

### 3.6 `app/services/` — Бизнес-логика

#### `key_generator.py` — Генерация FakeTLS секретов
```
Класс: KeyGenerator (все методы classmethod)

Константы:
  FAKE_TLS_PREFIX = "ee"
  RANDOM_BYTES_LENGTH = 16
  DEFAULT_DOMAIN = "www.google.com"

Методы:
  generate_secret(domain)                    — ee + 16 байт random + domain hex
  _normalize_domain(domain)                  — trim + lower + strip dot
  _is_valid_domain(domain)                   — regex FQDN валидация
  decode_domain_from_secret(secret)          — извлечение домена из secret
  validate_secret(secret)                    — полная валидация: префикс, hex, домен
  get_secret_info(secret)                    — словарь с информацией
  format_secret_for_display(secret)          — маскирование (показать первые/последние 8)
  generate_proxy_links(secret, server, port) — tg://, https://, t.me ссылки
  get_allowed_domains()                      — список подсказок доменов
  regenerate_secret_with_domain(domain)      — перегенерация с новым доменом

Зависимости: нет (чистый Python + stdlib)
```

#### `mtg_service.py` — Управление MTG и systemd
```
Класс: MTGService

Свойства: mtg_binary, mtg_config_dir, instances_dir, use_sudo

Методы:
  is_installed()            — проверка наличия бинарника
  get_version()             — --version
  _run_cmd(cmd, timeout)    — subprocess.run обёртка
  _systemctl(action, unit)  — systemctl через sudo -n
  _instance_unit(id)        — "mtg@{id}.service"
  _instance_toml_path(id)   — путь к TOML конфигу
  _pick_free_stats_port()   — поиск свободного stats_port
  generate_instance_config  — запись TOML файла
  create_instance           — создание: secret → UUID → конфиг → daemon-reload → enable → start
  update_instance           — перегенерация secret/конфига → restart
  delete_instance           — stop → disable → rm toml → rm from DB
  start_instance            — generate config → systemctl start
  stop_instance             — systemctl stop
  restart_instance          — generate config → systemctl restart
  instance_status           — is-active + MainPID
  start/stop/restart        — массовые операции по всем инстансам
  reload_config             — alias restart
  get_status                — сводка: установлен, версия, кол-во инстансов
  get_stats                 — заглушка (None)

Функции модуля:
  check_traffic_limits(app) — заглушка (пустая)
  get_mtg_service()         — фабрика

Зависимости: app (db), models (ProxyInstance, Settings), key_generator
```

#### `traffic_monitor.py` — Мониторинг трафика
```
Класс: TrafficMonitor

Методы:
  init_app(app)                      — инициализация
  _format_bytes(bytes)               — форматирование
  _parse_metric_with_labels(raw)     — парсинг Prometheus метрик с labels
  _parse_prometheus_metrics(text)    — парсинг /metrics: connections, bytes_in, bytes_out
  _fetch_instance_metrics(port)      — HTTP GET http://127.0.0.1:{port}/metrics
  get_key_stats(instance_id, period) — статистика одного инстанса
  get_all_keys_stats(period)         — статистика всех инстансов
  get_hourly_stats(instance_id, hours) — заглушка ([])
  get_daily_stats(instance_id, days)   — заглушка ([])
  get_total_stats()                  — суммарная статистика
  update_instance_counters()         — обновление total_traffic, проверка лимитов,
                                       автостоп при превышении, автозапуск при
                                       новом периоде
  cleanup_old_logs(days)             — заглушка (0)

Функции модуля:
  update_traffic_stats(app) — scheduler callback (interval 1min)
  get_traffic_monitor(app)  — фабрика

Зависимости: app (db), models (ProxyInstance), mtg_service (lazy)
```

#### `backup_service.py` — Бэкапы
```
Класс: BackupService

Константа: BACKUP_ITEMS = ["data/mtproxy.db", "mtg/mtg.toml", "scripts/"]

Свойства: backup_dir

Методы:
  _base_dir()                        — корень проекта
  create_backup(notes, type)         — tar.gz + metadata + BackupRecord
  _safe_extract(tar, path)           — защита от path traversal
  restore_backup(backup_id)          — safe_extract → копирование файлов
  get_all_backups()                  — все BackupRecord
  get_backup_settings()              — настройки из Settings
  update_backup_settings()           — обновление Settings
  download_backup(backup_id)         — путь к файлу
  delete_backup(backup_id)           — удаление файла + записи
  get_backup_info(backup_id)         — одна запись
  _is_backup_due(interval)           — проверка, пора ли делать автобэкап

Функции модуля:
  auto_backup(app)       — scheduler callback (cron 3:00)
  get_backup_service()   — фабрика

Зависимости: app (db), models (BackupRecord, Settings)
```

#### `system_monitor.py` — Мониторинг системы
```
Класс: SystemMonitor (все методы staticmethod)

Методы:
  get_cpu_usage()          — % по ядрам, load average (Unix)
  get_memory_usage()       — RAM + swap
  get_disk_usage()         — корневой раздел + IO
  get_network_usage()      — интерфейсы (кроме lo)
  get_uptime()             — аптайм + boot_time
  get_processes_info()     — топ 5 по CPU и памяти
  get_mtg_process_info()   — процесс mtg (pid, cpu, memory, threads)
  get_full_stats()         — всё сразу
  _format_bytes()          — форматирование
  check_system_health()    — статус ok/warning/critical с порогами

Функции модуля:
  get_system_stats()  — быстрый доступ
  get_system_monitor() — фабрика

Зависимости: psutil, os, datetime (нет импортов проекта)
```

---

### 3.7 `app/templates/` — Шаблоны

| Шаблон | Назначение |
|--------|-----------|
| `base.html` | Основной layout: sidebar (навигация, MTG статус), topbar (user info, logout), flash-сообщения, контент |
| `auth/login.html` | Форма входа |
| `auth/register.html` | Форма регистрации |
| `auth/pending.html` | Страница ожидания подтверждения |
| `admin/dashboard.html` | Дашборд: MTG статус, пользователи, инстансы, трафик, таблица мониторинга |
| `admin/setting.html` | Настройки приложения |
| `admin/users.html` | Список пользователей с фильтрацией |
| `admin/user_manage.html` | Управление пользователем (роли, инстансы, пароль) |
| `admin/users/keys.html` | Инстансы пользователя |
| `admin/users/login_history.html` | История входов |
| `admin/keys/list.html` | Список инстансов с фильтрацией |
| `admin/keys/create.html` | Создание инстанса |
| `admin/keys/edit.html` | Редактирование инстанса |
| `admin/keys/detail.html` | Детали инстанса (ссылки, трафик, лимиты, статус) |
| `admin/scripts.html` | Список скриптов |
| `admin/script_view.html` | Просмотр кода скрипта |
| `admin/script_history.html` | Аудит-лог запусков |
| `admin/scripts_result.html` | Результат выполнения скрипта |
| `admin/backup/index.html` | Список бэкапов |
| `admin/backup/info.html` | Информация о бэкапе |
| `admin/profiles/edit.html` | Редактирование профиля |
| `admin/profiles/my_keys.html` | Свои ключи (для user) |
| `admin/profiles/sessions.html` | История сессий |
| `admin/errors/403.html` | Доступ запрещён |
| `admin/errors/404.html` | Не найдено |
| `admin/errors/429.html` | Too Many Requests |
| `admin/errors/500.html` | Внутренняя ошибка |

---

### 3.8 `app/static/` — Статика

| Файл | Строк | Описание |
|------|-------|----------|
| `css/style.css` | ~2100 | Кастомный CSS: CSS Variables, sidebar, карточки, таблицы, формы, кнопки, badges, пагинация, графики, ошибки, адаптивность. Без фреймворков. |
| `js/main.js` | ~417 | Vanilla JS: sidebar toggle, alert auto-close, copy to clipboard, form confirmation, MTG status widget, dashboard auto-refresh, debounce, CSRF fetch helper, password match validation |

---

### 3.9 `app/migrations/versions/` — Миграции

| Файл | Описание |
|------|----------|
| `20261001_add_proxy_instances.py` | Создание таблицы `proxy_instances`, миграция активных ключей из `proxy_keys` с присвоением портов (начиная с 10000/31000) |
| `20261002_add_proxy_instance_limits.py` | Добавление 7 колонок лимитов в `proxy_instances` |

---

### 3.10 `app/deploy/systemd/` — Шаблон systemd

| Файл | Описание |
|------|----------|
| `mtg@.service` | Template unit `mtg@%i.service`. Пользователь mtproxy, AmbientCapabilities=CAP_NET_BIND_SERVICE, NoNewPrivileges=true, LimitNOFILE=65536 |

---

## 4. Data Flow

### 4.1 Создание инстанса

```
User → POST /keys/create
  → CreateKeyForm.validate_on_submit()
    → проверка уникальности (bind_ip, bind_port)
    → проверка лимита инстансов (для user)
  → get_mtg_service().create_instance()
    → KeyGenerator.generate_secret(domain)
      → random 31 bytes + "ee" prefix
    → ProxyInstance() + db.session.add + commit
    → generate_instance_config() → TOML файл
    → systemctl daemon-reload
    → systemctl enable mtg@{id}.service
    → systemctl start mtg@{id}.service
  → установка лимитов
  → redirect /keys/{id}
```

### 4.2 Мониторинг трафика

```
APScheduler (каждую 1 мин)
  → update_traffic_stats(app)
    → TrafficMonitor().update_instance_counters()
      → для каждого активного инстанса:
        → _fetch_instance_metrics(stats_port)
          → GET http://127.0.0.1:{port}/metrics
          → _parse_prometheus_metrics(text)
            → mtg_client_connections
            → mtg_telegram_traffic{from_client|to_client}
        → обновление total_traffic, connection_count, last_activity
        → reset_limit_period_if_needed()
        → update_period_usage()
        → если лимит превышен → stop_instance + paused_by_limit
        → если новый период и был paused → start_instance + unpause

APScheduler (каждые 5 мин)
  → check_traffic_limits(app)  — [ЗАГЛУШКА, пустая]
```

### 4.3 Аутентификация

```
POST /login
  → Rate limit: 10/min
  → IP block check (LoginAttempt.is_ip_blocked)
  → User query by email
  → Lock check (user.is_locked)
  → Password check (user.check_password) — scrypt
  → Account status check (is_blocked, is_approved)
  → user.reset_failed_login()
  → login_user()
  → LoginAttempt log (success=true)
  → Redirect (next_page с защитой startswith('/') или dashboard/keys)
```

### 4.4 Бэкапы

```
POST /backup/create
  → BackupService.create_backup()
    → tar.gz: data/mtproxy.db + mtg/mtg.toml + scripts/ + metadata.json
    → BackupRecord → DB
    → return filepath

APScheduler (cron 3:00)
  → auto_backup(app)
    → Settings.get("auto_backup_enabled")
    → if enabled & due → create_backup(type="auto")
```

---

## 5. Модель угроз (Threat Model)

| Вектор | Риск | Существующая защита | Статус |
|--------|------|-------------------|--------|
| Подбор пароля | Средний | Rate limit (10/min), block after N attempts, scrypt hashing | ✅ |
| Перехват сессии | Средний | HTTPOnly cookie, SameSite=Lax, `session_protection="strong"` | ✅ |
| Session fixation | Низкий | Flask-Login regenerates session on login | ✅ |
| Path traversal (scripts) | Высокий | `os.path.basename` + `_safe_realpath` + allowlist | ✅ |
| Path traversal (backup) | Высокий | `_safe_extract` c `startswith(base)` | ✅ |
| Open redirect | Средний | `next_page.startswith('/')` — частично | ❌ (//evil.com) |
| CSRF | Высокий | Flask-WTF CSRFProtect глобально | ✅ |
| XSS | Высокий | Jinja2 autoescaping | ✅ |
| SQL injection | Критический | SQLAlchemy ORM параметризация | ✅ |
| Command injection | Критический | `subprocess.run` с контролируемыми аргументами | ✅ |
| Privilege escalation | Критический | sudoers с ограниченным набором команд | ✅ |
| SSRF | Средний | requests.get только на 127.0.0.1:{stats_port} | ✅ |
| Unsafe deserialization | Критический | Только `json.loads` | ✅ |
| Secret key rotation | Средний | fallback на os.urandom при каждом рестарте | ❌ |
| Rate limiting (mutation) | Средний | Только на auth, не на CRUD/scripts | ❌ |

---

## 6. Рекомендации по улучшению

### Критические
1. **Исправить Open Redirect** в `auth.py:127` — добавить проверку `not next_page.startswith('//')`

### Средние
2. **Убрать fallback SECRET_KEY** в `config.py:32` — требовать явного указания в production
3. **Добавить rate limiting** на mutation-эндпоинты: создание/редактирование инстансов, запуск скриптов
4. **Вынести `admin_required`** в общий декоратор `app/decorators.py`
5. **Реализовать `check_traffic_limits`** — сейчас пустая заглушка
6. **Добавить `SESSION_COOKIE_SECURE = True`** в ProductionConfig

### Низкие
7. **Вынести `format_bytes`** в общий хелпер
8. **Удалить `ProxyKey`** после миграции всего кода на `ProxyInstance`
9. **Перепривязать `TrafficLog`** к `ProxyInstance` вместо `ProxyKey`
10. **Добавить валидацию** параметра `status` в фильтрах списков
11. **Заменить `os.path.basename`** на `werkzeug.utils.secure_filename` где уместно
