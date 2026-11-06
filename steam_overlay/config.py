"""Local configuration storage and validation helpers."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from .constants import CONFIG_PATH, LEGACY_V11_APP_ID, LEGACY_V11_GAME_NAME

API_KEY_RE = re.compile(r"^[A-Fa-f0-9]{32}$")
STEAM_ID_RE = re.compile(r"^\d{17}$")
APP_ID_RE = re.compile(r"^\d{1,10}$")


def read_config(path: Path = CONFIG_PATH) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}

    # Backward compatibility for the original single-game v1.1 format,
    # which persisted api_key + steamid without an AppID.
    if data.get("api_key") and data.get("steamid") and not data.get("appid"):
        data["appid"] = LEGACY_V11_APP_ID
        data.setdefault("game_name", LEGACY_V11_GAME_NAME)
    return data


def write_config(data: dict, path: Path = CONFIG_PATH) -> None:
    """Atomically write local config; the Steam key remains plaintext."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        # Windows does not implement POSIX permission bits in the same way.
        pass
    os.replace(temp, path)


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


def validate_app_id(value: str | int) -> int:
    raw = str(value).strip()
    if not APP_ID_RE.fullmatch(raw):
        raise ValueError("Enter a valid Steam AppID or Steam Store URL.")
    appid = int(raw)
    if not 1 <= appid <= 4_294_967_295:
        raise ValueError("The Steam AppID is outside the valid range.")
    return appid


def parse_app_id(value: str | int) -> int:
    """Accept a numeric AppID or a Steam Store URL containing /app/<id>."""
    raw = str(value).strip()
    if APP_ID_RE.fullmatch(raw):
        return validate_app_id(raw)

    candidate = raw if "://" in raw else f"https://{raw}"
    parsed = urlparse(candidate)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in (
        "store.steampowered.com", "www.store.steampowered.com"
    ):
        raise ValueError("Use a numeric Steam AppID or a store.steampowered.com/app/... URL.")
    match = re.match(r"^/app/(\d+)(?:/|$)", parsed.path)
    if not match:
        raise ValueError("The Steam Store URL must point to a game page (/app/...).")
    if parsed.port not in (None, 80, 443) or parsed.username or parsed.password:
        raise ValueError("Use a normal Steam Store URL without login details or a custom port.")
    return validate_app_id(match.group(1))
