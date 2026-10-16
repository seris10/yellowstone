import copy
import json
import math
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from yellowstone_python.park_runtime import legacy_adapter, parity
from yellowstone_python.park_runtime.legacy_adapter import LegacyLiveDomain
from yellowstone_python.park_runtime.runtime import ParkRuntime
from yellowstone_python.park_runtime.state_store import StateStore
from yellowstone_python.river.river_transport import Cell, River, Source, SurfaceBudget, Series
from yellowstone_python.service.live import LiveEngine, state_codec
from yellowstone_python.service.live.state_codec import StateCodecError, UnsupportedStateError

HORIZON_S = 60.0
INTERVAL_S = 10.0


def make_engine(build_id="synthetic", mammals=True, weather=False):
    river = River([Cell("a", 20.0, 10.0, 200.0, 15.0), Cell("b", 20.0, 10.0, 200.0, 14.0)], 5.0, 15.0,
                  sources=[Source("excelsior_aggregate_outflow", "b", 0.2, 62.0)],
                  surface_budget=SurfaceBudget.parse({"rh": 0.5, "wind_mps": 2.0, "shortwave_w_m2": 600.0, "cloud": 0.2}))
    config = {"live": {"foodweb_interval_s": 10.0, "aquatic_interval_s": 10.0},
              "patches": [{"id": "meadow", "habitat": "dry_meadow", "center_xz": [0.0, 0.0],
                           "biomass": 0.7, "capacity": 1.0, "moisture": 0.6, "soil_mm": 60.0, "snow_mm": 5.0}]}
    if mammals:
        config["mammals"] = {"enabled": True, "seed": 54173}
        config["wildlife"] = [{"id": "bison", "kind": "bison", "species_id": "bison_bison", "patch_id": "meadow",
                               "mammal_guild": "grazer", "grazing_owner": "legacy_grazers",
                               "encounter_probability": 1.0}]
    if weather:
        config["weather"] = {"night_air_c": 6.0}
    return LiveEngine(river, config, horizon_s=HORIZON_S, frame_interval_s=INTERVAL_S, build_id=build_id)


def runtime_for(engine):
    return ParkRuntime([LegacyLiveDomain(engine, "midway.firehole")], quantum_s=engine.frame_interval_s,
                       history_s=2 * engine.horizon_s, epoch_unix=engine.epoch_origin, max_frames=64)


def science(frame):
    """Return a frame without wall-clock performance fields."""
    result = copy.deepcopy(frame)
    for name in ("timings", "session_id", "compute_rate_sps", "max_dt_capacity_sps", "max_supported_time_scale",
                 "dirty_stages"):
        result["header"].pop(name)
    return result


def test_wrappers_return_copies_and_restore_the_frontier():
    engine = make_engine()
    engine.compute_until(30.0)
    frame = engine.snapshot_at_frontier()
    frame["temperature_c"][0] = -99.0
    assert engine.snapshot_at_frontier()["temperature_c"][0] != -99.0
    state = engine.checkpoint_state()
    engine.compute_until(60.0)
    expected = science(engine.snapshot_at_frontier())
    engine.restore_state(state)
    assert engine.river.time_s == 30.0
    assert engine.frames()["frames"][-1]["t_s"] == 30.0
    engine.compute_until(60.0)
    assert science(engine.snapshot_at_frontier()) == expected
    assert not engine.worker_running


def test_trim_history_keeps_the_frontier():
    engine = make_engine()
    engine.compute_until(60.0)
    engine.trim_history(40.0)
    times = [frame["t_s"] for frame in engine.frames()["frames"]]
    assert times == [40.0, 50.0, 60.0]


def test_adapter_uses_only_public_engine_surface():
    source = Path(legacy_adapter.__file__).read_text()
    assert "engine._" not in source


def test_adapter_rejects_a_running_worker():
    engine = make_engine()
    engine.start()
    try:
        with pytest.raises(ValueError):
            LegacyLiveDomain(engine)
    finally:
        engine.close()


@pytest.mark.parametrize("value", [
    None, True, 3, 2.5, "text", [1, [2.0]], (1, 2.0), {"a": (1, 2)}, {1: "x", 2.5: "y"}, {"$t": "literal"},
    float("nan"), float("inf"), -float("inf"), np.arange(6.0).reshape(2, 3), np.array([1, 2], dtype="int32"),
    Series((0.0, 5.0), (1.0, 2.0)), Source("s", "a", 0.1, 20.0),
    SurfaceBudget.parse({"rh": 0.5, "wind_mps": 2.0, "shortwave_w_m2": 600.0, "cloud": 0.2})])
def test_value_codec_round_trips_exactly(value):
    wire = json.loads(json.dumps(state_codec.encode_value(value), allow_nan=False))
    back = state_codec.decode_value(wire)
    if isinstance(value, np.ndarray):
        assert back.dtype == value.dtype and back.shape == value.shape and np.array_equal(back, value)
    elif isinstance(value, float) and math.isnan(value):
        assert math.isnan(back)
    else:
        assert back == value and type(back) is type(value)


@pytest.mark.parametrize("value", [object(), {"set"}, {1, 2}, np.array(["a"]), b"bytes", 1 + 2j])
def test_value_codec_refuses_unknown_types(value):
    with pytest.raises(StateCodecError):
        state_codec.encode_value(value)


@pytest.mark.parametrize("wire", [{"$t": "unknown"}, {"$t": "dataclass", "name": "os.system", "v": {}},
                                  {"$t": "ndarray", "dtype": "O", "shape": [1], "v": [0]}])
def test_value_decoder_refuses_unlisted_constructors(wire):
    with pytest.raises(StateCodecError):
        state_codec.decode_value(wire)


def test_config_delta_rebuilds_the_current_configuration():
    base = {"a": {"b": 1, "c": [1, 2]}, "d": 5, "e": {"f": 1.0}}
    current = {"a": {"b": 1, "c": [1, 3], "n": None}, "d": 5.0, "g": (1, 2)}
    delta = state_codec.config_delta(base, current)
    rebuilt = state_codec.apply_config_delta(base, json.loads(json.dumps(delta)))
    assert rebuilt == current and type(rebuilt["d"]) is float
    assert "e" in delta["drop"] and delta["change"]["a"]["change"].keys() == {"c"}


def test_exported_state_resumes_on_a_fresh_engine_bit_identically():
    first = make_engine()
    first.compute_until(30.0)
    first.command("control", {"at_s": 20.0, "changes": {"hydro.boundary_c": 21.0, "weather.night_air_c": -3.0}})
    first.compute_until(40.0)
    document = first.export_state(first.checkpoint_state(), revision=first.revision)
    wire = json.loads(json.dumps(document, allow_nan=False))
    first.compute_until(70.0)
    second = make_engine()
    second.import_state(wire)
    assert second.river.time_s == 40.0 and second.revision == first.revision
    second.compute_until(70.0)
    assert science(second.snapshot_at_frontier()) == science(first.snapshot_at_frontier())
    assert second.checkpoint_state()["solutes"]._totals == first.checkpoint_state()["solutes"]._totals
    assert second.river.budget() == first.river.budget()
    assert second.ecology["mammal_model"].checkpoint() == first.ecology["mammal_model"].checkpoint()
    assert second._integration_segments == first._integration_segments


def test_document_carries_every_state_group_and_model_versions():
    engine = make_engine()
    engine.compute_until(20.0)
    document = engine.export_state(engine.checkpoint_state(), revision=3)
    assert document["schema"] == state_codec.SCHEMA and document["revision"] == 3
    for group in ("river", "solutes", "ecology", "mammals", "config", "forcing_sha256", "integration_segments",
                  "forcing_catalog", "model_versions", "identity"):
        assert document[group] is not None
    assert set(document["river"]) >= {"temperature_c", "totals", "forcing", "hyporheic_t_c"}
    assert set(document["solutes"]) >= {"concentrations", "totals", "water_totals"}
    assert document["model_versions"]["mammal_data_sha256"] == engine.ecology["mammal_model"].catalogue_sha
    assert all(len(sha) == 64 for sha in document["model_versions"]["source_sha256"].values())
    assert "mammal_model" not in document["ecology"]
    assert document["config"]["op"] == "keep"


def test_document_is_smaller_than_the_native_configuration():
    engine = make_engine()
    engine.compute_until(20.0)
    document = engine.export_state(engine.checkpoint_state(), revision=0)
    assert len(json.dumps(document["config"])) < 100
    assert "patches" not in json.dumps(document["config"])


def test_import_refuses_other_builds_policies_and_schema():
    engine = make_engine()
    engine.compute_until(20.0)
    document = json.loads(json.dumps(engine.export_state(engine.checkpoint_state(), revision=0)))
    with pytest.raises(StateCodecError, match="different build"):
        make_engine(build_id="other").import_state(document)
    with pytest.raises(StateCodecError, match="mammal"):
        make_engine(mammals=False).import_state(document)
    other = make_engine()
    other.frame_interval_s = 5.0
    with pytest.raises(StateCodecError, match="different build"):
        other.import_state(document)
    document["schema"] = "yellowstone.live_engine_state.v0"
    with pytest.raises(StateCodecError, match="schema"):
        make_engine().import_state(document)


def test_import_refuses_source_drift_unless_accepted():
    engine = make_engine()
    engine.compute_until(20.0)
    document = json.loads(json.dumps(engine.export_state(engine.checkpoint_state(), revision=0)))
    module = next(iter(document["model_versions"]["source_sha256"]))
    document["model_versions"]["source_sha256"][module] = "0" * 64
    target = make_engine()
    with pytest.raises(StateCodecError, match=module):
        target.import_state(document)
    assert target.river.time_s == 0.0
    target.import_state(document, accept_source_drift=True)
    assert target.river.time_s == 20.0


def test_import_detects_forcing_corruption():
    engine = make_engine()
    engine.compute_until(20.0)
    document = json.loads(json.dumps(engine.export_state(engine.checkpoint_state(), revision=0)))
    document["forcing_sha256"] = "0" * 64
    with pytest.raises(StateCodecError, match="digest"):
        make_engine().import_state(document)


def test_branch_and_measured_state_are_refused():
    engine = make_engine()
    engine.compute_until(20.0)
    engine.command("mark", {"at_s": 20.0})
    with pytest.raises(UnsupportedStateError):
        engine.export_state(engine.checkpoint_state(), revision=0)


def test_diverged_segment_history_is_refused():
    engine = make_engine()
    engine.compute_until(30.0)
    state = engine.checkpoint_state()
    engine.compute_until(20.0 + 10.0)
    engine._integration_segments[state["integration_segment_count"] - 1]["end_s"] += 1.0
    with pytest.raises(StateCodecError, match="diverged"):
        engine.export_state(state, revision=0)


def test_runtime_save_and_load_resume_the_same_history(tmp_path):
    runtime = runtime_for(make_engine())
    runtime.compute_until(30.0)
    runtime.intervene("event-1", "midway.firehole", 20.0, {"hydro.boundary_c": 19.0})
    runtime.compute_until(40.0)
    store = StateStore(tmp_path / "state.sqlite3")
    assert runtime.save_committed(store, "world", 35.0) == 30.0
    runtime.compute_until(60.0)
    expected = science(runtime.domains["midway.firehole"].snapshot()["frame"])
    resumed = runtime_for(make_engine())
    assert resumed.load_committed(store, "world")
    assert resumed.time_s == 30.0 and resumed.revision == runtime.revision
    assert [event["event_id"] for event in resumed.events] == ["event-1"]
    resumed.compute_until(60.0)
    assert science(resumed.domains["midway.firehole"].snapshot()["frame"]) == expected
    store.close()


def test_saved_payload_is_plain_json_with_no_pickle(tmp_path):
    runtime = runtime_for(make_engine())
    runtime.compute_until(20.0)
    store = StateStore(tmp_path / "state.sqlite3")
    runtime.save_committed(store, "world", 20.0)
    saved = store.load("world", runtime.model_id)["checkpoint"]
    state = saved["domains"]["midway.firehole"]["state"]
    assert state["schema"] == state_codec.SCHEMA
    store.close()


def test_unportable_state_refuses_the_save_and_writes_nothing(tmp_path):
    engine = make_engine()
    runtime = runtime_for(engine)
    runtime.compute_until(20.0)
    engine.command("mark", {"at_s": 20.0})
    runtime._record()
    store = StateStore(tmp_path / "state.sqlite3")
    with pytest.raises(UnsupportedStateError):
        runtime.save_committed(store, "world", 20.0)
    assert store.load("world", runtime.model_id) is None
    store.close()


def test_store_refuses_arbitrary_objects_and_nonfinite_numbers(tmp_path):
    store = StateStore(tmp_path / "state.sqlite3")
    with pytest.raises(TypeError):
        store.save("w", "m", 0.0, 0, {"value": object()})
    with pytest.raises(ValueError):
        store.save("w", "m", 0.0, 0, {"value": float("nan")})
    assert store.load("w", "m") is None
    store.close()


def test_tampered_save_fails_the_checksum(tmp_path):
    runtime = runtime_for(make_engine())
    runtime.compute_until(20.0)
    path = tmp_path / "state.sqlite3"
    store = StateStore(path)
    runtime.save_committed(store, "world", 20.0)
    store.close()
    db = sqlite3.connect(path)
    db.execute("UPDATE checkpoints SET sha256=?", ("0" * 64,))
    db.commit()
    db.close()
    store = StateStore(path)
    with pytest.raises(ValueError, match="checksum"):
        runtime_for(make_engine()).load_committed(store, "world")
    store.close()


def test_in_memory_rollback_matches_a_continuous_run():
    runtime = runtime_for(make_engine())
    runtime.compute_until(40.0)
    runtime.intervene("event-1", "midway.firehole", 20.0, {"hydro.boundary_m3s": 6.0})
    runtime.compute_until(60.0)
    direct = make_engine()
    direct.compute_until(20.0)
    direct.command("control", {"at_s": 20.0, "changes": {"hydro.boundary_m3s": 6.0}})
    direct.compute_until(60.0)
    assert science(runtime.domains["midway.firehole"].snapshot()["frame"]) == science(direct.snapshot_at_frontier())


@pytest.mark.parametrize("weather", [False, True])
def test_native_and_adapter_agree_on_every_field_and_budget(weather):
    report = parity.compare_native_and_adapter(
        lambda: make_engine(weather=weather), end_s=40.0,
        intervention={"at_s": 20.0, "changes": {"hydro.boundary_c": 19.0}})
    assert report["passed"], report["mismatches"]
    assert report["frames_compared"] >= 5 and report["mismatch_count"] == 0
    assert {"temperature_c[]", "cells[].oxygen_mg_l"} <= set(report["advertised_fields"])
    assert any(name.startswith("ecology.mammals.ledger.") for name in report["advertised_fields"])
    assert any(name.startswith("solute_mass") for name in report["budget_fields"])
    assert any(name.startswith("river") for name in report["budget_fields"])


def test_parity_reports_a_perturbed_field():
    left = {"a": [1.0, 2.0], "header": {"timings": {"x": 1}}, "n": 1}
    right = {"a": [1.0, 2.0000001], "header": {"timings": {"x": 2}}, "n": 1}
    exact = parity.compare_frames(left, right, abs_tol=0.0, rel_tol=0.0)
    assert [row["path"] for row in exact["mismatches"]] == ["a[1]"]
    loose = parity.compare_frames(left, right, abs_tol=1e-6, rel_tol=0.0)
    assert not loose["mismatches"] and loose["max_abs"] > 0
