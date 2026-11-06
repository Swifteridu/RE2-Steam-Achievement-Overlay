import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from steam_overlay.service import AchievementService

VALID_KEY = "0123456789abcdef0123456789abcdef"
VALID_ID = "76561198000000000"
APP_ID = 123456


class AchievementServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temp_dir.name) / "config.json"
        self.client = Mock()
        self.service = AchievementService(client=self.client, config_path=self.config_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def fresh(steamid=VALID_ID, appid=APP_ID, unlocked=()):
        achievements = [
            {"api_name": name, "name": name, "description": "Description", "icon": "icon", "unlocked": True, "unlocktime": index}
            for index, name in enumerate(unlocked, 1)
        ]
        achievements.extend([
            {"api_name": "LOCKED", "name": "Locked", "unlocked": False, "unlocktime": 0}
        ])
        return {
            "configured": True, "connected": True, "status": "connected", "stale": False,
            "error": None, "game_name": "Example Game", "appid": appid, "steamid": steamid,
            "total": len(achievements), "unlocked": len(unlocked), "achievements": achievements,
            "last_updated": "2026-11-06T00:00:00+00:00", "new_unlocks": [],
            "_unlocked_names": set(unlocked),
        }

    def test_initial_snapshot_establishes_baseline_without_notifications(self):
        self.service._publish(self.fresh(unlocked=("A", "B")))
        self.assertEqual(self.service.snapshot()["new_unlocks"], [])

    def test_multiple_new_unlocks_are_queued(self):
        self.service._publish(self.fresh(unlocked=("A",)))
        self.service._publish(self.fresh(unlocked=("A", "B", "C")))
        names = [event["name"] for event in self.service.snapshot()["new_unlocks"]]
        self.assertEqual(names, ["B", "C"])

    def test_account_or_game_switch_establishes_new_baseline(self):
        self.service._publish(self.fresh(unlocked=("A",)))
        self.service._publish(self.fresh(steamid="76561198000000001", unlocked=("B",)))
        self.assertEqual(self.service.snapshot()["new_unlocks"], [])
        self.service._publish(self.fresh(steamid="76561198000000001", appid=APP_ID + 1, unlocked=("C",)))
        self.assertEqual(self.service.snapshot()["new_unlocks"], [])

    def test_refresh_failure_preserves_last_good_data(self):
        self.service._publish(self.fresh(unlocked=("A",)))
        self.service._record_refresh_error("Steam offline")
        state = self.service.snapshot()
        self.assertEqual(state["achievements"][0]["api_name"], "A")
        self.assertTrue(state["connected"])
        self.assertTrue(state["stale"])

    def test_snapshot_is_detached_from_live_state(self):
        self.service._publish(self.fresh(unlocked=("A",)))
        snapshot = self.service.snapshot()
        snapshot["achievements"].clear()
        self.assertEqual(len(self.service.snapshot()["achievements"]), 2)

    def test_connect_validates_candidate_before_saving(self):
        self.client.normalize_steam_id.return_value = VALID_ID
        self.client.fetch_achievement_data.return_value = self.fresh()
        success, message = self.service.connect(VALID_KEY, VALID_ID, str(APP_ID), "Example Game")
        self.assertTrue(success)
        self.assertIn("Connected to Example Game", message)
        self.assertTrue(self.config_path.exists())
        self.client.fetch_achievement_data.assert_called_once()

    def test_failed_connect_does_not_overwrite_existing_config(self):
        self.config_path.write_text('{"previous": true}', encoding="utf-8")
        self.client.normalize_steam_id.return_value = VALID_ID
        self.client.fetch_achievement_data.side_effect = RuntimeError("No schema")
        with self.assertRaises(RuntimeError):
            self.service.connect(VALID_KEY, VALID_ID, str(APP_ID), "Example Game")
        self.assertEqual(self.config_path.read_text(encoding="utf-8"), '{"previous": true}')


if __name__ == "__main__":
    unittest.main(verbosity=2)
