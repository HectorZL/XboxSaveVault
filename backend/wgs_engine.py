import os
import sys
import struct
import io
import shutil
import zipfile
import datetime
import json
import uuid

def parse_guid(guid_bytes):
    if len(guid_bytes) < 16:
        return ""
    d1, d2, d3, d4 = struct.unpack("<IHH8s", guid_bytes)
    return f"{d1:08X}{d2:04X}{d3:04X}{d4.hex().upper()}"

def format_guid_to_bytes(guid_str):
    """Converts 32-hex GUID string back to 16 binary bytes in Windows GUID layout."""
    clean = guid_str.replace("-", "").strip()
    if len(clean) != 32:
        clean = clean.ljust(32, '0')[:32]
    d1 = bytes.fromhex(clean[0:8])[::-1]
    d2 = bytes.fromhex(clean[8:12])[::-1]
    d3 = bytes.fromhex(clean[12:16])[::-1]
    d4 = bytes.fromhex(clean[16:32])
    return d1 + d2 + d3 + d4

def filetime_to_dt(ft):
    try:
        us = (ft - 116444736000000000) // 10
        return datetime.datetime(1970, 1, 1) + datetime.timedelta(microseconds=us)
    except:
        return None

def dt_to_filetime(dt=None):
    if dt is None:
        dt = datetime.datetime.utcnow()
    diff = dt - datetime.datetime(1970, 1, 1)
    us = int(diff.total_seconds() * 1000000)
    return (us * 10) + 116444736000000000

class WGSEngine:
    """
    Parser, Extractor, and Injector for Microsoft Xbox Game Pass / Windows Gaming Services (WGS) saves.
    """

    @staticmethod
    def read_str_u16(stream):
        l_bytes = stream.read(4)
        if not l_bytes or len(l_bytes) < 4:
            return ""
        char_len = struct.unpack("<I", l_bytes)[0]
        return stream.read(char_len * 2).decode('utf-16le', errors='ignore')

    @staticmethod
    def write_str_u16(text):
        encoded = text.encode('utf-16le')
        char_len = len(text)
        return struct.pack("<I", char_len) + encoded

    @classmethod
    def parse_wgs_container_index(cls, index_path):
        """Parses containers.index file returning package header and container list."""
        if not os.path.exists(index_path):
            return None

        with open(index_path, "rb") as f:
            data = f.read()

        stream = io.BytesIO(data)
        if len(data) < 16:
            return None

        version, count = struct.unpack("<II", stream.read(8))
        flags = struct.unpack("<I", stream.read(4))[0]
        pkg_name = cls.read_str_u16(stream)
        filetime = struct.unpack("<Q", stream.read(8))[0]
        sync_flag = struct.unpack("<I", stream.read(4))[0]
        sync_id = cls.read_str_u16(stream)
        stream.read(8) # trailer bytes

        containers = []
        user_wgs_dir = os.path.dirname(index_path)

        for i in range(count):
            c_name = cls.read_str_u16(stream)
            c_cloud_id = cls.read_str_u16(stream)
            c_tag = cls.read_str_u16(stream)
            seq = struct.unpack("<B", stream.read(1))[0]
            c_flag = struct.unpack("<I", stream.read(4))[0]
            c_guid = parse_guid(stream.read(16))
            ft_val = struct.unpack("<Q", stream.read(8))[0]
            c_filetime = filetime_to_dt(ft_val)
            c_unk = struct.unpack("<Q", stream.read(8))[0]
            c_size = struct.unpack("<Q", stream.read(8))[0]

            # Container directory
            container_dir = os.path.join(user_wgs_dir, c_guid)
            meta_file = os.path.join(container_dir, f"container.{seq}")
            files = []
            
            if os.path.exists(meta_file):
                with open(meta_file, "rb") as mf:
                    mdata = mf.read()
                mstream = io.BytesIO(mdata)
                if len(mdata) >= 8:
                    mver, mcount = struct.unpack("<II", mstream.read(8))
                    for _ in range(mcount):
                        raw_filename = mstream.read(128).decode('utf-16le', errors='ignore').split('\x00')[0]
                        c_guid_inner = parse_guid(mstream.read(16))
                        blob_guid = parse_guid(mstream.read(16))
                        blob_path = os.path.join(container_dir, blob_guid)
                        blob_size = os.path.getsize(blob_path) if os.path.exists(blob_path) else 0
                        files.append({
                            "filename": raw_filename if raw_filename else "save_blob",
                            "blob_guid": blob_guid,
                            "blob_path": blob_path,
                            "size": blob_size
                        })

            containers.append({
                "index": i,
                "name": c_name,
                "cloud_id": c_cloud_id,
                "tag": c_tag,
                "seq": seq,
                "guid": c_guid,
                "flags": c_flag,
                "filetime": ft_val,
                "modified": c_filetime.strftime("%Y-%m-%d %H:%M:%S") if c_filetime else "Unknown",
                "size": c_size,
                "dir_path": container_dir,
                "meta_path": meta_file,
                "files": files
            })

        return {
            "version": version,
            "count": count,
            "flags": flags,
            "pkg_name": pkg_name,
            "filetime": filetime,
            "sync_flag": sync_flag,
            "sync_id": sync_id,
            "index_path": index_path,
            "containers": containers
        }

    @classmethod
    def export_raw_saves(cls, user_wgs_dir, dest_dir):
        """
        Extracts readable raw save files (.sav / binary files) from Xbox WGS containers.
        Useful for copying to Steam, editing, or converting.
        """
        index_path = os.path.join(user_wgs_dir, "containers.index")
        parsed = cls.parse_wgs_container_index(index_path)
        if not parsed:
            raise ValueError(f"No valid containers.index found in {user_wgs_dir}")

        os.makedirs(dest_dir, exist_ok=True)
        exported_files = []

        # Check for LocalCache saves if in package
        pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(user_wgs_dir)))
        local_cache_dir = os.path.join(pkg_root, "LocalCache", "Local")
        if os.path.exists(local_cache_dir):
            for lc_file in os.listdir(local_cache_dir):
                src = os.path.join(local_cache_dir, lc_file)
                if os.path.isfile(src):
                    dst = os.path.join(dest_dir, lc_file)
                    shutil.copy2(src, dst)
                    exported_files.append({
                        "name": lc_file,
                        "path": dst,
                        "size": os.path.getsize(dst),
                        "type": "LocalCache Configuration"
                    })

        for c in parsed["containers"]:
            c_name = c["name"]
            for f in c["files"]:
                blob_path = f["blob_path"]
                if os.path.exists(blob_path):
                    # Naming strategy:
                    # If container has a meaningful name like borSaveDataNormal_0, use that + .sav
                    # If file has filename like 'Save' or 'Config', name it accordingly
                    if f["filename"] == "Data" or not f["filename"]:
                        out_name = f"{c_name}.sav"
                    else:
                        out_name = f"{c_name}_{f['filename']}.sav" if c_name != f['filename'] else f"{f['filename']}.sav"

                    # Clean invalid chars
                    clean_name = "".join(ch for ch in out_name if ch.isalnum() or ch in "._- ")
                    dst_path = os.path.join(dest_dir, clean_name)
                    shutil.copy2(blob_path, dst_path)
                    exported_files.append({
                        "name": clean_name,
                        "path": dst_path,
                        "size": os.path.getsize(dst_path),
                        "container": c_name,
                        "slot": c["name"],
                        "type": "Game Save Slot"
                    })

        return {
            "success": True,
            "export_dir": dest_dir,
            "file_count": len(exported_files),
            "files": exported_files
        }

    @classmethod
    def create_full_xbox_backup(cls, user_wgs_dir, backup_zip_path, game_meta=None):
        """
        Creates a complete restorable ZIP backup of the Xbox WGS save directory and metadata.
        """
        if not os.path.exists(user_wgs_dir):
            raise FileNotFoundError(f"Directory {user_wgs_dir} not found")

        os.makedirs(os.path.dirname(os.path.abspath(backup_zip_path)), exist_ok=True)
        
        index_path = os.path.join(user_wgs_dir, "containers.index")
        parsed = cls.parse_wgs_container_index(index_path)

        manifest = {
            "tool": "Xbox Save Manager",
            "version": "1.0.0",
            "created_at": datetime.datetime.utcnow().isoformat(),
            "wgs_user_title_dir": os.path.basename(user_wgs_dir),
            "game_meta": game_meta or {},
            "parsed_summary": {
                "package_name": parsed["pkg_name"] if parsed else "Unknown",
                "sync_id": parsed["sync_id"] if parsed else "Unknown",
                "container_count": len(parsed["containers"]) if parsed else 0
            }
        }

        with zipfile.ZipFile(backup_zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            # Add manifest
            zf.writestr("backup_manifest.json", json.dumps(manifest, indent=2))

            # Add all files from user_wgs_dir
            for root, dirs, files in os.walk(user_wgs_dir):
                for file in files:
                    full_p = os.path.join(root, file)
                    rel_p = os.path.join("wgs_data", os.path.relpath(full_p, user_wgs_dir))
                    zf.write(full_p, rel_p)

            # Also include LocalCache files if available
            pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(user_wgs_dir)))
            local_cache_dir = os.path.join(pkg_root, "LocalCache", "Local")
            if os.path.exists(local_cache_dir):
                for root, dirs, files in os.walk(local_cache_dir):
                    for file in files:
                        full_p = os.path.join(root, file)
                        rel_p = os.path.join("local_cache", os.path.relpath(full_p, local_cache_dir))
                        zf.write(full_p, rel_p)

        return {
            "success": True,
            "backup_path": backup_zip_path,
            "size": os.path.getsize(backup_zip_path),
            "created_at": manifest["created_at"]
        }

    @classmethod
    def restore_full_xbox_backup(cls, backup_zip_path, target_wgs_user_dir, create_pre_backup=True):
        """
        Restores a full Xbox ZIP backup into target WGS directory with automatic safety backup.
        """
        if not os.path.exists(backup_zip_path):
            raise FileNotFoundError(f"Backup file {backup_zip_path} not found")

        # Create pre-restore safety backup
        safety_backup = None
        if create_pre_backup and os.path.exists(target_wgs_user_dir):
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safety_dir = os.path.join(os.path.expanduser("~"), "XboxSaveBackups", "Safety_PreRestore", ts)
            os.makedirs(safety_dir, exist_ok=True)
            safety_zip = os.path.join(safety_dir, f"pre_restore_{os.path.basename(target_wgs_user_dir)}.zip")
            cls.create_full_xbox_backup(target_wgs_user_dir, safety_zip)
            safety_backup = safety_zip

        # Extract backup
        with zipfile.ZipFile(backup_zip_path, 'r') as zf:
            namelist = zf.namelist()
            wgs_members = [m for m in namelist if m.startswith("wgs_data/")]
            local_cache_members = [m for m in namelist if m.startswith("local_cache/")]

            os.makedirs(target_wgs_user_dir, exist_ok=True)
            for m in wgs_members:
                rel = m[len("wgs_data/"):]
                if not rel: continue
                dest_file = os.path.join(target_wgs_user_dir, rel)
                if m.endswith("/"):
                    os.makedirs(dest_file, exist_ok=True)
                else:
                    os.makedirs(os.path.dirname(dest_file), exist_ok=True)
                    with zf.open(m) as src, open(dest_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)

            # Restore local cache if applicable
            pkg_root = os.path.dirname(os.path.dirname(os.path.dirname(target_wgs_user_dir)))
            local_cache_dir = os.path.join(pkg_root, "LocalCache", "Local")
            if local_cache_members and os.path.exists(os.path.dirname(local_cache_dir)):
                os.makedirs(local_cache_dir, exist_ok=True)
                for m in local_cache_members:
                    rel = m[len("local_cache/"):]
                    if not rel or m.endswith("/"): continue
                    dst_file = os.path.join(local_cache_dir, rel)
                    with zf.open(m) as src, open(dst_file, "wb") as dst:
                        shutil.copyfileobj(src, dst)

        return {
            "success": True,
            "target_dir": target_wgs_user_dir,
            "safety_backup": safety_backup,
            "restored_at": datetime.datetime.now().isoformat()
        }

    @classmethod
    def inject_raw_save_to_slot(cls, user_wgs_dir, container_name, raw_save_data_or_path):
        """
        Injects an external save file (.sav / raw binary) into a specific WGS container slot.
        Rebuilds blob file, updates container.<seq> and containers.index.
        """
        index_path = os.path.join(user_wgs_dir, "containers.index")
        parsed = cls.parse_wgs_container_index(index_path)
        if not parsed:
            raise ValueError("Invalid WGS containers.index")

        # Find matching container
        target_container = None
        for c in parsed["containers"]:
            if c["name"].lower() == container_name.lower() or c["guid"].lower() == container_name.lower():
                target_container = c
                break

        if not target_container:
            raise ValueError(f"Container slot '{container_name}' not found in WGS index")

        # Read new save data
        if isinstance(raw_save_data_or_path, str) and os.path.isfile(raw_save_data_or_path):
            with open(raw_save_data_or_path, "rb") as f:
                new_data = f.read()
        elif isinstance(raw_save_data_or_path, bytes):
            new_data = raw_save_data_or_path
        else:
            raise ValueError("raw_save_data_or_path must be a valid file path or bytes")

        new_size = len(new_data)
        container_dir = target_container["dir_path"]
        os.makedirs(container_dir, exist_ok=True)

        # Get existing blob or create a new blob GUID
        if target_container["files"]:
            blob_guid = target_container["files"][0]["blob_guid"]
            file_title = target_container["files"][0]["filename"]
        else:
            blob_guid = uuid.uuid4().hex.upper()
            file_title = "Data"

        blob_path = os.path.join(container_dir, blob_guid)
        with open(blob_path, "wb") as bf:
            bf.write(new_data)

        # Update container.<seq> file
        seq = target_container["seq"]
        meta_path = os.path.join(container_dir, f"container.{seq}")
        
        # Write container.<seq>
        # Header: uint32 version (4), uint32 count (1)
        # Entry: 128 bytes wchar filename, 16 bytes container GUID, 16 bytes blob GUID
        with open(meta_path, "wb") as mf:
            mf.write(struct.pack("<II", 4, 1))
            name_buf = file_title.encode('utf-16le').ljust(128, b'\x00')[:128]
            mf.write(name_buf)
            mf.write(format_guid_to_bytes(target_container["guid"]))
            mf.write(format_guid_to_bytes(blob_guid))

        # Re-write containers.index with updated timestamp and size
        now_ft = dt_to_filetime()
        target_container["size"] = new_size
        target_container["filetime"] = now_ft

        # Build new containers.index binary
        out_stream = io.BytesIO()
        out_stream.write(struct.pack("<II", parsed["version"], len(parsed["containers"])))
        out_stream.write(struct.pack("<I", parsed["flags"]))
        out_stream.write(cls.write_str_u16(parsed["pkg_name"]))
        out_stream.write(struct.pack("<Q", now_ft))
        out_stream.write(struct.pack("<I", parsed["sync_flag"]))
        out_stream.write(cls.write_str_u16(parsed["sync_id"]))
        out_stream.write(b'\x00' * 8) # trailer

        for c in parsed["containers"]:
            out_stream.write(cls.write_str_u16(c["name"]))
            out_stream.write(cls.write_str_u16(c["cloud_id"]))
            out_stream.write(cls.write_str_u16(c["tag"]))
            out_stream.write(struct.pack("<B", c["seq"]))
            out_stream.write(struct.pack("<I", c["flags"]))
            out_stream.write(format_guid_to_bytes(c["guid"]))
            out_stream.write(struct.pack("<Q", c["filetime"]))
            out_stream.write(struct.pack("<Q", 0)) # unknown
            out_stream.write(struct.pack("<Q", c["size"]))

        with open(index_path, "wb") as f:
            f.write(out_stream.getvalue())

        return {
            "success": True,
            "container": target_container["name"],
            "guid": target_container["guid"],
            "blob_guid": blob_guid,
            "new_size": new_size,
            "updated_at": datetime.datetime.now().isoformat()
        }
