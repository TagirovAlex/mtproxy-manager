from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user

from app import db
from app.models import ProxyInstance, Settings
from app.forms import CreateKeyForm, EditKeyForm
from app.services.mtg_service import get_mtg_service
from app.services.traffic_monitor import TrafficMonitor

keys_bp = Blueprint("keys", __name__)


def _can_access(instance: ProxyInstance) -> bool:
    return current_user.is_admin or (instance.owner_user_id == current_user.id)


@keys_bp.route("/")
@login_required
def list_keys():
    page = request.args.get("page", 1, type=int)
    per_page = 20

    query = ProxyInstance.query
    if not current_user.is_admin:
        query = query.filter_by(owner_user_id=current_user.id)

    status_filter = request.args.get("status", "all")
    if status_filter == "active":
        query = query.filter_by(is_enabled=True, is_blocked=False)
    elif status_filter == "blocked":
        query = query.filter_by(is_blocked=True)
    elif status_filter == "inactive":
        query = query.filter_by(is_enabled=False)

    instances = query.order_by(ProxyInstance.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    server_domain = Settings.get("server_domain", "localhost")

    return render_template(
        "admin/keys/list.html",
        keys=instances,
        status_filter=status_filter,
        server_domain=server_domain,
    )


@keys_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_key():
    form = CreateKeyForm()

    if not current_user.is_admin:
        max_keys = Settings.get("max_keys_per_user", 5)
        user_count = ProxyInstance.query.filter_by(owner_user_id=current_user.id).count()
        if user_count >= max_keys:
            flash(f"Достигнут лимит инстансов ({max_keys})", "warning")
            return redirect(url_for("keys.list_keys"))

    if form.validate_on_submit():
        owner = form.owner_user_id.data if current_user.is_admin else current_user.id
        mtg = get_mtg_service()
        ok, msg, inst = mtg.create_instance(
            name=form.name.data,
            bind_ip=form.bind_ip.data,
            bind_port=form.bind_port.data,
            fake_tls_domain=form.fake_tls_domain.data,
            owner_user_id=owner,
            notes=form.notes.data,
        )
        flash(msg, "success" if ok else "danger")
        if ok and inst:
            return redirect(url_for("keys.key_detail", key_id=inst.id))

    return render_template("admin/keys/create.html", form=form)


@keys_bp.route("/<key_id>")
@login_required
def key_detail(key_id):
    instance = ProxyInstance.query.get_or_404(key_id)
    if not _can_access(instance):
        flash("Доступ запрещен", "danger")
        return redirect(url_for("keys.list_keys"))

    server_domain = Settings.get("server_domain", "localhost")
    links = {
        "tg": instance.get_tg_link(server_domain),
        "https": instance.get_https_link(server_domain),
        "tme": instance.get_https_link(server_domain).replace("https://", ""),
    }

    mtg_service = get_mtg_service()
    service_status = mtg_service.instance_status(instance.id)

    traffic_monitor = TrafficMonitor()
    traffic_stats = traffic_monitor.get_key_stats(instance.id, period="day")
    hourly_stats = traffic_monitor.get_hourly_stats(instance.id, hours=24)

    return render_template(
        "admin/keys/detail.html",
        key=instance,
        links=links,
        service_status=service_status,
        server_domain=server_domain,
        traffic_stats=traffic_stats,
        hourly_stats=hourly_stats,
    )


@keys_bp.route("/<key_id>/edit", methods=["GET", "POST"])
@login_required
def key_edit(key_id):
    instance = ProxyInstance.query.get_or_404(key_id)
    if not _can_access(instance):
        flash("Доступ запрещен", "danger")
        return redirect(url_for("keys.list_keys"))

    form = EditKeyForm(instance_id=instance.id, obj=instance)

    if request.method == "GET":
        form.owner_user_id.data = instance.owner_user_id or 0

    if form.validate_on_submit():
        instance.name = form.name.data.strip()
        instance.bind_ip = form.bind_ip.data.strip()
        instance.bind_port = int(form.bind_port.data)
        instance.fake_tls_domain = form.fake_tls_domain.data.strip()
        instance.owner_user_id = form.owner_user_id.data or None
        instance.is_enabled = form.is_enabled.data
        instance.is_blocked = form.is_blocked.data
        instance.notes = form.notes.data
        db.session.commit()

        ok, msg = get_mtg_service().update_instance(instance, regenerate_secret=False)
        flash("Сохранено" if ok else msg, "success" if ok else "danger")
        return redirect(url_for("keys.key_detail", key_id=instance.id))

    return render_template("admin/keys/edit.html", form=form, key=instance)


@keys_bp.route("/<key_id>/regenerate", methods=["POST"])
@login_required
def key_regenerate(key_id):
    instance = ProxyInstance.query.get_or_404(key_id)
    if not _can_access(instance):
        flash("Доступ запрещен", "danger")
        return redirect(url_for("keys.list_keys"))

    ok, msg = get_mtg_service().update_instance(instance, regenerate_secret=True)
    flash("Секрет перегенерирован" if ok else msg, "success" if ok else "danger")
    return redirect(url_for("keys.key_detail", key_id=instance.id))


@keys_bp.route("/<key_id>/start", methods=["POST"])
@login_required
def key_start(key_id):
    instance = ProxyInstance.query.get_or_404(key_id)
    if not _can_access(instance):
        flash("Доступ запрещен", "danger")
        return redirect(url_for("keys.list_keys"))

    ok, msg = get_mtg_service().start_instance(instance.id)
    flash("Запущен" if ok else msg, "success" if ok else "danger")
    return redirect(url_for("keys.key_detail", key_id=instance.id))


@keys_bp.route("/<key_id>/stop", methods=["POST"])
@login_required
def key_stop(key_id):
    instance = ProxyInstance.query.get_or_404(key_id)
    if not _can_access(instance):
        flash("Доступ запрещен", "danger")
        return redirect(url_for("keys.list_keys"))

    ok, msg = get_mtg_service().stop_instance(instance.id)
    flash("Остановлен" if ok else msg, "success" if ok else "danger")
    return redirect(url_for("keys.key_detail", key_id=instance.id))


@keys_bp.route("/<key_id>/restart", methods=["POST"])
@login_required
def key_restart(key_id):
    instance = ProxyInstance.query.get_or_404(key_id)
    if not _can_access(instance):
        flash("Доступ запрещен", "danger")
        return redirect(url_for("keys.list_keys"))

    ok, msg = get_mtg_service().restart_instance(instance.id)
    flash("Перезапущен" if ok else msg, "success" if ok else "danger")
    return redirect(url_for("keys.key_detail", key_id=instance.id))


@keys_bp.route("/<key_id>/toggle", methods=["POST"])
@login_required
def key_toggle(key_id):
    instance = ProxyInstance.query.get_or_404(key_id)
    if not _can_access(instance):
        flash("Доступ запрещен", "danger")
        return redirect(url_for("keys.list_keys"))

    instance.is_enabled = not instance.is_enabled
    db.session.commit()

    if instance.is_enabled:
        get_mtg_service().start_instance(instance.id)
    else:
        get_mtg_service().stop_instance(instance.id)

    flash("Состояние обновлено", "success")
    return redirect(url_for("keys.key_detail", key_id=instance.id))


@keys_bp.route("/<key_id>/block", methods=["POST"])
@login_required
def key_block(key_id):
    if not current_user.is_admin:
        flash("Только для администратора", "danger")
        return redirect(url_for("keys.list_keys"))

    instance = ProxyInstance.query.get_or_404(key_id)
    instance.is_blocked = True
    db.session.commit()
    get_mtg_service().stop_instance(instance.id)

    flash("Инстанс заблокирован", "success")
    return redirect(url_for("keys.key_detail", key_id=instance.id))


@keys_bp.route("/<key_id>/unblock", methods=["POST"])
@login_required
def key_unblock(key_id):
    if not current_user.is_admin:
        flash("Только для администратора", "danger")
        return redirect(url_for("keys.list_keys"))

    instance = ProxyInstance.query.get_or_404(key_id)
    instance.is_blocked = False
    db.session.commit()

    flash("Инстанс разблокирован", "success")
    return redirect(url_for("keys.key_detail", key_id=instance.id))


@keys_bp.route("/<key_id>/delete", methods=["POST"])
@login_required
def key_delete(key_id):
    instance = ProxyInstance.query.get_or_404(key_id)
    if not _can_access(instance):
        flash("Доступ запрещен", "danger")
        return redirect(url_for("keys.list_keys"))

    ok, msg = get_mtg_service().delete_instance(instance)
    flash(msg, "success" if ok else "danger")
    return redirect(url_for("keys.list_keys"))