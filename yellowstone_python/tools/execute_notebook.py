"""Stdlib notebook smoke-executor: runs a .ipynb's code cells in order (fail-fast by default)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def execute(path: str | Path, *, extra_ns: dict | None = None,
            allow_errors: bool = False) -> dict:
    path = Path(path)
    nb = json.loads(path.read_text())
    if nb.get("nbformat", 4) < 4:
        raise ValueError(f"{path}: unsupported nbformat {nb.get('nbformat')}")
    ns: dict = {"__name__": "__main__"}
    if extra_ns:
        ns.update(extra_ns)
    errors: list = []
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        if not src.strip():
            continue
        try:
            exec(compile(src, f"{path}#cell-{i}", "exec"), ns)
        except Exception as exc:  # pylint: disable=broad-except
            if not allow_errors:
                raise RuntimeError(
                    f"{path} code cell #{i} failed: {exc}") from exc
            errors.append({"cell": i, "error": repr(exc)})
            print(f"cell #{i} failed: {exc}")
    ns["_cell_errors"] = errors
    return ns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("notebook")
    ap.add_argument("--allow-errors", action="store_true",
                    help="continue past failing cells; print each failure "
                         "and record it in ns['_cell_errors']")
    args = ap.parse_args()
    ns = execute(args.notebook, allow_errors=args.allow_errors)
    keys = sorted(k for k in ns if not k.startswith("__"))
    print(f"executed OK; namespace keys: {keys}")
    if args.allow_errors and ns.get("_cell_errors"):
        print(f"errors: {len(ns['_cell_errors'])} cell(s) failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
