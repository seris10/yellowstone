"""River heat transport segments as coupled park runtime domains.

Ecology, solutes and actors stay in LiveEngine."""
from __future__ import annotations
import dataclasses
import math
import time
from yellowstone_python.river.river_transport import Cell, River
from .contracts import finite, identifier
from .coupling import FluxLedger, Stores

def segment_river(river: River, lo: int, hi: int) -> River:
    """Return a river over cells [lo, hi) holding the state of an unstepped river."""
    if river.time_s != 0.0 or river.steps:
        raise ValueError("split a river before its first step")
    if not 0 <= lo < hi <= len(river.cells):
        raise ValueError("the segment must hold at least one cell inside the river")
    cells = [dataclasses.replace(cell, initial_c=t) for cell, t in zip(river.cells, river.temperature_c)]
    ids = [cell.id for cell in cells]
    keep = set(ids[lo:hi])
    if lo == 0:
        boundary_m3_s, boundary_c = river.boundary_q_series, river.boundary_c
    else:
        boundary_m3_s, boundary_c = river.face_flow_m3_s[lo], river.temperature_c[lo - 1]
    zones = {ids[i]: dataclasses.replace(zone, initial_c=river._hyporheic_t_c[i])
             for i, zone in enumerate(river._hyporheic_zones) if zone is not None and ids[i] in keep}
    heat = {ids[i]: series for i, series in enumerate(river._cell_heat) if series is not None and ids[i] in keep}
    return River(cells[lo:hi], boundary_m3_s, boundary_c,
                 sources=[source for source in river.sources if source.cell_id in keep],
                 air_c=river.air_c, net_heat_flux_w_m2=river.net_heat_flux, rho_cp_j_m3_k=river.rho_cp,
                 surface_budget=river.surface_budget, cell_heat_w=heat or None,
                 max_surface_iterations=river.max_surface_iterations,
                 surface_tolerance_c=river.surface_tolerance_c, surface_relaxation=river.surface_relaxation,
                 shortwave_multiplier={ids[i]: value for i, value in enumerate(river._cell_shortwave_multiplier)
                                       if ids[i] in keep},
                 hyporheic_zones=zones or None)

def split_river(river: River, index: int) -> tuple[River, River]:
    """Return rivers over cells [0, index) and [index, n) holding the state of an unstepped river."""
    if not 0 < index < len(river.cells):
        raise ValueError("the split index must leave cells on both sides")
    return segment_river(river, 0, index), segment_river(river, index, len(river.cells))

def face_conductance(left: Cell, right: Cell) -> float:
    """Return the dispersive face conductance in m3/s between two adjacent cells."""
    kl = left.dispersion_m2_s * left.cross_section_m2
    kr = right.dispersion_m2_s * right.cross_section_m2
    if kl > 0.0 and kr > 0.0:
        return 1.0 / (left.length_m / (2.0 * kl) + right.length_m / (2.0 * kr))
    return 0.0

def start_at(river: River, time_s: float, temperatures) -> None:
    """Place an unstepped river at a time and channel state with its budget starting there."""
    if river.time_s != 0.0 or river.steps:
        raise ValueError("start an unstepped river")
    values = tuple(finite(t, "temperature_c") for t in temperatures)
    if len(values) != len(river.cells):
        raise ValueError("one temperature per cell required")
    if any(zone is not None for zone in river._hyporheic_zones):
        raise NotImplementedError("starting a river with hyporheic storage needs its storage state")
    state = river.checkpoint()
    river.restore(dataclasses.replace(state, time_s=finite(time_s, "time_s"), temperature_c=values,
                                      initial_c=values))

class RiverSegmentDomain:
    """Contiguous river segment advanced at a fixed solver step on the runtime clock."""
    model_id = "yellowstone.river_segment.v1"
    representation = "fine"
    persistence_supported = False

    def __init__(self, domain_id: str, river: River, *, dt_s: float = 1.0):
        self.domain_id = identifier(domain_id)
        self.river = river
        self.dt_s = finite(dt_s, "dt_s")
        if self.dt_s <= 0:
            raise ValueError("dt_s must be positive")
        self.last_advance_wall_s = 0.0

    @property
    def time_s(self) -> float:
        return float(self.river.time_s)

    @property
    def cell_count(self) -> int:
        return len(self.river.cells)

    def advance_to(self, target_s: float) -> None:
        span = finite(target_s, "target_s") - self.river.time_s
        started = time.perf_counter()
        if span > 0:
            self.river.run(span, dt_s=self.dt_s, sample_s=span)
        self.last_advance_wall_s = time.perf_counter() - started

    def snapshot(self) -> dict:
        return {"domain_id": self.domain_id, "model_id": self.model_id, "t_s": self.time_s,
                "representation": self.representation,
                "cell_ids": [cell.id for cell in self.river.cells],
                "temperature_c": list(self.river.temperature_c)}

    def checkpoint(self) -> dict:
        return {"model_id": self.model_id, "state": self.river.checkpoint()}

    def restore(self, checkpoint: dict) -> None:
        if checkpoint["model_id"] != self.model_id:
            raise ValueError("river segment checkpoint identity mismatch")
        self.river.restore(checkpoint["state"])

    def intervene(self, changes: dict) -> None:
        for name, value in changes.items():
            self.river.set_forcing(name, self.river.time_s, value)

    def stores(self) -> Stores:
        """Channel and hyporheic water and heat relative to 0 C."""
        rho_cp = self.river.rho_cp
        water = math.fsum(cell.volume_m3 for cell in self.river.cells)
        heat = rho_cp * math.fsum(cell.volume_m3 * t for cell, t in zip(self.river.cells, self.river.temperature_c))
        for zone, t in zip(self.river._hyporheic_zones, self.river._hyporheic_t_c):
            if zone is not None:
                heat += rho_cp * zone.storage_volume_m3 * t
        return Stores(water, heat)

    def outlet_totals(self) -> tuple[float, float]:
        """Cumulative outlet export of water in m3 and heat in J."""
        budget = self.river.budget()
        return budget["outlet_export_m3"], budget["outlet_export_j"]

class RiverInterface:
    """Couple an upstream segment outlet to a downstream segment inlet once per quantum.

    Advection carries the upstream export; dispersion moves as end-cell heat."""

    def __init__(self, interface_id: str, upstream_id: str, downstream_id: str, dispersion_m3_s: float | None = None):
        self.interface_id = identifier(interface_id)
        self.upstream_id = identifier(upstream_id)
        self.downstream_id = identifier(downstream_id)
        self.dispersion_m3_s = None if dispersion_m3_s is None else finite(dispersion_m3_s, "dispersion_m3_s")
        if self.dispersion_m3_s is not None and self.dispersion_m3_s < 0:
            raise ValueError("dispersive conductance must be nonnegative")
        self.ledger = FluxLedger()
        self._export_start = None
        self._dispersion_w = 0.0
        self.last_transfer = None

    def begin(self, upstream: RiverSegmentDomain, downstream: RiverSegmentDomain, start_s: float, end_s: float):
        """Fix the interface dispersive power from the quantum-start temperatures."""
        up, down = upstream.river, downstream.river
        # Without a given conductance the face conductance follows the adjacent end cells.
        conductance = (face_conductance(up.cells[-1], down.cells[0]) if self.dispersion_m3_s is None
                       else self.dispersion_m3_s)
        power_w = up.rho_cp * conductance * (up.temperature_c[-1] - down.temperature_c[0])
        up.set_forcing(f"cell_heat_w.{up.cells[-1].id}", up.time_s, -power_w, retain_history=False)
        down.set_forcing(f"cell_heat_w.{down.cells[0].id}", down.time_s, power_w, retain_history=False)
        self._dispersion_w = power_w
        self._export_start = upstream.outlet_totals()

    def transfer(self, upstream: RiverSegmentDomain, downstream: RiverSegmentDomain, start_s: float,
                 end_s: float, revision: int) -> None:
        """Set the downstream boundary to the upstream export of the quantum and record it once."""
        water_end, heat_end = upstream.outlet_totals()
        water_m3 = water_end - self._export_start[0]
        heat_j = heat_end - self._export_start[1]
        if water_m3 <= 0:
            raise ValueError("the upstream segment exported no water over the quantum")
        span = end_s - start_s
        down = downstream.river
        inlet_c = heat_j / (down.rho_cp * water_m3)
        down.set_forcing("boundary_m3_s", down.time_s, water_m3 / span, retain_history=False)
        down.set_forcing("boundary_c", down.time_s, inlet_c, retain_history=False)
        self.last_transfer = (start_s, end_s, water_m3 / span, inlet_c, self._dispersion_w)
        receipt = f"{self.interface_id}:{revision}:{start_s:.6f}"
        self.ledger.record(self.interface_id, start_s, end_s,
                           Stores(water_m3, heat_j + self._dispersion_w * span), receipt)

    def detach(self, domain_id: str, time_s: float) -> None:
        """Forget the last receipt so a later attachment starts a new contiguous record."""
        self.ledger.records.pop(self.interface_id, None)

    def checkpoint(self) -> dict:
        total = self.ledger.totals.get(self.interface_id)
        return {"records": {k: dict(v, transfer=list(v["transfer"])) for k, v in self.ledger.records.items()},
                "totals": None if total is None else [total.water_m3, total.heat_j, total.solute_kg]}

    def restore(self, state: dict) -> None:
        self.ledger = FluxLedger()
        self.ledger.records = {k: dict(v, transfer=tuple(v["transfer"])) for k, v in state["records"].items()}
        if state["totals"] is not None:
            self.ledger.totals[self.interface_id] = Stores(*state["totals"])

def compare_split(make_river, index: int, *, duration_s: float, quantum_s: float = 10.0, dt_s: float = 1.0) -> dict:
    """Run one river whole and split at a face on the same forcing; return the acceptance metrics."""
    from .runtime import ParkRuntime
    whole = make_river()
    samples = whole.run(duration_s, dt_s=dt_s, sample_s=quantum_s)
    reference = {round(frame["t_s"], 6): frame["temperature_c"] for frame in samples}
    upper, lower, interface = firehole_pair(make_river(), index, dt_s=dt_s)
    runtime = ParkRuntime([upper, lower], quantum_s=quantum_s, history_s=2 * quantum_s, couplers=[interface],
                          max_frames=8)
    worst_c = 0.0
    compared = 0
    while runtime.time_s < duration_s - 1e-9:
        runtime.advance_one(min(duration_s, runtime.time_s + quantum_s))
        runtime.prune(runtime.time_s)
        expected = reference.get(round(runtime.time_s, 6))
        if expected is not None:
            split = list(upper.river.temperature_c) + list(lower.river.temperature_c)
            worst_c = max(worst_c, max(abs(a - b) for a, b in zip(expected, split)))
            compared += 1
    whole_budget, upper_budget, lower_budget = whole.budget(), upper.river.budget(), lower.river.budget()
    ledger = interface.ledger.totals[interface.interface_id]
    dispersion_j = upper_budget["cell_heat_j"]
    throughput_j = math.fsum(abs(b[k]) for b in (upper_budget, lower_budget)
                             for k in ("boundary_input_j", "lateral_input_j", "outlet_export_j"))
    def relative(a, b):
        return abs(a - b) / max(abs(a), abs(b), 1e-300)
    return {"index": index, "duration_s": duration_s, "quantum_s": quantum_s, "dt_s": dt_s,
            "samples_compared": compared, "max_temperature_delta_c": worst_c,
            "outlet_water_relative": relative(whole_budget["outlet_export_m3"], lower_budget["outlet_export_m3"]),
            "outlet_heat_relative": relative(whole_budget["outlet_export_j"], lower_budget["outlet_export_j"]),
            "interface_water_relative": relative(upper_budget["outlet_export_m3"], lower_budget["boundary_input_m3"]),
            "interface_heat_relative": relative(upper_budget["outlet_export_j"], lower_budget["boundary_input_j"]),
            "ledger_water_relative": relative(ledger.water_m3, upper_budget["outlet_export_m3"]),
            "ledger_heat_relative": relative(ledger.heat_j, upper_budget["outlet_export_j"] - dispersion_j),
            "dispersion_cancel_j": upper_budget["cell_heat_j"] + lower_budget["cell_heat_j"],
            "heat_budget_relative": abs(upper_budget["heat_residual_j"] + lower_budget["heat_residual_j"])
            / max(throughput_j, 1e-300),
            "whole_heat_residual_j": whole_budget["heat_residual_j"]}

def firehole_pair(river: River, index: int, *, dt_s: float = 1.0, upstream_id="firehole.upper",
                  downstream_id="firehole.lower") -> tuple[RiverSegmentDomain, RiverSegmentDomain, RiverInterface]:
    """Split a river at a face into two segment domains and their interface coupler."""
    upper, lower = split_river(river, index)
    interface = RiverInterface(f"{upstream_id}:{downstream_id}", upstream_id, downstream_id,
                               river.face_dispersion_m3_s[index])
    return (RiverSegmentDomain(upstream_id, upper, dt_s=dt_s), RiverSegmentDomain(downstream_id, lower, dt_s=dt_s),
            interface)
