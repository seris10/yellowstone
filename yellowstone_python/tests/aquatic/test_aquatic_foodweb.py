"""Tests for the aquatic vertical slice (synthetic, offline)."""
from __future__ import annotations

import pytest

from yellowstone_python.aquatic.aquatic_foodweb import TRIBUTARY_CANDIDATES, TRIBUTARY_FOOD_SCALE_DEFAULT, append_tributary_cells, build_tributary_cell, compare_runs, run_foodweb, shear_to_disturbance, thermal_landscape, unwrap_replay
from yellowstone_python.aquatic.fish import THERMAL_SPECIES, thermal_performance
from yellowstone_python.insects_birds import (
    INSECT_GROUPS,
    develop_benthic,
    trout_diet_at_temp,
)


def fake_replay(temps_by_frame, n_cells=5):
    cells = [{
        "id": f"cell_{i:03d}", "river_id": "test_river",
        "center_s_m": i * 100.0, "start_s_m": i * 100.0,
        "end_s_m": (i + 1) * 100.0,
        "width_m": 20.0, "depth_m": 0.5,
        "representative_velocity_m_s": 0.5,
        "volume_m3": 100.0 * 20.0 * 0.5,
    } for i in range(n_cells)]
    frames = [{"t_s": k * 60.0, "temperature_c": list(temps)}
              for k, temps in enumerate(temps_by_frame)]
    return {"cells": cells, "frames": frames}


def test_performance_anchor_brown_anchors():
    assert thermal_performance(14.0, 'brown_trout')['feeding'] == 1.0
    assert thermal_performance(20.5, 'brown_trout')['feeding'] == 0.0
    assert thermal_performance(21.0, 'brown_trout')['refuge_drive'] == 0.0
    assert thermal_performance(24.5, 'brown_trout')['refuge_drive'] == 1.0
    assert thermal_performance(27.0, 'brown_trout')['lethal_flag'] == 1
    assert thermal_performance(20.0, 'brown_trout')['lethal_flag'] == 0


def test_performance_anchor_rainbow_more_tolerant_than_brown():
    brown = thermal_performance(20.0, "brown_trout")["feeding"]
    rainbow = thermal_performance(20.0, "rainbow_trout")["feeding"]
    assert brown == 0.0
    assert rainbow > 0.0
    assert thermal_performance(16.0, 'rainbow_trout')['feeding'] == 1.0


def test_performance_anchor_species_table_carries_provenance():
    for species, spec in THERMAL_SPECIES.items():
        assert (spec['sources'])
        assert 'transferred' in spec['status']


def test_performance_anchor_unknown_species_rejected():
    with pytest.raises(ValueError):
        thermal_performance(15.0, "cutthroat_trout")


def test_performance_anchor_hot_water_never_ties_at_zero_weight():
    # Regression: above feed_zero, feeding saturates at 0; stress keeps the coolest cell on top at any weight.
    from yellowstone_python.aquatic.fish import suitability
    for weight in (0.0, 0.6, 2.0):
        scored = sorted((
            suitability(0.5, 0.6, t, 0.5, 0.5, species="brown_trout",
                        refuge_weight=weight), t)
            for t in (23.0, 24.5, 26.0))
        assert scored[-1][1] == 23.0



def test_insect_group_groups_carry_provenance():
    for group, params in INSECT_GROUPS.items():
        assert (params['sources'])
        assert 'transferred' in params['status']


def test_insect_group_group_table_ordering():
    # Table claim: dipterans start later, develop faster, tolerate more heat than EPT fauna.
    ept, dipt = INSECT_GROUPS["ept"], INSECT_GROUPS["dipteran"]
    assert dipt['tbase_c'] > ept['tbase_c']
    assert dipt['rate_per_dd'] > ept['rate_per_dd']
    assert dipt['t_cutoff_c'] > ept['t_cutoff_c']


def test_insect_group_group_ordering_and_cutoff():
    e = INSECT_GROUPS["ept"]
    d = INSECT_GROUPS["dipteran"]
    _, warm_ept, _ = develop_benthic(0.5, 18.0, 86400.0, tbase=e["tbase_c"],
                                  rate=e["rate_per_dd"],
                                  t_cutoff=e["t_cutoff_c"])
    _, warm_dipt, _ = develop_benthic(0.5, 18.0, 86400.0, tbase=d["tbase_c"],
                                   rate=d["rate_per_dd"],
                                   t_cutoff=d["t_cutoff_c"])
    assert warm_dipt > warm_ept
    _, cold_ept, _ = develop_benthic(0.5, 6.0, 86400.0, tbase=e["tbase_c"],
                                  rate=e["rate_per_dd"],
                                  t_cutoff=e["t_cutoff_c"])
    _, cold_dipt, _ = develop_benthic(0.5, 6.0, 86400.0, tbase=d["tbase_c"],
                                   rate=d["rate_per_dd"],
                                   t_cutoff=d["t_cutoff_c"])
    assert cold_ept > cold_dipt
    _, stupor, _ = develop_benthic(0.5, 24.0, 86400.0, tbase=e["tbase_c"],
                                rate=e["rate_per_dd"],
                                t_cutoff=e["t_cutoff_c"])
    assert stupor == 0.0
    # Path with no cutoff still emerges at 24 C.
    _, legacy, _ = develop_benthic(0.5, 24.0, 86400.0)
    assert legacy > 0.0


def test_insect_group_diet_shifts_to_emergers_when_warm():
    cold = trout_diet_at_temp(10.0)
    warm = trout_diet_at_temp(25.0)
    assert cold['benthic'] > cold['emergent']
    assert warm['emergent'] > warm['benthic']
    assert cold['benthic'] + cold['emergent'] == pytest.approx(1.0, abs=0.5 * 10 ** -(7), rel=0)
    assert warm['benthic'] + warm['emergent'] == pytest.approx(1.0, abs=0.5 * 10 ** -(7), rel=0)



def test_foodweb_mechanism_refuge_seeks_cool_water():
    doc = fake_replay([[14.0, 16.0, 18.0, 22.0, 26.0]] * 3)
    out = run_foodweb(thermal_landscape(doc), days=4.0)
    assert out['trout']['temperature_c'] <= 18.0
    assert out['trout']['refuge_drive'] == 0.0
    assert out['status'] == 'illustrative_not_calibrated'


def test_foodweb_mechanism_hot_landscape_drives_refuge_and_flags():
    doc = fake_replay([[25.5, 26.0, 26.5, 27.5, 28.0]] * 3)
    out = run_foodweb(thermal_landscape(doc), days=2.0)
    assert out['trout']['refuge_drive'] == 1.0
    assert 'lethal' in str(out['trout']['thermal_performance'])


def test_foodweb_mechanism_ledger_and_stocks_sane():
    doc = fake_replay([[16.0] * 5] * 3)
    out = run_foodweb(thermal_landscape(doc), days=7.0)
    totals = out["prey_totals"]
    assert totals['emergence'] > 0.0
    assert totals['regrowth'] >= 0.0
    assert totals['trout_eaten'] >= 0.0
    assert totals['dipper_eaten'] >= 0.0
    for row in out["per_cell"]:
        assert row['ept'] >= 0.0
        assert row['dipt'] >= 0.0
        assert row['ne'] >= 0.0


def test_foodweb_mechanism_warming_moves_refuge_upstream():
    # Control refuge sits mid-reach; a downstream heat plume moves the refuge upstream of it.
    control = fake_replay(
        [[16.0, 15.0, 14.0, 15.0, 16.0]] * 3)
    warm = fake_replay(
        [[16.0, 15.0, 16.0, 24.0, 27.0]] * 3)
    cmp = compare_runs(control, warm, days=4.0)
    assert cmp['refuge_shift_m'] < 0.0
    assert cmp['pulse']['temperature_c'] <= 16.0
    assert cmp['pulse']['refuge_drive'] == 0.0


def test_foodweb_mechanism_window_and_wrapper_handling():
    doc = fake_replay([[15.0] * 5] * 5)
    full = thermal_landscape(doc)
    part = thermal_landscape(doc, t_min_s=60.0, t_max_s=120.0)
    assert len(full) == len(part)
    wrapped = thermal_landscape({"replay": doc})
    assert len(wrapped) == 5
    with pytest.raises(ValueError):
        thermal_landscape(doc, t_min_s=99999.0)
    with pytest.raises(ValueError):
        unwrap_replay({"nope": True})
    with pytest.raises(ValueError):
        run_foodweb([])



def test_shear_disturbance_ramp_shape_and_nulls():
    assert shear_to_disturbance(None, 20.0) == 0.0
    assert shear_to_disturbance(15.0, None) == 0.0
    assert shear_to_disturbance(15.0, 20.0) == 0.0
    assert shear_to_disturbance(20.0, 20.0) == 0.0
    assert shear_to_disturbance(30.0, 20.0) == pytest.approx(0.5, abs=0.5 * 10 ** -(7), rel=0)
    assert shear_to_disturbance(40.0, 20.0) == 1.0
    assert shear_to_disturbance(400.0, 20.0) == 1.0
    for bad in ((-1.0, 20.0), (15.0, 0.0), (15.0, -5.0),
                (float("nan"), 20.0), (15.0, float("inf"))):
        with pytest.raises(ValueError):
            shear_to_disturbance(*bad)


def test_shear_disturbance_default_threshold_leaves_disturbance_free_behavior():
    doc = fake_replay([[15.0] * 5] * 8)
    land = thermal_landscape(doc)
    for cell in land:
        cell["shear_pa"] = 15.08  # mapped reach-uniform value
    default = run_foodweb(land)
    off = run_foodweb(land, shear_disturb_pa=None)
    legacy = run_foodweb(
        [{k: v for k, v in cell.items() if k != "shear_pa"}
         for cell in land])
    assert default['prey_totals'] == off['prey_totals']
    assert default['prey_totals'] == legacy['prey_totals']
    assert default['trout']['cell_id'] == legacy['trout']['cell_id']


def test_shear_disturbance_lower_threshold_suppresses_emergence():
    doc = fake_replay([[15.0] * 5] * 8)
    land = thermal_landscape(doc)
    for cell in land:
        cell["shear_pa"] = 15.08
    calm = run_foodweb(land, shear_disturb_pa=20.0)
    rough = run_foodweb(land, shear_disturb_pa=10.0)
    assert rough['prey_totals']['emergence'] < calm['prey_totals']['emergence']
    assert 'shear_coupling' in rough['provenance']


def test_shear_disturbance_shear_null_cells_run_clean():
    doc = fake_replay([[15.0] * 5] * 8)
    land = thermal_landscape(doc)
    for cell in land:
        cell["shear_pa"] = None  # Manning-undefined cells
    result = run_foodweb(land, shear_disturb_pa=10.0)
    assert result['prey_totals']['emergence'] > 0.0



def test_tributary_refuge_candidates_below_refuge_threshold_with_provenance():
    assert len(TRIBUTARY_CANDIDATES) == 2
    seen = set()
    for spec in TRIBUTARY_CANDIDATES:
        assert spec['temperature_c'] < 24.0
        assert spec['confluence_s_m'] >= 0.0
        assert 'authored' in spec['temperature_provenance']
        assert 'map_measured' in spec['confluence_provenance']
        assert spec['cell_id'] not in seen
        seen.add(spec["cell_id"])


def test_tributary_refuge_append_returns_new_list_with_provenance():
    doc = fake_replay([[16.0] * 5] * 3)
    land = thermal_landscape(doc)
    out = append_tributary_cells(land)
    assert len(out) == len(land) + 2
    assert len(land) == 5  # input not mutated
    for cell in out[-2:]:
        assert cell['river_id'] == 'tributary'
        assert cell['shear_pa'] is None
        assert cell['food_scale'] == TRIBUTARY_FOOD_SCALE_DEFAULT
        assert 'tributary_provenance' in cell


def test_tributary_refuge_builder_rejects_bad_scales_and_temps():
    spec = TRIBUTARY_CANDIDATES[0]
    for bad in (-0.1, float("nan"), float("inf"), None):
        with pytest.raises(ValueError):
            build_tributary_cell(spec, food_scale=bad)
    with pytest.raises(ValueError):
        build_tributary_cell(spec, temperature_c=float("nan"))
    # food_scale 0 is allowed (starvation-pocket edge case).
    zero = build_tributary_cell(spec, food_scale=0.0)
    assert zero['food_scale'] == 0.0


def test_tributary_refuge_food_scale_default_reproduces_unscaled_behavior():
    doc = fake_replay([[15.0] * 5] * 8)
    land = thermal_landscape(doc)
    plain = run_foodweb(land)
    scaled = run_foodweb(
        [{**cell, "food_scale": 1.0} for cell in land])
    assert scaled['prey_totals'] == plain['prey_totals']
    assert scaled['trout']['cell_id'] == plain['trout']['cell_id']


def test_tributary_refuge_food_scale_downranks_but_cold_still_wins_when_hot():
    # Hot mainstem (>24 C, drive firing) plus one cold pocket at 1/20 food; pocket wins on thermal + refuge terms.
    doc = fake_replay([[26.0, 26.5, 27.0, 27.5, 28.0]] * 3)
    land = thermal_landscape(doc)
    pocket = build_tributary_cell(
        {**TRIBUTARY_CANDIDATES[0], "temperature_c": 11.0},
        food_scale=TRIBUTARY_FOOD_SCALE_DEFAULT)
    out = run_foodweb(land + [pocket], days=4.0)
    assert out['trout']['cell_id'] == pocket['id']
    assert out['trout']['refuge_drive'] == 0.0


def test_tributary_refuge_starved_pocket_loses_to_cool_mainstem():
    # food_scale 0 pocket vs 16 C mainstem; model prefers mainstem food.
    doc = fake_replay([[16.0] * 5] * 3)
    land = thermal_landscape(doc)
    pocket = build_tributary_cell(
        {**TRIBUTARY_CANDIDATES[0], "temperature_c": 11.0},
        food_scale=0.0)
    out = run_foodweb(land + [pocket], days=4.0)
    assert not (out['trout']['cell_id'].startswith('trib_'))


def test_tributary_refuge_compare_runs_appends_extra_cells_to_both():
    control = fake_replay([[16.0] * 5] * 3)
    hot = fake_replay([[27.0] * 5] * 3)
    extra = [build_tributary_cell(TRIBUTARY_CANDIDATES[0])]
    cmp = compare_runs(control, hot, extra_cells=extra, days=4.0)
    assert cmp['pulse']['cell_id'] == extra[0]['id']
    assert 'trib_' in cmp['landscape_window']
    # Without the pocket the hot run holds mainstem water.
    cmp0 = compare_runs(control, hot, days=4.0)
    assert not (cmp0['pulse']['cell_id'].startswith('trib_'))



