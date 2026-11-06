import unittest
from pathlib import Path

import server
import steam_overlay.app


class LauncherTests(unittest.TestCase):
    def test_server_entrypoint_delegates_to_modular_application(self):
        self.assertIs(server.main, steam_overlay.app.main)

    def test_launcher_does_not_contain_backend_implementation(self):
        source = Path(server.__file__).read_text(encoding="utf-8")
        self.assertLess(len(source.splitlines()), 20)
        self.assertIn("steam_overlay.app", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
