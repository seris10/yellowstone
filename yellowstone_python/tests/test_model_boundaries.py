"""River execution parity and interval-owned land transfers."""
import copy

import pytest

from yellowstone_python.land.snow_season import run_season, step_land, step_soil_bucket
from yellowstone_python.pipeline.stages.land import _overland_boundary_series, _overland_runoff_to_boundary, run as run_land
from yellowstone_python.river.river_transport import make_replay, river_from_config
from yellowstone_python.service.live import LiveEngine
from yellowstone_python.service.live.engine import replay_config


@pytest.mark.parametrize("explicit", [False, True])
@pytest.mark.parametrize("varying", [False, True])
@pytest.mark.parametrize("speed", [1., 60., 600.])
def test_same_model_and_forcing_produce_equal_baked_live_trajectories(explicit, varying, speed):
    config = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 12.},
                        {"id": "b", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 14.}],
              "boundary_m3_s": 5., "boundary_c": {"times_s": [0., 60.], "values": [15., 22.]} if varying else 15.,
              "air_c": {"times_s": [0., 60.], "values": [8., 10.]} if varying else 8.,
              "initialize_steady": False}
    if explicit:
        config["surface_budget"] = {"rh": .45, "wind_mps": 2., "shortwave_w_m2": 200., "cloud": .16}
    baked = river_from_config(config)
    live = LiveEngine(river_from_config(config), {"live": {"dt_s": 1.}},
                      epoch_unix=1782064800., frame_interval_s=10., time_scale=speed)
    expected_strategy = "explicit_surface_budget" if explicit else "newton_exchange"
    assert live._header()["exchange_strategy"] == expected_strategy
    for end in (10., 60., 120.):
        baked.run(end - baked.time_s, dt_s=1., sample_s=end - baked.time_s)
        live.compute_until(end)
        assert live.river.temperature_c == pytest.approx(baked.temperature_c, abs=1e-11)
        assert live.river.budget()["heat_relative_residual"] == pytest.approx(
            baked.budget()["heat_relative_residual"], abs=1e-12)
    assert live._header()["dt_s"] == 1.


def test_published_replay_retains_solver_options_and_post_equilibrium_initial_state():
    config = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 12.}],
              "boundary_m3_s": 5., "boundary_c": 20., "air_c": 8.,
              "surface_budget": {"rh": .45, "wind_mps": 2., "shortwave_w_m2": 200., "cloud": .16},
              "shortwave_multiplier": {"a": .4}, "max_surface_iterations": 50,
              "surface_tolerance_c": 1e-8, "surface_relaxation": .7,
              "hyporheic_zones": {"a": {"storage_volume_m3": 40., "alpha_per_s": .001, "initial_c": 10.}},
              "initialize_steady": True, "duration_s": 20., "dt_s": 1., "sample_s": 10.}
    replay = make_replay(config)
    restored = river_from_config(replay_config(replay))
    assert list(restored.temperature_c) == replay["frames"][0]["temperature_c"]
    assert restored.surface_relaxation == .7
    assert restored.surface_tolerance_c == 1e-8
    assert restored.max_surface_iterations == 50
    assert restored._cell_shortwave_multiplier == (.4,)
    assert restored._hyporheic_t_c == [10.]
    assert restored.run(20., dt_s=1., sample_s=10.)[-1]["temperature_c"] == pytest.approx(
        replay["frames"][-1]["temperature_c"], abs=1e-11)


def test_reset_repeats_initial_state_and_commutes_with_display_hour():
    solver = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 15.}],
              "boundary_m3_s": 5., "boundary_c": 15.}
    config = {"patches": [{"id": "p", "habitat": "dry_meadow", "center_xz": [0., 0.],
               "snow_mm": 100., "soil_mm": 12., "moisture": .1, "biomass": .5, "capacity": 1.}]}
    a, b = [LiveEngine(river_from_config(solver), config) for _ in range(2)]
    a.command("control", {"changes": {"snow.as_of_date": "2026-04-20", "clock_hour": 18.}})
    before = copy.deepcopy(a.ecology)
    a.compute_until(10.)
    a.command("control", {"changes": {"clock_hour": 18., "snow.as_of_date": "2026-04-20"}})
    b.command("control", {"changes": {"clock_hour": 18., "snow.as_of_date": "2026-04-20"}})
    assert a.ecology == before == b.ecology
    assert a.epoch_origin == b.epoch_origin
    assert a.initial_state_id == b.initial_state_id
    assert a.display_hour == b.display_hour == 18.


def test_forcing_control_identifies_branch_and_display_control_preserves_identity():
    solver = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 15.}],
              "boundary_m3_s": 5., "boundary_c": 15.}
    model = LiveEngine(river_from_config(solver), build_id="published")
    model.command("control", {"changes": {"clock_hour": 17.}})
    assert model._header()["scenario_id"] == "published"
    response = model.command("control", {"changes": {"hydro.boundary_c": 20.}})
    assert response["parent_scenario_id"] == "published"
    assert model._header()["scenario_id"] != "published"
    assert model._header()["exchange_strategy"] == "newton_exchange"
    assert model._header()["start_operation"] == "controlled_branch"


def test_zero_duration_preserves_soil_snow_and_biomass():
    patches = [{"id": "p", "snow_mm": 100., "soil_mm": 100., "biomass": .5, "gdd": 99.}]
    output, ledger = step_land(patches, 0., 20., 2., 2.)
    assert output == patches
    assert ledger["et_mm"] == ledger["runoff_mm"] == ledger["snow_export_mm"] == 0.
    assert step_soil_bucket(100., 0., 20., 2., elapsed_days=0.)["soil_mm"] == 100.
    assert run_season(patches, 0, [])[0] == patches


def test_invalid_spinup_leaves_the_live_state_unchanged():
    solver = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 15.}],
              "boundary_m3_s": 5., "boundary_c": 15.}
    config = {"patches": [{"id": "p", "biomass": .5, "capacity": 1., "soil_mm": 60.}]}
    model = LiveEngine(river_from_config(solver), config)
    before = copy.deepcopy(model.ecology)
    with pytest.raises(ValueError, match="entries"):
        model.command("reset", {"changes": {"snow.days": 30, "snow.air_c_by_day": [1.]}})
    assert model.ecology == before


def test_reset_refuses_unknown_river_cells_before_restoring_initial_state():
    solver = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 10.}],
              "boundary_m3_s": 5., "boundary_c": 20.}
    model = LiveEngine(river_from_config(solver), {"live": {"dt_s": 1.}})
    model.compute_until(10.)
    before = model.river.snapshot()
    with pytest.raises(ValueError, match="unknown cells"):
        model.command("reset", {"changes": {"river.shade": {"cell_ids": ["unknown"], "multiplier": .5}}})
    assert model.river.snapshot() == before


def test_split_cold_dry_interval_conserves_solid_export():
    patches = [{"id": "p", "habitat": "dry_meadow", "snow_mm": 100., "soil_mm": 12.}]
    full, whole = step_land(patches, 86400., -10., 0., 2.)
    half, first = step_land(patches, 43200., -10., 0., 2.)
    half, second = step_land(half, 43200., -10., 0., 2., interval_start_s=43200.)
    assert half[0]["snow_mm"] == pytest.approx(full[0]["snow_mm"], abs=1e-12)
    assert first["snow_export_mm"] + second["snow_export_mm"] == pytest.approx(whole["snow_export_mm"], abs=1e-12)


def test_overland_rate_uses_the_volume_source_window():
    field = {"seconds": 120., "surface_runoff": {"outflow_m3": 6., "carries_runoff_signal": True}}
    rate, report = _overland_runoff_to_boundary(field, {}, 600.)
    assert rate == .05
    assert rate * report["window_s"] == 6.
    assert report["river_window_s"] == 600.


def test_overland_volume_is_not_extrapolated_across_the_river_window():
    field = {"seconds": 120., "surface_runoff": {"outflow_m3": 6., "carries_runoff_signal": True}}
    forcing = _overland_boundary_series(5., field)
    config = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 15.}],
              "boundary_m3_s": forcing, "boundary_c": 15.}
    river = river_from_config(config)
    river.run(600., dt_s=10., sample_s=60.)
    assert river.budget()["boundary_input_m3"] - 5. * 600. == pytest.approx(6., abs=1e-10)
    assert river.budget()["water_relative_residual"] < 1e-12


def test_mapped_pipeline_routes_the_overland_source_volume_once():
    from tests.river.test_river_world import tiny_world_ecosystem
    from yellowstone_python.pipeline.stages.river import run_replay_solver
    world, ecosystem = tiny_world_ecosystem()
    field = {"seconds": 120., "surface_runoff": {"outflow_m3": 6., "carries_runoff_signal": True}}
    config = {"run_mode": "scenario", "replay": {"duration_s": 600., "dt_s": 10., "sample_s": 60.}}
    replay = run_replay_solver(config, ecosystem, world, hour0=12., boundary_m3s=5.05,
        simulation_start_epoch_unix=1782064800., boundary_series=_overland_boundary_series(5., field))
    assert replay["final_budget"]["boundary_input_m3"] - 5. * 600. == pytest.approx(6., abs=1e-10)
    assert replay["forcing"]["boundary_m3_s"]["values"] == [5.05, 5.]


def test_positive_outlet_volume_requires_declared_temporal_support_and_signal():
    with pytest.raises(ValueError, match="positive source window"):
        _overland_boundary_series(5., {"seconds": 0., "surface_runoff": {"outflow_m3": 6., "carries_runoff_signal": True}})
    with pytest.raises(ValueError, match="declared runoff signal"):
        _overland_boundary_series(5., {"seconds": 120., "surface_runoff": {"outflow_m3": 6., "carries_runoff_signal": False}})


def test_land_stage_has_one_evaporation_owner(tmp_path):
    patches = [{"id": "p", "habitat": "dry_meadow", "center_xz": [0., 0.], "soil_mm": 60., "moisture": .5}]
    state = {"_excluded": lambda *args: False, "air0": 10., "clock_info": {"season": "summer"},
             "hcfg": {}, "met_bundle": None, "patches1": patches, "run_mode_norm": "scenario",
             "shells": [], "sim_s": 0., "wcfg": {}, "wind_mag": 2., "world_root": tmp_path}
    output = run_land(state, {"snow": {"days": 0, "precip_mm_d": 0.}})
    assert output["patches2"] == patches
    assert output["et_ledger"]["role"] == "diagnostic"
    assert output["et_ledger"]["total_et_mm"] == 0.


def test_baked_and_live_land_share_the_same_hourly_stock_updates():
    from yellowstone_python.exporters.runtime_series import python_series
    epoch = 1782064800.
    hour0 = (epoch / 3600.0 - 6.0) % 24.0
    patches = [{"id": "p", "habitat": "dry_meadow", "center_xz": [0., 0.],
                "soil_mm": 60., "snow_mm": 0., "moisture": .5, "biomass": .5, "capacity": 1.}]
    weather = {"night_air_c": 10., "day_warming_c": 0., "wind_xz_mps": [0., 2.],
               "gust_mps": 0., "precip_mm_h": 2.}
    replay = {"simulation_time": {"start_epoch_unix": epoch}, "clock_hour0": hour0,
              "forcing": {"air_c": 10.}, "legacy_queries": [{"reach_id": "a", "s_m": 10.}],
              "cells": [{"id": "a", "start_s_m": 0., "end_s_m": 20., "center_s_m": 10., "q_out_m3_s": 5.}],
              "frames": [{"t_s": float(t), "temperature_c": [15.]} for t in range(0, 7201, 60)]}
    baked = python_series(replay, [{"id": "a"}], patches, weather, thermal_flux_mm_d_by_patch={"p": 0.})
    solver = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 15.}],
              "boundary_m3_s": 5., "boundary_c": 15., "air_c": 10.}
    live = LiveEngine(river_from_config(solver), {"patches": patches, "weather": weather,
                      "live": {"dt_s": 1.}, "land_thermal_flux_mm_d_by_patch": {"p": 0.}},
                      epoch_unix=epoch, frame_interval_s=60.)
    live.compute_until(7200.)
    for key in ("soil_mm", "snow_mm", "biomass", "gdd"):
        assert live.ecology["patches"][0][key] == pytest.approx(baked[-1]["patches"][0][key], abs=1e-11)
