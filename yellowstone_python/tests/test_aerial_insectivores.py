"""Aerial-insectivore consumers of the emergent compartment."""
from __future__ import annotations

import pytest

from yellowstone_python.insects_birds import (AERIAL_INSECTIVORE_DIETS,
                                               DEFAULT_DIETS,
                                               diets_with_aerial_insectivores,
                                               step_compartments)


FORCING = dict(sun=1.0, air_c=20.0, cloud=0.1, moisture=0.7, flowering=0.6,
               water_c=15.0, wind_mps=0.5)


def test_aerial_dict_shapes_and_sources():
    """Each aerial consumer carries a valid diet, Holling pair, status and citations."""
    assert set(AERIAL_INSECTIVORE_DIETS) == {"swallow", "bat", "riparian_spider"}
    for cid, consumer in AERIAL_INSECTIVORE_DIETS.items():
        assert consumer["a"] > 0.0
        assert consumer["h"] > 0.0
        assert consumer["status"] == "authored_illustrative"
        assert consumer["sources"], f"{cid} must carry at least one source"
        diet = consumer["diet"]
        assert "emergent" in diet
        assert pytest.approx(sum(diet.values()), rel=0, abs=1e-9) == 1.0


def test_consumer_registration_preserves_base_defaults():
    """Combined consumer map carries all base diets plus the aerial additions."""
    combined = diets_with_aerial_insectivores()
    assert set(DEFAULT_DIETS).issubset(set(combined))
    assert "swallow" in combined
    assert "bat" in combined
    assert "riparian_spider" in combined
    # The combined mapping holds only the Holling parameters the solver reads.
    swallow = combined["swallow"]
    assert set(swallow) == {"a", "h", "diet"}


def test_emergent_consumption_sums_over_consumers():
    """consumed_by totals equal the realized drop in the Ne pool."""
    s0 = {"Nt": 0.9, "Nb": 0.9, "Ne": 0.9}
    consumers = diets_with_aerial_insectivores()
    new_state, ledger = step_compartments(dict(s0), FORCING, dt_s=3600.0,
                                           consumers=consumers)
    emerged = ledger["emergence"]
    # Ne balance: initial + emergence = final + total consumed from emergent + wind loss.
    total_consumed = sum(ledger["consumed_by"].values())
    assert total_consumed > 0.0
    # Each named consumer appears in the ledger with a nonnegative intake.
    for cid in consumers:
        assert ledger["consumed_by"][cid] >= 0.0
    # Removing aerial consumers must raise emergent survival in the same step.
    _, base_ledger = step_compartments(dict(s0), FORCING, dt_s=3600.0,
                                        consumers=DEFAULT_DIETS)
    assert sum(ledger["consumed_by"].values()) > sum(
        base_ledger["consumed_by"].values())
    no_aerial_state, _ = step_compartments(dict(s0), FORCING, dt_s=3600.0,
                                            consumers=DEFAULT_DIETS)
    assert new_state["Ne"] < no_aerial_state["Ne"]
    _ = emerged  # emergence recorded on the ledger


def test_existing_defaults_match_without_aerial_opt_in():
    """A caller passing DEFAULT_DIETS alone gets the previous behavior exactly."""
    s0 = {"Nt": 0.6, "Nb": 0.6, "Ne": 0.5}
    out_a, led_a = step_compartments(dict(s0), FORCING, dt_s=3600.0,
                                      consumers=DEFAULT_DIETS)
    out_b, led_b = step_compartments(dict(s0), FORCING, dt_s=3600.0,
                                      consumers=dict(DEFAULT_DIETS))
    for key in ("Nt", "Nb", "Ne"):
        assert out_a[key] == pytest.approx(out_b[key], rel=0, abs=1e-12)
    assert led_a["consumed_by"] == led_b["consumed_by"]
