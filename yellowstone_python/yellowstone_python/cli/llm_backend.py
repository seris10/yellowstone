"""Command-line interface for llm backend."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG
from yellowstone_python.common.io import sha256_file as _sha256
import argparse
import hashlib
import json
import math
import re
import socket
import sqlite3
import threading
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from yellowstone_python.service.server import JsonRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.service.analysis_store import RADIUS_MAX_M as MAX_RADIUS_M
from yellowstone_python.service.analysis_store import RADIUS_MIN_M as MIN_RADIUS_M
from yellowstone_python.service.llm_backend import Backend, DEFAULT_DERIVED, DEFAULT_WORLD, serve

def main() -> int:
    import logging
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    ap.add_argument("--serve", action="store_true")
    ap.add_argument("--no-hydrology", action="store_true")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--world", default=str(DEFAULT_WORLD))
    ap.add_argument("--derived", default=str(DEFAULT_DERIVED))
    ap.add_argument("--snapshot-out", default=None)
    ap.add_argument("--zones", action="store_true")
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--x", type=float, default=-252.0)
    ap.add_argument("--z", type=float, default=159.0)
    ap.add_argument("--r", type=float, default=120.0)
    args = ap.parse_args()

    backend = Backend(Path(args.world), Path(args.derived))
    if args.serve:
        return serve(args.port, Path(args.world), Path(args.derived),
                     hydrology=not args.no_hydrology)
    if args.snapshot_out:
        out = Path(args.snapshot_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(out, backend.snapshot(), indent=1)
        print(f"snapshot -> {out}")
        return 0
    if args.zones:
        print(json.dumps(backend.zones(), indent=1))
        return 0
    if args.compare:
        print(json.dumps(backend.compare(args.x, args.z, args.r), indent=1))
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
