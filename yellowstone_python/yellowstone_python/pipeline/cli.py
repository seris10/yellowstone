"""Cli build operations."""
from __future__ import annotations

import argparse
import logging
from yellowstone_python.pipeline.shared import PKG_ROOT, Path, build_id, json
from yellowstone_python.pipeline.config import load_config, validate_config
from yellowstone_python.pipeline.inputs import load_inputs, verify_input_stability
from yellowstone_python.pipeline.pipeline import simulate_all
from yellowstone_python.pipeline.render import render_all
from yellowstone_python.pipeline.sidecars import _write_variant_and_gate

def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PKG_ROOT / "configs" / "baseline.yaml"))
    ap.add_argument("--out", default=str(PKG_ROOT / "derived"))
    ap.add_argument(
        "--force", action="store_true",
        help=("Reuse the build directory when CHECKS.json already exists. "
              "Default behavior raises so a completed build is never "
              "overwritten in place."))
    args = ap.parse_args()

    cfg_raw = load_config(Path(args.config))
    import os
    if os.environ.get("YELLOWSTONE_WORLD"):
        cfg_raw["world_root"] = os.environ["YELLOWSTONE_WORLD"]
    # Non-mutating validation: cfg is the normalized copy used downstream.
    cfg = validate_config(cfg_raw)
    baseline, world, deps, tfns = load_inputs(cfg)
    bid = build_id(cfg, deps, code_rev=deps["code_rev"])
    out = Path(args.out) / bid
    if (out / "CHECKS.json").is_file() and not args.force:
        raise FileExistsError(
            f"build directory {out} already holds a completed build "
            f"(CHECKS.json present); pass --force to reuse it")
    out.mkdir(parents=True, exist_ok=True)

    res = simulate_all(cfg, baseline, world, tfns)
    verify_input_stability(cfg, deps)
    shells_doc = render_all(res, out, deps, Path(cfg["world_root"]))
    _write_variant_and_gate(cfg, baseline, deps, res, out, bid,
                            shells_doc is not None)
    return 0 if json.loads((out / "CHECKS.json").read_text())["passed"] else 2
