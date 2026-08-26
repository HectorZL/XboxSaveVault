import os
import sys
import json
import urllib.parse
import subprocess
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
import traceback
from .wgs_engine import WGSEngine
from .scanner import XboxScanner

DEFAULT_BACKUP_ROOT = os.path.join(os.path.expanduser("~"), "XboxSaveBackups")
os.makedirs(DEFAULT_BACKUP_ROOT, exist_ok=True)

class XboxSaveAPIHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # Keep console output neat
        pass

    def send_json(self, data, status_code=200):
        body = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == "/api/games":
            try:
                games = XboxScanner.find_all_games()
                self.send_json({"success": True, "games": games, "default_backup_root": DEFAULT_BACKUP_ROOT})
            except Exception as e:
                self.send_json({"success": False, "error": str(e), "trace": traceback.format_exc()}, 500)
            return

        elif path == "/api/platforms":
            try:
                overview = XboxScanner.get_all_platforms_overview()
                self.send_json({"success": True, "data": overview, "default_backup_root": DEFAULT_BACKUP_ROOT})
            except Exception as e:
                self.send_json({"success": False, "error": str(e), "trace": traceback.format_exc()}, 500)
            return

        elif path == "/api/default-backup-dir":
            self.send_json({"success": True, "path": DEFAULT_BACKUP_ROOT})
            return

        elif path == "/api/tools/user-ids":
            try:
                from .converters import SaveTools
                data = SaveTools.detect_system_user_ids()
                self.send_json({"success": True, "data": data})
            except Exception as e:
                self.send_json({"success": False, "error": str(e)}, 500)
            return

        # Serve static web files
        self.serve_static(path)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get('Content-Length', 0))
        body_bytes = self.rfile.read(length) if length > 0 else b'{}'
        
        try:
            req_data = json.loads(body_bytes.decode('utf-8')) if body_bytes else {}
        except:
            req_data = {}

        try:
            if path == "/api/scan":
                games = XboxScanner.find_all_games()
                self.send_json({"success": True, "games": games})

            elif path == "/api/export/raw":
                user_wgs_dir = req_data.get("user_wgs_dir")
                dest_dir = req_data.get("dest_dir") or os.path.join(DEFAULT_BACKUP_ROOT, "Raw_Saves", req_data.get("game_name", "Game"))
                res = WGSEngine.export_raw_saves(user_wgs_dir, dest_dir)
                self.send_json(res)

            elif path == "/api/export/backup":
                user_wgs_dir = req_data.get("user_wgs_dir")
                game_name = req_data.get("game_name", "XboxGame").replace(" ", "_")
                import datetime
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = req_data.get("backup_path") or os.path.join(DEFAULT_BACKUP_ROOT, "Backups", f"{game_name}_Backup_{ts}.zip")
                res = WGSEngine.create_full_xbox_backup(user_wgs_dir, backup_path, req_data.get("game_meta"))
                self.send_json(res)

            elif path == "/api/import/backup":
                backup_zip_path = req_data.get("backup_zip_path")
                target_wgs_dir = req_data.get("target_wgs_dir")
                res = WGSEngine.restore_full_xbox_backup(backup_zip_path, target_wgs_dir)
                self.send_json(res)

            elif path == "/api/import/slot":
                user_wgs_dir = req_data.get("user_wgs_dir")
                container_name = req_data.get("container_name")
                raw_file_path = req_data.get("raw_file_path")
                res = WGSEngine.inject_raw_save_to_slot(user_wgs_dir, container_name, raw_file_path)
                self.send_json(res)

            elif path == "/api/tools/inspect-save":
                file_path = req_data.get("file_path")
                from .converters import SaveTools
                res = SaveTools.inspect_save_file(file_path)
                self.send_json({"success": True, "info": res})

            elif path == "/api/tools/patch-id":
                input_file = req_data.get("input_file")
                output_file = req_data.get("output_file") or input_file
                old_id = req_data.get("old_id", "")
                new_id = req_data.get("new_id", "")
                from .converters import SaveTools
                res = SaveTools.patch_account_id(input_file, output_file, old_id, new_id)
                self.send_json(res)

            elif path == "/api/bridge/transfer":
                source_platform = req_data.get("source_platform")
                target_platform = req_data.get("target_platform")
                source_file = req_data.get("source_file")
                target_meta = req_data.get("target_meta", {})
                target_slot = req_data.get("target_slot")
                from .converters import CrossPlatformBridge
                res = CrossPlatformBridge.transfer_save(source_platform, target_platform, source_file, target_meta, target_slot)
                self.send_json(res)

            elif path == "/api/open-folder":
                folder_path = req_data.get("path")
                if folder_path and os.path.exists(folder_path):
                    if sys.platform == "win32":
                        subprocess.Popen(f'explorer "{os.path.abspath(folder_path)}"')
                    self.send_json({"success": True, "opened": folder_path})
                else:
                    self.send_json({"success": False, "error": "Path does not exist"}, 400)

            elif path == "/api/open-file-selector":
                # Open Windows native file dialog via PowerShell
                mode = req_data.get("mode", "folder") # 'folder' or 'file'
                filter_type = req_data.get("filter", "All Files (*.*)|*.*")
                
                if mode == "folder":
                    ps_cmd = '[System.Reflection.Assembly]::LoadWithPartialName("System.windows.forms") | Out-Null; $d = New-Object System.Windows.Forms.FolderBrowserDialog; $d.ShowNewFolderButton = $true; if ($d.ShowDialog() -eq "OK") { Write-Output $d.SelectedPath }'
                else:
                    filter_str = filter_type.replace('"', '`"')
                    ps_cmd = '[System.Reflection.Assembly]::LoadWithPartialName("System.windows.forms") | Out-Null; $d = New-Object System.Windows.Forms.OpenFileDialog; $d.Filter = "' + filter_str + '"; if ($d.ShowDialog() -eq "OK") { Write-Output $d.FileName }'
                
                proc = subprocess.run(["powershell", "-Command", ps_cmd], capture_output=True, text=True)
                selected_path = proc.stdout.strip()
                self.send_json({"success": True, "selected_path": selected_path if selected_path else None})

            else:
                self.send_json({"success": False, "error": "Unknown API endpoint"}, 404)

        except Exception as e:
            self.send_json({"success": False, "error": str(e), "trace": traceback.format_exc()}, 500)

    def serve_static(self, path):
        if path == "/" or path == "":
            path = "/index.html"
        
        clean_path = path.lstrip("/")
        base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
        file_path = os.path.join(base_dir, clean_path)

        if not os.path.exists(file_path) or not os.path.isfile(file_path):
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"404 Not Found")
            return

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        with open(file_path, "rb") as f:
            content = f.read()

        self.send_response(200)
        self.send_header('Content-Type', f"{mime_type}; charset=utf-8" if "text" in mime_type or "javascript" in mime_type else mime_type)
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)

def start_server(port=8899):
    server = HTTPServer(('127.0.0.1', port), XboxSaveAPIHandler)
    print(f"[*] Xbox Save Manager Server running at http://127.0.0.1:{port}")
    return server
