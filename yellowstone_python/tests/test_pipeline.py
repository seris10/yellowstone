"""Pipeline stage ordering and missing-input rejection checks."""
from types import SimpleNamespace

import pytest

from yellowstone_python.pipeline import pipeline


def test_model_stage_inputs_have_producers():
    """Require the maintained model stages to form a valid dependency chain."""
    pipeline.validate_stage_dependencies()
    assert pipeline.STAGES[-1].WRITES == ("result",)


def test_invalid_stage_order_stops_before_model_execution(monkeypatch):
    """Reject a stage that consumes a value before its producer runs."""
    calls = []
    consumer = SimpleNamespace(__name__="consumer", READS=("temperature",), WRITES=("result",),
                               run=lambda state, cfg: calls.append("consumer"))
    producer = SimpleNamespace(__name__="producer", READS=("baseline",), WRITES=("temperature",),
                               run=lambda state, cfg: calls.append("producer"))
    monkeypatch.setattr(pipeline, "STAGES", (consumer, producer))
    with pytest.raises(ValueError, match="consumer missing inputs.*temperature"):
        pipeline.simulate_all({}, {}, {}, ())
    assert calls == []


def test_stage_state_reaches_the_final_result(monkeypatch):
    """Pass produced state and the caller's config through the ordered stages."""
    calls = []
    config = {"delta_c": 2.0}

    def heat(state, cfg):
        assert cfg is config
        state["temperature"] = state["baseline"]["temperature"] + cfg["delta_c"]
        calls.append("heat")
        return state

    def finish(state, cfg):
        state["result"] = {"temperature": state["temperature"], "world": state["world"]}
        calls.append("finish")
        return state

    first = SimpleNamespace(__name__="heat", READS=("baseline",), WRITES=("temperature",), run=heat)
    second = SimpleNamespace(__name__="finish", READS=("temperature", "world"), WRITES=("result",), run=finish)
    monkeypatch.setattr(pipeline, "STAGES", (first, second))
    world = {"id": "synthetic_world"}
    assert pipeline.simulate_all(config, {"temperature": 10.0}, world, ()) == {"temperature": 12.0, "world": world}
    assert calls == ["heat", "finish"]


@pytest.fixture
def stability_inputs(tmp_path, monkeypatch):
    """Small input files with the hashes recorded before a build starts."""
    import hashlib
    from yellowstone_python.common.io import sha256_file
    from yellowstone_python.pipeline import inputs

    data = tmp_path / "data"
    data.mkdir()
    names = ("world.json", "placements.json", "species_catalogue.json", "terrain.f32", "ecosystem.json")
    paths = {name: data / name for name in names}
    for name, path in paths.items():
        path.write_bytes(name.encode())
    digest = hashlib.sha256(b"unchanged sources")
    monkeypatch.setattr(inputs, "_hash_package_sources", lambda: (digest, "fixture"))
    deps = {name: sha256_file(path) for name, path in paths.items()}
    deps.update(code=digest.hexdigest()[:16], ecosystem_path=str(paths["ecosystem.json"]))
    return inputs, {"world_root": str(tmp_path)}, deps, paths


def test_unchanged_inputs_pass_build_stability_check(stability_inputs):
    inputs, cfg, deps, _ = stability_inputs
    inputs.verify_input_stability(cfg, deps)


@pytest.mark.parametrize("change", ["content", "disappearance"])
def test_bound_habitat_mask_change_stops_build(tmp_path, monkeypatch, change):
    import hashlib
    from yellowstone_python.pipeline import inputs
    from yellowstone_python.land import vegetation
    from yellowstone_python.validation import terrain

    data = tmp_path / "data"
    data.mkdir()
    for name in ("world.json", "placements.json", "species_catalogue.json", "ecosystem.json"):
        (data / name).write_text("{}")
    (data / "terrain.f32").write_bytes(b"terrain fixture")
    mask = tmp_path / "assets/textures/habitat_mask.png"
    mask.parent.mkdir(parents=True)
    mask.write_bytes(b"bound habitat support")
    digest = hashlib.sha256(b"stable source fixture")
    monkeypatch.setattr(inputs, "_hash_package_sources", lambda: (digest, "fixture"))
    monkeypatch.setattr(inputs, "resolve_code_rev", lambda: ("fixture", "fixture"))
    monkeypatch.setattr(terrain, "guard_terrain", lambda *args, **kwargs: {"guards": []})
    monkeypatch.setattr(vegetation, "load_terrain", lambda *args: None)
    monkeypatch.setattr(vegetation, "terrain_fns", lambda *args: ())
    cfg = {"world_root": str(tmp_path)}
    _, _, deps, _ = inputs.load_inputs(cfg)
    entry = deps["external_inputs"]["habitat_mask"]
    assert entry["exists"] and entry["path"] == str(mask)
    assert entry["sha256"] == hashlib.sha256(mask.read_bytes()).hexdigest()
    inputs.verify_input_stability(cfg, deps)
    if change == "disappearance":
        mask.unlink()
    else:
        mask.write_bytes(b"changed habitat support")
    with pytest.raises(RuntimeError, match="external build input habitat_mask changed"):
        inputs.verify_input_stability(cfg, deps)


def test_changed_sources_stop_build_before_publication(stability_inputs, monkeypatch):
    import hashlib
    inputs, cfg, deps, _ = stability_inputs
    monkeypatch.setattr(inputs, "_hash_package_sources", lambda: (hashlib.sha256(b"changed"), "fixture"))
    with pytest.raises(RuntimeError, match="model or render sources changed"):
        inputs.verify_input_stability(cfg, deps)


def test_motion_mesh_bytes_are_bound_independently_of_manifest(tmp_path, monkeypatch):
    import hashlib
    import json
    from yellowstone_python.pipeline import inputs
    from yellowstone_python.land import vegetation
    from yellowstone_python.validation import terrain

    data = tmp_path / "data"
    data.mkdir()
    for name in ("world.json", "placements.json", "species_catalogue.json", "ecosystem.json"):
        (data / name).write_text("{}")
    (data / "terrain.f32").write_bytes(b"terrain fixture")
    mesh = tmp_path / "assets/animal.glb"
    mesh.parent.mkdir()
    mesh.write_bytes(b"frozen mesh fixture")
    manifest = {"assets": [{"path": "assets/animal.glb",
                           "sha256": hashlib.sha256(mesh.read_bytes()).hexdigest()}]}
    (data / "wildlife_motion_assets.json").write_text(json.dumps(manifest))
    digest = hashlib.sha256(b"stable source fixture")
    monkeypatch.setattr(inputs, "_hash_package_sources", lambda: (digest, "fixture"))
    monkeypatch.setattr(inputs, "resolve_code_rev", lambda: ("fixture", "fixture"))
    monkeypatch.setattr(terrain, "guard_terrain", lambda *args, **kwargs: {"guards": []})
    monkeypatch.setattr(vegetation, "load_terrain", lambda *args: None)
    monkeypatch.setattr(vegetation, "terrain_fns", lambda *args: ())
    cfg = {"world_root": str(tmp_path)}
    _, _, deps, _ = inputs.load_inputs(cfg)
    inputs.verify_input_stability(cfg, deps)
    mesh.write_bytes(b"changed mesh fixture")
    with pytest.raises(RuntimeError, match="external build input wildlife_asset"):
        inputs.verify_input_stability(cfg, deps)
    with pytest.raises(ValueError, match="differs from its manifest"):
        inputs.load_inputs(cfg)


@pytest.mark.parametrize("relative", ["tools/bake_world.gd", "tools/author_lodgepole.py",
                                      "scripts/forest_floor.gd", "shaders/canopy_surface.gdshader"])
def test_render_authoring_sources_change_build_hash(tmp_path, monkeypatch, relative):
    from yellowstone_python.pipeline import inputs
    monkeypatch.setattr(inputs, "PKG_ROOT", tmp_path / "package")
    world = tmp_path / "world"
    monkeypatch.setattr(inputs, "_default_world_root_for_hash", lambda: world)
    path = world / relative
    path.parent.mkdir(parents=True)
    path.write_text("original source")
    before = inputs._hash_package_sources()[0].hexdigest()
    path.write_text("changed source")
    assert inputs._hash_package_sources()[0].hexdigest() != before


def test_outside_canopy_window_retains_unknown_coverage(tmp_path, monkeypatch):
    from yellowstone_python.pipeline.stages import vegetation
    from yellowstone_python.pipeline.shared import CANOPY_FALLBACK
    provenance = tmp_path / "canopy_height.provenance.json"
    provenance.write_text("{}")
    monkeypatch.setattr(vegetation, "_canopy_from_height", lambda *args: (
        None, {"reason": "outside_measured_canopy_window"}))
    value, source = vegetation._canopy_from_census((900, 900), 30,
        tmp_path / "census.json", canopy_provenance_path=provenance)
    assert value == CANOPY_FALLBACK
    assert source == "illustrative_fallback_outside_canopy_height_window"


@pytest.mark.parametrize("name", ["terrain.f32", "ecosystem.json", "world.json"])
def test_changed_required_input_stops_build(stability_inputs, name):
    inputs, cfg, deps, paths = stability_inputs
    paths[name].write_bytes(b"changed during model computation")
    with pytest.raises(RuntimeError, match=f"build input {name} changed"):
        inputs.verify_input_stability(cfg, deps)


def test_missing_required_input_stops_build(stability_inputs):
    inputs, cfg, deps, paths = stability_inputs
    paths["terrain.f32"].unlink()
    with pytest.raises(RuntimeError, match="build input terrain.f32 changed"):
        inputs.verify_input_stability(cfg, deps)


@pytest.mark.parametrize("change", ["content", "disappearance", "appearance"])
def test_changed_canopy_input_stops_build(stability_inputs, tmp_path, change):
    from yellowstone_python.common.io import sha256_file
    inputs, cfg, deps, _ = stability_inputs
    canopy = tmp_path / "canopy_height.tif"
    if change != "appearance":
        canopy.write_bytes(b"frozen canopy")
    deps["external_inputs"] = {"canopy_height": {
        "path": str(canopy), "exists": canopy.is_file(),
        "sha256": sha256_file(canopy) if canopy.is_file() else None}}
    inputs.verify_input_stability(cfg, deps)
    if change == "disappearance":
        canopy.unlink()
    else:
        canopy.write_bytes(b"different canopy")
    with pytest.raises(RuntimeError, match="external build input canopy_height changed"):
        inputs.verify_input_stability(cfg, deps)


@pytest.mark.parametrize("section,key", [("snow", "days"), (None, "wind_seed"), ("overland", "grid")])
@pytest.mark.parametrize("value", [True, False, "32", 32.5])
def test_integer_config_controls_reject_coercible_values(tmp_path, section, key, value):
    from yellowstone_python.pipeline.config import validate_config
    cfg = {"world_root": str(tmp_path)}
    if section is None:
        cfg[key] = value
    else:
        cfg[section] = {key: value}
        if section == "overland":
            cfg[section]["enabled"] = True
    with pytest.raises(ValueError, match=key):
        validate_config(cfg)
