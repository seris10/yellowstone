"""Versioned, JSON-compatible cross-process contracts, in SI units."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Protocol
import math
import re

SCHEMA = "yellowstone.park_runtime.v1"
_ID = re.compile(r"^[A-Za-z0-9_.:/-]{1,160}$")

def finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result

def identifier(value: str) -> str:
    if not isinstance(value, str) or not _ID.fullmatch(value) or ".." in value:
        raise ValueError("invalid identifier")
    return value

@dataclass(frozen=True)
class WorldFrame:
    """Absolute projected coordinates in Python float64."""
    easting_m: float
    northing_m: float
    elevation_origin_m: float = 2200.0
    crs: str = "EPSG:32612"

    def __post_init__(self):
        for key in ("easting_m", "northing_m", "elevation_origin_m"):
            finite(getattr(self, key), key)

    def to_projected(self, x: float, y: float, z: float) -> tuple[float, float, float]:
        return (self.easting_m + finite(x, "x"), self.northing_m - finite(z, "z"),
                self.elevation_origin_m + finite(y, "y"))

    def to_local(self, easting: float, northing: float, elevation: float):
        return (finite(easting, "easting") - self.easting_m,
                finite(elevation, "elevation") - self.elevation_origin_m,
                self.northing_m - finite(northing, "northing"))

@dataclass(frozen=True)
class Interest:
    """An output subscription, never permission to stop physical evolution."""
    region_ids: tuple[str, ...] = ()
    sequence: int = 0

    @classmethod
    def parse(cls, value: dict) -> "Interest":
        regions = value.get("region_ids", [])
        sequence = value.get("sequence", 0)
        if not isinstance(regions, list) or len(regions) > 128:
            raise ValueError("region_ids must contain at most 128 identifiers")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("sequence must be a nonnegative integer")
        return cls(tuple(sorted(set(identifier(r) for r in regions))), sequence)

RENDER_TIERS = ("A", "B", "C", "D", "occluded")

def _vector3(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} must be a list of three numbers")
    return tuple(finite(v, name) for v in value)

@dataclass(frozen=True)
class Focus:
    """Player focus in local-frame meters and m/s; reach and resident name render tiles."""
    sequence: int
    position_m: tuple[float, float, float]
    velocity_mps: tuple[float, float, float]
    t_s: float | None = None
    view_dir: tuple[float, float, float] | None = None
    fov_deg: float | None = None
    reach: tuple[str, ...] = ()
    resident: tuple[tuple[str, str], ...] = ()
    time_scale: float | None = None

    @classmethod
    def parse(cls, value: dict) -> "Focus":
        sequence = value.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 0:
            raise ValueError("sequence must be a nonnegative integer")
        if "position_m" not in value or "velocity_mps" not in value:
            raise ValueError("focus requires position_m and velocity_mps")
        view_dir = None if value.get("view_dir") is None else _vector3(value["view_dir"], "view_dir")
        if view_dir is not None and not math.hypot(*view_dir) > 0:
            raise ValueError("view_dir must be nonzero")
        fov = None if value.get("fov_deg") is None else finite(value["fov_deg"], "fov_deg")
        if fov is not None and not 0 < fov < 180:
            raise ValueError("fov_deg must be in (0, 180)")
        reach = value.get("reach", [])
        resident = value.get("resident", {})
        if not isinstance(reach, list) or len(reach) > 128:
            raise ValueError("reach must contain at most 128 tile identifiers")
        if not isinstance(resident, dict) or len(resident) > 4096:
            raise ValueError("resident must map at most 4096 tile identifiers to tiers")
        if any(tier not in RENDER_TIERS for tier in resident.values()):
            raise ValueError(f"resident tiers must be one of {RENDER_TIERS}")
        scale = None if value.get("time_scale") is None else finite(value["time_scale"], "time_scale")
        if scale is not None and scale <= 0:
            raise ValueError("time_scale must be positive")
        return cls(sequence, _vector3(value["position_m"], "position_m"),
                   _vector3(value["velocity_mps"], "velocity_mps"),
                   None if value.get("t_s") is None else finite(value["t_s"], "t_s"), view_dir, fov,
                   tuple(identifier(t) for t in reach),
                   tuple(sorted((identifier(k), tier) for k, tier in resident.items())), scale)

class Domain(Protocol):
    """Simulation domain owned by one worker; snapshots are independent copies.

    Checkpoints cover time, mutable state, forcing, counters and RNG state."""
    domain_id: str
    model_id: str
    time_s: float
    def advance_to(self, target_s: float) -> None: ...
    def snapshot(self) -> dict[str, Any]: ...
    def checkpoint(self) -> dict[str, Any]: ...
    def restore(self, checkpoint: dict[str, Any]) -> None: ...
    def intervene(self, changes: dict[str, Any]) -> None: ...

@dataclass(frozen=True)
class RegionSpec:
    region_id: str
    dependencies: tuple[str, ...] = ()
    always_active: bool = False
    representation: str = "coarse"

class DependencyGraph:
    """Logical dependency closure, separate from square rendering tiles."""
    def __init__(self, specs: list[RegionSpec]):
        self.specs = {identifier(s.region_id): s for s in specs}
        if len(self.specs) != len(specs):
            raise ValueError("duplicate region id")
        for spec in specs:
            for dependency in spec.dependencies:
                if dependency not in self.specs:
                    raise ValueError(f"unknown dependency {dependency}")

    def required(self, interest: set[str]) -> set[str]:
        pending = list(interest | {k for k, s in self.specs.items() if s.always_active})
        result = set()
        while pending:
            key = pending.pop()
            if key not in self.specs:
                raise ValueError(f"unknown region {key}")
            if key not in result:
                result.add(key)
                pending.extend(self.specs[key].dependencies)
        return result
