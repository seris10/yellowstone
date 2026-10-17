"""Notebook discipline + execution tests for reach_fit.ipynb."""
import json
import math
import sys
import time
from pathlib import Path

from yellowstone_python.river.calibrate import run_fit_forward


def _synthetic_bundle(path: Path) -> None:
    t0 = time.time()
    n = int(2 * 86400 // 1800)
    grid = [t0 + i * 1800 for i in range(n + 1)]
    up_t = [[g, 10.0 + 2.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi)]
            for g in grid]
    up_q = [[g, 1.0] for g in grid]
    met = [[g, 8.0 + 5.0 * math.sin((g - t0) / 86400.0 * 2 * math.pi),
            0.5, 2.0, max(0.0, 500.0 * math.sin(
                (g - t0) / 86400.0 * 2 * math.pi)), 0.2] for g in grid]
    draft = {"schema": "yellowstone.firehole_obs.v1",
             "sites": {
        "06036805": {"series": {"temperature_c": up_t,
                                "discharge_m3_s": up_q}},
        "06036905": {"series": {"temperature_c": [], "discharge_m3_s": []}}},
        "met": {"hourly": met}}
    fwd = run_fit_forward(draft, 300000.0, 600000.0, 3.5, 30.0, 1.0,
                          dt_s=1800.0)
    # Inverse-crime fixture: one model generates and fits the data to exercise notebook mechanics.
    draft["sites"]["06036905"]["series"] = {
        "temperature_c": [[g, v] for g, v in zip(fwd["grid"],
                                                 fwd["modeled_c"])],
        "discharge_m3_s": [[g, 4.5] for g in fwd["grid"]]}
    path.write_text(json.dumps(draft), encoding="utf-8")


def _cells(nb):
    return json.loads(nb.read_text(encoding="utf-8"))["cells"]


def test_notebook_stored_cleared(repo_root):
    nb = (repo_root / "notebooks/reach_fit.ipynb")
    assert nb.exists()
    data = json.loads(nb.read_text(encoding="utf-8"))
    assert data.get("nbformat") == 4
    code = [c for c in data["cells"] if c.get("cell_type") == "code"]
    assert len(code) >= 5
    for cell in code:
        assert cell.get("outputs") == []
        assert cell.get("execution_count") is None


def test_notebook_offline_only(repo_root):
    src = "\n".join("".join(c.get("source", []))
                    for c in _cells((repo_root / "notebooks/reach_fit.ipynb"))
                    if c.get("cell_type") == "code")
    for banned in ("urllib", "urlopen", "requests.get", "socket"):
        assert banned not in src


def test_notebook_executes_on_synthetic_bundle(tmp_path, monkeypatch, repo_root):
    bundle = tmp_path / "obs.json"
    _synthetic_bundle(bundle)
    figdir = tmp_path / "figs"
    monkeypatch.setenv("OBS", str(bundle))
    monkeypatch.setenv("FIG_DIR", str(figdir))
    monkeypatch.chdir(tmp_path)
    import tools.execute_notebook as ex
    import_path = list(sys.path)
    ex.execute((repo_root / "notebooks/reach_fit.ipynb"))
    assert sys.path == import_path
    for fig in ("fit_holdout.png", "bands.png", "ridge.png"):
        p = figdir / fig
        assert p.exists() and p.stat().st_size > 1000
