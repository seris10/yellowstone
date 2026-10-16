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
     "description": "Geothermal heat, thermal pools, ground temperature, and hot-water outflow processes."},
    {"id": "river", "label": "Hydrosphere", "color": "#77b9e6", "x": 0, "y": 70, "radius": 195,
     "description": "Water and heat transport along the mapped Firehole channel, with prescribed inflows."},
    {"id": "land", "label": "Terrestrial biosphere", "color": "#8ed5aa", "x": -390, "y": 285, "radius": 174,
     "description": "Vegetation stocks, canopy structure, grazing, and mammal guild responses."},
    {"id": "aquatic", "label": "Aquatic biosphere", "color": "#e2b6d1", "x": 390, "y": 300, "radius": 190,
     "description": "Temperature, oxygen, food resources, and habitat suitability in the river."},
]
DOMAIN_SLUGS = {
    "atmosphere": "atmosphere", "snow": "cryosphere", "thermal": "geosphere",
    "river": "hydrosphere", "land": "terrestrial-biosphere", "aquatic": "aquatic-biosphere",
}
for domain in DOMAINS:
    domain["slug"] = DOMAIN_SLUGS[domain["id"]]

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
    "outflow food web": ("outflow", "aquatic", "Outflow food web"),
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
    if not all(name in manifest["output_artifact_hashes"] for name in ["world.runtime.json", "patch_state.json", "outflow_temperature.json", "ground_heat.json"]):
        return None
    world = checked_document(build, manifest, "world.runtime.json")
    patches = checked_document(build, manifest, "patch_state.json")
    thermal = checked_document(build, manifest, "outflow_temperature.json")
    heat = checked_document(build, manifest, "ground_heat.json")
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
        "heat": {"grid": heat["grid"], "parameters": heat["parameters"], "values": heat["values_w_m2"]},
    }


def ecological_snapshot(build: Path, manifest: dict, cells: list) -> dict | None:
    """Extract spatial diagnostics and water stocks with their integration windows."""
    result = {}
    hashes = manifest["output_artifact_hashes"]
    for name, key, field in [("river_oxygen.json", "oxygen", "do_mg_l_by_cell"),
                             ("periphyton.json", "periphyton", "biomass_mg_c_m2_by_cell")]:
        if name in hashes:
            doc = checked_document(build, manifest, name)
            result[key] = [doc[field].get(c["id"]) for c in cells]
            result[key + "_dt_s"] = doc.get("dt_s")
    if "season.json" in hashes:
        season = checked_document(build, manifest, "season.json")
        water = season["ledger"]
        result["water"] = {key: water[key] for key in ["initial_mm", "final_mm", "rain_mm", "accum_mm", "et_mm", "drainage_mm", "runoff_mm", "snow_export_mm", "water_residual_mm", "days", "modeled_patch_count"]}
        result["snow"] = [{"id": p["id"], "label": p["id"].replace("_", " ").title(), "snow_mm": p["snow_mm"], "snow_depth_m": p["snow_depth_m"]} for p in season["patches"]]
    if "patch_state.json" in hashes:
        patch = checked_document(build, manifest, "patch_state.json")
        result["patches"] = [{"id": p["id"], "label": p["id"].replace("_", " ").title(), "biomass": p["biomass"], "capacity": p["capacity"], "moisture": p["moisture"]} for p in patch["patches"]]
    if "aquatic_foodweb.json" in hashes:
        food = checked_document(build, manifest, "aquatic_foodweb.json")["foodweb"]
        result["foodweb_days"] = food["simulated_days"]
        result["trout"] = {key: food["trout"][key] for key in ["s_m", "temperature_c", "U", "feeding"]}
    return result or None


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


def analytics_snapshot(build: Path, manifest: dict, cells: list) -> dict | None:
    """Extract bounded scientific diagnostics for linked interactive views."""
    result = {}
    hashes = manifest["output_artifact_hashes"]
    if all(name in hashes for name in ["weather.json", "weather_snapshot.json"]):
        weather = checked_document(build, manifest, "weather_snapshot.json")
        trace = checked_document(build, manifest, "weather.json")["wind_trace_60s"]
        result["weather"] = {"initial": {key: weather["weather"][key] for key in ["air_temperature_c", "relative_humidity", "wind_speed_mps", "cloud_fraction"]},
                             "trace": [{"t": row["t"], "air": row["air_c"], "wind": math.hypot(row["wind_x"], row["wind_z"])} for row in trace],
                             "basis": "Authored diurnal forcing and seeded wind; no local meteorological observations."}
    if all(name in hashes for name in ["pools_state.json", "world.runtime.json"]):
        pools = checked_document(build, manifest, "pools_state.json")["pools"]
        world = checked_document(build, manifest, "world.runtime.json")
        thermal_ids = {p["id"] for p in world["pools"] if p.get("thermal")}
        result["pools"] = [{"label": p["name"].strip().title(), "center": p["t_center_c"], "edge": p["t_edge_c"]} for p in pools if p["id"] in thermal_ids and p["name"].strip()]
    if "river_shading.json" in hashes:
        shade = checked_document(build, manifest, "river_shading.json")
        result["shading"] = [shade["multiplier_by_cell"].get(c["id"]) for c in cells]
        result["shading_basis"] = shade["provenance"]["method"]
    if "steam_microclimate.json" in hashes:
        result["steam"] = {key: checked_document(build, manifest, "steam_microclimate.json")["report"][key] for key in ["delta_air_c", "downwind_air_c", "downwind_rh"]}
    if "evapotranspiration.json" in hashes:
        result["reference_et_mm_day"] = checked_document(build, manifest, "evapotranspiration.json")["et0_mm_d"]
    return result or None


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
    for name in ["river_oxygen.json", "periphyton.json", "season.json", "patch_state.json", "aquatic_foodweb.json",
                 "weather.json", "weather_snapshot.json", "pools_state.json", "river_shading.json",
                 "steam_microclimate.json", "evapotranspiration.json", "world.runtime.json", "outflow_temperature.json", "ground_heat.json"]:
        if name in manifest["output_artifact_hashes"]:
            checked_document(build, manifest, name)
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
    frames = [{"t": frame["t_s"], "temperature": frame["temperature_c"]}
              for frame in (source_frames[i] for i in chosen)]
    if any(len(frame["temperature"]) != len(cells) for frame in frames):
        raise ValueError("River frame and cell dimensions differ")
    temperature_values = (v for frame in source_frames for v in frame["temperature_c"] if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v))
    domain_min, domain_max = math.inf, -math.inf
    for value in temperature_values:
        domain_min, domain_max = min(domain_min, value), max(domain_max, value)
    return {
        "schema": "yellowstone.public.v1", "snapshot": manifest["build_id"],
        "run_mode": manifest["run_mode"], "epoch": config["simulation"]["start_utc"],
        "scientific_acceptance": "Field validation remains incomplete.",
        "domains": DOMAINS, "nodes": nodes, "edges": edges,
        "coverage": geography_snapshot(build, manifest), "ecology": ecological_snapshot(build, manifest, cells),
        "analytics": analytics_snapshot(build, manifest, cells),
        "river": {"length_m": replay["mapping"]["length_m"],
                  "temperature_domain": [domain_min, domain_max] if math.isfinite(domain_min) else None,
                  "preview": {"source_frames": len(source_frames), "display_frames": len(frames),
                              "reduction": "Every Nth saved frame and final frame; source numeric precision retained."},
                  "cells": [{"s": c["center_s_m"], "x": c["position_xyz"][0], "z": c["position_xyz"][2]}
                            for c in cells], "frames": frames,
                  "boundary_flow": config["hydro"]["boundary_m3s"],
                  "boundary_temperature": config["hydro"]["boundary_c"],
                  "geometry": "Mapped centerline; authored channel widths and depth estimates.",
                  "forcing": "Prescribed upstream discharge and temperature; authored meteorology and lateral sources."},
    }


def river_dataset(build: Path) -> dict:
    """Extract native river samples and support from the checked artifact."""
    manifest = read_json(build / "BUILD.json")
    replay = checked_document(build, manifest, "river_replay.json")["replay"]
    cells = [{"id": c["id"], "s": c["center_s_m"], "bounds_m": [c["start_s_m"], c["end_s_m"]],
              "x": c["position_xyz"][0], "z": c["position_xyz"][2], "river_id": c["river_id"],
              "width_m": c["width_m"], "depth_m": c["depth_m"]} for c in replay["cells"]]
    frames = [{"t": f["t_s"], "temperature": f["temperature_c"]} for f in replay["frames"]]
    if not cells or len({c["id"] for c in cells}) != len(cells):
        raise ValueError("Native river cell identities are invalid")
    for i, cell in enumerate(cells):
        lo, hi = cell["bounds_m"]
        if not (lo <= cell["s"] <= hi and lo < hi and (i == 0 or cell["s"] > cells[i - 1]["s"])):
            raise ValueError("Native river support is invalid")
    for i, frame in enumerate(frames):
        if len(frame["temperature"]) != len(cells):
            raise ValueError("Native river frame dimensions differ")
        if not math.isfinite(frame["t"]) or (i and frame["t"] <= frames[i - 1]["t"]):
            raise ValueError("Native river times must increase")
        if any(v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)) for v in frame["temperature"]):
            raise ValueError("Native river temperature is invalid")
    if not frames:
        raise ValueError("Native river frames are unavailable")
    return {"schema": "yellowstone.river.v1", "snapshot": manifest["build_id"],
            "source_sha256": manifest["output_artifact_hashes"]["river_replay.json"],
            "run_mode": manifest["run_mode"], "epoch": manifest["config"]["simulation"]["start_utc"],
            "river": {"cells": cells, "frames": frames, "length_m": replay["mapping"]["length_m"]},
            "support": {"space": "Finite-volume cell bounds along horizontal channel chainage.",
                        "time": "Instantaneous saved states at elapsed seconds from the UTC start.",
                        "display": "Piecewise constant cells; nearest-sample time display regions. No interpolation.",
                        "uncertainty": "Unknown; no uncertainty interval supplied.", "units": "C",
                        "coordinates": "Local meters: x east, z south; y up.",
                        "geometry": "Mapped centerline; authored widths and submerged depth estimates."},
            "sources": [{"id": c["source_id"], "cell_id": c["receiving_cell_id"], "s_m": c["s_m"],
                         "flow_m3_s": c["ecosystem_flow_m3_s"], "temperature_c": c["ecosystem_entry_c"]}
                        for c in replay.get("source_connections", [])]}


def attach_river_dataset(snapshot: dict, dataset: dict) -> tuple[str, bytes]:
    """Bind the public catalog to the exact exported dataset bytes."""
    payload = (json.dumps(dataset, separators=(",", ":"), allow_nan=False) + "\n").encode()
    sha = hashlib.sha256(payload).hexdigest()
    path = f"data/river-{sha}.json"
    snapshot["datasets"] = {"river": {"url": "/dashboard/" + path, "sha256": sha,
                                      "source_sha256": dataset["source_sha256"],
                                      "cells": len(dataset["river"]["cells"]),
                                      "frames": len(dataset["river"]["frames"]), "bytes": len(payload)}}
    return path, payload


def public_worker(destination: Path) -> None:
    """Generate the request allowlist from approved staged files."""
    paths = []
    for file in sorted((destination / "dashboard").rglob("*")):
        if file.is_file():
            path = "/" + file.relative_to(destination).as_posix()
            paths.append(path)
            if path.endswith("/index.html"):
                paths.append(path[:-10])
    worker = (HERE / "src/worker.js").read_text().replace("/* PUBLIC_PATHS */ []", json.dumps(paths))
    (destination / "_worker.js").write_text(worker)


def package_site(destination: Path, snapshot: dict, datasets: dict | None = None) -> None:
    """Stage the public assets and explicit unavailable routes."""
    if destination.exists() and any(destination.iterdir()):
        raise ValueError("Site destination must be empty")
    page = destination / "dashboard"
    page.mkdir(parents=True)
    template = (HERE / "src/index.html").read_text()
    routes = [("", "overview", "Ecosystem explorer", ""), ("systems", "systems", "Earth systems", ""),
              ("results", "results", "Model results", ""), ("methods", "methods", "Science and scope", ""),
              ("analyze", "analyze", "Earth systems analysis", "")]
    routes.extend((f"systems/{domain['slug']}", "systems", domain["label"], domain["id"]) for domain in DOMAINS)
    for route, identity, title, domain in routes:
        target = page / route
        target.mkdir(exist_ok=True)
        html = template.replace('<body data-page="overview"', f'<body data-page="{identity}"')
        if domain:
            html = html.replace(f'data-page="{identity}">', f'data-page="{identity}" data-domain="{domain}">', 1)
        html = html.replace("Yellowstone | Ecosystem explorer", f"{title} | Yellowstone")
        for selected, section in [("systems", "system-view"), ("results", "river-view")]:
            if identity == selected:
                html = html.replace(f'<section id="{section}" hidden', f'<section id="{section}"')
        if identity == "methods":
            html = html.replace('<section id="methods-view" class="science-page" hidden',
                                '<section id="methods-view" class="science-page"')
        (target / "index.html").write_text(html)
    for name in ["explorer.css", "explorer.js", "coverage.js", "science.js", "workspace.css", "workspace.js", "workspace-model.js",
                 "data-model.js", "workbench.js", "workbench.css", "analysis.js", "analysis.css",
                 "systems-model.js", "systems-workbench.js", "systems-workbench.css"]:
        shutil.copyfile(HERE / "src" / name, page / name)
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
    for name, payload in (datasets or {}).items():
        target = page / name
        if not target.resolve().is_relative_to((page / "data").resolve()):
            raise ValueError("Dataset path is outside the public data directory")
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(payload)
    public_worker(destination)


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
    heat = checked_document(build, manifest, "ground_heat.json")
    values = np.asarray(heat["values_w_m2"]).reshape(heat["grid"]["nz"], heat["grid"]["nx"])
    colors = np.zeros((*values.shape, 4), dtype="uint8")
    colors[:] = [90, 135, 190, 30]
    colors[values >= heat["parameters"]["apron_w_m2"]] = [240, 160, 68, 145]
    colors[values >= heat["parameters"]["pool_w_m2"]] = [240, 84, 68, 210]
    colors[~np.isfinite(values)] = [0, 0, 0, 0]
    Image.fromarray(colors).save(destination / "ground-heat.png")
    shutil.copyfile(HERE / "assets/overlook.png", destination / "landscape.png")


def bundled_inputs(directory: Path = HERE) -> tuple[dict, dict]:
    """Verify the bundled public inputs and their catalog identities."""
    manifest = read_json(directory / "input-manifest.json")
    if manifest.get("schema") != "yellowstone.public-inputs.v1":
        raise ValueError("Unsupported public input manifest")
    for name, expected in manifest["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or Path(name).parts[0] not in {"data", "assets"}:
            raise ValueError("Public input is outside the bundle")
        if digest(path) != expected:
            raise ValueError(f"Public input hash mismatch: {name}")
    snapshot = read_json(directory / "data/snapshot.json")
    if snapshot.get("schema") != "yellowstone.public.v1" or snapshot["snapshot"] != manifest["snapshot"]:
        raise ValueError("Public snapshot identity differs from its manifest")
    datasets = {}
    catalog = [snapshot["datasets"]["river"], *snapshot["datasets"]["systems"]]
    for descriptor in catalog:
        url = descriptor["url"]
        if not url.startswith("/dashboard/data/") or Path(url).name != url.removeprefix("/dashboard/data/"):
            raise ValueError("Dataset path is outside the public data directory")
        name = "data/" + Path(url).name
        if manifest["files"].get(name) != descriptor["sha256"]:
            raise ValueError("Dataset catalog hash differs from the input manifest")
        payload = (directory / name).read_bytes()
        document = json.loads(payload)
        if document["snapshot"] != snapshot["snapshot"] or len(payload) != descriptor["bytes"]:
            raise ValueError("Dataset catalog identity or byte count differs")
        datasets[name] = payload
    expected = {"data/snapshot.json", "assets/terrain.png", "assets/ground-heat.png", "assets/overlook.png", *datasets}
    if set(manifest["files"]) != expected:
        raise ValueError("Public input manifest has missing or unlisted inputs")
    return snapshot, datasets


def build_bundled(destination: Path, directory: Path = HERE) -> dict:
    """Package the verified saved public data without a running model."""
    snapshot, datasets = bundled_inputs(directory)
    package_site(destination, snapshot, datasets)
    for source, name in [("terrain.png", "terrain.png"), ("ground-heat.png", "ground-heat.png"), ("overlook.png", "landscape.png")]:
        shutil.copyfile(directory / "assets" / source, destination / "dashboard" / name)
    public_worker(destination)
    return snapshot


def main() -> None:
    """Build from bundled public inputs, or extract an explicit checked build."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.build:
        snapshot = public_snapshot(args.build)
        path, payload = attach_river_dataset(snapshot, river_dataset(args.build))
        from domain_data import export_systems, attach_system_datasets
        datasets = {path: payload}
        datasets.update(attach_system_datasets(snapshot, export_systems(args.build)))
        package_site(args.out, snapshot, datasets)
        map_assets(args.build, args.out / "dashboard")
        public_worker(args.out)
    else:
        snapshot = build_bundled(args.out)
    print(f"Public snapshot {snapshot['snapshot']}: {len(snapshot['nodes'])} components, {len(snapshot['edges'])} relationships")


if __name__ == "__main__":
    main()
