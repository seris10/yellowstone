"""Command-line interface for study scenarios."""
from __future__ import annotations

import argparse
from pathlib import Path
from yellowstone_python.study_mode import *

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--write", metavar="DIR")
    ap.add_argument("--diff", nargs=2, metavar=("A", "B"))
    args = ap.parse_args()
    if args.list:
        for name, p in PRESETS.items():
            print(f"{name}: {p['about']}")
        return 0
    if args.write:
        import yaml
        import sys
        pass
        base = yaml.safe_load(
            (Path(__file__).resolve().parents[2] / "configs" / "baseline.yaml"
             ).read_text())
        d = Path(args.write)
        d.mkdir(parents=True, exist_ok=True)
        for name in PRESETS:
            (d / f"{name}.yaml").write_text(
                yaml.safe_dump(apply_preset(base, name), sort_keys=True))
            print("wrote", d / f"{name}.yaml")
        return 0
    if args.diff:
        import yaml
        a_raw = yaml.safe_load(Path(args.diff[0]).read_text())
        b_raw = yaml.safe_load(Path(args.diff[1]).read_text())
        if not isinstance(a_raw, dict) or not isinstance(b_raw, dict):
            raise ValueError("YAML inputs must be mappings")
        a, b = a_raw, b_raw
        for row in diff_configs(a, b):
            print(f"{row['path']}: {row['A']!r} -> {row['B']!r}")
        return 0
    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
