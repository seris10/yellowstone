"""Conservative transfer primitives. These do not claim to implement numerical AMR."""
from __future__ import annotations
from dataclasses import dataclass
import math
from .contracts import finite, identifier

@dataclass(frozen=True)
class Stores:
    water_m3: float
    heat_j: float
    solute_kg: float = 0.0

    def __post_init__(self):
        for name in ("water_m3", "heat_j", "solute_kg"):
            finite(getattr(self, name), name)
        if self.water_m3 < 0 or self.solute_kg < 0:
            raise ValueError("negative water or solute store")

    def scaled(self, weight: float):
        return Stores(self.water_m3 * weight, self.heat_j * weight, self.solute_kg * weight)

    def __add__(self, other):
        return Stores(self.water_m3 + other.water_m3, self.heat_j + other.heat_j,
                      self.solute_kg + other.solute_kg)

def restrict(children: list[Stores]) -> Stores:
    return Stores(math.fsum(s.water_m3 for s in children), math.fsum(s.heat_j for s in children),
                  math.fsum(s.solute_kg for s in children))

def prolong(parent: Stores, fractions: list[float]) -> list[Stores]:
    """Split extensive quantities by fraction."""
    if not fractions or any(finite(v, "fraction") < 0 for v in fractions):
        raise ValueError("nonnegative fractions required")
    if not math.isclose(math.fsum(fractions), 1.0, rel_tol=0, abs_tol=1e-12):
        raise ValueError("fractions must sum to one")
    return [parent.scaled(f) for f in fractions]

class FluxLedger:
    """Signed interface transfers shared by neighbor solvers.

    Retains totals and the last receipt per interface."""
    def __init__(self):
        self.records: dict[str, dict] = {}
        self.totals: dict[str, Stores] = {}

    def record(self, interface: str, start_s: float, end_s: float,
               transfer: Stores, receipt_id: str) -> bool:
        identifier(interface)
        identifier(receipt_id)
        finite(start_s, "start_s")
        finite(end_s, "end_s")
        if end_s <= start_s:
            raise ValueError("positive flux interval required")
        previous = self.records.get(interface)
        record = {"start_s": start_s, "end_s": end_s, "receipt": receipt_id,
                  "transfer": (transfer.water_m3, transfer.heat_j, transfer.solute_kg)}
        if previous:
            if previous["receipt"] == receipt_id:
                if previous != record:
                    raise ValueError("receipt reused with different flux")
                return False
            if not math.isclose(start_s, previous["end_s"], abs_tol=1e-9, rel_tol=0):
                raise ValueError("flux intervals overlap or have a gap")
        self.records[interface] = record
        self.totals[interface] = self.totals.get(interface, Stores(0, 0)) + transfer
        return True
