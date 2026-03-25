"""
Маршруты приложения MTProxy Manager
"""

from flask import Blueprint

# Импорт всех blueprints
from app.routes.auth import auth_bp
from app.routes.admin import admin_bp
from app.routes.keys import keys_bp
from app.routes.users import users_bp
from app.routes.profile import profile_bp
from app.routes.scripts import scripts_bp
from app.routes.backup import backup_bp

__all__ = [
    'auth_bp',
    'admin_bp', 
    'keys_bp',
    'users_bp',
    'profile_bp',
    'scripts_bp',
    'backup_bp'
]