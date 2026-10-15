"""Shared JSON HTTP transport for local simulation and analysis routes."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from urllib.parse import parse_qs, urlparse


class JsonRequestHandler(BaseHTTPRequestHandler):
    """Read and write bounded JSON requests for a local HTTP service."""

    max_body_bytes = 1048576

    def write_json(self, value, status: int = 200):
        """Send JSON with local cross-origin access headers."""
        body = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        """Return a bounded JSON request object or raise ValueError."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError as error:
            raise ValueError("Content-Length must be an integer") from error
        if not 0 < length <= self.max_body_bytes:
            raise ValueError("request body size must be within 1 and 1048576 bytes")
        try:
            value = json.loads(self.rfile.read(length))
        except (ValueError, UnicodeError) as error:
            raise ValueError("request body must contain valid JSON") from error
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def do_OPTIONS(self):
        """Respond to a local cross-origin preflight request."""
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        """Route request messages through the module logger."""
        import logging
        logging.getLogger(__name__).info(format, *args)


def live_server(engine, host: str = "127.0.0.1", port: int = 8765):
    """Create a HTTP server exposing an engine's live route table."""
    class Handler(JsonRequestHandler):
        def do_GET(self):
            """Dispatch a read-only live route."""
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            try:
                if parsed.path == "/api/live/schema":
                    result = engine.schema()
                elif parsed.path == "/api/live/frames":
                    result = engine.frames(float(query.get("after_t_s", [-1])[0]),
                                           float(query["player_t_s"][0]) if "player_t_s" in query else None)
                elif parsed.path == "/api/live/compare":
                    result = engine.compare()
                elif parsed.path == "/api/live/health":
                    result = engine.frames(engine.river.time_s)
                else:
                    self.write_json({"error": "unknown route"}, 404)
                    return
                self.write_json(result)
            except (ValueError, KeyError, RuntimeError) as error:
                self.write_json({"error": str(error)}, 400)

        def do_POST(self):
            """Dispatch a live model control request."""
            kind = urlparse(self.path).path.removeprefix("/api/live/")
            if kind not in ("control", "clock", "preset", "mark", "measured", "compare", "reset", "advance_time"):
                self.write_json({"error": "unknown route"}, 404)
                return
            try:
                payload = self.read_json()
                result = engine.compare(payload.get("t_s", payload.get("at_s"))) if kind == "compare" else engine.command(kind, payload)
                self.write_json(result)
            except (ValueError, KeyError, RuntimeError) as error:
                self.write_json({"error": str(error)}, 400)

    return ThreadingHTTPServer((host, port), Handler)
