"""Snow phase transfers and display-clock stock preservation."""
import copy

import pytest

from yellowstone_python.land.snow_season import run_season, catchment_runoff_m3_s
from yellowstone_python.river.river_transport import Cell, River, SurfaceBudget
from yellowstone_python.service.live import LiveEngine


def cold_patch():
    return {"id": "meadow", "habitat": "dry_meadow", "center_xz": [0., 0.],
            "snow_mm": 100., "soil_mm": 12., "moisture": .1,
            "biomass": .5, "capacity": 1.}


def test_cold_wind_exports_solid_water_without_liquid_discharge():
    patches, ledger = run_season([cold_patch()], 1, [-10.], precip_mm_d=0.,
                                thermal_flux_mm_d=0., wind_loss=.15, wind_mps=2.)
    assert patches[0]["snow_mm"] == 85.
    assert ledger["runoff_mm"] == 0.
    assert ledger["snow_export_mm"] == 15.
    assert ledger["storage_residual_mm"] == pytest.approx(0., abs=1e-9)
    assert catchment_runoff_m3_s(patches, ledger, catchment_area_m2=1e6)["runoff_m3_s"] == 0.


def test_warm_rain_produces_liquid_drainage():
    patch = {**cold_patch(), "snow_mm": 0., "soil_mm": 84., "moisture": .7}
    _, ledger = run_season([patch], 1, [10.], precip_mm_d=20., wind_loss=0., k_et=0.)
    assert ledger["surface_runoff_mm"] == 10.
    assert ledger["runoff_mm"] == 10.


def test_paused_display_hour_preserves_physical_state_well_after_water_year_start():
    river = River([Cell("a", 20., 10., 200., 15.)], 5., 15.)
    model = LiveEngine(river, {"patches": [cold_patch()]}, epoch_unix=1776643200.)
    model.command("clock", {"paused": True})
    before = copy.deepcopy(model.ecology)
    budget = model.river.budget()
    epoch = model.epoch_origin
    model.command("control", {"key": "clock_hour", "value": 18.})
    assert model.ecology == before
    assert model.river.budget() == budget
    assert model.epoch_origin == epoch
    assert model.player_t_s == 0.


@pytest.mark.parametrize("budget", [None, {"rh": .45, "wind_mps": 2.,
                                         "shortwave_w_m2": 200., "cloud": .16}])
def test_live_start_preserves_exchange_strategy_and_supplied_forcing(budget):
    river = River([Cell("a", 20., 10., 200., 15.)], 5., 15., air_c=4.,
                  surface_budget=SurfaceBudget.parse(budget) if budget else None)
    model = LiveEngine(river)
    before = model.solver_config()
    model._prepare_weather(60.)
    assert model.solver_config() == before
