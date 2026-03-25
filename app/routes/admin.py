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
    # Защита от 500: сбой вспомогательных сервисов не должен валить панель.
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


@admin_bp.route("/mtg/start", methods=["POST"])
@login_required
@admin_required
def mtg_start():
    success, message = get_mtg_service().start()
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/mtg/stop", methods=["POST"])
@login_required
@admin_required
def mtg_stop():
    success, message = get_mtg_service().stop()
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/mtg/restart", methods=["POST"])
@login_required
@admin_required
def mtg_restart():
    success, message = get_mtg_service().restart()
    flash(message, "success" if success else "danger")
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/mtg/reload", methods=["POST"])
@login_required
@admin_required
def mtg_reload():
    success, message = get_mtg_service().reload_config()
    flash("Конфигурация перезагружена" if success else message, "success" if success else "danger")
    return redirect(url_for("admin.dashboard"))


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
        try:
            Settings.set("server_domain", form.server_domain.data, "string")
            Settings.set("max_keys_per_user", str(form.max_keys_per_user.data), "int")
            Settings.set("auto_backup_enabled", str(form.auto_backup_enabled.data).lower(), "bool")
            Settings.set("auto_backup_interval", form.auto_backup_interval.data, "string")

            flash("Настройки сохранены", "success")

            mtg_service = get_mtg_service()
            if mtg_service.get_status().get("running"):
                mtg_service.reload_config()
                flash("Конфигурация MTG обновлена", "info")

            return redirect(url_for("admin.settings"))
        except Exception as exc:
            flash(f"Ошибка сохранения настроек: {exc}", "danger")

    return render_template("admin/setting.html", form=form)


@admin_bp.route("/users")
@login_required
@admin_required
def users_list():
    """
    ВАЖНО: endpoint admin.users_list нужен для base.html.
    """
    page = request.args.get("page", 1, type=int)
    per_page = 20

    status_filter = request.args.get("status", "all")
    query = User.query

    if status_filter == "pending":
        query = query.filter_by(is_approved=False, is_blocked=False)
    elif status_filter == "approved":
        query = query.filter_by(is_approved=True, is_blocked=False)
    elif status_filter == "blocked":
        query = query.filter_by(is_blocked=True)
    elif status_filter == "admin":
        query = query.filter_by(is_admin=True)

    users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template("admin/users.html", users=users, status_filter=status_filter)


@admin_bp.route("/users/<int:user_id>", methods=["GET", "POST"])
@login_required
@admin_required
def user_manage(user_id):
    user = User.query.get_or_404(user_id)
    form = UserManageForm(obj=user)

    if form.validate_on_submit():
        if user.id == current_user.id and not form.is_admin.data:
            flash("Вы не можете снять права администратора с себя", "danger")
            return redirect(url_for("admin.user_manage", user_id=user_id))

        if user.id == current_user.id and form.is_blocked.data:
            flash("Вы не можете заблокировать себя", "danger")
            return redirect(url_for("admin.user_manage", user_id=user_id))

        user.is_approved = form.is_approved.data
        user.is_admin = form.is_admin.data
        user.is_blocked = form.is_blocked.data
        db.session.commit()

        flash("Данные пользователя обновлены", "success")
        return redirect(url_for("admin.users_list"))

    user_keys = ProxyInstance.query.filter_by(owner_user_id=user_id).all()
    return render_template("admin/user_manage.html", user=user, form=form, user_keys=user_keys)


@admin_bp.route("/users/<int:user_id>/approve", methods=["POST"])
@login_required
@admin_required
def user_approve(user_id):
    user = User.query.get_or_404(user_id)
    user.is_approved = True
    db.session.commit()
    flash(f"Пользователь {user.email} подтверждён", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:user_id>/block", methods=["POST"])
@login_required
@admin_required
def user_block(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Вы не можете заблокировать себя", "danger")
        return redirect(url_for("admin.users_list"))

    user.is_blocked = True
    db.session.commit()
    flash(f"Пользователь {user.email} заблокирован", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:user_id>/unblock", methods=["POST"])
@login_required
@admin_required
def user_unblock(user_id):
    user = User.query.get_or_404(user_id)
    user.is_blocked = False
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()
    flash(f"Пользователь {user.email} разблокирован", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def user_delete(user_id):
    user = User.query.get_or_404(user_id)

    if user.id == current_user.id:
        flash("Вы не можете удалить себя", "danger")
        return redirect(url_for("admin.users_list"))

    ProxyInstance.query.filter_by(owner_user_id=user_id).update({"owner_user_id": None})

    email = user.email
    db.session.delete(user)
    db.session.commit()

    flash(f"Пользователь {email} удалён", "success")
    return redirect(url_for("admin.users_list"))


@admin_bp.route("/api/system-stats")
@login_required
@admin_required
def api_system_stats():
    try:
        system_stats = SystemMonitor.get_full_stats()
    except Exception:
        system_stats = {}

    try:
        system_health = SystemMonitor.check_system_health()
    except Exception:
        system_health = {"status": "unknown", "issues": [], "warnings": []}

    try:
        mtg_status = get_mtg_service().get_status()
    except Exception:
        mtg_status = {"installed": False, "running": False, "instances_total": 0, "instances_running": 0}

    return jsonify({"system": system_stats, "health": system_health, "mtg": mtg_status})


@admin_bp.route("/api/traffic-stats")
@login_required
@admin_required
def api_traffic_stats():
    period = request.args.get("period", "day")
    traffic_monitor = TrafficMonitor()
    try:
        stats = traffic_monitor.get_all_keys_stats(period)
    except Exception:
        stats = []
    try:
        total = traffic_monitor.get_total_stats()
    except Exception:
        total = {}
    return jsonify({"keys": stats, "total": total})