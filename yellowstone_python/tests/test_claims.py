from yellowstone_python.registry.claims import CLAIM_FIELDS, CLAIMS, get_claim, registry_errors, resolve_artifact_id, split_artifact_id, validate_claim


def test_registry_has_two_seed_claims():
    ids = [c["claim_id"] for c in CLAIMS]
    assert "reach_water_temperature_ice_free" in ids
    assert "snow_swe_clearings" in ids


def test_registry_passes_validation():
    assert registry_errors() == []


def test_seed_claims_start_unaccepted():
    for c in CLAIMS:
        assert c["review_status"] == "not_yet_accepted"


def test_seed_claims_name_datasets_and_evidence():
    temp = get_claim("reach_water_temperature_ice_free")
    assert temp["evaluation_dataset_ids"]
    assert temp["evidence_artifact_ids"]
    assert temp["known_exclusions"]
    snow = get_claim("snow_swe_clearings")
    assert snow["calibration_dataset_ids"]
    assert snow["evaluation_dataset_ids"]


def test_validate_claim_catches_missing_fields():
    assert validate_claim({"claim_id": "x"}) != []


def test_validate_claim_rejects_accepted_without_evaluation():
    rec = {f: "v" for f in CLAIM_FIELDS}
    rec["claim_id"] = "demo"
    rec["review_status"] = "accepted"
    rec["evaluation_dataset_ids"] = []
    assert validate_claim(rec) != []


def test_get_claim_rejects_unknown():
    try:
        get_claim("no_such_claim")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


def test_all_dataset_and_evidence_ids_resolve():
    for c in CLAIMS:
        for key in ("calibration_dataset_ids", "evaluation_dataset_ids",
                    "evidence_artifact_ids"):
            for aid in c[key]:
                resolve_artifact_id(aid)


def test_split_syntax():
    assert split_artifact_id("derived/snotel_obs.json:holdout") == \
        ("derived/snotel_obs.json", "holdout")
    assert split_artifact_id("derived/firehole_obs.json") == \
        ("derived/firehole_obs.json", None)
    for bad in ("derived/x.json:", ":holdout", "derived/x.json:a:b",
                " has space.json", "/abs.json"):
        try:
            resolve_artifact_id(bad)
        except (ValueError, FileNotFoundError):
            continue
        raise AssertionError(f"expected rejection for {bad!r}")


def test_resolver_rejects_missing_file():
    try:
        resolve_artifact_id("derived/no_such_bundle.json")
    except FileNotFoundError:
        return
    raise AssertionError("expected FileNotFoundError")
