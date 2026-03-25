import os
import subprocess
from typing import Optional, Dict, Tuple, List
from flask import current_app

from app import db
from app.models import ProxyInstance, Settings
from app.services.key_generator import KeyGenerator


class MTGService:
    @property
    def mtg_binary(self) -> str:
        return current_app.config.get("MTG_BINARY_PATH", "/usr/local/bin/mtg")

    @property
    def mtg_config_dir(self) -> str:
        return current_app.config.get("MTG_CONFIG_PATH", os.path.join(current_app.config["BASE_DIR"], "mtg"))

    @property
    def instances_dir(self) -> str:
        return os.path.join(self.mtg_config_dir, "instances")

    @property
    def use_sudo(self) -> bool:
        return bool(current_app.config.get("SYSTEMCTL_USE_SUDO", True))

    def is_installed(self) -> bool:
        return os.path.isfile(self.mtg_binary) and os.access(self.mtg_binary, os.X_OK)

    def _systemctl(self, action: str, unit: str) -> Tuple[bool, str]:
        cmd = ["systemctl", action, unit]
        if self.use_sudo:
            cmd = ["sudo", "-n"] + cmd
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return True, "ok"
            return False, (result.stderr or result.stdout or "systemctl error").strip()
        except Exception as exc:
            return False, str(exc)

    def _run_cmd(self, cmd: List[str], timeout=10) -> Tuple[bool, str]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                return True, (result.stdout or "").strip()
            return False, (result.stderr or result.stdout or "command error").strip()
        except Exception as exc:
            return False, str(exc)

    def _instance_toml_path(self, instance_id: str) -> str:
        return os.path.join(self.instances_dir, f"{instance_id}.toml")

    def _instance_unit(self, instance_id: str) -> str:
        return f"mtg@{instance_id}.service"

    def _pick_free_stats_port(self) -> int:
        start = int(Settings.get("instance_stats_port_start", 31000))
        used = {x.stats_port for x in ProxyInstance.query.all()}
        p = start
        while p in used:
            p += 1
        return p

    def generate_instance_config(self, instance: ProxyInstance) -> str:
        os.makedirs(self.instances_dir, exist_ok=True)
        path = self._instance_toml_path(instance.id)
        content = (
            f'secret = "{instance.secret}"\n'
            f'bind-to = "{instance.bind_ip}:{instance.bind_port}"\n\n'
            "[stats.prometheus]\n"
            f'bind-to = "127.0.0.1:{instance.stats_port}"\n'
        )
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return path

    def create_instance(
        self,
        name: str,
        bind_ip: str,
        bind_port: int,
        fake_tls_domain: str,
        owner_user_id: Optional[int] = None,
        notes: Optional[str] = None,
    ) -> Tuple[bool, str, Optional[ProxyInstance]]:
        if ProxyInstance.query.filter_by(bind_ip=bind_ip, bind_port=bind_port).first():
            return False, "Порт уже занят", None

        secret, domain = KeyGenerator.generate_secret(fake_tls_domain)
        stats_port = self._pick_free_stats_port()

        instance = ProxyInstance(
            name=name.strip(),
            secret=secret,
            fake_tls_domain=domain,
            bind_ip=bind_ip.strip(),
            bind_port=int(bind_port),
            stats_port=stats_port,
            owner_user_id=owner_user_id if owner_user_id else None,
            is_enabled=True,
            is_blocked=False,
            notes=notes,
        )
        db.session.add(instance)
        db.session.commit()

        self.generate_instance_config(instance)
        self._systemctl("daemon-reload", "dummy.target")  # harmless placeholder if sudo wrapper expects unit
        self._systemctl("enable", self._instance_unit(instance.id))
        ok, msg = self._systemctl("start", self._instance_unit(instance.id))
        if not ok:
            return False, f"Инстанс создан, но не запущен: {msg}", instance
        return True, "Инстанс создан и запущен", instance

    def update_instance(self, instance: ProxyInstance, regenerate_secret=False) -> Tuple[bool, str]:
        if regenerate_secret:
            secret, domain = KeyGenerator.generate_secret(instance.fake_tls_domain)
            instance.secret = secret
            instance.fake_tls_domain = domain

        db.session.commit()
        self.generate_instance_config(instance)
        return self.restart_instance(instance.id)

    def delete_instance(self, instance: ProxyInstance) -> Tuple[bool, str]:
        unit = self._instance_unit(instance.id)
        self._systemctl("stop", unit)
        self._systemctl("disable", unit)

        path = self._instance_toml_path(instance.id)
        if os.path.exists(path):
            os.remove(path)

        db.session.delete(instance)
        db.session.commit()
        return True, "Инстанс удален"

    def start_instance(self, instance_id: str) -> Tuple[bool, str]:
        instance = ProxyInstance.query.get(instance_id)
        if not instance:
            return False, "Инстанс не найден"
        self.generate_instance_config(instance)
        return self._systemctl("start", self._instance_unit(instance_id))

    def stop_instance(self, instance_id: str) -> Tuple[bool, str]:
        return self._systemctl("stop", self._instance_unit(instance_id))

    def restart_instance(self, instance_id: str) -> Tuple[bool, str]:
        instance = ProxyInstance.query.get(instance_id)
        if not instance:
            return False, "Инстанс не найден"
        self.generate_instance_config(instance)
        return self._systemctl("restart", self._instance_unit(instance_id))

    def instance_status(self, instance_id: str) -> Dict:
        unit = self._instance_unit(instance_id)
        ok, msg = self._systemctl("is-active", unit)
        status = "active" if ok else "inactive"

        pid = None
        cmd = ["systemctl", "show", unit, "--property=MainPID"]
        if self.use_sudo:
            cmd = ["sudo", "-n"] + cmd
        ok2, out = self._run_cmd(cmd)
        if ok2 and "=" in out:
            val = out.split("=", 1)[1].strip()
            if val.isdigit() and int(val) > 0:
                pid = int(val)

        return {"unit": unit, "active": status == "active", "pid": pid, "raw": msg}

    # Legacy methods for existing admin dashboard buttons.
    def start(self) -> Tuple[bool, str]:
        failed = []
        for inst in ProxyInstance.query.filter_by(is_enabled=True, is_blocked=False).all():
            ok, msg = self.start_instance(inst.id)
            if not ok:
                failed.append(f"{inst.id}: {msg}")
        if failed:
            return False, "; ".join(failed)
        return True, "Все инстансы запущены"

    def stop(self) -> Tuple[bool, str]:
        failed = []
        for inst in ProxyInstance.query.all():
            ok, msg = self.stop_instance(inst.id)
            if not ok:
                failed.append(f"{inst.id}: {msg}")
        if failed:
            return False, "; ".join(failed)
        return True, "Все инстансы остановлены"

    def restart(self) -> Tuple[bool, str]:
        failed = []
        for inst in ProxyInstance.query.filter_by(is_enabled=True, is_blocked=False).all():
            ok, msg = self.restart_instance(inst.id)
            if not ok:
                failed.append(f"{inst.id}: {msg}")
        if failed:
            return False, "; ".join(failed)
        return True, "Все инстансы перезапущены"

    def reload_config(self) -> Tuple[bool, str]:
        return self.restart()

    def get_status(self) -> Dict:
        items = ProxyInstance.query.all()
        running = 0
        for i in items:
            s = self.instance_status(i.id)
            if s["active"]:
                running += 1
        return {
            "installed": self.is_installed(),
            "instances_total": len(items),
            "instances_running": running,
            "active_keys": len(items),
            "connections": 0,
        }


def check_traffic_limits(app):
    # В multi-instance это место можно расширить: лимиты на уровне ProxyInstance.
    with app.app_context():
        return


def get_mtg_service() -> MTGService:
    return MTGService()