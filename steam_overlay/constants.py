"""Application-wide paths and settings."""
from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT_DIR / "static"
CONFIG_PATH = ROOT_DIR / "config.json"
CACHE_DIR = ROOT_DIR / "cache"

HOST = "127.0.0.1"
PORT = int(os.environ.get("STEAM_OVERLAY_PORT", "8765"))

# Used only when importing the original v1.1 Resident Evil 2 config, which did
# not store an AppID. New installations must explicitly choose a Steam game.
LEGACY_V11_APP_ID = 883710
LEGACY_V11_GAME_NAME = "Resident Evil 2"

POLL_SECONDS = 30
MAX_BACKOFF_SECONDS = 300
SCHEMA_CACHE_SECONDS = 6 * 60 * 60
MAX_RESPONSE_BYTES = 2_000_000
MAX_REQUEST_BYTES = 20_000
MAX_GAME_SEARCH_RESULTS = 3
STEAM_API_BASE = "https://api.steampowered.com"
STEAM_STORE_BASE = "https://store.steampowered.com"
