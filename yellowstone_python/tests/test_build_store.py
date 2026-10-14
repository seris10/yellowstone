"""Tests for tools/build_store.py: CLI contract, parse-error cleanup, BUILD.json sha cross-check."""
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOL = REPO_ROOT / "tools" / "build_store.py"


def _census_doc():
    return {"schema": "yellowstone.canopy_census.v1", "n": 1,
            "trees": [{"stable_id": "t", "x": 0.0, "z": 0.0,
                       "crown_r_m": 1.0, "confidence": "high",
                       "peak_exg": 0.1, "evidence_class": "synthetic"}]}


def _replay_doc():
    return {"cells": [{"id": "c", "river_id": "r",
                       "start_s_m": 0.0, "end_s_m": 10.0, "length_m": 10.0,
                       "width_m": 10.0, "depth_m": 0.5, "volume_m3": 50.0,
                       "representative_velocity_m_s": 0.5}],
            "frames": [{"t_s": 0.0, "temperature_c": [10.0]}]}


def _firehole_doc():
    return {"schema": "yellowstone.firehole_obs.v1",
            "sites": {"S": {"series": {"discharge_m3_s": [[1.0, 1.0]],
                                        "temperature_c": [[1.0, 10.0]]}}}}


def _snotel_doc():
    return {"schema": "yellowstone.snotel_obs.v1",
            "sites": {"X": {"days": {"2026-01-01": {"WTEQ": 1.0}}}}}


def _write_minimal_tree(tmp_path: Path) -> dict:
    build_dir = tmp_path / "derived" / "deadbeef"
    build_dir.mkdir(parents=True)
    (build_dir / "river_replay.json").write_text(json.dumps(_replay_doc()))
    derived = tmp_path / "derived"
    census = derived / "census.json"
    firehole = derived / "firehole_obs.json"
    snotel = derived / "snotel_obs.json"
    census.write_text(json.dumps(_census_doc()))
    firehole.write_text(json.dumps(_firehole_doc()))
    snotel.write_text(json.dumps(_snotel_doc()))
    return {"build_dir": build_dir, "census": census,
            "firehole": firehole, "snotel": snotel, "derived": derived}


def _run(args, cwd):
    env = {"PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, str(TOOL), *args],
        cwd=str(cwd), env={**env, "PATH": ""}, capture_output=True,
        text=True, check=False)


def test_build_store_cli_runs(tmp_path):
    t = _write_minimal_tree(tmp_path)
    result = _run(["--build", str(t["build_dir"]),
                   "--census", str(t["census"]),
                   "--firehole", str(t["firehole"]),
                   "--snotel", str(t["snotel"]),
                   "--out", str(tmp_path / "store.sqlite")],
                  cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "store.sqlite").exists()
    summary = json.loads(result.stdout.splitlines()[-1]
                         if result.stdout.count("\n") <= 1
                         else result.stdout[result.stdout.index("{"):])
    assert summary["build_id"] == "deadbeef"


def test_malformed_fit_clean_exit(tmp_path):
    t = _write_minimal_tree(tmp_path)
    bad_fit = tmp_path / "derived" / "bad_reach.json"
    bad_fit.write_text("{not valid json")
    result = _run(["--build", str(t["build_dir"]),
                   "--census", str(t["census"]),
                   "--firehole", str(t["firehole"]),
                   "--snotel", str(t["snotel"]),
                   "--reach-fit", str(bad_fit),
                   "--out", str(tmp_path / "store.sqlite")],
                  cwd=tmp_path)
    assert result.returncode == 1
    assert "build-failed" in result.stderr
    assert "Traceback" not in result.stderr


def test_sha_mismatch_against_build_json(tmp_path):
    t = _write_minimal_tree(tmp_path)
    fit = tmp_path / "derived" / "reach_heat_fit.json"
    fit.write_text(json.dumps({"status": "fitted_not_validated_single_window",
                               "effective_geometry": {"volume_m3": 300000.0},
                               "champion": {}}))
    # Record a sha that does not match the contents.
    wrong_sha = "0" * 64
    (t["build_dir"] / "BUILD.json").write_text(json.dumps(
        {"build_id": "deadbeef",
         "deps": {"reach_heat_fit.json": wrong_sha}}))
    result = _run(["--build", str(t["build_dir"]),
                   "--census", str(t["census"]),
                   "--firehole", str(t["firehole"]),
                   "--snotel", str(t["snotel"]),
                   "--reach-fit", str(fit),
                   "--out", str(tmp_path / "store.sqlite")],
                  cwd=tmp_path)
    assert result.returncode == 2
    assert "source-sha-mismatch" in result.stderr


def test_unreferenced_fit_warns_but_passes(tmp_path):
    t = _write_minimal_tree(tmp_path)
    fit = tmp_path / "derived" / "reach_polished_fit_v300k.json"
    fit.write_text(json.dumps({"status": "fitted_not_validated_single_window",
                               "effective_geometry": {"volume_m3": 300000.0},
                               "champion": {}}))
    (t["build_dir"] / "BUILD.json").write_text(json.dumps(
        {"build_id": "deadbeef", "deps": {"world.json": "a" * 64}}))
    result = _run(["--build", str(t["build_dir"]),
                   "--census", str(t["census"]),
                   "--firehole", str(t["firehole"]),
                   "--snotel", str(t["snotel"]),
                   "--reach-fit", str(fit),
                   "--out", str(tmp_path / "store.sqlite")],
                  cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert "not referenced by BUILD.json" in result.stdout
