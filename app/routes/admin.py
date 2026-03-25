"""
Маршруты панели администратора.
"""

from functools import wraps
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import User, ProxyInstance, Settings, LoginAttempt
from app.forms import SettingsForm, UserManageForm
from app.services.mtg_service import get_mtg_service
from app.services.system_monitor import SystemMonitor
from app.services.traffic_monitor import TrafficMonitor

admin_bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Необходимо войти в систему", "warning")
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            flash("Доступ запрещён. Требуются права администратора.", "danger")
            return redirect(url_for("keys.list_keys"))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route("/dashboard")
@login_required
@admin_required
def dashboard():
    # Защита от 500: любой сбой мониторов не валит панель
    try:
        system_stats = SystemMonitor.get_full_stats() or {}
    except Exception:
        system_stats = {}

    try:
        system_health = SystemMonitor.check_system_health() or {}
    except Exception:
        system_health = {"status": "unknown", "issues": [], "warnings": []}

    try:
        mtg_status = get_mtg_service().get_status() or {}
    except Exception:
        mtg_status = {"installed": False, "running": False, "instances_total": 0, "instances_running": 0}

    try:
        traffic_stats = TrafficMonitor().get_total_stats() or {}
    except Exception:
        traffic_stats = {
            "total_traffic_formatted": "0 Б",
            "current_period_formatted": "0 Б",
            "active_keys": 0,
            "last_activity": None,
        }

    users_stats = {
        "total": User.query.count(),
        "approved": User.query.filter_by(is_approved=True).count(),
        "pending": User.query.filter_by(is_approved=False, is_blocked=False).count(),
        "blocked": User.query.filter_by(is_blocked=True).count(),
        "admins": User.query.filter_by(is_admin=True).count(),
    }

    keys_stats = {
        "total": ProxyInstance.query.count(),
        "active": ProxyInstance.query.filter_by(is_enabled=True, is_blocked=False).count(),
        "blocked": ProxyInstance.query.filter_by(is_blocked=True).count(),
    }

    recent_logins = LoginAttempt.query.order_by(LoginAttempt.timestamp.desc()).limit(10).all()

    return render_template(
        "admin/dashboard.html",
        system_stats=system_stats,
        system_health=system_health,
        mtg_status=mtg_status,
        traffic_stats=traffic_stats,
        users_stats=users_stats,
        keys_stats=keys_stats,
        recent_logins=recent_logins,
    )


@admin_bp.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def settings():
    form = SettingsForm()

    if request.method == "GET":
        form.server_domain.data = Settings.get("server_domain", "localhost")
        form.max_keys_per_user.data = Settings.get("max_keys_per_user", 5)
        form.auto_backup_enabled.data = Settings.get("auto_backup_enabled", False)
        form.auto_backup_interval.data = Settings.get("auto_backup_interval", "daily")

    if form.validate_on_submit():
        Settings.set("server_domain", form.server_domain.data, "string")
        Settings.set("max_keys_per_user", str(form.max_keys_per_user.data), "int")
        Settings.set("auto_backup_enabled", str(form.auto_backup_enabled.data).lower(), "bool")
        Settings.set("auto_backup_interval", form.auto_backup_interval.data, "string")
        flash("Настройки сохранены", "success")
        return redirect(url_for("admin.settings"))

    return render_template("admin/setting.html", form=form)