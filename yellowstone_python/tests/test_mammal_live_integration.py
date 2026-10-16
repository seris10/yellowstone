"""Mammal ecology coupling through the physical-time live service."""
from yellowstone_python.river.river_transport import Cell, River
from yellowstone_python.service.live import LiveEngine


def model():
    river = River([Cell("a", 20.0, 10.0, 200.0, 15.0)], 5.0, 15.0)
    config = {
        "mammals": {"enabled": True, "seed": 54173},
        "patches": [{"id": "meadow", "habitat": "dry_meadow", "center_xz": [0.0, 0.0],
                     "biomass": 0.7, "capacity": 1.0, "moisture": 0.6}],
        "wildlife": [{"id": "bison", "kind": "bison", "species_id": "bison_bison",
                      "patch_id": "meadow", "mammal_guild": "grazer",
                      "grazing_owner": "legacy_grazers", "encounter_probability": 1.0}],
    }
    return LiveEngine(river, config, horizon_s=60.0, frame_interval_s=10.0)


def test_control_refreshes_mammal_forcing_at_the_same_physical_time():
    engine = model()
    before = engine.frames()["frames"][0]["ecology"]["mammals"]
    result = engine.command("control", {"at_s": 0.0, "changes": {"weather.night_air_c": -20.0}})
    after = engine.frames()["frames"][0]["ecology"]["mammals"]
    assert "mammals" in result["dirty_stages"]
    assert before["elapsed_s"] == after["elapsed_s"] == 0.0
    assert after["actors"]["bison"]["activity_index"] < before["actors"]["bison"]["activity_index"]
    assert after["actors"]["bison"]["population_measurement"] is None


def test_mammal_checkpoint_replay_matches_a_fresh_run_and_food_budget():
    engine = model()
    engine.compute_until(30.0)
    checkpoint = engine._checkpoint()
    engine.compute_until(60.0)
    first = engine.frames()["frames"][-1]["ecology"]["mammals"]
    engine._restore(checkpoint)
    engine.compute_until(60.0)
    replayed = engine.frames()["frames"][-1]["ecology"]["mammals"]
    fresh = model()
    fresh.compute_until(60.0)
    expected = fresh.frames()["frames"][-1]["ecology"]["mammals"]
    assert first == replayed == expected
    assert expected["elapsed_s"] == 60.0
    assert abs(expected["vegetation_coupling"]["residual"]) < 1e-12
    assert "bison" in expected["ledger"]["external_legacy_grazing_ids"]
