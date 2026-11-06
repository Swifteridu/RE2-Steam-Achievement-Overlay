import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import server


VALID_KEY = "0123456789abcdef0123456789abcdef"
VALID_ID = "76561198000000000"


class ValidationTests(unittest.TestCase):
    def test_accepts_32_character_hex_api_key(self):
        self.assertEqual(server.validate_api_key(VALID_KEY), VALID_KEY)

    def test_rejects_malformed_api_key(self):
        for value in ("too-short", "g" * 32, "a" * 31, "a" * 33):
            with self.subTest(value=value), self.assertRaises(ValueError):
                server.validate_api_key(value)

    def test_accepts_steamid64(self):
        self.assertEqual(server.validate_steam_id(VALID_ID), VALID_ID)

    def test_rejects_non_steam_hosts(self):
        with self.assertRaises(ValueError):
            server.normalize_steam_id("https://example.com/id/player", VALID_KEY)

    def test_profile_url_resolves_vanity(self):
        with patch.object(server, "steam_get", return_value={
            "response": {"success": 1, "steamid": VALID_ID}
        }) as steam_get:
            result = server.normalize_steam_id(
                "https://steamcommunity.com/id/example/", VALID_KEY
            )
        self.assertEqual(result, VALID_ID)
        self.assertEqual(steam_get.call_args.args[0], "ISteamUser/ResolveVanityURL/v1/")


class SteamDataTests(unittest.TestCase):
    def setUp(self):
        with server.cache_lock:
            server.schema_cache.update({"api_key": None, "expires_at": 0, "achievements": None})

    def test_merges_schema_and_player_unlocks(self):
        schema = [
            {"name": "ACH_ONE", "displayName": "First", "description": "First desc", "icon": "https://example.com/one.png", "icongray": "https://example.com/one-gray.png"},
            {"name": "ACH_TWO", "displayName": "Second", "hidden": 1},
        ]
        player = {
            "playerstats": {
                "success": True,
                "achievements": [
                    {"apiname": "ACH_ONE", "achieved": 1, "unlocktime": 1700000000},
                    {"apiname": "ACH_TWO", "achieved": 0, "unlocktime": 0},
                ],
            }
        }
        with patch.object(server, "steam_get", side_effect=[
            {"game": {"availableGameStats": {"achievements": schema}}}, player
        ]):
            result = server.fetch_steam_data({"api_key": VALID_KEY, "steamid": VALID_ID})

        self.assertEqual(result["total"], 2)
        self.assertEqual(result["unlocked"], 1)
        self.assertTrue(result["achievements"][0]["unlocked"])
        self.assertTrue(result["achievements"][1]["hidden"])
        self.assertEqual(result["_unlocked_names"], {"ACH_ONE"})

    def test_schema_is_cached_between_refreshes(self):
        schema = [{"name": "ACH_ONE", "displayName": "First"}]
        with patch.object(server, "steam_get", return_value={
            "game": {"availableGameStats": {"achievements": schema}}
        }) as steam_get:
            server._get_schema(VALID_KEY)
            server._get_schema(VALID_KEY)
        self.assertEqual(steam_get.call_count, 1)

    def test_rejects_player_stats_error(self):
        schema = [{"name": "ACH_ONE", "displayName": "First"}]
        with patch.object(server, "_get_schema", return_value=schema), patch.object(
            server, "steam_get", return_value={"playerstats": {"success": False, "error": "Profile is private"}}
        ):
            with self.assertRaisesRegex(RuntimeError, "private"):
                server.fetch_steam_data({"api_key": VALID_KEY, "steamid": VALID_ID})


class ConfigTests(unittest.TestCase):
    def test_config_write_is_valid_json_and_replaced_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original = server.CONFIG_PATH
            try:
                server.CONFIG_PATH = Path(temp_dir) / "config.json"
                server.write_config({"steamid": VALID_ID})
                self.assertEqual(json.loads(server.CONFIG_PATH.read_text()), {"steamid": VALID_ID})
                self.assertFalse(server.CONFIG_PATH.with_suffix(".tmp").exists())
            finally:
                server.CONFIG_PATH = original


class CacheBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.original_cache = dict(server.cache)
        self.original_unlocks = set(server.last_unlocks)
        self.original_steamid = server.last_steamid

    def tearDown(self):
        with server.cache_lock:
            server.cache.clear()
            server.cache.update(self.original_cache)
            server.last_unlocks = self.original_unlocks
            server.last_steamid = self.original_steamid

    def test_refresh_error_preserves_last_good_achievements(self):
        previous = [{"api_name": "ACH_OLD", "name": "Existing", "unlocked": True}]
        with server.cache_lock:
            server.cache.update({"achievements": previous, "connected": True, "status": "connected"})
        server.record_refresh_error("Steam is temporarily unavailable.")
        with server.cache_lock:
            self.assertEqual(server.cache["achievements"], previous)
            self.assertTrue(server.cache["connected"])
            self.assertTrue(server.cache["stale"])
            self.assertEqual(server.cache["status"], "stale")

    def test_first_snapshot_does_not_create_false_unlock_notification(self):
        with server.cache_lock:
            server.last_steamid = None
            server.last_unlocks = set()
        fresh = {
            "steamid": VALID_ID,
            "achievements": [{"api_name": "ACH_OLD", "name": "Already Owned", "unlocked": True}],
            "_unlocked_names": {"ACH_OLD"},
            "new_unlock": None,
        }
        server.publish_fresh_data(fresh)
        with server.cache_lock:
            self.assertIsNone(server.cache["new_unlock"])
            self.assertEqual(server.last_unlocks, {"ACH_OLD"})

    def test_new_unlock_is_detected_for_same_account(self):
        with server.cache_lock:
            server.last_steamid = VALID_ID
            server.last_unlocks = {"ACH_OLD"}
            server.cache["new_unlock"] = None
        fresh = {
            "steamid": VALID_ID,
            "achievements": [
                {"api_name": "ACH_OLD", "name": "Old", "unlocked": True},
                {"api_name": "ACH_NEW", "name": "New unlock", "description": "Great", "icon": "https://example.com/new.png", "unlocked": True},
            ],
            "_unlocked_names": {"ACH_OLD", "ACH_NEW"},
            "new_unlock": None,
        }
        server.publish_fresh_data(fresh)
        with server.cache_lock:
            self.assertEqual(server.cache["new_unlock"]["name"], "New unlock")

    def test_account_switch_does_not_emit_false_unlock(self):
        with server.cache_lock:
            server.last_steamid = VALID_ID
            server.last_unlocks = {"ACH_OLD"}
            server.cache["new_unlock"] = None
        other_id = "76561198000000001"
        fresh = {
            "steamid": other_id,
            "achievements": [{"api_name": "ACH_NEW", "name": "New account achievement", "unlocked": True}],
            "_unlocked_names": {"ACH_NEW"},
            "new_unlock": None,
        }
        server.publish_fresh_data(fresh)
        with server.cache_lock:
            self.assertIsNone(server.cache["new_unlock"])
            self.assertEqual(server.last_steamid, other_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
