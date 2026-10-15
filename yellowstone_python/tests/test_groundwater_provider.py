"""Mapping checks for the synthetic groundwater provider."""
import importlib

import pytest

import yellowstone_python.land.groundwater_provider as GP
from yellowstone_python.river.river_transport import Series

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
    out = GP.authored_reaches_to_sources([_reach()])
    assert len(out) == 1
    lateral = out[0]
    assert lateral["source_id"] == "gw_lateral_001"
    assert lateral["cell_id"] == "channel_010"
    assert lateral["flow_m3_s"] == pytest.approx(0.05)
    assert lateral["status"] == "authored_lateral_not_modeled"
    assert "authored" in lateral["status"]
    assert "package" not in lateral["provenance"]
    assert "mf6_version" not in lateral["provenance"]


def test_legacy_alias_points_to_authored_mapping():
    """The RIV-styled alias calls the authored mapping."""
    assert GP.riv_reaches_to_sources is GP.authored_reaches_to_sources


def test_temperature_spec_parses_as_solver_series():
    """Emitted temperature specs load through the transport Series parser."""
    out = GP.authored_reaches_to_sources([_reach(temperature_c=30.0)])
    series = Series.parse(out[0]["temperature_c"])
    assert series.at(0.0) == pytest.approx(30.0)
    scheduled = _reach(
        source_id="gw_lateral_002",
        temperature_c={"times_s": [0.0, 600.0], "values": [25.0, 35.0]},
    )
    out = GP.authored_reaches_to_sources([scheduled])
    series = Series.parse(out[0]["temperature_c"])
    assert series.at(900.0) == pytest.approx(35.0)


def test_provenance_names_cell_and_time_range():
    """Provenance carries cell, stress period, and time range."""
    out = GP.authored_reaches_to_sources(
        [_reach()], t0_epoch_s=1000.0, dt_s=600.0, stress_period=2
    )
    prov = out[0]["provenance"]
    assert prov["gw_cell"] == [0, 1, 2]
    assert prov["stress_period"] == 2
    assert prov["t0_epoch_s"] == 1000.0
    assert prov["t1_epoch_s"] > prov["t0_epoch_s"]


def test_rejects_bad_reaches():
    """Malformed reaches raise an error."""
    with pytest.raises(ValueError):
        GP.authored_reaches_to_sources([])
    with pytest.raises(ValueError):
        GP.authored_reaches_to_sources([_reach(source_id="")])
    with pytest.raises(ValueError):
        GP.authored_reaches_to_sources([_reach(gw_cell=[0, -1])])
    with pytest.raises(ValueError):
        GP.authored_reaches_to_sources([_reach(temperature_c=float("nan"))])


def test_losing_reach_rejected_at_mapping():
    """Negative flow_m3_s is refused by the first boundary, before chainage."""
    with pytest.raises(ValueError, match=r"flow_m3_s.*>= 0\.0"):
        GP.authored_reaches_to_sources([_reach(flow_m3_s=-0.01)])
    with pytest.raises(ValueError, match=r"flow_m3_s.*>= 0\.0"):
        GP.riv_reaches_to_sources([_reach(flow_m3_s=-0.01)])


def test_chainage_adapter_stamps_s_m():
    """Provider laterals map to mapped-replay chainage entries."""
    out = GP.authored_reaches_to_sources([_reach()])
    chained = GP.with_chainage(out, {"gw_lateral_001": 120.0})
    assert chained[0]["id"] == "gw_lateral_001"
    assert chained[0]["s_m"] == 120.0
    assert chained[0]["flow_m3_s"] == pytest.approx(0.05)


def test_chainage_adapter_rejects():
    """Missing chainage, hand-built losing laterals, and bad maps raise an error."""
    out = GP.authored_reaches_to_sources([_reach()])
    with pytest.raises(ValueError):
        GP.with_chainage(out, {"other": 1.0})
    with pytest.raises(ValueError):
        GP.with_chainage(out, [_reach()])
    hand_losing = [{
        "source_id": "gw_lateral_001",
        "cell_id": "channel_010",
        "flow_m3_s": -0.01,
        "temperature_c": 30.0,
        "status": GP.STATUS,
        "provenance": {},
    }]
    with pytest.raises(ValueError, match="losing reach"):
        GP.with_chainage(hand_losing, {"gw_lateral_001": 1.0})


@pytest.mark.needs_science
@needs_flopy
def test_flopy_model_carries_riv_package():
    """Synthetic MF6 simulation exposes a mapped RIV package."""
    sim = GP.synthetic_mf6_simulation(nrow=3, ncol=3)
    gwf = sim.get_model("synthetic_gwf")
    assert gwf is not None
    assert gwf.get_package("riv") is not None


def _exchange_cell(**over):
    base = {
        "cell_id": "firehole_cell_00042",
        "bed_conductivity_m_s": 1.0e-5,
        "bed_thickness_m": 1.0,
        "width_m": 20.0,
        "length_m": 10.0,
        "h_aquifer_m": 2.0,
        "h_river_m": 1.0,
        "river_temperature_c": 15.0,
        "aquifer_temperature_c": 8.0,
        "aquifer_temperature_source": (
            "authored_shallow_aquifer_8C_illustrative"),
    }
    base.update(over)
    return base


def test_groundwater_exchange_sign_and_budget():
    """Gaining reach adds water and heat at the aquifer temperature."""
    gain = _exchange_cell()
    loss = _exchange_cell(
        cell_id="firehole_cell_00050",
        h_aquifer_m=0.5,
        h_river_m=1.5,
    )
    result = GP.head_gradient_exchange([gain, loss])
    # C = K*W*L/b = 1e-5 * 20 * 10 / 1 = 2e-3 m2/s; gain q = C * (2.0 - 1.0) = 2e-3 m3/s at aquifer temperature.
    assert len(result["sources"]) == 1
    source = result["sources"][0]
    assert source["cell_id"] == "firehole_cell_00042"
    assert source["flow_m3_s"] == pytest.approx(2.0e-3)
    series = Series.parse(source["temperature_c"])
    assert series.at(0.0) == pytest.approx(8.0)
    assert "head_gradient_gaining" in source["status"]
    assert source["provenance"]["aquifer_temperature_source"] == (
        "authored_shallow_aquifer_8C_illustrative")
    # Loss: q = C * (0.5 - 1.5) = -2e-3 m3/s; magnitude 2e-3; temperature is the river's.
    assert len(result["losing"]) == 1
    loss_record = result["losing"][0]
    assert loss_record["cell_id"] == "firehole_cell_00050"
    assert loss_record["flow_m3_s"] == pytest.approx(2.0e-3)
    assert loss_record["temperature_c"] == pytest.approx(15.0)
    # Budget: gaining and losing totals match the conductance law exactly.
    assert result["totals"]["gaining_flow_m3_s"] == pytest.approx(2.0e-3)
    assert result["totals"]["losing_flow_m3_s"] == pytest.approx(2.0e-3)
    assert result["totals"]["net_flow_m3_s"] == pytest.approx(0.0)
    # Heat exchange: gain adds (T_aq - T_river) * q * rho_cp; loss removes (T_river - T_aq) * q * rho_cp.
    rho_cp = GP.RHO_CP_WATER_J_M3_K
    expected_gain_heat = 2.0e-3 * (8.0 - 15.0) * rho_cp
    expected_loss_heat = -2.0e-3 * (15.0 - 8.0) * rho_cp
    assert result["totals"]["gaining_heat_j_s_vs_river"] == pytest.approx(
        expected_gain_heat)
    assert result["totals"]["losing_heat_j_s_vs_river"] == pytest.approx(
        expected_loss_heat)


def test_groundwater_exchange_requires_labeled_aquifer_temperature():
    """Aquifer temperature source must be a nonempty label."""
    with pytest.raises(ValueError):
        GP.head_gradient_exchange([_exchange_cell(
            aquifer_temperature_source=""
        )])
    with pytest.raises(ValueError):
        GP.head_gradient_exchange([_exchange_cell(
            bed_conductivity_m_s=0.0
        )])
    with pytest.raises(ValueError):
        GP.head_gradient_exchange([])
