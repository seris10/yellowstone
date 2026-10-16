"""Branching well-mixed reservoir fixture with water, heat and solute ledgers.

Illustrative only; rates in 1/s, inflows in m3/s."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import copy
import math
from .contracts import finite, identifier

RHO_CP = 4_186_000.0  # J / (m^3 K), fixed authored water-property approximation

@dataclass
class Reservoir:
    node_id: str
    volume_m3: float
    heat_j: float
    solute_kg: float
    release_per_s: float

    @classmethod
    def at_temperature(cls, node_id, volume_m3, temperature_c, release_per_s, solute_kg=0.):
        return cls(node_id, volume_m3, RHO_CP * volume_m3 * temperature_c, solute_kg, release_per_s)

class ReservoirNetwork:
    model_id = "illustrative.reservoir_network.v1"

    def __init__(self, domain_id: str, nodes: list[Reservoir],
                 edges: list[tuple[str, str, float]], inputs: dict | None = None):
        self.domain_id = identifier(domain_id)
        self.nodes = {identifier(n.node_id): copy.deepcopy(n) for n in nodes}
        if not nodes or len(self.nodes) != len(nodes):
            raise ValueError("nonempty unique nodes required")
        self.edges = list(edges)
        self.inputs = copy.deepcopy(inputs or {})
        self.time_s = 0.0
        for n in self.nodes.values():
            if finite(n.volume_m3, "volume") <= 0 or finite(n.release_per_s, "release") < 0:
                raise ValueError("positive volume and nonnegative release required")
            finite(n.heat_j, "heat")
            if finite(n.solute_kg, "solute") < 0:
                raise ValueError("negative solute")
        fractions = dict.fromkeys(self.nodes, 0.)
        for source, target, fraction in edges:
            if source not in self.nodes or target not in self.nodes or source == target:
                raise ValueError("invalid network edge")
            if not 0 <= finite(fraction, "fraction") <= 1:
                raise ValueError("invalid split fraction")
            fractions[source] += fraction
        if any(f > 1 + 1e-12 for f in fractions.values()):
            raise ValueError("outgoing fractions exceed one")
        self._fractions = fractions
        self._validate_inputs(self.inputs)
        self.initial = self._totals()
        self.external_in = [0., 0., 0.]
        self.external_out = [0., 0., 0.]

    def _validate_inputs(self, inputs):
        for node_id, forcing in inputs.items():
            if node_id not in self.nodes:
                raise ValueError("unknown inlet node")
            if not isinstance(forcing, dict):
                raise ValueError("inlet forcing must be a mapping")
            if set(forcing) - {"flow_m3s", "temperature_c", "solute_kg_m3"}:
                raise ValueError("unsupported inlet quantity")
            if finite(forcing.get("flow_m3s", 0), "flow") < 0:
                raise ValueError("negative inflow")
            finite(forcing.get("temperature_c", 10.), "temperature")
            if finite(forcing.get("solute_kg_m3", 0.), "concentration") < 0:
                raise ValueError("negative concentration")

    def _totals(self):
        return [math.fsum(getattr(n, k) for n in self.nodes.values())
                for k in ("volume_m3", "heat_j", "solute_kg")]

    def advance_to(self, target_s):
        target_s = finite(target_s, "target_s")
        if target_s < self.time_s - 1e-9:
            raise ValueError("restore a checkpoint before rewinding")
        max_rate = max(n.release_per_s for n in self.nodes.values())
        max_dt = min(1., .25 / max_rate) if max_rate else 1.
        while self.time_s < target_s - 1e-10:
            dt = min(max_dt, target_s - self.time_s)
            outgoing = {}
            delta = {k: [0., 0., 0.] for k in self.nodes}
            for key, node in self.nodes.items():
                fraction = node.release_per_s * dt
                flux = [node.volume_m3 * fraction, node.heat_j * fraction, node.solute_kg * fraction]
                outgoing[key] = flux
                delta[key] = [-v for v in flux]
                remainder = max(0., 1. - self._fractions[key])
                for i in range(3):
                    self.external_out[i] += flux[i] * remainder
            for source, target, fraction in self.edges:
                for i in range(3):
                    delta[target][i] += outgoing[source][i] * fraction
            for target, source in self.inputs.items():
                volume = source.get("flow_m3s", 0.) * dt
                flux = [volume, volume * RHO_CP * source.get("temperature_c", 10.),
                        volume * source.get("solute_kg_m3", 0.)]
                for i in range(3):
                    delta[target][i] += flux[i]
                    self.external_in[i] += flux[i]
            for key, change in delta.items():
                node = self.nodes[key]
                node.volume_m3 += change[0]
                node.heat_j += change[1]
                node.solute_kg += change[2]
            self.time_s += dt
        self.time_s = target_s

    def snapshot(self):
        totals = self._totals()
        residual = [totals[i] - self.initial[i] - self.external_in[i] + self.external_out[i]
                    for i in range(3)]
        return {"domain_id": self.domain_id, "model_id": self.model_id, "t_s": self.time_s,
                "quality": "illustrative_not_field_validated",
                "nodes": [{"id": n.node_id, "volume_m3": n.volume_m3,
                           "temperature_c": n.heat_j / (RHO_CP * n.volume_m3) if n.volume_m3 > 0 else None,
                           "heat_j": n.heat_j, "solute_kg": n.solute_kg} for n in self.nodes.values()],
                "ledger": {"water_residual_m3": residual[0], "heat_residual_j": residual[1],
                           "solute_residual_kg": residual[2]}}

    def checkpoint(self):
        return copy.deepcopy({"model_id": self.model_id, "domain_id": self.domain_id,
             "time_s": self.time_s, "nodes": [asdict(n) for n in self.nodes.values()],
             "inputs": self.inputs, "edges": self.edges, "initial": self.initial,
             "external_in": self.external_in, "external_out": self.external_out})

    def restore(self, checkpoint):
        if checkpoint["model_id"] != self.model_id or checkpoint["domain_id"] != self.domain_id:
            raise ValueError("checkpoint identity mismatch")
        rebuilt = ReservoirNetwork(self.domain_id, [Reservoir(**n) for n in checkpoint["nodes"]],
                                   [tuple(edge) for edge in checkpoint["edges"]], checkpoint["inputs"])
        self.nodes, self.inputs = rebuilt.nodes, rebuilt.inputs
        self.edges, self._fractions = rebuilt.edges, rebuilt._fractions
        self.time_s = finite(checkpoint["time_s"], "checkpoint time")
        for key in ("initial", "external_in", "external_out"):
            setattr(self, key, list(checkpoint[key]))

    def intervene(self, changes):
        if set(changes) != {"inputs"}:
            raise ValueError("reference network accepts only an inputs replacement")
        self._validate_inputs(changes["inputs"])
        self.inputs = copy.deepcopy(changes["inputs"])
