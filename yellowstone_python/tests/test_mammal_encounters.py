"""Primary mammal catalogue reconciliation and terrain-qualified encounter routes."""
import copy
import json
from pathlib import Path

from yellowstone_python.authoring.mammal_encounters import RouteSupport, author_encounters, habitat_mask_blocker
from yellowstone_python.land.mammal_catalogue import build_catalogue, load_catalogue


def inputs():
    world = {"georeference": {"extent": 400.}, "pools": [], "rivers": [], "routes": []}
    patches = [{"id": "p", "habitat": "forest_edge", "center_xz": [0., 0.], "radius_m": 60.}]
    return world, patches


def test_primary_rows_remain_complete_after_species_and_alias_reconciliation():
    catalogue = load_catalogue()
    rows = catalogue["raw_occurrence_records"]
    raw = dict(catalogue["sources"]["npspecies"])
    raw["sections"] = [{"section": s, "records": [{k: v for k, v in r.items() if k != "section"} for r in rows if r["section"] == s]}
                       for s in ("main_list", "in_review")]
    compiled = build_catalogue(raw)
    assert compiled == catalogue
    assert catalogue["source_counts"] == {"headline": 67, "raw_occurrence_records": 78, "canonical_species": 74,
                                           "supported_species": 70, "unconfirmed_supplemental_species": 4}
    assert len([r for r in catalogue["species"] if r["qualitative_bat_confirmation"]]) == 13
    assert {r["scientific_name"] for r in catalogue["species"] if not r["supported_park_occurrence"]} == {
        "Spilogale gracilis", "Martes pennanti", "Sorex hoyi", "Lemmiscus curtatus"}
    deer = next(r for r in catalogue["species"] if r["species_id"] == "odocoileus_virginianus")
    assert deer["render_kind"] is None
    assert all(r["traits"]["trait_evidence_class"] == "authored" for r in catalogue["species"])


def test_supplied_bear_and_lynx_retain_distinct_species_and_local_habitat_gates():
    catalogue = load_catalogue()
    records = {r["render_kind"]: r for r in catalogue["species"] if r["render_kind"]}
    assert len(records) == 9
    assert records["black_bear"]["species_id"] == "ursus_americanus"
    assert records["canada_lynx"]["species_id"] == "lynx_canadensis"
    for kind in ("bison", "grizzly", "black_bear", "bobcat", "badger", "canada_lynx"):
        assert records[kind]["model_availability"]["render_geometry_class"] == "supplied_mesh_authored_motion"
    assert records["canada_lynx"]["traits"]["habitats"] == ["cold_conifer_forest"]
    assert "midway" not in records["canada_lynx"]["traits"]["allowed_local_modes"]
    world, contexts = inputs()
    contexts[0]["habitat"] = "cold_conifer_forest"
    source = [{"id": "lynx", "kind": "canada_lynx", "species_id": "lynx_canadensis",
               "patch_id": "p", "path_xz": [[0., 0.], [5., 0.]]}]
    doc = author_encounters(world, (lambda x, z: 3., lambda x, z: 0.), [],
                            patches=contexts, existing_actors=source)
    preserved = next(r for r in doc["actors"] if r["id"] == "lynx")
    assert preserved["path_xz"] == source[0]["path_xz"]
    assert not preserved["route_support"]["qualified"]
    assert preserved["route_support"]["rejection_reason"] == "unsupported_local_mode"
    assert preserved["encounter_probability"] == 0.


def test_encounters_are_reproducible_have_real_y_and_preserve_source_geometry():
    world, patches = inputs()
    source = [{"id": "bison_01", "kind": "bison", "species_id": "bison", "patch_id": "p", "path_xz": [[-20., 0.], [-15., 5.]]}]
    before = copy.deepcopy((world, patches, source))
    terrain = (lambda x, z: 10. + .01 * x - .02 * z, lambda x, z: 2.)
    a = author_encounters(world, terrain, [], patches=patches, existing_actors=source, seed=77)
    b = author_encounters(world, terrain, [], patches=patches, existing_actors=source, seed=77)
    assert a == b
    assert (world, patches, source) == before
    eligible_kinds = {r["render_kind"] for r in load_catalogue()["species"]
                      if r["render_kind"] and "midway" in r["traits"]["allowed_local_modes"]
                      and "forest_edge" in r["traits"]["habitats"]}
    assert {r["kind"] for r in a["actors"]} == eligible_kinds
    assert "black_bear" in eligible_kinds and "canada_lynx" not in eligible_kinds
    assert a["rejected_reasons"]["unsupported_local_mode_canada_lynx"] == 1
    baseline = next(r for r in a["actors"] if r["id"] == "bison_01")
    assert baseline["path_xz"] == source[0]["path_xz"]
    assert baseline["grazing_owner"] == "legacy_grazers"
    for row in a["actors"]:
        assert row["route_support"]["qualified"]
        if "position" in row:
            assert row["position"][1] == terrain[0](row["position"][0], row["position"][2])
            assert row["population_measurement"] is None
            assert 0 < row["encounter_probability"] < 1


def test_complete_segments_and_body_radius_reject_mapped_crossings():
    world, patches = inputs()
    world["routes"] = [{"points": [[0., 0., -100.], [0., 0., 100.]], "width": 2.}]
    world["rivers"] = [{"points": [[-100., 0., 50.], [100., 0., 50.]], "width": 4.}]
    support = RouteSupport(world, (lambda x, z: 3., lambda x, z: 0.), [], patches, None, None)
    bison = next(r for r in load_catalogue()["species"] if r["render_kind"] == "bison")
    assert support.check([[-20., 0.], [20., 0.]], bison) == "visitor_route"
    assert support.check([[-20., 35.], [-20., 60.]], bison) == "open_water"
    assert support.qualify(9., 0., bison) == "visitor_route"
    assert support.qualify(12., 0., bison) is None


def test_forest_obligate_candidates_use_the_complete_compatible_patch_support():
    world, patches = inputs()
    habitat = lambda x, z: "forest_edge" if x < -40. else "dry_meadow"
    document = author_encounters(world, (lambda x, z: 3., lambda x, z: 0.), [],
                                 patches=patches, habitat_sampler=habitat, seed=77)
    bear = next(r for r in document["actors"] if r["kind"] == "black_bear")
    assert bear["route_support"]["qualified"]
    assert all(x < -40. for x, z in bear["path_xz"])
    assert document["authoring_choices"]["forest_candidate_radius_fraction"] == {
        "value": 1., "status": "authored", "uncertainty": "unknown"}


def test_mapped_aprons_mineral_and_slope_reject_routes_without_changing_sources():
    world, patches = inputs()
    shell = {"center_xz": [0., 0.], "r_apron_m": 30.}
    source = [{"id": "b", "kind": "bison", "species_id": "bison", "patch_id": "p", "path_xz": [[0., 0.], [5., 0.]]}]
    doc = author_encounters(world, (lambda x, z: 1., lambda x, z: 0.), [shell], patches=patches, existing_actors=source)
    baseline = next(r for r in doc["actors"] if r["id"] == "b")
    assert baseline["path_xz"] == source[0]["path_xz"]
    assert baseline["encounter_probability"] == 0.
    assert baseline["route_support"]["rejection_reason"] == "mapped_pool_apron"
    steep = author_encounters(world, (lambda x, z: 1., lambda x, z: 50.), [], patches=patches)
    mineral = author_encounters(world, (lambda x, z: 1., lambda x, z: 0.), [], patches=patches, blocked=lambda x, z: True)
    assert not steep["actors"] and not mineral["actors"]
    assert steep["rejected_reasons"]["steep_terrain"] > 0
    assert mineral["rejected_reasons"]["mineral_surface"] > 0


def test_mask_sampler_uses_mineral_and_meadow_channels_without_claiming_water(tmp_path):
    from PIL import Image
    path = tmp_path / "assets/textures/habitat_mask.png"
    path.parent.mkdir(parents=True)
    image = Image.new("RGB", (1025, 1025), (0, 200, 255))
    image.putpixel((512, 512), (200, 0, 0))
    image.save(path)
    blocked = habitat_mask_blocker(tmp_path)
    assert blocked(0., 0.)
    assert not blocked(8., 8.)
    assert blocked.habitat_at(8., 8.) == "dry_meadow"
    assert blocked.habitat_at(5000., 0.) == "unsuitable_matrix"


def test_mask_body_disk_rejects_intersecting_mineral_pixel(tmp_path):
    from PIL import Image
    path = tmp_path / "assets/textures/habitat_mask.png"
    path.parent.mkdir(parents=True)
    image = Image.new("RGB", (1025, 1025), (0, 200, 0))
    image.putpixel((512, 512), (255, 0, 0))
    image.save(path)
    blocked = habitat_mask_blocker(tmp_path)
    assert not blocked(-.5, -.5)
    assert blocked.disk(-.5, -.5, 1.)
    assert not blocked.disk(-1., -1., 1.)


def test_cli_rejects_source_input_as_output_before_loading_or_overwriting(tmp_path):
    import pytest
    from tools.build_mammal_catalogue import main
    world = tmp_path / "data/world.json"
    world.parent.mkdir(parents=True)
    world.write_text('{"preserved": true}')
    before = world.read_bytes()
    with pytest.raises(ValueError, match="protected world input"):
        main(["--world", str(tmp_path), "--out", str(world)])
    assert world.read_bytes() == before
