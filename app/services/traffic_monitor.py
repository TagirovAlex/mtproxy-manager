"""
Мониторинг трафика для multi-instance MTG.
Считывает Prometheus-метрики каждого инстанса по его stats_port.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

import requests

from app import db
from app.models import ProxyInstance


class TrafficMonitor:
    def __init__(self, app=None):
        self.app = app

    def init_app(self, app):
        self.app = app

    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        if bytes_count is None:
            return "—"
        value = float(bytes_count)
        for unit in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
            if value < 1024:
                return f"{value:.2f} {unit}"
            value /= 1024
        return f"{value:.2f} ПБ"

    @staticmethod
    def _parse_metric_with_labels(raw_name: str):
        """
        mtg_telegram_traffic{direction="from_client",dc="2"} -> ("mtg_telegram_traffic", {"direction":"from_client","dc":"2"})
        """
        if "{" not in raw_name:
            return raw_name, {}

        metric = raw_name.split("{", 1)[0]
        labels_part = raw_name.split("{", 1)[1].rsplit("}", 1)[0]
        labels = {}

        for part in labels_part.split(","):
            part = part.strip()
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            labels[k.strip()] = v.strip().strip('"')

        return metric, labels

    @classmethod
    def _parse_prometheus_metrics(cls, text: str) -> Dict[str, int]:
        out = {"connections": 0, "bytes_in": 0, "bytes_out": 0}

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            raw_name, raw_val = parts[0], parts[1]
            metric_name, labels = cls._parse_metric_with_labels(raw_name)
            metric_l = metric_name.lower()

            try:
                val = int(float(raw_val))
            except Exception:
                continue

            # 1) Клиентские соединения
            if metric_l == "mtg_client_connections":
                out["connections"] += val
                continue

            # 2) Трафик Telegram<->клиент
            # mtg_telegram_traffic{direction="from_client"| "to_client", ...}
            if metric_l == "mtg_telegram_traffic":
                direction = (labels.get("direction") or "").lower()

                # from_client = клиент -> прокси -> telegram (входящий для нашего прокси)
                if direction == "from_client":
                    out["bytes_in"] += val
                    continue

                # to_client = telegram -> прокси -> клиент (исходящий для нашего прокси)
                if direction == "to_client":
                    out["bytes_out"] += val
                    continue

        return out

    def _fetch_instance_metrics(self, stats_port: int) -> Optional[Dict[str, int]]:
        try:
            r = requests.get(f"http://127.0.0.1:{stats_port}/metrics", timeout=3)
            if r.status_code != 200:
                return None
            return self._parse_prometheus_metrics(r.text)
        except Exception:
            return None

    def get_key_stats(self, instance_id: str, period: str = "day") -> Dict:
        inst = ProxyInstance.query.get(instance_id)
        if not inst:
            return {}

        metrics = self._fetch_instance_metrics(inst.stats_port) or {"connections": 0, "bytes_in": 0, "bytes_out": 0}
        total = metrics["bytes_in"] + metrics["bytes_out"]

        return {
            "key_id": inst.id,
            "key_name": inst.name,
            "period": period,
            "bytes_in": metrics["bytes_in"],
            "bytes_out": metrics["bytes_out"],
            "total_bytes": total,
            "connections": metrics["connections"],
            "formatted_in": self._format_bytes(metrics["bytes_in"]),
            "formatted_out": self._format_bytes(metrics["bytes_out"]),
            "formatted_total": self._format_bytes(total),
        }

    def get_all_keys_stats(self, period: str = "day") -> List[Dict]:
        items = ProxyInstance.query.order_by(ProxyInstance.created_at.desc()).all()
        return [self.get_key_stats(i.id, period=period) for i in items]

    def get_hourly_stats(self, instance_id: str, hours: int = 24) -> List[Dict]:
        return []

    def get_daily_stats(self, instance_id: str, days: int = 30) -> List[Dict]:
        return []

    def get_total_stats(self) -> Dict:
        items = ProxyInstance.query.all()
        total_in = 0
        total_out = 0
        total_connections = 0
        active = 0

        for inst in items:
            if inst.is_enabled and not inst.is_blocked:
                active += 1

            metrics = self._fetch_instance_metrics(inst.stats_port)
            if metrics:
                total_in += metrics["bytes_in"]
                total_out += metrics["bytes_out"]
                total_connections += metrics["connections"]

        total_traffic = total_in + total_out
        return {
            "total_keys": len(items),
            "active_keys": active,
            "total_traffic": total_traffic,
            "total_traffic_formatted": self._format_bytes(total_traffic),
            "current_period_traffic": total_traffic,
            "current_period_formatted": self._format_bytes(total_traffic),
            "connections": total_connections,
            "last_activity": datetime.utcnow().isoformat(),
        }

    def update_instance_counters(self) -> int:
        updated = 0
        items = ProxyInstance.query.filter_by(is_enabled=True, is_blocked=False).all()

        for inst in items:
            metrics = self._fetch_instance_metrics(inst.stats_port)
            if not metrics:
                continue

            total = metrics["bytes_in"] + metrics["bytes_out"]
            inst.total_traffic = total
            inst.connection_count = metrics["connections"]
            inst.last_activity = datetime.utcnow()
            updated += 1

        if updated:
            db.session.commit()
        return updated

    def cleanup_old_logs(self, days: int = 90):
        return 0


def update_traffic_stats(app):
    with app.app_context():
        TrafficMonitor().update_instance_counters()


def get_traffic_monitor(app=None) -> TrafficMonitor:
    return TrafficMonitor(app=app)