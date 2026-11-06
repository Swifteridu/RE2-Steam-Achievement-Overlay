import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from steam_overlay.steam_client import SteamClient

VALID_KEY = "0123456789abcdef0123456789abcdef"
VALID_ID = "76561198000000000"
APP_ID = 123456


class SteamClientTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.client = SteamClient(cache_dir=Path(self.temp_dir.name))

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_profile_url_resolves_vanity_name(self):
        with patch.object(self.client, "steam_get", return_value={
            "response": {"success": 1, "steamid": VALID_ID}
        }) as steam_get:
            result = self.client.normalize_steam_id("https://steamcommunity.com/id/example/", VALID_KEY)
        self.assertEqual(result, VALID_ID)
        self.assertEqual(steam_get.call_args.args[0], "ISteamUser/ResolveVanityURL/v1/")

    def test_rejects_non_steam_profile_host(self):
        with self.assertRaises(ValueError):
            self.client.normalize_steam_id("https://example.com/id/player", VALID_KEY)

    def test_search_store_games_returns_at_most_three_valid_results(self):
        payload = {"items": [
            {"id": index, "name": f"Game {index}", "tiny_image": f"https://example.test/{index}.jpg"}
            for index in range(1, 8)
        ]}
        with patch.object(self.client, "store_get", return_value=payload):
            results = self.client.search_store_games("Example")
        self.assertEqual(len(results), 3)
        self.assertEqual([item["appid"] for item in results], [1, 2, 3])

    def test_search_discards_invalid_appids_before_limit(self):
        payload = {"items": [
            {"id": "broken", "name": "Invalid"},
            *[{"id": index, "name": f"Game {index}"} for index in range(10, 15)],
        ]}
        with patch.object(self.client, "store_get", return_value=payload):
            results = self.client.search_store_games("Example")
        self.assertEqual([item["appid"] for item in results], [10, 11, 12])

    def test_search_requires_two_characters(self):
        with self.assertRaises(ValueError):
            self.client.search_store_games("x")

    def test_get_schema_caches_persistently_per_appid(self):
        schema = [{"name": "ACH_ONE", "displayName": "First"}]
        with patch.object(self.client, "steam_get", return_value={
            "game": {"gameName": "Example Game", "availableGameStats": {"achievements": schema}}
        }) as steam_get:
            first = self.client.get_schema(APP_ID, VALID_KEY)
            self.client._schema_memory.clear()
            second = self.client.get_schema(APP_ID, VALID_KEY)
        self.assertEqual(first, ("Example Game", schema))
        self.assertEqual(second, first)
        self.assertEqual(steam_get.call_count, 1)
        self.assertTrue((Path(self.temp_dir.name) / f"schema_{APP_ID}.json").exists())

    def test_stale_schema_is_used_when_steam_is_unavailable(self):
        schema = [{"name": "ACH_ONE"}]
        self.client._save_disk_schema(APP_ID, "Cached Title", schema)
        cache_path = Path(self.temp_dir.name) / f"schema_{APP_ID}.json"
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
        payload["fetched_at"] = time.time() - 100000
        cache_path.write_text(json.dumps(payload), encoding="utf-8")
        with patch.object(self.client, "steam_get", side_effect=RuntimeError("offline")):
            result = self.client.get_schema(APP_ID, VALID_KEY)
        self.assertEqual(result, ("Cached Title", schema))

    def test_rejects_games_without_achievement_schema(self):
        with patch.object(self.client, "steam_get", return_value={
            "game": {"availableGameStats": {"achievements": []}}
        }):
            with self.assertRaisesRegex(RuntimeError, "does not expose an achievement schema"):
                self.client.get_schema(APP_ID, VALID_KEY)

    def test_fetches_selected_game_player_stats(self):
        schema = [
            {"name": "A", "displayName": "Achievement A", "description": "First", "icon": "icon-a"},
            {"name": "B", "displayName": "Achievement B", "hidden": 1},
        ]
        player = {"playerstats": {"success": True, "achievements": [
            {"apiname": "A", "achieved": 1, "unlocktime": 1700000000},
            {"apiname": "B", "achieved": 0, "unlocktime": 0},
        ]}}
        with patch.object(self.client, "get_schema", return_value=("Example Game", schema)), \
             patch.object(self.client, "steam_get", return_value=player) as steam_get:
            result = self.client.fetch_achievement_data({
                "api_key": VALID_KEY, "steamid": VALID_ID, "appid": APP_ID,
            })
        self.assertEqual(result["game_name"], "Example Game")
        self.assertEqual(result["appid"], APP_ID)
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["unlocked"], 1)
        self.assertTrue(result["achievements"][0]["unlocked"])
        self.assertTrue(result["achievements"][1]["hidden"])
        self.assertEqual(result["_unlocked_names"], {"A"})
        self.assertEqual(steam_get.call_args.args[0], "ISteamUserStats/GetPlayerAchievements/v1/")
        self.assertEqual(steam_get.call_args.args[1]["appid"], APP_ID)

    def test_rejects_private_player_stats(self):
        with patch.object(self.client, "get_schema", return_value=("Example", [{"name": "A"}])), \
             patch.object(self.client, "steam_get", return_value={
                 "playerstats": {"success": False, "error": "Profile is private"}
             }):
            with self.assertRaisesRegex(RuntimeError, "private"):
                self.client.fetch_achievement_data({
                    "api_key": VALID_KEY, "steamid": VALID_ID, "appid": APP_ID,
                })


if __name__ == "__main__":
    unittest.main(verbosity=2)
