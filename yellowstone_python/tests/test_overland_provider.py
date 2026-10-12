"""Schema and runoff checks for the synthetic overland provider."""
import importlib
import math

import pytest

from yellowstone_python import overland_provider as OP

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
    """Nonphysical inputs fail loudly."""
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


@needs_landlab
def test_landlab_path_routes_synthetic_catchment():
    """Landlab drainage area feeds the discharge interface."""
    elevation = OP.synthetic_elevation(nrows=8, ncols=8, dx_m=30.0)
    out = OP.predict_discharge_landlab(elevation, 30.0, [10.0, 0.0])
    assert out["method"] == OP.METHOD_LANDLAB
    assert out["status"] == "synthetic_catchment_predicted_not_validated"
    assert all(math.isfinite(q) for q in out["discharge_m3_s"])
    assert out["discharge_m3_s"][0] > 0.0
    assert out["discharge_m3_s"][1] == 0.0
