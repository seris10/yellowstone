"""Outflow shortwave forcing and mat insolation coupling."""
from __future__ import annotations

import json

import numpy as np
import pytest

from yellowstone_python import build
import yellowstone_python.thermal_features.mat_appearance as mat_appearance
import yellowstone_python.thermal_features.outflow_thermal as outflow_thermal
from yellowstone_python.thermal_features.microbial_mats import CORE_GRID_SIZE, PIGMENT_SATURATION_SW_W_M2
from yellowstone_python.atmosphere.time_utils import epoch_unix_for_local


needs_network = pytest.mark.needs_network_inputs

WCFG = {"humidity": 0.34, "cloud": 0.0, "wind_xz_mps": [2.08, 0.69]}


@pytest.fixture
def captured_met(monkeypatch):
    """Replace the graph sweep with a stub that records its forcing."""
    seen = {}

    def fake_sweep(network, rasters, dem, pools, discharges, temps, met,
                   **kwargs):
        seen["met"] = met
        seen["forcing_epoch_utc"] = kwargs.get("forcing_epoch_utc")
        shape = (CORE_GRID_SIZE, CORE_GRID_SIZE)
        return {"temperature": np.full(shape, np.nan, dtype=np.float32),
                "wet_mask": np.zeros(shape, dtype=bool),
                "sidecar": {"forcing_epoch_utc": kwargs.get(
                    "forcing_epoch_utc")}}

    monkeypatch.setattr(outflow_thermal, "graph_sweep_outflow_temperature",
                        fake_sweep)
    return seen


@needs_network
@pytest.mark.needs_world
def test_outflow_shortwave_follows_simulation_epoch(captured_met):
    day = epoch_unix_for_local("2026-10-13", 12.0, -6.0)
    chain = build._run_outflow_chain(MIDWAY, 11.4, WCFG, day, "test")
    noon_sw = captured_met["met"].shortwave_w_m2
    assert 500.0 < noon_sw < 800.0
    assert captured_met["forcing_epoch_utc"] == day
    forcing = chain["outflow_sidecar"]["shortwave_forcing"]
    assert forcing["all_sky_w_m2"] == pytest.approx(noon_sw)
    assert forcing["epoch_utc_s"] == day
    assert forcing["epoch_source"] == "test"
    assert chain["dem"].shape == (CORE_GRID_SIZE, CORE_GRID_SIZE)

    night = epoch_unix_for_local("2026-10-13", 2.0, -6.0)
    build._run_outflow_chain(MIDWAY, 11.4, WCFG, night, "test")
    assert captured_met["met"].shortwave_w_m2 == 0.0


@needs_network
@pytest.mark.needs_world
def test_outflow_shortwave_scales_with_cloud(captured_met):
    day = epoch_unix_for_local("2026-10-13", 12.0, -6.0)
    build._run_outflow_chain(MIDWAY, 11.4, WCFG, day, "test")
    clear = captured_met["met"].shortwave_w_m2
    build._run_outflow_chain(MIDWAY, 11.4, {**WCFG, "cloud": 1.0}, day,
                             "test")
    assert captured_met["met"].shortwave_w_m2 == pytest.approx(0.25 * clear)


@needs_network
@pytest.mark.needs_world
def test_mat_insolation_uses_simulation_date(captured_met):
    october = epoch_unix_for_local("2026-10-13", 16.2, -6.0)
    july = epoch_unix_for_local("2026-07-15", 16.2, -6.0)
    oct_chain = build._run_outflow_chain(MIDWAY, 11.4, WCFG, october, "test")
    jul_chain = build._run_outflow_chain(MIDWAY, 11.4, WCFG, july, "test")
    assert oct_chain["insolation"]["date_utc"] == "2026-10-13"
    assert jul_chain["insolation"]["date_utc"] == "2026-07-15"
    oct_sw = oct_chain["insolation"]["all_sky_mean_w_m2"]
    jul_sw = jul_chain["insolation"]["all_sky_mean_w_m2"]
    assert oct_sw < 0.7 * jul_sw
    oct_pigment = float(np.nanmax(oct_chain["mat_state"].pigment_index))
    assert oct_pigment == pytest.approx(
        min(1.0, oct_sw / PIGMENT_SATURATION_SW_W_M2), rel=1e-5)


def test_imagery_pigment_ref_is_clear_sky_on_acquisition_date():
    ref, insolation = build.mat_imagery_pigment_ref()
    assert insolation["date_utc"] == build.MAT_IMAGERY_DATE_UTC == "2022-07-19"
    assert insolation["cloud_fraction"] == 0.0
    assert insolation["cloud_factor"] == 1.0
    assert ref == pytest.approx(min(
        1.0, insolation["all_sky_mean_w_m2"] / PIGMENT_SATURATION_SW_W_M2))


def test_mat_appearance_absent_inputs_returns_none(tmp_path):
    chain = {"dem": np.zeros((4, 4)),
             "network_rasters": {"flow_fraction": np.zeros((4, 4))}}
    assert build._write_mat_appearance(chain, tmp_path, tmp_path,
                                       {}) is None
    assert not (tmp_path / "mat_pigment.png").exists()


@pytest.mark.needs_network_inputs
@pytest.mark.needs_world
def test_mat_appearance_wiring(monkeypatch, tmp_path):
    seen = {}

    def fake_write(state, temperature, flow, dem, photo, mineral, path,
                   **kwargs):
        seen.update(photo=photo, mineral=mineral, flow=flow, dem=dem,
                    path=path, **kwargs)
        return {"schema": mat_appearance.SCHEMA_MAT_APPEARANCE,
                "status": mat_appearance.APPEARANCE_STATUS,
                "pigment_ref": kwargs["pigment_ref"], "sources": []}

    monkeypatch.setattr(mat_appearance, "write_mat_appearance_png",
                        fake_write)
    n = CORE_GRID_SIZE
    chain = {"dem": np.zeros((n, n)), "outflow_raster": np.zeros((n, n)),
             "mat_state": object(),
             "network_rasters": {"flow_fraction": np.ones((n, n))}}
    deps = {"world.json": "0" * 64, "code_rev": "test"}
    meta = build._write_mat_appearance(chain, MIDWAY, tmp_path, deps)
    size = n * mat_appearance.UPSAMPLE
    assert seen["photo"].shape == (size, size, 3)
    assert seen["mineral"].shape == (size, size)
    assert seen["flow"] is chain["network_rasters"]["flow_fraction"]
    assert seen["dem"] is chain["dem"]
    assert seen["path"].endswith("mat_pigment.png")
    ref, _ = build.mat_imagery_pigment_ref()
    assert seen["pigment_ref"] == pytest.approx(ref)
    doc = json.loads((tmp_path / "mat_appearance.json").read_text())
    assert doc["schema"] == mat_appearance.SCHEMA_MAT_APPEARANCE
    assert doc["pigment_ref_insolation"]["date_utc"] == "2022-07-19"
    assert any("midway_orthophoto_detail.jpg" in s["file"]
               for s in doc["sources"])
    assert meta["pigment_ref"] == pytest.approx(ref)


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'MIDWAY', resolved_paths['MIDWAY'], raising=False)
    if request.node.get_closest_marker("needs_world") or request.node.get_closest_marker("needs_network_inputs"):
        for relative in ('data/outflow_network/outflow_network.json', 'data/outflow_network/spring_discharges.json', 'references/dem_1m_core.tif', 'data/world.json', 'references/midway_orthophoto_detail.jpg', 'assets/textures/habitat_mask.png'):
            path = resolved_paths["MIDWAY"] / relative
            if not path.is_file():
                pytest.skip(f"required world input missing: {path}")
