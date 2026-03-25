"""
Мониторинг трафика MTG Proxy
Сбор статистики и обновление данных в БД
"""

import re
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from flask import current_app

from app import db
from app.models import ProxyKey, TrafficLog, Settings


class TrafficMonitor:
    """Монитор трафика для MTG Proxy"""
    
    def __init__(self, app=None):
        self.app = app
        self._last_stats = {}
    
    def init_app(self, app):
        self.app = app
    
    def get_mtg_stats(self) -> Optional[Dict]:
        """Получение текущей статистики от MTG"""
        from app.services.mtg_service import get_mtg_service
        
        mtg = get_mtg_service()
        return mtg.get_stats()
    
    def update_key_traffic(self, key_id: int, bytes_in: int, bytes_out: int):
        """
        Обновление статистики трафика для ключа.
        
        Args:
            key_id: ID ключа
            bytes_in: Входящий трафик в байтах
            bytes_out: Исходящий трафик в байтах
        """
        key = ProxyKey.query.get(key_id)
        if not key:
            return
        
        total_bytes = bytes_in + bytes_out
        
        # Обновляем счетчики ключа
        key.traffic_used += total_bytes
        key.total_traffic += total_bytes
        key.last_activity = datetime.utcnow()
        key.connection_count += 1
        
        # Создаем запись в логе
        log_entry = TrafficLog(
            key_id=key_id,
            bytes_in=bytes_in,
            bytes_out=bytes_out,
            connections=1
        )
        db.session.add(log_entry)
        db.session.commit()
        
        # Проверяем лимит
        if key.check_traffic_limit():
            current_app.logger.info(
                f"Ключ {key.name} достиг лимита трафика"
            )
    
    def get_key_stats(self, key_id: int, period: str = 'day') -> Dict:
        """
        Получение статистики по ключу за период.
        
        Args:
            key_id: ID ключа
            period: Период (hour, day, week, month)
            
        Returns:
            Dict: Статистика по ключу
        """
        key = ProxyKey.query.get(key_id)
        if not key:
            return {}
        
        # Определяем временной диапазон
        now = datetime.utcnow()
        if period == 'hour':
            start_time = now - timedelta(hours=1)
        elif period == 'day':
            start_time = now - timedelta(days=1)
        elif period == 'week':
            start_time = now - timedelta(weeks=1)
        elif period == 'month':
            start_time = now - timedelta(days=30)
        else:
            start_time = now - timedelta(days=1)
        
        # Получаем логи за период
        logs = TrafficLog.query.filter(
            TrafficLog.key_id == key_id,
            TrafficLog.timestamp >= start_time
        ).all()
        
        # Агрегируем данные
        total_in = sum(log.bytes_in for log in logs)
        total_out = sum(log.bytes_out for log in logs)
        total_connections = sum(log.connections for log in logs)
        
        return {
            'key_id': key_id,
            'key_name': key.name,
            'period': period,
            'start_time': start_time.isoformat(),
            'end_time': now.isoformat(),
            'bytes_in': total_in,
            'bytes_out': total_out,
            'total_bytes': total_in + total_out,
            'connections': total_connections,
            'formatted_in': self._format_bytes(total_in),
            'formatted_out': self._format_bytes(total_out),
            'formatted_total': self._format_bytes(total_in + total_out)
        }
    
    def get_all_keys_stats(self, period: str = 'day') -> List[Dict]:
        """
        Получение статистики по всем ключам.
        
        Args:
            period: Период статистики
            
        Returns:
            List[Dict]: Список статистики по ключам
        """
        keys = ProxyKey.query.all()
        return [self.get_key_stats(key.id, period) for key in keys]
    
    def get_hourly_stats(self, key_id: int, hours: int = 24) -> List[Dict]:
        """
        Получение почасовой статистики.
        
        Args:
            key_id: ID ключа
            hours: Количество часов
            
        Returns:
            List[Dict]: Почасовая статистика
        """
        now = datetime.utcnow()
        start_time = now - timedelta(hours=hours)
        
        logs = TrafficLog.query.filter(
            TrafficLog.key_id == key_id,
            TrafficLog.timestamp >= start_time
        ).order_by(TrafficLog.timestamp).all()
        
        # Группируем по часам
        hourly_data = {}
        for log in logs:
            hour_key = log.timestamp.strftime('%Y-%m-%d %H:00')
            if hour_key not in hourly_data:
                hourly_data[hour_key] = {
                    'hour': hour_key,
                    'bytes_in': 0,
                    'bytes_out': 0,
                    'connections': 0
                }
            hourly_data[hour_key]['bytes_in'] += log.bytes_in
            hourly_data[hour_key]['bytes_out'] += log.bytes_out
            hourly_data[hour_key]['connections'] += log.connections
        
        return list(hourly_data.values())
    
    def get_daily_stats(self, key_id: int, days: int = 30) -> List[Dict]:
        """
        Получение ежедневной статистики.
        
        Args:
            key_id: ID ключа
            days: Количество дней
            
        Returns:
            List[Dict]: Ежедневная статистика
        """
        now = datetime.utcnow()
        start_time = now - timedelta(days=days)
        
        logs = TrafficLog.query.filter(
            TrafficLog.key_id == key_id,
            TrafficLog.timestamp >= start_time
        ).order_by(TrafficLog.timestamp).all()
        
        # Группируем по дням
        daily_data = {}
        for log in logs:
            day_key = log.timestamp.strftime('%Y-%m-%d')
            if day_key not in daily_data:
                daily_data[day_key] = {
                    'date': day_key,
                    'bytes_in': 0,
                    'bytes_out': 0,
                    'connections': 0
                }
            daily_data[day_key]['bytes_in'] += log.bytes_in
            daily_data[day_key]['bytes_out'] += log.bytes_out
            daily_data[day_key]['connections'] += log.connections
        
        return list(daily_data.values())
    
    def get_total_stats(self) -> Dict:
        """
        Получение общей статистики по всем ключам.
        
        Returns:
            Dict: Общая статистика
        """
        keys = ProxyKey.query.all()
        
        total_traffic = sum(key.total_traffic for key in keys)
        total_used = sum(key.traffic_used for key in keys)
        active_keys = sum(1 for key in keys if key.is_active and not key.is_blocked)
        
        # Последняя активность
        last_activity = None
        for key in keys:
            if key.last_activity:
                if last_activity is None or key.last_activity > last_activity:
                    last_activity = key.last_activity
        
        return {
            'total_keys': len(keys),
            'active_keys': active_keys,
            'total_traffic': total_traffic,
            'total_traffic_formatted': self._format_bytes(total_traffic),
            'current_period_traffic': total_used,
            'current_period_formatted': self._format_bytes(total_used),
            'last_activity': last_activity.isoformat() if last_activity else None
        }
    
    def cleanup_old_logs(self, days: int = 90):
        """
        Очистка старых логов трафика.
        
        Args:
            days: Количество дней для хранения
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        deleted = TrafficLog.query.filter(
            TrafficLog.timestamp < cutoff_date
        ).delete()
        
        db.session.commit()
        
        if deleted > 0:
            current_app.logger.info(f"Удалено {deleted} старых записей трафика")
        
        return deleted
    
    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        """Форматирование байтов в читаемый вид"""
        if bytes_count is None:
            return '0 Б'
        
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if bytes_count < 1024:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024
        
        return f"{bytes_count:.2f} ПБ"


def update_traffic_stats(app):
    """
    Обновление статистики трафика.
    Вызывается планировщиком каждую минуту.
    """
    with app.app_context():
        from app.services.mtg_service import get_mtg_service
        
        mtg = get_mtg_service()
        stats = mtg.get_stats()
        
        if stats:
            # Логируем общую статистику
            current_app.logger.debug(
                f"MTG stats: connections={stats.get('connections', 0)}, "
                f"bytes_in={stats.get('bytes_in', 0)}, "
                f"bytes_out={stats.get('bytes_out', 0)}"
            )


def get_traffic_monitor() -> TrafficMonitor:
    """Получение экземпляра монитора трафика"""
    return TrafficMonitor()