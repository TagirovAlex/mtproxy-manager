"""
Сервис управления MTG Proxy v2+
Поддержка только FakeTLS режима
"""

import os
import json
import subprocess
from typing import Optional, Dict, Tuple
from datetime import datetime
from flask import current_app

from app import db
from app.models import ProxyKey, Settings
from app.services.key_generator import KeyGenerator


class MTGService:
    """Сервис для управления MTG Proxy v2"""
    
    # Минимальная поддерживаемая версия MTG
    MIN_VERSION = "2.0.0"
    
    def __init__(self, app=None):
        self.app = app
        
    def init_app(self, app):
        self.app = app
    
    @property
    def mtg_binary(self) -> str:
        """Путь к бинарному файлу MTG"""
        return current_app.config.get('MTG_BINARY_PATH', '/usr/local/bin/mtg')
    
    @property
    def mtg_config_dir(self) -> str:
        """Директория конфигурации MTG"""
        return current_app.config.get('MTG_CONFIG_PATH', 'mtg')
    
    @property
    def service_name(self) -> str:
        """Имя systemd сервиса"""
        return current_app.config.get('MTG_SERVICE_NAME', 'mtg-proxy')
    
    def is_installed(self) -> bool:
        """Проверка установки MTG"""
        return os.path.isfile(self.mtg_binary) and os.access(self.mtg_binary, os.X_OK)
    
    def get_version(self) -> Optional[str]:
        """Получение версии MTG"""
        if not self.is_installed():
            return None
        
        try:
            result = subprocess.run(
                [self.mtg_binary, '--version'],
                capture_output=True,
                text=True,
                timeout=5
            )
            version_output = result.stdout.strip() or result.stderr.strip()
            # Парсинг версии из вывода
            if version_output:
                # MTG обычно выводит "mtg version X.Y.Z"
                parts = version_output.split()
                for part in parts:
                    if part[0].isdigit():
                        return part
            return version_output
        except Exception as e:
            current_app.logger.error(f"Ошибка получения версии MTG: {e}")
            return None
    
    def check_version_compatibility(self) -> Tuple[bool, str]:
        """Проверка совместимости версии MTG"""
        version = self.get_version()
        if not version:
            return False, "Не удалось определить версию MTG"
        
        try:
            # Простое сравнение версий
            current_parts = [int(x) for x in version.split('.')[:3]]
            min_parts = [int(x) for x in self.MIN_VERSION.split('.')]
            
            if current_parts >= min_parts:
                return True, f"MTG v{version} совместима"
            else:
                return False, f"MTG v{version} устарела. Требуется v{self.MIN_VERSION}+"
        except Exception:
            return False, f"Не удалось проверить версию: {version}"
    
    def get_status(self) -> Dict:
        """Получение полного статуса сервиса MTG"""
        status = {
            'installed': self.is_installed(),
            'version': self.get_version(),
            'version_compatible': False,
            'running': False,
            'pid': None,
            'uptime': None,
            'active_keys': 0,
            'connections': 0,
            'error': None
        }
        
        if status['installed']:
            compat, msg = self.check_version_compatibility()
            status['version_compatible'] = compat
            if not compat:
                status['error'] = msg
        
        try:
            # Проверка через systemctl
            result = subprocess.run(
                ['systemctl', 'is-active', self.service_name],
                capture_output=True,
                text=True,
                timeout=5
            )
            status['running'] = result.stdout.strip() == 'active'
            
            if status['running']:
                # Получение PID
                pid_result = subprocess.run(
                    ['systemctl', 'show', self.service_name, '--property=MainPID'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                pid_line = pid_result.stdout.strip()
                if '=' in pid_line:
                    pid_value = pid_line.split('=')[1]
                    if pid_value.isdigit() and int(pid_value) > 0:
                        status['pid'] = int(pid_value)
                
                # Получение времени работы
                uptime_result = subprocess.run(
                    ['systemctl', 'show', self.service_name, 
                     '--property=ActiveEnterTimestamp'],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                uptime_line = uptime_result.stdout.strip()
                if '=' in uptime_line:
                    timestamp_str = uptime_line.split('=', 1)[1].strip()
                    if timestamp_str:
                        status['uptime'] = timestamp_str
                
                # Количество подключений
                status['connections'] = self.get_connections_count()
            
            # Количество активных ключей
            status['active_keys'] = ProxyKey.query.filter_by(
                is_active=True, 
                is_blocked=False
            ).count()
                        
        except subprocess.TimeoutExpired:
            status['error'] = "Таймаут при проверке статуса"
        except Exception as e:
            status['error'] = str(e)
            current_app.logger.error(f"Ошибка получения статуса MTG: {e}")
        
        return status
    
    def start(self) -> Tuple[bool, str]:
        """Запуск сервиса MTG"""
        try:
            # Проверка совместимости
            compat, msg = self.check_version_compatibility()
            if not compat:
                return False, msg
            
            # Генерация конфигурации перед запуском
            self.generate_config()
            
            result = subprocess.run(
                ['sudo', 'systemctl', 'start', self.service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                current_app.logger.info("MTG Proxy запущен")
                return True, "Сервис успешно запущен"
            else:
                error = result.stderr or "Неизвестная ошибка"
                current_app.logger.error(f"Ошибка запуска MTG: {error}")
                return False, f"Ошибка запуска: {error}"
                
        except subprocess.TimeoutExpired:
            return False, "Таймаут при запуске сервиса"
        except Exception as e:
            current_app.logger.error(f"Ошибка запуска MTG: {e}")
            return False, str(e)
    
    def stop(self) -> Tuple[bool, str]:
        """Остановка сервиса MTG"""
        try:
            result = subprocess.run(
                ['sudo', 'systemctl', 'stop', self.service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                current_app.logger.info("MTG Proxy остановлен")
                return True, "Сервис успешно остановлен"
            else:
                error = result.stderr or "Неизвестная ошибка"
                return False, f"Ошибка остановки: {error}"
                
        except subprocess.TimeoutExpired:
            return False, "Таймаут при остановке сервиса"
        except Exception as e:
            current_app.logger.error(f"Ошибка остановки MTG: {e}")
            return False, str(e)
    
    def restart(self) -> Tuple[bool, str]:
        """Перезапуск сервиса MTG"""
        try:
            # Генерация конфигурации перед перезапуском
            self.generate_config()
            
            result = subprocess.run(
                ['sudo', 'systemctl', 'restart', self.service_name],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                current_app.logger.info("MTG Proxy перезапущен")
                return True, "Сервис успешно перезапущен"
            else:
                error = result.stderr or "Неизвестная ошибка"
                return False, f"Ошибка перезапуска: {error}"
                
        except subprocess.TimeoutExpired:
            return False, "Таймаут при перезапуске сервиса"
        except Exception as e:
            current_app.logger.error(f"Ошибка перезапуска MTG: {e}")
            return False, str(e)
    
    def reload_config(self) -> Tuple[bool, str]:
        """Перезагрузка конфигурации MTG"""
        self.generate_config()
        return self.restart()
    
    def generate_config(self) -> str:
        """
        Генерация конфигурации для MTG v2.
        
        MTG v2 запускается с параметрами:
        mtg run <secret1> <secret2> ... --bind 0.0.0.0:443 --stats-bind 127.0.0.1:3129
        
        Создаем systemd unit файл и environment файл.
        """
        # Получаем активные ключи
        active_keys = ProxyKey.query.filter_by(
            is_active=True, 
            is_blocked=False
        ).all()
        
        # Фильтруем ключи с превышенным лимитом
        valid_keys = []
        for key in active_keys:
            key.reset_traffic_if_needed()
            if not key.check_traffic_limit():
                # Валидируем секрет
                is_valid, _ = KeyGenerator.validate_secret(key.secret)
                if is_valid:
                    valid_keys.append(key)
                else:
                    current_app.logger.warning(
                        f"Ключ {key.name} имеет невалидный секрет, пропускаем"
                    )
        
        # Получаем настройки
        mtg_port = Settings.get('mtg_port', 443)
        stats_port = current_app.config.get('MTG_STATS_PORT', 3129)
        
        # Формируем список секретов
        secrets_list = [key.secret for key in valid_keys]
        
        # Создаем директорию конфигурации
        os.makedirs(self.mtg_config_dir, exist_ok=True)
        
        # Записываем JSON конфиг (для справки и отладки)
        config_data = {
            'version': '2',
            'bind': f'0.0.0.0:{mtg_port}',
            'stats_bind': f'127.0.0.1:{stats_port}',
            'secrets_count': len(secrets_list),
            'keys': [
                {
                    'id': key.id,
                    'name': key.name,
                    'domain': KeyGenerator.decode_domain_from_secret(key.secret),
                    'active': True
                }
                for key in valid_keys
            ],
            'generated_at': datetime.utcnow().isoformat()
        }
        
        config_json_path = os.path.join(self.mtg_config_dir, 'config.json')
        with open(config_json_path, 'w') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        
        # Создаем файл с секретами (для systemd ExecStart)
        secrets_file_path = os.path.join(self.mtg_config_dir, 'secrets.txt')
        with open(secrets_file_path, 'w') as f:
            for secret in secrets_list:
                f.write(f"{secret}\n")
        
        # Создаем environment файл
        env_file_path = os.path.join(self.mtg_config_dir, 'mtg.env')
        env_vars = {
            'MTG_PORT': str(mtg_port),
            'MTG_STATS_PORT': str(stats_port),
            'MTG_SECRETS_COUNT': str(len(secrets_list))
        }
        
        with open(env_file_path, 'w') as f:
            for key, value in env_vars.items():
                f.write(f'{key}={value}\n')
        
        current_app.logger.info(
            f"Конфигурация MTG обновлена: {len(valid_keys)} активных ключей"
        )
        
        return config_json_path
    
    def get_stats(self) -> Optional[Dict]:
        """Получение статистики от MTG через stats endpoint"""
        stats_port = current_app.config.get('MTG_STATS_PORT', 3129)
        
        try:
            import requests
            response = requests.get(
                f'http://127.0.0.1:{stats_port}/metrics',
                timeout=5
            )
            if response.status_code == 200:
                # MTG возвращает метрики в формате Prometheus
                return self._parse_prometheus_metrics(response.text)
        except Exception as e:
            current_app.logger.debug(f"Не удалось получить статистику MTG: {e}")
        
        return None
    
    def _parse_prometheus_metrics(self, metrics_text: str) -> Dict:
        """Парсинг метрик Prometheus формата"""
        result = {
            'connections': 0,
            'bytes_in': 0,
            'bytes_out': 0
        }
        
        for line in metrics_text.split('\n'):
            line = line.strip()
            if line.startswith('#') or not line:
                continue
            
            try:
                if 'mtg_connections' in line and '{' not in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        result['connections'] = int(float(parts[1]))
                elif 'mtg_bytes_received' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        result['bytes_in'] = int(float(parts[1]))
                elif 'mtg_bytes_sent' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        result['bytes_out'] = int(float(parts[1]))
            except (ValueError, IndexError):
                continue
        
        return result
    
    def get_connections_count(self) -> int:
        """Получение количества активных подключений"""
        stats = self.get_stats()
        if stats:
            return stats.get('connections', 0)
        return 0
    
    def get_traffic_stats(self) -> Dict:
        """Получение статистики трафика"""
        stats = self.get_stats()
        if stats:
            return {
                'bytes_in': stats.get('bytes_in', 0),
                'bytes_out': stats.get('bytes_out', 0),
                'total': stats.get('bytes_in', 0) + stats.get('bytes_out', 0)
            }
        return {'bytes_in': 0, 'bytes_out': 0, 'total': 0}


def check_traffic_limits(app):
    """
    Проверка лимитов трафика и блокировка ключей.
    Вызывается планировщиком.
    """
    with app.app_context():
        keys = ProxyKey.query.filter_by(is_active=True, is_blocked=False).all()
        
        config_changed = False
        for key in keys:
            key.reset_traffic_if_needed()
            if key.check_traffic_limit():
                current_app.logger.info(
                    f"Ключ {key.name} (ID: {key.id}) превысил лимит трафика"
                )
                config_changed = True
        
        # Перегенерация конфига если были изменения
        if config_changed:
            mtg = MTGService()
            mtg.reload_config()


def get_mtg_service() -> MTGService:
    """Получение экземпляра сервиса MTG"""
    return MTGService()