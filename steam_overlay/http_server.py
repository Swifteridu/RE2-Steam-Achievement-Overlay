"""Local HTTP interface for the setup page and OBS browser source."""
from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .constants import HOST, MAX_REQUEST_BYTES, STATIC_DIR
from .service import AchievementService


class LocalThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


def add_security_headers(handler: BaseHTTPRequestHandler) -> None:
    handler.send_header("X-Content-Type-Options", "nosniff")
    handler.send_header("Referrer-Policy", "no-referrer")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
        "script-src 'self' 'unsafe-inline'; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'",
    )


def send_json(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    add_security_headers(handler)
    handler.end_headers()
    try:
        handler.wfile.write(body)
    except (BrokenPipeError, ConnectionResetError):
        pass


def create_handler(service: AchievementService, static_dir: Path = STATIC_DIR):
    """Create an HTTP handler bound to a specific service instance."""

    class OverlayRequestHandler(BaseHTTPRequestHandler):
        server_version = "SteamAchievementOverlay/1.5.0"
        sys_version = ""

        def log_request(self, code="-", size="-") -> None:
            # Never log query strings or request bodies; Steam search terms and
            # user data are intentionally omitted from routine console logging.
            path = urlparse(self.path).path
            print(f"[{self.log_date_time_string()}] {self.client_address[0]} {self.command} {path} {code}")

        def _expected_origin(self) -> str:
            return f"http://{HOST}:{self.server.server_port}"

        def _check_host(self) -> bool:
            expected = f"{HOST}:{self.server.server_port}"
            if self.headers.get("Host", "").lower() != expected.lower():
                send_json(self, {"ok": False, "error": "Requests must use the local overlay address."}, 403)
                return False
            return True

        def _check_same_origin(self) -> bool:
            if self.headers.get("Origin") != self._expected_origin():
                send_json(self, {"ok": False, "error": "This action must be submitted from the local setup page."}, 403)
                return False
            return True

        def do_GET(self) -> None:
            if not self._check_host():
                return
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/setup"):
                self.serve_file(static_dir / "setup.html", "text/html; charset=utf-8")
            elif parsed.path == "/overlay":
                self.serve_file(static_dir / "overlay.html", "text/html; charset=utf-8")
            elif parsed.path == "/dashboard":
                self.serve_file(static_dir / "dashboard.html", "text/html; charset=utf-8")
            elif parsed.path == "/api/status":
                send_json(self, service.status())
            elif parsed.path == "/api/achievements":
                send_json(self, service.snapshot())
            elif parsed.path == "/api/pins":
                send_json(self, {"ok": True, **service.pins_snapshot()})
            elif parsed.path == "/api/games/search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                try:
                    games = service.client.search_store_games(query)
                    send_json(self, {"ok": True, "games": games[:3]})
                except (ValueError, RuntimeError) as exc:
                    send_json(self, {"ok": False, "error": str(exc)}, 400)
            elif parsed.path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
            else:
                self.send_error(404)

        def do_POST(self) -> None:
            if not self._check_host() or not self._check_same_origin():
                return
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                send_json(self, {"ok": False, "error": "Content-Type must be application/json."}, 415)
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 1:
                send_json(self, {"ok": False, "error": "A JSON request body is required."}, 400)
                return
            if length > MAX_REQUEST_BYTES:
                send_json(self, {"ok": False, "error": "Request too large."}, 413)
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                send_json(self, {"ok": False, "error": "Invalid JSON."}, 400)
                return
            if not isinstance(payload, dict):
                send_json(self, {"ok": False, "error": "The request must be a JSON object."}, 400)
                return

            path = urlparse(self.path).path
            if path == "/api/config":
                try:
                    ok, message = service.connect(
                        payload.get("api_key", ""),
                        payload.get("profile", ""),
                        payload.get("appid", ""),
                        payload.get("game_name", ""),
                    )
                    send_json(self, {"ok": ok, "message": message})
                except (ValueError, RuntimeError, OSError) as exc:
                    send_json(self, {"ok": False, "error": str(exc)}, 400)
            elif path == "/api/refresh":
                success = service.request_refresh()
                send_json(self, {"ok": success, "error": service.snapshot().get("error")})
            elif path == "/api/pins":
                try:
                    pins = service.set_pins(payload.get("api_names"))
                    send_json(self, {"ok": True, **pins})
                except (ValueError, OSError) as exc:
                    send_json(self, {"ok": False, "error": str(exc)}, 400)
            else:
                send_json(self, {"ok": False, "error": "Not found."}, 404)

        def serve_file(self, path: Path, content_type: str) -> None:
            try:
                body = path.read_bytes()
            except OSError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            add_security_headers(self)
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return OverlayRequestHandler
