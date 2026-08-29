#!/usr/bin/env python3
"""
Xbox Save Vault / Xbox Save Manager
Gestor, exportador, importador y conversor de partidas guardadas de la app de Xbox PC / Game Pass.
"""

import os
import sys
import argparse
import webbrowser
import threading
import time

# Safe stdout/stderr handling for GUI/noconsole mode on Windows
class NullWriter:
    def write(self, s): pass
    def flush(self): pass
    def isatty(self): return False

if sys.stdout is None:
    sys.stdout = NullWriter()
if sys.stderr is None:
    sys.stderr = NullWriter()

# Ensure proper utf-8 encoding on Windows console
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

# Ensure backend package is in python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.scanner import XboxScanner
from backend.wgs_engine import WGSEngine
from backend.server import start_server, DEFAULT_BACKUP_ROOT
from backend.config_manager import ConfigManager

def cli_list_games():
    print("\n" + "="*80)
    print(" 🎮 XBOX SAVE VAULT - JUEGOS Y PARTIDAS DETECTADAS")
    print("="*80)
    games = XboxScanner.find_all_games()
    if not games:
        print("[-] No se encontraron juegos o partidas de Xbox en el sistema.")
        return

    for i, g in enumerate(games, 1):
        status = "INSTALADO" if g.get("is_installed") else "NO INSTALADO"
        saves_status = "CON PARTIDAS WGS" if g.get("has_saves") else "SIN PARTIDAS"
        print(f"\n[{i}] {g['name']}")
        print(f"    - Desarrollador/Publisher: {g.get('publisher', 'Desconocido')} (v{g.get('version', '1.0')})")
        print(f"    - Paquete: {g.get('package_id', 'N/A')}")
        if g.get("title_id"):
            print(f"    - Title ID: {g['title_id']}")
        if g.get("install_path"):
            print(f"    - Ruta de Instalación: {g['install_path']}")
        
        if g.get("has_saves"):
            details = g.get("save_details", {})
            print(f"    - 💾 Partidas Guardadas: {details.get('container_count', 0)} ranuras ({details.get('total_size_kb', 0)} KB)")
            print(f"    - Último guardado: {details.get('last_saved', 'N/A')}")
            for c in details.get("containers", []):
                print(f"        * Ranura: {c['name']} (Seq {c['seq']}, {round(c['size']/1024, 2)} KB, Mod: {c['modified']})")
        else:
            print(f"    - Estado de partidas: {saves_status}")
    print("\n" + "="*80 + "\n")

def find_game_by_name(query):
    games = XboxScanner.find_all_games()
    q = query.lower()
    for g in games:
        if q in g["name"].lower() or (g.get("package_id") and q in g["package_id"].lower()):
            return g
    return None

def cli_export_raw(game_name, dest_dir):
    game = find_game_by_name(game_name)
    if not game:
        print(f"[-] Error: Juego '{game_name}' no encontrado.")
        return
    if not game.get("wgs_user_dirs"):
        print(f"[-] Error: El juego '{game['name']}' no tiene partidas WGS guardadas.")
        return

    user_wgs_dir = game["wgs_user_dirs"][0]["path"]
    bdir = ConfigManager.get_backup_dir()
    out_dir = dest_dir or os.path.join(bdir, "Raw_Saves", game["name"])
    print(f"[*] Exportando partidas legibles (.sav) para '{game['name']}' a {out_dir}...")
    res = WGSEngine.export_raw_saves(user_wgs_dir, out_dir)
    print(f"[+] ¡Éxito! Se exportaron {res['file_count']} archivos:")
    for f in res["files"]:
        print(f"    - {f['name']} ({f['size']} bytes)")

def cli_export_slot(game_name, slot_name, out_path):
    game = find_game_by_name(game_name)
    if not game:
        print(f"[-] Error: Juego '{game_name}' no encontrado.")
        return
    if not game.get("wgs_user_dirs"):
        print(f"[-] Error: El juego '{game['name']}' no tiene partidas WGS guardadas.")
        return

    user_wgs_dir = game["wgs_user_dirs"][0]["path"]
    bdir = ConfigManager.get_backup_dir()
    target_out = out_path or os.path.join(bdir, "Raw_Saves", game["name"], f"{slot_name}.sav")
    print(f"[*] Exportando ranura '{slot_name}' de '{game['name']}' a {target_out}...")
    try:
        res = WGSEngine.export_single_slot_raw(user_wgs_dir, slot_name, target_out)
        print(f"[+] ¡Éxito! Ranura exportada: {res['exported_file']} ({res['size_kb']} KB)")
    except Exception as e:
        print(f"[-] Error: {e}")

def cli_export_backup(game_name, backup_file):
    game = find_game_by_name(game_name)
    if not game:
        print(f"[-] Error: Juego '{game_name}' no encontrado.")
        return
    if not game.get("wgs_user_dirs"):
        print(f"[-] Error: El juego '{game['name']}' no tiene partidas WGS guardadas.")
        return

    user_wgs_dir = game["wgs_user_dirs"][0]["path"]
    import datetime
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    bdir = ConfigManager.get_backup_dir()
    out_zip = backup_file or os.path.join(bdir, "Backups", f"{game['name'].replace(' ', '_')}_Backup_{ts}.zip")
    print(f"[*] Creando backup completo de Xbox (.ZIP) para '{game['name']}' en {out_zip}...")
    res = WGSEngine.create_full_xbox_backup(user_wgs_dir, out_zip, game)
    print(f"[+] ¡Backup completado exitosamente! Tamaño: {round(res['size']/1024, 2)} KB")

def cli_restore_backup(backup_zip, target_game_name):
    game = find_game_by_name(target_game_name)
    if not game:
        print(f"[-] Error: Juego '{target_game_name}' no encontrado.")
        return
    if not game.get("wgs_user_dirs"):
        print(f"[-] Error: El juego '{game['name']}' no tiene estructura WGS inicializada.")
        return

    target_wgs_dir = game["wgs_user_dirs"][0]["path"]
    print(f"[*] Restaurando backup {backup_zip} en '{game['name']}'...")
    res = WGSEngine.restore_full_xbox_backup(backup_zip, target_wgs_dir)
    print(f"[+] ¡Restauración completada con éxito!")
    if res.get("safety_backup"):
        print(f"[i] Copia de seguridad previa guardada en: {res['safety_backup']}")

def cli_sync_silent():
    """
    Executes a 100% silent automated background synchronization of all detected saves.
    Logs execution to sync_silent.log in the user's backup folder and exits.
    """
    cfg = ConfigManager.load_config()
    bdir = ConfigManager.get_backup_dir()
    max_history = cfg.get("max_backup_history", 10)
    
    log_path = os.path.join(bdir, "sync_silent.log")
    import datetime
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        results = WGSEngine.sync_all_games_backup(bdir, max_history)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now_str}] Auto-Sync Éxito: {results['total_games']} juegos respaldados, {results['total_saves']} archivos procesados.\n")
            if results.get("errors"):
                for err in results["errors"]:
                    f.write(f"    [!] Error: {err}\n")
    except Exception as e:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{now_str}] Auto-Sync Error crítico: {e}\n")

def start_gui(port=8899):
    server, actual_port = start_server(port)
    url = f"http://127.0.0.1:{actual_port}"
    print(f"\n[+] Servidor iniciado en: {url}")
    
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Intentar abrir con pywebview (Ventana nativa ultraligera WebView2)
    has_webview = False
    try:
        import webview
        has_webview = True
    except ImportError:
        pass

    if has_webview:
        print("[*] Iniciando ventana de escritorio nativa (WebView2)...")
        try:
            window = webview.create_window(
                title="Xbox Save Vault - Gestor de Partidas Xbox PC",
                url=url,
                width=1280,
                height=820,
                min_size=(980, 640),
                background_color="#0a0f12"
            )
            webview.start(gui="edgechromium")
            print("[*] Ventana cerrada por el usuario. Finalizando aplicación...")
            server.shutdown()
            return
        except Exception as e:
            print(f"[!] Aviso al iniciar pywebview ({e}). Usando modo alternativo...")

    # Fallback 1: Microsoft Edge en modo aplicación (ventana independiente sin barras)
    launched_app_mode = False
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        "msedge"
    ]
    for ep in edge_paths:
        try:
            import subprocess
            subprocess.Popen([ep, f"--app={url}", "--window-size=1280,820"])
            print("[+] Abierto en modo aplicación autónoma de Edge.")
            launched_app_mode = True
            break
        except:
            continue

    # Fallback 2: Navegador por defecto
    if not launched_app_mode:
        print("[+] Abriendo en el navegador...")
        webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Deteniendo servidor...")
        server.shutdown()

def main():
    parser = argparse.ArgumentParser(description="Xbox Save Vault - Gestor de Partidas Xbox PC & Game Pass")
    parser.add_argument("--gui", action="store_true", help="Iniciar interfaz gráfica web (Por defecto)")
    parser.add_argument("--port", type=int, default=8899, help="Puerto para la interfaz web (Default: 8899)")
    parser.add_argument("--list", action="store_true", help="Listar todos los juegos y partidas en consola")
    parser.add_argument("--export-raw", type=str, metavar="GAME_NAME", help="Exportar todas las partidas de un juego a archivos .sav legibles")
    parser.add_argument("--export-slot", type=str, metavar="GAME_NAME", help="Exportar una ranura específica a .sav")
    parser.add_argument("--slot", type=str, metavar="SLOT_NAME", help="Nombre de la ranura para --export-slot")
    parser.add_argument("--backup", type=str, metavar="GAME_NAME", help="Crear backup completo de Xbox en .ZIP")
    parser.add_argument("--restore", type=str, metavar="BACKUP_ZIP", help="Restaurar archivo .ZIP de backup")
    parser.add_argument("--target", type=str, metavar="TARGET_GAME", help="Juego objetivo para restaurar backup")
    parser.add_argument("--out", type=str, help="Ruta de destino para la exportación o backup")
    parser.add_argument("--sync-silent", action="store_true", help="Ejecutar sincronización/respaldo automático silencioso en segundo plano")
    parser.add_argument("--cron", action="store_true", help="Alias de --sync-silent")

    args = parser.parse_args()

    if args.sync_silent or args.cron:
        cli_sync_silent()
    elif args.list:
        cli_list_games()
    elif args.export_slot:
        if not args.slot:
            print("[-] Error: Debes especificar la ranura con --slot 'NombreDeRanura'")
            return
        cli_export_slot(args.export_slot, args.slot, args.out)
    elif args.export_raw:
        cli_export_raw(args.export_raw, args.out)
    elif args.backup:
        cli_export_backup(args.backup, args.out)
    elif args.restore:
        if not args.target:
            print("[-] Error: Debes especificar el juego objetivo con --target 'NombreDelJuego'")
            return
        cli_restore_backup(args.restore, args.target)
    else:
        # Default: Launch GUI
        start_gui(args.port)

if __name__ == "__main__":
    main()
