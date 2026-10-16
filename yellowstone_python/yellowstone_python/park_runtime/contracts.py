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
