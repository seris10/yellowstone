"""Stdlib notebook smoke-executor: runs a .ipynb's code cells in order.

No jupyter dependency (nbformat/nbconvert are NOT installed here): the
notebook JSON is read with stdlib json and each code cell is exec'd in a
shared namespace. Markdown cells are skipped. Environment overrides
(ANALYSIS_STORE, FIG_DIR, ...) pass through os.environ, so tests point
the notebook at synthetic stores in tmp_path.

Human equivalent (requires jupyter):
    jupyter nbconvert --to notebook --execute notebooks/census_explorer.ipynb \
        --output census_explorer.executed.ipynb --allow-errors

Usage:
    python3 tools/execute_notebook.py notebooks/census_explorer.ipynb
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def execute(path: str | Path, *, extra_ns: dict | None = None) -> dict:
    path = Path(path)
    nb = json.loads(path.read_text())
    if nb.get("nbformat", 4) < 4:
        raise ValueError(f"{path}: unsupported nbformat {nb.get('nbformat')}")
    ns: dict = {"__name__": "__main__"}
    if extra_ns:
        ns.update(extra_ns)
    for i, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        src = "".join(cell.get("source", []))
        if not src.strip():
            continue
        try:
            exec(compile(src, f"{path}#cell-{i}", "exec"), ns)
        except Exception as exc:
            raise RuntimeError(
                f"{path} code cell #{i} failed: {exc}") from exc
    return ns


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("notebook")
    args = ap.parse_args()
    ns = execute(args.notebook)
    print(f"executed OK; namespace keys: {sorted(k for k in ns if not k.startswith('__'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
