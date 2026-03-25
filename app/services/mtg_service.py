import os
import subprocess
from typing import Optional, Dict, Tuple
from datetime import datetime
from flask import current_app

from app.models import ProxyKey, Settings
from app.services.key_generator import KeyGenerator


class MTGService:
    MIN_VERSION = "2.0.0"

    @property
    def mtg_binary(self) -> str:
        return current_app.config.get("MTG_BINARY_PATH", "/usr/local/bin/mtg")

    @property
    def mtg_config_dir(self) -> str:
        return current_app.config.get("MTG_CONFIG_PATH", os.path.join(current_app.config["BASE_DIR"], "mtg"))

    @property
    def mtg_toml_path(self) -> str:
        return os.path.join(self.mtg_config_dir, "mtg.toml")

    @property
    def service_name(self) -> str:
        return current_app.config.get("MTG_SERVICE_NAME", "mtg-proxy")

    def is_installed(self) -> bool:
        return os.path.isfile(self.mtg_binary) and os.access(self.mtg_binary, os.X_OK)

    def get_version(self) -> Optional[str]:
        if not self.is_installed():
            return None
        try:
            result = subprocess.run([self.mtg_binary, "--version"], capture_output=True, text=True, timeout=5)
            out = (result.stdout or result.stderr).strip()
            for part in out.split():
                if part and part[0].isdigit():
                    return part
            return out or None
        except Exception:
            return None

    def _systemctl(self, action: str) -> Tuple[bool, str]:
        try:
            result = subprocess.run(
                ["systemctl", action, self.service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True, "ok"
            return False, (result.stderr or result.stdout or "systemctl error").strip()
        except Exception as e:
            return False, str(e)

    def get_status(self) -> Dict:
        status = {
            "installed": self.is_installed(),
            "version": self.get_version(),
            "running": False,
            "pid": None,
            "active_keys": 0,
            "connections": 0,
            "error": None,
        }

        if status["installed"]:
            ok, msg = self._systemctl("is-active")
            status["running"] = ok and msg == "ok"

        try:
            pid_result = subprocess.run(
                ["systemctl", "show", self.service_name, "--property=MainPID"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            line = pid_result.stdout.strip()
            if "=" in line:
                val = line.split("=", 1)[1]
                if val.isdigit() and int(val) > 0:
                    status["pid"] = int(val)
        except Exception:
            pass

        status["active_keys"] = ProxyKey.query.filter_by(is_active=True, is_blocked=False).count()
        status["connections"] = self.get_connections_count()
        return status

    def start(self) -> Tuple[bool, str]:
        self.generate_config()
        return self._systemctl("start")

    def stop(self) -> Tuple[bool, str]:
        return self._systemctl("stop")

    def restart(self) -> Tuple[bool, str]:
        self.generate_config()
        return self._systemctl("restart")

    def reload_config(self) -> Tuple[bool, str]:
        return self.restart()

    def generate_config(self) -> str:
        active_keys = ProxyKey.query.filter_by(is_active=True, is_blocked=False).all()

        valid = []
        for key in active_keys:
            key.reset_traffic_if_needed()
            if key.check_traffic_limit():
                continue
            ok, _ = KeyGenerator.validate_secret(key.secret)
            if ok:
                valid.append(key)

        mtg_port = int(Settings.get("mtg_port", 443))
        stats_port = int(current_app.config.get("MTG_STATS_PORT", 3129))

        os.makedirs(self.mtg_config_dir, exist_ok=True)

        secret = valid[0].secret if valid else KeyGenerator.generate_secret()[0]
        toml = (
            f'secret = "{secret}"\n'
            f'bind-to = "0.0.0.0:{mtg_port}"\n\n'
            "[stats.prometheus]\n"
            f'bind-to = "127.0.0.1:{stats_port}"\n'
        )

        with open(self.mtg_toml_path, "w", encoding="utf-8") as f:
            f.write(toml)

        current_app.logger.info("MTG config generated at %s (%d keys total in DB)", self.mtg_toml_path, len(valid))
        return self.mtg_toml_path

    def get_stats(self) -> Optional[Dict]:
        stats_port = int(current_app.config.get("MTG_STATS_PORT", 3129))
        try:
            import requests
            r = requests.get(f"http://127.0.0.1:{stats_port}/metrics", timeout=5)
            if r.status_code == 200:
                return self._parse_prometheus_metrics(r.text)
        except Exception:
            return None
        return None

    def _parse_prometheus_metrics(self, text: str) -> Dict:
        out = {"connections": 0, "bytes_in": 0, "bytes_out": 0}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            name, value = parts[0], parts[1]
            try:
                num = int(float(value))
            except Exception:
                continue
            if name == "mtg_connections":
                out["connections"] = num
            elif name.startswith("mtg_bytes_received"):
                out["bytes_in"] = num
            elif name.startswith("mtg_bytes_sent"):
                out["bytes_out"] = num
        return out

    def get_connections_count(self) -> int:
        stats = self.get_stats()
        return stats.get("connections", 0) if stats else 0


def check_traffic_limits(app):
    with app.app_context():
        keys = ProxyKey.query.filter_by(is_active=True, is_blocked=False).all()
        changed = False
        for key in keys:
            key.reset_traffic_if_needed()
            if key.check_traffic_limit():
                changed = True
        if changed:
            MTGService().reload_config()


def get_mtg_service() -> MTGService:
    return MTGService()