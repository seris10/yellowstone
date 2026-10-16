"""Map the conservative thermal solver onto the saved Midway Firehole."""
from __future__ import annotations

from bisect import bisect_right
from datetime import datetime
import json
import math
from pathlib import Path
from typing import Any

from yellowstone_python.river.river_transport import RHO_CP_J_M3_K, Series, finite, make_replay, positive
from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.atmosphere.time_utils import ISO_HINT, UTC, parse_simulation_start, timestamp_metadata
from yellowstone_python.atmosphere.microclimate import air_temp, wind_at
from yellowstone_python.river.hydraulics import DEFAULT_BANK_SLOPE_ZH, DEFAULT_MANNING_N, cell_hydraulics, thermal_inventory

# Upper physical guard for a pulse-adjusted lateral source temperature; site boiling point is near 93 C at the plateau pressure.
PULSE_TEMPERATURE_UPPER_C = 100.0

SCHEMA = "yellowstone.mapped_river_replay.v1"

# Explicit association between the aggregate thermal boundary and the representative authored channel locating it.
SOURCE_LINKS = {
    "excelsior_aggregate_outflow": "authored_excelsior_outflow_01",
}

# Weather keys accepting a scalar or {times_s, values} schedule.
SCHEDULABLE_WEATHER_KEYS = (
    "air_temperature_c",
    "relative_humidity",
    "wind_speed_mps",
    "cloud_fraction",
    "shortwave_w_m2",
)

# Scalar weather keys with their physical bounds.
BOUNDED_WEATHER_KEYS = (
    ("humidity", 0.0, 1.0),
    ("cloud", 0.0, 1.0),
    ("gust_mps", 0.0, None),
    ("sw_noon_w_m2", 0.0, None),
)


def validate_duration_and_step(
    duration_s: Any,
    dt_s: Any,
    sample_s: Any,
) -> tuple[float, float, float]:
    """Duration and time step of a run, with a sampleable output interval."""
    duration = positive("duration", duration_s)
    dt = positive("dt_s", dt_s)
    sample = positive("sample_s", sample_s)

    if not math.isfinite(duration + dt + sample):
        raise ValueError("duration and timestep values must be finite")

    # Sampling below the step would repeat frames.
    if sample < dt:
        raise ValueError("sample_s must be >= dt_s")

    return duration, dt, sample


def validate_source_record(source: Any, location: str) -> None:
    """Check one lateral source record before it reaches the solver."""
    if not isinstance(source, dict):
        raise ValueError(f"{location} must be an object")

    for key in ("id", "flow_m3s", "temperature_c"):
        if key not in source:
            raise ValueError(f"{location} requires {key!r}")

    source_id = source["id"]
    if not isinstance(source_id, str) or not source_id.strip():
        raise ValueError(f"{location}.id must be nonempty")

    flow = Series.parse(source["flow_m3s"])
    for value in flow.values:
        finite(f"{location}.flow_m3s", value, minimum=0.0)
    Series.parse(source["temperature_c"])


def validate_mapped_inputs(world: dict, ecosystem: dict) -> None:
    """Check the mapped inputs before any solver geometry is derived."""
    if not isinstance(world, dict):
        raise ValueError("world must be a JSON object")

    if not isinstance(ecosystem, dict):
        raise ValueError("ecosystem must be a JSON object")

    if not isinstance(world.get("rivers"), list):
        raise ValueError("world.rivers must be a list")

    if not isinstance(ecosystem.get("river_reaches"), list):
        raise ValueError("ecosystem.river_reaches must be a list")

    for key in ("boundary_m3s", "boundary_c"):
        if key not in ecosystem:
            raise ValueError(f"ecosystem requires {key!r}")

    if isinstance(ecosystem["boundary_m3s"], dict):
        flow_series = Series.parse(ecosystem["boundary_m3s"])
        for value in flow_series.values:
            finite("ecosystem boundary_m3s", value, minimum=0.0)
    else:
        finite("ecosystem boundary_m3s", ecosystem["boundary_m3s"], minimum=0.0)
    finite("ecosystem boundary_c", ecosystem["boundary_c"])

    reach_ids: set[str] = set()
    for index, reach in enumerate(ecosystem["river_reaches"]):
        if not isinstance(reach, dict):
            raise ValueError(f"river_reaches[{index}] must be an object")

        reach_id = reach.get("id")
        if not isinstance(reach_id, str) or not reach_id.strip():
            raise ValueError(f"river_reaches[{index}] requires a nonempty id")

        if reach_id in reach_ids:
            raise ValueError(f"duplicate ecosystem river reach id {reach_id!r}")
        reach_ids.add(reach_id)

        lateral_sources = reach.get("lateral_sources", [])
        if not isinstance(lateral_sources, list):
            raise ValueError(f"reach {reach_id!r}.lateral_sources must be a list")

        for source_index, source in enumerate(lateral_sources):
            validate_source_record(
                source,
                f"reach {reach_id!r}.lateral_sources[{source_index}]",
            )


def validate_weather_configuration(ecosystem: dict) -> None:
    """Check weather keys for type and range before a solver is created."""
    weather = ecosystem.get("weather", {})
    if not isinstance(weather, dict):
        raise ValueError("ecosystem.weather must be an object")

    for key, low, high in BOUNDED_WEATHER_KEYS:
        if key not in weather:
            continue
        value = weather[key]
        if isinstance(value, dict):
            values = Series.parse(value).values
        else:
            values = (finite(f"weather.{key}", value),)
        for item in values:
            if item < low:
                raise ValueError(f"weather.{key} must be >= {low}")
            if high is not None and item > high:
                raise ValueError(f"weather.{key} must be <= {high}")

    hour0 = finite("clock_hour", ecosystem.get("clock_hour", 16.2))
    if not 0.0 <= hour0 < 24.0:
        raise ValueError("clock_hour must be in [0, 24)")

    for key in SCHEDULABLE_WEATHER_KEYS:
        if key not in weather:
            continue
        Series.parse(weather[key])

    wind = weather.get("wind_xz_mps", [1.8, 0.6])
    if not isinstance(wind, (list, tuple)) or len(wind) != 2:
        raise ValueError("weather.wind_xz_mps must be a two-element vector")


def add_temperature_pulse(
    series: Series,
    start_s: float,
    end_s: float,
    delta_c: float,
    upper_c: float = PULSE_TEMPERATURE_UPPER_C,
) -> Series:
    """Insert pulse breakpoints and add delta_c inside the window."""
    if not 0.0 < start_s < end_s:
        raise ValueError("temperature pulse requires 0 < start_s < end_s")

    delta_c = finite("pulse temperature change", delta_c)
    upper_c = finite("pulse upper temperature", upper_c)
    breakpoints = sorted({0.0, start_s, end_s, *series.times_s})

    values = []
    for time_s in breakpoints:
        base = series.at(time_s)
        active = start_s <= time_s < end_s
        value = base + delta_c if active else base
        if active and value > upper_c:
            raise ValueError(
                "pulse-adjusted source temperature "
                f"{value:.2f} C at t={time_s:g} s exceeds the physical "
                f"upper guard of {upper_c:g} C"
            )
        values.append(value)

    return Series(tuple(breakpoints), tuple(values))

sha256 = sha256_file

def parse_cross_sections(value: Any) -> dict[str, dict[str, Any]]:
    """Validate per-feature mean-depth profiles"""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("cross_sections must be an object")
    profiles = {}
    for feature_id, record in value.items():
        if not isinstance(feature_id, str) or not feature_id:
            raise ValueError(
                "cross-section feature ids must be nonempty strings")
        if feature_id.startswith("_"):
            continue
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
        depth = positive(f"{feature_id} depth_m", record["depth_m"])
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
        if "real_measurement_site" in record:
            site = record["real_measurement_site"]
            if isinstance(site, bool) or not isinstance(site, str):
                raise ValueError(
                    f"cross-section {feature_id!r} real_measurement_site "
                    "must be a USGS gauge site id string of 8 to 15 digits")
            if not site.isdigit() or not 8 <= len(site) <= 15:
                raise ValueError(
                    f"cross-section {feature_id!r} real_measurement_site "
                    "must be a USGS gauge site id string of 8 to 15 digits")
            profiles[feature_id]["real_measurement_site"] = site
        if "dem_cross_check_depth_m" in record:
            profiles[feature_id]["dem_cross_check_depth_m"] = positive(f"{feature_id} dem_cross_check_depth_m", record["dem_cross_check_depth_m"])
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
        amount = finite(f"silica {feature_id}", mg_L)
        if amount <= 0.0:
            raise ValueError(f"silica {feature_id} must be > 0")
        out[feature_id] = amount
    return out

def parse_landscape_pockets(
    value: Any,
    channel: Channel | None = None,
) -> list[dict[str, Any]]:
    """Off-channel refuge pockets carried as a landscape artifact."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("landscape_pockets must be a list")
    records: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ValueError("landscape_pockets entries must be objects")
        pocket_id = entry.get("id")
        if not isinstance(pocket_id, str) or not pocket_id.strip():
            raise ValueError("landscape pocket id must be nonempty")
        kind = entry.get("kind", "pocket")
        if kind != "pocket":
            raise ValueError(
                f"landscape pocket {pocket_id!r} kind must be 'pocket'"
            )
        conservation = entry.get("conservation", "non_conservative")
        if conservation != "non_conservative":
            raise ValueError(
                f"landscape pocket {pocket_id!r} conservation must be "
                "'non_conservative' (solver cells carry the conservative path)"
            )
        river_id = entry.get("river_id")
        if not isinstance(river_id, str) or not river_id.strip():
            raise ValueError(
                f"landscape pocket {pocket_id!r} river_id must be nonempty"
            )
        chainage_m = finite(f"landscape pocket {pocket_id!r} chainage_m", entry.get("chainage_m"), minimum=0.0)
        if channel is not None and chainage_m > channel.length_m:
            raise ValueError(
                f"landscape pocket {pocket_id!r} chainage_m exceeds channel length"
            )
        flow_m3_s = entry.get("flow_m3_s")
        if isinstance(flow_m3_s, dict):
            raise ValueError(
                f"landscape pocket {pocket_id!r} flow_m3_s is a single "
                "mass-conserving inflow; schedules are not supported"
            )
        flow_m3_s = finite(f"landscape pocket {pocket_id!r} flow_m3_s", flow_m3_s, minimum=0.0)
        # q_in == q_out for pockets; one flow carries; consumer treats as non-conservative holding.
        temperature_c = entry.get("temperature_c")
        Series.parse(temperature_c)
        status = entry.get("status")
        if not isinstance(status, str) or not status.strip():
            raise ValueError(
                f"landscape pocket {pocket_id!r} status must be nonempty"
            )
        record = {
            "id": pocket_id,
            "kind": "pocket",
            "conservation": "non_conservative",
            "river_id": river_id,
            "chainage_m": chainage_m,
            "flow_m3_s": flow_m3_s,
            "temperature_c": temperature_c,
            "status": status.strip(),
        }
        if channel is not None:
            record["position_xyz"] = channel.position_at(chainage_m)
        if "provenance" in entry:
            record["provenance"] = entry["provenance"]
        records.append(record)
    ids = [record["id"] for record in records]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate landscape pocket ids")
    return records


def parse_extra_sources(value: Any) -> list[dict[str, Any]]:
    """Provider laterals keyed by channel chainage."""
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
        location = finite("extra source s_m", entry.get("s_m"))
        flow = finite("extra source flow", entry.get("flow_m3_s"), minimum=0.0)
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
    flows = [finite("predicted discharge", v, minimum=0.0)
             for v in value["discharge_m3_s"]]
    lo = [finite("predicted discharge lo", v, minimum=0.0)
          for v in value["discharge_lo_m3_s"]]
    hi = [finite("predicted discharge hi", v, minimum=0.0)
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
    """Find a single directed chain using declared endpoint IDs."""
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
            if not isinstance(feature, dict):
                raise ValueError("river features must be objects")
            feature_id = feature.get("id")
            if not isinstance(feature_id, str) or not feature_id.strip():
                raise ValueError("river feature id must be a nonempty string")
            if feature_id in self.features:
                raise ValueError(
                    f"{feature_id}: duplicate river feature id"
                )
            if "points" not in feature:
                raise ValueError(f"{feature_id}: points required")
            raw = feature["points"]
            if not isinstance(raw, list):
                raise ValueError(f"{feature_id}: points must be a list")
            if len(raw) < 2:
                raise ValueError(f"{feature_id}: too few vertices")

            points = [
                [finite("vertex coordinate", value) for value in point]
                for point in raw
            ]
            if any(len(point) != 3 for point in points):
                raise ValueError("river vertices must be [x, y, z]")

            width = positive("channel width", feature["width"])

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
        self._feature_records = sorted(
            self.features.values(),
            key=lambda record: record["start_s_m"],
        )
        self._feature_ends = [
            record["end_s_m"] for record in self._feature_records
        ]

    def position_at(self, s_m: float) -> list[float]:
        s_m = finite("chainage", s_m, minimum=0.0)
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
        s_m = finite("chainage", s_m, minimum=0.0)

        if s_m > self.length_m:
            raise ValueError(
                f"chainage {s_m} exceeds channel length {self.length_m}"
            )

        index = min(
            bisect_right(self._feature_ends, s_m),
            len(self._feature_records) - 1,
        )
        return self._feature_records[index]

    def chainage_at_z(self, z: float) -> float:
        """Translate a reach anchor, refusing ambiguous crossings"""
        z = finite("legacy reach z", z)
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

def validate_outlet_record(outlet: dict, source_id: str) -> None:
    """Check an authored outlet record before it drives a connection."""
    if not isinstance(outlet, dict):
        raise ValueError(f"outlet for source {source_id!r} must be an object")
    target_id = outlet.get("target_river_id")
    if not isinstance(target_id, str) or not target_id.strip():
        raise ValueError(
            f"outlet for source {source_id!r} target_river_id must be nonempty"
        )
    if "target_vertex_index" not in outlet:
        raise ValueError(
            f"outlet for source {source_id!r} requires target_vertex_index"
        )
    raw_index = outlet["target_vertex_index"]
    if isinstance(raw_index, bool) or not isinstance(raw_index, (int, float)):
        raise ValueError(
            f"outlet for source {source_id!r} target_vertex_index "
            "must be numeric"
        )
    if isinstance(raw_index, float) and not raw_index.is_integer():
        raise ValueError(
            f"outlet for source {source_id!r} target_vertex_index "
            "must be an integer"
        )
    points = outlet.get("points")
    if not isinstance(points, list) or not points:
        raise ValueError(
            f"outlet for source {source_id!r} points must be a nonempty list"
        )
    for index, point in enumerate(points):
        if not isinstance(point, (list, tuple)) or len(point) != 3:
            raise ValueError(
                f"outlet for source {source_id!r} points[{index}] "
                "must be [x, y, z]"
            )
        for value in point:
            finite(f"outlet for source {source_id!r} point coordinate", value)


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
    validate_outlet_record(outlet, source["id"])
    target_id = outlet["target_river_id"]

    if target_id not in channel.features:
        raise ValueError("thermal outlet targets a different water system")

    feature = channel.features[target_id]
    vertex_index = int(outlet["target_vertex_index"])
    if not 0 <= vertex_index < len(feature["points_xyz"]):
        raise ValueError("thermal target vertex outside feature")

    target = feature["points_xyz"][vertex_index]
    discrepancy = math.dist(outlet["points"][-1], target)
    if discrepancy > 0.001:
        raise ValueError(
            f"thermal outlet endpoint misses target by {discrepancy:.6f} m"
        )

    ecosystem_flow = source["flow_m3s"]
    world_flow = outlet.get("flow_m3_s")
    flow_comparison: dict[str, Any] = {
        "ecosystem_m3_s": ecosystem_flow,
        "world_outlet_m3_s": world_flow,
        "status": "world_outlet_flow_absent",
    }
    if isinstance(world_flow, (int, float)) and math.isfinite(world_flow):
        flow_comparison["difference_m3_s"] = ecosystem_flow - world_flow
        flow_comparison["status"] = "both_flows_present_difference_reported"

    return {
        "source_id": source["id"],
        "outlet_feature_id": outlet["id"],
        "target_river_id": target_id,
        "target_vertex_index": vertex_index,
        "s_m": feature["point_s_m"][vertex_index],
        "position_xyz": target,
        "join_error_m": discrepancy,
        "ecosystem_flow_m3_s": ecosystem_flow,
        "ecosystem_entry_c": source["temperature_c"],
        "world_outlet_flow_m3_s": world_flow,
        "world_outlet_temperature_c": outlet.get("temperature_c"),
        "flow_comparison": flow_comparison,
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
    """Split at sources and feature boundaries, then subdivide"""
    maximum_cell_m = positive("maximum cell length", maximum_cell_m)
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

def _weather_times(duration_s: float, interval_s: float) -> list[float]:
    """Sample times on the physical clock, ending exactly at the duration."""
    duration_s = finite("weather duration", duration_s, minimum=0.0)
    interval_s = positive("weather interval", interval_s)

    times: list[float] = []
    time_s = 0.0

    while time_s < duration_s:
        times.append(time_s)
        next_time = time_s + interval_s
        if next_time <= time_s:
            raise ArithmeticError("weather clock failed to advance")
        time_s = next_time

    if not times:
        times.append(0.0)

    if math.isclose(times[-1], duration_s):
        times[-1] = duration_s
    else:
        times.append(duration_s)

    return times


def _forcing_series_from_weather(
    weather: dict,
    key: str,
    *,
    default: Any,
    name: str,
) -> Series:
    """Weather forcing given as a scalar or as a {times_s, values} schedule."""
    if key in weather:
        value = weather[key]
        if isinstance(value, dict):
            return Series.parse(value)
        return Series.parse(finite(name, value))
    return Series.parse(default)


def physical_weather(
    ecosystem: dict,
    duration_s: float,
    interval_s: float = 60.0,
) -> tuple[Series, list[dict]]:
    """Air temperature and wind forcing on the physical clock (not measured meteorology)."""
    duration_s = finite("weather duration", duration_s, minimum=0.0)
    interval_s = positive("weather interval", interval_s)

    weather = ecosystem.get("weather", {})
    if not isinstance(weather, dict):
        raise ValueError("ecosystem.weather must be an object")

    hour0 = finite("clock_hour", ecosystem.get("clock_hour", 16.2))
    if not 0.0 <= hour0 < 24.0:
        raise ValueError("clock_hour must be in [0, 24)")

    times = _weather_times(duration_s, interval_s)

    scheduled_air: Series | None = None
    if "air_temperature_c" in weather:
        scheduled_air = Series.parse(weather["air_temperature_c"])

    night = finite("night air", weather.get("night_air_c", 7.0))
    warming = finite("day warming", weather.get("day_warming_c", 15.0))
    lag = finite("weather lag", weather.get("lag_hours", 3.0))

    wind = weather.get("wind_xz_mps", [1.8, 0.6])
    if not isinstance(wind, (list, tuple)) or len(wind) != 2:
        raise ValueError("weather.wind_xz_mps must be a two-element vector")
    wx, wz = [finite("base wind", value) for value in wind]
    gust = finite("gust", weather.get("gust_mps", 0.45), minimum=0.0)

    temperatures = []
    records = []

    for time_s in times:
        hour = (hour0 + time_s / 3600.0) % 24.0

        if scheduled_air is not None:
            air = scheduled_air.at(time_s)
            air_source = "scheduled_weather.air_temperature_c"
        else:
            # Share the microclimate diurnal curve with the ecosystem path.
            air = air_temp(hour, night, warming, lag)
            air_source = "authored_diurnal_approximation"

        temperatures.append(finite("weather air temperature", air))
        # Share the microclimate wind oscillation; identical period and gust shape.
        wind_xz = wind_at(time_s, (wx, wz), gust)
        records.append({
            "t_s": time_s,
            "hour": hour,
            "air_c": temperatures[-1],
            "air_source": air_source,
            "wind_xz_mps": [float(wind_xz[0]), float(wind_xz[1])],
        })

    return Series(tuple(times), tuple(temperatures)), records

def energy_met_series(ecosystem: dict, duration_s: float,
                      interval_s: float = 60.0,
                      weather_records: list[dict] | None = None) -> dict:
    """Meteorological series for the explicit surface budget."""
    from yellowstone_python.river.surface_flux import spec_from_series
    duration_s = finite("meteorology duration", duration_s, minimum=0.0)
    interval_s = positive("meteorology interval", interval_s)

    weather = ecosystem.get("weather", {})
    if not isinstance(weather, dict):
        raise ValueError("ecosystem.weather must be an object")

    hour0 = finite("clock_hour", ecosystem.get("clock_hour", 16.2))
    if not 0.0 <= hour0 < 24.0:
        raise ValueError("clock_hour must be in [0, 24)")

    if weather_records is None:
        _, weather_records = physical_weather(ecosystem, duration_s,
                                              interval_s)
    if not weather_records:
        raise ValueError("weather_records must not be empty")

    times = tuple(
        finite("weather record time", record["t_s"], minimum=0.0)
        for record in weather_records
    )
    if times[0] != 0.0:
        raise ValueError("weather records must begin at t=0")
    if any(later <= earlier for earlier, later in zip(times, times[1:])):
        raise ValueError("weather record times must be strictly increasing")

    humidity = _forcing_series_from_weather(
        weather, "relative_humidity",
        default=finite("humidity", weather.get("humidity", 0.45)),
        name="relative humidity",
    )
    cloud = _forcing_series_from_weather(
        weather, "cloud_fraction",
        default=finite("cloud", weather.get("cloud", 0.16)),
        name="cloud fraction",
    )

    if "wind_speed_mps" in weather:
        wind_speed = _forcing_series_from_weather(
            weather, "wind_speed_mps", default=0.0, name="wind speed")
        winds = [wind_speed.at(time_s) for time_s in times]
    else:
        winds = [math.hypot(record["wind_xz_mps"][0],
                            record["wind_xz_mps"][1])
                 for record in weather_records]

    if "shortwave_w_m2" in weather:
        shortwave = _forcing_series_from_weather(
            weather, "shortwave_w_m2", default=0.0, name="shortwave_w_m2")
        suns = [shortwave.at(time_s) for time_s in times]
    else:
        from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG, SITE_ELEVATION_M
        import pandas as pd
        from pvlib.location import Location
        epoch = ecosystem.get("simulation_start_epoch_unix")
        if epoch is None:
            date = ecosystem.get("as_of_date", "2001-07-15")
            start = datetime.fromisoformat(date).replace(tzinfo=UTC).timestamp()
            epoch = start + (hour0 + 6.0) * 3600.0
        datetimes = pd.to_datetime([epoch + t for t in times], unit="s", utc=True)
        site = Location(SITE_LAT_DEG, SITE_LON_DEG, altitude=SITE_ELEVATION_M, tz="UTC")
        clear = site.get_clearsky(datetimes, model="ineichen")["ghi"].to_numpy()
        suns = [float(sw) * (1.0 - 0.75 * cloud.at(t) ** 3.4)
                for sw, t in zip(clear, times)]

    return spec_from_series(
        Series(times, tuple(humidity.at(time_s) for time_s in times)),
        Series(times, tuple(winds)),
        Series(times, tuple(suns)),
        Series(times, tuple(cloud.at(time_s) for time_s in times)),
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
    landscape_pockets: list[dict[str, Any]] | None = None,
    simulation_start_utc: Any = None,
    simulation_start_epoch_unix: Any = None,
    shortwave_multiplier: dict[str, float] | None = None,
    hyporheic_zones: dict[str, dict] | None = None,
) -> dict[str, Any]:
    duration_s, dt_s, sample_s = validate_duration_and_step(
        duration_s, dt_s, sample_s)
    maximum_cell_m = positive("maximum cell length", maximum_cell_m)
    depth_m = positive("assumed mean depth", depth_m)
    dispersion_m2_s = finite("dispersion", dispersion_m2_s, minimum=0.0)
    exchange_w_m2_k = finite("exchange", exchange_w_m2_k, minimum=0.0)
    bank_slope_zh = finite("bank_slope_zh", bank_slope_zh, minimum=0.0)
    manning_n = positive("manning_n", manning_n)
    validate_mapped_inputs(world, ecosystem)
    validate_weather_configuration(ecosystem)
    simulation_start = parse_simulation_start(
        simulation_start_utc=simulation_start_utc,
        simulation_start_epoch_unix=simulation_start_epoch_unix,
    )
    simulation_time = timestamp_metadata(simulation_start, duration_s)
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
        pulse_start_s = positive("pulse start", pulse_start_s)
        pulse_end_s = positive("pulse end", pulse_end_s)
        pulse_delta_c = finite("pulse temperature change", pulse_delta_c)
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
    # Reach-averaged grade per river feature (total drop / total length); open-channel practice.
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
        # Reach-averaged grade; flat or adverse reaches stay None (Manning reported undefined).
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
        # Bed elevation: authored centerline y minus cell wetted depth; water surface is position_xyz[1]; depth_source carries provenance.
        bed_elevation_m = position[1] - cell_depth
        mapping.append({
            "id": cell_id,
            "river_id": feature["id"],
            "depth_m": cell_depth,
            "depth_status": depth_status,
            "depth_source": depth_source,
            "bed_elevation_m": bed_elevation_m,
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
        base_temperature = Series.parse(source["temperature_c"])

        if source["id"] == pulse_source:
            base_temperature = add_temperature_pulse(
                base_temperature,
                pulse_start_s,
                pulse_end_s,
                pulse_delta_c,
            )

        solver_sources.append({
            "id": source["id"],
            "cell_id": cells[index]["id"],
            "flow_m3_s": source["flow_m3s"],
            "temperature_c": {
                "times_s": list(base_temperature.times_s),
                "values": list(base_temperature.values),
            },
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

    # Accept scalar or Series boundary_m3s so overland can drive a scheduled hydrograph.
    boundary_cfg = ecosystem["boundary_m3s"]
    boundary_m3_s: Any
    if isinstance(boundary_cfg, dict) and {"times_s", "values"} <= set(
            boundary_cfg):
        for value in boundary_cfg["values"]:
            finite("boundary flow", value, minimum=0.0)
        boundary_m3_s = {
            "times_s": list(boundary_cfg["times_s"]),
            "values": list(boundary_cfg["values"]),
        }
    else:
        boundary_m3_s = finite("boundary flow", boundary_cfg)
    upstream_note: dict[str, Any] | str = (
        "ecosystem prescribed boundary discharge")
    if prediction is not None:
        flows = prediction["discharge_m3_s"]
        origin = prediction["t0_epoch_s"]
        interval = positive("upstream discharge dt_s", prediction["dt_s"])
        epoch = simulation_time["start_epoch_unix"]
        offsets = [origin + i * interval - epoch for i in range(len(flows))]
        if offsets[0] > 0.0 or offsets[-1] < duration_s:
            raise ValueError("predicted discharge does not cover replay interval")
        initial_index = bisect_right(offsets, 0.0) - 1
        selected = [(0.0, flows[initial_index])]
        selected.extend((t, flow) for t, flow in zip(offsets, flows) if 0.0 < t <= duration_s)
        boundary_m3_s = {"times_s": [t for t, _ in selected],
                         "values": [flow for _, flow in selected]}
        upstream_note = {
            "method": prediction["method"],
            "status": prediction["status"],
            "coverage": prediction.get("coverage"),
            "n_steps": len(flows),
            "mean_boundary_m3_s": math.fsum(flows) / len(flows),
            "series_retained": "scheduled hydrograph drives the solver",
            "prediction": prediction,
        }

    air, weather_records = physical_weather(ecosystem, duration_s)
    budget_spec = (energy_met_series({**ecosystem, "simulation_start_epoch_unix":
                                      simulation_time["start_epoch_unix"]}, duration_s,
                                     weather_records=weather_records)
                   if energy_budget else None)
    config = {
        "status": "mapped_illustrative_model_not_calibrated",
        "simulation_start_utc": simulation_time["start_utc"],
        "simulation_start_epoch_unix": simulation_time["start_epoch_unix"],
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
                "Diurnal approximation or a scheduled air_temperature_c, "
                "sampled every 60 physical seconds; not date-specific "
                "meteorology."
            ),
            "simulation_time": {
                "authority": "UTC epoch timestamp",
                "start_utc": simulation_time["start_utc"],
                "end_utc": simulation_time["end_utc"],
                "weather_clock": "physical seconds from replay start",
                "scheduled_forcing": (
                    "Right-continuous piecewise-constant Series; the "
                    "integration splits at forcing changes."
                ),
            },
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
    if shortwave_multiplier:
        config["shortwave_multiplier"] = dict(shortwave_multiplier)
    if hyporheic_zones:
        config["hyporheic_zones"] = dict(hyporheic_zones)

    document = make_replay(config)
    document["schema"] = SCHEMA
    for record, spatial in zip(document["cells"], mapping):
        record.update(spatial)

    # Trapezoidal hydraulics diagnostics (additive); per-cell discharge is the downstream face flow matching representative_velocity_m_s.
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
        record["volume_authority"] = "solver_rectangular_length_width_depth"
        record["hydraulics_authority"] = "diagnostic_trapezoidal_geometry"
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
        from yellowstone_python.thermal_features.geochemistry import diagnose_replay_frame
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
            "method": 'Fournier (1977) equilibrium at final-frame cell temperatures; chemistry never writes back',
            "n_cells": len(rows),
            "n_observed": sum(1 for row in rows
                              if row["flag"] != "no_observation"),
            "rows": rows,
        }

    legacy_queries = []
    reach_anchors = reach_anchors or {}
    if not isinstance(reach_anchors, dict):
        raise ValueError("reach_anchors must be an object")
    known_reach_ids = {reach["id"] for reach in ecosystem["river_reaches"]}
    unknown_anchor_ids = set(reach_anchors) - known_reach_ids
    if unknown_anchor_ids:
        raise ValueError(
            "reach anchors reference unknown reaches: "
            f"{sorted(unknown_anchor_ids)}"
        )
    for reach in ecosystem["river_reaches"]:
        anchor = reach_anchors.get(reach["id"])
        if anchor:
            if not isinstance(anchor, dict):
                raise ValueError(
                    f"reach anchor for {reach['id']!r} must be an object"
                )
            if "river_id" not in anchor or "vertex_index" not in anchor:
                raise ValueError(
                    f"reach anchor for {reach['id']!r} requires "
                    "river_id and vertex_index"
                )
            river_id = anchor["river_id"]
            if not isinstance(river_id, str) or not river_id.strip():
                raise ValueError(
                    f"reach anchor for {reach['id']!r} river_id must be nonempty"
                )
            if river_id not in channel.features:
                raise ValueError(
                    f"reach anchor for {reach['id']!r} river_id {river_id!r} "
                    "does not match a Firehole feature"
                )
            feature = channel.features[river_id]
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

    pockets = parse_landscape_pockets(landscape_pockets, channel)

    # Per-frame per-cell discharge aligned with document["cells"] order; face flows constant under this solver.
    cell_discharge_m3_s = list(face_flows[1:])
    # Per-frame per-cell wetted depth; constant per cell; each frame repeats the authored depth array.
    cell_depth_m = [record["depth_m"] for record in document["cells"]]
    from yellowstone_python.river.river_transport import river_from_config
    flow_river = river_from_config({**config, "initialize_steady": False})
    for frame in document["frames"]:
        frame["q_cells_m3s"] = list(flow_river._face_flow_at(frame["t_s"])[1:])
        frame["depth_m_cells"] = list(cell_depth_m)

    document.update({
        "river_features": channel.features,
        "legacy_queries": legacy_queries,
        "source_connections": connections,
        "weather_trace": weather_records,
        "simulation_time": simulation_time,
        "forcing_time_reference": {
            "start_epoch_unix": simulation_time["start_epoch_unix"],
            "meaning": (
                "Forcing schedule times are physical seconds after "
                "simulation_start_epoch_unix."
            ),
        },
        "weather_forcing": {
            "records": weather_records,
            "air_temperature": {
                "times_s": list(air.times_s),
                "values": list(air.values),
            },
        },
        "clock_hour0": ecosystem.get("clock_hour", 16.2),
        # Weather authority: humidity and cloud come from ecosystem.weather so the top-level document matches the met bundle.
        "humidity": ecosystem.get("weather", {}).get("humidity", 0.45),
        "cloud": ecosystem.get("weather", {}).get("cloud", 0.16),
        "georeference": world["georeference"],
        "landscape_pockets": {
            "status": "non_conservative_landscape_artifact",
            "authority": (
                "pockets are a landscape artifact; solver cells and the "
                "numerical budget do not integrate them"
            ),
            "n": len(pockets),
            "records": pockets,
        },
        "mapping": {
            "length_m": channel.length_m,
            "chain_order": list(channel.features),
            "distance": "horizontal polyline chainage in meters",
            "world_axes": "x east, y up, z south",
            "cell_ids": (
                "Numerical-grid ids; persistent world feature and actor "
                "ids are not changed."
            ),
        },
    })
    if budget_spec is not None:
        document["weather_forcing"]["surface_budget"] = budget_spec
    return document
