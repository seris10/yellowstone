"""Mapping checks for the synthetic groundwater provider."""
import importlib

import pytest

from yellowstone_python import groundwater_provider as GP
from yellowstone_python.replay.river_transport import Series

needs_flopy = pytest.mark.skipif(
    importlib.util.find_spec("flopy") is None, reason="flopy not present"
)


def _reach(**over):
    base = {
        "source_id": "gw_lateral_001",
        "cell_id": "channel_010",
        "gw_cell": [0, 1, 2],
        "flow_m3_s": 0.05,
        "temperature_c": 30.0,
    }
    base.update(over)
    return base


def test_mapping_emits_source_dicts():
    """Reach flows map to per-receiving-cell lateral dicts."""
    out = GP.riv_reaches_to_sources([_reach()])
    assert len(out) == 1
    lateral = out[0]
    assert lateral["source_id"] == "gw_lateral_001"
    assert lateral["cell_id"] == "channel_010"
    assert lateral["flow_m3_s"] == pytest.approx(0.05)
    assert lateral["status"] == "synthetic_modeled_not_calibrated"
    assert "synthetic" in lateral["status"]


def test_temperature_spec_parses_as_solver_series():
    """Emitted temperature specs load through the transport Series parser."""
    out = GP.riv_reaches_to_sources([_reach(temperature_c=30.0)])
    series = Series.parse(out[0]["temperature_c"])
    assert series.at(0.0) == pytest.approx(30.0)
    scheduled = _reach(
        source_id="gw_lateral_002",
        temperature_c={"times_s": [0.0, 600.0], "values": [25.0, 35.0]},
    )
    out = GP.riv_reaches_to_sources([scheduled])
    series = Series.parse(out[0]["temperature_c"])
    assert series.at(900.0) == pytest.approx(35.0)


def test_provenance_names_package_and_time_range():
    """Provenance carries MF6 version, package, cell, and time range."""
    out = GP.riv_reaches_to_sources(
        [_reach()], t0_epoch_s=1000.0, dt_s=600.0, stress_period=2
    )
    prov = out[0]["provenance"]
    assert prov["package"] == "RIV"
    assert prov["mf6_version"]
    assert prov["gw_cell"] == [0, 1, 2]
    assert prov["stress_period"] == 2
    assert prov["t0_epoch_s"] == 1000.0
    assert prov["t1_epoch_s"] > prov["t0_epoch_s"]


def test_rejects_bad_reaches():
    """Malformed reaches fail loudly."""
    with pytest.raises(ValueError):
        GP.riv_reaches_to_sources([])
    with pytest.raises(ValueError):
        GP.riv_reaches_to_sources([_reach(source_id="")])
    with pytest.raises(ValueError):
        GP.riv_reaches_to_sources([_reach(gw_cell=[0, -1])])
    with pytest.raises(ValueError):
        GP.riv_reaches_to_sources([_reach(temperature_c=float("nan"))])


def test_chainage_adapter_stamps_s_m():
    """Provider laterals map to mapped-replay chainage entries."""
    out = GP.riv_reaches_to_sources([_reach()])
    chained = GP.with_chainage(out, {"gw_lateral_001": 120.0})
    assert chained[0]["id"] == "gw_lateral_001"
    assert chained[0]["s_m"] == 120.0
    assert chained[0]["flow_m3_s"] == pytest.approx(0.05)


def test_chainage_adapter_rejects():
    """Missing chainage, losing reaches, and bad maps fail loudly."""
    out = GP.riv_reaches_to_sources([_reach()])
    with pytest.raises(ValueError):
        GP.with_chainage(out, {"other": 1.0})
    with pytest.raises(ValueError):
        GP.with_chainage(out, [_reach()])
    losing = GP.riv_reaches_to_sources([_reach(flow_m3_s=-0.01)])
    with pytest.raises(ValueError):
        GP.with_chainage(losing, {"gw_lateral_001": 1.0})


@needs_flopy
def test_flopy_model_carries_riv_package():
    """Synthetic MF6 simulation exposes a mapped RIV package."""
    sim = GP.synthetic_mf6_simulation(nrow=3, ncol=3)
    gwf = sim.get_model("synthetic_gwf")
    assert gwf is not None
    assert gwf.get_package("riv") is not None
