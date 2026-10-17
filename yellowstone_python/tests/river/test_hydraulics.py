import math
import pytest

from yellowstone_python.river.hydraulics import TrapezoidGeometry, bed_shear_pa, cell_hydraulics, fischer_dispersion_m2_s, froude_number, manning_velocity_m_s, rectangular_area_m2, residual_diagnostics, score_paired_series, shear_velocity_m_s, skill_scores, slope_from_drop, thermal_inventory, travel_time_s
from yellowstone_python.river.river_world import build_mapped_replay

# Fixed replay epoch so the clock is deterministic across runs.
REPLAY_START = {"simulation_start_epoch_unix": 1784000000.0}


def test_trapezoid_rectangular_limit():
    g = TrapezoidGeometry(10.0, 2.0, 0.0)
    assert g.area_m2 == pytest.approx(20.0, abs=0.5 * 10 ** -(7), rel=0)
    assert g.wetted_perimeter_m == pytest.approx(14.0, abs=0.5 * 10 ** -(7), rel=0)
    assert g.bottom_width_m == pytest.approx(10.0, abs=0.5 * 10 ** -(7), rel=0)


def test_trapezoid_trapezoid_handcalc():
    # W=10, d=2, z=1: b=6, A=(10-2)*2=16, P=6+4*sqrt2
    g = TrapezoidGeometry(10.0, 2.0, 1.0)
    assert g.bottom_width_m == pytest.approx(6.0, abs=0.5 * 10 ** -(7), rel=0)
    assert g.area_m2 == pytest.approx(16.0, abs=0.5 * 10 ** -(7), rel=0)
    assert g.wetted_perimeter_m == pytest.approx(6.0 + 4.0 * math.sqrt(2.0), abs=0.5 * 10 ** -(7), rel=0)
    assert g.hydraulic_depth_m == pytest.approx(1.6, abs=0.5 * 10 ** -(7), rel=0)


def test_trapezoid_banks_meeting_rejected():
    with pytest.raises(ValueError):
        TrapezoidGeometry(3.0, 2.0, 1.0)  # b = 3-4 < 0
    with pytest.raises(ValueError):
        TrapezoidGeometry(10.0, -1.0, 1.0)


def test_trapezoid_rectangular_area_legacy():
    assert rectangular_area_m2(22.0, 1.1) == pytest.approx(24.2, abs=0.5 * 10 ** -(7), rel=0)



def test_manning_manning_handcalc():
    v = manning_velocity_m_s(1.0, 0.01, 0.05)
    assert v == pytest.approx(1.0 / 0.05 * 1.0 * math.sqrt(0.01), abs=0.5 * 10 ** -(7), rel=0)


def test_manning_manning_rejects_flat_grade():
    with pytest.raises(ValueError):
        manning_velocity_m_s(1.0, 0.0)
    with pytest.raises(ValueError):
        manning_velocity_m_s(1.0, -0.001)


def test_manning_froude_critical():
    h = 1.0
    v_crit = math.sqrt(9.81 * h)
    assert froude_number(v_crit, h) == pytest.approx(1.0, abs=0.5 * 10 ** -(9), rel=0)


def test_manning_shear_and_ustar_consistent():
    tau = bed_shear_pa(1.0, 0.01)
    assert tau == pytest.approx(1000.0 * 9.81 * 1.0 * 0.01, abs=0.5 * 10 ** -(7), rel=0)
    assert shear_velocity_m_s(1.0, 0.01) == pytest.approx(math.sqrt(9.81 * 1.0 * 0.01), abs=0.5 * 10 ** -(7), rel=0)


def test_manning_fischer_positive_and_guarded():
    d = fischer_dispersion_m2_s(1.0, 20.0, 0.5, 0.1)
    assert d == pytest.approx(0.011 * 1.0 * 400.0 / (0.5 * 0.1), abs=0.5 * 10 ** -(7), rel=0)
    with pytest.raises(ValueError):
        fischer_dispersion_m2_s(1.0, 20.0, 0.5, 0.0)


def test_manning_travel_time():
    assert travel_time_s(100.0, 2.0) == pytest.approx(50.0, abs=0.5 * 10 ** -(7), rel=0)
    with pytest.raises(ValueError):
        travel_time_s(100.0, 0.0)


def test_manning_slope_from_drop():
    assert slope_from_drop(2.0, 1000.0) == pytest.approx(0.002, abs=0.5 * 10 ** -(7), rel=0)



def test_cell_hydraulics_positive_grade_full_diagnostics():
    h = cell_hydraulics(20.0, 10.0, 1.0, 5.0, 0.002)
    assert h['area_rect_m2'] > h['area_trap_m2']
    assert h['rectangular_bias_pct'] > 0.0
    assert h['velocity_continuity_m_s'] == pytest.approx(5.0 / h['area_trap_m2'], abs=0.5 * 10 ** -(7), rel=0)
    assert h['velocity_manning_m_s'] is not None
    assert h['fischer_dispersion_m2_s'] is not None
    assert h['travel_time_s'] is not None
    assert 'bank_slope_zh' in h['provenance']
    assert h['provenance']['manning_n'] == 'authored_illustrative_not_calibrated'


def test_cell_hydraulics_flat_grade_leaves_manning_undefined():
    for slope in (None, 0.0, -0.001):
        h = cell_hydraulics(20.0, 10.0, 1.0, 5.0, slope)
        assert h['velocity_manning_m_s'] is None
        assert h['fischer_dispersion_m2_s'] is None
        assert h['manning_consistency_ratio'] is None
        assert 'flat_or_adverse_grade_manning_undefined' in h['warnings']
        # Continuity diagnostics still defined.
        assert h['velocity_continuity_m_s'] > 0.0
        assert h['travel_time_s'] is not None



def test_scoring_rmse_bias_handcalc():
    s = score_paired_series([1.0, 2.0, 3.0], [1.0, 2.0, 4.0])
    assert s['bias'] == pytest.approx(-1.0 / 3.0, abs=0.5 * 10 ** -(7), rel=0)
    assert s['rmse'] == pytest.approx(math.sqrt(1.0 / 3.0), abs=0.5 * 10 ** -(7), rel=0)
    assert s['mae'] == pytest.approx(1.0 / 3.0, abs=0.5 * 10 ** -(7), rel=0)
    assert s['max_abs'] == pytest.approx(1.0, abs=0.5 * 10 ** -(7), rel=0)
    assert s['n'] == 3.0


def test_scoring_rejections():
    with pytest.raises(ValueError):
        score_paired_series([], [])
    with pytest.raises(ValueError):
        score_paired_series([1.0], [1.0, 2.0])
    with pytest.raises(ValueError):
        score_paired_series([float("nan")], [1.0])


def test_scoring_thermal_inventory():
    inv = thermal_inventory([
        {"id": "a", "flow_m3_s": 1.0, "temperature_c": 60.0,
         "status": "measured"},
        {"id": "b", "flow_m3_s": 3.0, "temperature_c": 20.0,
         "status": "authored"},
    ])
    assert inv['total_thermal_flow_m3_s'] == pytest.approx(4.0, abs=0.5 * 10 ** -(7), rel=0)
    assert inv['flow_weighted_entry_c'] == pytest.approx(30.0, abs=0.5 * 10 ** -(7), rel=0)
    assert inv['n_sources'] == 2


def test_scoring_thermal_inventory_excludes_scheduled_temps():
    # Pulse sources use Series dicts; single-value means exclude scheduled interventions and list them.
    inv = thermal_inventory([
        {"id": "a", "flow_m3_s": 1.0, "temperature_c": 60.0,
         "status": "measured"},
        {"id": "pulse", "flow_m3_s": 0.5,
         "temperature_c": {"times_s": [0.0, 1.0], "values": [60.0, 80.0]},
         "status": "synthetic_intervention"},
    ])
    assert inv['n_scheduled_sources'] == 1
    assert inv['total_thermal_flow_m3_s'] == pytest.approx(1.5, abs=0.5 * 10 ** -(7), rel=0)
    assert inv['flow_weighted_entry_c'] == pytest.approx(60.0, abs=0.5 * 10 ** -(7), rel=0)
    assert (inv['sources'][1]['scheduled'])
    assert inv['sources'][1]['temperature_c'] is None



def _sloped_world():
    # Steady 2 m drop over 100 m: slope 0.02 everywhere.
    return {
        "georeference": {"note": "test"},
        "rivers": [{
            "id": "seg_a",
            "name": "FIREHOLE RIVER",
            "width": 10.0,
            "endpoint_node_ids": ["n0", "n1"],
            "points": [[0, 2, 100], [0, 0, 0]],
        }],
    }, {
        "boundary_m3s": 5.0,
        "boundary_c": 15.0,
        "clock_hour": 12.0,
        "weather": {},
        "river_reaches": [],
    }


def test_mapped_hydraulics_diagnostics_present_volumes_unchanged():
    world, ecosystem = _sloped_world()
    doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=120.0,
                              maximum_cell_m=25.0)
    assert 'hydraulics_summary' in doc
    assert 'thermal_inventory' in doc['hydraulics_summary']
    for record in doc["cells"]:
        hydro = record["hydraulics"]
        # Solver volume still rectangular.
        assert record['volume_m3'] == pytest.approx(record['length_m'] * record['width_m'] * record['depth_m'], abs=0.5 * 10 ** -(7), rel=0)
        assert hydro['rectangular_bias_pct'] > 0.0
        assert hydro['slope'] == pytest.approx(0.02, abs=0.5 * 10 ** -(9), rel=0)
        assert hydro['velocity_manning_m_s'] is not None
        assert hydro['travel_time_s'] is not None
    total = doc["hydraulics_summary"]["total_travel_time_s"]
    parts = sum(r["hydraulics"]["travel_time_s"] for r in doc["cells"])
    assert total == pytest.approx(parts, abs=0.5 * 10 ** -(7), rel=0)
    assert (doc['numerical_checks']['passed'])


def test_mapped_hydraulics_flat_world_warns_without_failing():
    world = {
        "georeference": {"note": "test"},
        "rivers": [{
            "id": "seg_a",
            "name": "FIREHOLE RIVER",
            "width": 10.0,
            "endpoint_node_ids": ["n0", "n1"],
            "points": [[0, 0, 100], [0, 0, 0]],
        }],
    }
    _, ecosystem = _sloped_world()
    doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                              maximum_cell_m=200.0)
    for record in doc["cells"]:
        assert 'flat_or_adverse_grade_manning_undefined' in record['hydraulics']['warnings']
        assert record['hydraulics']['velocity_manning_m_s'] is None
    assert (doc['numerical_checks']['passed'])



def test_skill_perfect_scores():
    series = [10.0 + 0.5 * i for i in range(20)]
    skill = skill_scores(series, series)
    assert skill['nse'] == pytest.approx(1.0, abs=0.5 * 10 ** -(7), rel=0)
    assert skill['kge'] == pytest.approx(1.0, abs=0.5 * 10 ** -(7), rel=0)
    assert skill['correlation'] == pytest.approx(1.0, abs=0.5 * 10 ** -(7), rel=0)


def test_skill_mean_model_scores_zero_nse():
    observed = [10.0 + 0.5 * i for i in range(20)]
    mean = sum(observed) / len(observed)
    skill = skill_scores([mean] * 20, observed)
    assert skill['nse'] == pytest.approx(0.0, abs=0.5 * 10 ** -(7), rel=0)
    assert skill['kge'] is None
    assert (skill['constant_modeled'])


def test_skill_kge_degrades_with_bias():
    observed = [10.0 + 0.5 * i for i in range(20)]
    biased = [v + 2.0 for v in observed]
    assert skill_scores(biased, observed)['kge'] < skill_scores(observed, observed)['kge']


def test_skill_skill_rejects_degenerate():
    with pytest.raises(ValueError):
        skill_scores([1.0] * 10, [1.0] * 10)
    with pytest.raises(ValueError):
        skill_scores([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        skill_scores([], [])



def test_residual_perfect_fit_flag():
    series = [10.0 + 0.1 * i for i in range(15)]
    diag = residual_diagnostics(series, series)
    assert (diag['perfect_fit'])
    assert diag['max_qq_gap'] == 0.0


def test_residual_autocorr_recovers_ar1():
    import random
    rng = random.Random(20261010)
    resid = [0.0]
    for _ in range(400):
        resid.append(0.7 * resid[-1] + rng.gauss(0.0, 1.0))
    observed = [10.0] * 401
    modeled = [o + r for o, r in zip(observed, resid)]
    diag = residual_diagnostics(modeled, observed)
    assert diag['autocorr'][1] == pytest.approx(0.7, abs=0.1, rel=0)
    assert diag['autocorr'][1] > diag['autocorr'][5]


def test_residual_qq_small_gap_on_gaussian():
    import random
    rng = random.Random(7)
    noise = [rng.gauss(0.0, 2.0) for _ in range(500)]
    observed = [15.0] * 500
    modeled = [o + e for o, e in zip(observed, noise)]
    diag = residual_diagnostics(modeled, observed)
    assert diag['max_qq_gap'] < 0.3


def test_residual_residuals_reject_bad():
    with pytest.raises(ValueError):
        residual_diagnostics([1.0], [1.0])
    with pytest.raises(ValueError):
        residual_diagnostics([1.0, 2.0], [1.0])
    with pytest.raises(ValueError):
        residual_diagnostics([1.0, 2.0, 3.0], [1.0, 2.0, 3.0],
                             max_lag=3)



