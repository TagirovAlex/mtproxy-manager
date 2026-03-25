import os
import shutil
import tarfile
import json
from datetime import datetime, timedelta
from typing import Tuple, Optional
from flask import current_app

from app import db
from app.models import BackupRecord, Settings


class BackupService:
    BACKUP_ITEMS = [
        "data/mtproxy.db",
        "mtg/mtg.toml",
        "scripts/",
    ]

    @property
    def backup_dir(self) -> str:
        return current_app.config.get("BACKUPS_PATH", "backups")

    def _base_dir(self) -> str:
        return current_app.config.get(
            "BASE_DIR",
            os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        )

    def create_backup(self, notes: str = None, backup_type: str = "manual") -> Tuple[bool, str, Optional[str]]:
        try:
            os.makedirs(self.backup_dir, exist_ok=True)
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            filename = f"mtproxy_backup_{timestamp}.tar.gz"
            filepath = os.path.join(self.backup_dir, filename)
            base_dir = self._base_dir()

            with tarfile.open(filepath, "w:gz") as tar:
                for item in self.BACKUP_ITEMS:
                    full = os.path.join(base_dir, item)
                    if os.path.exists(full):
                        tar.add(full, arcname=item)

                meta = {
                    "created_at": datetime.utcnow().isoformat(),
                    "type": backup_type,
                    "notes": notes,
                    "items": self.BACKUP_ITEMS,
                }
                meta_path = os.path.join(self.backup_dir, "backup_metadata.json")
                with open(meta_path, "w", encoding="utf-8") as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)
                tar.add(meta_path, arcname="backup_metadata.json")
                os.remove(meta_path)

            size = os.path.getsize(filepath)
            rec = BackupRecord(
                filename=filename,
                filepath=filepath,
                size=size,
                backup_type=backup_type,
                notes=notes
            )
            db.session.add(rec)
            db.session.commit()
            return True, f"Backup created: {filename}", filepath
        except Exception as e:
            return False, f"Backup error: {e}", None

    def _safe_extract(self, tar: tarfile.TarFile, path: str) -> None:
        base = os.path.realpath(path)
        for member in tar.getmembers():
            target = os.path.realpath(os.path.join(path, member.name))
            if not target.startswith(base + os.sep) and target != base:
                raise RuntimeError(f"Unsafe path in archive: {member.name}")
        tar.extractall(path)

    def restore_backup(self, backup_id: int) -> Tuple[bool, str]:
        rec = BackupRecord.query.get(backup_id)
        if not rec:
            return False, "Backup not found"
        if not os.path.exists(rec.filepath):
            return False, "Backup file missing"

        base_dir = self._base_dir()
        tmp = os.path.join(self.backup_dir, "temp_restore")
        os.makedirs(tmp, exist_ok=True)

        try:
            with tarfile.open(rec.filepath, "r:gz") as tar:
                self._safe_extract(tar, tmp)

            for item in self.BACKUP_ITEMS:
                src = os.path.join(tmp, item)
                dst = os.path.join(base_dir, item)
                if not os.path.exists(src):
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.isdir(src):
                    if os.path.exists(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)

            return True, "Backup restored successfully"
        except Exception as e:
            return False, f"Restore error: {e}"
        finally:
            if os.path.exists(tmp):
                shutil.rmtree(tmp)

    def get_all_backups(self):
        return BackupRecord.query.order_by(BackupRecord.created_at.desc()).all()

    def get_backup_settings(self):
        return {
            "auto_backup_enabled": Settings.get("auto_backup_enabled", False),
            "auto_backup_interval": Settings.get("auto_backup_interval", "daily"),
        }

    def update_backup_settings(self, enabled: bool, interval: str) -> bool:
        try:
            Settings.set("auto_backup_enabled", str(enabled).lower(), "bool")
            Settings.set("auto_backup_interval", interval, "string")
            return True
        except Exception:
            return False

    def download_backup(self, backup_id: int) -> Optional[str]:
        rec = BackupRecord.query.get(backup_id)
        if not rec:
            return None
        return rec.filepath if os.path.exists(rec.filepath) else None

    def delete_backup(self, backup_id: int) -> Tuple[bool, str]:
        rec = BackupRecord.query.get(backup_id)
        if not rec:
            return False, "Backup not found"
        try:
            if os.path.exists(rec.filepath):
                os.remove(rec.filepath)
            db.session.delete(rec)
            db.session.commit()
            return True, "Backup deleted"
        except Exception as e:
            db.session.rollback()
            return False, f"Delete error: {e}"

    def get_backup_info(self, backup_id: int):
        return BackupRecord.query.get(backup_id)

    def _is_backup_due(self, interval: str) -> bool:
        last = BackupRecord.query.filter_by(backup_type="auto").order_by(BackupRecord.created_at.desc()).first()
        if not last:
            return True

        now = datetime.utcnow()
        delta = now - last.created_at

        if interval == "daily":
            return delta >= timedelta(days=1)
        if interval == "weekly":
            return delta >= timedelta(days=7)
        if interval == "monthly":
            return delta >= timedelta(days=30)
        return False


def auto_backup(app):
    with app.app_context():
        service = BackupService()
        enabled = Settings.get("auto_backup_enabled", False)
        interval = Settings.get("auto_backup_interval", "daily")
        if not enabled:
            return
        if service._is_backup_due(interval):
            service.create_backup(notes=f"Auto backup ({interval})", backup_type="auto")


def get_backup_service() -> BackupService:
    return BackupService()