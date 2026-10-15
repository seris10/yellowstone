"""New fish species profiles: brook, mountain whitefish, Yellowstone cutthroat, Arctic grayling."""
from __future__ import annotations

import pytest

from yellowstone_python.aquatic.fish import PRESENCE_DEFAULT_ON, SCENARIO_FISH_SPECIES, THERMAL_SPECIES, species_is_default_on, thermal_performance


REGISTRY_NEW_SPECIES = {
    "brook_trout", "yellowstone_cutthroat", "arctic_grayling",
}
SCENARIO_SPECIES = {"mountain_whitefish"}


def test_all_new_species_are_registered_or_scenario():
    """Evidence-supported species and unverified scenario profiles use separate registries."""
    for species in REGISTRY_NEW_SPECIES:
        assert species in THERMAL_SPECIES
    for species in SCENARIO_SPECIES:
        assert species in SCENARIO_FISH_SPECIES
        assert species not in THERMAL_SPECIES


def test_brook_trout_growth_anchors_from_chadwick_mccormick_2017():
    """Chadwick and McCormick 2017: optimum 13-16 C, upper limit for positive growth 23.4 C."""
    spec = THERMAL_SPECIES["brook_trout"]
    assert spec["t_opt_lo_c"] == pytest.approx(13.0)
    assert spec["t_opt_hi_c"] == pytest.approx(16.0)
    assert spec["t_feed_zero_c"] == pytest.approx(23.4)
    assert spec["t_opt_lo_c_status"] == (
        "transferred_from_chadwick_mccormick_2017")
    assert spec["t_opt_hi_c_status"] == (
        "transferred_from_chadwick_mccormick_2017")
    assert spec["t_feed_zero_c_status"] == (
        "transferred_from_chadwick_mccormick_2017")
    assert any("Chadwick and McCormick 2017" in s for s in spec["sources"])
    assert any("3976-3987" in s for s in spec["sources"])
    assert any("10.1242/jeb.161224" in s for s in spec["sources"])
    perf_opt = thermal_performance(14.5, "brook_trout")
    assert perf_opt["feeding"] == pytest.approx(1.0)


def test_brook_trout_refuge_anchor_from_chadwick_nislow_mccormick_2015():
    """Chadwick Nislow and McCormick 2015 Conservation Physiology: thermal ecological limit 21.0 C."""
    spec = THERMAL_SPECIES["brook_trout"]
    assert spec["t_refuge_c"] == pytest.approx(21.0)
    assert spec["t_refuge_c_status"] == (
        "transferred_from_chadwick_nislow_mccormick_2015")
    assert any("Chadwick Nislow and McCormick 2015" in s
               for s in spec["sources"])


def test_brook_trout_uilt_authored_pending_fry_hart_walker_1946():
    """t_uilt_c is labeled authored pending a readable Fry Hart Walker (1946) fetch, with the reason."""
    spec = THERMAL_SPECIES["brook_trout"]
    assert spec["t_uilt_c_status"] == (
        "authored_pending_fry_hart_walker_1946_fetch")
    assert "Fry" in spec["t_uilt_c_reason"]
    assert "1946" in spec["t_uilt_c_reason"]
    assert any("Fry Hart and Walker (1946)" in s for s in spec["sources"])
    perf_lethal = thermal_performance(spec["t_uilt_c"] + 0.5, "brook_trout")
    assert perf_lethal["lethal_flag"] == 1


def test_mountain_whitefish_lives_in_scenario_registry():
    """Mountain whitefish thermal anchors remain unverified scenario inputs."""
    spec = SCENARIO_FISH_SPECIES["mountain_whitefish"]
    assert spec["status"] == "authored_pending_source_verification"
    assert spec["presence_default_on"] is False
    assert "authored_pending_source_verification" in spec["presence_note"]


def test_yellowstone_cutthroat_reproduces_rogers_anchors():
    """Rogers and coauthors in Canadian Journal of Fisheries and Aquatic Sciences: optimal growth 15.4."""
    spec = THERMAL_SPECIES["yellowstone_cutthroat"]
    assert spec["t_opt_lo_c"] == pytest.approx(15.4)
    assert spec["t_opt_hi_c"] == pytest.approx(18.3)
    assert spec["t_uilt_c"] == pytest.approx(24.4)
    assert spec["presence_default_on"] is False
    assert "yellowstone_cutthroat" not in PRESENCE_DEFAULT_ON
    assert species_is_default_on("yellowstone_cutthroat") is False
    assert any("Rogers" in s and "27.91" in s for s in spec["sources"])
    assert any("Presence in the modeled reach" in s and "unconfirmed" in s for s in spec["sources"])


def test_arctic_grayling_reproduces_lohr_1996_uilt():
    """Lohr et al."""
    spec = THERMAL_SPECIES["arctic_grayling"]
    assert spec["t_opt_lo_c"] == pytest.approx(8.0)
    assert spec["t_opt_hi_c"] == pytest.approx(14.0)
    assert spec["t_uilt_c"] == pytest.approx(23.0)
    assert spec["presence_default_on"] is False
    assert species_is_default_on("arctic_grayling") is False
    assert any("Lohr" in s and "933-939" in s for s in spec["sources"])


def test_brown_rainbow_and_brook_default_on():
    """Species present or stocked in the modeled reach keep their default-on status."""
    assert species_is_default_on("brown_trout") is True
    assert species_is_default_on("rainbow_trout") is True
    assert species_is_default_on("brook_trout") is True


def test_unknown_species_raises():
    """Querying an unknown species raises ValueError."""
    with pytest.raises(ValueError):
        species_is_default_on("walleye")
    with pytest.raises(ValueError):
        thermal_performance(10.0, "walleye")


def test_each_registered_profile_feeding_is_zero_at_or_above_feed_zero():
    """Thermal performance drops the feeding factor to zero at t_feed_zero_c for every registered species."""
    for species in REGISTRY_NEW_SPECIES:
        spec = THERMAL_SPECIES[species]
        perf = thermal_performance(spec["t_feed_zero_c"] + 0.5, species)
        assert perf["feeding"] == pytest.approx(0.0, abs=1e-9)


def test_each_registered_profile_marks_lethal_above_uilt():
    """lethal_flag is 1 above the upper incipient lethal temperature for every registered species."""
    for species in REGISTRY_NEW_SPECIES:
        spec = THERMAL_SPECIES[species]
        perf = thermal_performance(spec["t_uilt_c"] + 1.0, species)
        assert perf["lethal_flag"] == 1


def test_scenario_registry_sources_name_fetched_evidence_only_as_unverified():
    """Scenario profile sources state which thermal evidence remains unverified."""
    for species, spec in SCENARIO_FISH_SPECIES.items():
        assert spec["status"] == "authored_pending_source_verification"
        assert "not retrieved" in " ".join(spec["sources"]).lower() \
            or "no critical thermal" in " ".join(spec["sources"]).lower()
