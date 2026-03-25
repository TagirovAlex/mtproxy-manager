"""
Мониторинг трафика в multi-instance режиме.
"""

from datetime import datetime
from typing import Dict, List

from app.models import ProxyInstance


class TrafficMonitor:
    def __init__(self, app=None):
        self.app = app

    def init_app(self, app):
        self.app = app

    def get_key_stats(self, instance_id: str, period: str = "day") -> Dict:
        inst = ProxyInstance.query.get(instance_id)
        if not inst:
            return {}

        return {
            "key_id": inst.id,
            "key_name": inst.name,
            "period": period,
            "bytes_in": 0,
            "bytes_out": 0,
            "total_bytes": inst.total_traffic or 0,
            "connections": inst.connection_count or 0,
            "formatted_in": "0 Б",
            "formatted_out": "0 Б",
            "formatted_total": self._format_bytes(inst.total_traffic or 0),
        }

    def get_all_keys_stats(self, period: str = "day") -> List[Dict]:
        items = ProxyInstance.query.order_by(ProxyInstance.created_at.desc()).all()
        return [self.get_key_stats(i.id, period=period) for i in items]

    def get_hourly_stats(self, instance_id: str, hours: int = 24) -> List[Dict]:
        # Пока без почасовой агрегации из MTG metrics history.
        # Возвращаем пустой список для совместимости шаблонов.
        return []

    def get_daily_stats(self, instance_id: str, days: int = 30) -> List[Dict]:
        return []

    def get_total_stats(self) -> Dict:
        items = ProxyInstance.query.all()
        total_traffic = sum(i.total_traffic or 0 for i in items)
        active = sum(1 for i in items if i.is_enabled and not i.is_blocked)

        last_activity = None
        for i in items:
            if i.last_activity and (last_activity is None or i.last_activity > last_activity):
                last_activity = i.last_activity

        return {
            "total_keys": len(items),
            "active_keys": active,
            "total_traffic": total_traffic,
            "total_traffic_formatted": self._format_bytes(total_traffic),
            "current_period_traffic": total_traffic,
            "current_period_formatted": self._format_bytes(total_traffic),
            "last_activity": last_activity.isoformat() if last_activity else None,
        }

    def cleanup_old_logs(self, days: int = 90):
        return 0

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


def update_traffic_stats(app):
    # Заглушка для scheduler в multi-instance базовой реализации.
    with app.app_context():
        return


def get_traffic_monitor(app=None) -> TrafficMonitor:
    return TrafficMonitor(app=app)