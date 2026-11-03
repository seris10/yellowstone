"""Solute transport carried by river segments in both representations and under residency."""
import copy
import json
import math

import pytest

from tests.park_runtime.test_park_focus import focus, straight_cells
from tests.park_runtime.test_residency import CLOSURE_REL, SWAP_REL, assert_walk_accepted
from tests.park_runtime.test_residency_state import walk_until_installed
from tests.paths import DATA
from yellowstone_python.common.io import load_json
from yellowstone_python.park_runtime.coarse_river import (CoarseRiverSegmentDomain, coarse_river, coarse_solutes,
                                                          prolong_concentrations, restrict_concentrations)
from yellowstone_python.park_runtime.firehole_split import (RiverInterface, RiverSegmentDomain, compare_chain,
                                                            segment_river, segment_solutes, solute_values)
from yellowstone_python.park_runtime.residency import (FIREHOLE_FACES, RESIDENCY_STATE_SCHEMA, ResidencyManager,
                                                       RiverChainage, evaluate_walk, firehole_residency,
                                                       replay_segment, run_walk, spinup_job)
from yellowstone_python.park_runtime.runtime import ParkRuntime
from yellowstone_python.park_runtime.service import RuntimeService
from yellowstone_python.park_runtime.state_store import StateStore
from yellowstone_python.river.river_transport import demo_config, river_from_config
from yellowstone_python.river.solute_transport import SOLUTE_KEYS, river_solute_transport

# Tolerances set before the runs.
INCREMENT_FRACTION = 4e-3
OUTLET_OVER_INPUT = 1e-4
FACE_REL = 1e-9
CHAIN_REL = 1e-9
EXACT_REL = 1e-14
COARSE_FACE_REL = 1e-12
REPLAY_REL = 1e-12

# Synthetic fixture: authored boundary chemistry and the bundled Excelsior values on the demo source.
FIXTURE = {"boundary": {"chloride_mg_l": 5.0, "arsenic_ug_l": 0.0, "boron_mg_l": 0.05},
           "sources": {"illustrative_thermal_inflow": {"chloride_mg_l": 258.0, "arsenic_ug_l": 1870.0,
                                                       "boron_mg_l": 3.01}}}


def assert_chain_accepted(report):
    assert report["quanta_compared"] > 0 and report["heat_identical"] and report["min_concentration"] >= 0.0
    for key, row in report["solutes"].items():
        assert row["mixed_increment"] > 0.0
        assert row["max_delta_over_increment"] <= INCREMENT_FRACTION, key
        assert row["outlet_over_input"] <= OUTLET_OVER_INPUT, key
        assert row["dispersion_cancel_relative"] <= CHAIN_REL and row["closure_relative"] <= CHAIN_REL, key
        for face in row["faces"]:
            assert face["inlet_relative"] <= FACE_REL and face["ledger_relative"] <= FACE_REL, (key, face)


def concentrations(m):
    return {key: [c for d in m.cells for c in m.runtime.domains[d].solutes.concentrations(key)] for key in SOLUTE_KEYS}


def worst_relative(a, b):
    return max(abs(x - y) / max(abs(x), abs(y), 1e-300) for key in SOLUTE_KEYS for x, y in zip(a[key], b[key]))


def manager(**kwargs):
    kwargs.setdefault("velocity_mps", 1.4)
    kwargs.setdefault("solutes", FIXTURE)
    return ResidencyManager(demo_config(), [20, 40], prefix="demo", workers=1, virtual_wall=True, **kwargs)


@pytest.fixture
def managers():
    made = []

    def make(**kwargs):
        made.append(manager(**kwargs))
        return made[-1]
    yield make
    for item in made:
        item.close()


def advance(m, quanta):
    for _ in range(quanta):
        m.advance(m.runtime.time_s + m.quantum_s)


def test_builder_labels_explicit_and_unknown_boundary_chemistry():
    river = river_from_config(demo_config())
    transport, provenance = river_solute_transport(river, FIXTURE)
    assert provenance == dict.fromkeys(SOLUTE_KEYS, "authored_explicit_concentration")
    assert transport.sources[0].status == "authored_explicit_concentration"
    with pytest.raises(ValueError, match="mapping_notes"):
        river_solute_transport(river, {})
    with pytest.raises(ValueError, match="unknown sources"):
        river_solute_transport(river, {"sources": {"other": FIXTURE["sources"]["illustrative_thermal_inflow"]}})


def test_demo_chain_matches_the_single_domain_transport():
    report = compare_chain(lambda: river_from_config(demo_config()), [20, 40], solute_settings=FIXTURE,
                           duration_s=1800.0)
    assert_chain_accepted(report)


@pytest.mark.needs_world
def test_firehole_chain_matches_the_single_domain_transport():
    from yellowstone_python.service.live.engine import replay_config
    document = load_json(DATA / "river_replay.json")
    solver = replay_config(document.get("replay", document))
    report = compare_chain(lambda: river_from_config(solver), list(FIREHOLE_FACES), solute_settings={},
                           duration_s=3600.0)
    assert_chain_accepted(report)
    assert report["boundary_provenance"] == {"chloride_mg_l": "fitted_from_upstream_gauge_sc",
                                             "arsenic_ug_l": "authored_zero_baseline_unknown_observation",
                                             "boron_mg_l": "authored_zero_baseline_unknown_observation"}


def test_coarse_restriction_and_prolongation_conserve_solute_mass():
    full = river_from_config(demo_config())
    transport, _ = river_solute_transport(full, FIXTURE)
    segment = segment_river(full, 0, 60)
    fine = segment_solutes(transport, segment, 0, 60)
    coarse, groups = coarse_river(segment, 7)
    merged = coarse_solutes(fine, coarse, groups)
    assert merged.sources[0].cell_id == coarse.cells[1].id
    shape = {key: [c * (1.0 + 0.2 * (i % 5)) for i, c in enumerate(fine.concentrations(key))] for key in SOLUTE_KEYS}
    restricted = restrict_concentrations(segment.cells, shape, groups)
    values, shifts = prolong_concentrations(segment.cells, shape, solute_values(merged), groups)
    for key in SOLUTE_KEYS:
        for (lo, hi), cell, value in zip(groups, coarse.cells, restricted[key]):
            fine_mass = math.fsum(c.volume_m3 * v for c, v in zip(segment.cells[lo:hi], shape[key][lo:hi]))
            assert cell.volume_m3 * value == pytest.approx(fine_mass, rel=EXACT_REL, abs=0.0)
        for (lo, hi), cell, target in zip(groups, coarse.cells, merged.concentrations(key)):
            held = math.fsum(c.volume_m3 * v for c, v in zip(segment.cells[lo:hi], values[key][lo:hi]))
            assert held == pytest.approx(cell.volume_m3 * target, rel=EXACT_REL, abs=0.0)
        assert min(values[key]) >= 0.0 and len(shifts[key]) == len(groups)
    zero = {key: [0.0] * 60 for key in SOLUTE_KEYS}
    uniform, _ = prolong_concentrations(segment.cells, zero, {key: [2.0] * len(groups) for key in SOLUTE_KEYS}, groups)
    assert all(v == 2.0 for key in SOLUTE_KEYS for v in uniform[key])


def test_coarse_solutes_between_fine_neighbors_close_the_chain():
    full = river_from_config(demo_config())
    transport, _ = river_solute_transport(full, FIXTURE)
    parts = []
    for lo, hi in ((0, 20), (20, 40), (40, 60)):
        segment = segment_river(full, lo, hi)
        parts.append((segment, segment_solutes(transport, segment, lo, hi)))
    upper = RiverSegmentDomain("demo.s0", parts[0][0], solutes=parts[0][1], solute_dt_s=10.0)
    coarse, groups = coarse_river(parts[1][0], 5)
    middle = CoarseRiverSegmentDomain("demo.s1", coarse, dt_s=10.0, solutes=coarse_solutes(parts[1][1], coarse, groups))
    lower = RiverSegmentDomain("demo.s2", parts[2][0], solutes=parts[2][1], solute_dt_s=10.0)
    domains = (upper, middle, lower)
    faces = [RiverInterface("demo.s0:demo.s1", "demo.s0", "demo.s1"),
             RiverInterface("demo.s1:demo.s2", "demo.s1", "demo.s2")]
    runtime = ParkRuntime(list(domains), quantum_s=10.0, history_s=20.0, max_frames=8, couplers=faces)
    while runtime.time_s < 3600.0 - 1e-9:
        runtime.advance_one(runtime.time_s + 10.0)
        runtime.prune(runtime.time_s)
    budgets = [d.solutes.mass_budget()["solutes"] for d in domains]
    for key in SOLUTE_KEYS:
        for up, down in zip(budgets, budgets[1:]):
            exported = up[key]["outlet_export_mass"]
            assert abs(down[key]["boundary_input_mass"] - exported) <= COARSE_FACE_REL * exported
        terms = (budgets[0][key]["boundary_input_mass"], -budgets[2][key]["outlet_export_mass"],
                 *(b[key][name] for b in budgets for name in ("lateral_input_mass", "cell_input_mass")))
        storage = math.fsum(b[key]["storage_change_mass"] for b in budgets)
        assert abs(storage - math.fsum(terms)) <= CHAIN_REL * math.fsum(abs(x) for x in terms)
    assert middle.snapshot()["representation"] == "coarse" and set(middle.snapshot()["solutes"]) == set(SOLUTE_KEYS)
    with pytest.raises(ValueError, match="carry solutes or neither"):
        RiverInterface("x", "a", "b").begin(upper, RiverSegmentDomain("b", segment_river(full, 20, 40)), 0.0, 10.0)


def assert_solute_ledger(m, result=None):
    ledger = m.tier_ledger()["solutes"]
    for key, row in ledger.items():
        assert row["closure_relative"] <= CLOSURE_REL, key
        assert all(face["relative"] <= CLOSURE_REL for face in row["faces"]), key
    if result is not None:
        assert result["max_swap_solute_relative"] <= SWAP_REL
    return ledger


def test_walk_carries_solutes_through_every_hand_off(managers):
    m = managers()
    end = m.specs[-1].end_m
    reports = run_walk(m, 0.0, end, 1.4)
    result = assert_walk_accepted(m, reports, 0.0, 1.4)
    assert_solute_ledger(m, result)
    retired = [s for s in m.swaps if s["domain_id"] == "demo.s0" and s["reason"] == "retire"]
    assert retired and retired[0]["solute_relative"]["arsenic_ug_l"] <= SWAP_REL
    assert all(r["walker_solutes"] is not None and min(r["walker_solutes"].values()) >= 0.0 for r in reports)
    assert reports[-1]["solute_provenance"] == dict.fromkeys(SOLUTE_KEYS, "authored_explicit_concentration")


def test_worker_spinup_replays_solutes_exactly(managers):
    m = managers(position_m=1000.0, velocity_mps=0.0)
    assert m.runtime.domains["demo.s1"].representation == "fine"
    advance(m, 30)
    spec = m.by_id["demo.s1"]
    temps = list(m.fine_pristine["demo.s1"].temperature_c)
    start = solute_values(m.fine_solutes["demo.s1"])
    inlet, outlet = m._faces("demo.s1", 0.0, m.runtime.time_s)
    river, solutes = copy.deepcopy(m.fine_pristine["demo.s1"]), copy.deepcopy(m.fine_solutes["demo.s1"])
    local = replay_segment(river, 0.0, temps, inlet, outlet, m.runtime.time_s, 1.0, solutes=solutes,
                           concentrations=start, solute_dt_s=m.solute_dt_s)
    remote = m.pool.submit(spinup_job, spec.lo, spec.hi, 0.0, temps, inlet, outlet, m.runtime.time_s, 1.0, (),
                           start, m.solute_dt_s).result()
    assert remote["temperature_c"] == local and remote["concentrations"] == solute_values(solutes)
    ran = m.runtime.domains["demo.s1"].solutes
    assert worst_relative(solute_values(ran), remote["concentrations"]) <= REPLAY_REL
    with pytest.raises(ValueError, match="exactly when the worker carries solutes"):
        m.pool.submit(spinup_job, spec.lo, spec.hi, 0.0, temps, inlet, outlet, m.runtime.time_s, 1.0).result()


def test_head_chemistry_rollback_matches_a_frontier_intervention(managers):
    change = {"solute.boundary.chloride_mg_l": 20.0}
    rolled, reference = managers(), managers()
    advance(rolled, 12)
    advance(reference, 11)
    a = rolled.intervene("salt", "demo.s0", 110.0, change)
    b = reference.intervene("salt", "demo.s0", 110.0, change)
    assert a == b and rolled.runtime.time_s == reference.runtime.time_s == 110.0
    advance(rolled, 60)
    advance(reference, 60)
    assert worst_relative(concentrations(rolled), concentrations(reference)) <= REPLAY_REL
    assert concentrations(rolled)["chloride_mg_l"] != concentrations(managers())["chloride_mg_l"]


def test_source_chemistry_change_on_a_coarse_segment_reaches_the_installed_segment(managers):
    m = managers(position_m=2500.0, velocity_mps=0.0)
    assert m.runtime.domains["demo.s0"].representation == "coarse"
    m.intervene("source", "demo.s0", 0.0, {"solute.source.illustrative_thermal_inflow.arsenic_ug_l": 900.0})
    walk_until_installed(m, "demo.s0", 100.0)
    installed = m.runtime.domains["demo.s0"].solutes
    assert installed.sources[0].concentrations["arsenic_ug_l"].at(installed.time_s) == 900.0
    assert_solute_ledger(m)


def test_refused_solute_interventions_leave_the_state_unchanged(managers):
    m = managers()
    advance(m, 3)
    before = (concentrations(m), m.runtime.revision, len(m._snapshots), m.runtime.time_s)
    refusals = [("demo.s0", {"solute.cell_mass.chloride_mg_l.channel_000": 1.0}, "representation-specific"),
                ("demo.s1", {"solute.boundary.chloride_mg_l": 1.0}, "upstream interface"),
                ("demo.s0", {"solute.boundary.lead_mg_l": 1.0}, "unknown solute forcing"),
                ("demo.s0", {"solute.boundary.chloride_mg_l": -1.0}, "chloride"),
                ("demo.s0", {"solute.source.missing.arsenic_ug_l": 1.0}, "unknown solute source")]
    for k, (domain_id, changes, message) in enumerate(refusals):
        with pytest.raises(ValueError, match=message):
            m.intervene(f"bad{k}", domain_id, m.runtime.time_s, changes)
        assert (concentrations(m), m.runtime.revision, len(m._snapshots), m.runtime.time_s) == before
    plain = managers(solutes=None)
    with pytest.raises(ValueError, match="without solutes"):
        plain.intervene("salt", "demo.s0", 0.0, {"solute.boundary.chloride_mg_l": 1.0})


def test_save_and_load_restore_the_solute_state(managers, tmp_path):
    m = managers(position_m=900.0)
    m.intervene("source", "demo.s0", 0.0, {"solute.source.illustrative_thermal_inflow.boron_mg_l": 6.0})
    walk_until_installed(m, "demo.s1", 900.0)
    store = StateStore(tmp_path / "residency.sqlite3")
    assert m.save_committed(store, "frontier", m.runtime.time_s) == m.runtime.time_s
    loaded = managers(position_m=900.0)
    assert loaded.load_committed(store, "frontier")
    assert concentrations(loaded) == concentrations(m)
    assert [c.solute_totals for c in loaded.runtime.couplers] == [c.solute_totals for c in m.runtime.couplers]
    for key, history in loaded.coarse_history.items():
        assert list(history) == list(m.coarse_history[key])
    for key, history in loaded.face_history.items():
        assert list(history) == list(m.face_history[key])
    assert loaded.last_fine == m.last_fine and loaded.initial_solutes == m.initial_solutes
    assert loaded.tier_ledger()["solutes"] == m.tier_ledger()["solutes"]
    advance(m, 30)
    advance(loaded, 30)
    assert worst_relative(concentrations(loaded), concentrations(m)) <= REPLAY_REL
    assert_solute_ledger(loaded)
    other = managers(solutes={**FIXTURE, "boundary": {**FIXTURE["boundary"], "chloride_mg_l": 6.0}})
    with pytest.raises(ValueError, match="different replay"):
        other.load_committed(store, "frontier")
    store.save("legacy", "yellowstone.park_residency_state.v1", 0.0, 0, {"schema": "v1"})
    with pytest.raises(ValueError, match="explicit save migration required"):
        loaded.load_committed(store, "legacy")
    assert RESIDENCY_STATE_SCHEMA == "yellowstone.park_residency_state.v2"
    store.close()


def test_service_publishes_cell_and_walker_solutes():
    m = ResidencyManager(demo_config(), [20, 40], prefix="demo", workers=1, solutes=FIXTURE)
    service = RuntimeService(m.runtime, horizon_s=m.quantum_s, residency=m,
                             chainage=RiverChainage(straight_cells(river_from_config(demo_config()))))
    try:
        block = service._command("focus", focus(1, m.specs[0].start_m + 200.0, vx=1.4))
        assert block["walker"]["solutes"]["chloride_mg_l"] == pytest.approx(5.0)
        service._publish()
        data = json.loads(service.publication())
        assert data["residency"]["solute_boundary_provenance"]["chloride_mg_l"] == "authored_explicit_concentration"
        region = data["bracket"][0]["regions"]["demo.s0"]
        assert set(region["solutes"]) == set(SOLUTE_KEYS) and len(region["solutes"]["boron_mg_l"]) == 20
    finally:
        service.close()
        m.close()


@pytest.mark.needs_world
def test_firehole_walk_carries_the_excelsior_solutes_through_two_installs():
    document = load_json(DATA / "river_replay.json")
    probe, _ = firehole_residency(document, workers=1)
    s2, s4 = probe.by_id["firehole.s2"], probe.by_id["firehole.s4"]
    probe.close()
    m, _ = firehole_residency(document, workers=2, virtual_wall=True, velocity_mps=1.4, position_m=s2.start_m)
    try:
        reports = run_walk(m, s2.start_m, s4.end_m, 1.4)
        result = evaluate_walk(m, reports, s2.start_m, 1.4)
        # The walk ends on the upstream face of firehole.s5.
        assert [a["domain_id"] for a in result["arrivals"]] == ["firehole.s3", "firehole.s4", "firehole.s5"]
        assert result["activated_before_arrival"] and result["reports_on_coarse"] == 0
        ledger = m.tier_ledger()
        assert ledger["heat_closure_relative"] <= CLOSURE_REL and ledger["water_closure_relative"] <= CLOSURE_REL
        assert result["max_swap_heat_relative"] <= SWAP_REL
        assert_solute_ledger(m, result)
        assert max(m.runtime.domains["firehole.s4"].solutes.concentrations("arsenic_ug_l")) > 0.0
        assert m.solute_provenance["arsenic_ug_l"] == "authored_zero_baseline_unknown_observation"
    finally:
        m.close()
