"""Tests for grazer nutrient return and trampling disturbance in patch_step."""
import math

import pytest

from yellowstone_python.land.vegetation import TRAMPLING_RECOVERY_TAU_S, patch_step


def _base_patch(pid="p"):
    return {"id": pid, "biomass": 0.5, "capacity": 1.0, "moisture": 0.6,
            "growth_per_hour": 0.05}


def test_patch_productivity_rises_with_nutrient_return():
    hour = 12.0
    dt_s = 3600.0
    # Equal grazing demand on both runs; one receives dung nitrogen, the other does not.
    grazers = {"g1": {"patch_id": "p", "active": True,
                      "rate_per_second": 1.0e-07}}
    plain, _ = patch_step([_base_patch()], hour, dt_s, grazers=grazers)
    enriched, led = patch_step(
        [_base_patch()], hour, dt_s, grazers=grazers,
        nutrient_return_by_patch={"p": 20.0})
    assert enriched[0]["biomass"] > plain[0]["biomass"]
    assert led["nitrogen_return_total_kg_ha"] == pytest.approx(20.0)
    assert enriched[0]["nitrogen_kg_ha"] > 0.0


def test_trampling_damage_reduces_biomass():
    hour = 12.0
    dt_s = 3600.0
    untrampled, _ = patch_step([_base_patch()], hour, dt_s)
    trampled, _ = patch_step([_base_patch()], hour, dt_s,
                             trampling_by_patch={"p": 0.3})
    assert trampled[0]["biomass"] < untrampled[0]["biomass"]
    assert trampled[0]["trampling_damage"] > 0.0


def test_trampling_decays_over_declared_time_scale():
    # Start with a lingering trampling fraction, no new disturbance.
    hour = 12.0
    patch = _base_patch()
    patch["trampling_damage"] = 0.5
    # Step by two time constants and verify the damage decays by about exp(-2).
    dt_s = 2.0 * TRAMPLING_RECOVERY_TAU_S
    out, _ = patch_step([patch], hour, dt_s)
    expected = 0.5 * math.exp(-2.0)
    assert out[0]["trampling_damage"] == pytest.approx(expected, abs=1e-3)
    # Approximate half-recovery over tau.
    patch2 = _base_patch()
    patch2["trampling_damage"] = 0.5
    out2, _ = patch_step([patch2], hour, TRAMPLING_RECOVERY_TAU_S)
    assert out2[0]["trampling_damage"] < 0.5 * math.exp(-0.5)


def test_nitrogen_stock_decays_without_new_return():
    hour = 12.0
    patch = _base_patch()
    patch["nitrogen_kg_ha"] = 10.0
    # One decay tau should drop the stock to about exp(-1) of its starting value.
    from yellowstone_python.land.vegetation import NITROGEN_DECAY_TAU_S
    out, _ = patch_step([patch], hour, NITROGEN_DECAY_TAU_S)
    assert out[0]["nitrogen_kg_ha"] == pytest.approx(10.0 * math.exp(-1.0),
                                                     abs=0.05)


def test_ledger_reports_source_citations():
    _, led = patch_step([_base_patch()], 12.0, 60.0,
                        nutrient_return_by_patch={"p": 1.0},
                        trampling_by_patch={"p": 0.05})
    assert "nutrient_source" in led and "Frank" in led["nutrient_source"]
    assert "trampling_source" in led and "Weisberg" in led["trampling_source"]


def test_sinter_crust_thins_from_trampling_in_thermal_patch():
    from yellowstone_python.land.vegetation import SINTER_DEPOSITION_MM_PER_S, SINTER_THINNING_MM_PER_UNIT
    hour = 12.0
    dt_s = 3600.0
    thermal = _base_patch("thermal_1")
    thermal["sinter_crust_mm"] = 50.0
    cold = _base_patch("meadow_1")
    cold["sinter_crust_mm"] = 50.0
    out, led = patch_step([thermal, cold], hour, dt_s,
                          trampling_by_patch={"thermal_1": 0.2,
                                              "meadow_1": 0.2},
                          thermal_patch_ids={"thermal_1"})
    by_id = {p["id"]: p for p in out}
    assert by_id["thermal_1"]["sinter_crust_mm"] < 50.0
    assert by_id["meadow_1"]["sinter_crust_mm"] == pytest.approx(50.0)
    expected_thin = SINTER_THINNING_MM_PER_UNIT * 0.2
    expected_deposit = SINTER_DEPOSITION_MM_PER_S * dt_s
    assert led["sinter_thin_total_mm"] == pytest.approx(expected_thin,
                                                         rel=1e-6)
    assert led["sinter_deposit_total_mm"] == pytest.approx(expected_deposit,
                                                            rel=1e-6)


def test_sinter_crust_recovers_from_deposition():
    hour = 12.0
    dt_s = 365.0 * 86400.0
    thermal = _base_patch("thermal_1")
    thermal["sinter_crust_mm"] = 10.0
    out, _ = patch_step([thermal], hour, dt_s,
                        thermal_patch_ids={"thermal_1"})
    assert out[0]["sinter_crust_mm"] > 10.5
