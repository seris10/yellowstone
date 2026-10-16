"""Inputs build operations."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import PKG_ROOT, Path, WORLD_ID, default_world_root, json, resolve_code_rev, sha256_file, sha256_json

def _hash_package_sources() -> tuple[object, str]:
    """SHA-256 of package tools plus Godot scripts, shaders and authoring tools.
Returns (hash, source) where source names the lister (fd or rglob) and the roots included."""
    import hashlib
    import subprocess
    code_hash = hashlib.sha256()
    world_root = Path(_default_world_root_for_hash())
    roots: list[tuple[Path, tuple[str, ...]]] = [
        (PKG_ROOT / "yellowstone_python", (".py",)),
        (PKG_ROOT / "tools", (".py",)),
        (world_root / "scripts", (".gd",)),
        (world_root / "shaders", (".gdshader", ".gdshaderinc")),
        (world_root / "tools", (".gd", ".py")),
    ]
    sources: list[str] = []
    for root, suffixes in roots:
        if not root.is_dir():
            continue
        tracked: list[Path] = []
        source_tag = "rglob"
        try:
            fd_args = ["fd", "-u", "-0", "-t", "f"]
            for suffix in suffixes:
                fd_args += ["-e", suffix.lstrip(".")]
            fd_args += [".", str(root)]
            proc = subprocess.run(fd_args, capture_output=True, timeout=10,
                                  check=False)
            if proc.returncode == 0 and proc.stdout:
                rows = proc.stdout.split(b"\x00")
                tracked = [Path(r.decode("utf-8")) for r in rows if r]
                source_tag = "fd"
        except (OSError, subprocess.TimeoutExpired):
            tracked = []
        if not tracked:
            for suffix in suffixes:
                tracked.extend(root.rglob(f"*{suffix}"))  # fd-ok
            source_tag = "rglob"
        for p in sorted(tracked):
            if p.is_file():
                # Prefix every file's relative path so moves and renames affect the hash.
                code_hash.update(str(p.relative_to(root.parent)).encode())
                code_hash.update(b"\x00")
                code_hash.update(p.read_bytes())
        sources.append(f"{root.name}:{source_tag}")
    return code_hash, "+".join(sources) if sources else "empty"


def _default_world_root_for_hash() -> Path:
    """World root used by the code hash; honors $YELLOWSTONE_WORLD."""
    import os as _os
    return Path(_os.environ.get("YELLOWSTONE_WORLD")
                or (PKG_ROOT.parent / WORLD_ID))

def verify_input_stability(cfg: dict, deps: dict) -> None:
    """Reject a build when its model sources or required inputs change during computation."""
    digest, _ = _hash_package_sources()
    if digest.hexdigest()[:16] != deps["code"]:
        raise RuntimeError("model or render sources changed during the build; rerun a fresh build")
    world_root = Path(cfg.get("world_root") or default_world_root())
    inputs = {name: world_root / "data" / name for name in
              ("world.json", "placements.json", "species_catalogue.json", "terrain.f32")}
    inputs["ecosystem.json"] = Path(deps["ecosystem_path"])
    for name, path in inputs.items():
        if not path.is_file() or sha256_file(path) != deps[name]:
            raise RuntimeError(f"build input {name} changed during computation; rerun a fresh build")
    for name, entry in deps.get("external_inputs", {}).items():
        if entry.get("path") is None:
            continue
        path = Path(entry["path"])
        if (path.is_file() != entry["exists"]
                or (path.is_file() and sha256_file(path) != entry["sha256"])):
            raise RuntimeError(f"external build input {name} changed during computation; rerun a fresh build")


def load_inputs(cfg: dict) -> tuple[dict, dict, dict, object]:
    """(baseline, world, deps, terrain_sample_fns). Content-complete hashes."""
    from yellowstone_python.land.vegetation import load_terrain, terrain_fns
    world_root = Path(cfg.get("world_root") or default_world_root())
    required = [
        world_root / "data" / "ecosystem.json",
        world_root / "data" / "world.json",
        world_root / "data" / "placements.json",
        world_root / "data" / "species_catalogue.json",
        world_root / "data" / "terrain.f32",
    ]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise FileNotFoundError(
            "missing world inputs: " + ", ".join(missing))
    eco_path = world_root / "data" / "ecosystem.json"
    frozen = eco_path.with_suffix(".json.pre-python")
    eco_role = "active_baseline"
    if frozen.exists():
        eco_path = frozen
        eco_role = "frozen_pre_python_baseline"
    try:
        baseline = json.loads(eco_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {eco_path}: {exc}") from exc
    try:
        world = json.loads(
            (world_root / "data" / "world.json").read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in world.json: {exc}") from exc
    code_hash, code_hash_source = _hash_package_sources()
    code_rev, code_rev_source = resolve_code_rev()

    def _external_entry(path: Path) -> dict:
        """Path, size, and content hash so an input change surfaces at a stable build-id."""
        if not path.is_file():
            return {"path": str(path), "exists": False, "sha256": None}
        return {"path": str(path), "exists": True,
                "sha256": sha256_file(path),
                "size": path.stat().st_size}

    rcfg = cfg.get("replay", {}) or {}
    cross_sections_cfg = rcfg.get("cross_sections_file")
    if isinstance(cross_sections_cfg, str) and cross_sections_cfg:
        cs_path = Path(cross_sections_cfg)
        if not cs_path.is_absolute():
            cs_path = PKG_ROOT / cs_path
    else:
        cs_path = None
    wcfg_io = cfg.get("weather", {}) or {}
    met_cfg = wcfg_io.get("met_bundle")
    if isinstance(met_cfg, str) and met_cfg:
        met_candidate = Path(met_cfg)
        if not met_candidate.is_absolute():
            met_candidate = PKG_ROOT / met_candidate
    else:
        met_candidate = PKG_ROOT / "derived" / "met.json"
    external_inputs = {
        "terrain": _external_entry(world_root / "data" / "terrain.f32"),
        "cross_sections": (_external_entry(cs_path) if cs_path is not None
                           else {"path": None, "exists": False,
                                 "sha256": None}),
        "met_bundle": (_external_entry(met_candidate) if wcfg_io.get("use_met_bundle", True)
                       else {"path": None, "exists": False, "sha256": None}),
        "requirements": _external_entry(PKG_ROOT / "requirements.txt"),
        "package_metadata": _external_entry(PKG_ROOT / "pyproject.toml"),
        "canopy_census": _external_entry(PKG_ROOT / "derived" / "census.json"),
        "canopy_height": _external_entry(PKG_ROOT / "derived" / "lidar_canopy" / "canopy_height.tif"),
        "interpreted_canopy_height": _external_entry(PKG_ROOT / "derived" / "lidar_canopy" / "interpreted_canopy_height.tif"),
        "canopy_cover": _external_entry(PKG_ROOT / "derived" / "lidar_canopy" / "canopy_coverage.json"),
        "canopy_provenance": _external_entry(PKG_ROOT / "derived" / "lidar_canopy" / "canopy_height.provenance.json"),
        "treemap_sizes": _external_entry(PKG_ROOT / "derived" / "treemap_midway.json"),
        "habitat_mask": _external_entry(world_root / "assets" / "textures" / "habitat_mask.png"),
        "authored_scene": _external_entry(world_root / "scenes" / "authored_world.tscn"),
        "lodgepole_metadata": _external_entry(world_root / "assets/imported/lodgepole/lodgepole_metadata.json"),
        "asset_manifest": _external_entry(world_root / "data" / "asset_manifest.json"),
        "wildlife_motion_assets": _external_entry(world_root / "data" / "wildlife_motion_assets.json"),
        "mammal_catalogue": _external_entry(PKG_ROOT / "yellowstone_python" / "data" / "mammal_catalogue.json"),
    }
    from yellowstone_python.common.canopy_artifacts import CANOPY_RENDER_FILES, FOREST_FLOOR_FILE
    external_inputs.update({f"canopy_render/{name}": _external_entry(
        PKG_ROOT / "derived/lidar_canopy" / name) for name in CANOPY_RENDER_FILES})
    external_inputs["forest_floor"] = _external_entry(PKG_ROOT / "derived" / FOREST_FLOOR_FILE)
    for name in ("species.json", "sources.json"):
        external_inputs[f"motion_profiles/{name}"] = _external_entry(
            PKG_ROOT / "yellowstone_python/wildlife_motion/profiles" / name)
    lodgepole_root = world_root / "assets/imported/lodgepole"
    lodgepole_path = lodgepole_root / "lodgepole_metadata.json"
    if lodgepole_path.is_file():
        lodgepole = json.loads(lodgepole_path.read_text(encoding="utf-8"))
        for source_name, mip in lodgepole.get("cutout_mips", {}).items():
            for name, expected in ((mip["path"], mip["sha256"]),
                                   (source_name, mip["source_sha256"])):
                target = lodgepole_root / name
                if not target.resolve().is_relative_to(lodgepole_root.resolve()):
                    raise ValueError("lodgepole texture path must stay within its asset directory")
                entry = _external_entry(target)
                if not entry["exists"] or entry["sha256"] != expected:
                    raise ValueError(f"lodgepole texture differs from its metadata: {name}")
                external_inputs[f"lodgepole_texture/{name}"] = entry
        if lodgepole.get("architecture_library_sha256"):
            entry = _external_entry(lodgepole_root / "architecture_library.json")
            if entry.get("sha256") != lodgepole["architecture_library_sha256"]:
                raise ValueError("lodgepole architecture differs from its metadata")
            external_inputs["tree_architecture_library"] = entry
    motion_path = world_root / "data/wildlife_motion_assets.json"
    if motion_path.is_file():
        motion = json.loads(motion_path.read_text(encoding="utf-8"))
        for asset in motion.get("assets", []):
            relative = Path(asset["path"])
            target = world_root / relative
            if relative.is_absolute() or not target.resolve().is_relative_to(world_root.resolve()):
                raise ValueError("wildlife asset path must stay within the world")
            entry = _external_entry(target)
            if not entry["exists"] or entry["sha256"] != asset.get("sha256"):
                raise ValueError(f"wildlife asset differs from its manifest: {relative}")
            external_inputs[f"wildlife_asset/{relative.as_posix()}"] = entry

    deps = {"ecosystem.json": sha256_file(eco_path),
            "ecosystem_role": eco_role,
            "ecosystem_path": str(eco_path),
            "world.json": sha256_file(world_root / "data" / "world.json"),
            "placements.json": sha256_file(world_root / "data" / "placements.json"),
            "species_catalogue.json": sha256_file(
                world_root / "data" / "species_catalogue.json"),
            "terrain.f32": sha256_file(world_root / "data" / "terrain.f32"),
            "terrain": {"path": str(world_root / "data" / "terrain.f32"),
                        "sha256": sha256_file(
                            world_root / "data" / "terrain.f32")},
            "external_inputs": external_inputs,
            "external_inputs_sha256": sha256_json(external_inputs),
            "code": code_hash.hexdigest()[:16],
            "code_hash_source": code_hash_source,
            "code_rev": code_rev,
            "code_rev_source": code_rev_source,
            "config": sha256_json(cfg)}

    try:
        from yellowstone_python.validation.terrain import (DEFAULT_MAX_M, DEFAULT_MIN_M,
                                                          guard_terrain)
        kwargs = {
            "expect_sha256": deps["terrain.f32"],
            "min_m": DEFAULT_MIN_M, "max_m": DEFAULT_MAX_M,
        }
        import inspect as _inspect
        sig = _inspect.signature(guard_terrain)
        if "datum_status" in sig.parameters:
            kwargs["datum_status"] = "NAVD88 meters (USGS 3DEP)"
        if "require_datum" in sig.parameters:
            kwargs["require_datum"] = False
        terrain_report = guard_terrain(
            world_root / "data" / "terrain.f32", **kwargs)
    except ImportError:
        terrain_report = {"schema": "yellowstone.terrain_guard.v1",
                          "passed": False,
                          "guards": [{"name": "import", "passed": False,
                                      "detail": ("terrain guard not "
                                                 "importable from validation.terrain")}]}
    deps["terrain_guard"] = terrain_report
    critical_names = {"size", "grid", "finite", "range", "hash",
                      "terrain-readable", "import"}
    critical_failures = [
        g.get("detail", g.get("name", "?"))
        for g in terrain_report.get("guards", [])
        if not g.get("passed") and g.get("name") in critical_names]
    if critical_failures:
        raise ValueError(
            "terrain guard failed: " + "; ".join(critical_failures))
    advisory_failures = [
        f"{g.get('name')}: {g.get('detail', '?')}"
        for g in terrain_report.get("guards", [])
        if not g.get("passed") and g.get("name") not in critical_names]
    deps["terrain_guard_advisories"] = advisory_failures

    tfns = terrain_fns(load_terrain(str(world_root / "data" / "terrain.f32")))
    return baseline, world, deps, tfns
