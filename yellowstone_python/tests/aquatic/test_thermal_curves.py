"""Checks for fitted per-endpoint thermal curves."""
from __future__ import annotations

import math

import pytest

import yellowstone_python.aquatic.thermal_curves as tc
from yellowstone_python.aquatic.fish import THERMAL_SPECIES
from yellowstone_python.aquatic.thermal_curves import feeding, growth, refuge_drive, reproduction, survival

FITTED = (growth, feeding, survival, refuge_drive)
ALL = FITTED + (reproduction,)
NAMES = ("growth", "feeding", "survival", "refuge_drive")


def test_species_registry_matches_fish():
    """Curve species set tracks THERMAL_SPECIES."""
    assert set(tc.SPECIES) == set(THERMAL_SPECIES)


def test_brown_growth_reproduces_elliott_hurley_anchors():
    """Zeros 2.9/18.7 C, optimum 13.9 C."""
    assert abs(growth(13.9, "brown_trout")["value"] - 1.0) < 0.01
    assert growth(2.9, "brown_trout")["value"] < 0.06
    assert growth(18.7, "brown_trout")["value"] < 0.06


def test_rainbow_growth_reproduces_bear_hokanson_anchors():
    """Optima 13.1/17.2 C, zero-net 23 C."""
    assert growth(13.1, "rainbow_trout")["value"] > 0.94
    assert growth(17.2, "rainbow_trout")["value"] > 0.94
    assert growth(23.0, "rainbow_trout")["value"] < 0.06


def test_feeding_zero_anchors():
    """Brown zero 20.0 C past 19.3 C decline; rainbow zero 22.0 C."""
    assert feeding(19.3, "brown_trout")["value"] > 0.94
    assert feeding(20.0, "brown_trout")["value"] < 0.06
    assert feeding(17.0, "rainbow_trout")["value"] > 0.94
    assert feeding(22.0, "rainbow_trout")["value"] < 0.06


def test_survival_uilt_anchors():
    """Rainbow UILT 25.6 C; brown UILT range 24.4-26.5 C."""
    assert survival(20.0, "rainbow_trout")["value"] > 0.99
    assert abs(survival(25.6, "rainbow_trout")["value"] - 0.5) < 0.06
    assert abs(survival(25.45, "brown_trout")["value"] - 0.5) < 0.06
    assert survival(24.4, "brown_trout")["value"] > 0.8
    assert survival(26.5, "brown_trout")["value"] < 0.2


def test_refuge_drive_kaya_thresholds():
    """Drive rises through 24 C and saturates by 25 C."""
    for species in ("brown_trout", "rainbow_trout"):
        assert refuge_drive(22.0, species)["value"] < 0.15
        assert abs(refuge_drive(24.0, species)["value"] - 0.5) < 0.1
        assert refuge_drive(25.0, species)["value"] > 0.8


def test_brown_growth_fall_steeper_than_rise():
    """Asymmetric growth; warm-side drop exceeds cold-side drop."""
    params = growth(13.9, "brown_trout")["provenance"]["params"]
    assert params["sigma_fall_c"] < params["sigma_rise_c"]
    cold_drop = 1.0 - growth(11.9, "brown_trout")["value"]
    warm_drop = 1.0 - growth(15.9, "brown_trout")["value"]
    assert warm_drop > cold_drop


@pytest.mark.parametrize("fn", FITTED)
@pytest.mark.parametrize("species", ["brown_trout", "rainbow_trout"])
def test_curves_finite_and_bounded(fn, species):
    """Values finite in [0, 1] across -5 to 30 C."""
    for t in range(-5, 31):
        v = fn(float(t), species)["value"]
        assert math.isfinite(v) and 0.0 <= v <= 1.0


def test_monotonic_limbs():
    """Check growth, survival, and refuge trends past the thermal optimum."""
    warm = [growth(t, "brown_trout")["value"]
            for t in [13.9 + 0.5 * k for k in range(12)]]
    assert all(b <= a for a, b in zip(warm, warm[1:]))
    feed = [feeding(t, "rainbow_trout")["value"]
            for t in [15.0 + 0.5 * k for k in range(16)]]
    assert all(b <= a for a, b in zip(feed, feed[1:]))
    surv = [survival(float(t), "brown_trout")["value"] for t in range(15, 31)]
    assert all(b <= a for a, b in zip(surv, surv[1:]))
    drive = [refuge_drive(float(t), "rainbow_trout")["value"]
             for t in range(15, 31)]
    assert all(b >= a for a, b in zip(drive, drive[1:]))


@pytest.mark.parametrize("fn", ALL)
def test_unknown_species_raises(fn):
    """Species outside THERMAL_SPECIES raise ValueError."""
    with pytest.raises(ValueError):
        fn(15.0, "cutthroat")


@pytest.mark.parametrize("fn_name", NAMES)
@pytest.mark.parametrize("species", ["brown_trout", "rainbow_trout"])
def test_provenance_complete(fn_name, species):
    """Study, DOI key, fitted params, and RMSE under 0.06."""
    fn = {"growth": growth, "feeding": feeding, "survival": survival,
          "refuge_drive": refuge_drive}[fn_name]
    prov = fn(15.0, species)["provenance"]
    assert prov["study"]
    assert "doi" in prov
    assert prov["params"]
    assert prov["rmse_vs_anchors"] is not None
    assert prov["rmse_vs_anchors"] < 0.06
    assert prov["anchors"]


def test_endpoints_stay_separate():
    """Endpoints disagree at 20 C brown water."""
    vals = [fn(20.0, "brown_trout")["value"] for fn in FITTED]
    assert len({round(v, 3) for v in vals}) > 1


def test_fits_deterministic():
    """Repeated evaluation returns identical envelopes."""
    assert growth(16.0, "brown_trout") == growth(16.0, "brown_trout")


def test_reproduction_stub_reports_no_data():
    """Reproduction carries explicit no-data status."""
    result = reproduction(12.0, "brown_trout")
    assert result["value"] is None
    assert result["status"] == "no_data"
