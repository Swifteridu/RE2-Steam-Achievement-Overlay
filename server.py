#!/usr/bin/env python3
"""Local Steam achievement bridge for the Resident Evil 2 OBS overlay.

The Steam Web API key stays in config.json on this PC. The HTTP server listens
on IPv4 loopback only and accepts setup/refresh requests from its own origin.
Only Python's standard library is required.
"""
from __future__ import annotations

import json
import os
import re
import socket
import threading
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
CONFIG_PATH = ROOT / "config.json"
HOST = "127.0.0.1"
PORT = int(os.environ.get("RE2_OVERLAY_PORT", "8765"))
APP_ID = 883710  # Resident Evil 2 (2019)
POLL_SECONDS = 30
MAX_BACKOFF_SECONDS = 300
SCHEMA_CACHE_SECONDS = 6 * 60 * 60
MAX_RESPONSE_BYTES = 1_000_000
MAX_REQUEST_BYTES = 20_000
STEAM_API = "https://api.steampowered.com"
API_KEY_RE = re.compile(r"^[A-Fa-f0-9]{32}$")
STEAM_ID_RE = re.compile(r"^\d{17}$")

cache_lock = threading.RLock()
refresh_lock = threading.Lock()
stop_event = threading.Event()
refresh_event = threading.Event()

cache: dict = {
    "configured": False,
    "connected": False,
    "status": "setup_required",
    "stale": False,
    "error": "Connect your Steam account in the setup page.",
    "game": "Resident Evil 2",
    "appid": APP_ID,
    "steamid": None,
    "total": 44,
    "unlocked": 0,
    "achievements": [],
    "last_updated": None,
    "new_unlock": None,
}
last_unlocks: set[str] = set()
last_steamid: str | None = None
schema_cache: dict = {"api_key": None, "expires_at": 0.0, "achievements": None}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_config() -> dict:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_config(data: dict) -> None:
    """Replace the config atomically so an interrupted write cannot corrupt it."""
    temp = CONFIG_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        # Effective on POSIX. Windows file permissions remain those of the user
        # account running the overlay; do not treat this as encryption.
        os.chmod(temp, 0o600)
    except OSError:
        pass
    os.replace(temp, CONFIG_PATH)


def validate_api_key(api_key: str) -> str:
    value = str(api_key).strip()
    if not API_KEY_RE.fullmatch(value):
        raise ValueError("Enter a valid 32-character hexadecimal Steam Web API key.")
    return value


def validate_steam_id(steamid: str) -> str:
    value = str(steamid).strip()
    if not STEAM_ID_RE.fullmatch(value):
        raise ValueError("The Steam profile did not resolve to a valid 17-digit SteamID64.")
    return value


def steam_get(path: str, params: dict) -> dict:
    url = f"{STEAM_API}/{path}?{urlencode(params)}"
    req = Request(url, headers={"User-Agent": "RE2-OBS-Achievement-Overlay/1.1"})
    try:
        with urlopen(req, timeout=15) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        # Never include the request URL: it contains the private API key.
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


def normalize_steam_id(profile_input: str, api_key: str) -> str:
    """Resolve a SteamID64 or a Steam Community profile URL/vanity name."""
    value = str(profile_input).strip()
    if STEAM_ID_RE.fullmatch(value):
        return value

    candidate = value if "://" in value else f"https://{value}"
    parsed = urlparse(candidate)

    # A pasted profile URL must actually belong to Steam Community. This avoids
    # treating arbitrary third-party hosts as valid vanity profile URLs.
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Use a Steam Community profile URL or a 17-digit SteamID64.")
    if parsed.hostname and parsed.hostname.lower() not in ("steamcommunity.com", "www.steamcommunity.com"):
        # Still permit a bare vanity name such as "mySteamName".
        if "://" in value or "/" in value or "." in value:
            raise ValueError("The profile URL must use steamcommunity.com.")
        vanity = value
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", vanity):
            raise ValueError("Enter a valid Steam profile URL, vanity name, or SteamID64.")
        return resolve_vanity(vanity, api_key)
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
    return resolve_vanity(vanity, api_key)


def resolve_vanity(vanity: str, api_key: str) -> str:
    payload = steam_get("ISteamUser/ResolveVanityURL/v1/", {
        "key": api_key,
        "vanityurl": vanity,
    })
    response = payload.get("response", {})
    if not isinstance(response, dict) or response.get("success") != 1 or not response.get("steamid"):
        raise RuntimeError("Steam could not resolve that profile. Check the URL or use your SteamID64.")
    return validate_steam_id(str(response["steamid"]))


def _get_schema(api_key: str) -> list[dict]:
    now = time.monotonic()
    with cache_lock:
        if (schema_cache["api_key"] == api_key
                and schema_cache["expires_at"] > now
                and isinstance(schema_cache["achievements"], list)):
            return schema_cache["achievements"]

    payload = steam_get("ISteamUserStats/GetSchemaForGame/v2/", {
        "key": api_key,
        "appid": APP_ID,
        "l": "english",
    })
    game = payload.get("game", {})
    available = game.get("availableGameStats", {}) if isinstance(game, dict) else {}
    schema = available.get("achievements") if isinstance(available, dict) else None
    if not isinstance(schema, list) or not schema:
        raise RuntimeError("Steam did not return the game's achievement list.")

    # Store only the achievement schema, not the API response or credentials.
    with cache_lock:
        schema_cache.update({
            "api_key": api_key,
            "expires_at": time.monotonic() + SCHEMA_CACHE_SECONDS,
            "achievements": schema,
        })
    return schema


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def fetch_steam_data(config: dict) -> dict:
    api_key = validate_api_key(config.get("api_key", ""))
    steamid = validate_steam_id(config.get("steamid", ""))
    schema = _get_schema(api_key)

    player_payload = steam_get("ISteamUserStats/GetPlayerAchievements/v1/", {
        "key": api_key,
        "steamid": steamid,
        "appid": APP_ID,
        "l": "english",
    })
    player = player_payload.get("playerstats", {})
    player_achievements = player.get("achievements") if isinstance(player, dict) else None

    if (not isinstance(player, dict) or player.get("success") in (False, 0)
            or not isinstance(player_achievements, list)):
        detail = player.get("error") if isinstance(player, dict) else None
        if detail:
            raise RuntimeError(str(detail))
        raise RuntimeError("Steam could not read this account's achievements. Check Game details privacy settings.")

    player_by_name = {
        str(item.get("apiname")): item
        for item in player_achievements
        if isinstance(item, dict) and item.get("apiname")
    }

    combined = []
    seen_api_names: set[str] = set()
    for item in schema:
        if not isinstance(item, dict):
            continue
        api_name = str(item.get("name", "")).strip()
        if not api_name or api_name in seen_api_names:
            continue
        seen_api_names.add(api_name)
        player_item = player_by_name.get(api_name, {})
        achieved = _as_int(player_item.get("achieved"), 0) == 1
        unlocktime = max(0, _as_int(player_item.get("unlocktime"), 0))
        combined.append({
            "api_name": api_name,
            "name": str(item.get("displayName") or api_name),
            "description": str(item.get("description") or ""),
            "unlocked": achieved,
            "unlocktime": unlocktime,
            "icon": str(item.get("icon") or ""),
            "icon_gray": str(item.get("icongray") or ""),
            "hidden": _as_int(item.get("hidden"), 0) == 1,
        })

    if not combined:
        raise RuntimeError("Steam returned an empty achievement list for this game.")

    combined.sort(key=lambda item: (
        not item["unlocked"],
        -(item["unlocktime"] or 0),
        item["name"].casefold(),
    ))
    unlocked_names = {item["api_name"] for item in combined if item["unlocked"]}
    return {
        "configured": True,
        "connected": True,
        "status": "connected",
        "stale": False,
        "error": None,
        "game": "Resident Evil 2",
        "appid": APP_ID,
        "steamid": steamid,
        "total": len(combined),
        "unlocked": len(unlocked_names),
        "achievements": combined,
        "last_updated": now_iso(),
        "new_unlock": None,
        "_unlocked_names": unlocked_names,
    }


def publish_fresh_data(fresh: dict) -> None:
    """Publish a successful response and detect unlocks for the same account."""
    global cache, last_unlocks, last_steamid
    unlocked_names = fresh.pop("_unlocked_names", set())
    steamid = fresh.get("steamid")

    with cache_lock:
        same_account = bool(last_steamid and last_steamid == steamid)
        newly_unlocked = unlocked_names - last_unlocks if same_account else set()
        if newly_unlocked:
            unlocked_api_name = next(
                (item["api_name"] for item in fresh["achievements"]
                 if item["api_name"] in newly_unlocked),
                None,
            )
            new_achievement = next(
                (item for item in fresh["achievements"] if item["api_name"] == unlocked_api_name),
                None,
            )
            if new_achievement:
                fresh["new_unlock"] = {
                    "id": str(uuid.uuid4()),
                    "name": new_achievement["name"],
                    "description": new_achievement["description"],
                    "icon": new_achievement["icon"],
                }
        elif same_account:
            # Keep the last event available until another event supersedes it;
            # the overlay's event ID prevents it from displaying repeatedly.
            fresh["new_unlock"] = cache.get("new_unlock")

        cache = fresh
        last_unlocks = set(unlocked_names)
        last_steamid = steamid


def set_setup_required() -> None:
    global last_unlocks, last_steamid
    with cache_lock:
        cache.update({
            "configured": False,
            "connected": False,
            "status": "setup_required",
            "stale": False,
            "error": "Connect your Steam account in the setup page.",
            "steamid": None,
            "last_updated": None,
            "new_unlock": None,
            "achievements": [],
            "total": 44,
            "unlocked": 0,
        })
        last_unlocks = set()
        last_steamid = None


def record_refresh_error(message: str, configured: bool = True) -> None:
    """Keep the last good data, marking it stale instead of hiding it."""
    with cache_lock:
        has_last_good_data = bool(cache.get("achievements"))
        cache.update({
            "configured": configured,
            "connected": has_last_good_data,
            "status": "stale" if has_last_good_data else "error",
            "stale": has_last_good_data,
            "error": message,
        })


def refresh() -> bool:
    # Read the config only after acquiring the lock. Otherwise, a refresh that
    # started before an account change could later publish the old account data.
    with refresh_lock:
        config = read_config()
        if not config.get("api_key") or not config.get("steamid"):
            set_setup_required()
            return False
        try:
            fresh = fetch_steam_data(config)
            publish_fresh_data(fresh)
            return True
        except Exception as exc:
            message = str(exc)
            if "achievement" in message.lower() or "profile" in message.lower() or "user stats" in message.lower():
                message += " Check that your Steam profile and Game details are set to Public."
            record_refresh_error(message)
            return False


def connect_steam(api_key: str, profile: str) -> tuple[bool, str]:
    """Validate a candidate account before replacing the saved configuration."""
    api_key = validate_api_key(api_key)
    steamid = normalize_steam_id(profile, api_key)
    candidate = {"api_key": api_key, "steamid": steamid}

    with refresh_lock:
        fresh = fetch_steam_data(candidate)
        write_config(candidate)
        # A new or changed account establishes a baseline and does not emit an
        # unlock notification for achievements the player already owns.
        global last_unlocks, last_steamid
        with cache_lock:
            if last_steamid != steamid:
                last_unlocks = set()
                last_steamid = None
                fresh["new_unlock"] = None
        publish_fresh_data(fresh)

    return True, "Steam connected. Your achievements have loaded."


def background_refresher() -> None:
    delay = 1
    while not stop_event.is_set():
        success = refresh()
        if success:
            delay = POLL_SECONDS
        else:
            delay = min(MAX_BACKOFF_SECONDS, max(POLL_SECONDS, delay * 2))
        # Manual refreshes wake this loop rather than waiting for the backoff.
        refresh_event.wait(delay)
        refresh_event.clear()


def expected_host() -> str:
    return f"{HOST}:{PORT}"


def add_security_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
    )


def send_json(handler: BaseHTTPRequestHandler, obj: dict, status: int = 200) -> None:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    add_security_headers(handler)
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        pass


class LocalThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


class Handler(BaseHTTPRequestHandler):
    server_version = "RE2Overlay/1.1"
    sys_version = ""

    def log_request(self, code="-", size="-") -> None:
        # Log only the path, never query strings or submitted request bodies.
        path = urlparse(self.path).path
        print(f"[{self.log_date_time_string()}] {self.client_address[0]} {self.command} {path} {code}")

    def _check_host(self) -> bool:
        if self.headers.get("Host", "").lower() != expected_host().lower():
            send_json(self, {"ok": False, "error": "Requests must use the local overlay address."}, 403)
            return False
        return True

    def _check_same_origin(self) -> bool:
        if self.headers.get("Origin") != f"http://{expected_host()}":
            send_json(self, {"ok": False, "error": "This action must be submitted from the local overlay setup page."}, 403)
            return False
        return True

    def do_GET(self) -> None:
        if not self._check_host():
            return
        path = urlparse(self.path).path
        if path in ("/", "/setup"):
            self.serve_file(STATIC / "setup.html", "text/html; charset=utf-8")
        elif path == "/overlay":
            self.serve_file(STATIC / "overlay.html", "text/html; charset=utf-8")
        elif path == "/api/status":
            cfg = read_config()
            with cache_lock:
                result = {
                    "configured": bool(cfg.get("api_key") and cfg.get("steamid")),
                    "connected": cache.get("connected", False),
                    "status": cache.get("status"),
                    "stale": cache.get("stale", False),
                    "error": cache.get("error"),
                    "last_updated": cache.get("last_updated"),
                    "steamid": cache.get("steamid"),
                    "total": cache.get("total", 44),
                    "unlocked": cache.get("unlocked", 0),
                }
            send_json(self, result)
        elif path == "/api/achievements":
            with cache_lock:
                result = dict(cache)
            send_json(self, result)
        elif path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
        else:
            self.send_error(404)

    def do_POST(self) -> None:
        if not self._check_host() or not self._check_same_origin():
            return

        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            send_json(self, {"ok": False, "error": "Content-Type must be application/json."}, 415)
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 1:
            send_json(self, {"ok": False, "error": "A JSON request body is required."}, 400)
            return
        if length > MAX_REQUEST_BYTES:
            send_json(self, {"ok": False, "error": "Request too large."}, 413)
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            send_json(self, {"ok": False, "error": "Invalid JSON."}, 400)
            return
        if not isinstance(payload, dict):
            send_json(self, {"ok": False, "error": "The request must be a JSON object."}, 400)
            return

        path = urlparse(self.path).path
        if path == "/api/config":
            try:
                ok, message = connect_steam(payload.get("api_key", ""), payload.get("profile", ""))
                send_json(self, {"ok": ok, "message": message})
                refresh_event.set()
            except (ValueError, RuntimeError, OSError) as exc:
                send_json(self, {"ok": False, "error": str(exc)}, 400)
        elif path == "/api/refresh":
            success = refresh()
            with cache_lock:
                send_json(self, {"ok": success, "error": cache.get("error")})
            refresh_event.set()
        else:
            send_json(self, {"ok": False, "error": "Not found."}, 404)

    def serve_file(self, path: Path, content_type: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        add_security_headers(self)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main() -> None:
    if not 1 <= PORT <= 65535:
        raise SystemExit("RE2_OVERLAY_PORT must be between 1 and 65535.")

    print("=" * 60)
    print("Resident Evil 2 Achievement Overlay")
    print(f"Setup page:  http://{HOST}:{PORT}/")
    print(f"OBS source:  http://{HOST}:{PORT}/overlay")
    print("Keep this window open while streaming.")
    print("Press Ctrl+C to stop the local helper.")
    print("=" * 60)

    try:
        server = LocalThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        raise SystemExit(f"Could not start the local server on port {PORT}: {exc}") from None

    threading.Thread(target=background_refresher, name="SteamRefresh", daemon=True).start()
    timer = threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}/"))
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nStopping overlay helper...")
    finally:
        stop_event.set()
        refresh_event.set()
        server.server_close()


if __name__ == "__main__":
    main()
