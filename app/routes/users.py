"""
Маршруты для работы с пользователями (админ).
"""

from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app import db
from app.models import User, ProxyInstance, LoginAttempt

users_bp = Blueprint("users", __name__)


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash("Необходимо войти в систему", "warning")
            return redirect(url_for("auth.login"))
        if not current_user.is_admin:
            flash("Доступ запрещён", "danger")
            return redirect(url_for("keys.list_keys"))
        return f(*args, **kwargs)

    return decorated_function


@users_bp.route("/")
@login_required
@admin_required
def index():
    return redirect(url_for("admin.users_list"))


@users_bp.route("/<int:user_id>/keys")
@login_required
@admin_required
def user_keys(user_id):
    user = User.query.get_or_404(user_id)
    keys = ProxyInstance.query.filter_by(owner_user_id=user_id).order_by(ProxyInstance.created_at.desc()).all()
    return render_template("admin/users/keys.html", user=user, keys=keys)


@users_bp.route("/<int:user_id>/assign-key", methods=["POST"])
@login_required
@admin_required
def assign_key(user_id):
    user = User.query.get_or_404(user_id)
    key_id = request.form.get("key_id")
    if not key_id:
        flash("Не указан инстанс", "danger")
        return redirect(url_for("admin.user_manage", user_id=user_id))

    instance = ProxyInstance.query.get_or_404(key_id)
    instance.owner_user_id = user_id
    db.session.commit()

    flash(f'Инстанс "{instance.name}" привязан к пользователю {user.email}', "success")
    return redirect(url_for("admin.user_manage", user_id=user_id))


@users_bp.route("/<int:user_id>/unassign-key/<key_id>", methods=["POST"])
@login_required
@admin_required
def unassign_key(user_id, key_id):
    instance = ProxyInstance.query.get_or_404(key_id)

    if instance.owner_user_id != user_id:
        flash("Инстанс не принадлежит этому пользователю", "danger")
        return redirect(url_for("admin.user_manage", user_id=user_id))

    instance.owner_user_id = None
    db.session.commit()

    flash(f'Инстанс "{instance.name}" отвязан от пользователя', "success")
    return redirect(url_for("admin.user_manage", user_id=user_id))


@users_bp.route("/<int:user_id>/login-history")
@login_required
@admin_required
def login_history(user_id):
    user = User.query.get_or_404(user_id)
    page = request.args.get("page", 1, type=int)
    per_page = 50

    attempts = LoginAttempt.query.filter_by(email=user.email).order_by(LoginAttempt.timestamp.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    return render_template("admin/users/login_history.html", user=user, attempts=attempts)


@users_bp.route("/<int:user_id>/reset-password", methods=["POST"])
@login_required
@admin_required
def reset_password(user_id):
    # Безопасный вариант: пароль задается вручную админом и не отображается в flash.
    user = User.query.get_or_404(user_id)
    new_password = (request.form.get("new_password") or "").strip()

    if len(new_password) < 8:
        flash("Новый пароль должен быть не короче 8 символов", "danger")
        return redirect(url_for("admin.user_manage", user_id=user_id))

    user.set_password(new_password)
    user.failed_login_attempts = 0
    user.locked_until = None
    db.session.commit()

    flash(f"Пароль пользователя {user.email} обновлен", "success")
    return redirect(url_for("admin.user_manage", user_id=user_id))


@users_bp.route("/api/search")
@login_required
@admin_required
def api_search():
    query = request.args.get("q", "").strip()
    if len(query) < 2:
        return jsonify([])

    users = User.query.filter(User.email.ilike(f"%{query}%")).limit(10).all()
    return jsonify(
        [
            {
                "id": u.id,
                "email": u.email,
                "status": u.get_status(),
                "is_admin": u.is_admin,
            }
            for u in users
        ]
    )


@users_bp.route("/api/unassigned-keys")
@login_required
@admin_required
def api_unassigned_keys():
    keys = ProxyInstance.query.filter_by(owner_user_id=None).order_by(ProxyInstance.created_at.desc()).all()
    return jsonify([{"id": k.id, "name": k.name, "status": k.status_label} for k in keys])