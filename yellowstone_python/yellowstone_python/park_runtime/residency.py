"""River segment simulation residency.

Fine segments follow the walker, the rest run coarse, and activation spin-up runs in workers."""
from __future__ import annotations
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
import copy
import dataclasses
import hashlib
import importlib.util
import json
import math
import multiprocessing
import time
from yellowstone_python.river.river_transport import River, RiverState, river_from_config
from .coarse_river import CoarseRiverSegmentDomain, coarse_river, prolong_temperatures, restrict_temperatures
from .contracts import finite, identifier
from .coupling import Stores
from .firehole_split import RiverInterface, RiverSegmentDomain, segment_river, start_at
from .runtime import ParkRuntime
from .state_store import canonical

# Lookahead time in s of the reach set point q = p + v * T.
REACH_LOOKAHEAD_S = 20.0
# Interior faces of the six 46-cell Firehole segments.
FIREHOLE_FACES = (46, 92, 138, 184, 230)
BUDGET_TERMS_J = ("boundary_input_j", "lateral_input_j", "outlet_export_j", "surface_exchange_j",
                  "additional_heat_flux_j", "cell_heat_j")
RESIDENCY_STATE_SCHEMA = "yellowstone.park_residency_state.v1"
RESIDENCY_MODULES = ("yellowstone_python.river.river_transport", "yellowstone_python.river.surface_flux",
                     "yellowstone_python.park_runtime.firehole_split", "yellowstone_python.park_runtime.coarse_river",
                     "yellowstone_python.park_runtime.runtime", "yellowstone_python.park_runtime.residency")

def residency_model_versions() -> dict:
    """Return the source SHA-256 of each module that shapes a saved residency state."""
    versions = {}
    for module in RESIDENCY_MODULES:
        spec = importlib.util.find_spec(module)
        if spec is None or spec.origin is None:
            raise ValueError(f"cannot locate module {module}")
        with open(spec.origin, "rb") as stream:
            versions[module] = hashlib.sha256(stream.read()).hexdigest()
    return versions

@dataclass(frozen=True)
class SegmentSpec:
    """River segment over fine cells [lo, hi) with its chainage and nominal water travel time."""
    domain_id: str
    lo: int
    hi: int
    start_m: float
    end_m: float
    travel_s: float

    @property
    def cells(self) -> int:
        return self.hi - self.lo

def segment_specs(river: River, faces: list[int], prefix: str) -> list[SegmentSpec]:
    """Return segments of a river split at interior faces, upstream first."""
    edges = [0, *faces, len(river.cells)]
    if any(b - a < 2 for a, b in zip(edges, edges[1:])):
        raise ValueError("faces must be increasing and leave at least two cells per segment")
    lengths = [cell.length_m for cell in river.cells]
    residence = [cell.volume_m3 / river.face_flow_m3_s[i + 1] for i, cell in enumerate(river.cells)]
    specs = []
    for k, (lo, hi) in enumerate(zip(edges, edges[1:])):
        specs.append(SegmentSpec(identifier(f"{prefix}.s{k}"), lo, hi, math.fsum(lengths[:lo]),
                                 math.fsum(lengths[:hi]), math.fsum(residence[lo:hi])))
    return specs

class RiverChainage:
    """Map local-frame x and z in m to river chainage over mapped cell pieces, positive downstream.

    Each piece runs through a cell center along its downstream unit vector between the cell ends."""

    def __init__(self, cells: list[dict]):
        if not cells:
            raise ValueError("chainage needs mapped cells")
        self.pieces = []
        for cell in cells:
            x, _, z = (finite(v, "position_xyz") for v in cell["position_xyz"])
            ux, uz = (finite(v, "downstream_unit_xz") for v in cell["downstream_unit_xz"])
            norm = math.hypot(ux, uz)
            start, center, end = (finite(cell[k], k) for k in ("start_s_m", "center_s_m", "end_s_m"))
            if not norm > 0 or not start <= center <= end:
                raise ValueError(f"cell {cell.get('id')} needs a downstream direction and ordered chainage")
            self.pieces.append((x, z, ux / norm, uz / norm, start, center, end))

    def locate(self, x_m: float, z_m: float) -> tuple[float, float, int]:
        """Return the chainage in m, the lateral distance in m and the cell index of the nearest piece."""
        x_m, z_m = finite(x_m, "x_m"), finite(z_m, "z_m")
        best = None
        for index, (x, z, ux, uz, start, center, end) in enumerate(self.pieces):
            along = min(max((x_m - x) * ux + (z_m - z) * uz, start - center), end - center)
            distance = math.hypot(x_m - x - ux * along, z_m - z - uz * along)
            if best is None or distance < best[1]:
                best = (center + along, distance, index)
        return best

    def along_channel(self, index: int, vx_mps: float, vz_mps: float) -> float:
        """Return the downstream velocity component in m/s at a cell."""
        _, _, ux, uz, *_ = self.pieces[index]
        return finite(vx_mps, "vx_mps") * ux + finite(vz_mps, "vz_mps") * uz

def _segment_at(specs, x_m: float) -> int:
    x = min(max(x_m, specs[0].start_m), specs[-1].end_m)
    for k, spec in enumerate(specs):
        if x < spec.end_m:
            return k
    return len(specs) - 1

def anticipation(specs: list[SegmentSpec], position_m: float, velocity_mps: float, lead_wall_s: float,
                 time_scale: float, *, reach_lookahead_s: float = REACH_LOOKAHEAD_S) -> list[tuple[str, str]]:
    """Rank segments for fine residency as (domain_id, reason) with reasons reach, ahead and halo.

    Position and velocity are along the chainage, positive downstream; lead time is in wall seconds."""
    position_m, velocity_mps = finite(position_m, "position_m"), finite(velocity_mps, "velocity_mps")
    lead_wall_s, time_scale = finite(lead_wall_s, "lead_wall_s"), finite(time_scale, "time_scale")
    ranked, seen = [], set()

    def add(k, reason):
        if specs[k].domain_id not in seen:
            seen.add(specs[k].domain_id)
            ranked.append((specs[k].domain_id, reason))

    def span(a, b, reason):
        lo, hi = sorted((_segment_at(specs, a), _segment_at(specs, b)))
        order = range(lo, hi + 1) if velocity_mps >= 0 else range(hi, lo - 1, -1)
        for k in order:
            add(k, reason)

    span(position_m, position_m + velocity_mps * reach_lookahead_s, "reach")
    span(position_m, position_m + velocity_mps * max(lead_wall_s, reach_lookahead_s), "ahead")
    lead_sim_s = lead_wall_s * time_scale
    for domain_id, _ in list(ranked):
        k = next(i for i, spec in enumerate(specs) if spec.domain_id == domain_id)
        travel = 0.0
        for u in range(k - 1, -1, -1):
            travel += specs[u].travel_s
            if travel >= lead_sim_s:
                break
            add(u, "halo")
    return ranked

@dataclass(frozen=True)
class Admission:
    """Fine and coarse segment sets with the effective time scale and the capacity used."""
    fine: tuple[str, ...]
    coarse: tuple[str, ...]
    effective_rate: float
    held: bool
    demand: float
    budget: float

def admit(ranked: list[tuple[str, str]], cells: dict[str, int], capacity: float | None, time_scale: float,
          *, utilization: float = 0.8) -> Admission:
    """Admit ranked segments while fine cells times the rate fit the capacity budget.

    Capacity is in cell-simulated-seconds per wall second; reach segments run fine at a held rate."""
    time_scale = finite(time_scale, "time_scale")
    budget = math.inf if capacity is None else finite(capacity, "capacity") * finite(utilization, "utilization")
    reach = [d for d, reason in ranked if reason == "reach"]
    reach_cells = sum(cells[d] for d in reach)
    rate = time_scale
    held = reach_cells * time_scale > budget
    if held:
        rate = budget / reach_cells
    fine, used = list(reach), reach_cells * rate
    for domain_id, reason in ranked:
        if reason != "reach" and used + cells[domain_id] * rate <= budget:
            fine.append(domain_id)
            used += cells[domain_id] * rate
    coarse = tuple(d for d in cells if d not in fine)
    return Admission(tuple(fine), coarse, rate, held, used, budget)

_WORKER = {}

def _worker_init(config: dict) -> None:
    _WORKER["full"] = river_from_config(config)
    _WORKER["segments"] = {}

def replay_segment(river: River, start_s: float, temperatures, inlet: list[tuple], outlet: list[tuple],
                   end_s: float, dt_s: float, interventions: list[tuple] = ()) -> list[float]:
    """Advance an unstepped fine segment from a state through recorded interface quanta.

    Entries: (start_s, end_s, inlet_m3_s, inlet_c, dispersion_w); interventions: (at_s, changes)."""
    start_at(river, start_s, temperatures)
    inlet_at = {round(e[0], 6): e for e in inlet}
    outlet_at = {round(e[0], 6): e for e in outlet}
    pending = sorted(interventions, key=lambda item: item[0])
    first, last = river.cells[0].id, river.cells[-1].id
    while river.time_s < end_s - 1e-9:
        while pending and pending[0][0] <= river.time_s + 1e-9:
            for name, value in pending.pop(0)[1].items():
                river.set_forcing(name, river.time_s, value)
        key = round(river.time_s, 6)
        entry_in, entry_out = inlet_at.get(key), outlet_at.get(key)
        if (inlet and entry_in is None) or (outlet and entry_out is None):
            raise ValueError(f"interface history has a gap at {river.time_s} s")
        stop = (entry_in or entry_out)[1]
        if pending and pending[0][0] < min(stop, end_s) - 1e-9:
            raise ValueError(f"interface history is not split at the intervention at {pending[0][0]} s")
        if entry_in is not None:
            river.set_forcing("boundary_m3_s", river.time_s, entry_in[2], retain_history=False)
            river.set_forcing("boundary_c", river.time_s, entry_in[3], retain_history=False)
            river.set_forcing(f"cell_heat_w.{first}", river.time_s, entry_in[4], retain_history=False)
        if entry_out is not None:
            if entry_in is not None and not math.isclose(entry_out[1], stop, rel_tol=0, abs_tol=1e-9):
                raise ValueError("inlet and outlet quanta disagree")
            river.set_forcing(f"cell_heat_w.{last}", river.time_s, -entry_out[4], retain_history=False)
        span = min(stop, end_s) - river.time_s
        river.run(span, dt_s=dt_s, sample_s=span)
    return list(river.temperature_c)

def spinup_job(lo: int, hi: int, start_s: float, temperatures, inlet, outlet, end_s: float, dt_s: float,
               interventions=()) -> dict:
    """Replay one fine segment in a worker process; return end temperatures and the wall cost."""
    started = time.perf_counter()
    cache = _WORKER["segments"]
    if (lo, hi) not in cache:
        cache[(lo, hi)] = segment_river(_WORKER["full"], lo, hi)
    river = copy.deepcopy(cache[(lo, hi)])
    temps = replay_segment(river, start_s, temperatures, inlet, outlet, end_s, dt_s, interventions)
    return {"temperature_c": temps, "start_s": start_s, "end_s": end_s, "wall_s": time.perf_counter() - started,
            "cell_seconds": (hi - lo) * (end_s - start_s)}

class _Job:
    def __init__(self, future, submit_wall_s: float, kind: str):
        self.future, self.submit_wall_s, self.kind = future, submit_wall_s, kind

class ResidencyManager:
    """Own a segmented river in a ParkRuntime and keep the walker's segments fine.

    With a virtual wall clock a job counts as finished at its submit time plus its measured cost."""

    def __init__(self, config: dict, faces: list[int], *, prefix: str = "firehole", quantum_s: float = 10.0,
                 dt_s: float = 1.0, cells_per_coarse: int = 23, spinup_s: float = 3600.0,
                 lead_margin_s: float = 30.0, retire_after_s: float = 10.0, utilization: float = 0.8,
                 checkpoint_fresh_s: float = 86400.0, workers: int = 2, virtual_wall: bool = False,
                 position_m: float = 0.0, velocity_mps: float = 0.0, time_scale: float = 1.0,
                 epoch_unix: float | None = None):
        self.config = copy.deepcopy(config)
        full = river_from_config(self.config)
        self.specs = segment_specs(full, faces, prefix)
        self.by_id = {spec.domain_id: spec for spec in self.specs}
        self.cells = {spec.domain_id: spec.cells for spec in self.specs}
        self.quantum_s, self.dt_s = finite(quantum_s, "quantum_s"), finite(dt_s, "dt_s")
        self.spinup_s, self.lead_margin_s = finite(spinup_s, "spinup_s"), finite(lead_margin_s, "lead_margin_s")
        self.retire_after_s, self.utilization = finite(retire_after_s, "retire_after_s"), utilization
        self.checkpoint_fresh_s = finite(checkpoint_fresh_s, "checkpoint_fresh_s")
        self.virtual_wall = virtual_wall
        self.interventions = []
        self._snapshots = {}
        self.fine_pristine = {s.domain_id: segment_river(full, s.lo, s.hi) for s in self.specs}
        self.coarse_pristine = {d: coarse_river(r, cells_per_coarse) for d, r in self.fine_pristine.items()}
        self.capacity = None
        self.worker_rate = None
        ranked = anticipation(self.specs, position_m, velocity_mps, lead_margin_s, time_scale)
        initial = set(admit(ranked, self.cells, None, time_scale).fine)
        domains = [self._fine_domain(d, 0.0, self.fine_pristine[d].temperature_c) if d in initial
                   else self._coarse_domain(d, 0.0, self.coarse_pristine[d][0].temperature_c)
                   for d in self.cells]
        self.interfaces = [RiverInterface(f"{a.domain_id}:{b.domain_id}", a.domain_id, b.domain_id)
                           for a, b in zip(self.specs, self.specs[1:])]
        epoch = {} if epoch_unix is None else {"epoch_unix": epoch_unix}
        self.runtime = ParkRuntime(domains, quantum_s=self.quantum_s, history_s=2 * self.quantum_s,
                                   max_frames=8, couplers=self.interfaces, **epoch)
        history = int(math.ceil(self.checkpoint_fresh_s / self.quantum_s)) + 2
        self.face_history = {i.interface_id: deque(maxlen=history) for i in self.interfaces}
        self.coarse_history = {d: deque(maxlen=int(math.ceil(self.spinup_s / self.quantum_s)) + 2)
                               for d in self.cells}
        self.last_fine = {}
        self.jobs = {}
        self.leave_wall = {}
        self.swaps, self.lifetimes, self.events = [], [], []
        self.open_lifetimes = {d: {"domain_id": d, "start_s": 0.0} for d in self.cells}
        self.initial_stores = {d: self.runtime.domains[d].stores() for d in self.cells}
        self._record_coarse()
        self._capture()
        self.pool = ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn"),
                                        initializer=_worker_init, initargs=(self.config,))

    def close(self) -> None:
        self.pool.shutdown(wait=True, cancel_futures=True)

    def _fine_domain(self, domain_id, time_s, temperatures):
        river = copy.deepcopy(self.fine_pristine[domain_id])
        start_at(river, time_s, temperatures)
        self._reapply(domain_id, river)
        return RiverSegmentDomain(domain_id, river, dt_s=self.dt_s)

    def _coarse_domain(self, domain_id, time_s, temperatures):
        river = copy.deepcopy(self.coarse_pristine[domain_id][0])
        start_at(river, time_s, temperatures)
        self._reapply(domain_id, river)
        return CoarseRiverSegmentDomain(domain_id, river, dt_s=self.quantum_s)

    def _reapply(self, domain_id, river):
        """Apply the accepted interventions of a segment, in time order, to a river built at the frontier."""
        for item in self.interventions:
            if item["domain_id"] == domain_id:
                for name, value in item["changes"].items():
                    river.set_forcing(name, river.time_s, value)

    def _blank_domain(self, domain_id, model_id):
        """Return an unstepped segment domain in a recorded representation, ready for restore()."""
        if model_id == RiverSegmentDomain.model_id:
            return RiverSegmentDomain(domain_id, copy.deepcopy(self.fine_pristine[domain_id]), dt_s=self.dt_s)
        if model_id == CoarseRiverSegmentDomain.model_id:
            return CoarseRiverSegmentDomain(domain_id, copy.deepcopy(self.coarse_pristine[domain_id][0]),
                                            dt_s=self.quantum_s)
        raise ValueError(f"unknown segment representation {model_id!r}")

    def _close_lifetime(self, domain_id):
        domain = self.runtime.domains[domain_id]
        budget = domain.river.budget()
        return dict(self.open_lifetimes[domain_id], end_s=self.runtime.time_s,
                    representation=domain.representation, storage_change_j=budget["storage_change_j"],
                    heat_residual_j=budget["heat_residual_j"],
                    **{k: budget[k] for k in BUDGET_TERMS_J},
                    **{k: budget[k] for k in ("boundary_input_m3", "lateral_input_m3", "outlet_export_m3")})

    def _swap(self, domain_id, replacement, reason, reconciliation_j=()):
        self.lifetimes.append(self._close_lifetime(domain_id))
        removed = self.runtime.remove_domain(domain_id)["entry"]
        added = self.runtime.add_domain(replacement)
        self.open_lifetimes[domain_id] = {"domain_id": domain_id, "start_s": self.runtime.time_s}
        old, new = removed["stores"], added["stores"]
        self.swaps.append({"t_s": self.runtime.time_s, "domain_id": domain_id, "reason": reason,
                           "from": removed["model_id"], "to": added["model_id"],
                           "water_relative": abs(old["water_m3"] - new["water_m3"]) / old["water_m3"],
                           "heat_relative": abs(old["heat_j"] - new["heat_j"]) / abs(old["heat_j"]),
                           "reconciliation_j": list(reconciliation_j)})

    def _retire(self, domain_id, wall_s):
        fine = self.runtime.domains[domain_id]
        temps = list(fine.river.temperature_c)
        groups = self.coarse_pristine[domain_id][1]
        coarse = restrict_temperatures(fine.river.cells, temps, groups)
        self.last_fine[domain_id] = (self.runtime.time_s, temps)
        self._swap(domain_id, self._coarse_domain(domain_id, self.runtime.time_s, coarse), "retire")
        self.leave_wall.pop(domain_id, None)
        self.events.append({"wall_s": wall_s, "t_s": self.runtime.time_s, "domain_id": domain_id,
                            "event": "retired"})

    def _install(self, domain_id, temperatures, wall_s):
        coarse = self.runtime.domains[domain_id]
        groups = self.coarse_pristine[domain_id][1]
        fine_cells = self.fine_pristine[domain_id].cells
        temps, shifts = prolong_temperatures(fine_cells, temperatures, list(coarse.river.temperature_c), groups,
                                             coarse.river.rho_cp)
        self._swap(domain_id, self._fine_domain(domain_id, self.runtime.time_s, temps), "install", shifts)
        self.events.append({"wall_s": wall_s, "t_s": self.runtime.time_s, "domain_id": domain_id,
                            "event": "installed"})

    def _record_coarse(self):
        for domain_id, domain in self.runtime.domains.items():
            if domain.representation == "coarse":
                self.coarse_history[domain_id].append((self.runtime.time_s, list(domain.river.temperature_c)))

    def _faces(self, domain_id, start_s, end_s):
        k = next(i for i, s in enumerate(self.specs) if s.domain_id == domain_id)
        def entries(face):
            return [e for e in self.face_history[face.interface_id]
                    if e[0] >= start_s - 1e-9 and e[1] <= end_s + 1e-9]
        inlet = entries(self.interfaces[k - 1]) if k > 0 else []
        outlet = entries(self.interfaces[k]) if k < len(self.interfaces) else []
        return inlet, outlet

    def _start_state(self, domain_id):
        """Return the replay start time, fine temperatures and their source for an activation."""
        frontier = self.runtime.time_s
        last = self.last_fine.get(domain_id)
        if last is not None and frontier - last[0] <= self.checkpoint_fresh_s:
            return last[0], list(last[1]), "fine_checkpoint"
        start_s = max(0.0, frontier - self.spinup_s)
        if start_s == 0.0 and last is None:
            return 0.0, list(self.fine_pristine[domain_id].temperature_c), "published_initial_state"
        entries = [e for e in self.coarse_history[domain_id] if e[0] <= start_s + 1e-9]
        t_s, coarse = entries[-1] if entries else self.coarse_history[domain_id][0]
        groups = self.coarse_pristine[domain_id][1]
        temps = [0.0] * self.cells[domain_id]
        for (lo, hi), value in zip(groups, coarse):
            temps[lo:hi] = [value] * (hi - lo)
        return t_s, temps, "coarse_prolonged"

    def _submit(self, domain_id, start_s, temperatures, wall_s, kind):
        spec = self.by_id[domain_id]
        frontier = self.runtime.time_s
        inlet, outlet = self._faces(domain_id, start_s, frontier)
        changes = [(item["at_s"], item["changes"]) for item in self.interventions if item["domain_id"] == domain_id]
        future = self.pool.submit(spinup_job, spec.lo, spec.hi, start_s, list(temperatures), inlet, outlet,
                                  frontier, self.dt_s, changes)
        self.jobs[domain_id] = _Job(future, wall_s, kind)

    def _discard_jobs(self):
        """Cancel every spin-up in flight; the next update resubmits the target segments."""
        for job in self.jobs.values():
            job.future.cancel()
        self.jobs = {}

    def _collect(self, wall_s, target):
        """Install finished jobs at the frontier and resubmit stale results as catch-up jobs."""
        progressed = True
        while progressed:
            progressed = False
            for domain_id, job in list(self.jobs.items()):
                if not self.virtual_wall and not job.future.done():
                    continue
                result = job.future.result()
                ready_wall = job.submit_wall_s + result["wall_s"] if self.virtual_wall else wall_s
                if ready_wall > wall_s + 1e-9:
                    continue
                del self.jobs[domain_id]
                progressed = True
                rate = result["cell_seconds"] / max(result["wall_s"], 1e-9)
                self.worker_rate = rate if self.worker_rate is None else 0.8 * self.worker_rate + 0.2 * rate
                if domain_id not in target or self.runtime.domains[domain_id].representation != "coarse":
                    continue
                if result["end_s"] < self.runtime.time_s - 1e-9:
                    self._submit(domain_id, result["end_s"], result["temperature_c"], ready_wall, "catch_up")
                else:
                    self._install(domain_id, result["temperature_c"], wall_s)

    def lead_wall_s(self, time_scale: float) -> float:
        """Return the activation lead time in wall seconds from the measured spin-up cost."""
        rate = self.worker_rate or self.capacity
        if rate is None:
            return self.lead_margin_s
        cost = max(self.cells.values()) * min(self.spinup_s, max(self.runtime.time_s, self.quantum_s))
        return cost / rate + self.lead_margin_s

    def update(self, wall_s: float, position_m: float, velocity_mps: float, time_scale: float) -> dict:
        """Apply the residency policy at a quantum boundary; return the residency report."""
        wall_s = finite(wall_s, "wall_s")
        lead = self.lead_wall_s(time_scale)
        ranked = anticipation(self.specs, position_m, velocity_mps, lead, time_scale)
        admission = admit(ranked, self.cells, self.capacity, time_scale, utilization=self.utilization)
        target = set(admission.fine)
        self._collect(wall_s, target)
        for domain_id in admission.fine:
            domain = self.runtime.domains[domain_id]
            if domain.representation == "fine":
                self.leave_wall.pop(domain_id, None)
            elif domain_id not in self.jobs:
                start_s, temps, source = self._start_state(domain_id)
                self._submit(domain_id, start_s, temps, wall_s, source)
                self.events.append({"wall_s": wall_s, "t_s": self.runtime.time_s, "domain_id": domain_id,
                                    "event": "activating", "source": source})
        for domain_id in [d for d in self.jobs if d not in target]:
            self.jobs.pop(domain_id).future.cancel()
            self.events.append({"wall_s": wall_s, "t_s": self.runtime.time_s, "domain_id": domain_id,
                                "event": "activation_discarded"})
        for domain_id, domain in list(self.runtime.domains.items()):
            if domain.representation == "fine" and domain_id not in target:
                left = self.leave_wall.setdefault(domain_id, wall_s)
                if wall_s - left >= self.retire_after_s - 1e-9:
                    self._retire(domain_id, wall_s)
        here = self.specs[_segment_at(self.specs, position_m)].domain_id
        fine = [d for d, dom in self.runtime.domains.items() if dom.representation == "fine"]
        return {"wall_s": wall_s, "t_s": self.runtime.time_s, "position_m": position_m, "segment": here,
                "walker_on": self.runtime.domains[here].representation,
                "walker_temperature_c": self.temperature_at(position_m), "fine": fine,
                "coarse": [d for d in self.cells if d not in fine], "activating": sorted(self.jobs),
                "retiring": [d for d in fine if d not in target],
                "reach": [d for d, reason in ranked if reason == "reach"], "requested_rate": time_scale,
                "target": list(admission.fine), "ranked": ranked, "effective_rate": admission.effective_rate,
                "held": admission.held, "demand": admission.demand, "budget": admission.budget,
                "lead_wall_s": lead, "capacity_cell_s_per_s": self.capacity, "worker_rate": self.worker_rate}

    def temperature_at(self, position_m: float) -> float:
        """Return the water temperature in C of the resident cell holding a chainage."""
        spec = self.specs[_segment_at(self.specs, position_m)]
        river = self.runtime.domains[spec.domain_id].river
        x = min(max(position_m, spec.start_m), spec.end_m) - spec.start_m
        edge = 0.0
        for cell, value in zip(river.cells, river.temperature_c):
            edge += cell.length_m
            if x < edge:
                return value
        return river.temperature_c[-1]

    def advance(self, target_s: float, *, presentation_s: float | None = None) -> None:
        """Advance the runtime by one quantum and update capacity and interface histories.

        Frames and snapshots are pruned at the presentation time, else at the frontier."""
        start_s = self.runtime.time_s
        self._capture()
        self.runtime.advance_one(target_s)
        presentation_s = self.runtime.time_s if presentation_s is None else presentation_s
        self.runtime.prune(presentation_s)
        self._prune_snapshots(presentation_s)
        fine = [d for d in self.runtime.domains.values() if d.representation == "fine"]
        wall = math.fsum(d.last_advance_wall_s for d in fine)
        if fine and wall > 0:
            sample = sum(d.cell_count for d in fine) * (target_s - start_s) / wall
            self.capacity = sample if self.capacity is None else 0.8 * self.capacity + 0.2 * sample
        for interface in self.interfaces:
            self.face_history[interface.interface_id].append(interface.last_transfer)
        self._record_coarse()

    def tier_ledger(self) -> dict:
        """Close the water and heat budget over both tiers and every hand-off."""
        lifetimes = self.lifetimes + [self._close_lifetime(d) for d in self.cells]
        first, last = self.specs[0].domain_id, self.specs[-1].domain_id

        def total(key, ids=None):
            return math.fsum(item[key] for item in lifetimes if ids is None or item["domain_id"] in ids)

        heat_now = math.fsum(self.runtime.domains[d].stores().heat_j for d in self.cells)
        heat_start = math.fsum(s.heat_j for s in self.initial_stores.values())
        terms = (total("boundary_input_j", {first}), total("lateral_input_j"), total("surface_exchange_j"),
                 total("additional_heat_flux_j"), total("cell_heat_j"), -total("outlet_export_j", {last}))
        external = math.fsum(terms)
        throughput = math.fsum(abs(x) for x in terms)
        faces = []
        for up, down in zip(self.specs, self.specs[1:]):
            exported = total("outlet_export_j", {up.domain_id})
            received = total("boundary_input_j", {down.domain_id})
            water_out = total("outlet_export_m3", {up.domain_id})
            water_in = total("boundary_input_m3", {down.domain_id})
            faces.append({"face": f"{up.domain_id}:{down.domain_id}",
                          "heat_relative": abs(exported - received) / max(abs(exported), 1e-300),
                          "water_relative": abs(water_out - water_in) / max(water_out, 1e-300)})
        water_in = math.fsum((total("boundary_input_m3", {first}), total("lateral_input_m3")))
        water_out = total("outlet_export_m3", {last})
        return {"heat_change_j": heat_now - heat_start, "external_flux_j": external,
                "heat_closure_relative": abs(heat_now - heat_start - external) / max(throughput, 1e-300),
                "throughput_j": throughput, "faces": faces,
                "water_closure_relative": abs(water_in - water_out) / max(water_in, 1e-300),
                "dispersion_cell_heat_j": total("cell_heat_j"),
                "lifetimes": len(lifetimes), "swaps": len(self.swaps)}

    def _capture(self) -> None:
        """Record the composite state at the frontier for rollback and committed saves."""
        runtime = self.runtime
        self._snapshots[runtime.time_s] = {
            "t_s": runtime.time_s, "revision": runtime.revision,
            "domains": {key: domain.checkpoint() for key, domain in runtime.domains.items()},
            "couplers": [coupler.checkpoint() for coupler in runtime.couplers],
            "membership": len(runtime.membership), "events": len(runtime.events),
            "interventions": len(self.interventions), "lifetimes": len(self.lifetimes), "swaps": len(self.swaps),
            "last_fine": dict(self.last_fine), "open_lifetimes": dict(self.open_lifetimes)}

    def _prune_snapshots(self, presentation_s: float) -> None:
        """Keep the snapshots from the latest one at or before the retained frame window."""
        cutoff = presentation_s - self.runtime.history_s
        anchors = [t for t in self._snapshots if t <= cutoff]
        if anchors:
            keep = max(anchors)
            self._snapshots = {t: snap for t, snap in self._snapshots.items() if t >= keep}

    def _restore_snapshot(self, snap: dict) -> None:
        """Return the runtime and the residency histories to a snapshot; spin-ups in flight are discarded."""
        self._discard_jobs()
        t_s = snap["t_s"]
        domains = []
        for key, saved in snap["domains"].items():
            domain = self._blank_domain(key, saved["model_id"])
            domain.restore(saved)
            domains.append(domain)
        runtime = self.runtime
        runtime.reset_to(domains, snap["couplers"], t_s, snap["revision"], runtime.membership[:snap["membership"]],
                         runtime.events[:snap["events"]])
        for history in self.face_history.values():
            while history and history[-1][1] > t_s + 1e-9:
                history.pop()
        for history in self.coarse_history.values():
            while history and history[-1][0] > t_s + 1e-9:
                history.pop()
        self.lifetimes = self.lifetimes[:snap["lifetimes"]]
        self.swaps = self.swaps[:snap["swaps"]]
        self.interventions = self.interventions[:snap["interventions"]]
        self.last_fine, self.open_lifetimes = dict(snap["last_fine"]), dict(snap["open_lifetimes"])
        self.leave_wall = {d: w for d, w in self.leave_wall.items() if runtime.domains[d].representation == "fine"}

    def _hold(self) -> tuple:
        """Return the runtime token and copies of the residency state for _release()."""
        return (self.runtime.state_token(),
                {k: deque(v, maxlen=v.maxlen) for k, v in self.face_history.items()},
                {k: deque(v, maxlen=v.maxlen) for k, v in self.coarse_history.items()},
                list(self.lifetimes), list(self.swaps), list(self.interventions), dict(self.last_fine),
                dict(self.open_lifetimes), dict(self.leave_wall), dict(self._snapshots), self.capacity)

    def _release(self, held: tuple) -> None:
        """Return to the state recorded by _hold()."""
        (token, self.face_history, self.coarse_history, self.lifetimes, self.swaps, self.interventions,
         self.last_fine, self.open_lifetimes, self.leave_wall, self._snapshots, self.capacity) = held
        self.runtime.reinstate(token)

    def _check_changes(self, domain_id: str, changes: dict) -> None:
        """Refuse a forcing change that either representation or an interface cannot carry."""
        if not isinstance(changes, dict) or not changes:
            raise ValueError("an intervention names at least one forcing")
        head = domain_id == self.specs[0].domain_id
        for name, value in changes.items():
            if not isinstance(name, str) or name.startswith("cell_heat_w."):
                raise ValueError(f"forcing {name!r} names a representation-specific cell under segment residency")
            if name in ("boundary_m3_s", "boundary_c") and not head:
                raise ValueError(f"{name} of {domain_id} is set by its upstream interface")
            if name == "boundary_m3_s" and not finite(value, name) > 0:
                raise ValueError("boundary_m3_s must stay positive so that every interface carries water")
        for river in (copy.deepcopy(self.fine_pristine[domain_id]), copy.deepcopy(self.coarse_pristine[domain_id][0])):
            for name, value in changes.items():
                river.set_forcing(name, 0.0, value)

    def intervene(self, event_id: str, domain_id: str, at_s: float, changes: dict) -> dict:
        """Apply a segment forcing change at its time, recomputing from the latest snapshot before it.

        Rebuilt segments and spin-ups carry the change; a failure leaves the prior state."""
        prior = self.runtime.prior_event(event_id, domain_id, at_s, changes)
        if prior is not None:
            return prior
        if domain_id not in self.by_id:
            raise ValueError("unknown intervention domain")
        at_s = finite(at_s, "at_s")
        times = [t for t in self._snapshots if t <= at_s + 1e-9]
        if not times or at_s > self.runtime.time_s + 1e-9:
            raise ValueError("event is outside the retained residency snapshots")
        if self.runtime.events and at_s < self.runtime.events[-1]["at_s"]:
            raise ValueError("late event precedes committed event history")
        self._check_changes(domain_id, changes)
        held = self._hold()
        try:
            self._restore_snapshot(self._snapshots[max(times)])
            # Replay on the quantum grid so interface quanta match the original timeline.
            while self.runtime.time_s < at_s - 1e-9:
                boundary = (math.floor(self.runtime.time_s / self.quantum_s + 1e-8) + 1) * self.quantum_s
                self.advance(min(at_s, boundary))
            self.runtime.domains[domain_id].intervene(copy.deepcopy(changes))
            result = self.runtime.record_event(event_id, domain_id, at_s, changes)
            self.interventions.append({"event_id": event_id, "domain_id": domain_id, "at_s": at_s,
                                       "changes": copy.deepcopy(changes)})
            self.runtime.restart_history()
            self._snapshots = {}
            self._capture()
        except BaseException:
            self._release(held)
            raise
        return result

    def identity(self) -> dict:
        """Return the replay, epoch, segmentation and numerical policy a saved state belongs to."""
        from yellowstone_python.service.live.state_codec import encode_value
        return {"config_sha256": hashlib.sha256(canonical(encode_value(self.config))).hexdigest(),
                "epoch_unix": self.runtime.epoch_unix,
                "segments": [[s.domain_id, s.lo, s.hi] for s in self.specs],
                "coarse_groups": {d: [list(g) for g in self.coarse_pristine[d][1]] for d in self.cells},
                "quantum_s": self.quantum_s, "dt_s": self.dt_s, "spinup_s": self.spinup_s,
                "checkpoint_fresh_s": self.checkpoint_fresh_s}

    def _document(self, snap: dict) -> dict:
        """Return the portable state document of a snapshot with the histories up to its time."""
        from yellowstone_python.service.live.state_codec import encode_value
        t_s, runtime = snap["t_s"], self.runtime

        def river(state):
            return {f.name: encode_value(getattr(state, f.name)) for f in dataclasses.fields(state)}

        return {"schema": RESIDENCY_STATE_SCHEMA, "identity": self.identity(),
                "model_versions": residency_model_versions(), "time_s": t_s, "revision": snap["revision"],
                "domains": {k: {"model_id": c["model_id"], "river": river(c["state"])}
                            for k, c in snap["domains"].items()},
                "couplers": snap["couplers"], "membership": runtime.membership[:snap["membership"]],
                "events": runtime.events[:snap["events"]], "interventions": self.interventions[:snap["interventions"]],
                "face_history": {k: [list(e) for e in v if e[1] <= t_s + 1e-9] for k, v in self.face_history.items()},
                "coarse_history": {k: [[s, list(temps)] for s, temps in v if s <= t_s + 1e-9]
                                   for k, v in self.coarse_history.items()},
                "last_fine": {k: [s, list(temps)] for k, (s, temps) in snap["last_fine"].items()},
                "lifetimes": self.lifetimes[:snap["lifetimes"]], "swaps": self.swaps[:snap["swaps"]],
                "open_lifetimes": snap["open_lifetimes"],
                "initial_stores": {k: [s.water_m3, s.heat_j, s.solute_kg] for k, s in self.initial_stores.items()}}

    def save_committed(self, store, world_id: str, presentation_s: float) -> float:
        """Persist the latest composite state at or before the presentation time; return its time.

        The frontier state is committed once the presentation clock has reached it."""
        presentation_s = finite(presentation_s, "presentation_s")
        if self.runtime.time_s <= presentation_s + 1e-9:
            self._capture()
        committed = [t for t in self._snapshots if t <= presentation_s + 1e-9]
        if not committed:
            raise ValueError("no committed residency state at or before the presentation time")
        snap = self._snapshots[max(committed)]
        document = self._document(snap)
        store.save(world_id, RESIDENCY_STATE_SCHEMA, snap["t_s"], snap["revision"], document, document["events"])
        return snap["t_s"]

    def load_committed(self, store, world_id: str) -> bool:
        """Restore a saved composite state; return False when the store holds none for the world."""
        from yellowstone_python.service.live.state_codec import decode_value
        saved = store.load(world_id, RESIDENCY_STATE_SCHEMA)
        if saved is None:
            return False
        document = saved["checkpoint"]
        if document.get("schema") != RESIDENCY_STATE_SCHEMA:
            raise ValueError("unknown residency state schema; explicit save migration required")
        if document["identity"] != json.loads(canonical(self.identity())):
            raise ValueError("saved residency state belongs to a different replay, epoch, segmentation "
                             "or numerical policy")
        current = residency_model_versions()
        drift = sorted(m for m in current if document["model_versions"].get(m) != current[m])
        if drift:
            raise ValueError("model source changed since the save: " + ", ".join(drift))
        domains = []
        for domain_id in self.cells:
            entry = document["domains"][domain_id]
            domain = self._blank_domain(domain_id, entry["model_id"])
            state = RiverState(**{name: decode_value(value) for name, value in entry["river"].items()})
            domain.restore({"model_id": entry["model_id"], "state": state})
            domains.append(domain)
        self._discard_jobs()
        self.runtime.reset_to(domains, document["couplers"], document["time_s"], document["revision"],
                              document["membership"], document["events"])
        self.interventions = document["interventions"]
        for key, history in self.face_history.items():
            history.clear()
            history.extend(tuple(e) for e in document["face_history"][key])
        for key, history in self.coarse_history.items():
            history.clear()
            history.extend((s, temps) for s, temps in document["coarse_history"][key])
        self.last_fine = {k: (s, temps) for k, (s, temps) in document["last_fine"].items()}
        self.lifetimes, self.swaps = document["lifetimes"], document["swaps"]
        self.open_lifetimes = document["open_lifetimes"]
        self.initial_stores = {k: Stores(*v) for k, v in document["initial_stores"].items()}
        self.leave_wall = {}
        self._snapshots = {}
        self._capture()
        return True

def run_walk(manager: ResidencyManager, start_m: float, end_m: float, speed_mps: float,
             time_scale: float = 1.0) -> list[dict]:
    """Walk downstream along the chainage, one residency update per quantum; return the reports."""
    reports, wall = [], 0.0
    while True:
        position = min(start_m + speed_mps * wall, end_m)
        report = manager.update(wall, position, speed_mps, time_scale)
        reports.append(report)
        if position >= end_m:
            return reports
        manager.advance(manager.runtime.time_s + manager.quantum_s)
        wall += manager.quantum_s / report["effective_rate"]

def evaluate_walk(manager: ResidencyManager, reports: list[dict], start_m: float, speed_mps: float) -> dict:
    """Return the walk acceptance metrics: arrivals, retirements, hand-offs, admission and ledger."""
    end_m = reports[-1]["position_m"]
    installs = {}
    for event in manager.events:
        if event["event"] == "installed":
            installs.setdefault(event["domain_id"], event["wall_s"])
    arrivals = []
    for spec in manager.specs:
        if start_m < spec.start_m <= end_m:
            arrival = (spec.start_m - start_m) / speed_mps
            install = installs.get(spec.domain_id)
            arrivals.append({"domain_id": spec.domain_id, "arrival_wall_s": arrival, "install_wall_s": install,
                             "lead_s": None if install is None else arrival - install})
    retirements = []
    for event in manager.events:
        if event["event"] != "retired":
            continue
        targeted = [r["wall_s"] for r in reports
                    if r["wall_s"] < event["wall_s"] and event["domain_id"] in r["target"]]
        left = next(r["wall_s"] for r in reports if r["wall_s"] > max(targeted, default=-1.0))
        retirements.append({"domain_id": event["domain_id"], "left_wall_s": left, "retired_wall_s": event["wall_s"],
                            "delay_s": event["wall_s"] - left})
    reach_m = speed_mps * max(manager.lead_margin_s, REACH_LOOKAHEAD_S)
    final = reports[-1]
    # Upstream halo segments stay targeted behind the walker, more of them at higher time scales.
    passed = [s.domain_id for s in manager.specs
              if s.end_m < final["position_m"] - reach_m and s.domain_id not in final["target"]]
    held = [r for r in reports if r["held"]]
    unreported = [r for r in reports if not r["held"]
                  and sum(manager.cells[d] for d in r["reach"]) * r["requested_rate"] > r["budget"] * (1 + 1e-12)]
    return {"arrivals": arrivals, "retirements": retirements,
            "activated_before_arrival": all(a["lead_s"] is not None and a["lead_s"] > 0 for a in arrivals),
            "reports_on_coarse": sum(1 for r in reports if r["walker_on"] != "fine"),
            "max_retire_delay_s": max((r["delay_s"] for r in retirements), default=0.0),
            "passed_segments_coarse": all(d in final["coarse"] for d in passed), "passed_segments": passed,
            "max_fine": max(len(r["fine"]) for r in reports),
            "max_swap_water_relative": max((s["water_relative"] for s in manager.swaps), default=0.0),
            "max_swap_heat_relative": max((s["heat_relative"] for s in manager.swaps), default=0.0),
            "max_reconciliation_j": max((abs(x) for s in manager.swaps for x in s["reconciliation_j"]), default=0.0),
            "admission_inside_budget": all(r["demand"] <= r["budget"] * (1 + 1e-12) or r["held"] for r in reports),
            "held_updates": len(held), "unreported_holds": len(unreported),
            "max_held_rate_relative": max((abs(r["effective_rate"] * sum(manager.cells[d] for d in r["reach"])
                                               - r["budget"]) / r["budget"] for r in held), default=0.0),
            "min_effective_rate": min(r["effective_rate"] for r in reports),
            "ledger": manager.tier_ledger(), "updates": len(reports), "swaps": len(manager.swaps)}

def firehole_residency(document: dict, **kwargs) -> tuple[ResidencyManager, RiverChainage]:
    """Return the Firehole residency manager and its chainage map from a published river replay."""
    from yellowstone_python.service.live.engine import replay_config
    replay = document.get("replay", document)
    epoch = replay.get("simulation_time", {}).get("start_epoch_unix")
    if epoch is not None:
        kwargs.setdefault("epoch_unix", epoch)
    manager = ResidencyManager(replay_config(replay), list(FIREHOLE_FACES), **kwargs)
    chainage = RiverChainage(replay["cells"])
    for spec in manager.specs:
        first, last = chainage.pieces[spec.lo], chainage.pieces[spec.hi - 1]
        if abs(first[4] - spec.start_m) > 1e-6 or abs(last[6] - spec.end_m) > 1e-6:
            manager.close()
            raise ValueError(f"solver chainage of {spec.domain_id} differs from the mapped cell chainage")
    return manager, chainage
