"""Render build operations."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import POOL_GRAND, Path, REACH_BRIDGE, REACH_EXCELSIOR, _find, plume_field, render_plume_png, write_sidecar

def render_all(res: dict, out: Path, deps: dict, world_root: Path) -> None:
    """Visualization + export: PNGs and JSON sidecars from simulated state."""
    from yellowstone_python.thermal_features.plume import plume_field, render_plume_png
    from yellowstone_python.thermal_features.pool_crust import render_apron_mask, render_apron_tiles, render_ramp
    from yellowstone_python.thermal_features.pool_crust import render_cross_section
    from yellowstone_python.aquatic.fish import render_refuge_map
    from yellowstone_python.land.grazers import render_tracks as render_grazer_tracks
    from yellowstone_python.land.snow_season import render_snow_map
    from yellowstone_python.land.vegetation import render_suitability_png
    from yellowstone_python.thermal_features.geochemistry import rules_doc as substrate_rules
    from yellowstone_python.common.canopy_artifacts import copy_render_canopy, copy_forest_floor

    canopy_metadata = deps.get("external_inputs", {}).get(
        "canopy_render/unresolved_render_canopy.json", {})
    if canopy_metadata.get("exists"):
        copy_render_canopy(Path(canopy_metadata["path"]).parent, out)
    floor_metadata = deps.get("external_inputs", {}).get("forest_floor", {})
    if floor_metadata.get("exists"):
        copy_forest_floor(Path(floor_metadata["path"]), out)

    river_state, shells = res["river_state"], res["shells"]
    render_refuge_map(river_state, res["wildlife2"],
                      str(out / "refuge_map.png"),
                      river_points=res["firehole_points"], shells=shells)
    render_grazer_tracks(res["wildlife3"], str(out / "grazer_tracks.png"))
    render_snow_map(shells, 256, str(out / "snow_map.png"),
                    snow_m=max((p.get("snow_depth_m", 0.0)
                                for p in res["patches2"]), default=0.0))
    exc = _find(river_state, "id", REACH_EXCELSIOR, "reach")
    river_ref = next(
        (r for r in river_state if r["id"] == REACH_BRIDGE),
        river_state[-1] if river_state else None)
    if river_ref is None:
        raise ValueError("river_state is empty; cannot render plume")
    field = plume_field(nx=128, nz=128, hot_c=float(exc["temperature_c"]),
                        river_c=float(river_ref["temperature_c"]))
    render_plume_png(field, 128, 128, str(out / "plume_map.png"))

    shells_doc = write_sidecar(
        out / "pool_shells.json", {"pool_shells": shells},
        sources=[{"file": "yellowstone_midway/data/world.json",
                  "sha256": deps["world.json"]}],
        params={"recipe": "RECIPES per pool name; depths/colors illustrative",
                "outline": "mapped water polygons preserved"},
        code_rev=deps["code_rev"])
    render_apron_mask(shells, 256, str(out / "apron_mask.png"))
    render_apron_tiles(shells, str(out / "apron_tiles"))
    rampdir = out / "pool_ramps"
    rampdir.mkdir(exist_ok=True)
    for s in shells:
        render_ramp(s, str(rampdir / f"{s['id']}.png"))
    gp = _find(shells, "id", POOL_GRAND, "pool shell")
    render_cross_section(gp, str(out / "pool_cross_section.png"))
    write_sidecar(out / "substrate_rules.json", substrate_rules(),
                  sources=[{"id": "NPS_G4",
                            "url": "https://www.nps.gov/yell/learn/nature/hydrothermal-features.htm"}],
                  params={"midway": "siliceous only; travertine refused"},
                  code_rev=deps["code_rev"])

    prop_cfg, patches0 = res["prop_cfg"], res["patches0"]
    cx0, cz0 = prop_cfg.get("center_xz", [-360, 260])
    _rr = float(prop_cfg.get("radius_m", 30))
    render_suitability_png(prop_cfg.get("guild", "lodgepole_pine"), 128,
                           str(out / "suitability_demo.png"),
                           bbox=(cx0 - _rr, cz0 - _rr, cx0 + _rr, cz0 + _rr),
                           terrain_fn=res["tfns"], patches=patches0,
                           shells=shells)
    return shells_doc
