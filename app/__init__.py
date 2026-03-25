import os
import logging
from logging.handlers import RotatingFileHandler
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_migrate import Migrate
from flask_limiter.util import get_remote_address
from apscheduler.schedulers.background import BackgroundScheduler

from config import config

# Инициализация расширений
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)
scheduler = BackgroundScheduler()


def create_app(config_name=None):
    """Фабрика приложения Flask"""
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')
    
    app = Flask(__name__)
    app.config.from_object(config[config_name])
    
    # Создание необходимых директорий
    for path in [app.config['DATA_PATH'], app.config['LOGS_PATH'], 
                 app.config['BACKUPS_PATH'], app.config['SCRIPTS_PATH']]:
        os.makedirs(path, exist_ok=True)
    
    # Инициализация расширений с приложением
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    
    # Настройка Flask-Login
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Пожалуйста, войдите для доступа к этой странице.'
    login_manager.login_message_category = 'warning'
    login_manager.session_protection = 'strong'
    
    # Настройка логирования
    setup_logging(app)
    
    # Регистрация blueprints
    register_blueprints(app)
    
    # Создание таблиц БД
    with app.app_context():
        db.create_all()
        
        # Инициализация настроек по умолчанию
        from app.models import Settings
        Settings.init_defaults()
    
    # Запуск планировщика задач
    if not scheduler.running:
        setup_scheduler(app)
        scheduler.start()
    
    # Регистрация обработчиков ошибок
    register_error_handlers(app)
    
    # Контекстные процессоры
    register_context_processors(app)
    
    return app


def register_blueprints(app):
    """Регистрация всех blueprints"""
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.keys import keys_bp
    from app.routes.users import users_bp
    from app.routes.profile import profile_bp
    from app.routes.scripts import scripts_bp
    from app.routes.backup import backup_bp
    
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(keys_bp, url_prefix='/keys')
    app.register_blueprint(users_bp, url_prefix='/users')
    app.register_blueprint(profile_bp, url_prefix='/profile')
    app.register_blueprint(scripts_bp, url_prefix='/scripts')
    app.register_blueprint(backup_bp, url_prefix='/backup')


def setup_logging(app):
    """Настройка логирования"""
    if not app.debug:
        log_file = os.path.join(app.config['LOGS_PATH'], 'mtproxy-manager.log')
        file_handler = RotatingFileHandler(
            log_file, maxBytes=10240000, backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)
        app.logger.setLevel(logging.INFO)
        app.logger.info('MTProxy Manager startup')


def setup_scheduler(app):
    """Настройка планировщика задач"""
    from app.services.traffic_monitor import update_traffic_stats
    from app.services.backup_service import auto_backup
    
    # Обновление статистики трафика каждую минуту
    scheduler.add_job(
        func=lambda: update_traffic_stats(app),
        trigger='interval',
        minutes=1,
        id='update_traffic_stats',
        replace_existing=True
    )
    
    # Проверка лимитов трафика каждые 5 минут
    from app.services.mtg_service import check_traffic_limits
    scheduler.add_job(
        func=lambda: check_traffic_limits(app),
        trigger='interval',
        minutes=5,
        id='check_traffic_limits',
        replace_existing=True
    )
    
    # Автоматический бэкап (настраивается)
    scheduler.add_job(
        func=lambda: auto_backup(app),
        trigger='cron',
        hour=3,
        minute=0,
        id='auto_backup',
        replace_existing=True
    )


def register_error_handlers(app):
    """Регистрация обработчиков ошибок"""
    from flask import render_template
    
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('admin/errors/404.html'), 404
    
    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template('admin/errors/403.html'), 403
    
    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('admin/errors/500.html'), 500
    
    @app.errorhandler(429)
    def ratelimit_error(error):
        return render_template('admin/errors/429.html'), 429


def register_context_processors(app):
    """Регистрация контекстных процессоров"""
    from app.services.system_monitor import get_system_stats
    
    @app.context_processor
    def inject_globals():
        return {
            'app_name': 'MTProxy Manager',
            'app_version': '1.0.0'
        }


@login_manager.user_loader
def load_user(user_id):
    """Загрузка пользователя для Flask-Login"""
    from app.models import User
    return User.query.get(int(user_id))