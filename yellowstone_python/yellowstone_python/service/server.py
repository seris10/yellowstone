"""Shared JSON HTTP transport for local simulation and analysis routes."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
from urllib.parse import parse_qs, urlparse

TOKEN_HEADER = "X-Yellowstone-Token"
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]"})


class JsonRequestHandler(BaseHTTPRequestHandler):
    """Read and write bounded JSON requests for a local HTTP service.

    Browser pages are refused unless their origin is listed in ``allowed_origins``.
    Native clients send no ``Origin`` header and are unaffected. When ``auth_token``
    is set, every state-changing request must carry it in ``X-Yellowstone-Token``.
    """

    max_body_bytes = 1048576
    allowed_origins: tuple[str, ...] = ()
    auth_token: str | None = None

    def _host_name(self) -> str:
        host = self.headers.get("Host", "")
        return host.rsplit(":", 1)[0] if not host.endswith("]") and ":" in host else host

    def _origin_allowed(self) -> bool:
        origin = self.headers.get("Origin")
        return origin is None or origin in self.allowed_origins

    def guard(self, mutating: bool) -> bool:
        """Refuse DNS-rebound hosts, foreign origins, non-JSON writes and missing tokens.

        Writes the error response and returns False when the request is refused.
        """
        bound = str(self.server.server_address[0])
        if self._host_name().lower() not in LOOPBACK_HOSTS | {bound.lower()}:
            self.write_json({"error": "host not allowed"}, 403)
            return False
        if not self._origin_allowed():
            self.write_json({"error": "origin not allowed"}, 403)
            return False
        if mutating:
            media_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if media_type != "application/json":
                self.write_json({"error": "Content-Type must be application/json"}, 415)
                return False
            if self.auth_token is not None and not hmac.compare_digest(
                    self.headers.get(TOKEN_HEADER, "").encode(), self.auth_token.encode()):
                self.write_json({"error": "missing or invalid session token"}, 401)
                return False
        return True

    def write_json(self, value, status: int = 200):
        """Send JSON, adding cross-origin headers only for an allowed origin."""
        body = json.dumps(value, allow_nan=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin")
        if origin is not None and origin in self.allowed_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
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
        """Answer a preflight only for an explicitly allowed origin."""
        origin = self.headers.get("Origin")
        if origin is None or origin not in self.allowed_origins:
            self.write_json({"error": "origin not allowed"}, 403)
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", f"Content-Type, {TOKEN_HEADER}")
        self.end_headers()

    def log_message(self, format, *args):
        """Route request messages through the module logger."""
        import logging
        logging.getLogger(__name__).info(format, *args)


def live_server(engine, host: str = "127.0.0.1", port: int = 8765, token: str | None = None,
                allowed_origins: tuple[str, ...] = ()):
    """Create a HTTP server exposing an engine's live route table.

    A ``token`` makes every POST require a matching ``X-Yellowstone-Token`` header.
    """
    origins = tuple(allowed_origins)

    class Handler(JsonRequestHandler):
        auth_token = token
        allowed_origins = origins

        def do_GET(self):
            """Dispatch a read-only live route."""
            if not self.guard(mutating=False):
                return
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
            if not self.guard(mutating=True):
                return
            kind =urlparse(self.path).path.removeprefix("/api/live/")
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
