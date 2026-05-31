# MTProxy Manager (Multi-Instance MTG, SQLite)

Проект делался под свои узконаправленные потребности. Стабильность и качество сами понимаете ... никто не обещает. Но сервис работает и заявленное выполняет.
Если у вас есть желание/возможность поспособствовать улучшению - буду рад выслушать ваши предложения.

Веб-панель управления [MTG](https://github.com/9seconds/mtg) (Telegram MTProto Proxy) с поддержкой **multi-instance**:
- 1 инстанс = 1 секретный ключ = 1 systemd unit `mtg@<instance_id>.service`
- Управление через UI: create / edit / start / stop / restart / delete / block
- Мониторинг трафика и соединений по каждому инстансу через Prometheus-метрики
- Лимиты трафика: **без лимита / день / неделя / месяц** с автоостановкой при превышении и автозапуском при сбросе периода
- Режим **Frontend** — MTG на сервере А, трафик через WireGuard туннель на сервер Б (NAT/gateway)
- База данных: **только SQLite**
- Безопасный запуск shell-скриптов с allowlist и аудитом

## Возможности

- Аутентификация пользователей, роли (admin/user), подтверждение регистрации админом
- Админ-панель: дашборд со статистикой, управление пользователями, настройки
- Multi-instance: неограниченное количество proxy-инстансов, каждый со своим портом и secret
- **Frontend-режим**: инстанс с ролью `frontend` + IP backend сервера в WireGuard туннеле
- Генерация FakeTLS secret с произвольным валидным доменом (`ee + 16 байт + домен`)
- Авто-генерация конфигов `mtg/instances/<id>.toml` (формат TOML для MTG)
- Управление systemd юнитами `mtg@*.service` через sudoers
- Мониторинг метрик MTG через Prometheus endpoint каждого инстанса (`mtg_client_connections`, `mtg_telegram_traffic`)
- Лимиты трафика с периодами: пересчёт периода, остановка при превышении, автозапуск при новом периоде
- Бэкапы (tar.gz): ручные и автоматические (по расписанию APScheduler), с восстановлением
- Системный мониторинг: CPU, RAM, диск, сеть, процессы, аптайм, информация о процессе MTG
- Безопасный запуск скриптов: только admin, только из allowlist, с аудитом в `script_audit.log`
- Защита форм через CSRF
- Rate limiting на логин и регистрацию
- Отслеживание попыток входа (IP-based блокировка)
- Управление пользователями: approve/block/delete, привязка инстансов, просмотр истории входов
- Профиль пользователя: смена email/пароля, просмотр своих ключей и сессий
- Telegram-ссылки для каждого инстанса (tg://, https://t.me/)
- QR-код данные для подключения

## Архитектура

- **Backend**: Flask 3.1 (Python 3)
- **DB**: SQLite (через Flask-SQLAlchemy)
- **WSGI**: Gunicorn
- **Scheduler**: APScheduler (трафик каждую минуту, лимиты каждые 5 минут, бэкап в 3:00)
- **Migrations**: Flask-Migrate / Alembic
- **Proxy runtime**: MTG (golang)
- **Service manager**: systemd (template unit)
- **CI/Deploy**: Bash install scripts
- **Администрирование**: CLI-скрипт `create_admin.py`
- **Frontend**: Jinja2 шаблоны + CSS (кастомный) + Vanilla JS
- **Туннель (опционально)**: WireGuard

## Быстрый старт (Debian 12)

### 1) Установка

**Сервер А (с панелью и MTG):**
~~~bash
sudo MTG_SHA256="<sha256_архива_mtg>" bash install.sh
~~~

Скрипт выполнит:
1. Установка пакетов (git, curl, jq, python3, sqlite3 и др.)
2. Создание пользователя `mtproxy`
3. Клонирование репозитория в `/opt/mtproxy-manager`
4. Создание Python venv + установка зависимостей
5. Создание директорий: `data`, `logs`, `backups`, `scripts`, `mtg/instances`
6. Установка MTG (авто-определение архитектуры, проверка SHA256)
7. Установка systemd unit: `mtg@.service` и `mtproxy-manager.service`
8. Настройка sudoers для управления `mtg@*.service`
9. **Опционально**: WireGuard туннель до backend-сервера (спросит при установке)

**Сервер Б (backend gateway — только WireGuard + NAT):**
~~~bash
sudo bash install_server_b.sh
~~~

Скрипт выполнит:
1. Установка WireGuard
2. Генерация ключей, создание конфига с PostUp правилами (NAT)
3. Включение `net.ipv4.ip_forward`
4. Запуск `wg-quick@wg0`

### 2) Конфигурация

~~~bash
sudo nano /opt/mtproxy-manager/.env
~~~

Минимум:
~~~env
FLASK_CONFIG=production
SECRET_KEY=change_me_to_long_random_secret
DATABASE_URL=sqlite:////opt/mtproxy-manager/data/mtproxy.db
MANAGER_BIND_HOST=127.0.0.1
MANAGER_BIND_PORT=5000
SYSTEMCTL_USE_SUDO=true
SERVER_DOMAIN=your-domain.example
~~~

Все переменные описаны в `.env.example`.

### 3) Инициализация (SQLite + admin)

~~~bash
sudo bash init_app.sh
~~~

Если хотите задать admin вручную:
~~~bash
sudo ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='StrongPassword123!' bash init_app.sh
~~~

Или через CLI:
~~~bash
cd /opt/mtproxy-manager && source .venv/bin/activate && python create_admin.py --create admin@example.com
~~~

### 4) Применение миграций

~~~bash
sudo -u mtproxy bash -c 'cd /opt/mtproxy-manager && source .venv/bin/activate && flask db upgrade'
~~~

### 5) Проверка сервиса панели

~~~bash
sudo systemctl status mtproxy-manager --no-pager
sudo journalctl -u mtproxy-manager -f
~~~

### 6) Доступ к панели

Если `MANAGER_BIND_HOST=127.0.0.1`, используйте SSH-туннель:
~~~bash
ssh -L 5000:127.0.0.1:5000 root@SERVER_IP
~~~

Открыть локально: `http://127.0.0.1:5000`

## Frontend / Backend (VPN tunnel)

### Архитектура

```
Клиенты → Сервер А (MTG + панель) → WireGuard → Сервер Б (NAT/gateway) → Telegram
```

- **Сервер А** — панель + MTG. Принимает клиентов, секрет хранится здесь.
- **Сервер Б** — чистый шлюз. Только WireGuard + `ip_forward` + MASQUERADE. Без MTG, без панели.
- Трафик от MTG до Telegram маршрутизируется через WireGuard туннель на сервер Б (NAT).

### Роли инстансов

В панели при создании инстанса можно выбрать роль:

| Роль | Описание |
|------|----------|
| `standalone` (по умолчанию) | Обычный инстанс, MTG работает напрямую |
| `frontend` | Инстанс на сервере А, трафик через ВПН-туннель на сервер Б |

Для `frontend` нужно указать **IP сервера Б в туннеле** (например, `10.0.0.1`).

### Установка

**Сервер Б (однократно):**
```bash
sudo bash install_server_b.sh
# Ввести IP сервера А, вставить его публичный ключ
```

**Сервер А:**
```bash
export FRONTEND_MODE=yes
sudo bash install.sh
# Или ответить "yes" на вопрос про frontend при установке
```

После установки обоих серверов:
```bash
# На сервере Б — скопировать публичный ключ Server B
# На сервере А — вставить его в /etc/wireguard/wg0.conf
systemctl enable --now wg-quick@wg0  # на обоих серверах
```

Проверка:
```bash
ping 10.0.0.1  # с сервера А
ping 10.0.0.2  # с сервера Б
```

## Multi-Instance MTG

### Systemd template unit

- `/etc/systemd/system/mtg@.service` — шаблон для всех инстансов (CapabilityBoundingSet=CAP_NET_BIND_SERVICE, NoNewPrivileges=true, LimitNOFILE=65536)

### Конфиги инстансов

- `/opt/mtproxy-manager/mtg/instances/<instance_id>.toml`

Формат:
~~~toml
secret = "ee<hex>"
bind-to = "0.0.0.0:10000"

[stats.prometheus]
enabled = true
bind-to = "127.0.0.1:31000"
http-path = "/metrics"
metric-prefix = "mtg"
~~~

Для frontend-инстансов конфиг идентичен — маршрутизация на уровне OC (WireGuard + ip route).

### Управление

~~~bash
systemctl status mtg@<instance_id>.service
systemctl restart mtg@<instance_id>.service
~~~

## Мониторинг трафика

MTG метрики читаются с локального Prometheus endpoint каждого инстанса:
- `mtg_client_connections` — количество соединений
- `mtg_telegram_traffic{direction="from_client"}` — входящий трафик (от клиента)
- `mtg_telegram_traffic{direction="to_client"}` — исходящий трафик (к клиенту)

Проверка вручную:
~~~bash
sqlite3 /opt/mtproxy-manager/data/mtproxy.db "select id,name,stats_port from proxy_instances;"
curl -s http://127.0.0.1:<stats_port>/metrics | head -n 100
~~~

Обновление статистики происходит каждую минуту через APScheduler.

## Лимиты трафика

Для каждого инстанса доступны режимы:
- `none` (без лимита)
- `day` — суточный лимит
- `week` — недельный лимит
- `month` — месячный лимит (30 дней)

Механизм:
- При превышении лимита инстанс останавливается и отмечается как `paused_by_limit`
- При наступлении нового периода инстанс автоматически запускается (если не заблокирован вручную)
- Проверка лимитов каждые 5 минут через APScheduler + при каждом обновлении трафика

## Управление пользователями

- Регистрация с подтверждением администратором
- Роли: admin / user
- Админ может: approve/block/delete пользователей, привязывать/отвязывать инстансы
- CLI-скрипт `create_admin.py`:
  - `--list` — список администраторов
  - `--create EMAIL` — создание администратора
  - `--password EMAIL` — смена пароля
  - `--promote EMAIL` / `--demote EMAIL` — управление правами
  - `--reset EMAIL` — сброс блокировки
  - `--delete EMAIL --confirm` — удаление пользователя
- История входов для каждого пользователя
- Блокировка аккаунта после N неудачных попыток (настраивается)

## Скрипты (Script Runner)

Безопасный запуск shell/Python скриптов из директории `scripts/`:
- Только для администраторов
- Только из `SCRIPT_ALLOWLIST` (настраивается в `.env`)
- Авто-детект скриптов: разрешены `.sh` и `.py`
- Защита от path traversal (только basename)
- Аудит всех запусков в `scripts/script_audit.log`
- Таймаут выполнения (по умолчанию 300 секунд)
- UI: список скриптов, просмотр кода, запуск, история

## Бэкапы

- Формат: `mtproxy_backup_<timestamp>.tar.gz`
- Состав: `data/mtproxy.db`, `mtg/mtg.toml`, `scripts/`
- Ручные: через веб-интерфейс
- Автоматические: ежедневно в 3:00 (настраивается)
- Возможность скачивания и восстановления из бэкапа
- Защита от path traversal при восстановлении

## Безопасность

- CSRF защита форм (Flask-WTF)
- Rate limiting: 10 попыток/мин на логин, 5/час на регистрацию
- Session protection: `strong` (проверка IP и User-Agent)
- Password hashing: scrypt (через Werkzeug)
- IP-based блокировка после N неудачных попыток
- Ограничение управления systemd через `sudoers` (`mtg@*.service`)
- Script runner: только allowlist, только admin, без пользовательских аргументов
- Бэкапы: safe extract с проверкой path traversal
- Первый зарегистрированный пользователь становится администратором
- Рекомендуется:
  - оставлять panel bind на `127.0.0.1`
  - публиковать наружу через Nginx + HTTPS
  - ограничить доступ к admin UI по IP
  - использовать сильный `SECRET_KEY`
  - включить UFW и открыть только нужные порты

## UFW пример

~~~bash
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 5000/tcp
sudo ufw allow 10000:10100/tcp
sudo ufw allow 51820/udp  # WireGuard (для frontend-режима)
sudo ufw enable
sudo ufw status
~~~

## Обновление проекта

~~~bash
cd /opt/mtproxy-manager
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
flask db upgrade
sudo systemctl restart mtproxy-manager
~~~

## Миграции БД

Используется Flask-Migrate. Миграции в `app/migrations/versions/`:
- `20261001_add_proxy_instances.py` — создание таблицы proxy_instances, миграция активных ключей из proxy_keys
- `20261002_add_proxy_instance_limits.py` — добавление полей лимитов трафика в proxy_instances
- `20261003_add_proxy_instance_roles.py` — добавление полей `role` (standalone/frontend) и `backend_tunnel_ip`

Применить миграции:
~~~bash
flask db upgrade
# или
sudo -u mtproxy bash -c 'cd /opt/mtproxy-manager && source .venv/bin/activate && flask db upgrade'
~~~

## Структура проекта

```
mtproxy-manager/
├── app/
│   ├── __init__.py              # Фабрика Flask-приложения
│   ├── models.py                # SQLAlchemy модели (включая role, backend_tunnel_ip)
│   ├── forms.py                 # WTForms
│   ├── routes/
│   │   ├── auth.py              # Аутентификация
│   │   ├── admin.py             # Админ-панель
│   │   ├── keys.py              # Управление инстансами
│   │   ├── users.py             # Управление пользователями
│   │   ├── profile.py           # Профиль пользователя
│   │   ├── scripts.py           # Безопасный запуск скриптов
│   │   └── backup.py            # Управление бэкапами
│   ├── services/
│   │   ├── mtg_service.py       # Управление MTG
│   │   ├── traffic_monitor.py   # Мониторинг трафика
│   │   ├── backup_service.py    # Бэкапы
│   │   ├── key_generator.py     # Генерация секретов
│   │   └── system_monitor.py    # Мониторинг системы
│   ├── templates/               # Jinja2 шаблоны
│   ├── static/                  # CSS, JS
│   ├── migrations/              # Alembic миграции (3 шт.)
│   └── deploy/systemd/          # systemd unit
├── data/                        # SQLite БД
├── logs/                        # Логи
├── backups/                     # Бэкапы
├── scripts/                     # Пользовательские скрипты
├── mtg/instances/               # TOML-конфиги инстансов
├── run.py                       # Точка входа
├── config.py                    # Конфигурация
├── requirements.txt             # Python-зависимости
├── install.sh                   # Установщик для сервера А (панель + MTG + опц. WireGuard)
├── install_server_b.sh          # Установщик для сервера Б (только WireGuard + NAT)
├── init_app.sh                  # Инициализация БД
├── create_admin.py              # CLI управление админами
├── .env.example                 # Пример конфига
└── AGENTS.md                    # Инструкции для AI-агентов
```

## Используемые библиотеки, ПО и ссылки

### Ядро приложения

- [Flask](https://palletsprojects.com/p/flask/) — BSD-3-Clause
- [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) — BSD-3-Clause
- [SQLAlchemy](https://www.sqlalchemy.org/) — MIT
- [Flask-Login](https://flask-login.readthedocs.io/) — MIT
- [Flask-WTF](https://flask-wtf.readthedocs.io/) — BSD
- [WTForms](https://wtforms.readthedocs.io/) — BSD
- [Flask-Migrate](https://flask-migrate.readthedocs.io/) — MIT
- [Alembic](https://alembic.readthedocs.io/) — MIT
- [Flask-Limiter](https://flask-limiter.readthedocs.io/) — MIT
- [limits](https://limits.readthedocs.io/) — MIT
- [Flask-APScheduler](https://github.com/viniciuschiele/flask-apscheduler) — MIT
- [APScheduler](https://apscheduler.readthedocs.io/) — MIT
- [python-dotenv](https://github.com/theskumar/python-dotenv) — BSD-3-Clause
- [requests](https://requests.readthedocs.io/) — Apache-2.0
- [psutil](https://github.com/giampaolo/psutil) — BSD-3-Clause
- [gunicorn](https://gunicorn.org/) — MIT
- [cryptography](https://cryptography.io/) — Apache-2.0 OR BSD-3-Clause
- [bleach](https://bleach.readthedocs.io/) — Apache-2.0
- [email-validator](https://github.com/JoshData/python-email-validator) — Unlicense
- [Werkzeug](https://werkzeug.palletsprojects.com/) — BSD-3-Clause

### Runtime / инфраструктура

- [MTG (9seconds/mtg)](https://github.com/9seconds/mtg) — MIT
- [systemd](https://systemd.io/) — LGPL-2.1-or-later
- [SQLite](https://sqlite.org/) — Public Domain
- [WireGuard](https://www.wireguard.com/) (опционально) — GPL-2.0
- [Nginx](https://nginx.org/) (опционально) — BSD-2-Clause
- [Debian](https://www.debian.org/) — свободное ПО

## Лицензия

Добавьте в репозиторий файл `LICENSE` (рекомендуется MIT):
- [MIT License template](https://opensource.org/license/mit/)

## Важные замечания

- Этот проект управляет сетевым прокси и системными сервисами, используйте только в соответствии с законами вашей юрисдикции.
- Telegram и связанные торговые марки принадлежат их правообладателям.
- Перед публикацией убедитесь, что в репозитории нет реальных секретов (`.env`, токены, приватные ключи).
