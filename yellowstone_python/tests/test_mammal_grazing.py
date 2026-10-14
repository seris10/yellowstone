"""Grazer allocation ownership and explicit route eligibility."""
import copy

import pytest

from yellowstone_python.land.grazers import consumed_by_patch_from_grazers, update_grazers


@pytest.mark.parametrize("changes", [{"active": False}, {"route_support": {"qualified": False}}, {"grazing_owner": "mammals"}])
def test_excluded_or_separately_owned_actor_cannot_consume_cached_rates(changes):
    record = {"id": "b", "kind": "bison", "patch_id": "p", "path_xz": [[0, 0], [5, 5]],
              "rate_per_second": .1, **changes}
    before = copy.deepcopy(record)
    updated = update_grazers([record], [{"id": "p", "biomass": .8, "capacity": 1.}])
    assert record == before
    assert updated[0]["id"] == record["id"] and updated[0]["path_xz"] == record["path_xz"]
    assert updated[0]["rate_per_second"] == 0.
    assert consumed_by_patch_from_grazers([record], 60.) == {}
    assert consumed_by_patch_from_grazers(updated, 60.) == {}


def test_active_bison_allocation_preserves_original_rate_and_observation_separation():
    record = {"id": "b", "kind": "bison", "patch_id": "p", "grazing_owner": "legacy_grazers",
              "encounter_probability": 0., "route_support": {"qualified": True}}
    patch = {"id": "p", "biomass": .8, "capacity": 1.}
    original = update_grazers([{k: v for k, v in record.items() if k not in ("grazing_owner", "encounter_probability", "route_support")}], [patch])[0]
    updated = update_grazers([record], [patch])[0]
    assert updated["rate_per_second"] == original["rate_per_second"] > 0.
    assert consumed_by_patch_from_grazers([updated], 60.) == {"p": updated["rate_per_second"] * 60.}
