import json
import tempfile
import unittest
from pathlib import Path

from steam_overlay.config import (
    parse_app_id,
    read_config,
    validate_api_key,
    validate_app_id,
    validate_steam_id,
    write_config,
)
from steam_overlay.constants import LEGACY_V11_APP_ID, LEGACY_V11_GAME_NAME


VALID_KEY = "0123456789abcdef0123456789abcdef"
VALID_ID = "76561198000000000"


class ValidationTests(unittest.TestCase):
    def test_accepts_valid_api_key(self):
        self.assertEqual(validate_api_key(VALID_KEY), VALID_KEY)

    def test_rejects_invalid_api_keys(self):
        for value in ("too-short", "g" * 32, "a" * 31, "a" * 33):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_api_key(value)

    def test_accepts_valid_steamid64(self):
        self.assertEqual(validate_steam_id(VALID_ID), VALID_ID)

    def test_rejects_invalid_steamid64(self):
        with self.assertRaises(ValueError):
            validate_steam_id("12345")

    def test_accepts_numeric_appid(self):
        self.assertEqual(validate_app_id(123456), 123456)

    def test_parses_store_url(self):
        self.assertEqual(parse_app_id("https://store.steampowered.com/app/123456/Example/"), 123456)

    def test_parses_store_url_without_scheme(self):
        self.assertEqual(parse_app_id("store.steampowered.com/app/123456/"), 123456)

    def test_rejects_untrusted_store_url(self):
        with self.assertRaises(ValueError):
            parse_app_id("https://example.com/app/123456/")

    def test_rejects_invalid_appid(self):
        for value in ("0", "abc", "1" * 11):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_app_id(value)


class ConfigTests(unittest.TestCase):
    def test_config_write_is_atomic_and_valid_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            write_config({"steamid": VALID_ID, "appid": 123456}, path)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {
                "steamid": VALID_ID, "appid": 123456,
            })
            self.assertFalse(path.with_suffix(".json.tmp").exists())

    def test_legacy_v11_config_migrates_to_its_original_game(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "config.json"
            path.write_text(json.dumps({"api_key": VALID_KEY, "steamid": VALID_ID}), encoding="utf-8")
            migrated = read_config(path)
            self.assertEqual(migrated["appid"], LEGACY_V11_APP_ID)
            self.assertEqual(migrated["game_name"], LEGACY_V11_GAME_NAME)


if __name__ == "__main__":
    unittest.main(verbosity=2)
