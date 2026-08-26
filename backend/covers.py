import os
import json
import urllib.request
import urllib.parse
import re

CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cover_cache.json")

# Popular aliases / direct Steam AppID mappings for quick 0ms resolution
KNOWN_GAME_MAP = {
    "fall guys": "1097150",
    "fallguys": "1097150",
    "kingdomcome2": "1771300",
    "kingdom come 2": "1771300",
    "kingdom come deliverance": "379430",
    "kingdomcome": "379430",
    "astral ascent": "1280930",
    "astralascent": "1280930",
    "carx street": "1114150",
    "carxstreet": "1114150",
    "nightmare shift": "3212180",
    "nightmareshift": "3212180",
    "mojang studios": "1672970",
    "minecraft": "1672970",
    "palworld": "1623730",
    "hollow knight": "367520",
    "hollowknight": "367520",
    "silksong": "1030300",
    "sekiro": "814380",
    "elden ring": "1245620",
    "eldenring": "1245620",
    "dark souls 3": "374320",
    "darksoulsiii": "374320",
    "dark souls 2": "335300",
    "dark souls remastered": "570940",
    "darksoulsremastered": "570940",
    "dead cells": "588650",
    "deadcells": "588650",
    "celeste": "504230",
    "dave the diver": "1868140",
    "davethediver": "1868140",
    "lies of p": "1627720",
    "liesofp": "1627720",
    "baldur's gate 3": "1086940",
    "baldurs gate 3": "1086940",
    "baldursgate3": "1086940",
    "starfield": "1716740",
    "cyberpunk 2077": "1091500",
    "cyberpunk": "1091500",
    "the witcher 3": "292030",
    "witcher 3": "292030",
    "witcher3": "292030",
    "monster hunter world": "582010",
    "monster hunter rise": "1446780",
    "mhrise": "1446780",
    "mhw": "582010",
    "grand theft auto v": "271590",
    "gta v": "271590",
    "gtav": "271590",
    "red dead redemption 2": "1174180",
    "rdr2": "1174180",
    "forza horizon 5": "1551360",
    "forzahorizon5": "1551360",
    "forza horizon 4": "1293830",
    "persona 5 royal": "1687950",
    "persona 3 reload": "2161700",
    "deep rock galactic": "548430",
    "deeprockgalactic": "548430",
    "hades": "1145360",
    "hades ii": "1145350",
    "hades 2": "1145350",
    "subnautica": "264710",
    "stardew valley": "413150",
    "terraria": "105600",
    "slay the spire": "646570",
    "slaythespire": "646570",
    "no mans sky": "275850",
    "sea of thieves": "1172620",
    "beast of reincarnation": "3154860",
    "graveyard keeper": "599140",
    "graveyardkeeper": "599140"
}

class GameCoverService:
    _cache = {}

    @classmethod
    def _load_cache(cls):
        if not cls._cache and os.path.exists(CACHE_FILE):
            try:
                with open(CACHE_FILE, "r", encoding="utf-8") as f:
                    cls._cache = json.load(f)
            except:
                cls._cache = {}

    @classmethod
    def _save_cache(cls):
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(cls._cache, f, ensure_ascii=False, indent=2)
        except:
            pass

    @classmethod
    def clean_name(cls, name):
        if not name:
            return ""
        # Remove noisy suffixes and camelCase separation
        s = name
        s = re.sub(r"(?i)(Saved Games|PC Saved Games|LocalLow|AppData|Saves|_|v\d+)", " ", s)
        s = re.sub(r"([a-z])([A-Z])", r"\1 \2", s)
        s = re.sub(r"[^\w\s\:\-\'\&]", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @classmethod
    def get_cover(cls, game_name, app_id=None):
        """
        Resolves the game header/cover URL.
        1. If app_id provided -> direct Steam CDN header
        2. Check memory & file cache
        3. Check known alias dictionary
        4. Query Steam Store Search API (with exact match prioritization)
        """
        if app_id and str(app_id).isdigit():
            return f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"

        if not game_name:
            return None

        cls._load_cache()

        norm_key = cls.clean_name(game_name).lower()
        if not norm_key:
            return None

        # Check Cache
        if norm_key in cls._cache and cls._cache[norm_key]:
            return cls._cache[norm_key]

        # Check Known Aliases
        if norm_key in KNOWN_GAME_MAP:
            aid = KNOWN_GAME_MAP[norm_key]
            url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg"
            cls._cache[norm_key] = url
            cls._save_cache()
            return url

        for alias_k, aid in KNOWN_GAME_MAP.items():
            if alias_k in norm_key or norm_key in alias_k:
                url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{aid}/header.jpg"
                cls._cache[norm_key] = url
                cls._save_cache()
                return url

        # Online Query to Steam Store Search
        try:
            search_term = cls.clean_name(game_name)
            encoded = urllib.parse.quote(search_term)
            query_url = f"https://store.steampowered.com/api/storesearch/?term={encoded}&l=spanish&cc=US"
            req = urllib.request.Request(query_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            
            with urllib.request.urlopen(req, timeout=2.5) as res:
                data = json.loads(res.read().decode("utf-8", errors="ignore"))
                items = data.get("items", [])
                if items:
                    st_lower = search_term.lower().strip()
                    target_id = None
                    # 1. Exact match prioritization
                    for it in items:
                        if it.get("name", "").lower().strip() == st_lower:
                            target_id = it.get("id")
                            break
                    # 2. Prefix match
                    if not target_id:
                        for it in items:
                            if it.get("name", "").lower().startswith(st_lower):
                                target_id = it.get("id")
                                break
                    # 3. Fallback to first item
                    if not target_id:
                        target_id = items[0].get("id")

                    if target_id:
                        cover_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{target_id}/header.jpg"
                        cls._cache[norm_key] = cover_url
                        cls._save_cache()
                        return cover_url
        except Exception:
            pass

        # If not found, cache empty to prevent repeating slow queries
        cls._cache[norm_key] = None
        cls._save_cache()
        return None
