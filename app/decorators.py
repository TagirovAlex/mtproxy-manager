from functools import wraps

from flask import flash, redirect, url_for
from flask_login import current_user


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
