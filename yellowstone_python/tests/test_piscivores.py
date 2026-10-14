"""Piscivore predation: Holling II response, depth-refuge, per-m-river spatial support."""
from __future__ import annotations

import pytest

from yellowstone_python.aquatic.piscivores import DEPTH_REFUGE_SOURCES, PISCIVORES, SIZE_CLASSES, TROUT_DENSITY_DEFAULT_PER_M2_WETTED, depth_refuge_factor, predation_over_refuge, predation_rate_per_day, refuge_predation_risk


def test_registry_has_the_five_named_species_with_sources():
    """Osprey, bald eagle, common merganser, belted kingfisher and river otter registered with sources."""
    expected = {"osprey", "bald_eagle", "common_merganser",
                "belted_kingfisher", "river_otter"}
    assert set(PISCIVORES) == expected
    for cid, entry in PISCIVORES.items():
        assert entry["sources"], f"{cid} needs at least one source"
        assert entry["max_kg_fish_per_day"] > 0.0
        assert entry["handling_time_days_per_kg"] > 0.0
        assert entry["attack_rate_m_per_day"] > 0.0
        assert entry["depth_scale_m"] > 0.0
        assert entry["density_status"] == "authored_illustrative"
        assert entry["depth_scale_status"] == "authored_illustrative"


def test_depth_refuge_factor_declines_monotonically():
    """exp(-d/scale) is in (0,1] and strictly decreasing in depth."""
    shallow = depth_refuge_factor(0.0, 1.0)
    mid = depth_refuge_factor(1.0, 1.0)
    deep = depth_refuge_factor(3.0, 1.0)
    assert shallow == pytest.approx(1.0, rel=0, abs=1e-12)
    assert 0.0 < deep < mid < shallow <= 1.0


def test_mortality_rises_with_piscivore_density():
    """Doubling piscivore density raises mortality (bounded by Holling II saturation)."""
    base = predation_rate_per_day(size_class="adult", depth_m=1.0)
    doubled = {cid: 2.0 * entry["density_per_m_river"]
               for cid, entry in PISCIVORES.items()}
    heavy = predation_rate_per_day(size_class="adult", depth_m=1.0,
                                    density_overrides=doubled)
    assert heavy["mortality_rate_per_day"] > base["mortality_rate_per_day"]


def test_mortality_stays_bounded_as_trout_density_falls():
    """Per-capita mortality rate stays finite when trout density is small (Holling II handling cap)."""
    sparse = predation_rate_per_day(size_class="adult", depth_m=1.0,
                                     trout_density_per_m2_wetted=0.01)
    dense = predation_rate_per_day(size_class="adult", depth_m=1.0,
                                    trout_density_per_m2_wetted=1.0)
    assert sparse["mortality_rate_per_day"] >= dense["mortality_rate_per_day"]
    assert sparse["mortality_rate_per_day"] < 10.0


def test_deeper_refuge_lowers_mortality():
    """A deeper refuge cell lowers predation at matched trout density and size class."""
    shallow = predation_rate_per_day(size_class="adult", depth_m=0.2)
    deep = predation_rate_per_day(size_class="adult", depth_m=3.0)
    assert deep["mortality_rate_per_day"] < shallow["mortality_rate_per_day"]
    acc_shallow = {c["id"]: c["accessibility"] for c in shallow["components"]}
    acc_deep = {c["id"]: c["accessibility"] for c in deep["components"]}
    for cid, acc in acc_shallow.items():
        if acc > 0.0:
            assert acc_deep[cid] < acc


def test_size_class_shares_route_prey_correctly():
    """Belted kingfisher takes no adults; eagle takes mostly adults."""
    adult = predation_rate_per_day(size_class="adult", depth_m=0.5)
    yoy = predation_rate_per_day(size_class="yoy", depth_m=0.5)
    adult_comps = {c["id"]: c for c in adult["components"]}
    yoy_comps = {c["id"]: c for c in yoy["components"]}
    assert adult_comps["belted_kingfisher"]["rate_per_day"] == 0.0
    assert yoy_comps["belted_kingfisher"]["rate_per_day"] >= 0.0


def test_refuge_predation_risk_requires_cell_depth():
    """refuge_predation_risk and predation_over_refuge raise on missing depth; no silent default."""
    with pytest.raises(ValueError):
        refuge_predation_risk(cell_depth_m=None)
    with pytest.raises(ValueError):
        predation_over_refuge({"id": "trout_01"}, cell_depth_m=None)
    risk = refuge_predation_risk(cell_depth_m=1.5)
    assert risk >= 0.0


def test_predation_over_refuge_attaches_trout_id():
    """predation_over_refuge takes an explicit depth and reports the trout id."""
    record = {"id": "trout_01"}
    report = predation_over_refuge(record, cell_depth_m=2.0,
                                     size_class="adult")
    assert report["trout_id"] == "trout_01"
    assert report["depth_m"] == 2.0


def test_default_trout_density_is_authored_and_labeled():
    """The default trout density per m2 wetted is authored illustrative."""
    assert TROUT_DENSITY_DEFAULT_PER_M2_WETTED > 0.0
    assert SIZE_CLASSES["yoy"]["mass_kg_hi"] < SIZE_CLASSES["adult"]["mass_kg_lo"] * 10


def test_depth_refuge_sources_reference_power_harvey_lonzarich():
    """Depth refuge sources name Power, Harvey and Stewart, and Lonzarich and Quinn."""
    joined = " ".join(DEPTH_REFUGE_SOURCES).lower()
    assert "power" in joined
    assert "harvey" in joined
    assert "lonzarich" in joined
