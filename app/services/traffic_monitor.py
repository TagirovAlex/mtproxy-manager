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
    def _parse_prometheus_metrics(text: str) -> Dict[str, int]:
        out = {"connections": 0, "bytes_in": 0, "bytes_out": 0}

        def parse_labels(raw_name: str):
            # metric{a="b",c="d"} -> ("metric", {"a":"b","c":"d"})
            if "{" not in raw_name:
                return raw_name, {}
            metric = raw_name.split("{", 1)[0]
            labels_str = raw_name.split("{", 1)[1].rsplit("}", 1)[0]
            labels = {}
            for part in labels_str.split(","):
                part = part.strip()
                if "=" not in part:
                    continue
                k, v = part.split("=", 1)
                labels[k.strip()] = v.strip().strip('"')
            return metric, labels

        def direction_from(metric_l: str, labels: dict) -> str:
            """
            Возвращает:
            - "in"  для входящего трафика
            - "out" для исходящего
            - ""    если направление не определено
            """
            label_blob = " ".join([f"{k}={v}" for k, v in labels.items()]).lower()
            blob = f"{metric_l} {label_blob}"

            in_markers = [
                "in",
                "inbound",
                "received",
                "recv",
                "download",
                "client_to_proxy",
                "from_client",
                "to_server",
                "server_in",
                "rx",
            ]
            out_markers = [
                "out",
                "outbound",
                "sent",
                "send",
                "upload",
                "proxy_to_client",
                "to_client",
                "from_server",
                "server_out",
                "tx",
            ]

            if any(x in blob for x in in_markers):
                return "in"
            if any(x in blob for x in out_markers):
                return "out"
            return ""

        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split()
            if len(parts) < 2:
                continue

            raw_name, raw_val = parts[0], parts[1]

            try:
                num = int(float(raw_val))
            except Exception:
                continue

            metric_name, labels = parse_labels(raw_name)
            m = metric_name.lower()

            # Пропускаем гистограммные bucket/quantile
            if m.endswith("_bucket") or "quantile" in raw_name.lower():
                continue

            # connections
            if "connection" in m:
                out["connections"] = max(out["connections"], num)
                continue

            # Явные byte counters
            if ("byte" in m or "octet" in m) and (
                m.endswith("_total") or m.endswith("_sum") or "bytes" in m
            ):
                d = direction_from(m, labels)
                if d == "in":
                    out["bytes_in"] = max(out["bytes_in"], num)
                    continue
                if d == "out":
                    out["bytes_out"] = max(out["bytes_out"], num)
                    continue

            # Метрики размера пакетов (частый формат у mtg)
            # Например: ...packet...size..._sum
            if "packet" in m and "size" in m and (m.endswith("_sum") or m.endswith("_total")):
                d = direction_from(m, labels)
                if d == "in":
                    out["bytes_in"] = max(out["bytes_in"], num)
                    continue
                if d == "out":
                    out["bytes_out"] = max(out["bytes_out"], num)
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
        # История почасово не хранится (пока). Возвращаем пустой список для совместимости UI.
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
        """
        Обновляет кеш-поля в ProxyInstance (total_traffic, connection_count, last_activity)
        из live метрик MTG.
        """
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
        # Нет отдельной таблицы history в этом минимальном варианте.
        return 0


def update_traffic_stats(app):
    with app.app_context():
        TrafficMonitor().update_instance_counters()


def get_traffic_monitor(app=None) -> TrafficMonitor:
    return TrafficMonitor(app=app)