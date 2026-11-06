import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import Mock

from http.server import ThreadingHTTPServer

from steam_overlay.http_server import create_handler
from steam_overlay.service import AchievementService


class LocalHttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.service = AchievementService()
        self.service.client = Mock()
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), create_handler(self.service))
        self.base_url = f"http://127.0.0.1:{self.httpd.server_port}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def test_local_achievement_endpoint_is_readable(self):
        with urllib.request.urlopen(self.base_url + "/api/achievements", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            payload = json.loads(response.read())
        self.assertIn("new_unlocks", payload)

    def test_cross_origin_post_is_rejected(self):
        request = urllib.request.Request(
            self.base_url + "/api/unknown", data=b"{}",
            headers={"Content-Type": "application/json", "Origin": "https://attacker.example"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)

    def test_unexpected_host_is_rejected(self):
        request = urllib.request.Request(
            self.base_url + "/api/achievements", headers={"Host": "attacker.example"}
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)

    def test_same_origin_post_passes_origin_validation(self):
        request = urllib.request.Request(
            self.base_url + "/api/unknown", data=b"{}",
            headers={"Content-Type": "application/json", "Origin": self.base_url},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 404)

    def test_setup_page_explains_all_steam_games(self):
        with urllib.request.urlopen(self.base_url + "/", timeout=3) as response:
            html = response.read().decode("utf-8")
        self.assertIn("Choose a Steam game", html)
        self.assertIn('id="gameSearch"', html)
        self.assertIn("data.games.slice(0,3)", html)

    def test_game_search_endpoint_returns_at_most_three_results(self):
        self.service.client.search_store_games.return_value = [
            {"appid": index, "name": f"Game {index}", "image": ""}
            for index in range(1, 8)
        ]
        with urllib.request.urlopen(self.base_url + "/api/games/search?q=test", timeout=3) as response:
            payload = json.loads(response.read())
        self.assertTrue(payload["ok"])
        self.assertEqual(len(payload["games"]), 3)
        self.service.client.search_store_games.assert_called_once_with("test")


if __name__ == "__main__":
    unittest.main(verbosity=2)
