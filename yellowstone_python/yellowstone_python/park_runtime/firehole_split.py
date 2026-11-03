"""River heat and solute transport segments as coupled park runtime domains.

Ecology and actors stay in LiveEngine."""
from __future__ import annotations
import dataclasses
import math
import time
from yellowstone_python.river.river_transport import Cell, River
from yellowstone_python.river.solute_transport import (SOLUTE_KEYS, BoundaryConcentrations, SoluteTransport,
                                                       river_solute_transport)
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

def segment_solutes(transport: SoluteTransport, segment: River, lo: int, hi: int) -> SoluteTransport:
    """Return solutes over cells [lo, hi) of an unstepped transport on a segment river's cells and flows."""
    if transport.time_s != 0.0 or transport.steps:
        raise ValueError("split a solute transport before its first step")
    if [cell.id for cell in segment.cells] != [cell.id for cell in transport.cells[lo:hi]]:
        raise ValueError("the segment river and the solute cells differ")
    if lo == 0:
        boundary = {key: transport._boundary_c_series[key] for key in SOLUTE_KEYS}
    else:
        boundary = {key: transport.concentrations(key)[lo - 1] for key in SOLUTE_KEYS}
    keep = {cell.id for cell in segment.cells}
    return SoluteTransport(tuple(segment.cells), segment.boundary_q_series, BoundaryConcentrations(**boundary),
                           sources=tuple(source for source in transport.sources if source.cell_id in keep),
                           initial_concentrations={key: transport.concentrations(key)[lo:hi] for key in SOLUTE_KEYS})

def start_solutes_at(transport: SoluteTransport, time_s: float, concentrations: dict) -> None:
    """Place an unstepped solute transport at a time and concentrations with its budget starting there."""
    if transport.time_s != 0.0 or transport.steps:
        raise ValueError("start an unstepped solute transport")
    values = tuple(tuple(finite(c, "concentration") for c in concentrations[key]) for key in SOLUTE_KEYS)
    if any(len(row) != len(transport.cells) for row in values) or any(c < 0 for row in values for c in row):
        raise ValueError("one nonnegative concentration per cell and solute required")
    state = transport.checkpoint()
    transport.restore(dataclasses.replace(state, time_s=finite(time_s, "time_s"), concentrations=values,
                                          initial=values))

def solute_values(transport: SoluteTransport | None) -> dict | None:
    """Return the concentrations of each solute as lists, or None without solutes."""
    return None if transport is None else {key: list(transport.concentrations(key)) for key in SOLUTE_KEYS}

def advance_solutes(solutes: SoluteTransport, river: River, span_s: float, dt_s: float, *,
                    nonnegative: bool = True) -> None:
    """Advance solutes over a span on the flow schedules of the river that carries them.

    A replay through recorded interface fluxes passes nonnegative=False."""
    solutes.use_flows(river.boundary_q_series, {source.id: source.flow_m3_s for source in river.sources})
    solutes.run(span_s, dt_s=dt_s, sample_s=span_s)
    if not math.isclose(solutes.time_s, river.time_s, rel_tol=0, abs_tol=1e-7):
        raise RuntimeError("solutes did not reach the river time")
    low = min(min(solutes.concentrations(key)) for key in SOLUTE_KEYS)
    if nonnegative and low < 0.0:
        raise ArithmeticError(f"negative solute concentration {low} after the advance")

def apply_forcing(river: River, solutes: SoluteTransport | None, name: str, at_s: float, value) -> None:
    """Set a river forcing, or a solute forcing named with the solute. prefix."""
    if name.startswith("solute."):
        if solutes is None:
            raise ValueError(f"forcing {name!r} names solutes on a segment without solutes")
        solutes.set_forcing(name.removeprefix("solute."), at_s, value)
    else:
        river.set_forcing(name, at_s, value)

class RiverSegmentDomain:
    """Contiguous river segment advanced at a fixed solver step on the runtime clock.

    Optional solutes on the same cells take the river flows and advance after the heat."""
    model_id = "yellowstone.river_segment.v1"
    representation = "fine"
    persistence_supported = False

    def __init__(self, domain_id: str, river: River, *, dt_s: float = 1.0, solutes: SoluteTransport | None = None,
                 solute_dt_s: float | None = None):
        self.domain_id = identifier(domain_id)
        self.river = river
        self.dt_s = finite(dt_s, "dt_s")
        if self.dt_s <= 0:
            raise ValueError("dt_s must be positive")
        if solutes is not None and [c.id for c in solutes.cells] != [c.id for c in river.cells]:
            raise ValueError("solutes must share the segment cells")
        self.solutes = solutes
        self.solute_dt_s = self.dt_s if solute_dt_s is None else finite(solute_dt_s, "solute_dt_s")
        if self.solute_dt_s <= 0:
            raise ValueError("solute_dt_s must be positive")
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
            if self.solutes is not None:
                advance_solutes(self.solutes, self.river, span, self.solute_dt_s)
        self.last_advance_wall_s = time.perf_counter() - started

    def snapshot(self) -> dict:
        snapshot = {"domain_id": self.domain_id, "model_id": self.model_id, "t_s": self.time_s,
                    "representation": self.representation,
                    "cell_ids": [cell.id for cell in self.river.cells],
                    "temperature_c": list(self.river.temperature_c)}
        if self.solutes is not None:
            snapshot["solutes"] = solute_values(self.solutes)
        return snapshot

    def checkpoint(self) -> dict:
        return {"model_id": self.model_id, "state": self.river.checkpoint(),
                "solutes": None if self.solutes is None else self.solutes.checkpoint()}

    def restore(self, checkpoint: dict) -> None:
        if checkpoint["model_id"] != self.model_id:
            raise ValueError("river segment checkpoint identity mismatch")
        if (checkpoint.get("solutes") is None) != (self.solutes is None):
            raise ValueError("river segment checkpoint carries a different set of transported quantities")
        self.river.restore(checkpoint["state"])
        if self.solutes is not None:
            self.solutes.restore(checkpoint["solutes"])

    def intervene(self, changes: dict) -> None:
        for name, value in changes.items():
            apply_forcing(self.river, self.solutes, name, self.river.time_s, value)

    def solute_stores(self) -> dict | None:
        """Channel mass of each solute in concentration units times m3, or None without solutes."""
        return None if self.solutes is None else self.solutes.mass_stores()

    def solute_outlet_totals(self) -> dict:
        """Cumulative outlet export of each solute in concentration units times m3."""
        budget = self.solutes.mass_budget()["solutes"]
        return {key: budget[key]["outlet_export_mass"] for key in SOLUTE_KEYS}

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

    Advection carries the upstream export; dispersion moves as end-cell heat and solute mass."""

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
        self._solute_export_start = None
        self._solute_dispersion = None
        # Received advective and dispersive mass per solute in SOLUTE_KEYS order.
        self.solute_totals = None
        self.last_transfer = None

    def begin(self, upstream: RiverSegmentDomain, downstream: RiverSegmentDomain, start_s: float, end_s: float):
        """Fix the interface dispersive power and solute rates from the quantum-start end cells."""
        if (upstream.solutes is None) != (downstream.solutes is None):
            raise ValueError("both sides of a river interface carry solutes or neither does")
        up, down = upstream.river, downstream.river
        # Without a given conductance the face conductance follows the adjacent end cells.
        conductance = (face_conductance(up.cells[-1], down.cells[0]) if self.dispersion_m3_s is None
                       else self.dispersion_m3_s)
        power_w = up.rho_cp * conductance * (up.temperature_c[-1] - down.temperature_c[0])
        up.set_forcing(f"cell_heat_w.{up.cells[-1].id}", up.time_s, -power_w, retain_history=False)
        down.set_forcing(f"cell_heat_w.{down.cells[0].id}", down.time_s, power_w, retain_history=False)
        self._dispersion_w = power_w
        self._export_start = upstream.outlet_totals()
        if upstream.solutes is not None:
            sender, receiver = upstream.solutes, downstream.solutes
            rates = tuple(conductance * (sender.concentrations(key)[-1] - receiver.concentrations(key)[0])
                          for key in SOLUTE_KEYS)
            for key, rate in zip(SOLUTE_KEYS, rates):
                sender.set_forcing(f"cell_mass.{key}.{up.cells[-1].id}", sender.time_s, -rate, retain_history=False)
                receiver.set_forcing(f"cell_mass.{key}.{down.cells[0].id}", receiver.time_s, rate,
                                     retain_history=False)
            self._solute_dispersion = rates
            self._solute_export_start = upstream.solute_outlet_totals()

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
        masses = solute_inlet = None
        if upstream.solutes is not None:
            exported = upstream.solute_outlet_totals()
            masses = tuple(exported[key] - self._solute_export_start[key] for key in SOLUTE_KEYS)
            solute_inlet = tuple(mass / water_m3 for mass in masses)
            receiver = downstream.solutes
            for key, value in zip(SOLUTE_KEYS, solute_inlet):
                receiver.set_forcing(f"boundary.{key}", receiver.time_s, value, retain_history=False)
        self.last_transfer = (start_s, end_s, water_m3 / span, inlet_c, self._dispersion_w)
        if solute_inlet is not None:
            self.last_transfer += (solute_inlet, self._solute_dispersion)
        receipt = f"{self.interface_id}:{revision}:{start_s:.6f}"
        recorded = self.ledger.record(self.interface_id, start_s, end_s,
                                      Stores(water_m3, heat_j + self._dispersion_w * span), receipt)
        if recorded and masses is not None:
            held = self.solute_totals or (0.0,) * len(SOLUTE_KEYS)
            self.solute_totals = tuple(total + mass + rate * span for total, mass, rate
                                       in zip(held, masses, self._solute_dispersion))

    def detach(self, domain_id: str, time_s: float) -> None:
        """Forget the last receipt so a later attachment starts a new contiguous record."""
        self.ledger.records.pop(self.interface_id, None)

    def checkpoint(self) -> dict:
        total = self.ledger.totals.get(self.interface_id)
        return {"records": {k: dict(v, transfer=list(v["transfer"])) for k, v in self.ledger.records.items()},
                "totals": None if total is None else [total.water_m3, total.heat_j, total.solute_kg],
                "solute_totals": None if self.solute_totals is None else list(self.solute_totals)}

    def restore(self, state: dict) -> None:
        self.ledger = FluxLedger()
        self.ledger.records = {k: dict(v, transfer=tuple(v["transfer"])) for k, v in state["records"].items()}
        if state["totals"] is not None:
            self.ledger.totals[self.interface_id] = Stores(*state["totals"])
        saved = state.get("solute_totals")
        self.solute_totals = None if saved is None else tuple(saved)

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

def segmented_river(river: River, faces: list[int], *, prefix: str, dt_s: float = 1.0,
                    solutes: SoluteTransport | None = None, solute_dt_s: float | None = None):
    """Split an unstepped river and its optional solutes at interior faces into domains and interfaces."""
    edges = [0, *faces, len(river.cells)]
    domains = []
    for k, (lo, hi) in enumerate(zip(edges, edges[1:])):
        segment = segment_river(river, lo, hi)
        carried = None if solutes is None else segment_solutes(solutes, segment, lo, hi)
        domains.append(RiverSegmentDomain(f"{prefix}.s{k}", segment, dt_s=dt_s, solutes=carried,
                                          solute_dt_s=solute_dt_s))
    interfaces = [RiverInterface(f"{a.domain_id}:{b.domain_id}", a.domain_id, b.domain_id,
                                 river.face_dispersion_m3_s[face]) for a, b, face in zip(domains, domains[1:], faces)]
    return domains, interfaces

def compare_chain(make_river, faces: list[int], *, solute_settings: dict | None = None, duration_s: float,
                  quantum_s: float = 10.0, dt_s: float = 1.0, solute_dt_s: float | None = None) -> dict:
    """Compare whole-river solutes with a coupled segment chain; return the acceptance metrics.

    Mass uses concentration units times m3; increment is the mixed source rise at the outlet."""
    from .runtime import ParkRuntime
    solute_dt_s = quantum_s if solute_dt_s is None else solute_dt_s
    whole = make_river()
    whole_solutes, provenance = river_solute_transport(whole, solute_settings)
    chain_river = make_river()
    domains, interfaces = segmented_river(chain_river, faces, prefix="chain", dt_s=dt_s,
                                          solutes=river_solute_transport(chain_river, solute_settings)[0],
                                          solute_dt_s=solute_dt_s)
    heat_domains, heat_interfaces = segmented_river(make_river(), faces, prefix="heat", dt_s=dt_s)
    runtime = ParkRuntime(domains, quantum_s=quantum_s, history_s=2 * quantum_s, couplers=interfaces, max_frames=8)
    heat_runtime = ParkRuntime(heat_domains, quantum_s=quantum_s, history_s=2 * quantum_s, couplers=heat_interfaces,
                               max_frames=8)
    worst = dict.fromkeys(SOLUTE_KEYS, 0.0)
    dispersion = [dict.fromkeys(SOLUTE_KEYS, 0.0) for _ in interfaces]
    heat_identical, compared, lowest = True, 0, math.inf
    while runtime.time_s < duration_s - 1e-9:
        target = min(duration_s, runtime.time_s + quantum_s)
        span = target - runtime.time_s
        whole.run(span, dt_s=dt_s, sample_s=span)
        advance_solutes(whole_solutes, whole, span, solute_dt_s)
        for kernel in (runtime, heat_runtime):
            kernel.advance_one(target)
            kernel.prune(kernel.time_s)
        for k, interface in enumerate(interfaces):
            for key, rate in zip(SOLUTE_KEYS, interface.last_transfer[6]):
                dispersion[k][key] += rate * span
        for key in SOLUTE_KEYS:
            chain = [c for domain in domains for c in domain.solutes.concentrations(key)]
            worst[key] = max(worst[key], max(abs(a - b) for a, b in zip(whole_solutes.concentrations(key), chain)))
            lowest = min(lowest, min(chain))
        heat_identical = heat_identical and ([t for d in domains for t in d.river.temperature_c]
                                             == [t for d in heat_domains for t in d.river.temperature_c])
        compared += 1

    def relative(a, b):
        return abs(a - b) / max(abs(a), abs(b), 1e-300)

    whole_budget = whole_solutes.mass_budget()["solutes"]
    budgets = [domain.solutes.mass_budget()["solutes"] for domain in domains]
    outlet_q = whole.face_flow_m3_s[-1]
    report = {"faces": list(faces), "duration_s": duration_s, "quantum_s": quantum_s, "dt_s": dt_s,
              "solute_dt_s": solute_dt_s, "quanta_compared": compared, "heat_identical": heat_identical,
              "min_concentration": lowest, "boundary_provenance": provenance, "solutes": {}}
    for key in SOLUTE_KEYS:
        boundary = whole_solutes._boundary_c_series[key].at(0.0)
        increment = math.fsum(source.flow_m3_s.at(0.0) * (source.concentrations[key].at(0.0) - boundary)
                              for source in whole_solutes.sources) / outlet_q
        terms = (budgets[0][key]["boundary_input_mass"],
                 *(b[key]["lateral_input_mass"] for b in budgets), *(b[key]["cell_input_mass"] for b in budgets),
                 -budgets[-1][key]["outlet_export_mass"])
        throughput = math.fsum(abs(x) for x in terms)
        storage = math.fsum(b[key]["storage_change_mass"] for b in budgets)
        face_rows = []
        for k, (interface, up, down) in enumerate(zip(interfaces, budgets, budgets[1:])):
            exported = up[key]["outlet_export_mass"]
            index = SOLUTE_KEYS.index(key)
            face_rows.append({"face": interface.interface_id,
                              "inlet_relative": relative(down[key]["boundary_input_mass"], exported),
                              "ledger_relative": relative(interface.solute_totals[index],
                                                          exported + dispersion[k][key])})
        report["solutes"][key] = {
            "mixed_increment": increment, "max_delta": worst[key],
            "max_delta_over_increment": worst[key] / increment if increment > 0 else math.inf,
            "outlet_relative": relative(whole_budget[key]["outlet_export_mass"],
                                        budgets[-1][key]["outlet_export_mass"]),
            "outlet_over_input": abs(whole_budget[key]["outlet_export_mass"] - budgets[-1][key]["outlet_export_mass"])
            / max(whole_budget[key]["boundary_input_mass"] + whole_budget[key]["lateral_input_mass"], 1e-300),
            "faces": face_rows, "throughput": throughput,
            "dispersion_cancel_relative": abs(math.fsum(b[key]["cell_input_mass"] for b in budgets))
            / max(throughput, 1e-300),
            "closure_relative": abs(storage - math.fsum(terms)) / max(throughput, 1e-300)}
    return report
