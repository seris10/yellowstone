"""Mammal proxy forcing, bounded stocks and checkpoint replay."""
import copy
import math

import pytest

from yellowstone_python.land.mammals import MammalEcology, load_catalogue


def patches(habitat="dry_meadow"):
    return [{"id": "p", "habitat": habitat, "biomass": .8, "capacity": 1., "moisture": .8,
             "center_xz": [0., 0.], "radius_m": 80., "insect_activity": .8}]


def forcing(**changes):
    row = {"air_c": 18., "daylight_fraction": .5, "season_phase": .5,
           "by_patch": {"p": {"forage_fraction": .8, "water_fraction": .8, "insect_fraction": .8,
                                 "soil_temperature_c": 18., "snow_m": 0.}}}
    for key, value in changes.items():
        if key in ("forage_fraction", "water_fraction", "insect_fraction", "soil_temperature_c", "snow_m"):
            row["by_patch"]["p"][key] = value
        else:
            row[key] = value
    return row


def actor(**changes):
    row = {"id": "b", "kind": "bison", "species_id": "bison", "patch_id": "p",
           "mammal_guild": "grazer", "encounter_probability": .45}
    row.update(changes)
    return row


def test_mixed_wildlife_ignores_other_taxa_and_canonicalizes_documented_aliases():
    original = [actor(), {"id": "fish", "kind": "rainbow_trout", "species_id": "rainbow_trout"},
                {"id": "bird", "kind": "raven", "species_id": "common_raven"}]
    before = copy.deepcopy(original)
    model = MammalEcology(patches(), original)
    assert original == before
    assert [a["id"] for a in model.actors] == ["b"]
    assert model.actors[0]["species_id"] == "bison_bison"
    with pytest.raises(ValueError, match="unknown claimed mammal"):
        MammalEcology(patches(), [{"id": "x", "kind": "unknown", "mammal_guild": "carnivore"}])
    with pytest.raises(ValueError, match="catalogued species"):
        MammalEcology(patches(), [actor(species_id="invented_species")])


@pytest.mark.parametrize("changes", [{"forage_fraction": .1}, {"water_fraction": .1}, {"snow_m": .9},
                                     {"air_c": 50.}, {"air_c": -25.}, {"soil_temperature_c": 42.}])
def test_bison_activity_decreases_with_resource_and_weather_stress(changes):
    baseline = MammalEcology(patches(), [actor()]).step(0., forcing())["actors"]["b"]["activity_index"]
    stressed = MammalEcology(patches(), [actor()]).step(0., forcing(**changes))["actors"]["b"]["activity_index"]
    assert 0 <= stressed < baseline <= 1


def test_hot_ground_blocks_actor_presence_at_any_encounter_probability():
    state = MammalEcology(patches(), [actor(encounter_probability=1.)]).step(0., forcing(soil_temperature_c=50.))
    assert state["actors"]["b"]["activity_index"] == 0.
    assert not state["actors"]["b"]["active"]
    assert state["actors"]["b"]["speed_multiplier"] == 0.


def test_insect_food_night_and_season_drive_bat_activity():
    sid = "myotis_lucifugus"
    def activity(**changes):
        model = MammalEcology(patches("forest_edge"))
        model.step(0., forcing(**changes))
        return model.activity["p"][sid]
    assert activity(daylight_fraction=0.) > activity(daylight_fraction=.9)
    assert activity(insect_fraction=.9) > activity(insect_fraction=.1)
    assert activity(season_phase=.5) > activity(season_phase=.05) == 0.


def test_wolf_prey_and_predation_have_causal_bounded_effects():
    with_wolf = MammalEcology(patches())
    without_wolf = with_wolf.clone()
    without_wolf.population["p"]["canis_lupus"] = 0.
    full = with_wolf.step(86400., forcing())
    absent = without_wolf.step(86400., forcing())
    assert full["by_patch"]["p"]["cervus_elaphus"] < absent["by_patch"]["p"]["cervus_elaphus"]
    assert with_wolf.activity["p"]["cervus_elaphus"] < without_wolf.activity["p"]["cervus_elaphus"]
    assert full["ledger"]["predation"] == full["ledger"]["predator_intake"] > 0.
    no_prey = MammalEcology(patches())
    for prey in no_prey.species["canis_lupus"]["traits"]["prey_species_ids"]:
        no_prey.population["p"][prey] = 0.
    no_prey.step(0., forcing())
    assert no_prey.activity["p"]["canis_lupus"] == 0.
    assert full["ledger"]["predator_intake_units"] == "removed_prey_population_equivalents"


def test_all_supported_species_have_nonzero_park_reference_habitat_states():
    catalogue = load_catalogue()
    habitats = sorted({h for r in catalogue["species"] for h in r["traits"]["habitats"]})
    contexts = [{**patches(h)[0], "id": h} for h in habitats]
    model = MammalEcology(contexts, catalogue=catalogue, local_mode="park_reference")
    state = model.step(3600., {"season_phase": .5, "daylight_fraction": .5})
    assert len(state["species"]) == 74
    for sid, row in state["species"].items():
        assert row["model_availability"]["ecology"] == "authored_guild_model"
        if row["supported_park_occurrence"]:
            assert row["population_equivalents"] > 0.
            assert any(model.activity[p][sid] > 0. for p in model.patches)
        else:
            assert row["population_equivalents"] == 0.
    assert all(0 <= n <= 1 for p in model.population.values() for n in p.values())
    assert abs(state["ledger"]["population_residual"]) < 1e-12


@pytest.mark.parametrize("sid", ["oreamnos_americanus", "ovis_canadensis", "ochotona_princeps", "marmota_flaviventris",
                                  "antilocapra_americana", "odocoileus_virginianus", "lynx_canadensis", "gulo_gulo"])
def test_midway_excludes_inappropriate_park_wide_habitat_species(sid):
    model = MammalEcology(patches("forest_edge"))
    state = model.step(0., forcing())
    assert state["species"][sid]["population_equivalents"] == 0.
    assert state["species"][sid]["eligible_local_patches"] == []


def test_observation_windows_are_reproducible_and_do_not_reroll_population():
    a, b = MammalEcology(patches(), [actor()], seed=123), MammalEcology(patches(), [actor()], seed=123)
    seen = []
    for _ in range(60):
        first, second = a.step(300., forcing()), b.step(300., forcing())
        assert first == second
        seen.append(first["actors"]["b"]["active"])
        assert first["species"]["bison_bison"]["population_equivalents"] > 0.
    assert any(seen) and not all(seen)
    c = MammalEcology(patches(), [actor(encounter_probability=0.)], seed=123)
    d = MammalEcology(patches(), [actor(encounter_probability=1.)], seed=123)
    assert c.step(300., forcing())["by_patch"] == d.step(300., forcing())["by_patch"]


def test_food_allocation_reserves_external_demand_and_prevents_duplicate_bison_grazing():
    a = MammalEcology(patches(), [actor(grazing_owner="mammals")])
    b = MammalEcology(patches(), [actor(grazing_owner="legacy_grazers")])
    for model in (a, b):
        for sid in model.population["p"]:
            model.population["p"][sid] = .2 if sid == "bison_bison" else 0.
    context = forcing()
    context["external_grazing_by_patch"] = {"p": .799999}
    sa, sb = a.step(86400., context), b.step(86400., context)
    assert 0 < sa["consumption_by_patch"]["p"] <= .8 - .799999
    assert sb["consumption_by_patch"]["p"] == 0.
    assert sb["ledger"]["external_legacy_grazing_ids"] == ["b"]
    assert sa["ledger"]["food_units"] == "vegetation_normalized_biomass_index"


def test_physical_time_splitting_agrees_for_inactive_population_decay():
    whole = MammalEcology(patches())
    halves = whole.clone()
    whole.step(86400., forcing(soil_temperature_c=50.))
    halves.step(43200., forcing(soil_temperature_c=50.))
    halves.step(43200., forcing(soil_temperature_c=50.))
    assert whole.elapsed_s == halves.elapsed_s == 86400.
    for sid in whole.species:
        assert whole.population["p"][sid] == pytest.approx(halves.population["p"][sid], rel=1e-12, abs=1e-15)


def test_checkpoint_replay_and_clone_preserve_full_state_without_aliasing():
    model = MammalEcology(patches(), [actor()])
    model.step(60., forcing())
    checkpoint = model.checkpoint()
    expected = model.step(120., forcing(snow_m=.3))
    model.restore(checkpoint)
    assert model.step(120., forcing(snow_m=.3)) == expected
    clone = model.clone()
    clone.population["p"]["bison_bison"] = 0.
    assert model.population["p"]["bison_bison"] > 0.
    assert checkpoint["elapsed_s"] == 60.


@pytest.mark.parametrize("field,value", [("activity", math.nan), ("risk", -1.), ("population", True),
                                          ("population", "0.2"), ("activity", 1.1)])
def test_invalid_checkpoint_matrices_are_transactional(field, value):
    model = MammalEcology(patches(), [actor()])
    model.step(60., forcing())
    before = model.checkpoint()
    bad = copy.deepcopy(before)
    bad[field]["p"]["bison_bison"] = value
    with pytest.raises(ValueError):
        model.restore(bad)
    assert model.checkpoint() == before


@pytest.mark.parametrize("field", ["environment", "consumption_by_patch", "ledger", "activity"])
def test_invalid_checkpoint_nested_state_is_transactional(field):
    model = MammalEcology(patches(), [actor()])
    model.step(60., forcing())
    before = model.checkpoint()
    bad = copy.deepcopy(before)
    if field == "environment":
        bad[field]["air_c"] = True
    elif field == "consumption_by_patch":
        bad[field]["p"] = math.inf
    elif field == "ledger":
        bad[field]["births"] = math.nan
    else:
        bad[field]["other_patch"] = {}
    with pytest.raises(ValueError):
        model.restore(bad)
    assert model.checkpoint() == before


@pytest.mark.parametrize("value", [True, "60", -1., math.nan, math.inf, 86401.])
def test_invalid_physical_timestep_rejected_before_mutation(value):
    model = MammalEcology(patches())
    before = model.checkpoint()
    with pytest.raises(ValueError):
        model.step(value, forcing())
    assert model.checkpoint() == before


@pytest.mark.parametrize("changes", [{"season_phase": 1.}, {"snow_m": -1.}, {"soil_temperature_c": True},
                                     {"water_fraction": math.nan}, {"insect_fraction": "1"}])
def test_invalid_environment_rejected_before_mutation(changes):
    model = MammalEcology(patches())
    before = model.checkpoint()
    with pytest.raises(ValueError):
        model.step(1., forcing(**changes))
    assert model.checkpoint() == before


@pytest.mark.parametrize("value", [True, "0", -1, .5, 0.0])
def test_seed_rejects_coercion_negative_and_fractional_values(value):
    with pytest.raises(ValueError, match="nonnegative integer"):
        MammalEcology(patches(), seed=value)


def test_zero_seed_checkpoint_and_json_replay_are_supported():
    a = MammalEcology(patches(), [actor()], seed=0)
    state = a.step(10., forcing())
    b = MammalEcology(patches(), [actor()], seed=0)
    import json
    assert b.restore(json.loads(json.dumps(a.checkpoint()))) == state
    assert b.step(50., forcing()) == a.step(50., forcing())
    wrong = b.checkpoint()
    wrong["seed"] = False
    with pytest.raises(ValueError):
        b.restore(wrong)


@pytest.mark.parametrize("changes", [{"active": False}, {"route_support": {"qualified": False}}])
def test_excluded_external_actor_cannot_reserve_a_species_proxy_stock(changes):
    model = MammalEcology(patches(), [actor(grazing_owner="legacy_grazers", **changes)])
    for sid in model.population["p"]:
        model.population["p"][sid] = .2 if sid == "bison_bison" else 0.
    state = model.step(3600., forcing())
    assert state["consumption_by_patch"]["p"] > 0.
    assert state["ledger"]["external_legacy_grazing_ids"] == []
    assert state["ledger"]["externally_owned_population_by_patch"]["p"] == {}


def test_shared_species_proxy_is_owned_once_and_display_count_does_not_add_population():
    source = [actor(grazing_owner="legacy_grazers"), actor(id="second", grazing_owner="mammals")]
    model = MammalEcology(patches(), source)
    for sid in model.population["p"]:
        model.population["p"][sid] = .2 if sid == "bison_bison" else 0.
    state = model.step(3600., forcing())
    assert state["consumption_by_patch"]["p"] == 0.
    assert state["ledger"]["externally_owned_population_by_patch"]["p"] == {"bison_bison": .2}
    assert state["ledger"]["ownership_evidence_class"] == "authored"
    assert len(state["actors"]) == 2
    assert state["species"]["bison_bison"]["population_equivalents"] < 1.


def test_species_identity_must_match_render_kind_and_documented_deer_alias():
    with pytest.raises(ValueError, match="disagrees with species identity"):
        MammalEcology(patches(), [actor(species_id="canis_lupus")])
    model = MammalEcology(patches(), [actor(kind="deer", species_id="mule_deer")])
    assert model.actors[0]["species_id"] == "odocoileus_hemionus"


@pytest.mark.parametrize("kind,sid,habitat,mode", [
    ("black_bear", "ursus_americanus", "forest_edge", "midway"),
    ("canada_lynx", "lynx_canadensis", "cold_conifer_forest", "park_reference"),
])
def test_supplied_bear_and_lynx_run_their_own_ecology_and_checkpoint(kind, sid, habitat, mode):
    representative = actor(kind=kind, species_id=kind, mammal_guild="omnivore" if kind == "black_bear" else "carnivore",
                           encounter_probability=1., grazing_owner="mammals")
    model = MammalEcology(patches(habitat), [representative], local_mode=mode)
    first = model.step(60., forcing())
    row = first["actors"]["b"]
    assert row["species_id"] == sid and row["kind"] == kind
    assert row["active"] and 0 < row["activity_index"] <= 1.
    checkpoint = model.checkpoint()
    expected = model.step(120., forcing(snow_m=.3))
    model.restore(checkpoint)
    assert model.step(120., forcing(snow_m=.3)) == expected
    mismatched = {**representative, "species_id": "ursus_arctos" if kind == "black_bear" else "lynx_rufus"}
    with pytest.raises(ValueError, match="disagrees with species identity"):
        MammalEcology(patches(habitat), [mismatched], local_mode=mode)


def test_black_bear_forest_requirement_and_lynx_local_mode_block_inappropriate_presence():
    for kind, habitat, mode in (("black_bear", "dry_meadow", "midway"),
                               ("canada_lynx", "forest_edge", "park_reference"),
                               ("canada_lynx", "cold_conifer_forest", "midway")):
        model = MammalEcology(patches(habitat), [actor(kind=kind, species_id=kind, encounter_probability=1.)],
                              local_mode=mode)
        state = model.step(60., forcing())
        assert not state["actors"]["b"]["active"]
        assert state["actors"]["b"]["activity_index"] == 0.
        assert state["species"][state["actors"]["b"]["species_id"]]["eligible_local_patches"] == []
