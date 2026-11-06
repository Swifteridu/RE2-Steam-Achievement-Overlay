import json
import threading
import unittest
import urllib.error
import urllib.request

import server


class LocalHttpSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_port = server.PORT
        self.httpd = server.LocalThreadingHTTPServer((server.HOST, 0), server.Handler)
        server.PORT = self.httpd.server_port
        self.base_url = f"http://{server.HOST}:{server.PORT}"
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)
        server.PORT = self.original_port

    def test_local_achievement_endpoint_is_readable(self):
        with urllib.request.urlopen(self.base_url + "/api/achievements", timeout=3) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get("Cache-Control"), "no-store")
            payload = json.loads(response.read())
        self.assertEqual(payload["appid"], server.APP_ID)

    def test_cross_origin_post_is_rejected(self):
        request = urllib.request.Request(
            self.base_url + "/api/unknown",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": "https://attacker.example",
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)

    def test_unexpected_host_is_rejected(self):
        request = urllib.request.Request(
            self.base_url + "/api/achievements",
            headers={"Host": "attacker.example"},
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        self.assertEqual(caught.exception.code, 403)

    def test_same_origin_post_passes_origin_check(self):
        request = urllib.request.Request(
            self.base_url + "/api/unknown",
            data=b"{}",
            headers={
                "Content-Type": "application/json",
                "Origin": self.base_url,
            },
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3)
        # The endpoint is intentionally unknown, but the request passes the
        # Host/Origin checks and reaches normal route handling.
        self.assertEqual(caught.exception.code, 404)


if __name__ == "__main__":
    unittest.main(verbosity=2)
