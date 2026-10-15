"""Schema and runoff checks for the synthetic overland provider."""
import importlib
import math

import pytest

import yellowstone_python.land.overland_provider as OP

needs_landlab = pytest.mark.skipif(
    importlib.util.find_spec("landlab") is None, reason="landlab not present"
)


def test_interface_schema_always_runs():
    """Discharge dict carries series, bounds, method, and provenance."""
    out = OP.predict_discharge([5.0, 0.0], area_m2=1.0e6)
    assert out["t0_epoch_s"] == 0.0
    assert out["dt_s"] == 3600.0
    assert len(out["discharge_m3_s"]) == 2
    assert len(out["discharge_lo_m3_s"]) == 2
    assert len(out["discharge_hi_m3_s"]) == 2
    assert out["coverage"] == pytest.approx(0.90)
    assert out["method"] == OP.METHOD_AREA
    assert out["status"] == "synthetic_catchment_predicted_not_validated"
    assert "synthetic" in out["status"]
    assert out["model_version"]
    assert out["forcing_hash"]


def test_runoff_scales_with_coefficient_and_area():
    """Discharge equals coefficient times precipitation depth times area."""
    out = OP.predict_discharge([36.0], area_m2=1.0e6, runoff_coefficient=0.5)
    assert out["discharge_m3_s"][0] == pytest.approx(5.0)
    assert out["discharge_lo_m3_s"][0] < out["discharge_m3_s"][0]
    assert out["discharge_hi_m3_s"][0] > out["discharge_m3_s"][0]


def test_zero_rain_gives_zero_flow():
    """Dry steps produce zero discharge with zero-width bounds."""
    out = OP.predict_discharge([0.0, 0.0], area_m2=2.0e6)
    assert out["discharge_m3_s"] == [0.0, 0.0]
    assert out["discharge_lo_m3_s"] == [0.0, 0.0]


def test_forcing_hash_distinguishes_inputs():
    """Distinct forcing produces distinct hashes for provenance."""
    base = OP.predict_discharge([5.0], area_m2=1.0e6)
    wet = OP.predict_discharge([6.0], area_m2=1.0e6)
    assert base["forcing_hash"] != wet["forcing_hash"]


def test_rejects_bad_inputs():
    """Nonphysical inputs raise an error."""
    with pytest.raises(ValueError):
        OP.predict_discharge([], area_m2=1.0e6)
    with pytest.raises(ValueError):
        OP.predict_discharge([5.0], area_m2=-1.0)
    with pytest.raises(ValueError):
        OP.predict_discharge([5.0], area_m2=1.0e6, runoff_coefficient=1.5)
    with pytest.raises(ValueError):
        OP.predict_discharge([-2.0], area_m2=1.0e6)


def test_series_spec_matches_solver_clock():
    """Series-spec view carries one value per step from t=0."""
    out = OP.predict_discharge([5.0, 5.0], area_m2=1.0e6, dt_s=600.0)
    spec = OP.series_spec(out)
    assert spec["times_s"] == [0.0, 600.0]
    assert spec["values"] == out["discharge_m3_s"]


@pytest.mark.needs_science
@needs_landlab
def test_landlab_path_routes_synthetic_catchment():
    """Landlab drainage area feeds the discharge interface."""
    elevation = OP.synthetic_elevation(nrows=8, ncols=8, dx_m=30.0)
    out = OP.predict_discharge_landlab(elevation, 30.0, [10.0, 0.0],
                                       outlet_row=7, outlet_col=7)
    assert out["method"] == OP.METHOD_LANDLAB
    assert out["status"] == "synthetic_catchment_predicted_not_validated"
    assert all(math.isfinite(q) for q in out["discharge_m3_s"])
    assert out["discharge_m3_s"][0] > 0.0
    assert out["discharge_m3_s"][1] == 0.0
    assert out["outlet_row"] == 7 and out["outlet_col"] == 7
    assert out["boundary_condition"] == "fixed_value_boundary_node"
    assert out["drainage_area_m2"] > 0.0


@pytest.mark.needs_science
@needs_landlab
def test_landlab_requires_explicit_outlet():
    """Omitting outlet coordinates is rejected to keep the drain explicit."""
    elevation = OP.synthetic_elevation(nrows=8, ncols=8, dx_m=30.0)
    with pytest.raises(ValueError, match="outlet"):
        OP.predict_discharge_landlab(elevation, 30.0, [10.0, 0.0])


@pytest.mark.needs_science
@needs_landlab
def test_landlab_interior_outlet_records_warning():
    """An interior outlet is accepted but flagged as an interior sink."""
    elevation = OP.synthetic_elevation(nrows=8, ncols=8, dx_m=30.0)
    out = OP.predict_discharge_landlab(elevation, 30.0, [10.0],
                                       outlet_row=3, outlet_col=3)
    assert out["boundary_condition"] == "fixed_value_interior_node"
    assert any("interior" in w for w in out["warnings"])


def test_linear_reservoir_routing_lags_runoff_without_losing_volume():
    """Routing shifts volume into later steps while total mass is conserved."""
    base = OP.predict_discharge([50.0, 0.0, 0.0, 0.0],
                                area_m2=1.0e6, dt_s=600.0)
    routed = OP.predict_discharge([50.0, 0.0, 0.0, 0.0],
                                  area_m2=1.0e6, dt_s=600.0,
                                  routing_tau_s=1200.0)
    assert routed["routing"]["mode"] == "linear_reservoir"
    assert routed["routing"]["tau_s"] == 1200.0
    assert routed["routing"]["tau_status"] == "authored_not_calibrated"
    assert routed["discharge_m3_s"][0] < base["discharge_m3_s"][0]
    assert routed["discharge_m3_s"][1] > 0.0
    dt = 600.0
    direct_total = sum(base["discharge_m3_s"]) * dt
    routed_total = (sum(routed["discharge_m3_s"]) * dt
                    + routed["routing"]["storage_remaining_m3"])
    assert routed_total == pytest.approx(direct_total, rel=1e-9)


def test_runoff_temperature_scalar_broadcasts_and_rejects_out_of_range():
    """Scalar scenario temperature fills every step and bounds are enforced."""
    out = OP.predict_discharge([5.0, 5.0], area_m2=1.0e6,
                               runoff_temperature_c=12.5)
    assert out["temperature_c"] == [12.5, 12.5]
    assert out["temperature_status"] == "authored_scenario_value"
    with pytest.raises(ValueError):
        OP.predict_discharge([5.0], area_m2=1.0e6,
                             runoff_temperature_c=1000.0)


def test_boundary_role_round_trips_and_rejects_unknown():
    """Role label is preserved; unknown values are refused."""
    out = OP.predict_discharge([5.0], area_m2=1.0e6,
                               boundary_role="lateral_source")
    assert out["boundary_role"] == "lateral_source"
    with pytest.raises(ValueError):
        OP.predict_discharge([5.0], area_m2=1.0e6,
                             boundary_role="interior_point")


@pytest.mark.needs_science
def test_boundary_schedule_matches_river_series_parse():
    """boundary_schedule produces a Series.parse-compatible dict at t=0."""
    out = OP.predict_discharge([3.0, 6.0, 0.0], area_m2=1.0e6,
                               dt_s=1200.0, t0_epoch_s=100000.0)
    schedule = OP.boundary_schedule(out, river_t0_epoch_s=100000.0)
    assert schedule["times_s"][0] == 0.0
    assert len(schedule["times_s"]) == len(schedule["values"])
    assert all(b > a for a, b in zip(schedule["times_s"],
                                     schedule["times_s"][1:]))
    try:
        from yellowstone_python.river.river_transport import Series
    except ImportError:
        pytest.skip("replay.river_transport not importable")
    parsed = Series.parse(schedule)
    assert parsed.times_s[0] == 0.0
    assert parsed.values == tuple(schedule["values"])
