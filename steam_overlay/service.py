"""Application service for account/game connection and achievement sync."""
from __future__ import annotations

import json
import threading
import time
import uuid
from pathlib import Path

from .config import read_config, write_config, parse_app_id, validate_api_key
from .constants import (
    CONFIG_PATH,
    MAX_BACKOFF_SECONDS,
    POLL_SECONDS,
)
from .steam_client import SteamClient


class AchievementService:
    """Coordinates Steam data retrieval, cached state and unlock notifications."""

    def __init__(self, client: SteamClient | None = None, config_path: Path = CONFIG_PATH) -> None:
        self.client = client or SteamClient()
        self.config_path = Path(config_path)
        self._state_lock = threading.RLock()
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
            return json.loads(json.dumps(self._state))

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
