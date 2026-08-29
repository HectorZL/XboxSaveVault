import os
import sys
import json
import subprocess
import datetime

APPDATA_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "XboxSaveVault")
DEFAULT_CONFIG_PATH = os.path.join(APPDATA_DIR, "config.json")
OLD_CONFIG_PATH = os.path.join(os.path.expanduser("~"), "XboxSaveBackups", "config.json")
DEFAULT_BACKUP_DIR = os.path.join(os.path.expanduser("~"), "XboxSaveBackups")

TASK_NAME = "XboxSaveVault_AutoSync_Silent"

class ConfigManager:
    """
    Manages persistent configuration, automatic backup rules,
    and Windows Task Scheduler integration for silent background sync (Cron).
    """

    @classmethod
    def get_config_path(cls):
        os.makedirs(APPDATA_DIR, exist_ok=True)
        return DEFAULT_CONFIG_PATH

    @classmethod
    def get_default_config(cls):
        return {
            "backup_root_dir": DEFAULT_BACKUP_DIR,
            "raw_saves_subfolder": "Raw_Saves",
            "backups_subfolder": "Backups",
            "auto_sync_enabled": False,
            "auto_sync_interval_mins": 60,
            "max_backup_history": 10,
            "backup_all_platforms": True,
            "last_sync_time": None,
            "last_sync_status": "Sin sincronizaciones previas",
            "last_sync_files_count": 0
        }

    @classmethod
    def load_config(cls):
        config_path = cls.get_config_path()
        defaults = cls.get_default_config()

        # Migrate from old config path if exists and new does not
        if not os.path.exists(config_path) and os.path.exists(OLD_CONFIG_PATH):
            try:
                with open(OLD_CONFIG_PATH, "r", encoding="utf-8") as f:
                    old_data = json.load(f)
                cls.save_config(old_data)
                return old_data
            except:
                pass

        if not os.path.exists(config_path):
            cls.save_config(defaults)
            return defaults

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Merge with defaults in case of new keys
            for k, v in defaults.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            return defaults

    @classmethod
    def save_config(cls, new_config):
        config_path = cls.get_config_path()
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(new_config, f, indent=2, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"Error guardando configuración: {e}")
            return False

    @classmethod
    def update_key(cls, key, value):
        cfg = cls.load_config()
        cfg[key] = value
        cls.save_config(cfg)
        return cfg

    @classmethod
    def get_backup_dir(cls):
        cfg = cls.load_config()
        bdir = cfg.get("backup_root_dir", DEFAULT_BACKUP_DIR)
        os.makedirs(bdir, exist_ok=True)
        return bdir

    @classmethod
    def get_scheduled_task_status(cls):
        """
        Queries Windows Task Scheduler to see if our silent cron task is installed and enabled.
        """
        if sys.platform != "win32":
            return {"installed": False, "status": "No soportado en este SO", "next_run": "N/A"}

        try:
            cmd = f'schtasks /Query /TN "{TASK_NAME}" /FO CSV /NH'
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors='ignore')
            if proc.returncode == 0 and TASK_NAME.lower() in proc.stdout.lower():
                lines = [l.strip() for l in proc.stdout.strip().splitlines() if l.strip()]
                if lines:
                    parts = [p.strip('"') for p in lines[0].split('","')]
                    task_status = parts[2] if len(parts) > 2 else "Listo"
                    next_run = parts[1] if len(parts) > 1 else "Programada"
                    return {
                        "installed": True,
                        "task_name": TASK_NAME,
                        "status": task_status,
                        "next_run": next_run
                    }
                return {"installed": True, "task_name": TASK_NAME, "status": "Activa", "next_run": "Programada"}
            else:
                return {"installed": False, "task_name": TASK_NAME, "status": "No Instalada", "next_run": "N/A"}
        except Exception as e:
            return {"installed": False, "error": str(e), "status": "Desconocido", "next_run": "N/A"}

    @classmethod
    def install_windows_scheduled_task(cls, interval_mins=60):
        """
        Installs a silent cron task into Windows Task Scheduler.
        Runs pythonw.exe or the compiled exe with --sync-silent every interval_mins.
        """
        if sys.platform != "win32":
            return {"success": False, "error": "Solo disponible en Windows"}

        # Determine executable and arguments
        if getattr(sys, 'frozen', False):
            # Executable build
            exe_path = sys.executable
            action_cmd = f'"{exe_path}" --sync-silent'
        else:
            # Running as python script
            script_path = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(__file__)), "xbox_save_manager.py"))
            # Prefer pythonw.exe to be completely invisible without console
            pythonw_path = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
            if not os.path.exists(pythonw_path):
                pythonw_path = sys.executable
            action_cmd = f'"{pythonw_path}" "{script_path}" --sync-silent'

        # Remove existing task if present
        subprocess.run(f'schtasks /Delete /TN "{TASK_NAME}" /F', shell=True, capture_output=True)

        # Schedule frequency mapping
        interval_mins = max(5, int(interval_mins))
        
        # Build schtasks create command
        # /SC MINUTE /MO <mins> runs every <mins> minutes silently
        cmd = f'schtasks /Create /TN "{TASK_NAME}" /TR "{action_cmd}" /SC MINUTE /MO {interval_mins} /F /RU "%USERNAME%"'
        
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, errors='ignore')
            if proc.returncode == 0:
                cls.update_key("auto_sync_enabled", True)
                cls.update_key("auto_sync_interval_mins", interval_mins)
                return {
                    "success": True,
                    "message": f"Tarea programada silenciosa instalada exitosamente (cada {interval_mins} minutos).",
                    "task_name": TASK_NAME,
                    "interval_mins": interval_mins
                }
            else:
                return {
                    "success": False,
                    "error": f"Error al crear la tarea: {proc.stderr or proc.stdout}"
                }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @classmethod
    def uninstall_windows_scheduled_task(cls):
        """
        Removes the silent cron task from Windows Task Scheduler.
        """
        if sys.platform != "win32":
            return {"success": False, "error": "Solo disponible en Windows"}

        try:
            proc = subprocess.run(f'schtasks /Delete /TN "{TASK_NAME}" /F', shell=True, capture_output=True, text=True, errors='ignore')
            cls.update_key("auto_sync_enabled", False)
            if proc.returncode == 0 or "no se encuentra" in (proc.stderr or proc.stdout).lower() or "not found" in (proc.stderr or proc.stdout).lower():
                return {"success": True, "message": "Tarea programada eliminada exitosamente."}
            else:
                return {"success": False, "error": proc.stderr or proc.stdout}
        except Exception as e:
            return {"success": False, "error": str(e)}
