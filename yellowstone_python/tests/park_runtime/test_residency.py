"""River segment residency: coarse tier, anticipation, admission, worker spin-up and walks."""
import copy
import math
import pytest

from tests.paths import DATA
from yellowstone_python.common.io import load_json
from yellowstone_python.park_runtime.coarse_river import (CoarseRiverSegmentDomain, coarse_river,
                                                          prolong_temperatures, restrict_temperatures)
from yellowstone_python.park_runtime.firehole_split import (RiverInterface, RiverSegmentDomain, face_conductance,
                                                            segment_river)
from yellowstone_python.park_runtime.residency import (ResidencyManager, SegmentSpec, admit, anticipation,
                                                       evaluate_walk, replay_segment, run_walk, spinup_job)
from yellowstone_python.park_runtime.runtime import ParkRuntime
from yellowstone_python.river.river_transport import demo_config, river_from_config

# Walk acceptance tolerances, set before the walk run.
SWAP_REL = 1e-12
CLOSURE_REL = 1e-9
MAX_FINE = 3


def assert_walk_accepted(manager, reports, start_m, speed_mps):
    result = evaluate_walk(manager, reports, start_m, speed_mps)
    assert result["arrivals"]
    assert result["activated_before_arrival"], result["arrivals"]
    assert result["reports_on_coarse"] == 0
    assert result["retirements"]
    assert result["max_retire_delay_s"] <= manager.retire_after_s + manager.quantum_s + 1e-9
    assert result["passed_segments"] and result["passed_segments_coarse"]
    assert result["max_fine"] <= MAX_FINE
    assert result["max_swap_water_relative"] <= SWAP_REL
    assert result["max_swap_heat_relative"] <= SWAP_REL
    assert result["admission_inside_budget"]
    ledger = result["ledger"]
    assert ledger["heat_closure_relative"] <= CLOSURE_REL
    assert ledger["water_closure_relative"] <= CLOSURE_REL
    assert all(face["heat_relative"] <= CLOSURE_REL and face["water_relative"] <= CLOSURE_REL
               for face in ledger["faces"])
    return result


def test_coarse_restriction_and_prolongation_conserve_heat():
    full = river_from_config(demo_config())
    segment = segment_river(full, 0, 60)
    coarse, groups = coarse_river(segment, 7)
    assert [hi - lo for lo, hi in groups] == [6, 1] + [7] * 6 + [11]
    assert groups[1][0] == 6 and coarse.sources[0].cell_id == coarse.cells[1].id
    fine_heat = math.fsum(c.volume_m3 * t for c, t in zip(segment.cells, segment.temperature_c))
    coarse_heat = math.fsum(c.volume_m3 * t for c, t in zip(coarse.cells, coarse.temperature_c))
    assert coarse_heat == pytest.approx(fine_heat, rel=1e-14)
    assert math.fsum(c.surface_area_m2 for c in coarse.cells) == pytest.approx(
        math.fsum(c.surface_area_m2 for c in segment.cells), rel=1e-14)
    assert restrict_temperatures(segment.cells, segment.temperature_c, groups) == list(coarse.temperature_c)
    shape = [t + 0.1 * (i % 5) for i, t in enumerate(segment.temperature_c)]
    temps, shifts = prolong_temperatures(segment.cells, shape, list(coarse.temperature_c), groups, coarse.rho_cp)
    for (lo, hi), cell in zip(groups, coarse.cells):
        held = math.fsum(c.volume_m3 * t for c, t in zip(segment.cells[lo:hi], temps[lo:hi]))
        assert held == pytest.approx(cell.volume_m3 * coarse.temperature_c[groups.index((lo, hi))], rel=1e-14)
    assert any(abs(s) > 0 for s in shifts)


def test_end_cell_conductance_equals_the_solver_face_dispersion():
    full = river_from_config(demo_config())
    assert [face_conductance(a, b) for a, b in zip(full.cells, full.cells[1:])] == list(
        full.face_dispersion_m3_s[1:-1])


def test_coarse_segment_between_fine_neighbors_closes_budget():
    full = river_from_config(demo_config())
    upper = RiverSegmentDomain("demo.s0", segment_river(full, 0, 20))
    middle = CoarseRiverSegmentDomain("demo.s1", coarse_river(segment_river(full, 20, 40), 5)[0], dt_s=10.0)
    lower = RiverSegmentDomain("demo.s2", segment_river(full, 40, 60))
    faces = [RiverInterface("demo.s0:demo.s1", "demo.s0", "demo.s1"),
             RiverInterface("demo.s1:demo.s2", "demo.s1", "demo.s2")]
    start = math.fsum(d.stores().heat_j for d in (upper, middle, lower))
    runtime = ParkRuntime([upper, middle, lower], quantum_s=10.0, history_s=20.0, max_frames=8, couplers=faces)
    while runtime.time_s < 3600.0 - 1e-9:
        runtime.advance_one(runtime.time_s + 10.0)
        runtime.prune(runtime.time_s)
    budgets = [d.river.budget() for d in (upper, middle, lower)]
    for up, down in zip(budgets, budgets[1:]):
        assert down["boundary_input_j"] == pytest.approx(up["outlet_export_j"], rel=1e-12)
        assert down["boundary_input_m3"] == pytest.approx(up["outlet_export_m3"], rel=1e-12)
    external = math.fsum((budgets[0]["boundary_input_j"], -budgets[2]["outlet_export_j"],
                          *(b[k] for b in budgets for k in ("lateral_input_j", "surface_exchange_j", "cell_heat_j"))))
    end = math.fsum(d.stores().heat_j for d in (upper, middle, lower))
    assert end - start == pytest.approx(external, rel=1e-9)
    assert middle.snapshot()["representation"] == "coarse"


def specs():
    return [SegmentSpec(f"t.s{k}", 10 * k, 10 * k + 10, 100.0 * k, 100.0 * (k + 1), 50.0) for k in range(4)]


def test_anticipation_ranks_reach_ahead_and_halo():
    assert anticipation(specs(), 90.0, 1.4, 100.0, 1.0) == [("t.s0", "reach"), ("t.s1", "reach"),
                                                            ("t.s2", "ahead")]
    assert anticipation(specs(), 250.0, 1.0, 100.0, 3.0) == [("t.s2", "reach"), ("t.s3", "ahead"),
                                                             ("t.s1", "halo"), ("t.s0", "halo")]
    assert anticipation(specs(), 230.0, -1.0, 40.0, 1.0) == [("t.s2", "reach"), ("t.s1", "ahead")]


def test_admission_holds_the_rate_when_the_reach_set_exceeds_capacity():
    cells = {"a": 50, "b": 50, "c": 50}
    ranked = [("a", "reach"), ("b", "ahead"), ("c", "halo")]
    assert admit(ranked, cells, 1000.0, 1.0).fine == ("a", "b", "c")
    partial = admit(ranked, cells, 1000.0, 10.0)
    assert partial.fine == ("a",) and partial.coarse == ("b", "c") and not partial.held
    held = admit(ranked, cells, 1000.0, 20.0)
    assert held.fine == ("a",) and held.held and held.effective_rate == pytest.approx(16.0)
    assert held.demand <= held.budget
    assert admit(ranked, cells, None, 3600.0).fine == ("a", "b", "c")


@pytest.fixture
def demo_manager():
    manager = ResidencyManager(demo_config(), [20, 40], prefix="demo", workers=1, virtual_wall=True,
                               velocity_mps=1.4)
    yield manager
    manager.close()


def test_worker_spinup_equals_the_in_process_replay(demo_manager):
    for _ in range(30):
        demo_manager.advance(demo_manager.runtime.time_s + demo_manager.quantum_s)
    spec = demo_manager.by_id["demo.s1"]
    start = list(demo_manager.fine_pristine["demo.s1"].temperature_c)
    inlet, outlet = demo_manager._faces("demo.s1", 0.0, demo_manager.runtime.time_s)
    local = replay_segment(copy.deepcopy(demo_manager.fine_pristine["demo.s1"]), 0.0, start, inlet, outlet,
                           demo_manager.runtime.time_s, 1.0)
    remote = demo_manager.pool.submit(spinup_job, spec.lo, spec.hi, 0.0, start, inlet, outlet,
                                      demo_manager.runtime.time_s, 1.0).result()
    assert remote["temperature_c"] == local
    assert remote["end_s"] == demo_manager.runtime.time_s and remote["wall_s"] > 0


def test_synthetic_walk_activates_ahead_and_retires_behind(demo_manager):
    end = demo_manager.specs[-1].end_m
    reports = run_walk(demo_manager, 0.0, end, 1.4)
    result = assert_walk_accepted(demo_manager, reports, 0.0, 1.4)
    assert [a["domain_id"] for a in result["arrivals"]] == ["demo.s1", "demo.s2"]
    assert {e["source"] for e in demo_manager.events if e["event"] == "activating"} <= {
        "published_initial_state", "coarse_prolonged"}


def test_a_returning_walker_reactivates_from_the_fine_checkpoint(demo_manager):
    reports = run_walk(demo_manager, 0.0, 1150.0, 1.4)
    assert reports[-1]["walker_on"] == "fine"
    assert demo_manager.runtime.domains["demo.s0"].representation == "coarse"
    wall = reports[-1]["wall_s"]
    for _ in range(40):
        demo_manager.advance(demo_manager.runtime.time_s + demo_manager.quantum_s)
        wall += demo_manager.quantum_s
        report = demo_manager.update(wall, 990.0, -1.4, 1.0)
    sources = [e["source"] for e in demo_manager.events if e["event"] == "activating" and e["domain_id"] == "demo.s0"]
    assert sources == ["fine_checkpoint"]
    assert report["walker_on"] == "fine" and "demo.s0" in report["fine"]
    ledger = demo_manager.tier_ledger()
    assert ledger["heat_closure_relative"] <= CLOSURE_REL


@pytest.mark.needs_world
def test_firehole_walk_activates_downstream_before_arrival_and_retires_upstream():
    document = load_json(DATA / "river_replay.json")
    from yellowstone_python.service.live.engine import replay_config
    config = replay_config(document.get("replay", document))
    manager = ResidencyManager(config, [46, 92, 138, 184, 230], workers=2, virtual_wall=True, velocity_mps=1.4)
    try:
        end = manager.specs[2].end_m
        reports = run_walk(manager, 0.0, end, 1.4)
        result = assert_walk_accepted(manager, reports, 0.0, 1.4)
        assert [a["domain_id"] for a in result["arrivals"]] == ["firehole.s1", "firehole.s2", "firehole.s3"]
        assert {"firehole.s0", "firehole.s1"} <= set(r["domain_id"] for r in result["retirements"])
    finally:
        manager.close()
