"""Application service for account/game connection and achievement sync."""
from __future__ import annotations

import json
import threading
import uuid
from pathlib import Path

from .config import read_config, write_config, parse_app_id, validate_api_key
from .constants import (
    CONFIG_PATH,
    PINS_PATH,
    MAX_BACKOFF_SECONDS,
    POLL_SECONDS,
)
from .steam_client import SteamClient


class AchievementService:
    """Coordinates Steam data retrieval, cached state and unlock notifications."""

    def __init__(
        self,
        client: SteamClient | None = None,
        config_path: Path = CONFIG_PATH,
        pins_path: Path | None = None,
    ) -> None:
        self.client = client or SteamClient()
        self.config_path = Path(config_path)
        self.pins_path = Path(pins_path) if pins_path else Path(PINS_PATH)
        self._state_lock = threading.RLock()
        self._pins_lock = threading.RLock()
        self._refresh_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._refresh_event = threading.Event()
        self._last_scope: tuple[str, int] | None = None
        self._last_unlocks: set[str] = set()
        self._state: dict = {
            "configured": False,
            "connected": False,
            "status": "setup_required",
            "stale": False,
            "error": "Choose a Steam game and connect your account in the setup page.",
            "game_name": None,
            "appid": None,
            "steamid": None,
            "total": 0,
            "unlocked": 0,
            "achievements": [],
            "last_updated": None,
            "new_unlocks": [],
        }

    def snapshot(self) -> dict:
        with self._state_lock:
            # Return a detached snapshot so handlers cannot mutate live state.
            result = json.loads(json.dumps(self._state))
        pins = self.pins_snapshot()
        result["pinned_api_names"] = pins["api_names"]
        result["pinned_achievements"] = pins["achievements"]
        return result

    def _scope_key(self, steamid: str, appid: int) -> str:
        return f"{steamid}:{appid}"

    def _read_pins_document(self) -> dict:
        try:
            payload = json.loads(self.pins_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_pins_document(self, payload: dict) -> None:
        self.pins_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.pins_path.with_suffix(self.pins_path.suffix + ".tmp")
        temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            temp.chmod(0o600)
        except OSError:
            pass
        temp.replace(self.pins_path)

    def pins_snapshot(self) -> dict:
        with self._state_lock:
            steamid = self._state.get("steamid")
            appid = self._state.get("appid")
            achievements = list(self._state.get("achievements", []))
        if not steamid or not appid:
            return {"api_names": [], "achievements": []}

        key = self._scope_key(str(steamid), int(appid))
        with self._pins_lock:
            document = self._read_pins_document()
            saved = document.get(key, [])
        if not isinstance(saved, list):
            saved = []
        available = {item.get("api_name"): item for item in achievements if item.get("api_name")}
        names = [name for name in saved[:3] if isinstance(name, str) and name in available]
        return {
            "api_names": names,
            "achievements": [available[name] for name in names],
        }

    def set_pins(self, api_names) -> dict:
        if not isinstance(api_names, list):
            raise ValueError("Pinned achievements must be submitted as a list.")
        if len(api_names) > 3:
            raise ValueError("You can pin a maximum of three achievements.")
        if any(not isinstance(name, str) or not name or len(name) > 256 for name in api_names):
            raise ValueError("The pinned achievement list contains an invalid achievement ID.")
        if len(set(api_names)) != len(api_names):
            raise ValueError("An achievement can only be pinned once.")

        with self._state_lock:
            steamid = self._state.get("steamid")
            appid = self._state.get("appid")
            available = {
                item.get("api_name")
                for item in self._state.get("achievements", [])
                if item.get("api_name")
            }
            connected = bool(self._state.get("connected"))
        if not connected or not steamid or not appid:
            raise ValueError("Connect a Steam game before managing pinned achievements.")
        unknown = [name for name in api_names if name not in available]
        if unknown:
            raise ValueError("One or more pinned achievements do not belong to the currently selected game.")

        key = self._scope_key(str(steamid), int(appid))
        with self._pins_lock:
            document = self._read_pins_document()
            document[key] = list(api_names)
            self._write_pins_document(document)
        return self.pins_snapshot()

    def status(self) -> dict:
        config = read_config(self.config_path)
        state = self.snapshot()
        return {
            "configured": bool(config.get("api_key") and config.get("steamid") and config.get("appid")),
            **{key: state.get(key) for key in (
                "connected", "status", "stale", "error", "last_updated", "game_name",
                "appid", "steamid", "total", "unlocked",
            )},
        }

    def _publish(self, fresh: dict) -> None:
        unlocked_names = set(fresh.pop("_unlocked_names", set()))
        scope = (str(fresh.get("steamid")), int(fresh.get("appid")))

        with self._state_lock:
            same_scope = self._last_scope == scope
            if same_scope:
                newly_unlocked = unlocked_names - self._last_unlocks
                events = list(self._state.get("new_unlocks", []))
                new_items = [
                    item for item in fresh["achievements"]
                    if item["api_name"] in newly_unlocked
                ]
                new_items.sort(key=lambda item: (
                    item.get("unlocktime", 0), item.get("name", "").casefold()
                ))
                for item in new_items:
                    events.append({
                        "id": str(uuid.uuid4()),
                        "api_name": item["api_name"],
                        "name": item["name"],
                        "description": item.get("description", ""),
                        "icon": item.get("icon", ""),
                    })
                fresh["new_unlocks"] = events[-50:]
            else:
                # Initial connection or account/game switch establishes baseline.
                fresh["new_unlocks"] = []

            self._state = fresh
            self._last_unlocks = unlocked_names
            self._last_scope = scope

    def _set_setup_required(self) -> None:
        with self._state_lock:
            self._state = {
                "configured": False,
                "connected": False,
                "status": "setup_required",
                "stale": False,
                "error": "Choose a Steam game and connect your account in the setup page.",
                "game_name": None,
                "appid": None,
                "steamid": None,
                "total": 0,
                "unlocked": 0,
                "achievements": [],
                "last_updated": None,
                "new_unlocks": [],
            }
            self._last_unlocks.clear()
            self._last_scope = None

    def _record_refresh_error(self, message: str) -> None:
        with self._state_lock:
            has_data = bool(self._state.get("achievements"))
            self._state.update({
                "configured": True,
                "connected": has_data,
                "status": "stale" if has_data else "error",
                "stale": has_data,
                "error": message,
            })

    def refresh(self) -> bool:
        with self._refresh_lock:
            config = read_config(self.config_path)
            if not config.get("api_key") or not config.get("steamid") or not config.get("appid"):
                self._set_setup_required()
                return False
            try:
                fresh = self.client.fetch_achievement_data(config)
                self._publish(fresh)
                return True
            except Exception as exc:
                message = str(exc)
                if "achievement" in message.lower() or "profile" in message.lower():
                    message += " Check your Steam privacy settings and confirm that the selected game supports achievements."
                self._record_refresh_error(message)
                return False

    def connect(
        self,
        api_key: str,
        profile: str,
        appid_input: str,
        game_name: str = "",
    ) -> tuple[bool, str]:
        api_key = validate_api_key(api_key)
        steamid = self.client.normalize_steam_id(profile, api_key)
        appid = parse_app_id(appid_input)
        selected_name = str(game_name).strip()[:120]
        candidate = {
            "api_key": api_key,
            "steamid": steamid,
            "appid": appid,
            "game_name": selected_name,
        }

        with self._refresh_lock:
            # Validate the entire candidate before replacing the saved account.
            fresh = self.client.fetch_achievement_data(candidate)
            write_config(candidate, self.config_path)
            self._publish(fresh)

        self._refresh_event.set()
        return True, (
            f"Connected to {fresh['game_name']}. Loaded "
            f"{fresh['unlocked']} of {fresh['total']} achievements."
        )

    def request_refresh(self) -> bool:
        success = self.refresh()
        self._refresh_event.set()
        return success

    def run_refresh_loop(self) -> None:
        delay = 1
        while not self._stop_event.is_set():
            success = self.refresh()
            delay = POLL_SECONDS if success else min(
                MAX_BACKOFF_SECONDS, max(POLL_SECONDS, delay * 2)
            )
            self._refresh_event.wait(delay)
            self._refresh_event.clear()

    def stop(self) -> None:
        self._stop_event.set()
        self._refresh_event.set()
