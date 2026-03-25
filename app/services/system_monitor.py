"""
Мониторинг системных ресурсов сервера
"""

import os
import psutil
from datetime import datetime
from typing import Dict, List, Optional


class SystemMonitor:
    """Монитор системных ресурсов"""
    
    @staticmethod
    def get_cpu_usage() -> Dict:
        """
        Получение информации о CPU.
        
        Returns:
            Dict: Информация о загрузке CPU
        """
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()
        cpu_count_logical = psutil.cpu_count(logical=True)
        
        # Загрузка по ядрам
        per_cpu = psutil.cpu_percent(interval=0.1, percpu=True)
        
        # Load average (только для Unix)
        try:
            load_avg = os.getloadavg()
        except (OSError, AttributeError):
            load_avg = (0, 0, 0)
        
        return {
            'percent': cpu_percent,
            'count': cpu_count,
            'count_logical': cpu_count_logical,
            'per_cpu': per_cpu,
            'load_avg_1': round(load_avg[0], 2),
            'load_avg_5': round(load_avg[1], 2),
            'load_avg_15': round(load_avg[2], 2)
        }
    
    @staticmethod
    def get_memory_usage() -> Dict:
        """
        Получение информации о памяти.
        
        Returns:
            Dict: Информация о памяти
        """
        memory = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        return {
            'total': memory.total,
            'available': memory.available,
            'used': memory.used,
            'percent': memory.percent,
            'total_formatted': SystemMonitor._format_bytes(memory.total),
            'available_formatted': SystemMonitor._format_bytes(memory.available),
            'used_formatted': SystemMonitor._format_bytes(memory.used),
            'swap_total': swap.total,
            'swap_used': swap.used,
            'swap_percent': swap.percent,
            'swap_total_formatted': SystemMonitor._format_bytes(swap.total),
            'swap_used_formatted': SystemMonitor._format_bytes(swap.used)
        }
    
    @staticmethod
    def get_disk_usage() -> Dict:
        """
        Получение информации о дисках.
        
        Returns:
            Dict: Информация о дисках
        """
        # Основной раздел
        disk = psutil.disk_usage('/')
        
        # IO статистика
        try:
            disk_io = psutil.disk_io_counters()
            io_stats = {
                'read_bytes': disk_io.read_bytes,
                'write_bytes': disk_io.write_bytes,
                'read_formatted': SystemMonitor._format_bytes(disk_io.read_bytes),
                'write_formatted': SystemMonitor._format_bytes(disk_io.write_bytes)
            }
        except Exception:
            io_stats = {
                'read_bytes': 0,
                'write_bytes': 0,
                'read_formatted': '0 Б',
                'write_formatted': '0 Б'
            }
        
        return {
            'total': disk.total,
            'used': disk.used,
            'free': disk.free,
            'percent': disk.percent,
            'total_formatted': SystemMonitor._format_bytes(disk.total),
            'used_formatted': SystemMonitor._format_bytes(disk.used),
            'free_formatted': SystemMonitor._format_bytes(disk.free),
            'io': io_stats
        }
    
    @staticmethod
    def get_network_usage() -> Dict:
        """
        Получение информации о сети.
        
        Returns:
            Dict: Информация о сетевом трафике
        """
        net_io = psutil.net_io_counters()
        
        # Получаем информацию по интерфейсам
        interfaces = {}
        try:
            net_if = psutil.net_io_counters(pernic=True)
            for name, stats in net_if.items():
                if name != 'lo':  # Пропускаем loopback
                    interfaces[name] = {
                        'bytes_sent': stats.bytes_sent,
                        'bytes_recv': stats.bytes_recv,
                        'sent_formatted': SystemMonitor._format_bytes(stats.bytes_sent),
                        'recv_formatted': SystemMonitor._format_bytes(stats.bytes_recv)
                    }
        except Exception:
            pass
        
        return {
            'bytes_sent': net_io.bytes_sent,
            'bytes_recv': net_io.bytes_recv,
            'packets_sent': net_io.packets_sent,
            'packets_recv': net_io.packets_recv,
            'sent_formatted': SystemMonitor._format_bytes(net_io.bytes_sent),
            'recv_formatted': SystemMonitor._format_bytes(net_io.bytes_recv),
            'interfaces': interfaces
        }
    
    @staticmethod
    def get_uptime() -> Dict:
        """
        Получение времени работы системы.
        
        Returns:
            Dict: Информация об аптайме
        """
        boot_time = datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.now() - boot_time
        
        days = uptime.days
        hours, remainder = divmod(uptime.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        return {
            'boot_time': boot_time.isoformat(),
            'uptime_seconds': int(uptime.total_seconds()),
            'uptime_formatted': f"{days}д {hours}ч {minutes}м {seconds}с",
            'days': days,
            'hours': hours,
            'minutes': minutes
        }
    
    @staticmethod
    def get_processes_info() -> Dict:
        """
        Получение информации о процессах.
        
        Returns:
            Dict: Информация о процессах
        """
        processes = list(psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']))
        
        # Топ процессов по CPU
        top_cpu = sorted(
            processes, 
            key=lambda p: p.info.get('cpu_percent', 0) or 0, 
            reverse=True
        )[:5]
        
        # Топ процессов по памяти
        top_memory = sorted(
            processes,
            key=lambda p: p.info.get('memory_percent', 0) or 0,
            reverse=True
        )[:5]
        
        return {
            'total_count': len(processes),
            'top_cpu': [
                {
                    'pid': p.info['pid'],
                    'name': p.info['name'],
                    'cpu_percent': round(p.info.get('cpu_percent', 0) or 0, 1)
                }
                for p in top_cpu
            ],
            'top_memory': [
                {
                    'pid': p.info['pid'],
                    'name': p.info['name'],
                    'memory_percent': round(p.info.get('memory_percent', 0) or 0, 1)
                }
                for p in top_memory
            ]
        }
    
    @staticmethod
    def get_mtg_process_info() -> Optional[Dict]:
        """
        Получение информации о процессе MTG.
        
        Returns:
            Optional[Dict]: Информация о процессе MTG или None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 
                                          'memory_percent', 'create_time',
                                          'num_threads', 'connections']):
            try:
                if 'mtg' in proc.info['name'].lower():
                    create_time = datetime.fromtimestamp(proc.info['create_time'])
                    uptime = datetime.now() - create_time
                    
                    # Количество соединений
                    try:
                        connections = len(proc.connections())
                    except (psutil.AccessDenied, psutil.NoSuchProcess):
                        connections = 0
                    
                    return {
                        'pid': proc.info['pid'],
                        'name': proc.info['name'],
                        'cpu_percent': round(proc.info.get('cpu_percent', 0) or 0, 1),
                        'memory_percent': round(proc.info.get('memory_percent', 0) or 0, 1),
                        'threads': proc.info.get('num_threads', 0),
                        'connections': connections,
                        'uptime': str(uptime).split('.')[0],
                        'create_time': create_time.isoformat()
                    }
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return None
    
    @staticmethod
    def get_full_stats() -> Dict:
        """
        Получение полной статистики системы.
        
        Returns:
            Dict: Полная статистика
        """
        return {
            'timestamp': datetime.utcnow().isoformat(),
            'cpu': SystemMonitor.get_cpu_usage(),
            'memory': SystemMonitor.get_memory_usage(),
            'disk': SystemMonitor.get_disk_usage(),
            'network': SystemMonitor.get_network_usage(),
            'uptime': SystemMonitor.get_uptime(),
            'processes': SystemMonitor.get_processes_info(),
            'mtg_process': SystemMonitor.get_mtg_process_info()
        }
    
    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        """Форматирование байтов в читаемый вид"""
        if bytes_count is None or bytes_count == 0:
            return '0 Б'
        
        for unit in ['Б', 'КБ', 'МБ', 'ГБ', 'ТБ']:
            if bytes_count < 1024:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024
        
        return f"{bytes_count:.2f} ПБ"
    
    @staticmethod
    def check_system_health() -> Dict:
        """
        Проверка здоровья системы.
        
        Returns:
            Dict: Статус здоровья с предупреждениями
        """
        warnings = []
        status = 'ok'
        
        # Проверка CPU
        cpu = SystemMonitor.get_cpu_usage()
        if cpu['percent'] > 90:
            warnings.append(f"Высокая загрузка CPU: {cpu['percent']}%")
            status = 'critical'
        elif cpu['percent'] > 70:
            warnings.append(f"Повышенная загрузка CPU: {cpu['percent']}%")
            if status != 'critical':
                status = 'warning'
        
        # Проверка памяти
        memory = SystemMonitor.get_memory_usage()
        if memory['percent'] > 90:
            warnings.append(f"Критически мало памяти: {memory['percent']}% использовано")
            status = 'critical'
        elif memory['percent'] > 80:
            warnings.append(f"Мало свободной памяти: {memory['percent']}% использовано")
            if status != 'critical':
                status = 'warning'
        
        # Проверка диска
        disk = SystemMonitor.get_disk_usage()
        if disk['percent'] > 95:
            warnings.append(f"Критически мало места на диске: {disk['percent']}%")
            status = 'critical'
        elif disk['percent'] > 85:
            warnings.append(f"Мало места на диске: {disk['percent']}%")
            if status != 'critical':
                status = 'warning'
        
        return {
            'status': status,
            'warnings': warnings,
            'cpu_percent': cpu['percent'],
            'memory_percent': memory['percent'],
            'disk_percent': disk['percent']
        }


def get_system_stats() -> Dict:
    """Быстрое получение основных метрик системы"""
    return SystemMonitor.get_full_stats()


def get_system_monitor() -> SystemMonitor:
    """Получение экземпляра монитора системы"""
    return SystemMonitor()