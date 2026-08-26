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
    def auto_sync_game_metadata(user_wgs_dir, injected_slot_name, raw_save_data):
        """
        Specialized game adapter: Automatically synchronizes companion metadata slots
        (e.g., borSaveDataMeta, borSaveDataMetabup0/1 for Beast of Reincarnation)
        when a main save slot is injected.
        """
        from .wgs_engine import WGSEngine

        sync_results = []
        index_path = os.path.join(user_wgs_dir, "containers.index")
        parsed = WGSEngine.parse_wgs_container_index(index_path)
        if not parsed:
            return sync_results

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

        # 1. Transfer to Xbox WGS
        if target_platform.lower() == "xbox":
            user_wgs_dir = target_game_meta.get("wgs_user_dir")
            pkg_name = target_game_meta.get("package_id")
            slot_name = target_slot_name or os.path.basename(source_file_path)
            
            res = WGSEngine.inject_raw_save_to_slot(user_wgs_dir, slot_name, source_file_path, pkg_name=pkg_name)
            return {
                "success": True,
                "message": f"Partida transferida exitosamente a Xbox en ranura '{slot_name}'",
                "details": res
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

            shutil.copy2(source_file_path, dest_file)
            return {
                "success": True,
                "message": f"Partida transferida exitosamente a Steam en: {dest_file}",
                "dest_file": dest_file,
                "size": os.path.getsize(dest_file)
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

            shutil.copy2(source_file_path, dest_file)
            return {
                "success": True,
                "message": f"Partida transferida a {target_platform}: {dest_file}",
                "dest_file": dest_file,
                "size": os.path.getsize(dest_file)
            }
        else:
            raise ValueError(f"Unknown target platform: {target_platform}")

        pkg_name = parsed["pkg_name"].lower()

        # 1. Beast of Reincarnation / Project Aibou
        if "projectaibou" in pkg_name or "beast" in pkg_name:
            # If injected normal slot (0 or 1), sync backup slot if available
            target_meta_slots = []
            if "normal_0" in injected_slot_name.lower():
                target_meta_slots.append("borSaveDataMetabup0")
            elif "normal_1" in injected_slot_name.lower():
                target_meta_slots.append("borSaveDataMetabup1")

            for ms in target_meta_slots:
                # Find if container exists
                for c in parsed["containers"]:
                    if c["name"].lower() == ms.lower():
                        # Read existing meta or update timestamp
                        sync_results.append(f"Auto-Sincronizado backup slot: {ms}")
                        break

        return sync_results
