"""Firehole river split into two coupled domains against the single-domain solver."""
import pytest

from tests.paths import DATA
from yellowstone_python.common.io import load_json
from yellowstone_python.park_runtime.firehole_split import compare_split, firehole_pair
from yellowstone_python.park_runtime.runtime import ParkRuntime
from yellowstone_python.river.river_transport import river_from_config
from yellowstone_python.service.live.engine import replay_config

# Split acceptance tolerances, set before the comparison run.
WATER_REL = 1e-9
INTERFACE_REL = 1e-9
HEAT_BUDGET_REL = 1e-6
TEMPERATURE_C = 0.02
OUTLET_HEAT_REL = 1e-4


@pytest.fixture(scope="module")
def solver():
    document = load_json(DATA / "river_replay.json")
    return replay_config(document.get("replay", document))


def warm_front(solver):
    """River whose inflow runs 5 C above the published boundary from the start."""
    def make():
        river = river_from_config(solver)
        river.set_forcing("boundary_c", 0.0, river.boundary_c.at(0.0) + 5.0)
        return river
    return make


def assert_accepted(report):
    assert report["samples_compared"] > 0
    assert report["outlet_water_relative"] <= WATER_REL
    assert report["interface_water_relative"] <= INTERFACE_REL
    assert report["interface_heat_relative"] <= INTERFACE_REL
    assert report["ledger_water_relative"] <= INTERFACE_REL
    assert report["ledger_heat_relative"] <= INTERFACE_REL
    assert report["dispersion_cancel_j"] == pytest.approx(0.0, abs=1e-6)
    assert report["heat_budget_relative"] <= HEAT_BUDGET_REL
    assert report["max_temperature_delta_c"] <= TEMPERATURE_C
    assert report["outlet_heat_relative"] <= OUTLET_HEAT_REL


def test_split_at_the_acceptance_face_matches_the_single_domain_solver(solver):
    assert_accepted(compare_split(lambda: river_from_config(solver), 138, duration_s=1800.0))


def test_a_warm_front_crosses_the_interface_within_tolerance(solver):
    report = compare_split(warm_front(solver), 20, duration_s=1800.0)
    assert_accepted(report)
    assert report["max_temperature_delta_c"] > 0.0


def test_intervention_replay_records_each_interface_transfer_once(solver):
    upper, lower, interface = firehole_pair(river_from_config(solver), 20)
    runtime = ParkRuntime([lower, upper], quantum_s=10.0, history_s=600.0, couplers=[interface], max_frames=128)
    assert list(runtime.domains) == ["firehole.upper", "firehole.lower"]
    runtime.compute_until(300.0)
    runtime.intervene("warm", "firehole.upper", 200.0, {"boundary_c": 20.0})
    runtime.compute_until(400.0)
    total = interface.ledger.totals[interface.interface_id]
    upper_budget, lower_budget = upper.river.budget(), lower.river.budget()
    assert total.water_m3 == pytest.approx(upper_budget["outlet_export_m3"], rel=1e-12)
    assert lower_budget["boundary_input_m3"] == pytest.approx(upper_budget["outlet_export_m3"], rel=1e-12)
    assert lower_budget["boundary_input_j"] == pytest.approx(upper_budget["outlet_export_j"], rel=1e-12)
    fresh_upper, fresh_lower, fresh_interface = firehole_pair(river_from_config(solver), 20)
    fresh = ParkRuntime([fresh_upper, fresh_lower], quantum_s=10.0, history_s=600.0, couplers=[fresh_interface],
                        max_frames=128)
    fresh.compute_until(200.0)
    fresh.domains["firehole.upper"].intervene({"boundary_c": 20.0})
    fresh.compute_until(400.0)
    assert list(lower.river.temperature_c) == list(fresh_lower.river.temperature_c)
