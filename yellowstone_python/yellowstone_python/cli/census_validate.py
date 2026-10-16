"""Command-line interface for census validate."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.io import sha256_file as _sha
import argparse
import hashlib
import json
import math
from pathlib import Path
import numpy as np
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.census.census_validate import PKG, cmd_annotate, cmd_annotate_web, cmd_evaluate, cmd_freeze, cmd_sample

def main() -> int:
    import logging
    logging.basicConfig(level=logging.INFO)
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--census", default=str(PKG / "derived" / "census.json"))
    s = sub.add_parser("sample")
    s.add_argument("--plots", type=int, default=12)
    s.add_argument("--cell-px", type=int, default=256)
    s.add_argument("--seed", type=int, default=42)
    sub.add_parser("annotate")
    e = sub.add_parser("evaluate")
    e.add_argument("--tolerances", nargs="+", type=float, default=[4.0, 6.0, 10.0])
    args = ap.parse_args()
    cmds = {"freeze": cmd_freeze, "sample": cmd_sample,
              "annotate": cmd_annotate_web, "annotate-tk": cmd_annotate,
              "evaluate": cmd_evaluate}
    return cmds[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
