"""Map the conservative thermal solver onto the saved Midway Firehole.

Requires the previously provided river_transport.py in the same directory.

Examples:
    python river_world.py --world world.json --ecosystem ecosystem.json \
        --out derived/firehole_control.json

    python river_world.py --world world.json --ecosystem ecosystem.json \
        --pulse-source excelsior_aggregate_outflow \
        --pulse-start 300 --pulse-end 900 --pulse-delta-c 18 \
        --out derived/firehole_pulse.json

The pulse changes temperature at the river-entry boundary. It is not a
simulation of the spring's underground plumbing or outflow cooling.

No source geography, placements, ecosystem configuration, or Godot scene
is overwritten.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from .river_transport import (
    RHO_CP_J_M3_K,
    Series,
    finite,
    make_replay,
    positive,
)
from .hydraulics import (
    DEFAULT_BANK_SLOPE_ZH,
    DEFAULT_MANNING_N,
    cell_hydraulics,
    thermal_inventory,
)

SCHEMA = "yellowstone.mapped_river_replay.v1"

# Explicit association between the ecosystem's aggregate thermal boundary
# and the representative authored channel used to locate its connection.
# This does not assert that this one branch carries the actual aggregate.
SOURCE_LINKS = {
    "excelsior_aggregate_outflow": "authored_excelsior_outflow_01",
}

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def parse_cross_sections(value: Any) -> dict[str, dict[str, Any]]:
    """Validate per-feature mean-depth profiles. Format: {feature_id: {"depth_m": positive float, "status": str}}. Unknown feature ids rejected. channel_geometry fields real_measurement_site and dem_cross_check_depth_m are accepted and preserved."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("cross_sections must be an object")
    profiles = {}
    for feature_id, record in value.items():
        if feature_id.startswith("_"):
            continue
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError("cross-section feature ids must be nonempty")
        if not isinstance(record, dict):
            raise ValueError(
                f"cross-section {feature_id!r} must be an object")
        unknown = set(record) - {"depth_m", "status", "source",
                                 "real_measurement_site",
                                 "dem_cross_check_depth_m"}
        if unknown:
            raise ValueError(
                f"cross-section {feature_id!r} has unknown keys: "
                f"{sorted(unknown)}")
        if "depth_m" not in record or "status" not in record:
            raise ValueError(
                f"cross-section {feature_id!r} requires depth_m + status")
        depth = positive(record["depth_m"], f"{feature_id} depth_m")
        status = record["status"]
        if not isinstance(status, str) or not status.strip():
            raise ValueError(
                f"cross-section {feature_id!r} status must be nonempty")
        source = record.get("source", "unspecified_treat_as_authored")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(
                f"cross-section {feature_id!r} source must be nonempty")
        profiles[feature_id] = {
            "depth_m": depth, "status": status.strip(),
            "source": source.strip(),
        }
        for opt in ("real_measurement_site", "dem_cross_check_depth_m"):
            if opt in record:
                profiles[feature_id][opt] = record[opt]
    return profiles

def feature_by_id(world: dict, feature_id: str) -> dict:
    matches = [
        feature for feature in world["rivers"]
        if feature["id"] == feature_id
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one river feature {feature_id!r}")
    return matches[0]

def parse_silica_obs(value: Any) -> dict[str, float]:
    """Observed dissolved SiO2 per river feature id, mg/L as SiO2."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("silica_obs must be an object")
    out = {}
    for feature_id, mg_L in value.items():
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError("silica feature ids must be nonempty")
        amount = finite(mg_L, f"silica {feature_id}")
        if amount <= 0.0:
            raise ValueError(f"silica {feature_id} must be > 0")
        out[feature_id] = amount
    return out

def parse_extra_sources(value: Any) -> list[dict[str, Any]]:
    """Provider laterals keyed by channel chainage, not ecosystem ids."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("extra_sources must be a list")
    records = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("extra_sources entries must be objects")
        source_id = entry.get("id")
        if not isinstance(source_id, str) or not source_id:
            raise ValueError("extra source id must be a nonempty string")
        location = finite(entry.get("s_m"), "extra source s_m")
        flow = finite(entry.get("flow_m3_s"), "extra source flow", 0.0)
        temperature = entry.get("temperature_c")
        Series.parse(temperature)
        status = entry.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError("extra source status must be nonempty")
        records.append({"id": source_id, "s_m": location,
                        "flow_m3_s": flow, "temperature_c": temperature,
                        "status": status.strip()})
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate extra source ids")
    return records

def parse_upstream_discharge(value: Any) -> dict[str, Any] | None:
    """Predicted upstream discharge series with bounds and provenance."""
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("upstream_discharge must be an object")
    required = ("t0_epoch_s", "dt_s", "discharge_m3_s",
                "discharge_lo_m3_s", "discharge_hi_m3_s", "coverage",
                "method", "status")
    for key in required:
        if key not in value:
            raise ValueError(f"upstream_discharge requires {key!r}")
    flows = [finite(v, "predicted discharge", 0.0)
             for v in value["discharge_m3_s"]]
    lo = [finite(v, "predicted discharge lo", 0.0)
          for v in value["discharge_lo_m3_s"]]
    hi = [finite(v, "predicted discharge hi", 0.0)
          for v in value["discharge_hi_m3_s"]]
    if not flows or not (len(flows) == len(lo) == len(hi)):
        raise ValueError("predicted discharge series must be nonempty "
                         "and equal length")
    for key in ("method", "status"):
        if not isinstance(value[key], str) or not value[key].strip():
            raise ValueError(f"upstream_discharge {key} must be nonempty")
    return {**value, "discharge_m3_s": flows,
            "discharge_lo_m3_s": lo, "discharge_hi_m3_s": hi}

def firehole_chain(world: dict) -> list[dict]:
    """Find a single directed chain using declared endpoint IDs.

    Do not infer direction from list order, velocity art parameters,
    latitude, or local changes in z.
    """
    features = [
        feature for feature in world["rivers"]
        if str(feature.get("name", "")).strip().upper()
        == "FIREHOLE RIVER"
    ]
    if not features:
        raise ValueError("no named Firehole features")

    if len({feature["id"] for feature in features}) != len(features):
        raise ValueError("duplicate Firehole feature ids")

    outgoing: dict[str, dict] = {}
    incoming: dict[str, dict] = {}

    for feature in features:
        nodes = feature.get("endpoint_node_ids", [])
        if len(nodes) != 2 or nodes[0] == nodes[1]:
            raise ValueError(
                f"{feature['id']}: two distinct directed endpoints required"
            )
        upstream, downstream = nodes
        if upstream in outgoing or downstream in incoming:
            raise ValueError(
                "branched Firehole topology is unsupported by the 1-D solver"
            )
        outgoing[upstream] = feature
        incoming[downstream] = feature

    starts = [node for node in outgoing if node not in incoming]
    if len(starts) != 1:
        raise ValueError("Firehole must have exactly one upstream boundary")

    result = []
    visited = set()
    node = starts[0]

    while node in outgoing:
        feature = outgoing[node]
        if feature["id"] in visited:
            raise ValueError("cycle in Firehole topology")
        visited.add(feature["id"])
        result.append(feature)
        node = feature["endpoint_node_ids"][1]

    if len(result) != len(features):
        raise ValueError("disconnected Firehole features")

    return result

class Channel:
    """Original vertices plus their downstream horizontal chainage."""

    def __init__(self, features: list[dict]) -> None:
        self.points: list[list[float]] = []
        self.s_m: list[float] = []
        self.features: dict[str, dict] = {}

        for feature in features:
            raw = feature["points"]
            if len(raw) < 2:
                raise ValueError(f"{feature['id']}: too few vertices")

            points = [
                [finite(value, "vertex coordinate") for value in point]
                for point in raw
            ]
            if any(len(point) != 3 for point in points):
                raise ValueError("river vertices must be [x, y, z]")

            width = positive(feature["width"], "channel width")

            if self.points:
                discrepancy = math.dist(self.points[-1], points[0])
                if discrepancy > 0.001:
                    raise ValueError(
                        f"{feature['id']}: declared junction has "
                        f"{discrepancy:.6f} m coordinate discrepancy"
                    )
                point_chainage = [self.s_m[-1]]
            else:
                self.points.append(points[0])
                self.s_m.append(0.0)
                point_chainage = [0.0]

            for previous, point in zip(points, points[1:]):
                distance = math.hypot(
                    point[0] - previous[0],
                    point[2] - previous[2],
                )
                if distance <= 0.0:
                    raise ValueError(
                        f"{feature['id']}: repeated horizontal vertex"
                    )
                chainage = self.s_m[-1] + distance
                self.points.append(point)
                self.s_m.append(chainage)
                point_chainage.append(chainage)

            self.features[feature["id"]] = {
                "id": feature["id"],
                "width_m": width,
                "points_xyz": points,
                "point_s_m": point_chainage,
                "start_s_m": point_chainage[0],
                "end_s_m": point_chainage[-1],
            }

        self.length_m = self.s_m[-1]
        self._feature_ends = [
            record["end_s_m"] for record in self.features.values()
        ]
        self._feature_records = list(self.features.values())

    def position_at(self, s_m: float) -> list[float]:
        s_m = finite(s_m, "chainage", 0.0)
        if s_m > self.length_m:
            raise ValueError("chainage outside channel")
        if s_m == self.length_m:
            return self.points[-1].copy()

        index = max(0, bisect_right(self.s_m, s_m) - 1)
        fraction = (
            (s_m - self.s_m[index])
            / (self.s_m[index + 1] - self.s_m[index])
        )
        return [
            a + fraction * (b - a)
            for a, b in zip(self.points[index], self.points[index + 1])
        ]

    def feature_at(self, s_m: float) -> dict:
        index = min(
            bisect_right(self._feature_ends, s_m),
            len(self._feature_records) - 1,
        )
        return self._feature_records[index]

    def chainage_at_z(self, z: float) -> float:
        """Translate a reach anchor, refusing ambiguous crossings. Exists for compatibility with the six-reach display."""
        z = finite(z, "legacy reach z")
        candidates = []

        for index, (a, b) in enumerate(zip(self.points, self.points[1:])):
            za, zb = a[2], b[2]
            if za == zb:
                if z == za:
                    raise ValueError(
                        f"legacy z={z} lies on a flat-z segment; "
                        "supply an explicit vertex anchor"
                    )
                continue

            fraction = (z - za) / (zb - za)
            if 0.0 <= fraction <= 1.0:
                candidates.append(
                    self.s_m[index]
                    + fraction * (self.s_m[index + 1] - self.s_m[index])
                )

        unique = []
        for candidate in sorted(candidates):
            if not unique or candidate - unique[-1] > 0.001:
                unique.append(candidate)

        if len(unique) != 1:
            raise ValueError(
                f"legacy z={z} has {len(unique)} channel crossings; "
                "supply an explicit vertex anchor"
            )
        return unique[0]

def source_connection(
    world: dict,
    channel: Channel,
    source: dict,
) -> dict:
    if source["id"] not in SOURCE_LINKS:
        raise ValueError(
            f"source {source['id']!r} lacks an explicit geometry association"
        )

    outlet = feature_by_id(world, SOURCE_LINKS[source["id"]])
    target_id = outlet["target_river_id"]

    if target_id not in channel.features:
        raise ValueError("thermal outlet targets a different water system")

    feature = channel.features[target_id]
    raw_index = outlet["target_vertex_index"]
    if isinstance(raw_index, bool) or int(raw_index) != raw_index:
        raise ValueError("target_vertex_index must be an integer")
    vertex_index = int(raw_index)
    if not 0 <= vertex_index < len(feature["points_xyz"]):
        raise ValueError("thermal target vertex outside feature")

    target = feature["points_xyz"][vertex_index]
    discrepancy = math.dist(outlet["points"][-1], target)
    if discrepancy > 0.001:
        raise ValueError(
            f"thermal outlet endpoint misses target by {discrepancy:.6f} m"
        )

    return {
        "source_id": source["id"],
        "outlet_feature_id": outlet["id"],
        "target_river_id": target_id,
        "target_vertex_index": vertex_index,
        "s_m": feature["point_s_m"][vertex_index],
        "position_xyz": target,
        "join_error_m": discrepancy,
        "ecosystem_flow_m3_s": source["flow_m3s"],
        "ecosystem_entry_c": source["temperature_c"],
        "world_outlet_flow_m3_s": outlet.get("flow_m3_s"),
        "world_outlet_temperature_c": outlet.get("temperature_c"),
        "authority": (
            "ecosystem values define river-entry forcing; "
            "world outlet defines connection geometry only"
        ),
    }

def cell_faces(
    length_m: float,
    required_faces: list[float],
    maximum_cell_m: float,
) -> list[float]:
    """Split at sources and feature boundaries, then subdivide.

    A source lies at the upstream face of its receiving cell, rather
    than being smeared over a legacy compartment.
    """
    maximum_cell_m = positive(maximum_cell_m, "maximum cell length")
    breaks = sorted(set([0.0, length_m, *required_faces]))

    if any(not 0.0 <= value <= length_m for value in breaks):
        raise ValueError("required face outside channel")

    result = [0.0]
    for start, finish in zip(breaks, breaks[1:]):
        distance = finish - start
        if distance < 1e-6:
            raise ValueError("required faces are too close")
        count = math.ceil(distance / maximum_cell_m)
        result.extend(
            start + distance * index / count
            for index in range(1, count + 1)
        )
        result[-1] = finish
    return result

def physical_weather(
    ecosystem: dict,
    duration_s: float,
    interval_s: float = 60.0,
) -> tuple[Series, list[dict]]:
    """Use the existing weather approximation on a physical clock.

    Air forcing is held constant over each interval. day_rate does not
    accelerate scientific forcing. This is not measured meteorology.
    lag_hours defaults to the microclimate air-curve lag so the solver and
    the mixing chain share one curve.
    """
    weather = ecosystem.get("weather", {})
    hour0 = finite(ecosystem.get("clock_hour", 16.2), "clock_hour")
    night = finite(weather.get("night_air_c", 7.0), "night air")
    warming = finite(weather.get("day_warming_c", 15.0), "day warming")
    lag = finite(weather.get("lag_hours", 3.0), "weather lag")
    wind = weather.get("wind_xz_mps", [1.8, 0.6])
    wx, wz = [finite(value, "base wind") for value in wind]
    gust = finite(weather.get("gust_mps", 0.45), "gust", 0.0)

    times = [
        index * interval_s
        for index in range(int(duration_s // interval_s) + 1)
    ]
    temperatures = []
    records = []

    for time_s in times:
        hour = (hour0 + time_s / 3600.0) % 24.0
        sun = max(0.0, math.sin((hour - 6.0 - lag) * math.pi / 12.0))
        air = night + warming * sun
        temperatures.append(air)
        records.append({
            "t_s": time_s,
            "hour": hour,
            "air_c": air,
            "wind_xz_mps": [
                wx + gust * math.sin(time_s / 61.0),
                wz + gust * math.cos(time_s / 87.0),
            ],
        })

    return Series(tuple(times), tuple(temperatures)), records

def energy_met_series(ecosystem: dict, duration_s: float,
                      interval_s: float = 60.0,
                      weather_records: list[dict] | None = None) -> dict:
    """Meteorological series for the explicit surface budget.

    Relative humidity and cloud are held constant (no met station data);
    wind speed reuses the physical_weather trace magnitude so both
    forcings share one wind history; shortwave is a synthetic diurnal
    curve scaled by sw_noon_w_m2. All labeled synthetic in the notes.
    """
    from .surface_flux import spec_from_series
    weather = ecosystem.get("weather", {})
    hour0 = finite(ecosystem.get("clock_hour", 16.2), "clock_hour")
    humidity = finite(weather.get("humidity", 0.45), "humidity")
    cloud = finite(weather.get("cloud", 0.16), "cloud")
    sw_noon = finite(weather.get("sw_noon_w_m2", 700.0),
                     "sw_noon_w_m2", 0.0)
    if weather_records is None:
        _, weather_records = physical_weather(ecosystem, duration_s,
                                              interval_s)
    times = [record["t_s"] for record in weather_records]
    winds = [math.hypot(record["wind_xz_mps"][0],
                        record["wind_xz_mps"][1])
             for record in weather_records]
    suns = []
    for time_s in times:
        hour = (hour0 + time_s / 3600.0) % 24.0
        sun = max(0.0, math.sin((hour - 6.0) * math.pi / 12.0))
        suns.append(sw_noon * sun ** 1.2)
    return spec_from_series(
        Series(tuple(times), tuple([humidity] * len(times))),
        Series(tuple(times), tuple(winds)),
        Series(tuple(times), tuple(suns)),
        Series(tuple(times), tuple([cloud] * len(times))),
    )

def build_mapped_replay(
    world: dict,
    ecosystem: dict,
    *,
    duration_s: float = 7200.0,
    maximum_cell_m: float = 20.0,
    depth_m: float = 1.1,
    dispersion_m2_s: float = 1.0,
    exchange_w_m2_k: float = 12.0,
    dt_s: float = 2.0,
    sample_s: float = 10.0,
    pulse_source: str = "",
    pulse_start_s: float = 300.0,
    pulse_end_s: float = 900.0,
    pulse_delta_c: float = 18.0,
    reach_anchors: dict[str, dict] | None = None,
    cross_sections: dict[str, dict] | None = None,
    energy_budget: bool = False,
    bank_slope_zh: float = DEFAULT_BANK_SLOPE_ZH,
    manning_n: float = DEFAULT_MANNING_N,
    upstream_discharge: dict[str, Any] | None = None,
    extra_sources: list[dict[str, Any]] | None = None,
    silica_obs: dict[str, float] | None = None,
) -> dict[str, Any]:
    duration_s = positive(duration_s, "duration")
    depth_m = positive(depth_m, "assumed mean depth")
    dispersion_m2_s = finite(dispersion_m2_s, "dispersion", 0.0)
    exchange_w_m2_k = finite(exchange_w_m2_k, "exchange", 0.0)
    bank_slope_zh = finite(bank_slope_zh, "bank_slope_zh", 0.0)
    manning_n = positive(manning_n, "manning_n")
    profiles = parse_cross_sections(cross_sections)
    prediction = parse_upstream_discharge(upstream_discharge)
    extra = parse_extra_sources(extra_sources)
    silica = parse_silica_obs(silica_obs)

    channel = Channel(firehole_chain(world))
    known_features = set(channel.features)
    unknown = set(profiles) - known_features
    if unknown:
        raise ValueError(
            f"cross-sections name unknown features: {sorted(unknown)}")

    sources = [
        source
        for reach in ecosystem["river_reaches"]
        for source in reach.get("lateral_sources", [])
    ]
    if len({source["id"] for source in sources}) != len(sources):
        raise ValueError("duplicate ecosystem lateral source ids")
    if {record["id"] for record in extra} & {source["id"] for source in sources}:
        raise ValueError("extra source ids collide with ecosystem sources")
    for record in extra:
        if not 0.0 <= record["s_m"] < channel.length_m:
            raise ValueError("extra source chainage outside channel")

    connections = [
        source_connection(world, channel, source)
        for source in sources
    ]
    if pulse_source and pulse_source not in {
        source["id"] for source in sources
    }:
        raise ValueError("pulse source does not exist")

    if pulse_source:
        pulse_start_s = positive(pulse_start_s, "pulse start")
        pulse_end_s = positive(pulse_end_s, "pulse end")
        pulse_delta_c = finite(pulse_delta_c, "pulse temperature change")
        if not pulse_start_s < pulse_end_s < duration_s:
            raise ValueError("require 0 < pulse start < pulse end < duration")

    required_faces = [
        record["end_s_m"]
        for record in channel.features.values()
    ] + [connection["s_m"] for connection in connections
         ] + [record["s_m"] for record in extra]

    faces = cell_faces(
        channel.length_m, required_faces, maximum_cell_m
    )

    cells = []
    mapping = []
    # Reach-averaged grade per river feature (total drop / total length):
    # cell-scale elevation differences are vertex/DEM noise, not energy
    # slope. Standard open-channel practice uses the reach grade.
    feature_slopes: dict[str, float | None] = {}
    for feature in channel.features.values():
        pts = feature["points_xyz"]
        total = sum(
            math.hypot(q[0] - p[0], q[2] - p[2])
            for p, q in zip(pts, pts[1:]))
        drop = pts[0][1] - pts[-1][1]
        feature_slopes[feature["id"]] = (
            drop / total if total > 0 else None)
    cell_slopes: list[float | None] = []
    for index, (start, finish) in enumerate(zip(faces, faces[1:])):
        center = (start + finish) / 2.0
        feature = channel.feature_at(center)
        width = feature["width_m"]
        profile = profiles.get(feature["id"])
        if profile is None:
            cell_depth = depth_m
            depth_status = "assumed_rectangular_depth_no_bathymetry"
            depth_source = "default_depth_m_argument"
            geometry_status = (
                "mapped_centerline_authored_width_assumed_rectangular_depth"
            )
        else:
            cell_depth = profile["depth_m"]
            depth_status = profile["status"]
            depth_source = profile["source"]
            geometry_status = (
                "mapped_centerline_authored_width_profile_depth"
            )
        position = channel.position_at(center)
        a, b = channel.position_at(start), channel.position_at(finish)

        direction_length = math.hypot(b[0] - a[0], b[2] - a[2])
        if direction_length <= 0.0:
            raise ValueError("cell chord has no horizontal direction")
        # Reach-averaged grade (see above); flat or adverse reaches stay
        # None: Manning is reported undefined, never replaced.
        cell_slopes.append(feature_slopes[feature["id"]])

        cell_id = f"firehole_cell_{index:05d}"
        cells.append({
            "id": cell_id,
            "length_m": finish - start,
            "width_m": width,
            "volume_m3": (finish - start) * width * cell_depth,
            "initial_c": ecosystem["boundary_c"],
            "dispersion_m2_s": dispersion_m2_s,
            "exchange_w_m2_k": exchange_w_m2_k,
            "geometry_status": geometry_status,
        })
        mapping.append({
            "id": cell_id,
            "river_id": feature["id"],
            "depth_m": cell_depth,
            "depth_status": depth_status,
            "depth_source": depth_source,
            "position_xyz": position,
            "downstream_unit_xz": [
                (b[0] - a[0]) / direction_length,
                (b[2] - a[2]) / direction_length,
            ],
        })

    solver_sources = []
    for source, connection in zip(sources, connections):
        location = connection["s_m"]
        if location >= channel.length_m:
            raise ValueError("lateral source cannot enter after last cell")
        index = bisect_right(faces, location) - 1
        temperature = finite(source["temperature_c"], "entry temperature")
        forcing: Any = temperature

        if source["id"] == pulse_source:
            forcing = {
                "times_s": [0.0, pulse_start_s, pulse_end_s],
                "values": [
                    temperature,
                    temperature + pulse_delta_c,
                    temperature,
                ],
            }

        solver_sources.append({
            "id": source["id"],
            "cell_id": cells[index]["id"],
            "flow_m3_s": finite(source["flow_m3s"], "lateral flow", 0.0),
            "temperature_c": forcing,
            "status": "illustrative_river_entry_forcing_not_measured",
        })
        connection["receiving_cell_id"] = cells[index]["id"]

    for record in extra:
        index = bisect_right(faces, record["s_m"]) - 1
        solver_sources.append({
            "id": record["id"],
            "cell_id": cells[index]["id"],
            "flow_m3_s": record["flow_m3_s"],
            "temperature_c": record["temperature_c"],
            "status": record["status"],
        })

    boundary_m3_s = finite(ecosystem["boundary_m3s"], "boundary flow")
    upstream_note: dict[str, Any] | str = (
        "ecosystem prescribed boundary discharge")
    if prediction is not None:
        flows = prediction["discharge_m3_s"]
        boundary_m3_s = math.fsum(flows) / len(flows)
        upstream_note = {
            "method": prediction["method"],
            "status": prediction["status"],
            "coverage": prediction.get("coverage"),
            "n_steps": len(flows),
            "applied_boundary_m3_s": boundary_m3_s,
            "series_retained": ("window mean drives the constant-discharge "
                                "solver; full series kept for provenance"),
            "prediction": prediction,
        }

    air, weather_records = physical_weather(ecosystem, duration_s)
    budget_spec = (energy_met_series(ecosystem, duration_s,
                                     weather_records=weather_records)
                   if energy_budget else None)
    config = {
        "status": "mapped_illustrative_model_not_calibrated",
        "boundary_m3_s": boundary_m3_s,
        "boundary_c": ecosystem["boundary_c"],
        "air_c": {
            "times_s": list(air.times_s),
            "values": list(air.values),
        },
        "duration_s": duration_s,
        "dt_s": dt_s,
        "sample_s": sample_s,
        "initialize_steady": True,
        "cells": cells,
        "sources": solver_sources,
        "parameter_notes": {
            "initial_condition": ("Calculated steady state at t=0 forcing."),
            "width": "Authored width from world.json; not surveyed banks.",
            "depth_m": depth_m,
            "depth_status": (
                "Default assumed rectangular mean depth; no bathymetry. "
                "Per-feature cross_sections override it where supplied."
            ),
            "cross_sections": profiles or (
                "none supplied; every cell uses the default depth_m"
            ),
            "dispersion_m2_s": dispersion_m2_s,
            "dispersion_status": "Illustrative coefficient, not fitted.",
            "exchange_w_m2_k": exchange_w_m2_k,
            "exchange_status": (
                "Explicit shortwave/longwave/sensible/latent budget; "
                "illustrative coefficients, synthetic diurnal met."
                if energy_budget else
                "Illustrative Newton coefficient; not inherited or "
                "calibrated from legacy cooling_seconds."
            ),
            "surface_budget": (
                "SW/LW/sensible/latent from weather-config humidity, "
                "trace wind magnitude, synthetic diurnal shortwave; "
                "per-cell Newton coefficients ignored (no double count)."
                if energy_budget else
                "Not used; lumped Newton exchange only."
            ),
            "weather": (
                "Existing diurnal approximation, sampled every 60 physical "
                "seconds; not date-specific meteorology."
            ),
            "omitted_tributaries": (
                "Only explicitly configured ecosystem lateral flows are "
                "included. Mapped streams do not supply invented discharge."
            ),
            "upstream_discharge": upstream_note,
            "extra_sources": (
                f"{len(extra)} provider laterals at mapped chainages; "
                f"status carried per source"
                if extra else "none supplied"),
            "pulse": (
                "Synthetic river-entry temperature intervention."
                if pulse_source else "No intervention."
            ),
            "hydraulics": {
                "bank_slope_zh": bank_slope_zh,
                "bank_slope_status": (
                    "authored_illustrative_not_measured; override with "
                    "--bank-slope when surveyed valley profiles exist"),
                "manning_n": manning_n,
                "manning_status": (
                    "authored_illustrative_not_calibrated; override with "
                    "--manning-n when gauge-fitted"),
                "slope": ("reach-averaged grade per river feature (total "
                          "elevation drop / total length); cell-scale drops "
                          "are vertex noise, not energy slope; flat/adverse "
                          "grades leave Manning undefined"),
                "solver_volumes": (
                    "rectangular length*width*depth (baseline preserved); "
                    "trapezoid area/volume reported per cell as diagnostic "
                    "with rectangular_bias_pct"),
                "dispersion_context": (
                    "Fischer D per cell is an order-of-magnitude check on "
                    "the illustrative dispersion_m2_s, not a fitted value"),
            },
        },
    }
    if budget_spec is not None:
        config["surface_budget"] = budget_spec

    document = make_replay(config)
    document["schema"] = SCHEMA
    for record, spatial in zip(document["cells"], mapping):
        record.update(spatial)

    # Trapezoidal hydraulics diagnostics (additive; solver volumes and
    # temperatures above are unchanged). Discharge per cell is the
    # downstream face flow, matching representative_velocity_m_s.
    face_flows = document["face_flow_m3_s"]
    total_travel_s = 0.0
    manning_ratios: list[float] = []
    fischer_values: list[float] = []
    flat_cells = 0
    for i, record in enumerate(document["cells"]):
        q_out = face_flows[i + 1]
        hydro = cell_hydraulics(
            length_m=record["length_m"],
            top_width_m=record["width_m"],
            depth_m=record["depth_m"],
            discharge_m3_s=q_out,
            slope=cell_slopes[i],
            bank_slope_zh=bank_slope_zh,
            manning_n=manning_n,
        )
        record["hydraulics"] = hydro
        if hydro["travel_time_s"] is not None:
            total_travel_s += hydro["travel_time_s"]
        if hydro["manning_consistency_ratio"] is not None:
            manning_ratios.append(hydro["manning_consistency_ratio"])
        if hydro["fischer_dispersion_m2_s"] is not None:
            fischer_values.append(hydro["fischer_dispersion_m2_s"])
        if "flat_or_adverse_grade_manning_undefined" in hydro["warnings"]:
            flat_cells += 1
    document["hydraulics_summary"] = {
        "status": "diagnostic_not_calibrated",
        "n_cells": len(document["cells"]),
        "n_flat_or_adverse_grade_cells": flat_cells,
        "total_travel_time_s": total_travel_s,
        "manning_consistency_ratio_median": (
            sorted(manning_ratios)[len(manning_ratios) // 2]
            if manning_ratios else None),
        "manning_consistency_ratio_range": (
            [min(manning_ratios), max(manning_ratios)]
            if manning_ratios else None),
        "fischer_dispersion_m2_s_median": (
            sorted(fischer_values)[len(fischer_values) // 2]
            if fischer_values else None),
        "solver_dispersion_m2_s": dispersion_m2_s,
        "thermal_inventory": thermal_inventory(solver_sources),
    }

    if silica:
        from ..geochemistry import diagnose_replay_frame
        unknown = set(silica) - known_features
        if unknown:
            raise ValueError(
                f"silica_obs names unknown features: {sorted(unknown)}")
        final_temps = document["frames"][-1]["temperature_c"]
        obs = [silica.get(record.get("river_id")) for record in
               document["cells"]]
        rows = diagnose_replay_frame(
            [{"id": record["id"], "temperature_c": t}
             for record, t in zip(document["cells"], final_temps)],
            obs)
        document["silica_diagnostic"] = {
            "status": "diagnostic_not_calibrated",
            "phase_rule": "quartz",
            "method": "Fournier 1977 equilibrium at final-frame cell "
                      "temperatures; chemistry never writes back",
            "n_cells": len(rows),
            "n_observed": sum(1 for row in rows
                              if row["flag"] != "no_observation"),
            "rows": rows,
        }

    legacy_queries = []
    reach_anchors = reach_anchors or {}
    for reach in ecosystem["river_reaches"]:
        anchor = reach_anchors.get(reach["id"])
        if anchor:
            feature = channel.features[anchor["river_id"]]
            raw_index = anchor["vertex_index"]
            if isinstance(raw_index, bool) or int(raw_index) != raw_index:
                raise ValueError("reach vertex anchor must be integer")
            vertex_index = int(raw_index)
            if not 0 <= vertex_index < len(feature["point_s_m"]):
                raise ValueError("reach vertex anchor outside feature")
            location = feature["point_s_m"][vertex_index]
            basis = "explicit_feature_vertex"
        else:
            location = channel.chainage_at_z(reach["z"])
            basis = "unique_polyline_crossing_of_legacy_z"

        legacy_queries.append({
            "reach_id": reach["id"],
            "s_m": location,
            "basis": basis,
        })

    document.update({
        "river_features": channel.features,
        "legacy_queries": legacy_queries,
        "source_connections": connections,
        "weather_trace": weather_records,
        "clock_hour0": ecosystem.get("clock_hour", 16.2),
        "humidity": ecosystem.get("humidity", 0.45),
        "cloud": ecosystem.get("cloud", 0.16),
        "georeference": world["georeference"],
        "mapping": {
            "length_m": channel.length_m,
            "chain_order": list(channel.features),
            "distance": "horizontal polyline chainage in metres",
            "world_axes": "x east, y up, z south",
            "cell_ids": (
                "Numerical-grid ids; persistent world feature and actor "
                "ids are not changed."
            ),
        },
    })
    return document

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, required=True)
    parser.add_argument("--ecosystem", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=7200.0)
    parser.add_argument("--cell-m", type=float, default=20.0)
    parser.add_argument("--depth-m", type=float, default=1.1)
    parser.add_argument("--dispersion", type=float, default=1.0)
    parser.add_argument("--exchange", type=float, default=12.0)
    parser.add_argument("--dt", type=float, default=2.0)
    parser.add_argument("--sample", type=float, default=10.0)
    parser.add_argument("--pulse-source", default="")
    parser.add_argument("--pulse-start", type=float, default=300.0)
    parser.add_argument("--pulse-end", type=float, default=900.0)
    parser.add_argument("--pulse-delta-c", type=float, default=18.0)
    parser.add_argument(
        "--reach-anchors", type=Path,
        help="Optional JSON: reach id -> {river_id, vertex_index}",
    )
    parser.add_argument(
        "--cross-sections", type=Path,
        help="Optional JSON: river feature id -> "
             "{depth_m, status, source?} mean-depth profiles",
    )
    parser.add_argument(
        "--upstream-discharge", type=Path,
        help="Optional JSON: predicted upstream discharge series with "
             "bounds (overland_provider interface)",
    )
    parser.add_argument(
        "--extra-sources", type=Path,
        help="Optional JSON list: provider laterals as "
             "{id, s_m, flow_m3_s, temperature_c, status}",
    )
    parser.add_argument(
        "--silica-obs", type=Path,
        help="Optional JSON: river feature id -> observed dissolved "
             "SiO2 mg/L for the silica diagnostic",
    )
    parser.add_argument(
        "--energy-budget", action="store_true",
        help="Use the explicit shortwave/longwave/sensible/latent "
             "surface budget instead of the lumped Newton coefficient",
    )
    parser.add_argument(
        "--bank-slope", type=float, default=DEFAULT_BANK_SLOPE_ZH,
        help="Trapezoid bank slope z (H:V) for hydraulics diagnostics; "
             "authored illustrative, not measured",
    )
    parser.add_argument(
        "--manning-n", type=float, default=DEFAULT_MANNING_N,
        help="Manning roughness for hydraulics diagnostics; "
             "authored illustrative, not calibrated",
    )
    args = parser.parse_args()

    # A diagnostic output path must never overwrite immutable inputs.
    inputs = [args.world, args.ecosystem]
    if args.reach_anchors:
        inputs.append(args.reach_anchors)
    if args.cross_sections:
        inputs.append(args.cross_sections)
    if args.upstream_discharge:
        inputs.append(args.upstream_discharge)
    if args.extra_sources:
        inputs.append(args.extra_sources)
    if args.silica_obs:
        inputs.append(args.silica_obs)
    if args.out.resolve() in {path.resolve() for path in inputs}:
        parser.error("output must not overwrite an input")

    try:
        world = json.loads(args.world.read_text(encoding="utf-8"))
        ecosystem = json.loads(
            args.ecosystem.read_text(encoding="utf-8")
        )
        anchors = (
            json.loads(args.reach_anchors.read_text(encoding="utf-8"))
            if args.reach_anchors else None
        )
        sections = (
            json.loads(args.cross_sections.read_text(encoding="utf-8"))
            if args.cross_sections else None
        )
        discharge = (
            json.loads(args.upstream_discharge.read_text(encoding="utf-8"))
            if args.upstream_discharge else None
        )
        extra = (
            json.loads(args.extra_sources.read_text(encoding="utf-8"))
            if args.extra_sources else None
        )
        silica_file = (
            json.loads(args.silica_obs.read_text(encoding="utf-8"))
            if args.silica_obs else None
        )

        document = build_mapped_replay(
            world, ecosystem,
            duration_s=args.duration,
            maximum_cell_m=args.cell_m,
            depth_m=args.depth_m,
            dispersion_m2_s=args.dispersion,
            exchange_w_m2_k=args.exchange,
            dt_s=args.dt,
            sample_s=args.sample,
            pulse_source=args.pulse_source,
            pulse_start_s=args.pulse_start,
            pulse_end_s=args.pulse_end,
            pulse_delta_c=args.pulse_delta_c,
            reach_anchors=anchors,
            cross_sections=sections,
            energy_budget=args.energy_budget,
            bank_slope_zh=args.bank_slope,
            manning_n=args.manning_n,
            upstream_discharge=discharge,
            extra_sources=extra,
            silica_obs=silica_file,
        )
        document["input_files"] = {
            "world": {"path": str(args.world), "sha256": sha256(args.world)},
            "ecosystem": {
                "path": str(args.ecosystem),
                "sha256": sha256(args.ecosystem),
            },
        }
        if args.reach_anchors:
            document["input_files"]["reach_anchors"] = {
                "path": str(args.reach_anchors),
                "sha256": sha256(args.reach_anchors),
            }
        if args.cross_sections:
            document["input_files"]["cross_sections"] = {
                "path": str(args.cross_sections),
                "sha256": sha256(args.cross_sections),
            }
        if args.upstream_discharge:
            document["input_files"]["upstream_discharge"] = {
                "path": str(args.upstream_discharge),
                "sha256": sha256(args.upstream_discharge),
            }
        if args.extra_sources:
            document["input_files"]["extra_sources"] = {
                "path": str(args.extra_sources),
                "sha256": sha256(args.extra_sources),
            }
        if args.silica_obs:
            document["input_files"]["silica_obs"] = {
                "path": str(args.silica_obs),
                "sha256": sha256(args.silica_obs),
            }
        document["adapter_code_sha256"] = sha256(Path(__file__))

        if not document["numerical_checks"]["passed"]:
            raise ArithmeticError("solver budget closure checks failed")

        text = json.dumps(document, indent=2, allow_nan=False) + "\n"
        args.out.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.out.with_name(args.out.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(args.out)

    except (ValueError, TypeError, KeyError, ArithmeticError, OSError) as error:
        parser.exit(2, f"mapped river build failed: {error}\n")

    print(f"Wrote {args.out}")
    print("Chain:", " -> ".join(document["mapping"]["chain_order"]))
    print(f"Length: {document['mapping']['length_m']:.1f} m")
    print(f"Cells: {len(document['cells'])}")
    for connection in document["source_connections"]:
        print(
            f"Source {connection['source_id']}: "
            f"s={connection['s_m']:.1f} m, "
            f"{connection['target_river_id']} "
            f"vertex {connection['target_vertex_index']}"
        )
    print("Budget:", document["final_budget"]["heat_relative_residual"])
    print("Mapped illustrative simulation; not a Yellowstone forecast.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())