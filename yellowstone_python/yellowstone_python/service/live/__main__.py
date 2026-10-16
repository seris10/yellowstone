"""Command-line entry point for the live simulation service."""
from __future__ import annotations

import argparse
import json
import logging
import os
import secrets
import sys
from pathlib import Path

from yellowstone_python.service.live.engine import LiveEngine
from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.service.server import live_server


def export_session(path: Path, destination: Path) -> Path:
    """Export an append-only session log as a scenario configuration."""
    import yaml
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not records or records[0].get("kind") != "session_start":
        raise ValueError("session log requires a session_start record")
    first = records[0]
    last = next((record for record in reversed(records) if "solver_config" in record), first)
    clock = next((record for record in reversed(records) if record["kind"] == "clock"), {})
    config = {"run_mode": "scenario", "live": {"session_id": path.stem, "build_id": first["build_id"],
        "epoch_unix": first["epoch_unix"], "events": records, "duration_s": records[-1]["t_s"],
        "dt_s": min(first["max_dt_s"], max(.1, clock.get("time_scale", 1.) / 150.)),
        "frame_interval_s": first["frame_interval_s"], "solver_config": last["solver_config"],
        "initial_solver_config": first["solver_config"],
        "integration_segments": last.get("integration_segments", []),
        "forcing_catalog": last.get("forcing_catalog", {})}}
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(yaml.safe_dump(config, sort_keys=True), encoding="utf-8")
    return destination


def main() -> int:
    """Serve live frames or export a recorded session scenario."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--time-scale", type=float, default=1.)
    parser.add_argument("--horizon-s", type=float, default=600.)
    parser.add_argument("--export-scenario", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    if args.export_scenario:
        destination = args.out or Path("configs/experiments") / f"session-{args.export_scenario.stem}.yaml"
        print(export_session(args.export_scenario, destination))
        return 0
    if args.build is None:
        parser.error("--build is required for the service")
    engine = LiveEngine.from_build(args.build, time_scale=args.time_scale, horizon_s=args.horizon_s, start_worker=True)
    token = os.environ.get("YS_LIVE_TOKEN") or secrets.token_urlsafe(24)
    if "YS_LIVE_TOKEN" not in os.environ:
        print(f"State-changing requests need header X-Yellowstone-Token: {token}", file=sys.stderr)
    server = live_server(engine, port=args.port, token=token)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
