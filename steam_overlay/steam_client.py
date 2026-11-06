"""Steam Web API, Store search and persistent achievement-schema caching."""
from __future__ import annotations

import json
import re
import socket
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

from .config import parse_app_id, validate_api_key, validate_app_id, validate_steam_id
from .constants import (
    CACHE_DIR,
    MAX_GAME_SEARCH_RESULTS,
    MAX_RESPONSE_BYTES,
    SCHEMA_CACHE_SECONDS,
    STEAM_API_BASE,
    STEAM_STORE_BASE,
)


class SteamClient:
    """Small, dependency-free Steam client with a per-AppID schema cache."""

    def __init__(self, cache_dir: Path = CACHE_DIR, opener=urlopen) -> None:
        self.cache_dir = Path(cache_dir)
        self.opener = opener
        self._schema_memory: dict[int, dict] = {}

    def _read_url(self, url: str, *, user_agent: str = "Swifteridu-Steam-Achievement-Overlay/1.4.0") -> dict:
        request = Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
        try:
            with self.opener(request, timeout=15) as response:
                raw = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            # URLs may contain the Steam API key; never include them in errors/logs.
            raise RuntimeError(f"Steam returned HTTP {exc.code}.") from None
        except (TimeoutError, socket.timeout):
            raise RuntimeError("Steam did not respond in time. Try again shortly.") from None
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, (TimeoutError, socket.timeout)):
                raise RuntimeError("Steam did not respond in time. Try again shortly.") from None
            raise RuntimeError("Could not reach Steam. Check your internet connection.") from None
        except OSError:
            raise RuntimeError("A network error occurred while contacting Steam.") from None

        if len(raw) > MAX_RESPONSE_BYTES:
            raise RuntimeError("Steam returned an unexpectedly large response.")
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RuntimeError("Steam returned an unreadable response.") from None
        if not isinstance(payload, dict):
            raise RuntimeError("Steam returned an unexpected response.")
        return payload

    def steam_get(self, path: str, params: dict) -> dict:
        return self._read_url(f"{STEAM_API_BASE}/{path}?{urlencode(params)}")

    def store_get(self, path: str, params: dict) -> dict:
        return self._read_url(f"{STEAM_STORE_BASE}/{path}?{urlencode(params)}")

    def resolve_vanity(self, vanity: str, api_key: str) -> str:
        payload = self.steam_get("ISteamUser/ResolveVanityURL/v1/", {
            "key": api_key,
            "vanityurl": vanity,
        })
        response = payload.get("response", {})
        if not isinstance(response, dict) or response.get("success") != 1 or not response.get("steamid"):
            raise RuntimeError("Steam could not resolve that profile. Check the URL or use your SteamID64.")
        return validate_steam_id(str(response["steamid"]))

    def normalize_steam_id(self, profile_input: str, api_key: str) -> str:
        value = str(profile_input).strip()
        if re.fullmatch(r"\d{17}", value):
            return validate_steam_id(value)

        candidate = value if "://" in value else f"https://{value}"
        parsed = urlparse(candidate)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("Use a Steam Community profile URL or a 17-digit SteamID64.")
        if parsed.hostname and parsed.hostname.lower() not in (
            "steamcommunity.com", "www.steamcommunity.com"
        ):
            if "://" in value or "/" in value or "." in value:
                raise ValueError("The profile URL must use steamcommunity.com.")
            vanity = value
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", vanity):
                raise ValueError("Enter a valid Steam profile URL, vanity name, or SteamID64.")
            return self.resolve_vanity(vanity, api_key)
        if parsed.port not in (None, 80, 443) or parsed.username or parsed.password:
            raise ValueError("Use a normal Steam Community profile URL without login details or a custom port.")

        parts = [unquote(part) for part in parsed.path.split("/") if part]
        if len(parts) == 2 and parts[0].lower() == "profiles":
            return validate_steam_id(parts[1])
        if len(parts) == 2 and parts[0].lower() == "id":
            vanity = parts[1]
        elif len(parts) == 1 and "://" not in value and "/" not in value:
            vanity = parts[0]
        else:
            raise ValueError("Enter a SteamID64 or a Steam profile URL (/id/... or /profiles/...).")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", vanity):
            raise ValueError("The Steam vanity name contains unsupported characters.")
        return self.resolve_vanity(vanity, api_key)

    def search_store_games(self, query: str) -> list[dict]:
        """Search the Steam Store and return up to three full games only.

        Steam's lightweight store-search endpoint can return DLC and other app
        types alongside base games. Verify each candidate with appdetails and
        accept only entries whose Store metadata explicitly reports type=game.
        Unknown or unavailable types are skipped rather than treated as games.
        """
        term = str(query).strip()
        if len(term) < 2:
            raise ValueError("Enter at least two characters to search for a game.")
        if len(term) > 80:
            raise ValueError("The game search is limited to 80 characters.")

        payload = self.store_get("api/storesearch/", {
            "term": term, "l": "english", "cc": "US",
        })
        items = payload.get("items", [])
        if not isinstance(items, list):
            raise RuntimeError("Steam returned an unexpected game search response.")

        candidates = []
        seen_appids: set[int] = set()
        for item in items:
            if not isinstance(item, dict) or not item.get("id") or not item.get("name"):
                continue
            # Store search can include package results (type=sub); these are not
            # individual game AppIDs and should never be selectable here.
            if item.get("type") not in (None, "app"):
                continue
            try:
                appid = validate_app_id(item["id"])
            except ValueError:
                continue
            if appid in seen_appids:
                continue
            seen_appids.add(appid)
            candidates.append((appid, item))

        if not candidates:
            return []

        # AppDetails exposes the actual Store item type (game, dlc, demo,
        # music, software, etc.). Verify candidates individually: Steam's
        # public appdetails endpoint has inconsistent multi-AppID behavior.
        # Only an explicit type="game" is selectable; unknown types are skipped.
        results = []
        for appid, item in candidates:
            detail_payload = self.store_get("api/appdetails/", {
                "appids": appid,
                "l": "english",
                "cc": "US",
                "filters": "basic",
            })
            entry = detail_payload.get(str(appid), {})
            details = entry.get("data") if isinstance(entry, dict) and entry.get("success") else None
            if not isinstance(details, dict) or str(details.get("type", "")).casefold() != "game":
                continue
            results.append({
                "appid": appid,
                "name": str(details.get("name") or item["name"])[:120],
                "image": str(item.get("tiny_image") or details.get("header_image") or ""),
            })
            if len(results) >= MAX_GAME_SEARCH_RESULTS:
                break
        return results

    def _schema_cache_path(self, appid: int) -> Path:
        return self.cache_dir / f"schema_{appid}.json"

    def _load_disk_schema(self, appid: int) -> dict | None:
        try:
            payload = json.loads(self._schema_cache_path(appid).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if (isinstance(payload, dict) and payload.get("appid") == appid
                and isinstance(payload.get("achievements"), list) and payload["achievements"]):
            return payload
        return None

    def _save_disk_schema(self, appid: int, game_name: str | None, achievements: list[dict]) -> None:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        path = self._schema_cache_path(appid)
        temp = path.with_suffix(".tmp")
        payload = {
            "appid": appid,
            "game_name": game_name or "",
            "fetched_at": time.time(),
            "achievements": achievements,
        }
        temp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        temp.replace(path)

    def get_schema(self, appid: int, api_key: str) -> tuple[str | None, list[dict]]:
        now = time.time()
        memory = self._schema_memory.get(appid)
        if memory and memory.get("expires_at", 0) > now:
            return memory.get("game_name"), memory["achievements"]

        disk = self._load_disk_schema(appid)
        if disk and now - float(disk.get("fetched_at", 0)) < SCHEMA_CACHE_SECONDS:
            self._schema_memory[appid] = {
                "game_name": disk.get("game_name"),
                "achievements": disk["achievements"],
                "expires_at": now + SCHEMA_CACHE_SECONDS,
            }
            return disk.get("game_name"), disk["achievements"]

        try:
            payload = self.steam_get("ISteamUserStats/GetSchemaForGame/v2/", {
                "key": api_key, "appid": appid, "l": "english",
            })
            game = payload.get("game", {})
            available = game.get("availableGameStats", {}) if isinstance(game, dict) else {}
            schema = available.get("achievements") if isinstance(available, dict) else None
            if not isinstance(schema, list) or not schema:
                raise RuntimeError(
                    "Steam does not expose an achievement schema for this game. "
                    "The game may not support Steam achievements, or its developer may not publish the data."
                )
            game_name = str(game.get("gameName") or "").strip() or None
            try:
                self._save_disk_schema(appid, game_name, schema)
            except OSError:
                # Caching is optional; it must not prevent a successful connection.
                pass
            self._schema_memory[appid] = {
                "game_name": game_name,
                "achievements": schema,
                "expires_at": time.time() + SCHEMA_CACHE_SECONDS,
            }
            return game_name, schema
        except Exception:
            # A previously cached schema can still be used during a temporary
            # schema endpoint outage. Player stats are validated separately.
            if disk and disk.get("achievements"):
                self._schema_memory[appid] = {
                    "game_name": disk.get("game_name"),
                    "achievements": disk["achievements"],
                    "expires_at": time.time() + 60,
                }
                return disk.get("game_name"), disk["achievements"]
            raise

    def fetch_achievement_data(self, config: dict) -> dict:
        api_key = validate_api_key(config.get("api_key", ""))
        steamid = validate_steam_id(config.get("steamid", ""))
        appid = validate_app_id(config.get("appid", 0))
        schema_game_name, schema = self.get_schema(appid, api_key)

        player_payload = self.steam_get("ISteamUserStats/GetPlayerAchievements/v1/", {
            "key": api_key, "steamid": steamid, "appid": appid, "l": "english",
        })
        player = player_payload.get("playerstats", {})
        player_achievements = player.get("achievements") if isinstance(player, dict) else None
        if (not isinstance(player, dict) or player.get("success") in (False, 0)
                or not isinstance(player_achievements, list)):
            detail = player.get("error") if isinstance(player, dict) else None
            if detail:
                raise RuntimeError(str(detail))
            raise RuntimeError(
                "Steam could not read this player's achievements. Check Game details privacy "
                "settings and confirm the account owns/has access to the game."
            )

        player_by_name = {
            str(item.get("apiname")): item for item in player_achievements
            if isinstance(item, dict) and item.get("apiname")
        }
        combined: list[dict] = []
        seen: set[str] = set()
        for item in schema:
            if not isinstance(item, dict):
                continue
            api_name = str(item.get("name", "")).strip()
            if not api_name or api_name in seen:
                continue
            seen.add(api_name)
            player_item = player_by_name.get(api_name, {})
            unlocked = _as_int(player_item.get("achieved"), 0) == 1
            unlocktime = max(0, _as_int(player_item.get("unlocktime"), 0))
            combined.append({
                "api_name": api_name,
                "name": str(item.get("displayName") or api_name),
                "description": str(item.get("description") or ""),
                "unlocked": unlocked,
                "unlocktime": unlocktime,
                "icon": str(item.get("icon") or ""),
                "icon_gray": str(item.get("icongray") or ""),
                "hidden": _as_int(item.get("hidden"), 0) == 1,
            })
        if not combined:
            raise RuntimeError("Steam returned an empty achievement list for this game.")

        combined.sort(key=lambda item: (
            not item["unlocked"], -(item["unlocktime"] or 0), item["name"].casefold()
        ))
        unlocked_names = {item["api_name"] for item in combined if item["unlocked"]}
        game_name = str(config.get("game_name") or schema_game_name or f"Steam App {appid}").strip()
        return {
            "configured": True,
            "connected": True,
            "status": "connected",
            "stale": False,
            "error": None,
            "game_name": game_name[:120],
            "appid": appid,
            "steamid": steamid,
            "total": len(combined),
            "unlocked": len(unlocked_names),
            "achievements": combined,
            "last_updated": now_iso(),
            "new_unlocks": [],
            "_unlocked_names": unlocked_names,
        }


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
