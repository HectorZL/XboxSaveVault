import os
import glob
import datetime
import xml.etree.ElementTree as ET
import json
import base64
from .wgs_engine import WGSEngine

class XboxScanner:
    """
    Scans the system for installed Xbox PC / Game Pass games and their active WGS save games.
    """

    @classmethod
    def find_all_games(cls):
        installed_games = cls.scan_installed_games()
        wgs_saves = cls.scan_wgs_packages()

        # Combine information
        merged_games = []
        matched_pkg_ids = set()

        # Match installed games with WGS saves
        for ig in installed_games:
            pkg_name = ig.get("package_name")
            clean_display_name = ig.get("display_name") or ig.get("name") or "Juego Xbox"
            matched_save = None
            for ws in wgs_saves:
                if ws["package_id"] == pkg_name or (pkg_name and pkg_name.lower() in ws["package_id"].lower()):
                    matched_save = ws
                    matched_pkg_ids.add(ws["package_id"])
                    break

            # If matched_save is None, check if package folder exists in %LOCALAPPDATA%\Packages
            wgs_root = matched_save.get("wgs_path") if matched_save else None
            wgs_user_dirs = matched_save.get("user_dirs") if matched_save else []

            if not wgs_root and pkg_name:
                packages_dir = os.path.expandvars(r"%LOCALAPPDATA%\Packages")
                for p in os.listdir(packages_dir) if os.path.exists(packages_dir) else []:
                    if p.startswith(pkg_name):
                        cand_wgs = os.path.join(packages_dir, p, "SystemAppData", "wgs")
                        wgs_root = cand_wgs
                        # Create standard user dir path if known title_id and XUID exist
                        from .converters import SaveTools
                        sys_ids = SaveTools.detect_system_user_ids()
                        if sys_ids.get("xbox_xuids") and ig.get("title_id"):
                            xuid = sys_ids["xbox_xuids"][0]["hex"]
                            tid = ig["title_id"].upper().zfill(32)
                            user_dir_name = f"{xuid}_{tid}"
                            cand_user_dir = os.path.join(cand_wgs, user_dir_name)
                            wgs_user_dirs = [{
                                "user_title_id": user_dir_name,
                                "path": cand_user_dir,
                                "sync_id": "",
                                "pkg_name": pkg_name,
                                "containers": []
                            }]
                        break

            # Check if game has a native engine save location (e.g. Dead Cells in %LOCALAPPDATA%\MotionTwin\DeadCells)
            native_save_path = None
            native_files = []
            if clean_display_name == "Dead Cells" or "deadcells" in (pkg_name or "").lower():
                dc_local = os.path.expandvars(r"%LOCALAPPDATA%\MotionTwin\DeadCells")
                if os.path.exists(dc_local):
                    native_save_path = dc_local
                    for f in os.listdir(dc_local):
                        fp = os.path.join(dc_local, f)
                        if os.path.isfile(fp):
                            native_files.append({
                                "name": f,
                                "path": fp,
                                "size": os.path.getsize(fp),
                                "size_kb": round(os.path.getsize(fp) / 1024, 2),
                                "modified": datetime.datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M:%S")
                            })

            game_entry = {
                "id": ig.get("id") or ig.get("name"),
                "name": clean_display_name,
                "display_name": clean_display_name,
                "publisher": ig.get("publisher", "Unknown Publisher"),
                "version": ig.get("version", "1.0"),
                "title_id": ig.get("title_id"),
                "package_id": pkg_name,
                "install_path": ig.get("install_path"),
                "logo_path": ig.get("logo_path"),
                "logo_base64": ig.get("logo_base64"),
                "is_installed": True,
                "has_saves": matched_save is not None or (wgs_user_dirs and len(wgs_user_dirs[0]["containers"]) > 0) or len(native_files) > 0,
                "save_details": matched_save.get("details") if matched_save else {
                    "container_count": len(native_files),
                    "file_count": len(native_files),
                    "total_size_bytes": sum(f["size"] for f in native_files),
                    "total_size_kb": round(sum(f["size"] for f in native_files) / 1024, 2),
                    "last_saved": max(f["modified"] for f in native_files) if native_files else "N/A",
                    "containers": [{"name": f["name"], "size": f["size"], "modified": f["modified"], "files": [{"filename": f["name"], "blob_path": f["path"], "blob_guid": f["name"], "size": f["size"]}]} for f in native_files]
                } if native_files else None,
                "wgs_root": wgs_root,
                "wgs_user_dirs": wgs_user_dirs,
                "native_save_path": native_save_path,
                "native_files": native_files
            }
            merged_games.append(game_entry)

        # Add WGS saves for games that might not be in C:\XboxGames (or were uninstalled/stored elsewhere)
        for ws in wgs_saves:
            if ws["package_id"] not in matched_pkg_ids:
                game_name = ws.get("inferred_name") or ws["package_id"].split("_")[0]
                game_entry = {
                    "id": ws["package_id"],
                    "name": game_name,
                    "publisher": "Microsoft Store / Xbox",
                    "version": "Cloud/Local Save",
                    "title_id": ws.get("title_id"),
                    "package_id": ws["package_id"],
                    "install_path": None,
                    "logo_path": None,
                    "logo_base64": None,
                    "is_installed": False,
                    "has_saves": True,
                    "save_details": ws.get("details"),
                    "wgs_root": ws.get("wgs_path"),
                    "wgs_user_dirs": ws.get("user_dirs", [])
                }
                merged_games.append(game_entry)

        return merged_games

    @classmethod
    def scan_installed_games(cls):
        """Scans C:\XboxGames and other drive letters for Xbox Game Pass titles."""
        games = []
        drives = ['C', 'D', 'E', 'F', 'G', 'H', 'Z']
        scan_paths = []
        for d in drives:
            p = f"{d}:\\XboxGames"
            if os.path.exists(p):
                scan_paths.append(p)

        for base_p in scan_paths:
            try:
                for folder in os.listdir(base_p):
                    full_p = os.path.join(base_p, folder)
                    if not os.path.isdir(full_p):
                        continue
                    
                    content_dir = os.path.join(full_p, "Content")
                    target_dir = content_dir if os.path.exists(content_dir) else full_p

                    # Read MicrosoftGame.config
                    mg_config = os.path.join(target_dir, "MicrosoftGame.config")
                    meta = cls._parse_microsoft_game_config(mg_config, target_dir)
                    if meta:
                        meta["install_path"] = full_p
                        games.append(meta)
                    else:
                        # Check appxmanifest.xml
                        appx_manifest = os.path.join(target_dir, "appxmanifest.xml")
                        meta_appx = cls._parse_appx_manifest(appx_manifest, target_dir)
                        if meta_appx:
                            meta_appx["install_path"] = full_p
                            games.append(meta_appx)
                        else:
                            # Basic folder
                            if folder.lower() not in ["gamesave"]:
                                games.append({
                                    "id": folder,
                                    "name": folder,
                                    "display_name": folder,
                                    "publisher": "Unknown",
                                    "version": "1.0",
                                    "install_path": full_p
                                })
            except Exception as e:
                pass

        return games

    @classmethod
    def _parse_microsoft_game_config(cls, config_path, base_dir):
        if not os.path.exists(config_path):
            return None
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()

            identity = root.find("Identity")
            pkg_name = identity.get("Name") if identity is not None else None
            version = identity.get("Version") if identity is not None else "1.0"

            shell_vis = root.find("ShellVisuals")
            disp_name = shell_vis.get("DefaultDisplayName") if shell_vis is not None else None
            publisher = shell_vis.get("PublisherDisplayName") if shell_vis is not None else "Unknown"
            logo_rel = shell_vis.get("StoreLogo") or shell_vis.get("Square150x150Logo") if shell_vis is not None else None

            # Check OverrideDisplayName in Executable
            exe_list = root.find("ExecutableList")
            if exe_list is not None:
                exe_elem = exe_list.find("Executable")
                if exe_elem is not None:
                    override_name = exe_elem.get("OverrideDisplayName")
                    if override_name and not override_name.startswith("ms-resource:"):
                        disp_name = override_name

            # Check Description if DefaultDisplayName is package id
            if not disp_name or disp_name == pkg_name:
                desc = shell_vis.get("Description") if shell_vis is not None else None
                if desc and not desc.startswith("ms-resource:") and len(desc) < 40:
                    disp_name = desc

            title_id_elem = root.find("TitleId")
            title_id = title_id_elem.text.strip() if title_id_elem is not None and title_id_elem.text else None

            logo_b64 = None
            logo_full = None
            if logo_rel:
                logo_full = os.path.join(base_dir, logo_rel)
                if os.path.exists(logo_full):
                    try:
                        with open(logo_full, "rb") as lf:
                            logo_b64 = f"data:image/png;base64,{base64.b64encode(lf.read()).decode('utf-8')}"
                    except:
                        pass

            clean_display_name = disp_name or pkg_name or os.path.basename(base_dir)
            if clean_display_name.startswith("MotionTwin."):
                clean_display_name = "Dead Cells"

            return {
                "id": pkg_name or clean_display_name,
                "name": clean_display_name,
                "display_name": clean_display_name,
                "publisher": publisher,
                "version": version,
                "package_name": pkg_name,
                "title_id": title_id,
                "logo_path": logo_full,
                "logo_base64": logo_b64
            }
        except Exception:
            return None

    @classmethod
    def _parse_appx_manifest(cls, manifest_path, base_dir):
        if not os.path.exists(manifest_path):
            return None
        try:
            tree = ET.parse(manifest_path)
            root = tree.getroot()
            # Namespace handling
            ns = {'def': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10'}
            identity = root.find('def:Identity', ns) or root.find('Identity')
            pkg_name = identity.get('Name') if identity is not None else None

            props = root.find('def:Properties', ns) or root.find('Properties')
            disp_name = None
            publisher = "Unknown"
            logo_rel = None
            if props is not None:
                disp_elem = props.find('def:DisplayName', ns) or props.find('DisplayName')
                if disp_elem is not None and disp_elem.text:
                    disp_name = disp_elem.text
                pub_elem = props.find('def:PublisherDisplayName', ns) or props.find('PublisherDisplayName')
                if pub_elem is not None and pub_elem.text:
                    publisher = pub_elem.text
                logo_elem = props.find('def:Logo', ns) or props.find('Logo')
                if logo_elem is not None and logo_elem.text:
                    logo_rel = logo_elem.text

            logo_b64 = None
            logo_full = None
            if logo_rel:
                logo_full = os.path.join(base_dir, logo_rel)
                if os.path.exists(logo_full):
                    try:
                        with open(logo_full, "rb") as lf:
                            logo_b64 = f"data:image/png;base64,{base64.b64encode(lf.read()).decode('utf-8')}"
                    except:
                        pass

            return {
                "id": pkg_name or disp_name,
                "name": disp_name or pkg_name or os.path.basename(base_dir),
                "display_name": disp_name or pkg_name or os.path.basename(base_dir),
                "publisher": publisher,
                "version": identity.get("Version") if identity is not None else "1.0",
                "package_name": pkg_name,
                "title_id": None,
                "logo_path": logo_full,
                "logo_base64": logo_b64
            }
        except:
            return None

    @classmethod
    def scan_wgs_packages(cls):
        """Scans %LOCALAPPDATA%\Packages for all packages with WGS save structures."""
        packages_dir = os.path.expandvars(r"%LOCALAPPDATA%\Packages")
        results = []
        if not os.path.exists(packages_dir):
            return results

        for pkg in os.listdir(packages_dir):
            pkg_path = os.path.join(packages_dir, pkg)
            wgs_path = os.path.join(pkg_path, "SystemAppData", "wgs")
            if os.path.exists(wgs_path):
                # Inspect user title directories
                user_dirs = []
                total_files = 0
                total_size = 0
                last_mod = None
                containers_all = []

                for sub in os.listdir(wgs_path):
                    if sub == "t": continue
                    sub_path = os.path.join(wgs_path, sub)
                    if os.path.isdir(sub_path):
                        index_file = os.path.join(sub_path, "containers.index")
                        if os.path.exists(index_file):
                            parsed = WGSEngine.parse_wgs_container_index(index_file)
                            if parsed:
                                user_dirs.append({
                                    "user_title_id": sub,
                                    "path": sub_path,
                                    "sync_id": parsed["sync_id"],
                                    "pkg_name": parsed["pkg_name"],
                                    "containers": parsed["containers"]
                                })
                                for c in parsed["containers"]:
                                    total_size += c["size"]
                                    total_files += len(c["files"])
                                    containers_all.append(c)
                                    if c["modified"] and (not last_mod or c["modified"] > last_mod):
                                        last_mod = c["modified"]

                if user_dirs:
                    # Infer readable game name from package ID
                    clean_name = pkg.split("_")[0]
                    if "." in clean_name:
                        parts = clean_name.split(".")
                        clean_name = " ".join(parts[1:]) if len(parts) > 1 else clean_name

                    results.append({
                        "package_id": pkg,
                        "inferred_name": clean_name,
                        "wgs_path": wgs_path,
                        "user_dirs": user_dirs,
                        "details": {
                            "container_count": len(containers_all),
                            "file_count": total_files,
                            "total_size_bytes": total_size,
                            "total_size_kb": round(total_size / 1024, 2),
                            "last_saved": last_mod or "Unknown",
                            "containers": containers_all
                        }
                    })

        return results

    @classmethod
    def scan_steam_data(cls):
        """Scans Steam installations, installed games (appmanifest), and remote save files in userdata."""
        import re
        import datetime
        steam_roots = [
            r"C:\Program Files (x86)\Steam",
            r"C:\Steam",
            r"D:\Steam",
            r"D:\SteamLibrary",
            r"E:\SteamLibrary"
        ]
        installed_games = []
        app_saves_map = {}

        for sr in steam_roots:
            if not os.path.exists(sr): continue
            
            # 1. Scan userdata saves
            ud = os.path.join(sr, "userdata")
            if os.path.exists(ud):
                for u in os.listdir(ud):
                    if u.isdigit() and u != "0":
                        u_dir = os.path.join(ud, u)
                        for app in os.listdir(u_dir):
                            if app.isdigit() and app not in ["7", "760"]:
                                remote = os.path.join(u_dir, app, "remote")
                                files = []
                                if os.path.exists(remote):
                                    for r_root, _, r_files in os.walk(remote):
                                        for rf in r_files:
                                            full_rf = os.path.join(r_root, rf)
                                            files.append({
                                                "name": rf,
                                                "path": full_rf,
                                                "size": os.path.getsize(full_rf),
                                                "size_kb": round(os.path.getsize(full_rf) / 1024, 2),
                                                "modified": datetime.datetime.fromtimestamp(os.path.getmtime(full_rf)).strftime("%Y-%m-%d %H:%M:%S")
                                            })
                                if files:
                                    app_saves_map[app] = {
                                        "steam3_id": u,
                                        "appid": app,
                                        "remote_path": remote,
                                        "files": files,
                                        "total_size": sum(f["size"] for f in files),
                                        "total_size_kb": round(sum(f["size"] for f in files) / 1024, 2),
                                        "last_modified": max(f["modified"] for f in files) if files else "N/A"
                                    }

            # 2. Scan installed games
            steamapps_dirs = [os.path.join(sr, "steamapps")]
            lib_vdf = os.path.join(sr, "steamapps", "libraryfolders.vdf")
            if os.path.exists(lib_vdf):
                try:
                    with open(lib_vdf, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    paths = re.findall(r'"path"\s+"([^"]+)"', content)
                    for p in paths:
                        sa = os.path.join(p.replace("\\\\", "\\"), "steamapps")
                        if os.path.exists(sa) and sa not in steamapps_dirs:
                            steamapps_dirs.append(sa)
                except:
                    pass

            for sa in steamapps_dirs:
                if not os.path.exists(sa): continue
                for acf in glob.glob(os.path.join(sa, "appmanifest_*.acf")):
                    try:
                        with open(acf, "r", encoding="utf-8", errors="ignore") as f:
                            text = f.read()
                        appid_match = re.search(r'"appid"\s+"(\d+)"', text)
                        name_match = re.search(r'"name"\s+"([^"]+)"', text)
                        installdir_match = re.search(r'"installdir"\s+"([^"]+)"', text)
                        if appid_match and name_match:
                            app_id = appid_match.group(1)
                            game_name = name_match.group(1)
                            if "redistributable" in game_name.lower() or "steamworks" in game_name.lower():
                                continue
                            inst_dir = installdir_match.group(1) if installdir_match else game_name
                            full_install = os.path.join(sa, "common", inst_dir)
                            
                            matched_save = app_saves_map.get(app_id)

                            # Check for local game save folder (e.g. Dead Cells/save)
                            local_save_dir = os.path.join(full_install, "save")
                            extra_files = []
                            if os.path.exists(local_save_dir):
                                for f in os.listdir(local_save_dir):
                                    fp = os.path.join(local_save_dir, f)
                                    if os.path.isfile(fp):
                                        extra_files.append({
                                            "name": f,
                                            "path": fp,
                                            "size": os.path.getsize(fp),
                                            "size_kb": round(os.path.getsize(fp) / 1024, 2),
                                            "modified": datetime.datetime.fromtimestamp(os.path.getmtime(fp)).strftime("%Y-%m-%d %H:%M:%S")
                                        })

                            installed_games.append({
                                "id": f"steam_{app_id}",
                                "appid": app_id,
                                "name": game_name,
                                "platform": "Steam",
                                "install_path": full_install if os.path.exists(full_install) else None,
                                "has_saves": matched_save is not None or len(extra_files) > 0,
                                "save_details": matched_save,
                                "extra_save_files": extra_files,
                                "remote_save_path": matched_save["remote_path"] if matched_save else (local_save_dir if extra_files else None)
                            })
                    except:
                        pass

        # Also add saves for games not currently installed
        for app_id, sdata in app_saves_map.items():
            if not any(g["appid"] == app_id for g in installed_games):
                installed_games.append({
                    "id": f"steam_{app_id}",
                    "appid": app_id,
                    "name": f"Steam App ({app_id})",
                    "platform": "Steam (Cloud Save)",
                    "install_path": None,
                    "has_saves": True,
                    "save_details": sdata,
                    "extra_save_files": [],
                    "remote_save_path": sdata["remote_path"]
                })

        return installed_games

    @classmethod
    def scan_epic_and_local_data(cls):
        """Scans Epic Games Launcher manifests, AppData LocalLow, and %USERPROFILE%\\Saved Games."""
        import datetime
        epic_games = []
        epic_manifests = r"C:\ProgramData\Epic\EpicGamesLauncher\Data\Manifests"
        if os.path.exists(epic_manifests):
            for item in os.listdir(epic_manifests):
                if item.endswith(".item"):
                    try:
                        with open(os.path.join(epic_manifests, item), "r", encoding="utf-8", errors="ignore") as f:
                            data = json.load(f)
                        disp = data.get("DisplayName")
                        inst = data.get("InstallLocation")
                        if disp:
                            epic_games.append({
                                "id": f"epic_{data.get('AppName', disp)}",
                                "name": disp,
                                "platform": "Epic Games",
                                "install_path": inst,
                                "app_name": data.get("AppName"),
                                "has_saves": False,
                                "save_path": None,
                                "save_files": []
                            })
                    except:
                        pass

        # Scan %USERPROFILE%\Saved Games
        saved_games_root = os.path.expandvars(r"%USERPROFILE%\Saved Games")
        local_saves = []
        if os.path.exists(saved_games_root):
            for sub in os.listdir(saved_games_root):
                full_s = os.path.join(saved_games_root, sub)
                if os.path.isdir(full_s) and sub.lower() != "desktop.ini":
                    files = []
                    for r_root, _, r_files in os.walk(full_s):
                        for rf in r_files:
                            full_rf = os.path.join(r_root, rf)
                            files.append({
                                "name": rf,
                                "path": full_rf,
                                "size": os.path.getsize(full_rf),
                                "size_kb": round(os.path.getsize(full_rf) / 1024, 2),
                                "modified": datetime.datetime.fromtimestamp(os.path.getmtime(full_rf)).strftime("%Y-%m-%d %H:%M:%S")
                            })
                    if files:
                        local_saves.append({
                            "id": f"savedgames_{sub}",
                            "name": sub,
                            "platform": "PC Saved Games",
                            "save_path": full_s,
                            "files": files,
                            "file_count": len(files),
                            "total_size": sum(f["size"] for f in files),
                            "total_size_kb": round(sum(f["size"] for f in files) / 1024, 2),
                            "last_modified": max(f["modified"] for f in files) if files else "N/A"
                        })

        # Scan %USERPROFILE%\AppData\LocalLow
        locallow_root = os.path.expandvars(r"%USERPROFILE%\AppData\LocalLow")
        if os.path.exists(locallow_root):
            for dev in os.listdir(locallow_root):
                dev_path = os.path.join(locallow_root, dev)
                if os.path.isdir(dev_path) and dev.lower() not in ["microsoft", "intel", "nvidia", "temp", "cryptneturlcache", "unity"]:
                    for title in os.listdir(dev_path):
                        title_path = os.path.join(dev_path, title)
                        if os.path.isdir(title_path):
                            files = []
                            for r_root, _, r_files in os.walk(title_path):
                                for rf in r_files:
                                    if rf.endswith((".sav", ".dat", ".json", ".xml", ".bin", ".db", ".txt")) and not rf.endswith((".log", ".tmp")):
                                        full_rf = os.path.join(r_root, rf)
                                        files.append({
                                            "name": rf,
                                            "path": full_rf,
                                            "size": os.path.getsize(full_rf),
                                            "size_kb": round(os.path.getsize(full_rf) / 1024, 2),
                                            "modified": datetime.datetime.fromtimestamp(os.path.getmtime(full_rf)).strftime("%Y-%m-%d %H:%M:%S")
                                        })
                            if files:
                                local_saves.append({
                                    "id": f"locallow_{dev}_{title}",
                                    "name": title,
                                    "developer": dev,
                                    "platform": "AppData LocalLow",
                                    "save_path": title_path,
                                    "files": files,
                                    "file_count": len(files),
                                    "total_size": sum(f["size"] for f in files),
                                    "total_size_kb": round(sum(f["size"] for f in files) / 1024, 2),
                                    "last_modified": max(f["modified"] for f in files) if files else "N/A"
                                })

        return epic_games, local_saves

    @classmethod
    def get_all_platforms_overview(cls):
        """Returns consolidated overview of Xbox, Steam, Epic Games, and Local Saves."""
        xbox_games = cls.find_all_games()
        steam_games = cls.scan_steam_data()
        epic_games, local_saves = cls.scan_epic_and_local_data()

        return {
            "xbox": xbox_games,
            "steam": steam_games,
            "epic": epic_games,
            "local_saves": local_saves,
            "counts": {
                "xbox": len(xbox_games),
                "steam": len(steam_games),
                "epic": len(epic_games),
                "local_saves": len(local_saves)
            }
        }
