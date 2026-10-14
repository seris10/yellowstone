"""River invertebrate taxa with cited thermal, DO and feeding-group traits."""
from __future__ import annotations

import pytest

from yellowstone_python.aquatic.aquatic_foodweb import INVERT_TAXA, _taxon_do_survival, run_taxon_foodweb, taxon_step
from yellowstone_python.insects_birds import emergence_total_from_taxa


def test_registry_covers_the_named_taxa_with_sources():
    """Require cited thermal, oxygen, and feeding traits for each named taxon."""
    expected = {"mayflies", "caddisflies", "stoneflies", "midges",
                "nz_mudsnail"}
    assert set(INVERT_TAXA) == expected
    for taxon_id, entry in INVERT_TAXA.items():
        assert entry["sources"], f"{taxon_id} needs at least one source"
        assert entry["feeding_group"], f"{taxon_id} needs a feeding_group"
        assert entry["do_sensitive_min_mg_l"] > entry["do_lethal_min_mg_l"]
        if entry.get("emerges", True):
            assert entry["rate_per_dd"] > 0.0
        else:
            assert taxon_id == "nz_mudsnail"


def test_mudsnail_marked_as_non_emerging_competing_grazer():
    """NZ mudsnail does not emerge and its feeding group marks it as a grazer."""
    entry = INVERT_TAXA["nz_mudsnail"]
    assert entry["emerges"] is False
    assert "grazer" in entry["feeding_group"]
    assert any("Potamopyrgus" in src for src in entry["sources"])
    assert any("new_zealand_mudsnail" in src for src in entry["sources"])


def test_do_survival_is_monotonic_in_oxygen():
    """Increase taxon survival from zero to one between its oxygen thresholds."""
    mayfly = INVERT_TAXA["mayflies"]
    assert _taxon_do_survival(mayfly, None) == pytest.approx(1.0)
    assert _taxon_do_survival(mayfly,
                              mayfly["do_lethal_min_mg_l"] - 0.1) == 0.0
    assert _taxon_do_survival(mayfly,
                              mayfly["do_sensitive_min_mg_l"] + 1.0) == 1.0
    low = _taxon_do_survival(mayfly, 3.5)
    high = _taxon_do_survival(mayfly, 4.5)
    assert 0.0 < low < high < 1.0


def test_emergence_from_taxa_sums_to_total():
    """emergence_total_from_taxa returns the sum of per-taxon emergence."""
    taxa_emergence = {"mayflies": 0.02, "caddisflies": 0.015,
                      "stoneflies": 0.005, "midges": 0.03}
    total = emergence_total_from_taxa(taxa_emergence)
    assert total == pytest.approx(0.07)


def test_taxon_step_emergence_matches_sum_check():
    """taxon_step returns per-taxon emergence that sums to emergent_compartment_input."""
    state = {t: 0.6 for t in INVERT_TAXA}
    report = taxon_step(state, water_c=12.0,
                        periphyton_biomass_mg_c_m2=200.0,
                        dt_s=86400.0)
    summed = sum(report["emergence_by_taxon"].values())
    assert report["emergent_compartment_input"] == pytest.approx(summed)
    # Mudsnail does not contribute to emergence.
    assert "nz_mudsnail" not in report["emergence_by_taxon"]


def test_removing_periphyton_starves_grazer_taxa_over_declared_time():
    """Reduce grazer biomass when periphyton food is absent over the same interval."""
    landscape = [{"id": "cell_0", "temperature_c": 10.0, "s_m": 0.0,
                  "velocity_m_s": 0.3, "depth_m": 0.5, "width_m": 10.0}]
    rich = run_taxon_foodweb(
        landscape,
        periphyton_biomass_mg_c_m2_by_cell={"cell_0": 500.0},
        days=14.0, dt_days=1.0,
        periphyton_shortfall_decay_per_day=0.2)
    starved = run_taxon_foodweb(
        landscape,
        periphyton_biomass_mg_c_m2_by_cell={"cell_0": 0.0},
        days=14.0, dt_days=1.0,
        periphyton_shortfall_decay_per_day=0.2)
    for taxon_id, entry in INVERT_TAXA.items():
        if "grazer" in entry["feeding_group"] or "collector" in entry[
                "feeding_group"]:
            rich_val = rich["cell_states"]["cell_0"][taxon_id]
            starved_val = starved["cell_states"]["cell_0"][taxon_id]
            assert starved_val < rich_val


def test_mudsnail_raises_competition_pressure_on_native_grazers():
    """Doubling the mudsnail biomass raises per-time grazing of native scraper taxa in taxon_step."""
    base_state = {t: 0.5 for t in INVERT_TAXA}
    double_state = dict(base_state, nz_mudsnail=1.0)
    base = taxon_step(base_state, water_c=12.0,
                      periphyton_biomass_mg_c_m2=200.0, dt_s=3600.0)
    doubled = taxon_step(double_state, water_c=12.0,
                         periphyton_biomass_mg_c_m2=200.0, dt_s=3600.0)
    for taxon_id in ("mayflies", "caddisflies"):
        base_graze = base["taxa"][taxon_id]["grazing_mg_c_m2_s"]
        doubled_graze = doubled["taxa"][taxon_id]["grazing_mg_c_m2_s"]
        assert doubled_graze > base_graze


def test_do_response_lowers_biomass():
    """Low dissolved oxygen below the lethal anchor drives taxon biomass to zero over one day."""
    state = {t: 0.5 for t in INVERT_TAXA}
    report = taxon_step(state, water_c=12.0,
                        periphyton_biomass_mg_c_m2=200.0,
                        dt_s=86400.0, do_mg_l=1.0)
    for taxon_id in ("mayflies", "stoneflies"):
        taxon_entry = INVERT_TAXA[taxon_id]
        if 1.0 <= taxon_entry["do_lethal_min_mg_l"]:
            assert report["taxa"][taxon_id]["nb"] == pytest.approx(0.0, abs=1e-9)


def test_emergence_total_rejects_negative_amount():
    """Negative emergence amounts are refused."""
    with pytest.raises(ValueError):
        emergence_total_from_taxa({"mayflies": -0.01})
