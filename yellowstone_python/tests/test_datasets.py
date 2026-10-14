from yellowstone_python.registry.claims import get_claim
from yellowstone_python.river.datasets import CLAIM_ID, ROLES, role_errors, window_errors


def test_roles_pass_validation():
    assert role_errors() == []


def test_locked_final_frozen_and_disjoint():
    assert ROLES["locked_final"] == [
        "derived/firehole_obs_locked_final.json"]
    assert window_errors() == []


def test_roles_match_claim_record():
    claim = get_claim(CLAIM_ID)
    for aid in ROLES["calibration"]:
        assert aid in claim["calibration_dataset_ids"]
    for aid in ROLES["development"] + ROLES["locked_final"]:
        assert aid in claim["evaluation_dataset_ids"]
