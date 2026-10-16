"""Tests for the outflow sheet-flow energy balance."""
from __future__ import annotations

import hashlib
import json
import math
import tempfile
from pathlib import Path

import numpy as np
import pytest

import yellowstone_python.thermal_features.outflow_thermal as outflow_thermal
from yellowstone_python.thermal_features.outflow_thermal import CP_WATER_J_KG_K, MANNING_REYNOLDS_HIGH, MANNING_REYNOLDS_LOW, RHO_WATER_KG_M3, SinterConduction, edinger_exchange, edinger_fill_piecewise, edinger_temperature, manning_sheet_flow, manning_turbulent_flow, segment_temperature, sheet_flow_depth_velocity, water_kinematic_viscosity_m2_s
from yellowstone_python.river.surface_flux import MetState, es_kpa, es_kpa_wagner_pruss


def _straight_segment(length_m: float = 50.0, width_m: float = 2.0,
                      slope: float = 0.02) -> dict:
    return {
        "id": "seg1",
        "spring_index": 0,
        "upstream_id": None,
        "points_xz": [[0.0, 0.0], [length_m, 0.0]],
        "length_m": length_m,
        "mean_slope": slope,
        "width_m": width_m,
        "width_source": "authored",
        "flow_fraction": 1.0,
        "imagery_wet_fraction": 1.0,
    }


def _calm_dry_met(air_c: float = 10.0, wind_mps: float = 2.0,
                  shortwave: float = 0.0) -> MetState:
    return MetState(air_c=air_c, rh=0.4, wind_mps=wind_mps,
                    shortwave_w_m2=shortwave, cloud=0.5)


def _no_sinter() -> SinterConduction:
    """SinterConduction that contributes zero flux (k = 0)."""
    return SinterConduction(k_w_m_k=0.0, thickness_m=1.0,
                            t_substrate_c=0.0, status="test_zero")


def test_manning_sheet_flow_monotone_with_discharge():
    d1, v1 = manning_sheet_flow(0.01, slope_m_m=0.02)
    d2, v2 = manning_sheet_flow(0.04, slope_m_m=0.02)
    assert d2 > d1
    assert v2 > v1


def test_segment_rim_equals_pool_edge_temperature():
    seg = _straight_segment()
    met = _calm_dry_met()
    profile = segment_temperature(70.0, seg, 0.5, met,
                                  sinter=_no_sinter())
    assert profile["t_c"][0] == pytest.approx(70.0)


def test_closed_energy_budget_along_synthetic_channel():
    seg = _straight_segment(length_m=20.0, width_m=1.0, slope=0.01)
    met = _calm_dry_met(air_c=10.0, wind_mps=1.0, shortwave=0.0)
    profile = segment_temperature(60.0, seg, 0.2, met,
                                  sinter=_no_sinter(),
                                  step_count=400)
    t = np.array(profile["t_c"])
    flux = np.array(profile["net_flux_w_m2"])
    s = np.array(profile["s_m"])
    width = seg["width_m"]
    # Integral of F*w over the channel length.
    heat_lost_from_atm_w = -np.trapezoid(flux * width, s)
    q = profile["q_m3_s"]
    advected_change_w = (RHO_WATER_KG_M3 * CP_WATER_J_KG_K
                         * q * (t[0] - t[-1]))
    assert heat_lost_from_atm_w == pytest.approx(advected_change_w, rel=0.02)


def test_cooling_length_increases_with_discharge():
    seg = _straight_segment(length_m=100.0, width_m=2.0, slope=0.01)
    met = _calm_dry_met(air_c=5.0, wind_mps=2.0, shortwave=0.0)
    low = segment_temperature(70.0, seg, 0.1, met, sinter=_no_sinter(),
                              step_count=400)
    high = segment_temperature(70.0, seg, 2.0, met, sinter=_no_sinter(),
                               step_count=400)
    assert low["t_c"][-1] < high["t_c"][-1]


def test_cooling_length_decreases_with_wind():
    seg = _straight_segment(length_m=100.0, width_m=2.0, slope=0.01)
    low_wind = _calm_dry_met(air_c=5.0, wind_mps=0.5, shortwave=0.0)
    high_wind = _calm_dry_met(air_c=5.0, wind_mps=5.0, shortwave=0.0)
    low = segment_temperature(70.0, seg, 0.5, low_wind,
                              sinter=_no_sinter(), step_count=400)
    high = segment_temperature(70.0, seg, 0.5, high_wind,
                               sinter=_no_sinter(), step_count=400)
    assert high["t_c"][-1] < low["t_c"][-1]


def test_sinter_conduction_warms_cool_water():
    sink = SinterConduction(k_w_m_k=2.5, thickness_m=0.1,
                            t_substrate_c=70.0, status="authored")
    cold_flux = sink.flux_w_m2(20.0)
    assert cold_flux > 0.0
    neutral_flux = sink.flux_w_m2(70.0)
    assert math.isclose(neutral_flux, 0.0, abs_tol=1e-9)


def test_sinter_conductivity_default_is_opal_table_value():
    """Diment and Pratt (1988) opal 3.3 mcal/cm/s/C converted to W/m/K."""
    from yellowstone_python.registry.param_registry import PARAMS
    mcal_cm_s_c_to_w_m_k = 1.0e-3 * 4.184 / 1.0e-2
    assert SinterConduction().k_w_m_k == pytest.approx(
        3.3 * mcal_cm_s_c_to_w_m_k, abs=5e-3)
    assert outflow_thermal.SINTER_CONDUCTIVITY_STATUS == "literature"
    assert "ofr88690" in outflow_thermal.SINTER_CONDUCTIVITY_SOURCE
    entries = {e["param_id"]: e for e in PARAMS}
    assert entries["outflow_thermal.sinter_k_w_m_k"]["param_class"] == "literature"
    for pid in ("outflow_thermal.sinter_thickness_m",
                "outflow_thermal.sinter_substrate_t_c"):
        assert entries[pid]["param_class"] == "assumed"


def test_manning_sheet_flow_qdv_identity_without_clamps():
    for q, slope in [(0.01, 0.02), (0.05, 0.01), (0.2, 0.03), (3.5e-5, 0.02)]:
        d, v = manning_sheet_flow(q, slope_m_m=slope)
        assert d * v == pytest.approx(q, rel=1e-10)


def test_laminar_regime_covers_thin_sheet_flow_without_raising():
    out = sheet_flow_depth_velocity(3.5e-5, slope_m_m=0.02, t_water_c=70.0)
    assert out["regime"] == "laminar"
    assert out["reynolds"] < MANNING_REYNOLDS_LOW
    assert out["depth_m"] * out["velocity_mps"] == pytest.approx(3.5e-5, rel=1e-10)


def test_turbulent_regime_matches_manning_at_high_discharge():
    out = sheet_flow_depth_velocity(0.5, slope_m_m=0.01, t_water_c=70.0)
    assert out["regime"] == "turbulent"
    assert out["reynolds"] > MANNING_REYNOLDS_HIGH
    manning_d, manning_v = manning_turbulent_flow(0.5, 0.01)
    assert out["depth_m"] == pytest.approx(manning_d, rel=1e-10)
    assert out["velocity_mps"] == pytest.approx(manning_v, rel=1e-10)


def test_blended_regime_qdv_identity():
    midpoint = 0.5 * (MANNING_REYNOLDS_LOW + MANNING_REYNOLDS_HIGH)
    nu_70 = water_kinematic_viscosity_m2_s(70.0)
    q_blend = midpoint * nu_70
    out = sheet_flow_depth_velocity(q_blend, slope_m_m=0.01, t_water_c=70.0)
    assert out["regime"] == "blended"
    assert out["depth_m"] * out["velocity_mps"] == pytest.approx(q_blend, rel=1e-10)


def test_sheet_flow_continuous_across_transition():
    nu_70 = water_kinematic_viscosity_m2_s(70.0)
    for re_target in (
            MANNING_REYNOLDS_LOW * 0.99,
            MANNING_REYNOLDS_LOW * 1.01,
            MANNING_REYNOLDS_HIGH * 0.99,
            MANNING_REYNOLDS_HIGH * 1.01):
        q = re_target * nu_70
        out_before = sheet_flow_depth_velocity(q * 0.999, 0.01, 70.0)
        out_at = sheet_flow_depth_velocity(q, 0.01, 70.0)
        out_after = sheet_flow_depth_velocity(q * 1.001, 0.01, 70.0)
        delta_before = abs(out_at["depth_m"] - out_before["depth_m"])
        delta_after = abs(out_after["depth_m"] - out_at["depth_m"])
        assert delta_before < 1.0e-4
        assert delta_after < 1.0e-4


def test_water_viscosity_matches_tabulated_values():
    assert water_kinematic_viscosity_m2_s(20.0) == pytest.approx(1.004e-6, rel=0.1)
    assert water_kinematic_viscosity_m2_s(70.0) == pytest.approx(0.413e-6, rel=0.2)


def test_edinger_piecewise_matches_segment_long_cooling_single_channel():
    seg = _straight_segment(length_m=100.0, width_m=1.0, slope=0.01)
    met = _calm_dry_met(air_c=8.0, wind_mps=3.0, shortwave=0.0)
    discharge = 0.002
    profile = segment_temperature(70.0, seg, discharge, met,
                                  sinter=_no_sinter(), step_count=2000)
    assert profile["t_c"][-1] < 45.0
    sample_points = np.array([25.0, 50.0, 75.0, 100.0])
    q_cells = np.full(sample_points.shape, discharge / seg["width_m"])
    piece = edinger_fill_piecewise(70.0, met, q_cells, sample_points,
                                   sinter=_no_sinter(), step_m=1.0)
    seg_s = np.array(profile["s_m"])
    seg_t = np.array(profile["t_c"])
    reference_t = np.interp(sample_points, seg_s, seg_t)
    diffs = piece["temperature_c"] - reference_t
    assert np.max(np.abs(diffs)) < 1.0
    assert np.abs(piece["temperature_c"][-1] - reference_t[-1]) < 1.0


def test_edinger_single_anchor_overcools_long_cooling_run():
    seg = _straight_segment(length_m=100.0, width_m=1.0, slope=0.01)
    met = _calm_dry_met(air_c=8.0, wind_mps=3.0, shortwave=0.0)
    discharge = 0.002
    profile = segment_temperature(70.0, seg, discharge, met,
                                  sinter=_no_sinter(), step_count=2000)
    lin = edinger_exchange(70.0, met, sinter=_no_sinter())
    t_single = edinger_temperature(70.0, lin["t_e_c"],
                                   lin["k_total_w_m2_k"],
                                   flow_length_m=100.0,
                                   unit_discharge_m2_s=discharge)
    piece = edinger_fill_piecewise(70.0, met,
                                   np.array([discharge]),
                                   np.array([100.0]),
                                   sinter=_no_sinter(), step_m=1.0)
    err_single = abs(t_single - profile["t_c"][-1])
    err_piece = abs(float(piece["temperature_c"][0]) - profile["t_c"][-1])
    assert err_piece < err_single


def test_edinger_lower_flow_fraction_cools_more_at_equal_distance():
    met = _calm_dry_met(air_c=5.0, wind_mps=2.0, shortwave=0.0)
    lin = edinger_exchange(70.0, met, sinter=_no_sinter())
    k = lin["k_total_w_m2_k"]
    t_e = lin["t_e_c"]
    t_full = edinger_temperature(70.0, t_e, k,
                                 flow_length_m=5.0,
                                 unit_discharge_m2_s=0.1)
    t_fraction = edinger_temperature(70.0, t_e, k,
                                     flow_length_m=5.0,
                                     unit_discharge_m2_s=0.01)
    assert t_fraction < t_full


def _write_raster_record(array: np.ndarray, dtype_str: str,
                         directory: Path, filename: str) -> dict:
    """Write a raster to a file and return its real-format record dict."""
    path = directory / filename
    data = np.ascontiguousarray(array.astype(dtype_str)).tobytes()
    path.write_bytes(data)
    return {
        "path": filename,
        "dtype": dtype_str,
        "sha256": hashlib.sha256(data).hexdigest(),
        "shape": list(array.shape),
    }


def test_rasterize_outflow_temperature_is_retired_and_raises():
    with pytest.raises(NotImplementedError, match="graph_sweep_outflow_temperature"):
        outflow_thermal.rasterize_outflow_temperature(
            {}, {}, {}, _calm_dry_met())


def test_graph_sweep_outflow_temperature_closes_energy_on_small_synthetic_network():
    size = outflow_thermal.CORE_GRID_SIZE
    dem = np.full((size, size), 2200.0, dtype=np.float32)
    cx = size // 2
    cz = size // 2
    for di in range(-3, 4):
        for dj in range(-3, 4):
            dem[cz + dj, cx + di] = 2210.0
    for i in range(cx, cx + 40):
        dem[cz, i] = 2208.0 - 0.1 * (i - cx)
    ring = [
        [-2.5, -2.5], [2.5, -2.5], [2.5, 2.5], [-2.5, 2.5],
    ]
    world_pools = [{"id": "pool_test", "name": "Test",
                    "ring": ring, "source_id": 999,
                    "center": [0.0, 0.0, 2200.0]}]
    discharges = {"pool_test": 0.05}
    spring_temps = {"pool_test": 70.0}
    met = _calm_dry_met(air_c=10.0, wind_mps=2.0, shortwave=200.0)
    verification = outflow_thermal.recompute_flow_fraction_wp_a(
        dem, world_pools, discharges, convention="weir",
    )
    reference_fraction = verification["flow_fraction"]
    size = outflow_thermal.CORE_GRID_SIZE
    network = {
        "schema": "yellowstone.outflow_network.v1",
        "status": "test_fixture",
        "springs": [{"pool_id": "pool_test", "name": "Test",
                     "index": 0, "rim_xz": [[0.0, 0.0]],
                     "rim_elevation_m": 2200.0}],
        "segments": [_straight_segment(length_m=10.0, width_m=1.0,
                                       slope=0.1)],
        "method": {"routing": {"exponent": 1.1},
                   "rim_injection": {"convention": "weir"}},
    }
    network_rasters = {
        "spring_index": np.full((size, size), -1, dtype=np.int16),
        "flow_length_m": np.full((size, size), np.nan, dtype=np.float32),
        "flow_fraction": reference_fraction,
    }
    result = outflow_thermal.graph_sweep_outflow_temperature(
        network, network_rasters, dem, world_pools,
        discharges, spring_temps, met,
        sinter=_no_sinter(),
        min_film_depth_m=0.0,
        verify_tolerance=1.0e-5,
    )
    assert result["fill_method"] == "graph_energy_sweep_mfd_wp_a_injection"
    assert result["t_equilibrium_c"] >= -1.0
    wet_mask = result["wet_mask"]
    temps = result["temperature"][wet_mask]
    t_eq = result["t_equilibrium_c"]
    assert float(temps.min()) >= t_eq - 0.1
    assert float(temps.max()) <= 70.0 + 0.1
    assert result["sidecar"]["rim_injection_convention"] == "weir"
    assert result["sidecar"]["flow_fraction_verify_max_abs_diff"] <= 1.0e-5


def test_load_network_rasters_detects_sha256_mismatch():
    size = outflow_thermal.CORE_GRID_SIZE
    spring_index = np.full((size, size), -1, dtype=np.int16)
    flow_length = np.full((size, size), np.nan, dtype=np.float32)
    flow_fraction = np.full((size, size), 0.0, dtype=np.float32)
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rasters = {
            "spring_index": _write_raster_record(
                spring_index, "<i2", tmp_path, "spring_index.i16"),
            "flow_length_m": _write_raster_record(
                flow_length, "<f4", tmp_path, "flow_length_m.f32"),
            "flow_fraction": _write_raster_record(
                flow_fraction, "<f4", tmp_path, "flow_fraction.f32"),
        }
        rasters["spring_index"]["sha256"] = "0" * 64
        network = {"schema": "yellowstone.outflow_network.v1",
                   "rasters": rasters}
        with pytest.raises(ValueError, match="sha256"):
            outflow_thermal.load_network_rasters(network, tmp_path)


def test_load_network_rasters_round_trips_record_format():
    size = outflow_thermal.CORE_GRID_SIZE
    spring_index = np.full((size, size), -1, dtype=np.int16)
    flow_length = np.full((size, size), np.nan, dtype=np.float32)
    flow_fraction = np.full((size, size), 0.0, dtype=np.float32)
    spring_index[size // 2, size // 2] = 0
    flow_length[size // 2, size // 2] = 1.0
    flow_fraction[size // 2, size // 2] = 1.0
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        rasters = {
            "spring_index": _write_raster_record(
                spring_index, "<i2", tmp_path, "spring_index.i16"),
            "flow_length_m": _write_raster_record(
                flow_length, "<f4", tmp_path, "flow_length_m.f32"),
            "flow_fraction": _write_raster_record(
                flow_fraction, "<f4", tmp_path, "flow_fraction.f32"),
        }
        network = {"schema": "yellowstone.outflow_network.v1",
                   "rasters": rasters}
        loaded = outflow_thermal.load_network_rasters(network, tmp_path)
    assert loaded is not None
    assert loaded["spring_index"][size // 2, size // 2] == 0
    assert loaded["flow_fraction"][size // 2, size // 2] == 1.0


@pytest.mark.needs_network_inputs
def test_graph_sweep_outflow_temperature_matches_rework_7_real_run():
    repo_root = Path(__file__).resolve().parents[2]
    midway = repo_root / "yellowstone_midway"
    network_path = midway / "data" / "outflow_network" / "outflow_network.json"
    dem_path = midway / "references" / "dem_1m_core.tif"
    world_path = midway / "data" / "world.json"
    discharges_path = (midway / "data" / "outflow_network"
                       / "spring_discharges.json")
    for p in (network_path, dem_path, world_path, discharges_path):
        if not p.exists():
            pytest.skip(f"required real-network artifact missing: {p}")
    network = json.loads(network_path.read_text())
    network_rasters = outflow_thermal.load_network_rasters(
        network, network_path.parent)
    dem = outflow_thermal.load_dem_core_tif(dem_path)
    world_data = json.loads(world_path.read_text())
    spring_names = {s.get("name") for s in network["springs"]}
    world_pools = [p for p in world_data.get("pools", [])
                   if p.get("name") in spring_names]
    discharges_doc = json.loads(discharges_path.read_text())
    discharges = {pid: float(entry["discharge_m3_s"])
                  for pid, entry in discharges_doc["springs"].items()}
    spring_temps = {
        "pool_1030_0": 88.7, "pool_1034_0": 70.0,
        "pool_1028_0": 62.0, "pool_1029_0": 60.0,
    }
    met = MetState(air_c=15.2, rh=0.27, wind_mps=2.58,
                   shortwave_w_m2=512.0, cloud=0.0)
    result = outflow_thermal.graph_sweep_outflow_temperature(
        network, network_rasters, dem, world_pools,
        discharges, spring_temps, met,
    )
    assert result["fill_method"] == "graph_energy_sweep_mfd_wp_a_injection"
    assert result["sidecar"]["rim_injection_convention"] == "weir"
    assert result["sidecar"]["flow_fraction_verify_max_abs_diff"] <= 1.0e-6
    assert result["t_equilibrium_c"] == pytest.approx(21.555, abs=0.1)
    assert result["t_hot_c"] == pytest.approx(88.7, abs=0.1)
    wet_mask = result["wet_mask"]
    temps = result["temperature"][wet_mask]
    t_eq = result["t_equilibrium_c"]
    assert float(temps.min()) >= t_eq - 0.05
    assert float(temps.max()) <= result["t_hot_c"] + 0.05
    assert int(wet_mask.sum()) == pytest.approx(281077, rel=0.01)


def test_wagner_pruss_saturation_at_90c_matches_tabulated_value():
    assert es_kpa_wagner_pruss(90.0) == pytest.approx(70.182, rel=1.0e-3)
    assert es_kpa(90.0) == pytest.approx(70.182, rel=1.0e-3)


def test_es_kpa_bit_identical_below_switch_window():
    # Pre-rework Magnus formula; must match es_kpa bit-for-bit at and below 50 C.
    def magnus(t):
        return 0.61094 * math.exp(17.625 * t / (t + 243.04))
    for t in (-10.0, 0.0, 10.0, 25.0, 37.0, 50.0):
        assert es_kpa(t) == magnus(t)


def test_graph_energy_sweep_matches_segment_integration_single_channel():
    size = 32
    filled = np.full((size, size), 2200.0, dtype=np.float64)
    for i in range(size):
        filled[size // 2, i] = 2200.0 - 0.1 * i
    weights = outflow_thermal._outflow_network.mfd_weights(
        filled, cell_m=1.0, exponent=1.0)
    discharge = np.zeros_like(filled, dtype=np.float32)
    rim_j = size // 2
    rim_i = 0
    discharge_val = 0.1
    discharge_cube = outflow_thermal._outflow_network.propagate_discharge(
        weights, filled, [(0, rim_j, rim_i, discharge_val)])
    discharge = discharge_cube[0][0]
    met = _calm_dry_met(air_c=10.0, wind_mps=2.0, shortwave=0.0)
    injections = [(rim_j, rim_i, discharge_val, 70.0)]
    sweep = outflow_thermal.graph_energy_sweep(
        filled, weights, discharge, injections, met,
        sinter=_no_sinter(), step_m=1.0, min_film_depth_m=0.0,
    )
    temp = sweep["temperature"]
    seg = _straight_segment(length_m=float(size - rim_i - 1),
                            width_m=1.0, slope=0.1)
    profile = outflow_thermal.segment_temperature(
        70.0, seg, discharge_val, met,
        sinter=_no_sinter(), step_count=500)
    end_cell_t = float(temp[rim_j, size - 1])
    reference_t = profile["t_c"][-1]
    assert abs(end_cell_t - reference_t) < 3.0


def test_graph_energy_sweep_no_cell_below_equilibrium_or_above_vent():
    size = 32
    filled = np.full((size, size), 2200.0, dtype=np.float64)
    for i in range(size):
        filled[size // 2, i] = 2200.0 - 0.1 * i
    weights = outflow_thermal._outflow_network.mfd_weights(
        filled, cell_m=1.0, exponent=1.0)
    discharge_val = 0.001
    rim_j = size // 2
    rim_i = 0
    discharge_cube = outflow_thermal._outflow_network.propagate_discharge(
        weights, filled, [(0, rim_j, rim_i, discharge_val)])
    discharge = discharge_cube[0][0]
    met = _calm_dry_met(air_c=15.2, wind_mps=2.5, shortwave=512.0)
    injections = [(rim_j, rim_i, discharge_val, 70.0)]
    sweep = outflow_thermal.graph_energy_sweep(
        filled, weights, discharge, injections, met,
        sinter=_no_sinter(), step_m=1.0, min_film_depth_m=0.0,
    )
    t_eq = sweep["t_equilibrium_c"]
    assert t_eq > met.air_c - 2.0
    wet_cells = sweep["wet_mask"]
    wet_temps = sweep["temperature"][wet_cells]
    eps = 0.05
    assert float(wet_temps.min()) >= t_eq - eps
    assert float(wet_temps.max()) <= 70.0 + eps


def test_graph_energy_sweep_closes_energy_budget_on_synthetic_channel():
    size = 16
    filled = np.full((size, size), 2200.0, dtype=np.float64)
    for i in range(size):
        filled[size // 2, i] = 2200.0 - 0.05 * i
    weights = outflow_thermal._outflow_network.mfd_weights(
        filled, cell_m=1.0, exponent=1.0)
    discharge_val = 0.05
    rim_j = size // 2
    rim_i = 0
    discharge_cube = outflow_thermal._outflow_network.propagate_discharge(
        weights, filled, [(0, rim_j, rim_i, discharge_val)])
    discharge = discharge_cube[0][0]
    met = _calm_dry_met(air_c=10.0, wind_mps=2.0, shortwave=0.0)
    injections = [(rim_j, rim_i, discharge_val, 70.0)]
    sweep = outflow_thermal.graph_energy_sweep(
        filled, weights, discharge, injections, met,
        sinter=_no_sinter(), step_m=1.0, min_film_depth_m=0.0,
    )
    injected = sweep["injected_qt_wk"]
    exported = sweep["exported_qt_wk"]
    surface = sweep["surface_loss_wk"]
    sinter = sweep["sinter_loss_wk"]
    denom = outflow_thermal.RHO_WATER_KG_M3 * outflow_thermal.CP_WATER_J_KG_K
    injected_power = injected * denom
    exported_power = exported * denom
    budget_residual = injected_power - exported_power - surface - sinter
    assert abs(budget_residual) < 0.05 * injected_power
