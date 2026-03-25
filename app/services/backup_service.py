"""
Сервис резервного копирования
Бэкап базы данных, конфигурации и файлов приложения
"""

import os
import shutil
import tarfile
import json
from datetime import datetime
from typing import List, Dict, Tuple, Optional
from flask import current_app

from app import db
from app.models import BackupRecord, Settings


class BackupService:
    """Сервис резервного копирования"""
    
    # Файлы и папки для бэкапа
    BACKUP_ITEMS = [
        'data/mtproxy.db',      # База данных
        'mtg/config.json',       # Конфигурация MTG
        'mtg/secrets.txt',       # Секреты MTG
        'mtg/mtg.env',           # Environment MTG
        'scripts/',              # Пользовательские скрипты
    ]
    
    def __init__(self, app=None):
        self.app = app
    
    def init_app(self, app):
        self.app = app
    
    @property
    def backup_dir(self) -> str:
        """Директория для бэкапов"""
        return current_app.config.get('BACKUPS_PATH', 'backups')
    
    @property
    def max_backups(self) -> int:
        """Максимальное количество бэкапов"""
        return current_app.config.get('MAX_BACKUPS', 10)
    
    def create_backup(self, notes: str = None, backup_type: str = 'manual') -> Tuple[bool, str, Optional[str]]:
        """
        Создание резервной копии.
        
        Args:
            notes: Примечание к бэкапу
            backup_type: Тип бэкапа (manual, auto)
            
        Returns:
            Tuple[bool, str, Optional[str]]: (успех, сообщение, путь к файлу)
        """
        try:
            # Создаем директорию если не существует
            os.makedirs(self.backup_dir, exist_ok=True)
            
            # Генерируем имя файла
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"mtproxy_backup_{timestamp}.tar.gz"
            filepath = os.path.join(self.backup_dir, filename)
            
            # Базовая директория приложения
            base_dir = current_app.config.get('BASE_DIR', os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            
            # Создаем архив
            with tarfile.open(filepath, 'w:gz') as tar:
                for item in self.BACKUP_ITEMS:
                    item_path = os.path.join(base_dir, item)
                    if os.path.exists(item_path):
                        # Определяем имя в архиве
                        arcname = item
                        tar.add(item_path, arcname=arcname)
                        current_app.logger.debug(f"Добавлено в бэкап: {item}")
                
                # Добавляем метаданные бэкапа
                metadata = {
                    'created_at': datetime.utcnow().isoformat(),
                    'type': backup_type,
                    'notes': notes,
                    'version': current_app.config.get('VERSION', '1.0.0'),
                    'items': self.BACKUP_ITEMS
                }
                
                # Создаем временный файл с метаданными
                metadata_content = json.dumps(metadata, indent=2, ensure_ascii=False)
                metadata_path = os.path.join(self.backup_dir, 'backup_metadata.json')
                with open(metadata_path, 'w') as f:
                    f.write(metadata_content)
                tar.add(metadata_path, arcname='backup_metadata.json')
                os.remove(metadata_path)
            
            # Получаем размер файла
            file_size = os.path.getsize(filepath)
            
            # Записываем в БД
            record = BackupRecord(
                filename=filename,
                filepath=filepath,
                size=file_size,
                backup_type=backup_type,
                notes=notes
            )
            db.session.add(record)
            db.session.commit()
            
            # Очищаем старые бэкапы
            self._cleanup_old_backups()
            
            current_app.logger.info(f"Бэкап создан: {filename} ({self._format_bytes(file_size)})")
            
            return True, f"Бэкап успешно создан: {filename}", filepath
            
        except Exception as e:
            current_app.logger.error(f"Ошибка создания бэкапа: {e}")
            return False, f"Ошибка создания бэкапа: {str(e)}", None
    
    def restore_backup(self, backup_id: int) -> Tuple[bool, str]:
        """
        Восстановление из резервной копии.
        
        Args:
            backup_id: ID записи бэкапа
            
        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        try:
            record = BackupRecord.query.get(backup_id)
            if not record:
                return False, "Бэкап не найден"
            
            if not os.path.exists(record.filepath):
                return False, "Файл бэкапа не найден на диске"
            
            # Базовая директория
            base_dir = current_app.config.get('BASE_DIR', os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
            
            # Создаем временную директорию для распаковки
            temp_dir = os.path.join(self.backup_dir, 'temp_restore')
            os.makedirs(temp_dir, exist_ok=True)
            
            try:
                # Распаковываем архив
                with tarfile.open(record.filepath, 'r:gz') as tar:
                    tar.extractall(temp_dir)
                
                # Восстанавливаем файлы
                for item in self.BACKUP_ITEMS:
                    src_path = os.path.join(temp_dir, item)
                    dst_path = os.path.join(base_dir, item)
                    
                    if os.path.exists(src_path):
                        # Создаем родительскую директорию
                        os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                        
                        if os.path.isdir(src_path):
                            if os.path.exists(dst_path):
                                shutil.rmtree(dst_path)
                            shutil.copytree(src_path, dst_path)
                        else:
                            shutil.copy2(src_path, dst_path)
                        
                        current_app.logger.debug(f"Восстановлено: {item}")
                
                current_app.logger.info(f"Бэкап восстановлен: {record.filename}")
                return True, "Бэкап успешно восстановлен. Перезапустите приложение."
                
            finally:
                # Очищаем временную директорию
                if os.path.exists(temp_dir):
                    shutil.rmtree(temp_dir)
                    
        except Exception as e:
            current_app.logger.error(f"Ошибка восстановления бэкапа: {e}")
            return False, f"Ошибка восстановления: {str(e)}"
    
    def delete_backup(self, backup_id: int) -> Tuple[bool, str]:
        """
        Удаление резервной копии.
        
        Args:
            backup_id: ID записи бэкапа
            
        Returns:
            Tuple[bool, str]: (успех, сообщение)
        """
        try:
            record = BackupRecord.query.get(backup_id)
            if not record:
                return False, "Бэкап не найден"
            
            # Удаляем файл
            if os.path.exists(record.filepath):
                os.remove(record.filepath)
            
            # Удаляем запись из БД
            db.session.delete(record)
            db.session.commit()
            
            current_app.logger.info(f"Бэкап удален: {record.filename}")
            return True, "Бэкап успешно удален"
            
        except Exception as e:
            current_app.logger.error(f"Ошибка удаления бэкапа: {e}")
            return False, f"Ошибка удаления: {str(e)}"
    
    def get_all_backups(self) -> List[Dict]:
        """
        Получение списка всех бэкапов.
        
        Returns:
            List[Dict]: Список бэкапов
        """
        records = BackupRecord.query.order_by(BackupRecord.created_at.desc()).all()
        
        backups = []
        for record in records:
            exists = os.path.exists(record.filepath)
            backups.append({
                'id': record.id,
                'filename': record.filename,
                'filepath': record.filepath,
                'size': record.size,
                'size_formatted': self._format_bytes(record.size),
                'backup_type': record.backup_type,
                'type_label': 'Автоматический' if record.backup_type == 'auto' else 'Ручной',
                'created_at': record.created_at,
                'notes': record.notes,
                'exists': exists
            })
        
        return backups
    
    def get_backup_info(self, backup_id: int) -> Optional[Dict]:
        """
        Получение информации о бэкапе.
        
        Args:
            backup_id: ID бэкапа
            
        Returns:
            Optional[Dict]: Информация о бэкапе
        """
        record = BackupRecord.query.get(backup_id)
        if not record:
            return None
        
        info = {
            'id': record.id,
            'filename': record.filename,
            'filepath': record.filepath,
            'size': record.size,
            'size_formatted': self._format_bytes(record.size),
            'backup_type': record.backup_type,
            'created_at': record.created_at,
            'notes': record.notes,
            'exists': os.path.exists(record.filepath),
            'contents': []
        }
        
        # Получаем содержимое архива
        if info['exists']:
            try:
                with tarfile.open(record.filepath, 'r:gz') as tar:
                    info['contents'] = tar.getnames()
            except Exception:
                pass
        
        return info
    
    def download_backup(self, backup_id: int) -> Optional[str]:
        """
        Получение пути к файлу бэкапа для скачивания.
        
        Args:
            backup_id: ID бэкапа
            
        Returns:
            Optional[str]: Путь к файлу или None
        """
        record = BackupRecord.query.get(backup_id)
        if record and os.path.exists(record.filepath):
            return record.filepath
        return None
    
    def _cleanup_old_backups(self):
        """Очистка старых бэкапов сверх лимита"""
        records = BackupRecord.query.order_by(BackupRecord.created_at.desc()).all()
        
        if len(records) > self.max_backups:
            # Удаляем самые старые
            for record in records[self.max_backups:]:
                try:
                    if os.path.exists(record.filepath):
                        os.remove(record.filepath)
                    db.session.delete(record)
                    current_app.logger.info(f"Удален старый бэкап: {record.filename}")
                except Exception as e:
                    current_app.logger.error(f"Ошибка удаления старого бэкапа: {e}")
            
            db.session.commit()
    
    def get_backup_settings(self) -> Dict:
        """Получение настроек автобэкапа"""
        return {
            'enabled': Settings.get('auto_backup_enabled', False),
            'interval': Settings.get('auto_backup_interval', 'daily'),
            'max_backups': self.max_backups
        }
    
    def update_backup_settings(self, enabled: bool, interval: str) -> bool:
        """
        Обновление настроек автобэкапа.
        
        Args:
            enabled: Включен ли автобэкап
            interval: Интервал (daily, weekly, monthly)
            
        Returns:
            bool: Успех операции
        """
        try:
            Settings.set('auto_backup_enabled', str(enabled).lower(), 'bool')
            Settings.set('auto_backup_interval', interval, 'string')
            return True
        except Exception as e:
            current_app.logger.error(f"Ошибка сохранения настроек бэкапа: {e}")
            return False
    
    @staticmethod
    def _format_bytes(bytes_count: int) -> str:
        """Форматирование размера файла"""
        if bytes_count is None or bytes_count == 0:
            return '0 Б'
        
        for unit in ['Б', 'КБ', 'МБ', 'ГБ']:
            if bytes_count < 1024:
                return f"{bytes_count:.2f} {unit}"
            bytes_count /= 1024
        
        return f"{bytes_count:.2f} ТБ"


def auto_backup(app):
    """
    Автоматическое создание бэкапа.
    Вызывается планировщиком.
    """
    with app.app_context():
        # Проверяем включен ли автобэкап
        if not Settings.get('auto_backup_enabled', False):
            return
        
        backup_service = BackupService()
        success, message, filepath = backup_service.create_backup(
            notes="Автоматический бэкап",
            backup_type='auto'
        )
        
        if success:
            current_app.logger.info(f"Автобэкап создан: {filepath}")
        else:
            current_app.logger.error(f"Ошибка автобэкапа: {message}")


def get_backup_service() -> BackupService:
    """Получение экземпляра сервиса бэкапов"""
    return BackupService()