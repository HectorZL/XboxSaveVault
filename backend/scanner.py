import os
import glob
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

            game_entry = {
                "id": ig.get("id") or ig.get("name"),
                "name": ig.get("display_name") or ig.get("name"),
                "publisher": ig.get("publisher", "Unknown Publisher"),
                "version": ig.get("version", "1.0"),
                "title_id": ig.get("title_id"),
                "package_id": pkg_name,
                "install_path": ig.get("install_path"),
                "logo_path": ig.get("logo_path"),
                "logo_base64": ig.get("logo_base64"),
                "is_installed": True,
                "has_saves": matched_save is not None or (wgs_user_dirs and len(wgs_user_dirs[0]["containers"]) > 0),
                "save_details": matched_save.get("details") if matched_save else None,
                "wgs_root": wgs_root,
                "wgs_user_dirs": wgs_user_dirs
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
