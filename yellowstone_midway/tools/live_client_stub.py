"""Serve deterministic live-client fixtures on a local test port."""
from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args: object) -> None:
        pass

    def send_json(self, payload: dict) -> None:
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.endswith("/schema"):
            self.send_json({"controls": [{"key": "hydro.boundary_c", "type": "float", "min": 0, "max": 30, "default": 17.5, "bound_source": "test fixture", "provenance": "authored"}], "cells": [{"id": "cell", "start_s_m": 0, "end_s_m": 20, "position_xyz": [0, 1, 10]}], "river_features": {"test": {"points_xyz": [[0, 1, 0], [0, 1, 20]], "point_s_m": [0, 20], "width_m": 20}}})
        else:
            after = float(parse_qs(parsed.query).get("after_t_s", [-1])[0])
            self.send_json({"revision": 0, "frames": [{"t_s": t, "epoch_unix": 1784052000 + t, "temperature_c": [10 + t]} for t in [0, 10, 20] if t > after]})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        self.send_json({"ok": True, "revision": 1, "truncate_after_t_s": body.get("at_s", 0), "controls": body.get("changes", {}), "dirty_stages": ["river", "oxygen", "foodweb"]})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18876)
    args = parser.parse_args()
    HTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
