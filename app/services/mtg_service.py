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
        return current_app.config.get(
            "MTG_CONFIG_PATH",
            os.path.join(current_app.config["BASE_DIR"], "mtg"),
        )

    @property
    def instances_dir(self) -> str:
        return os.path.join(self.mtg_config_dir, "instances")

    @property
    def use_sudo(self) -> bool:
        return bool(current_app.config.get("SYSTEMCTL_USE_SUDO", True))

    def is_installed(self) -> bool:
        return os.path.isfile(self.mtg_binary) and os.access(self.mtg_binary, os.X_OK)

    def get_version(self) -> Optional[str]:
        if not self.is_installed():
            return None
        ok, out = self._run_cmd([self.mtg_binary, "--version"], timeout=5)
        if not ok:
            return None
        return out.strip() or None

    def _run_cmd(self, cmd: List[str], timeout: int = 20) -> Tuple[bool, str]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            if result.returncode == 0:
                return True, (result.stdout or "").strip()
            return False, (result.stderr or result.stdout or "command error").strip()
        except Exception as exc:
            return False, str(exc)

    def _systemctl(self, action: str, unit: Optional[str] = None) -> Tuple[bool, str]:
        cmd = ["systemctl", action]
        if unit:
            cmd.append(unit)
        if self.use_sudo:
            cmd = ["sudo", "-n"] + cmd
        return self._run_cmd(cmd, timeout=30)

    def _instance_unit(self, instance_id: str) -> str:
        return f"mtg@{instance_id}.service"

    def _instance_toml_path(self, instance_id: str) -> str:
        return os.path.join(self.instances_dir, f"{instance_id}.toml")

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
            "enabled = true\n"
            f'bind-to = "127.0.0.1:{instance.stats_port}"\n'
            'http-path = "/metrics"\n'
            'metric-prefix = "mtg"\n'
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
        bind_ip = (bind_ip or "0.0.0.0").strip()
        bind_port = int(bind_port)

        exists = ProxyInstance.query.filter_by(bind_ip=bind_ip, bind_port=bind_port).first()
        if exists:
            return False, "Этот bind_ip:bind_port уже занят", None

        try:
            secret, domain = KeyGenerator.generate_secret(fake_tls_domain)
        except ValueError as exc:
            return False, str(exc), None

        stats_port = self._pick_free_stats_port()

        instance = ProxyInstance(
            name=(name or "").strip(),
            secret=secret,
            fake_tls_domain=domain,
            bind_ip=bind_ip,
            bind_port=bind_port,
            stats_port=stats_port,
            owner_user_id=owner_user_id if owner_user_id else None,
            is_enabled=True,
            is_blocked=False,
            notes=notes,
        )
        db.session.add(instance)
        db.session.commit()

        self.generate_instance_config(instance)

        ok_reload, msg_reload = self._systemctl("daemon-reload")
        if not ok_reload:
            return False, f"Инстанс создан, но daemon-reload не выполнен: {msg_reload}", instance

        self._systemctl("enable", self._instance_unit(instance.id))
        ok_start, msg_start = self._systemctl("start", self._instance_unit(instance.id))
        if not ok_start:
            return False, f"Инстанс создан, но не запущен: {msg_start}", instance

        return True, "Инстанс создан и запущен", instance

    def update_instance(self, instance: ProxyInstance, regenerate_secret: bool = False) -> Tuple[bool, str]:
        if regenerate_secret:
            try:
                secret, domain = KeyGenerator.generate_secret(instance.fake_tls_domain)
            except ValueError as exc:
                return False, str(exc)
            instance.secret = secret
            instance.fake_tls_domain = domain

        db.session.commit()
        self.generate_instance_config(instance)
        return self.restart_instance(instance.id)

    def delete_instance(self, instance: ProxyInstance) -> Tuple[bool, str]:
        unit = self._instance_unit(instance.id)
        self._systemctl("stop", unit)
        self._systemctl("disable", unit)

        toml_path = self._instance_toml_path(instance.id)
        if os.path.exists(toml_path):
            os.remove(toml_path)

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
        ok_active, raw = self._systemctl("is-active", unit)

        pid = None
        cmd = ["systemctl", "show", unit, "--property=MainPID"]
        if self.use_sudo:
            cmd = ["sudo", "-n"] + cmd
        ok_pid, out_pid = self._run_cmd(cmd, timeout=10)
        if ok_pid and "=" in out_pid:
            val = out_pid.split("=", 1)[1].strip()
            if val.isdigit() and int(val) > 0:
                pid = int(val)

        return {"unit": unit, "active": ok_active, "pid": pid, "raw": raw}

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
        instances = ProxyInstance.query.all()
        running_count = 0
        for item in instances:
            if self.instance_status(item.id).get("active"):
                running_count += 1

        return {
            "installed": self.is_installed(),
            "version": self.get_version(),
            "instances_total": len(instances),
            "instances_running": running_count,
            "active_keys": len(instances),
            "connections": 0,
            "running": running_count > 0,
        }

    def get_stats(self) -> Optional[Dict]:
        return None


def check_traffic_limits(app):
    with app.app_context():
        return


def get_mtg_service() -> MTGService:
    return MTGService()