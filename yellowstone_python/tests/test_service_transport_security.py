"""Cross-origin, content-type, host and token boundaries of the local JSON service."""
import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from yellowstone_python.service.server import live_server

TOKEN = "test-token"


class StubEngine:
    def __init__(self):
        self.commands = []

    def schema(self):
        return {"ok": True}

    def command(self, kind, payload):
        self.commands.append(kind)
        return {"kind": kind}


@pytest.fixture
def service():
    engine = StubEngine()
    server = live_server(engine, port=0, token=TOKEN, allowed_origins=("http://127.0.0.1:5173",))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield engine, f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def call(base, path, method="POST", headers=None, body=b"{}"):
    request = Request(base + path, data=body if method == "POST" else None, method=method, headers=headers or {})
    try:
        with urlopen(request, timeout=5) as response:
            return response.status, dict(response.headers), json.loads(response.read() or b"{}")
    except HTTPError as error:
        return error.code, dict(error.headers), json.loads(error.read() or b"{}")


def test_native_client_with_token_can_write(service):
    engine, base = service
    status, headers, _ = call(base, "/api/live/clock", headers={"Content-Type": "application/json", "X-Yellowstone-Token": TOKEN})
    assert status == 200
    assert "Access-Control-Allow-Origin" not in headers
    assert engine.commands == ["clock"]


def test_write_without_or_with_wrong_token_is_refused(service):
    engine, base = service
    assert call(base, "/api/live/reset", headers={"Content-Type": "application/json"})[0] == 401
    assert call(base, "/api/live/reset", headers={"Content-Type": "application/json", "X-Yellowstone-Token": "nope"})[0] == 401
    assert engine.commands == []


def test_write_must_declare_json(service):
    engine, base = service
    for content_type in ("text/plain", "application/x-www-form-urlencoded"):
        assert call(base, "/api/live/reset", headers={"Content-Type": content_type, "X-Yellowstone-Token": TOKEN})[0] == 415
    assert engine.commands == []


def test_foreign_origin_is_refused_even_with_token(service):
    engine, base = service
    headers = {"Content-Type": "application/json", "X-Yellowstone-Token": TOKEN, "Origin": "https://evil.example"}
    assert call(base, "/api/live/reset", headers=headers)[0] == 403
    assert call(base, "/api/live/schema", method="GET", headers={"Origin": "https://evil.example"})[0] == 403
    assert engine.commands == []


def test_preflight_has_no_wildcard_and_only_allows_listed_origin(service):
    _, base = service
    status, headers, _ = call(base, "/api/live/reset", method="OPTIONS", headers={"Origin": "https://evil.example"})
    assert status == 403 and "Access-Control-Allow-Origin" not in headers
    status, headers, _ = call(base, "/api/live/reset", method="OPTIONS", headers={"Origin": "http://127.0.0.1:5173"})
    assert status == 204 and headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5173"


def test_rebound_host_header_is_refused(service):
    _, base = service
    assert call(base, "/api/live/schema", method="GET", headers={"Host": "attacker.example:8765"})[0] == 403
    assert call(base, "/api/live/schema", method="GET")[0] == 200
