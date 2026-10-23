"""Build-bound Midway browser data exports."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(path, expected):
    if digest(path) != expected:
        raise ValueError(f"Source hash mismatch: {path.name}")
    return json.loads(path.read_text())


def finite(values):
    array = np.asarray(values, dtype=float)
    if not np.isfinite(array).all():
        raise ValueError("Nonfinite data or missing terrain support")
    return array


def write_json(path, value):
    path.write_text(json.dumps(value, separators=(",", ":"), allow_nan=False))


def export(root, build_id, out):
    build = root / "yellowstone_python/derived" / build_id
    manifest = json.loads((build / "BUILD.json").read_text())
    if manifest["build_id"] != build_id:
        raise ValueError("Build identity mismatch")
    used = {}

    def document(name):
        path = build / name
        value = checked(path, manifest["output_artifact_hashes"][name])
        used[str(path.relative_to(root))] = digest(path)
        return value

    world = document("world.runtime.json")
    replay = document("river_replay.json")["replay"]
    census = document("census.json")["payload"]
    pools = document("pools_state.json")
    geo = world["georeference"]
    if geo != replay["georeference"] or geo["crs"] != "EPSG:32612":
        raise ValueError("Coordinate contracts differ")
    refs = root / "yellowstone_midway/references"
    source = json.loads((refs / "terrain_source.json").read_text())
    raw = refs / "terrain_source.f32"
    if digest(raw) != source["sha256"]:
        raise ValueError("Terrain source hash mismatch")
    if source["origin_utm_m"] != geo["origin"][:2]:
        raise ValueError("Terrain origin differs from mapped vectors")
    broad = finite(np.fromfile(raw, dtype="<f4").reshape(source["height"], source["width"]))
    provenance = json.loads((refs / "dem_1m_core.tif.provenance.json").read_text())
    core_path = refs / "dem_1m_core.tif"
    if digest(core_path) != provenance["sha256"]:
        raise ValueError("Core DEM hash mismatch")
    core = finite(np.asarray(Image.open(core_path)))
    if core.shape != (1280, 1280):
        raise ValueError("Unexpected core dimensions")
    cells = [{k: c[k] for k in ("id", "position_xyz", "river_id", "start_s_m", "end_s_m", "center_s_m", "width_m", "depth_m")} for c in replay["cells"]]
    if len({c["id"] for c in cells}) != len(cells):
        raise ValueError("Duplicate cell identity")
    frames = [{"t": f["t_s"], "values": f["temperature_c"]} for f in replay["frames"]]
    for i, frame in enumerate(frames):
        finite(frame["values"])
        if len(frame["values"]) != len(cells) or (i and frame["t"] <= frames[i - 1]["t"]):
            raise ValueError("Invalid replay dimensions or time ordering")
    used[str(raw.relative_to(root))] = digest(raw)
    used[str(core_path.relative_to(root))] = digest(core_path)
    for name in ("terrain_source.json", "dem_1m_core.tif.provenance.json", "geodata_manifest.json"):
        used[str((refs / name).relative_to(root))] = digest(refs / name)
    used[str((build / "BUILD.json").relative_to(root))] = digest(build / "BUILD.json")
    output = out / "data"
    output.mkdir(parents=True, exist_ok=True)
    # Samples retain their original raster centers and source values.
    broad_view = broad.astype("<f4")
    core_view = core[::2, ::2].astype("<f4")
    broad_view.tofile(output / "terrain-full.f32")
    core_view.tofile(output / "terrain-core.f32")
    crown_fields = ["stable_id", "x", "z", "height_m", "crown_area_m2", "crown_r_m"]
    write_json(output / "crowns.json", {"fields": crown_fields, "rows": [[t[k] for k in crown_fields] for t in census["trees"]], "source": census["source"], "status": census["status"]})
    write_json(output / "replay.json", {"cells": cells, "frames": frames, "source_connections": replay.get("source_connections", [])})
    features = {
        "rivers": [{"id": r["id"], "name": r.get("name") or "Waterway", "points": r["points"]} for r in world["rivers"]],
        "routes": [{"id": r["id"], "name": r.get("name") or "Route", "kind": r["kind"], "points": r["points"]} for r in world["routes"]],
        "pools": [{k: p[k] for k in ("id", "name", "ring", "center_xz", "area_m2", "outline_basis", "t_center_c", "t_center_basis", "depth_center_basis")} for p in pools["pools"]],
        "anchors": world["anchors"],
    }
    write_json(output / "features.json", features)
    metadata = {
        "schema": "yellowstone.browser-explorer.v1", "build_id": build_id,
        "source_commit": manifest["code_commit"], "run_mode": manifest["run_mode"],
        "start_utc": manifest["config"]["simulation"]["start_utc"],
        "georeference": geo, "coordinate_contract": "x=E-E0; z=N0-N; y=H-2200; meters",
        "validation": "not_yet_accepted; saved illustrative output; no field forecast validation",
        "terrain": {
            "full": {"file": "terrain-full.f32", "n": int(broad_view.shape[0]), "start": [-2048, -2048], "spacing_m": 4, "source_spacing_m": 4, "support": "USGS 3DEP resampled source grid; every source sample retained", "acquired": "Source project 2020; full service export 2026", "limit": source["native_source_note"]},
            "core": {"file": "terrain-core.f32", "n": int(core_view.shape[0]), "start": [-639.5, -639.5], "spacing_m": 2, "source_spacing_m": 1, "support": "USGS QL1 1 m DEM; every second pixel center retained", "acquired": provenance["source_acquisition_window"], "limit": "Pixel centers span -639.5 to 638.5 m after display sampling. Terrain beneath water is not measured bathymetry."},
        },
        "crown_count": len(census["trees"]), "frame_count": len(frames), "cell_count": len(cells),
        "temperature_range_c": [float(np.min([f["values"] for f in frames])), float(np.max([f["values"] for f in frames]))],
        "sources": used,
        "assets": {p.name: {"sha256": digest(p), "bytes": p.stat().st_size} for p in sorted(output.iterdir()) if p.name != "manifest.json"},
    }
    write_json(output / "manifest.json", metadata)
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--build", required=True)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    result = export(args.root, args.build, args.out)
    print(json.dumps({k: result[k] for k in ("build_id", "crown_count", "frame_count", "cell_count", "temperature_range_c")}, indent=2))
