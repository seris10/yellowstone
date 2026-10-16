"""CLI: build outflow temperature and mat state outputs into a directory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from yellowstone_python.common.io import write_json_atomic

ROOT = Path(__file__).resolve().parents[1]
import numpy as np  # noqa: E402

import yellowstone_python.thermal_features.microbial_mats as microbial_mats  # noqa: E402
import yellowstone_python.thermal_features.outflow_network as outflow_network  # noqa: E402
import yellowstone_python.thermal_features.outflow_thermal as outflow_thermal  # noqa: E402
from yellowstone_python.river.surface_flux import BudgetParams, MetState

from yellowstone_python.common.units import us_gpm_to_m3s
NPS_SPRING_DISCHARGES_M3_S = {
    "grand_prismatic": us_gpm_to_m3s(560.0),
    "excelsior": us_gpm_to_m3s(4000.0),
    "turquoise": 0.01,
    "opal": 0.01,
    "pool_1034_0": us_gpm_to_m3s(560.0),
    "pool_1030_0": us_gpm_to_m3s(4000.0),
    "pool_1028_0": 0.01,
    "pool_1029_0": 0.01,
}
NPS_SPRING_DISCHARGE_SOURCES = {
    "grand_prismatic": ("authored from a repeated 560 gal/min estimate in"
                        " popular references; NPS places page lists no"
                        " discharge value"),
    "excelsior": ("NPS places page Excelsior Geyser Crater (> 4,000 gal/min)"
                  " verified at nps.gov/places/000/excelsior-geyser-crater.htm"),
    "turquoise": "authored small-pool proxy 0.01 m3/s",
    "opal": "authored small-pool proxy 0.01 m3/s",
    "pool_1034_0": "same as grand_prismatic",
    "pool_1030_0": "same as excelsior",
    "pool_1028_0": "same as turquoise",
    "pool_1029_0": "same as opal",
}
NPS_SPRING_DISCHARGE_STATUS = {
    "grand_prismatic": "authored",
    "excelsior": "literature",
    "turquoise": "authored",
    "opal": "authored",
    "pool_1034_0": "authored",
    "pool_1030_0": "literature",
    "pool_1028_0": "authored",
    "pool_1029_0": "authored",
}
DEFAULT_SOURCE_TEMPERATURES_C = {
    "pool_1030_0": 88.7,
    "pool_1034_0": 70.0,
    "pool_1028_0": 62.0,
    "pool_1029_0": 60.0,
    "excelsior": 88.7,
    "grand_prismatic": 70.0,
    "turquoise": 62.0,
    "opal": 60.0,
}
DEFAULT_SOURCE_TEMPERATURE_STATUS = {
    "pool_1030_0": "literature",
    "pool_1034_0": "authored_within_literature_range",
    "pool_1028_0": "authored",
    "pool_1029_0": "authored",
}
DEFAULT_SOURCE_TEMPERATURE_SOURCES = {
    "pool_1030_0": ("Excelsior Geyser outflow 88.7 C, USGS Open-File Report"
                    " 2010-1192 sample 07WA148 (2007-09-19)"),
    "pool_1034_0": ("Grand Prismatic pool temperature 63-74 C in Nugent, Shaw,"
                    " Vollmer (2015) Appl. Opt. 54(4) B128; 70 C is the"
                    " midpoint used as the source temperature"),
    "pool_1028_0": ("Turquoise Pool authored source temperature 62 C above"
                    " the cyanobacteria lower edge"),
    "pool_1029_0": ("Opal Pool authored source temperature 60 C above the"
                    " cyanobacteria lower edge"),
}
from yellowstone_python.common.site import (SITE_LAT_DEG as SITE_LATITUDE_DEG,
                                           SITE_LON_DEG as SITE_LONGITUDE_DEG)
SITE_ALTITUDE_M = 2216.0


from yellowstone_python.common.io import load_json as _load_json


def _parse_met(section: dict) -> MetState:
    return MetState(
        air_c=float(section["air_c"]),
        rh=float(section["rh"]),
        wind_mps=float(section["wind_mps"]),
        shortwave_w_m2=float(section["shortwave_w_m2"]),
        cloud=float(section["cloud"]),
    )


def _resolve_raster_record(entry) -> dict:
    """Normalize a raster entry to a dict with path/dtype/sha256/shape."""
    if isinstance(entry, str):
        return {"path": entry}
    if isinstance(entry, dict):
        if "path" not in entry:
            raise ValueError("raster record missing path")
        return entry
    raise ValueError("raster record must be a string path or dict")


def _load_raster(entry, base_dir: Path, expected_dtype: str) -> np.ndarray:
    """Load one raster from a string path or a record dict with verification."""
    import hashlib
    record = _resolve_raster_record(entry)
    file_path = base_dir / record["path"]
    dtype = record.get("dtype", expected_dtype)
    if dtype != expected_dtype:
        raise ValueError(
            f"raster {record['path']} dtype {dtype} does not match expected"
            f" {expected_dtype}")
    data = file_path.read_bytes()
    declared_sha = record.get("sha256")
    if declared_sha:
        actual_sha = hashlib.sha256(data).hexdigest()
        if actual_sha != declared_sha:
            raise ValueError(
                f"raster {record['path']} sha256 mismatch:"
                f" declared {declared_sha} vs computed {actual_sha}")
    arr = np.frombuffer(data, dtype=dtype)
    shape = record.get("shape")
    if shape:
        shape_tuple = tuple(int(v) for v in shape)
        if arr.size != shape_tuple[0] * shape_tuple[1]:
            raise ValueError(
                f"raster {record['path']} size {arr.size} does not match"
                f" declared shape {shape_tuple}")
        arr = arr.reshape(shape_tuple)
    else:
        side = outflow_thermal.CORE_GRID_SIZE
        if arr.size != side * side:
            raise ValueError(
                f"raster {record['path']} size {arr.size} does not match"
                f" the default core-grid shape ({side}, {side})")
        arr = arr.reshape(side, side)
    return arr


def _load_network_rasters(network: dict, base_dir: Path) -> dict | None:
    """Load spring_index, flow_length_m, and flow_fraction rasters."""
    section = network.get("rasters")
    if not isinstance(section, dict):
        return None
    for required in ("spring_index", "flow_length_m", "flow_fraction"):
        if required not in section:
            return None
    return {
        "spring_index": _load_raster(
            section["spring_index"], base_dir, "<i2"),
        "flow_length_m": _load_raster(
            section["flow_length_m"], base_dir, "<f4"),
        "flow_fraction": _load_raster(
            section["flow_fraction"], base_dir, "<f4"),
    }


def _default_source_temperature(pool_id: str) -> float | None:
    """Return the authored or sourced source temperature for a known pool, else None."""
    return DEFAULT_SOURCE_TEMPERATURES_C.get(pool_id)


def _build_wp_a_vent_injections(springs_data: list,
                                network_springs: list,
                                discharges: dict,
                                spring_temps: dict
                                ) -> list[tuple[int, int, float, float]]:
    """Build vent injections at WP-A's rim cells for the energy sweep."""
    name_to_pool_id = {s.get("name"): s["pool_id"] for s in network_springs}
    name_to_source_id = {s.get("name"): s.get("source_id")
                         for s in network_springs}
    out: list[tuple[int, int, float, float]] = []
    for spring in springs_data:
        pool_id = (spring.get("pool_id")
                   or name_to_pool_id.get(spring.get("name")))
        if pool_id is None:
            continue
        q_total = float(discharges.get(pool_id, 0.0))
        t_vent = spring_temps.get(pool_id)
        if q_total <= 0.0 or t_vent is None:
            continue
        for (j, i, w) in spring["rim_cells"]:
            out.append((int(j), int(i),
                        float(q_total) * float(w),
                        float(t_vent)))
    _ = name_to_source_id
    return out


def _build_vent_injections(network: dict,
                           discharges: dict,
                           spring_temps: dict
                           ) -> list[tuple[int, int, float, float]]:
    """Injection list for graph_energy_sweep: (j, i, Q_at_cell, T_vent)."""
    out: list[tuple[int, int, float, float]] = []
    pool_id_by_index: dict[int, str] = {}
    springs_list = network.get("springs", [])
    for i, spring in enumerate(springs_list):
        pool_id_by_index[int(spring.get("index", i))] = spring["pool_id"]
    for seg in network.get("segments", []):
        if seg.get("upstream_id") is not None:
            continue
        s_idx = int(seg["spring_index"])
        pool_id = pool_id_by_index.get(s_idx)
        if pool_id is None:
            continue
        q_total = float(discharges.get(pool_id, 0.0))
        t_vent = spring_temps.get(pool_id)
        if q_total <= 0.0 or t_vent is None:
            continue
        q_here = q_total * float(seg.get("flow_fraction", 1.0))
        xz = seg["points_xz"][0]
        x = float(xz[0])
        z = float(xz[1])
        import math
        i_grid = int(math.floor((x + outflow_thermal.CORE_HALF_M)
                                / outflow_thermal.CORE_CELL_M))
        j_grid = int(math.floor((z + outflow_thermal.CORE_HALF_M)
                                / outflow_thermal.CORE_CELL_M))
        if (0 <= i_grid < outflow_thermal.CORE_GRID_SIZE
                and 0 <= j_grid < outflow_thermal.CORE_GRID_SIZE):
            out.append((j_grid, i_grid, q_here, float(t_vent)))
    return out


def _per_spring_summary(network: dict,
                        network_rasters: dict | None,
                        temperature_raster: np.ndarray,
                        mat_state: "microbial_mats.MatState",
                        spring_temps_used: dict) -> dict:
    """Wet-cell count, temperature min/median/max, class areas per spring."""
    rows = []
    springs = network.get("springs", [])
    legend_name = {int(e["class_id"]): e["name"]
                   for e in microbial_mats.COMMUNITY_LEGEND}
    if network_rasters is not None and "spring_index" in network_rasters:
        spring_index_r = network_rasters["spring_index"]
    else:
        spring_index_r = None
    for s_idx, spring in enumerate(springs):
        pool_id = spring.get("pool_id", f"spring_{s_idx}")
        row: dict = {
            "pool_id": pool_id,
            "name": spring.get("name"),
            "spring_index": s_idx,
            "source_temperature_c": spring_temps_used.get(pool_id),
        }
        if spring_index_r is None:
            rows.append(row)
            continue
        mask = (spring_index_r == s_idx) & np.isfinite(temperature_raster)
        count = int(mask.sum())
        row["wet_cell_count"] = count
        if count > 0:
            temps = temperature_raster[mask]
            row["temperature_c"] = {
                "min": float(np.nanmin(temps)),
                "median": float(np.nanmedian(temps)),
                "max": float(np.nanmax(temps)),
            }
            class_counts: dict = {}
            classes = mat_state.community_class[mask]
            for cls_id in np.unique(classes):
                name = legend_name.get(int(cls_id), f"class_{int(cls_id)}")
                class_counts[name] = int((classes == cls_id).sum())
            row["class_areas_m2"] = class_counts
            if "flow_length_m" in (network_rasters or {}):
                flow_len = network_rasters["flow_length_m"][mask]
                order = np.argsort(flow_len)
                row["flow_length_bins_m"] = [
                    float(np.nanmin(flow_len)),
                    float(np.nanmedian(flow_len)),
                    float(np.nanmax(flow_len)),
                ]
                temps_sorted = temps[order]
                n = len(temps_sorted)
                if n >= 3:
                    bins = np.array_split(temps_sorted, 3)
                    row["temperature_sequence_from_rim"] = [
                        float(np.nanmedian(b)) for b in bins]
                    row["temperature_descends_from_rim"] = (
                        row["temperature_sequence_from_rim"][0]
                        >= row["temperature_sequence_from_rim"][-1])
        rows.append(row)
    return {"springs": rows}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network", required=True,
                        help="outflow_network.json path")
    parser.add_argument("--forcing", required=True,
                        help="json with met, spring_temps_c, discharges_m3_s, "
                             "date_utc, daily_cloud_fraction")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--pool-shells", default=None,
                        help="optional pool_shells.json to produce ramps")
    parser.add_argument("--ph", type=float, default=8.0)
    parser.add_argument("--dt-days", type=float, default=1.0)
    parser.add_argument("--manning-n", type=float,
                        default=outflow_thermal.DEFAULT_MANNING_N)
    parser.add_argument("--default-discharges", action="store_true",
                        help="apply NPS defaults to springs not in forcing")
    parser.add_argument("--default-source-temps", action="store_true",
                        help="apply sourced vent temperatures to springs not"
                             " in forcing")
    parser.add_argument("--dem", default=None,
                        help='path to the 1 m DEM for the graph energy sweep; when set, provides the per-cell path integration')
    parser.add_argument("--world-json", default=None,
                        help="world.json pool-polygon source for the strict"
                             " flow_fraction verification against WP-A")
    parser.add_argument("--spring-discharges", default=None,
                        help="spring_discharges.json from WP-A; applied as the"
                             " discharge for each spring in the network")
    parser.add_argument("--min-film-depth-m", type=float,
                        default=outflow_thermal.MIN_FILM_DEPTH_M_DEFAULT,
                        help="cells with a film thinner than this are dry")
    args = parser.parse_args(argv)

    network = _load_json(args.network)
    network_path = Path(args.network).resolve()
    forcing = _load_json(args.forcing)
    met = _parse_met(forcing["met"])
    forcing_discharges = {
        str(k): float(v)
        for k, v in forcing.get("discharges_m3_s", {}).items()
    }
    discharges = dict(forcing_discharges)
    if args.spring_discharges:
        wpa_discharges = _load_json(args.spring_discharges)
        for pid, entry in wpa_discharges.get("springs", {}).items():
            if pid not in discharges:
                discharges[pid] = float(entry["discharge_m3_s"])
    if args.default_discharges:
        for spring in network.get("springs", []):
            pid = spring.get("pool_id")
            if pid not in discharges and pid in NPS_SPRING_DISCHARGES_M3_S:
                discharges[pid] = NPS_SPRING_DISCHARGES_M3_S[pid]
    spring_temps = {str(k): float(v)
                    for k, v in forcing.get("spring_temps_c", {}).items()}
    if args.default_source_temps:
        for spring in network.get("springs", []):
            pid = spring.get("pool_id")
            default_t = _default_source_temperature(pid)
            if default_t is not None and pid not in spring_temps:
                spring_temps[pid] = default_t
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    network_rasters = outflow_thermal.load_network_rasters(
        network, network_path.parent)
    if args.dem is None:
        raise ValueError(
            "run_mat_model requires --dem; the accepted graph energy sweep"
            " needs the 1 m DEM and the WP-A world.json pool rings")
    if args.world_json is None:
        raise ValueError(
            "run_mat_model requires --world-json for the strict flow_fraction"
            " verification against WP-A's injection convention")
    dem = outflow_thermal.load_dem_core_tif(args.dem)
    world_data = _load_json(args.world_json)
    spring_names = {s.get("name") for s in network["springs"]}
    world_pools = [p for p in world_data.get("pools", [])
                   if p.get("name") in spring_names]
    graph_result = outflow_thermal.graph_sweep_outflow_temperature(
        network, network_rasters, dem, world_pools,
        discharges, spring_temps, met,
        manning_n=float(args.manning_n),
        min_film_depth_m=float(args.min_film_depth_m),
        forcing_epoch_utc=forcing.get("epoch_utc"),
    )
    outflow_thermal.write_outflow_temperature(
        graph_result["temperature"], graph_result["sidecar"],
        str(out / "outflow_temperature.f32"),
        str(out / "outflow_temperature.json"),
    )
    result = {"raster": graph_result["temperature"],
              "sidecar": graph_result["sidecar"]}

    daily_cloud = float(forcing.get("daily_cloud_fraction", met.cloud))
    insolation = microbial_mats.daily_mean_insolation_w_m2(
        forcing.get("date_utc", "2026-07-15"),
        latitude=forcing.get("latitude_deg", SITE_LATITUDE_DEG),
        longitude=forcing.get("longitude_deg", SITE_LONGITUDE_DEG),
        daily_cloud_fraction=daily_cloud,
        altitude_m=forcing.get("altitude_m", SITE_ALTITUDE_M),
    )
    daily_sw = insolation["all_sky_mean_w_m2"]

    mat = microbial_mats.build_mat_state(
        result["raster"],
        daily_mean_shortwave_w_m2=daily_sw,
        dt_days=float(args.dt_days), ph=float(args.ph),
    )
    sidecar = mat.to_sidecar(
        forcing_epoch_utc=forcing.get("epoch_utc"),
        daily_mean_shortwave_w_m2=daily_sw,
        daily_cloud_fraction=daily_cloud,
        ph=float(args.ph),
        insolation_detail=insolation,
    )
    microbial_mats.write_mat_state(mat, str(out), sidecar_extra=sidecar)
    microbial_mats.write_mat_pigment_png(
        mat, str(out / "mat_pigment.png"),
        legend_path=str(out / "mat_pigment.json"),
        season=forcing.get("season"),
    )

    summary = _per_spring_summary(network, network_rasters, result["raster"],
                                  mat, spring_temps)
    write_json_atomic(out / "mat_summary.json", summary, indent=2)

    if args.pool_shells:
        shells = _load_json(args.pool_shells)
        ramps_dir = out / "pool_ramps"
        ramps_dir.mkdir(parents=True, exist_ok=True)
        shell_list = shells if isinstance(shells, list) else shells.get(
            "pools", [])
        ramps = []
        for shell in shell_list:
            ramp = microbial_mats.pool_ramp(shell, ph=float(args.ph))
            pool_id = shell.get("id", "pool")
            png_path = ramps_dir / f"ramp_{pool_id}.png"
            microbial_mats.write_pool_ramp_png(ramp, str(png_path))
            json_path = ramps_dir / f"ramp_{pool_id}.json"
            write_json_atomic(json_path, ramp, indent=2)
            ramps.append(str(png_path))
        print(f"wrote {len(ramps)} pool ramps")
    print(f"wrote outputs to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
