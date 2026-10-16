"""Behavior checks for hot low-flow scenario subcommands on synthetic replay inputs."""
from __future__ import annotations

import json

import pytest

from tools.hot_lowflow import main
from yellowstone_python.scenarios import hot_lowflow as scenarios


def replay(temperature_c):
    cells = [{"id": f"cell_{i:03d}", "river_id": "test", "center_s_m": i * 100.0,
              "start_s_m": i * 100.0, "end_s_m": (i + 1) * 100.0,
              "width_m": 20.0, "depth_m": 0.5, "representative_velocity_m_s": 0.5,
              "volume_m3": 1000.0} for i in range(3)]
    frames = [{"t_s": k * 60.0, "temperature_c": [temperature_c] * 3} for k in range(4)]
    return {"cells": cells, "frames": frames, "run_mode": "illustrative"}


@pytest.fixture
def inputs(tmp_path):
    control, pulse = tmp_path / "control.json", tmp_path / "pulse.json"
    control.write_text(json.dumps(replay(17.5)))
    pulse.write_text(json.dumps(replay(27.0)))
    return control, pulse


def run_arguments(command, inputs, tmp_path):
    return [command, "--control", str(inputs[0]), "--pulse", str(inputs[1]),
            "--out", str(tmp_path / "comparison.json"),
            "--out-replay", str(tmp_path / "output_replay.json"), "--days", "0.1"]


def assert_solver_cells_preserved(inputs, output):
    source = json.loads(inputs[1].read_text())
    assert [c["id"] for c in output["cells"]] == [c["id"] for c in source["cells"]]
    assert all(len(frame["temperature_c"]) == len(source["cells"]) for frame in output["frames"])
    assert source["run_mode"] == "illustrative"


def test_mainstem_emits_scenario_and_source_values(inputs, tmp_path):
    assert main(run_arguments("mainstem", inputs, tmp_path)) == 0
    document = json.loads((tmp_path / "comparison.json").read_text())
    scenario = document["scenario"]
    assert scenario["run_mode"] == "scenario"
    assert scenario["boundary_m3s"] == 2.5
    assert scenario["boundary_c"] == 26.0
    assert scenario["refuge_threshold_c"] == 24.0
    for field in ("boundary_m3s_source", "boundary_c_source", "observed_max_c_source",
                  "uilt_c_source", "refuge_threshold_source"):
        assert scenario[field]["citation"]
        assert scenario[field]["value_cited_in_file"]
    assert_solver_cells_preserved(inputs, json.loads((tmp_path / "output_replay.json").read_text()))


def test_authored_pockets_sweeps_and_scope(inputs, tmp_path):
    args = run_arguments("tributary-pockets", inputs, tmp_path)
    args += ["--out-sweep", str(tmp_path / "sweep.json"),
             "--out-single-pocket", str(tmp_path / "single.json")]
    assert main(args) == 0
    document = json.loads((tmp_path / "comparison.json").read_text())
    sweep = json.loads((tmp_path / "sweep.json").read_text())
    assert document["scenario"]["run_mode"] == "scenario"
    assert document["scenario"]["starvation_absent"] is True
    assert document["scenario"]["model_scope"]
    assert [row["trib_temp_c"] for row in sweep["temperature_sweep_at_default_size"]] == [8, 11, 14, 17, 20, 23, 24, 25, 26]
    assert [row["food_scale"] for row in sweep["size_sweep_at_spec_temp"]] == [0, 0.01, 0.05, 0.2, 1]
    assert [(row["pocket_velocity_m_s"], row["pocket_depth_m"]) for row in sweep["velocity_depth_sweep"]] == [(0.1, 0.3), (0.25, 0.5), (0.5, 1)]
    assert len(json.loads((tmp_path / "single.json").read_text())["scenario"]["tributary_cells"]) == 1
    assert_solver_cells_preserved(inputs, json.loads((tmp_path / "output_replay.json").read_text()))


def test_measured_tributaries_require_an_existing_file(inputs, tmp_path, capsys):
    missing = tmp_path / "missing_tributaries.json"
    args = run_arguments("measured-tributaries", inputs, tmp_path) + ["--tributary-data", str(missing)]
    with pytest.raises(SystemExit) as error:
        main(args)
    assert error.value.code == 2
    assert str(missing) in capsys.readouterr().err
    assert not (tmp_path / "comparison.json").exists()
    assert not (tmp_path / "output_replay.json").exists()


def test_measured_tributaries_leave_transport_cells_intact(inputs, tmp_path):
    evidence = tmp_path / "tributaries.json"
    evidence.write_text(json.dumps({"schema": "yellowstone.tributary_evidence.v1",
        "cold_refuge_candidates": [{"site_id": "test_creek", "confluence_s_m": 100.0,
            "temperature_c": 11.0, "discharge_m3s": 0.2, "habitat_area_m2": 22.0}]}))
    args = run_arguments("measured-tributaries", inputs, tmp_path) + ["--tributary-data", str(evidence)]
    assert main(args) == 0
    output = json.loads((tmp_path / "output_replay.json").read_text())
    assert output["run_mode"] == "scenario"
    assert len(output["landscape_pocket_cells"]) == 1
    assert output["landscape_pocket_cells"][0]["conservation"] == "non_conservative"
    assert_solver_cells_preserved(inputs, output)


def test_measured_tributaries_reject_authored_fallback(inputs, tmp_path):
    evidence = tmp_path / "authored.json"
    evidence.write_text(json.dumps({"schema": "yellowstone.tributaries_fallback.v1", "scientific_use": "prohibited"}))
    with pytest.raises(SystemExit):
        main(run_arguments("measured-tributaries", inputs, tmp_path) + ["--tributary-data", str(evidence)])


def test_window_uses_replay_clock_and_settling_floor():
    assert scenarios._window(60.0, replay(27.0)) == (60.0, 181.0)
    assert scenarios._window(0.0, replay(27.0)) is None


@pytest.mark.parametrize("field,value", [
    ("velocity", True), ("velocity", "0.1"), ("velocity", float("nan")), ("velocity", -0.1),
    ("depth", False), ("depth", "0.5"), ("depth", float("inf")), ("depth", 0.0),
])
def test_pocket_geometry_rejects_coercible_or_nonphysical_overrides(field, value):
    with pytest.raises(ValueError, match="velocity_m_s|depth_m"):
        scenarios.run_case(replay(17.5), replay(27.0), list(scenarios.TRIBUTARY_CANDIDATES),
                           None, scenarios.TRIBUTARY_FOOD_SCALE_DEFAULT, 0.1, "brown_trout", **{field: value})


@pytest.mark.parametrize("value", [True, "27.0", float("nan"), float("inf")])
def test_quasi_steady_diagnostic_rejects_invalid_temperature_values(value):
    pulse = replay(27.0)
    pulse["frames"][0]["temperature_c"][0] = value
    with pytest.raises(ValueError, match="frame temperature_c"):
        scenarios._quasi_steady_check(pulse)


@pytest.mark.parametrize("value", [True, "60.0", float("nan")])
def test_settling_window_rejects_invalid_floor_values(value):
    with pytest.raises(ValueError, match="settle_s"):
        scenarios._window(value, replay(27.0))
