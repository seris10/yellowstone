"""Synthetic terrain guard and CLI checks."""

import subprocess
import sys
from pathlib import Path

import numpy as np

from yellowstone_python.validation.terrain import (DEFAULT_MAX_M, DEFAULT_MIN_M, N_BYTES,
                                 guard_terrain)

TOOL = Path(__file__).resolve().parents[1] / "tools" / "check_terrain.py"
LIVE_MIN, LIVE_MAX = -10.89, 238.13


def _fixture(path: Path, shape=(1025, 1025), fill=50.0) -> Path:
    rows, cols = shape
    # Linear ramp in rows plus a per-column modulation so slope is non-zero (the flat-cell guard needs a gradient).
    r = np.arange(rows, dtype="<f4").reshape(rows, 1)
    c = np.arange(cols, dtype="<f4").reshape(1, cols)
    arr = (np.full(shape, fill, dtype="<f4")
           + (r * 0.001).astype("<f4")
           + (c * 0.0005).astype("<f4"))
    arr.tofile(str(path))
    return path


def test_good_fixture_passes(tmp_path):
    import hashlib
    p = _fixture(tmp_path / "t.f32")
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    report = guard_terrain(p, sha, DEFAULT_MIN_M, DEFAULT_MAX_M)
    assert report["passed"] is True
    assert report["terrain"]["dims"] == [1025, 1025]


def test_truncated_fails_size(tmp_path):
    p = tmp_path / "t.f32"
    np.zeros(1000, dtype="<f4").tofile(str(p))
    report = guard_terrain(p, None, DEFAULT_MIN_M, DEFAULT_MAX_M)
    assert report["passed"] is False
    assert any(g["name"] == "size" and "bad-size" in g["detail"]
               for g in report["guards"])


def test_wrong_shape_fails(tmp_path):
    # 1025x1024 has the wrong byte size; the size guard fires first and the grid guard covers the same invariant post-read.
    p = _fixture(tmp_path / "t.f32", shape=(1025, 1024))
    assert p.stat().st_size != N_BYTES
    report = guard_terrain(p, None, DEFAULT_MIN_M, DEFAULT_MAX_M)
    assert report["passed"] is False
    assert any(not g["passed"] for g in report["guards"])


def test_out_of_range_fails(tmp_path):
    p = _fixture(tmp_path / "t.f32", fill=999.0)
    report = guard_terrain(p, None, DEFAULT_MIN_M, DEFAULT_MAX_M)
    assert report["passed"] is False
    assert any(g["name"] == "range" and "999" in g["detail"]
               for g in report["guards"])


def test_hash_mismatch_names_both(tmp_path):
    p = _fixture(tmp_path / "t.f32")
    report = guard_terrain(p, "0" * 64, DEFAULT_MIN_M, DEFAULT_MAX_M)
    assert report["passed"] is False
    detail = next(g["detail"] for g in report["guards"] if g["name"] == "hash")
    assert "0" * 64 in detail and report["terrain"]["sha256"] in detail


def test_defaults_justify_envelope():
    assert DEFAULT_MIN_M < LIVE_MIN
    assert DEFAULT_MAX_M > LIVE_MAX


def test_missing_file_exit1(tmp_path):
    r = subprocess.run([sys.executable, str(TOOL), "--terrain",
                        str(tmp_path / "nope.f32")],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "terrain-unreadable" in r.stdout


def test_enclosing_build_hash_picked_up(tmp_path):
    import hashlib
    import json
    build_dir = tmp_path / "build123"
    build_dir.mkdir()
    p = _fixture(build_dir / "terrain.f32")
    sha = hashlib.sha256(p.read_bytes()).hexdigest()
    (build_dir / "BUILD.json").write_text(json.dumps(
        {"deps": {"terrain.f32": sha}}))
    r = guard_terrain(p, None, DEFAULT_MIN_M, DEFAULT_MAX_M)
    assert r["passed"] is True  # no expect: hash guard skipped
    assert not any(g["name"] == "hash" for g in r["guards"])
    import subprocess
    cli = subprocess.run([sys.executable, str(TOOL), "--terrain", str(p)],
                         capture_output=True, text=True)
    assert cli.returncode == 0
    assert "PASS hash" in cli.stdout
