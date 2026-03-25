"""
Безопасный запуск служебных скриптов:
- только для admin
- только из scripts/ директории
- только из allowlist
- без пользовательских аргументов
"""

from __future__ import annotations

import os
import shlex
import subprocess
from datetime import datetime
from functools import wraps

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app.forms import ScriptRunForm

scripts_bp = Blueprint("scripts", __name__)


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


def _scripts_dir() -> str:
    return current_app.config.get("SCRIPTS_PATH", os.path.join(current_app.config["BASE_DIR"], "scripts"))


def _safe_realpath(base_dir: str, rel_name: str) -> str | None:
    # Принимаем только basename, никаких путей пользователя.
    name = os.path.basename(rel_name.strip())
    if not name:
        return None
    candidate = os.path.realpath(os.path.join(base_dir, name))
    base_real = os.path.realpath(base_dir)
    if not (candidate == base_real or candidate.startswith(base_real + os.sep)):
        return None
    return candidate


def _load_allowlist() -> set[str]:
    # Приоритет: config -> env -> авто-детект исполняемых .sh/.py
    configured = current_app.config.get("SCRIPT_ALLOWLIST")
    if configured and isinstance(configured, (list, tuple, set)):
        return {os.path.basename(x) for x in configured}

    env_val = os.environ.get("SCRIPT_ALLOWLIST", "")
    if env_val.strip():
        return {os.path.basename(x.strip()) for x in env_val.split(",") if x.strip()}

    out = set()
    sdir = _scripts_dir()
    if os.path.isdir(sdir):
        for name in os.listdir(sdir):
            if name.endswith(".sh") or name.endswith(".py"):
                out.add(name)
    return out


def _build_command(script_path: str) -> list[str] | None:
    if script_path.endswith(".sh"):
        return ["/bin/bash", script_path]
    if script_path.endswith(".py"):
        py = current_app.config.get("PYTHON_BINARY_PATH") or "python3"
        return [py, script_path]
    return None


def _run_script(script_path: str, timeout_sec: int = 300) -> tuple[bool, str, str, int]:
    cmd = _build_command(script_path)
    if not cmd:
        return False, "", "Unsupported script extension", -1

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=_scripts_dir(),
            env={
                "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            },
        )
        ok = proc.returncode == 0
        return ok, proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        return False, "", f"Timeout > {timeout_sec}s", -1
    except Exception as exc:
        return False, "", str(exc), -1


def _append_audit_line(action: str, script_name: str, result: str) -> None:
    try:
        sdir = _scripts_dir()
        os.makedirs(sdir, exist_ok=True)
        audit_log = os.path.join(sdir, "script_audit.log")
        now = datetime.utcnow().isoformat()
        email = current_user.email if current_user.is_authenticated else "unknown"
        line = f"{now}\t{email}\t{action}\t{script_name}\t{result}\n"
        with open(audit_log, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        # Не валим UI из-за ошибок аудита.
        pass


@scripts_bp.route("/")
@login_required
@admin_required
def index():
    sdir = _scripts_dir()
    allowlist = _load_allowlist()
    items = []

    if os.path.isdir(sdir):
        for name in sorted(os.listdir(sdir)):
            if name not in allowlist:
                continue
            full = _safe_realpath(sdir, name)
            if not full or not os.path.isfile(full):
                continue
            if not (name.endswith(".sh") or name.endswith(".py")):
                continue
            st = os.stat(full)
            items.append(
                {
                    "name": name,
                    "size": st.st_size,
                    "mtime": datetime.utcfromtimestamp(st.st_mtime),
                    "path": full,
                }
            )

    return render_template("admin/scripts.html", scripts=items, allowlist=sorted(allowlist))


@scripts_bp.route("/<script_name>")
@login_required
@admin_required
def view(script_name):
    sdir = _scripts_dir()
    allowlist = _load_allowlist()
    script_name = os.path.basename(script_name)

    if script_name not in allowlist:
        flash("Скрипт не разрешен allowlist", "danger")
        return redirect(url_for("scripts.index"))

    full = _safe_realpath(sdir, script_name)
    if not full or not os.path.isfile(full):
        flash("Скрипт не найден", "danger")
        return redirect(url_for("scripts.index"))

    with open(full, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    form = ScriptRunForm()
    form.script_name.data = script_name
    return render_template("admin/script_view.html", script_name=script_name, content=content, form=form)


@scripts_bp.route("/run", methods=["POST"])
@login_required
@admin_required
def run():
    form = ScriptRunForm()
    if not form.validate_on_submit():
        flash("Некорректная форма", "danger")
        return redirect(url_for("scripts.index"))

    script_name = os.path.basename(form.script_name.data or "")
    sdir = _scripts_dir()
    allowlist = _load_allowlist()

    if script_name not in allowlist:
        flash("Скрипт не разрешен allowlist", "danger")
        _append_audit_line("run", script_name, "DENY_ALLOWLIST")
        return redirect(url_for("scripts.index"))

    full = _safe_realpath(sdir, script_name)
    if not full or not os.path.isfile(full):
        flash("Скрипт не найден", "danger")
        _append_audit_line("run", script_name, "NOT_FOUND")
        return redirect(url_for("scripts.index"))

    ok, stdout, stderr, code = _run_script(full, timeout_sec=300)
    _append_audit_line("run", script_name, f"code={code}")

    return render_template(
        "admin/scripts_result.html",
        script_name=script_name,
        command=shlex.join(_build_command(full) or [full]),
        success=ok,
        return_code=code,
        stdout=stdout,
        stderr=stderr,
    )


@scripts_bp.route("/history")
@login_required
@admin_required
def history():
    sdir = _scripts_dir()
    audit_log = os.path.join(sdir, "script_audit.log")
    lines = []

    if os.path.isfile(audit_log):
        with open(audit_log, "r", encoding="utf-8", errors="replace") as f:
            rows = f.readlines()[-500:]
        for row in reversed(rows):
            parts = row.rstrip("\n").split("\t")
            if len(parts) >= 5:
                lines.append(
                    {
                        "ts": parts[0],
                        "email": parts[1],
                        "action": parts[2],
                        "script_name": parts[3],
                        "result": parts[4],
                    }
                )

    return render_template("admin/script_history.html", history=lines)