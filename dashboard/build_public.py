"""Public scientific model snapshot and static site packaging."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DOMAINS = [
    {"id": "atmosphere", "label": "Atmosphere", "color": "#8dcaca", "x": 0, "y": -380, "radius": 158,
     "description": "Meteorological forcing, surface energy exchange, and steam microclimate."},
    {"id": "snow", "label": "Cryosphere & soil", "color": "#b8b4e9", "x": -390, "y": -155, "radius": 158,
     "description": "Snow accumulation and melt, soil storage, and evapotranspiration."},
    {"id": "thermal", "label": "Geosphere", "color": "#efa774", "x": 390, "y": -155, "radius": 174,
     "description": "Pool temperature, ground heat, thermal plumes, and outflow ecology."},
    {"id": "river", "label": "Hydrosphere", "color": "#77b9e6", "x": 0, "y": 70, "radius": 195,
     "description": "Water and heat transport along the mapped Firehole channel, with prescribed inflows."},
    {"id": "land", "label": "Terrestrial biosphere", "color": "#b4cb83", "x": -390, "y": 285, "radius": 174,
     "description": "Vegetation stocks, canopy structure, grazing, and mammal guild responses."},
    {"id": "aquatic", "label": "Aquatic biosphere", "color": "#e2b6d1", "x": 390, "y": 300, "radius": 190,
     "description": "Temperature, oxygen, food resources, and habitat suitability in the river."},
]

COMPONENTS = {
    "six-reach mixing chain": ("mixing", "river", "Reach mixing"),
    "1-D advection-dispersion replay": ("transport", "river", "Heat transport"),
    "surface heat exchange": ("surface", "atmosphere", "Surface heat exchange"),
    "2-D plume field": ("plume", "thermal", "Thermal plume"),
    "pool radial temperature": ("pool", "thermal", "Pool temperature"),
    "patch biomass": ("vegetation", "land", "Vegetation"),
    "insect compartments": ("insects", "aquatic", "Insect life stages"),
    "trout suitability and refuge": ("fish", "aquatic", "Trout habitat"),
    "grazer routing": ("grazers", "land", "Grazing routes"),
    "replay solute transport": ("solutes", "river", "Solute transport"),
    "river dissolved oxygen": ("oxygen", "aquatic", "Dissolved oxygen"),
    "periphyton biomass": ("periphyton", "aquatic", "Periphyton"),
    "river shading": ("shading", "river", "Canopy & terrain shade"),
    "ground heat flux and soil temperature": ("ground", "thermal", "Ground heat"),
    "reference evapotranspiration": ("et", "snow", "Reference ET"),
    "piscivore predation": ("predation", "aquatic", "Piscivores"),
    "aerial insectivores": ("aerial", "aquatic", "Aerial insectivores"),
    "outflow food web": ("outflow", "thermal", "Outflow food web"),
    "steam microclimate plume": ("steam", "atmosphere", "Steam microclimate"),
    "invertebrate taxa foodweb": ("taxa", "aquatic", "Benthic food web"),
    "snow and soil water": ("snow", "snow", "Snow & soil storage"),
    "mammal guild ecology": ("mammals", "land", "Mammal guilds"),
}

EXCHANGES = {
    "boundary_water": ("boundary", "transport"),
    "boundary_heat": ("boundary", "transport"),
    "lateral_water": ("tributaries", "transport"),
    "lateral_heat": ("tributaries", "transport"),
    "outlet_export": ("transport", "outlet"),
    "surface_newton": ("surface", "transport"),
    "surface_budget": ("surface", "transport"),
    "landscape_temperature": ("transport", "fish"),
    "snow_runoff_discharge": ("snow", "transport"),
    "shear_disturbance": ("transport", "insects"),
    "solute_habitat_multiplier": ("solutes", "fish"),
    "oxygen_do_fish_multiplier": ("oxygen", "fish"),
    "oxygen_do_insect_multiplier": ("oxygen", "taxa"),
    "periphyton_oxygen_metabolism": ("periphyton", "oxygen"),
    "shortwave_shading_multiplier": ("shading", "surface"),
    "piscivore_predation": ("predation", "fish"),
    "aerial_insectivore_consumption": ("insects", "aerial"),
    "ground_heat_snow_melt": ("ground", "snow"),
    "ground_heat_tree_suitability": ("ground", "vegetation"),
    "snow_depth_grazer_cost": ("snow", "grazers"),
    "warm_ground_grazer_refuge": ("ground", "grazers"),
    "grazer_nutrient_return": ("grazers", "vegetation"),
    "grazer_trampling_crust": ("grazers", "pool"),
    "reference_et_soil_water": ("snow", "et"),
    "steam_plume_microclimate": ("pool", "steam"),
    "outflow_foodweb_mat": ("mat", "outflow"),
    "hyporheic_exchange": ("transport", "hyporheic"),
}


def read_json(path: Path) -> dict:
    """Read a JSON document."""
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    """Return the SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_document(build: Path, manifest: dict, name: str) -> dict:
    """Read one artifact after verifying its build-bound digest."""
    if digest(build / name) != manifest["output_artifact_hashes"][name]:
        raise ValueError(f"Artifact hash mismatch: {name}")
    return read_json(build / name)


def geography_snapshot(build: Path, manifest: dict) -> dict | None:
    """Extract mapped features and authored habitat patches."""
    if "world.runtime.json" not in manifest["output_artifact_hashes"]:
        return None
    world = checked_document(build, manifest, "world.runtime.json")
    patches = checked_document(build, manifest, "patch_state.json")
    thermal = checked_document(build, manifest, "outflow_temperature.json")
    def line(points):
        indexes = sorted(set(range(0, len(points), 5)) | {len(points) - 1})
        return [[round(points[i][0], 2), round(points[i][2], 2)] for i in indexes]
    return {
        "extent": world["georeference"]["extent"], "crs": world["georeference"]["crs"],
        "grid_step_m": world["georeference"]["grid_step_m"],
        "vertical_datum": world["georeference"]["vertical_datum"],
        "rivers": [{"id": r["id"], "name": r.get("name", "Waterway").strip().title(), "points": line(r["points"])} for r in world["rivers"]],
        "routes": [{"id": r["id"], "name": r.get("name", "Path").strip().title(), "kind": r["kind"], "points": line(r["points"])} for r in world["routes"]],
        "pools": [{"id": p["id"], "name": p.get("name", "").strip().title() or "Mapped water body",
                   "thermal": p.get("thermal", False), "area_m2": p["area_m2"], "ring": p["ring"],
                   "center": [p["center"][0], p["center"][2]], "temperature_c": p.get("temperature_c")}
                  for p in world["pools"]],
        "anchors": [{"label": a["title"], "position": [a["position"][0], a["position"][2]]} for a in world["anchors"]],
        "patches": [{"label": p["id"].replace("_", " ").title(), "center": p["center_xz"], "radius": p["radius_m"]}
                    for p in patches["patches"]],
        "thermal_extent": {key: thermal["grid"][key] for key in ["nx", "nz", "cell_size_m", "origin_xz_m"]},
    }


def ecological_snapshot(build: Path, manifest: dict, cells: list) -> dict | None:
    """Extract spatial diagnostics and water stocks with their integration windows."""
    if "river_oxygen.json" not in manifest["output_artifact_hashes"]:
        return None
    oxygen_doc = checked_document(build, manifest, "river_oxygen.json")
    algae_doc = checked_document(build, manifest, "periphyton.json")
    oxygen = oxygen_doc["do_mg_l_by_cell"]
    algae = algae_doc["biomass_mg_c_m2_by_cell"]
    season = checked_document(build, manifest, "season.json")
    patch = checked_document(build, manifest, "patch_state.json")
    food = checked_document(build, manifest, "aquatic_foodweb.json")["foodweb"]
    water = season["ledger"]
    return {"oxygen": [oxygen.get(c["id"]) for c in cells], "periphyton": [algae.get(c["id"]) for c in cells],
            "oxygen_dt_s": oxygen_doc.get("dt_s"), "periphyton_dt_s": algae_doc.get("dt_s"),
            "foodweb_days": food["simulated_days"],
            "trout": {key: food["trout"][key] for key in ["s_m", "temperature_c", "U", "feeding"]},
            "water": {key: water[key] for key in ["initial_mm", "final_mm", "rain_mm", "accum_mm", "et_mm", "drainage_mm", "runoff_mm", "snow_export_mm", "water_residual_mm", "days", "modeled_patch_count"]},
            "patches": [{"label": p["id"].replace("_", " ").title(), "biomass": p["biomass"], "capacity": p["capacity"], "moisture": p["moisture"]} for p in patch["patches"]],
            "snow": [{"label": p["id"].replace("_", " ").title(), "snow_mm": p["snow_mm"], "snow_depth_m": p["snow_depth_m"]} for p in season["patches"]]}


def selected_build(root: Path) -> Path:
    """Resolve the world-selected generation to its checked model build."""
    world = root / "yellowstone_midway"
    pointer = read_json(world / "data/release.json")
    manifest = (world / pointer["manifest"]).resolve()
    if not manifest.is_relative_to((world / "data/releases").resolve()):
        raise ValueError("Release manifest is outside the generation directory")
    if digest(manifest) != pointer["sha256"]:
        raise ValueError("Release manifest hash mismatch")
    release = read_json(manifest)
    built = manifest.parent / "BUILD.json"
    if digest(built) != release["artifacts"]["BUILD.json"]["sha256"]:
        raise ValueError("Released build manifest hash mismatch")
    build = root / "yellowstone_python/derived" / read_json(built)["build_id"]
    if digest(build / "BUILD.json") != digest(built):
        raise ValueError("Selected generation and model build differ")
    return build


def public_snapshot(build: Path, root: Path = ROOT) -> dict:
    """Extract scientific fields from hash-verified model outputs."""
    manifest = read_json(build / "BUILD.json")
    if manifest.get("checks_passed") is not True:
        raise ValueError("Public snapshot requires a checked build")
    names = ["equations.json", "coupling.json", "river_replay.json", "CHECKS.json", "claims.json"]
    documents = {}
    for name in names:
        if digest(build / name) != manifest["output_artifact_hashes"][name]:
            raise ValueError(f"Artifact hash mismatch: {name}")
        documents[name] = read_json(build / name)
    if documents["CHECKS.json"].get("passed") is not True:
        raise ValueError("Model checks failed")
    nodes = []
    for component in documents["equations.json"]["components"]:
        if component["component"] not in COMPONENTS:
            continue
        identity, domain, label = COMPONENTS[component["component"]]
        module = component["module"].split()[0]
        source = root / "yellowstone_python/yellowstone_python" / module
        if not source.is_file():
            raise ValueError(f"Component source missing: {module}")
        nodes.append({"id": identity, "domain": domain, "label": label, "kind": "process",
                      **{key: component[key] for key in ["equations", "assumptions", "limits", "units", "variables", "model_level"]}})
    config = manifest["config"]
    nodes.extend([
        {"id": "boundary", "domain": "river", "label": "Upstream boundary", "kind": "prescribed",
         "model_level": "Prescribed upstream discharge and temperature.",
         "assumptions": "Upstream forcing is specified by the scenario.",
         "limits": "Discharge and upstream temperature are prescribed inputs.", "units": "m3/s; C"},
        {"id": "tributaries", "domain": "river", "label": "Lateral inflows", "kind": "prescribed",
         "model_level": "Water and heat enter at specified connection locations.",
         "assumptions": "Source temperatures and discharges are authored.",
         "limits": "Local source hydrographs are unmeasured.", "units": "m3/s; C"},
        {"id": "outlet", "domain": "river", "label": "Downstream export", "kind": "boundary",
         "model_level": "Water and thermal energy leave the modeled channel.",
         "assumptions": "Advective outflow; zero dispersive boundary flux.",
         "limits": "The downstream river is outside the modeled reach.", "units": "m3/s; J/s"},
    ])
    content = read_json(HERE / "public-content.json")
    for item in content["supporting_nodes"]:
        if item["artifact"] not in manifest["output_artifact_hashes"]:
            continue
        checked_document(build, manifest, item["artifact"])
        nodes.append({key: value for key, value in item.items() if key != "artifact"})
    for node in nodes:
        node.update(content["processes"].get(node["id"], {}))
        node["implementation"] = "implemented"
    implemented_ids = {node["id"] for node in nodes}
    for item in content["research"]:
        if item["target"] not in implemented_ids:
            continue
        nodes.append({**{k: item[k] for k in ["id", "domain", "label", "summary"]},
                      "kind": "research", "implementation": "research", "display": "none", "formulation": "research extension",
                      "model_level": item["summary"], "assumptions": "Absent from the selected model formulation.",
                      "limits": "No results for this extension are represented in this snapshot.", "units": "Not applicable"})
    ids = {node["id"] for node in nodes}
    edges = []
    for item in documents["coupling.json"]["exchanges"]:
        if item["exchange_id"] not in EXCHANGES:
            continue
        source, target = EXCHANGES[item["exchange_id"]]
        if source not in ids or target not in ids:
            raise ValueError("Exchange endpoint is absent")
        condition = ""
        if item["exchange_id"] == "snow_runoff_discharge" and not config["hydro"]["catchment"].get("area_m2"):
            condition = "Requires a configured contributing catchment area; inactive in this scenario."
        if item["exchange_id"] == "surface_budget" and not config["replay"].get("energy_budget"):
            condition = "Explicit surface budget is inactive; this scenario uses Newton exchange."
        if item["exchange_id"] == "surface_newton" and config["replay"].get("energy_budget"):
            condition = "Newton exchange is inactive; this scenario uses an explicit surface budget."
        edges.append({"id": item["exchange_id"], "from": source, "to": target,
                      "label": item["quantity"], "units": item["units"], "method": item["method"],
                      "kind": item["kind"], "conservation": item["conservation"],
                      "spatial_support": item["spatial_support"], "temporal_support": item["temporal_support"],
                      "condition": condition, "summary": content["exchanges"].get(item["exchange_id"], "Heat exchanges between channel water and a represented storage zone."),
                      "bidirectional": item["exchange_id"] == "hyporheic_exchange", "research": False})
    for item in content["supporting_edges"]:
        if item["from"] in ids and item["to"] in ids:
            edges.append({**item, "kind": "model dependency", "conservation": "mapped", "condition": "",
                          "spatial_support": "model field or patch", "temporal_support": "declared model interval", "research": False})
    for item in content["research"]:
        if item["id"] not in ids:
            continue
        edges.append({"id": "research_" + item["id"], "from": item["id"], "to": item["target"],
                      "label": item["label"], "summary": item["summary"], "research": True,
                      "condition": "Research extension; absent from the selected model.", "units": "Not applicable",
                      "method": "Research concept", "kind": "proposed dependency", "conservation": "not assessed",
                      "spatial_support": "Not implemented", "temporal_support": "Not implemented"})
    replay = documents["river_replay.json"]["replay"]
    cells = replay["cells"]
    source_frames = replay["frames"]
    step = max(1, math.ceil((len(source_frames) - 1) / 120))
    chosen = sorted(set(range(0, len(source_frames), step)) | {len(source_frames) - 1})
    frames = [{"t": frame["t_s"], "temperature": [round(v, 4) for v in frame["temperature_c"]]}
              for frame in (source_frames[i] for i in chosen)]
    if any(len(frame["temperature"]) != len(cells) for frame in frames):
        raise ValueError("River frame and cell dimensions differ")
    return {
        "schema": "yellowstone.public.v1", "snapshot": manifest["build_id"],
        "run_mode": manifest["run_mode"], "epoch": config["simulation"]["start_utc"],
        "scientific_acceptance": "Field validation remains incomplete.",
        "domains": DOMAINS, "nodes": nodes, "edges": edges,
        "coverage": geography_snapshot(build, manifest), "ecology": ecological_snapshot(build, manifest, cells),
        "river": {"length_m": replay["mapping"]["length_m"],
                  "cells": [{"s": round(c["center_s_m"], 2), "x": c["position_xyz"][0], "z": c["position_xyz"][2]}
                            for c in cells], "frames": frames,
                  "boundary_flow": config["hydro"]["boundary_m3s"],
                  "boundary_temperature": config["hydro"]["boundary_c"],
                  "geometry": "Mapped centerline; authored channel widths and depth estimates.",
                  "forcing": "Prescribed upstream discharge and temperature; authored meteorology and lateral sources."},
    }


def package_site(destination: Path, snapshot: dict) -> None:
    """Stage the public assets and explicit unavailable routes."""
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Site destination must be empty")
    page = destination / "dashboard"
    page.mkdir(parents=True)
    template = (HERE / "public/index.html").read_text()
    for route, identity, title in [("", "overview", "Geographic overview"), ("systems", "systems", "Earth systems"),
                                    ("results", "results", "Model results"), ("methods", "methods", "Science and scope")]:
        target = page / route
        target.mkdir(exist_ok=True)
        (target / "index.html").write_text(template.replace('<body data-page="overview"', f'<body data-page="{identity}"')
                                          .replace("Yellowstone | Ecosystem explorer", f"{title} | Yellowstone"))
    for name in ["explorer.css", "explorer.js", "coverage.js", "science.js"]:
        shutil.copyfile(HERE / "public" / name, page / name)
    (page / "snapshot.json").write_text(json.dumps(snapshot, separators=(",", ":"), allow_nan=False) + "\n")
    (destination / "_redirects").write_text("/ /dashboard/ 302\n")
    (destination / "404.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><title>Page unavailable</title>'
        '<h1>Page unavailable</h1><p><a href="/dashboard/">Yellowstone ecosystem explorer</a></p></html>\n')
    (destination / "_headers").write_text(
        "/*\n  X-Content-Type-Options: nosniff\n  Referrer-Policy: strict-origin-when-cross-origin\n"
        "  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'\n"
        "/dashboard/*\n  Cache-Control: public, no-cache, no-transform\n")
    shutil.copyfile(HERE / "public/worker.js", destination / "_worker.js")


def map_assets(build: Path, destination: Path, root: Path = ROOT) -> None:
    """Render the checked terrain grid as neutral shaded relief."""
    import numpy as np
    from PIL import Image
    manifest = read_json(build / "BUILD.json")
    source = root / "yellowstone_midway/data/terrain.f32"
    if digest(source) != manifest["input_datasets"]["terrain"]["sha256"]:
        raise ValueError("Terrain input hash differs from selected build")
    world = checked_document(build, manifest, "world.runtime.json")
    size = world["georeference"]["grid_size"]
    terrain = np.fromfile(source, dtype="<f4").reshape(size, size)
    dz, dx = np.gradient(terrain, world["georeference"]["grid_step_m"])
    relief = np.clip(((-.5 * dx - .5 * dz + .707) / np.sqrt(dx * dx + dz * dz + 1)) * 85 + 12, 9, 100).astype("uint8")
    Image.fromarray(relief).save(destination / "terrain.png")
    shutil.copyfile(root / "docs/portfolio-overlook.png", destination / "landscape.png")


def main() -> None:
    """Build a public site from the world-selected model generation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    build = args.build or selected_build(ROOT)
    snapshot = public_snapshot(build)
    package_site(args.out, snapshot)
    map_assets(build, args.out / "dashboard")
    print(f"Public snapshot {snapshot['snapshot']}: {len(snapshot['nodes'])} components, {len(snapshot['edges'])} relationships")


if __name__ == "__main__":
    main()
