"""Application startup and graceful local-server shutdown."""
from __future__ import annotations

import threading
import webbrowser
from http.server import ThreadingHTTPServer

from .constants import HOST, PORT
from .http_server import create_handler
from .service import AchievementService


def main() -> None:
    if not 1 <= PORT <= 65535:
        raise SystemExit("STEAM_OVERLAY_PORT must be between 1 and 65535.")

    service = AchievementService()
    handler = create_handler(service)

    print("=" * 62)
    print("Steam Achievement Overlay")
    print(f"Setup page:  http://{HOST}:{PORT}/")
    print(f"OBS source:  http://{HOST}:{PORT}/overlay")
    print("Keep this window open while streaming. Press Ctrl+C to stop.")
    print("=" * 62)

    try:
        httpd = ThreadingHTTPServer((HOST, PORT), handler)
    except OSError as exc:
        raise SystemExit(f"Could not start the local server on port {PORT}: {exc}") from None

    refresher = threading.Thread(
        target=service.run_refresh_loop,
        name="SteamAchievementRefresh",
        daemon=True,
    )
    refresher.start()
    browser_timer = threading.Timer(1.0, lambda: webbrowser.open(f"http://{HOST}:{PORT}/"))
    browser_timer.daemon = True
    browser_timer.start()

    try:
        httpd.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        print("\nStopping overlay helper...")
    finally:
        service.stop()
        httpd.shutdown()
        httpd.server_close()
        refresher.join(timeout=2)
