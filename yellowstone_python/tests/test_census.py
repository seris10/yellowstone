import math

import numpy as np

from yellowstone_python.census.canopy_census import calibrate_lone_trees, density_stats
from yellowstone_python.census.canopy_census import detect, detect_v2, qa_census
from yellowstone_python.census.canopy_census import exclude_pool_rims, to_world
import pytest


def _synthetic(crowns, size=200, bg=(0.55, 0.52, 0.45)):
    """Dark-green discs (crowns) on bright grass. crowns: (x, y, r)."""
    img = np.zeros((size, size, 3))
    img[:, :] = bg
    yy, xx = np.mgrid[0:size, 0:size]
    for x, y, r in crowns:
        m = (xx - x) ** 2 + (yy - y) ** 2 <= r ** 2
        img[m] = (0.10, 0.22, 0.08)
    return img


def test_finds_isolated_crowns():
    truth = [(40, 40, 6), (120, 60, 8), (80, 150, 5), (160, 160, 7)]
    recs = detect(_synthetic(truth))
    assert len(recs) == 4, recs
    for tx, ty, _ in truth:
        assert min(math.hypot(r["ix"] - tx, r["iz"] - ty) for r in recs) <= 3


def test_splits_touching_crowns_by_peaks():
    # Two overlapping discs with distinct peaks count as two detections.
    img = _synthetic([(90, 100, 10), (112, 100, 10)])
    recs = detect(img)
    assert len(recs) == 2


def test_ignores_grass_and_water():
    img = _synthetic([])
    img[30:60, 30:60] = (0.10, 0.15, 0.45)  # blue water patch
    assert detect(img) == []


def test_world_ids_stable_and_metric():
    recs = to_world(detect(_synthetic([(100, 100, 6)])))
    assert len(recs) == 1
    assert recs[0]["stable_id"].startswith("census_")
    assert -640.0 <= recs[0]["x"] <= 640.0
    again = to_world(detect(_synthetic([(100, 100, 6)])))
    assert again[0]["stable_id"] == recs[0]["stable_id"]


def test_density_zones():
    recs = [{"x": 0.0, "z": 0.0}, {"x": 10.0, "z": 0.0}]
    d = density_stats(recs, {"c": {"circle": (0.0, 0.0, 20.0)}})
    assert d["c"]["n"] == 2
    assert abs(d["c"]["trees_per_ha"] - 2 / (math.pi * 400 / 1e4)) < 0.5


@pytest.mark.needs_world
def test_rim_artifacts_excluded():
    # Grand Prismatic center is mapped water; its detection is a rim artifact; far-field records pass.
    recs = [{"x": -94.7, "z": -10.6}, {"x": -500.0, "z": 400.0}]
    kept, dropped = exclude_pool_rims(recs)
    assert dropped == 1
    assert kept == [{"x": -500.0, "z": 400.0}]


def _census_doc(n=20, **kw):
    trees = [{"stable_id": f"census_{i:04d}_0000", "x": float(i),
              "z": 0.0, "crown_r_m": 2.0, "peak_exg": 0.2,
              "confidence": "high",
              "evidence_class": "synthetic"} for i in range(n)]
    doc = {"schema": "yellowstone.canopy_census.v1", "n": n, "trees": trees}
    doc.update(kw)
    return doc


def test_qa_selfcheck_passes_on_v1_fixture():
    assert qa_census(_census_doc()) == []


def test_qa_catches_count_mismatch():
    doc = _census_doc(n=20)
    doc["n"] = 19
    failures = qa_census(doc)
    assert any(f.startswith("count:") for f in failures)


def test_qa_catches_bad_confidence():
    doc = _census_doc(n=2)
    doc["trees"][1]["confidence"] = "ultra"
    failures = qa_census(doc)
    assert any("census_0001_0000" in f and "confidence" in f for f in failures)


def test_qa_catches_cap_violation():
    doc = _census_doc(n=1)
    doc["trees"][0]["crown_r_m"] = 9.0
    assert any(f.startswith("cap:") for f in qa_census(doc))


def test_calibrate_refuses_few_lone():
    img = _synthetic([(100, 100, 6)])
    with pytest.raises(ValueError, match="cannot calibrate"):
        calibrate_lone_trees(img)


def test_detect_v2_topup_shape():
    img = _synthetic([(60, 60, 10), (140, 140, 10)])
    cal = {"n_lone": 12, "median_area_px": 300.0, "p95_area_px": 400.0,
           "median_crown_r_m": 2.0}
    out = detect_v2(img, calibration=cal)
    assert len(out) >= 2
    assert all("splitting_basis" in r for r in out)
    assert all(r["splitting_basis"] in ("peak", "area_topup") for r in out)


def test_docstring_matches_parser():
    import subprocess
    import sys
    from pathlib import Path
    help_text = subprocess.run(
        [sys.executable, "-m", "yellowstone_python.census.canopy_census", "--help"],
        capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1],
    ).stdout
    assert "--qa" in help_text
    import yellowstone_python.census.canopy_census as cc
    assert "--qa" in (cc.__doc__ or "")


def test_live_census_qa_status():
    from pathlib import Path
    live = Path(__file__).resolve().parents[1] / "derived" / "census.json"
    import json
    failures = qa_census(json.loads(live.read_text()))
    assert failures == [], failures


def test_qa_overlapping_density_zones_pass():
    doc = _census_doc(n=10)
    doc["density"] = {"a": {"n": 8}, "b": {"n": 8}}  # overlap allowed
    assert qa_census(doc) == []


def test_qa_oversized_zone_fails():
    doc = _census_doc(n=10)
    doc["density"] = {"a": {"n": 11}}
    assert any(f.startswith("density:") for f in qa_census(doc))
