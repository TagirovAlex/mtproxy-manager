# MTProxy Manager (Multi-Instance MTG, SQLite)

Веб-панель управления [MTG](https://github.com/9seconds/mtg) с поддержкой **multi-instance**:
- 1 инстанс = 1 ключ (secret) = 1 unit `mtg@<instance_id>.service`
- Управление через UI: create / edit / start / stop / restart / delete
- Мониторинг трафика и соединений по каждому инстансу
- Лимиты трафика: **без лимита / день / неделя / месяц**
- База данных: **только SQLite**

## Возможности

- Аутентификация пользователей и роли (admin/user)
- Админ-панель управления инстансами MTG
- Генерация FakeTLS secret с пользовательским доменом
- Авто-генерация конфигов `mtg/instances/<id>.toml`
- Управление systemd юнитами `mtg@*.service`
- Мониторинг метрик MTG (`mtg_client_connections`, `mtg_telegram_traffic`)
- Лимиты трафика по периодам
- Бэкапы и базовые системные проверки
- Защита форм через CSRF

## Архитектура

- **Backend**: Flask
- **DB**: SQLite
- **WSGI**: Gunicorn
- **Scheduler**: APScheduler
- **Proxy runtime**: MTG
- **Service manager**: systemd
- **Firewall**: UFW (рекомендуется)
- **Reverse proxy (опционально)**: Nginx

## Быстрый старт (Debian 12)

### 1) Установка

~~~bash
sudo MTG_SHA256="<sha256_архива_mtg>" bash install.sh
~~~

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

### 3) Инициализация (SQLite + admin)

~~~bash
sudo bash init_app.sh
~~~

Если хотите задать admin вручную:
~~~bash
sudo ADMIN_EMAIL=admin@example.com ADMIN_PASSWORD='StrongPassword123!' bash init_app.sh
~~~

### 4) Проверка сервиса панели

~~~bash
sudo systemctl status mtproxy-manager --no-pager
sudo journalctl -u mtproxy-manager -f
~~~

### 5) Доступ к панели

Если `MANAGER_BIND_HOST=127.0.0.1`, используйте SSH-туннель:
~~~bash
ssh -L 5000:127.0.0.1:5000 root@SERVER_IP
~~~

Открыть локально:
`http://127.0.0.1:5000`

## Multi-Instance MTG

### Systemd template unit

- `/etc/systemd/system/mtg@.service`

### Конфиги инстансов

- `/opt/mtproxy-manager/mtg/instances/<instance_id>.toml`

### Управление

~~~bash
systemctl status mtg@<instance_id>.service
systemctl restart mtg@<instance_id>.service
~~~

## Мониторинг трафика

MTG метрики читаются с локального Prometheus endpoint каждого инстанса:
- `mtg_client_connections`
- `mtg_telegram_traffic{direction="from_client|to_client"}`

Проверка вручную:
~~~bash
sqlite3 /opt/mtproxy-manager/data/mtproxy.db "select id,name,stats_port from proxy_instances;"
curl -s http://127.0.0.1:<stats_port>/metrics | head -n 100
~~~

## Лимиты трафика

Для каждого инстанса доступны режимы:
- `none` (без лимита)
- `day`
- `week`
- `month`

При превышении лимита инстанс останавливается и отмечается как `paused_by_limit`. При начале нового периода инстанс автоматически может быть запущен обратно (если не заблокирован вручную).

## Безопасность

- CSRF защита форм (Flask-WTF)
- Ограничение управления systemd через `sudoers` (`mtg@*.service`)
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
sudo ufw enable
sudo ufw status
~~~

## Обновление проекта

~~~bash
cd /opt/mtproxy-manager
git pull --ff-only
source .venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart mtproxy-manager
~~~

## Структура проекта (кратко)

~~~text
app/
  routes/
  services/
  templates/
  deploy/systemd/mtg@.service
data/mtproxy.db
mtg/instances/
install.sh
mtg_install.sh
init_app.sh
run.py
config.py
~~~

## Используемые библиотеки, ПО и ссылки

### Ядро приложения

- [Flask](https://palletsprojects.com/p/flask/) — BSD-3-Clause
- [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) — BSD-3-Clause
- [SQLAlchemy](https://www.sqlalchemy.org/) — MIT
- [Flask-Login](https://flask-login.readthedocs.io/) — MIT
- [Flask-WTF](https://flask-wtf.readthedocs.io/) — BSD
- [WTForms](https://wtforms.readthedocs.io/) — BSD
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

### Runtime / инфраструктура

- [MTG (9seconds/mtg)](https://github.com/9seconds/mtg) — MIT
- [systemd](https://systemd.io/) — LGPL-2.1-or-later
- [SQLite](https://sqlite.org/) — Public Domain
- [Nginx](https://nginx.org/) (опционально) — BSD-2-Clause
- [Debian](https://www.debian.org/) — свободное ПО (см. лицензии пакетов)

### Инструменты безопасности и аудита (рекомендуемые)

- [pip-audit](https://github.com/pypa/pip-audit) — Apache-2.0
- [Bandit](https://bandit.readthedocs.io/) — Apache-2.0
- [Semgrep](https://semgrep.dev/) — LGPL-2.1 (engine), см. репозиторий
- [Gitleaks](https://github.com/gitleaks/gitleaks) — MIT

## Лицензия проекта

Добавьте в репозиторий файл `LICENSE` (рекомендуется MIT):
- [MIT License template](https://opensource.org/license/mit/)

## Важные замечания
Проект делался под свои узконаправленные потребности. Стабильность и качество сами понимаете ... никто не обещает. Но сервис работат и заявленное выполняет.
- Этот проект управляет сетевым прокси и системными сервисами, используйте только в соответствии с законами вашей юрисдикции.
- Telegram и связанные торговые марки принадлежат их правообладателям.
- Перед публикацией убедитесь, что в репозитории нет реальных секретов (`.env`, токены, приватные ключи).
