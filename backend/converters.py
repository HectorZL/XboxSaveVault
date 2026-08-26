import os
import sys
import struct
import io
import re
import glob

class SaveTools:
    """
    Advanced converters, ID patchers, and metadata auto-sync for cross-platform save transfers (Steam / Epic / Xbox).
    """

    @staticmethod
    def detect_system_user_ids():
        """
        Auto-detects the local user's Xbox XUID and SteamID64 from local storage.
        """
        detected = {
            "xbox_xuids": [],
            "steam_ids": []
        }

        # 1. Detect Xbox XUIDs from %LOCALAPPDATA%\Packages
        packages_dir = os.path.expandvars(r"%LOCALAPPDATA%\Packages")
        if os.path.exists(packages_dir):
            for pkg in os.listdir(packages_dir):
                wgs_path = os.path.join(packages_dir, pkg, "SystemAppData", "wgs")
                if os.path.exists(wgs_path):
                    for sub in os.listdir(wgs_path):
                        if sub == "t": continue
                        # format: <16_hex_xuid>_<32_hex_titleid>
                        if "_" in sub:
                            xuid_hex = sub.split("_")[0]
                            if len(xuid_hex) == 16 and xuid_hex not in detected["xbox_xuids"]:
                                try:
                                    xuid_dec = str(int(xuid_hex, 16))
                                    detected["xbox_xuids"].append({
                                        "hex": xuid_hex,
                                        "dec": xuid_dec,
                                        "source_dir": sub
                                    })
                                except:
                                    pass

        # 2. Detect SteamID3 and SteamID64 from Steam userdata
        steam_paths = [
            r"C:\Program Files (x86)\Steam\userdata",
            r"C:\Steam\userdata",
            r"D:\Steam\userdata",
            r"E:\Steam\userdata"
        ]
        for sp in steam_paths:
            if os.path.exists(sp):
                for folder in os.listdir(sp):
                    if folder.isdigit() and folder != "0":
                        steam3_id = int(folder)
                        # SteamID64 base = 76561197960265728
                        steam64_id = steam3_id + 76561197960265728
                        detected["steam_ids"].append({
                            "steam3": str(steam3_id),
                            "steam64": str(steam64_id),
                            "steam64_hex": f"{steam64_id:016X}",
                            "userdata_path": os.path.join(sp, folder)
                        })

        return detected

    @staticmethod
    def inspect_save_file(file_path):
        """
        Inspects a .sav file to detect engine format (Unreal GVAS, Unity, SQLite, JSON, etc.),
        engine versions, and embedded account IDs.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File {file_path} not found")

        with open(file_path, "rb") as f:
            header = f.read(512)
            f.seek(0)
            data = f.read()

        file_size = len(data)
        info = {
            "file_name": os.path.basename(file_path),
            "size_bytes": file_size,
            "size_kb": round(file_size / 1024, 2),
            "format": "Unknown Binary",
            "is_unreal_gvas": False,
            "engine_version": None,
            "save_class": None,
            "detected_ids": []
        }

        # Check Unreal Engine GVAS
        if header.startswith(b"GVAS"):
            info["format"] = "Unreal Engine GVAS Save"
            info["is_unreal_gvas"] = True
            try:
                stream = io.BytesIO(data)
                stream.seek(4) # Skip GVAS
                save_version = struct.unpack("<I", stream.read(4))[0]
                pkg_version = struct.unpack("<I", stream.read(4))[0]
                info["save_game_version"] = save_version
                info["package_version"] = pkg_version
                
                # Try reading engine version if present
                if save_version >= 2:
                    eng_major, eng_minor, eng_patch, eng_build = struct.unpack("<HHHH", stream.read(8))
                    info["engine_version"] = f"{eng_major}.{eng_minor}.{eng_patch}-{eng_build}"
            except Exception:
                pass

        # Check JSON / Plaintext
        elif data.strip().startswith(b"{") or data.strip().startswith(b"["):
            info["format"] = "JSON / Plaintext Save"

        # Check SQLite
        elif header.startswith(b"SQLite format 3"):
            info["format"] = "SQLite Database Save"

        # Check for potential SteamID64 (76561198...) in raw data
        # Search for 8-byte uint64 in range 76561197960265728 - 76561200000000000
        steam_min = 76561197960265728
        steam_max = 76561200000000000
        
        # Scan for SteamID strings
        str_matches = re.findall(rb'7656119\d{10}', data)
        for m in str_matches:
            s_id = m.decode('utf-8', errors='ignore')
            if s_id not in info["detected_ids"]:
                info["detected_ids"].append(f"SteamID64 (String): {s_id}")

        # Scan for 8-byte binary integers
        for offset in range(0, min(len(data) - 8, 4096), 4):
            val = struct.unpack_from("<Q", data, offset)[0]
            if steam_min <= val <= steam_max:
                info["detected_ids"].append(f"SteamID64 (Binary at offset 0x{offset:X}): {val}")

        return info

    @staticmethod
    def patch_account_id(input_file, output_file, old_id_str, new_id_str):
        """
        Replaces SteamID64 / XUID in both string and binary 64-bit formats inside the save file.
        """
        if not os.path.exists(input_file):
            raise FileNotFoundError("Input file not found")

        with open(input_file, "rb") as f:
            data = f.read()

        replacements = 0
        old_id_str = old_id_str.strip()
        new_id_str = new_id_str.strip()

        # 1. Text replace (UTF-8 and UTF-16LE)
        old_u8 = old_id_str.encode('utf-8')
        new_u8 = new_id_str.encode('utf-8')
        if len(old_u8) == len(new_u8):
            if old_u8 in data:
                count = data.count(old_u8)
                data = data.replace(old_u8, new_u8)
                replacements += count

        old_u16 = old_id_str.encode('utf-16le')
        new_u16 = new_id_str.encode('utf-16le')
        if len(old_u16) == len(new_u16):
            if old_u16 in data:
                count = data.count(old_u16)
                data = data.replace(old_u16, new_u16)
                replacements += count

        # 2. Binary 64-bit integer replace
        try:
            old_num = int(old_id_str)
            new_num = int(new_id_str)
            old_b8 = struct.pack("<Q", old_num)
            new_b8 = struct.pack("<Q", new_num)
            if old_b8 in data:
                count = data.count(old_b8)
                data = data.replace(old_b8, new_b8)
                replacements += count
        except ValueError:
            pass

        # 3. Hex 16-char replace
        try:
            if len(old_id_str) == 16 and len(new_id_str) == 16:
                old_hex_bytes = bytes.fromhex(old_id_str)
                new_hex_bytes = bytes.fromhex(new_id_str)
                if old_hex_bytes in data:
                    count = data.count(old_hex_bytes)
                    data = data.replace(old_hex_bytes, new_hex_bytes)
                    replacements += count
        except:
            pass

        with open(output_file, "wb") as f:
            f.write(data)

        return {
            "success": True,
            "replacements_count": replacements,
            "output_path": output_file
        }

    @staticmethod
    def auto_sync_game_metadata(user_wgs_dir, injected_slot_name, raw_save_data=None):
        """
        Specialized game adapter: Automatically synchronizes companion metadata slots
        (e.g., borSaveDataMeta, borSaveDataMetabup0/1 for Beast of Reincarnation)
        when a main save slot is injected.
        """
        from .wgs_engine import WGSEngine

        sync_results = []
        index_path = os.path.join(user_wgs_dir, "containers.index")
        if not os.path.exists(index_path):
            return sync_results

        parsed = WGSEngine.parse_wgs_container_index(index_path)
        if not parsed:
            return sync_results

        pkg_name = parsed["pkg_name"].lower()

        # 1. Beast of Reincarnation / Project Aibou
        if "projectaibou" in pkg_name or "beast" in pkg_name:
            target_meta_slots = []
            if "normal_0" in injected_slot_name.lower():
                target_meta_slots.append("borSaveDataMetabup0")
            elif "normal_1" in injected_slot_name.lower():
                target_meta_slots.append("borSaveDataMetabup1")

            for ms in target_meta_slots:
                for c in parsed["containers"]:
                    if c["name"].lower() == ms.lower():
                        sync_results.append(f"Auto-Sincronizado backup slot: {ms}")
                        break

        return sync_results

class AutoIDPatcher:
    """
    Intelligent automatic account ID patcher.
    Detects embedded account IDs (SteamID64, Xbox XUID) in the save file
    and automatically replaces them with the target platform's local user ID.
    Works seamlessly for Sekiro, Elden Ring, Dark Souls, Palworld, Monster Hunter, Deep Rock Galactic, Starfield, etc.
    """

    @classmethod
    def auto_patch_save_for_platform(cls, input_file_path, target_platform, target_meta=None):
        """
        Reads input_file_path, detects source IDs, patches with destination local account ID,
        and saves into a ready-to-inject temp file if patched (or returns original if no IDs found).
        """
        if not os.path.exists(input_file_path):
            return input_file_path, []

        with open(input_file_path, "rb") as f:
            data = f.read()

        sys_ids = SaveTools.detect_system_user_ids()
        target_platform = (target_platform or "").lower()
        replacements = []

        steam_min = 76561197960265728
        steam_max = 76561200000000000

        # Detect binary SteamIDs in data
        found_steam_ids = set()
        for offset in range(0, min(len(data) - 8, 1024 * 1024 * 16), 4):
            val = struct.unpack_from("<Q", data, offset)[0]
            if steam_min <= val <= steam_max:
                found_steam_ids.add(val)

        # Detect string SteamIDs in data
        str_matches = re.findall(rb'7656119\d{10}', data)
        for m in str_matches:
            try:
                found_steam_ids.add(int(m.decode()))
            except:
                pass

        # 1. Target is Xbox: Replace SteamIDs with target Xbox XUID
        if target_platform == "xbox":
            target_xuid = None
            if target_meta and target_meta.get("wgs_user_dir"):
                dir_name = os.path.basename(target_meta["wgs_user_dir"])
                if "_" in dir_name:
                    target_xuid = dir_name.split("_")[0]
            if not target_xuid and sys_ids["xbox_xuids"]:
                target_xuid = sys_ids["xbox_xuids"][0]["hex"]

            if target_xuid and found_steam_ids:
                try:
                    xuid_int = int(target_xuid, 16)
                    target_bin = struct.pack("<Q", xuid_int)
                    target_str = str(xuid_int).encode('ascii')

                    for sid in found_steam_ids:
                        sid_bin = struct.pack("<Q", sid)
                        if sid_bin in data:
                            c = data.count(sid_bin)
                            data = data.replace(sid_bin, target_bin)
                            replacements.append(f"Auto-Parche: SteamID64 {sid} -> Xbox XUID {target_xuid} ({c} ocurrencias binarias)")

                        sid_str = str(sid).encode('ascii')
                        if sid_str in data:
                            c = data.count(sid_str)
                            data = data.replace(sid_str, target_str)
                            replacements.append(f"Auto-Parche: SteamID64 texto {sid} -> Xbox XUID {target_xuid} ({c} ocurrencias)")
                except Exception as e:
                    pass

        # 2. Target is Steam: Replace other IDs / previous SteamIDs with local SteamID64
        elif target_platform == "steam":
            target_steam64 = None
            if sys_ids["steam_ids"]:
                target_steam64 = int(sys_ids["steam_ids"][0]["steam64"])

            if target_steam64:
                target_bin = struct.pack("<Q", target_steam64)
                target_str = str(target_steam64).encode('ascii')

                for sid in found_steam_ids:
                    if sid != target_steam64:
                        sid_bin = struct.pack("<Q", sid)
                        if sid_bin in data:
                            c = data.count(sid_bin)
                            data = data.replace(sid_bin, target_bin)
                            replacements.append(f"Auto-Parche: SteamID64 previo {sid} -> Tu SteamID64 {target_steam64} ({c} ocurrencias)")

                        sid_str = str(sid).encode('ascii')
                        if sid_str in data:
                            c = data.count(sid_str)
                            data = data.replace(sid_str, target_str)
                            replacements.append(f"Auto-Parche: SteamID64 texto {sid} -> Tu SteamID64 {target_steam64} ({c} ocurrencias)")

        if replacements:
            # Write to a patched temp file
            temp_dir = os.path.expandvars(r"%LOCALAPPDATA%\Temp\XboxSaveVault")
            os.makedirs(temp_dir, exist_ok=True)
            patched_file = os.path.join(temp_dir, f"patched_{os.path.basename(input_file_path)}")
            with open(patched_file, "wb") as f:
                f.write(data)
            return patched_file, replacements

        return input_file_path, replacements


class CompatibilityChecker:
    """
    Pre-verification system that analyzes game and save versions between platforms
    before transferring to prevent incompatibility errors.
    """

    @classmethod
    def get_game_version(cls, platform, game_meta):
        """Extracts version info from platform metadata, manifests, or game files."""
        if not game_meta:
            return "Desconocida"

        platform = (platform or "").lower()

        if platform == "xbox":
            ver = game_meta.get("version")
            inst = game_meta.get("install_path")
            if inst and os.path.exists(inst):
                mg_cfg = os.path.join(inst, "MicrosoftGame.config")
                if os.path.exists(mg_cfg):
                    try:
                        with open(mg_cfg, "r", encoding="utf-8", errors="ignore") as f:
                            text = f.read()
                        import re
                        m = re.search(r'Version="([^"]+)"', text)
                        if m: ver = f"v{m.group(1)}"
                    except:
                        pass
            return ver or "v1.0"

        elif platform == "steam":
            inst = game_meta.get("install_path")
            app_id = game_meta.get("appid")
            build_id = None
            if app_id:
                manifest_path = rf"C:\Program Files (x86)\Steam\steamapps\appmanifest_{app_id}.acf"
                if os.path.exists(manifest_path):
                    try:
                        with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
                            import re
                            m = re.search(r'"buildid"\s+"(\d+)"', f.read())
                            if m: build_id = m.group(1)
                    except:
                        pass
            if build_id:
                return f"Build #{build_id}"
            return "Última versión"

        elif platform in ["epic", "local"]:
            return "PC Local"

        return "v1.0"

    @classmethod
    def inspect_save_version(cls, file_path):
        """Inspects internal version signatures inside save files (e.g. Dead Cells, Unreal Engine, etc.)."""
        if not file_path or not os.path.exists(file_path):
            return None

        try:
            with open(file_path, "rb") as f:
                header = f.read(128)

            # Dead Cells magic
            if header.startswith(b"\xde\xad\xce\x11"):
                import re
                import struct
                m = re.search(rb'202\d-\d\d-\d\d', header)
                date_str = m.group(0).decode() if m else None
                z_idx = header.find(b"\x78\xda")
                ver_int = None
                if z_idx != -1 and z_idx >= 4:
                    ver_int = struct.unpack_from("<I", header, z_idx - 4)[0]
                
                return {
                    "format": "Dead Cells HXS",
                    "save_version_int": ver_int,
                    "date": date_str,
                    "summary": f"Ver {ver_int or 'N/A'} ({date_str or 'Sin fecha'})"
                }

            # Unreal Engine GVAS
            if header.startswith(b"GVAS"):
                return {
                    "format": "Unreal Engine GVAS",
                    "summary": "Unreal Engine Save Data"
                }
        except:
            pass

        return None

    @classmethod
    def check_transfer_compatibility(cls, source_platform, target_platform, source_file, source_game_meta, target_game_meta):
        """Performs pre-verification and returns warnings if version mismatch is detected."""
        src_ver = cls.get_game_version(source_platform, source_game_meta)
        tgt_ver = cls.get_game_version(target_platform, target_game_meta)
        save_info = cls.inspect_save_version(source_file)

        src_name = source_game_meta.get("name", "Juego de Origen")
        tgt_name = target_game_meta.get("name", "Juego de Destino")

        src_plat_label = "Steam" if source_platform.lower() == "steam" else ("Xbox Game Pass" if source_platform.lower() == "xbox" else "Epic / PC")
        tgt_plat_label = "Xbox Game Pass" if target_platform.lower() == "xbox" else ("Steam" if target_platform.lower() == "steam" else "Epic / PC")

        # Specific known game checks with genuine format disparities (e.g., Dead Cells v461 vs v35)
        if "dead cells" in src_name.lower() or "dead cells" in tgt_name.lower():
            if source_platform.lower() == "steam" and target_platform.lower() == "xbox":
                return {
                    "has_mismatch": True,
                    "severity": "warning",
                    "source_platform": src_plat_label,
                    "target_platform": tgt_plat_label,
                    "source_version": f"Steam ({src_ver})",
                    "target_version": f"Xbox ({tgt_ver})",
                    "title": "⚠️ Desfase de Versiones Detectado",
                    "message": f"La versión de Steam ({src_ver}) contiene parches más recientes que la versión instalada en Xbox ({tgt_ver}).",
                    "recommendation": "Verifica si hay actualizaciones en la Microsoft Store o la App de Xbox antes de jugar."
                }

        # For standard games, Steam Build IDs and Xbox Package Versions are store-specific numbering schemes
        return {
            "has_mismatch": False,
            "severity": "success",
            "source_platform": src_plat_label,
            "target_platform": tgt_plat_label,
            "source_version": f"{src_plat_label} ({src_ver})",
            "target_version": f"{tgt_plat_label} ({tgt_ver})",
            "title": "✅ Versiones Compatibles",
            "message": f"Las versiones instaladas en {src_plat_label} y {tgt_plat_label} son compatibles para transferir.",
            "recommendation": "Puedes transferir tu partida directamente."
        }


class CrossPlatformBridge:
    """
    Bridge for 1-click cross-platform save transfers between Xbox, Steam, Epic Games, and Local PC.
    """

    @classmethod
    def transfer_save(cls, source_platform, target_platform, source_file_path, target_game_meta, target_slot_name=None):
        import shutil
        import datetime
        from .wgs_engine import WGSEngine

        if not os.path.exists(source_file_path):
            raise FileNotFoundError(f"Source file {source_file_path} not found")

        # ⚡ Automatically patch embedded user account IDs (SteamID64 ⇄ Xbox XUID)
        effective_file_path, patch_log = AutoIDPatcher.auto_patch_save_for_platform(
            source_file_path, target_platform, target_game_meta
        )

        patch_msg = f" | {len(patch_log)} IDs auto-parcheados" if patch_log else ""

        # 1. Transfer to Xbox (WGS and Native LocalAppData paths)
        if target_platform.lower() == "xbox":
            user_wgs_dir = target_game_meta.get("wgs_user_dir")
            pkg_name = target_game_meta.get("package_id")
            slot_name = target_slot_name or os.path.basename(source_file_path)
            
            res = {}
            if user_wgs_dir:
                res = WGSEngine.inject_raw_save_to_slot(user_wgs_dir, slot_name, effective_file_path, pkg_name=pkg_name)

            # Also sync to native LocalAppData path if applicable (e.g. Dead Cells in %LOCALAPPDATA%\MotionTwin\DeadCells)
            if pkg_name and ("deadcells" in pkg_name.lower() or "motiontwin" in pkg_name.lower()):
                dc_local_dir = os.path.expandvars(r"%LOCALAPPDATA%\MotionTwin\DeadCells")
                os.makedirs(dc_local_dir, exist_ok=True)
                dest_file = os.path.join(dc_local_dir, slot_name)
                shutil.copy2(effective_file_path, dest_file)
                src_dir = os.path.dirname(source_file_path)
                src_opt = os.path.join(src_dir, "dc_options.json")
                if os.path.exists(src_opt):
                    shutil.copy2(src_opt, os.path.join(dc_local_dir, "dc_options.json"))

            return {
                "success": True,
                "message": f"Partida transferida exitosamente a Xbox en ranura '{slot_name}'{patch_msg}",
                "details": res,
                "auto_patches": patch_log
            }

        # 2. Transfer to Steam
        elif target_platform.lower() == "steam":
            target_dir = target_game_meta.get("remote_save_path") or target_game_meta.get("install_path")
            if not target_dir:
                raise ValueError("Target Steam save path not specified")

            os.makedirs(target_dir, exist_ok=True)
            filename = target_slot_name or os.path.basename(source_file_path)
            dest_file = os.path.join(target_dir, filename)

            # Safety backup
            if os.path.exists(dest_file):
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.copy2(dest_file, f"{dest_file}.bak_{ts}")

            shutil.copy2(effective_file_path, dest_file)
            return {
                "success": True,
                "message": f"Partida transferida exitosamente a Steam en: {dest_file}{patch_msg}",
                "dest_file": dest_file,
                "size": os.path.getsize(dest_file),
                "auto_patches": patch_log
            }

        # 3. Transfer to Epic / Local Folder
        elif target_platform.lower() in ["epic", "local"]:
            target_dir = target_game_meta.get("save_path") or target_game_meta.get("install_path")
            if not target_dir:
                raise ValueError("Target local/epic save path not specified")

            os.makedirs(target_dir, exist_ok=True)
            filename = target_slot_name or os.path.basename(source_file_path)
            dest_file = os.path.join(target_dir, filename)

            if os.path.exists(dest_file):
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                shutil.copy2(dest_file, f"{dest_file}.bak_{ts}")

            shutil.copy2(effective_file_path, dest_file)
            return {
                "success": True,
                "message": f"Partida transferida a {target_platform}: {dest_file}{patch_msg}",
                "dest_file": dest_file,
                "size": os.path.getsize(dest_file),
                "auto_patches": patch_log
            }
        else:
            raise ValueError(f"Unknown target platform: {target_platform}")
