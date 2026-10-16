"""Conservative solute transport on replay river cells."""
from __future__ import annotations
from yellowstone_python.common.checks import nonnegative as _nonnegative

from dataclasses import dataclass, field
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import solve_banded

from yellowstone_python.river.river_transport import Cell, Series, finite, positive, solve_tridiagonal

SCHEMA = "yellowstone.solute_transport.v1"

# Supported solutes with the per-species label used on inputs and outputs.
SOLUTE_KEYS = ("chloride_mg_l", "arsenic_ug_l", "boron_mg_l")

# Default data file bundled with the package.
DEFAULT_SOLUTE_DATA = (
    Path(__file__).resolve().parents[1] / "data" / "hydrothermal_solutes.json"
)





def load_hydrothermal_solutes(path: Path | None = None) -> dict[str, Any]:
    """Load the bundled per-spring source chemistry data file."""
    source = DEFAULT_SOLUTE_DATA if path is None else Path(path)
    document = json.loads(source.read_text(encoding="utf-8"))
    if document.get("schema") != "yellowstone.hydrothermal_solutes.v1":
        raise ValueError(
            f"expected yellowstone.hydrothermal_solutes.v1, got "
            f"{document.get('schema')!r}"
        )
    return document


@dataclass(frozen=True)
class SoluteSource:
    """Lateral inflow with a per-solute concentration schedule."""

    id: str
    cell_id: str
    flow_m3_s: Any
    concentrations: dict[str, Any]
    status: str = "authored_representative_from_literature_range"

    def __post_init__(self) -> None:
        for name in ("id", "cell_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ValueError(f"{name} must be a nonempty string")
        flow = Series.parse(self.flow_m3_s)
        for value in flow.values:
            _nonnegative("source flow", value)
        object.__setattr__(self, "flow_m3_s", flow)
        if not isinstance(self.concentrations, dict) or not self.concentrations:
            raise ValueError(
                "source concentrations must be a nonempty mapping"
            )
        parsed: dict[str, Series] = {}
        for key, value in self.concentrations.items():
            if key not in SOLUTE_KEYS:
                raise ValueError(
                    f"unsupported solute {key!r}; expected one of "
                    f"{list(SOLUTE_KEYS)}"
                )
            series = Series.parse(value)
            for v in series.values:
                _nonnegative(f"concentration {key} on source {self.id}", v)
            parsed[key] = series
        object.__setattr__(self, "concentrations", parsed)


@dataclass
class BoundaryConcentrations:
    """Upstream boundary concentrations as scalars or scheduled series."""

    chloride_mg_l: Any = 0.0
    arsenic_ug_l: Any = 0.0
    boron_mg_l: Any = 0.0

    def as_series(self) -> dict[str, Series]:
        series = {
            "chloride_mg_l": Series.parse(self.chloride_mg_l),
            "arsenic_ug_l": Series.parse(self.arsenic_ug_l),
            "boron_mg_l": Series.parse(self.boron_mg_l),
        }
        for key, s in series.items():
            for value in s.values:
                _nonnegative(f"boundary {key}", value)
        return series


@dataclass
class SoluteTransport:
    """Multi-solute conservative transport on a shared river geometry."""

    cells: tuple[Cell, ...]
    boundary_m3_s: Any
    boundary_concentrations: BoundaryConcentrations
    sources: tuple[SoluteSource, ...] = ()
    initial_concentrations: dict[str, tuple[float, ...]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        self.cells = tuple(self.cells)
        if not self.cells:
            raise ValueError("at least one river cell is required")
        self.sources = tuple(self.sources)
        if len({c.id for c in self.cells}) != len(self.cells):
            raise ValueError("duplicate cell ids")
        if len({s.id for s in self.sources}) != len(self.sources):
            raise ValueError("duplicate source ids")

        self._boundary_q_series = Series.parse(self.boundary_m3_s)
        for value in self._boundary_q_series.values:
            _nonnegative("boundary flow", value)

        self._boundary_c_series = self.boundary_concentrations.as_series()

        indices = {cell.id: i for i, cell in enumerate(self.cells)}
        self._sources_by_cell: list[list[SoluteSource]] = [
            [] for _ in self.cells
        ]
        for source in self.sources:
            if source.cell_id not in indices:
                raise ValueError(
                    f"source {source.id!r} names unknown cell "
                    f"{source.cell_id!r}"
                )
            self._sources_by_cell[indices[source.cell_id]].append(source)

        self._lateral_q = [
            math.fsum(s.flow_m3_s.at(0.) for s in group)
            for group in self._sources_by_cell
        ]

        self._face_dispersion = self._compute_face_dispersion()
        self._volumes_m3 = np.asarray([cell.volume_m3 for cell in self.cells])
        self._dispersion_array = np.asarray(self._face_dispersion)
        self._source_groups_owner = None
        self._compiled_solutes = True
        self._matrix_cache = None

        self._concentrations: dict[str, list[float]] = {}
        for key in SOLUTE_KEYS:
            if key in self.initial_concentrations:
                values = list(self.initial_concentrations[key])
                if len(values) != len(self.cells):
                    raise ValueError(
                        f"initial_concentrations[{key}] must have one value "
                        f"per cell"
                    )
                for i, value in enumerate(values):
                    _nonnegative(f"initial {key} cell {i}", value)
                self._concentrations[key] = [float(v) for v in values]
            else:
                self._concentrations[key] = [
                    float(self._boundary_c_series[key].at(0.0))
                    for _ in self.cells
                ]

        self._initial = {
            key: tuple(values)
            for key, values in self._concentrations.items()
        }

        self._time_s = 0.0
        self.steps = 0

        forcing_series: list[Series] = [self._boundary_q_series]
        forcing_series.extend(self._boundary_c_series.values())
        for source in self.sources:
            forcing_series.extend(source.concentrations.values())
            forcing_series.append(source.flow_m3_s)
        self._forcing = tuple(forcing_series)

        self._totals: dict[str, dict[str, float]] = {
            key: {
                "boundary_input_mass": 0.0,
                "lateral_input_mass": 0.0,
                "outlet_export_mass": 0.0,
            }
            for key in SOLUTE_KEYS
        }
        self._water_totals = {
            "boundary_input_m3": 0.0,
            "lateral_input_m3": 0.0,
            "outlet_export_m3": 0.0,
        }
        self.max_advective_courant = 0.0
        self.max_diffusive_number = 0.0

    def _compute_face_dispersion(self) -> tuple[float, ...]:
        """Harmonic dispersive conductance per interior face (m3 per s)."""
        g = [0.0] * (len(self.cells) + 1)
        for j in range(1, len(self.cells)):
            left = self.cells[j - 1]
            right = self.cells[j]
            kl = left.dispersion_m2_s * left.cross_section_m2
            kr = right.dispersion_m2_s * right.cross_section_m2
            if kl > 0.0 and kr > 0.0:
                g[j] = 1.0 / (
                    left.length_m / (2.0 * kl)
                    + right.length_m / (2.0 * kr)
                )
        return tuple(g)

    def _face_flow_at(self, time_s: float) -> tuple[float, ...]:
        self._refresh_source_groups()
        cached = self._flow_cache
        if (cached is not None and cached[0] is self._boundary_q_series
                and cached[1] <= time_s < cached[2]):
            return cached[3]
        current = float(self._boundary_q_series.at(time_s))
        q = [current] * (len(self.cells) + 1)
        previous = 0
        until = self._boundary_q_series.next_change(time_s)
        for index, group in self._active_source_groups:
            q[previous:index + 1] = [current] * (index + 1 - previous)
            lateral_q = math.fsum(source.flow_m3_s.at(time_s) for source in group)
            current = finite("derived face discharge", math.fsum((current, lateral_q)), minimum=0.0)
            until = min(until, *(source.flow_m3_s.next_change(time_s) for source in group))
            previous = index + 1
        q[previous:] = [current] * (len(q) - previous)
        result = tuple(q)
        self._flow_cache = (self._boundary_q_series, time_s, until, result)
        return result

    def _refresh_source_groups(self) -> None:
        """Cache nonempty source groups and invalidate forcing-dependent calculations."""
        if self._source_groups_owner is self._sources_by_cell:
            return
        self._source_groups_owner = self._sources_by_cell
        self._active_source_groups = [(i, tuple(group)) for i, group in enumerate(self._sources_by_cell)
                                      if group]
        self._flow_cache = None
        self._source_qc_cache = {}
        self._matrix_cache = None

    def _source_qc(
        self, solute: str, time_s: float
    ) -> list[float]:
        self._refresh_source_groups()
        cached = self._source_qc_cache.get(solute)
        if cached is not None and cached[0] <= time_s < cached[1]:
            return cached[2]
        values = [0.0] * len(self.cells)
        until = math.inf
        for index, group in self._active_source_groups:
            values[index] = math.fsum(
                source.flow_m3_s.at(time_s) * source.concentrations[solute].at(time_s)
                for source in group
            )
            until = min(until, *(min(source.flow_m3_s.next_change(time_s),
                                    source.concentrations[solute].next_change(time_s))
                                 for source in group))
        self._source_qc_cache[solute] = (time_s, until, values)
        return values

    def _next_change(self) -> float:
        return min(
            series.next_change(self._time_s)
            for series in self._forcing
        )

    @property
    def time_s(self) -> float:
        return self._time_s

    def concentrations(self, solute: str) -> tuple[float, ...]:
        if solute not in SOLUTE_KEYS:
            raise ValueError(
                f"unknown solute {solute!r}; expected one of {list(SOLUTE_KEYS)}"
            )
        return tuple(self._concentrations[solute])

    def steady_concentrations(
        self, time_s: float = 0.0
    ) -> dict[str, tuple[float, ...]]:
        """Fixed point with forcing frozen at time_s."""
        time_s = finite("steady time", time_s, minimum=0.0)
        return {
            key: tuple(self._solve_tridiagonal_for(key, time_s))
            for key in SOLUTE_KEYS
        }

    def _solve_tridiagonal_for(
        self, solute: str, time_s: float, dt_s: float | None = None,
    ) -> list[float]:
        if not self._compiled_solutes:
            return self._solve_tridiagonal_reference(solute, time_s, dt_s)
        flows = self._face_flow_at(time_s)
        cached = self._matrix_cache
        if cached is None or cached[0] is not flows or cached[1] != dt_s:
            q = np.asarray(flows)
            g = self._dispersion_array
            bands = np.zeros((3, len(self.cells)))
            bands[0, 1:] = -g[1:-1]
            bands[2, :-1] = -(q[1:-1] + g[1:-1])
            bands[1] = q[1:] + g[:-1] + g[1:]
            storage = None if dt_s is None else self._volumes_m3 / dt_s
            if storage is not None:
                bands[1] += storage
            self._matrix_cache = (flows, dt_s, bands, storage)
        _, _, bands, storage = self._matrix_cache
        rhs = np.array(self._source_qc(solute, time_s))
        if storage is not None:
            rhs += storage * np.asarray(self._concentrations[solute])
        rhs[0] += flows[0] * self._boundary_c_series[solute].at(time_s)
        try:
            result = solve_banded((1, 1), bands, rhs, check_finite=True)
        except (ValueError, np.linalg.LinAlgError):
            return self._solve_tridiagonal_reference(solute, time_s, dt_s)
        if not np.isfinite(result).all():
            raise ArithmeticError("nonfinite solute solution")
        return result.tolist()

    def _solve_tridiagonal_reference(
        self,
        solute: str,
        time_s: float,
        dt_s: float | None = None,
    ) -> list[float]:
        n = len(self.cells)
        q = self._face_flow_at(time_s)
        g = self._face_dispersion
        source_qc = self._source_qc(solute, time_s)
        boundary_c = self._boundary_c_series[solute].at(time_s)

        lower = [0.0] * n
        diagonal = [0.0] * n
        upper = [0.0] * n
        rhs = [0.0] * n

        for i, cell in enumerate(self.cells):
            lower[i] = -(q[i] + g[i]) if i > 0 else 0.0
            diagonal[i] = q[i + 1] + g[i] + g[i + 1]
            upper[i] = -g[i + 1] if i + 1 < n else 0.0
            rhs[i] = source_qc[i]
            if dt_s is not None:
                storage = cell.volume_m3 / dt_s
                diagonal[i] += storage
                rhs[i] += storage * self._concentrations[solute][i]

        rhs[0] += q[0] * boundary_c

        return solve_tridiagonal(
            lower, diagonal, upper, rhs,
            cell_ids=[cell.id for cell in self.cells],
        )

    def step(self, dt_s: float) -> dict[str, float]:
        """Advance one interval; raises if the interval crosses a forcing change."""
        dt_s = positive("dt_s", dt_s)
        end_s = finite("step end time", self._time_s + dt_s)
        if end_s <= self._time_s:
            raise ValueError("dt_s is below clock floating-point resolution")
        if end_s > self._next_change():
            raise ValueError(
                "step crosses a forcing change; use run() or split the interval"
            )
        return self._advance_to(end_s)

    def _advance_to(self, end_s: float) -> dict[str, float]:
        start_s = self._time_s
        dt_s = end_s - start_s
        if dt_s <= 0.0 or end_s > self._next_change():
            raise ValueError("invalid integration interval")

        q = self._face_flow_at(start_s)
        g = self._face_dispersion
        n = len(self.cells)

        new: dict[str, list[float]] = {}
        step_record: dict[str, float] = {"dt_s": dt_s}

        for solute in SOLUTE_KEYS:
            solved = self._solve_tridiagonal_for(solute, start_s, dt_s)
            new[solute] = solved

            # Global mass balances use the upstream and outlet face fluxes.
            source_qc = self._source_qc(solute, start_s)
            boundary_c = self._boundary_c_series[solute].at(start_s)
            boundary_mass = dt_s * (q[0] * boundary_c)
            lateral_mass = dt_s * math.fsum(source_qc)
            outlet_mass = dt_s * (q[-1] * solved[-1])
            self._totals[solute]["boundary_input_mass"] += boundary_mass
            self._totals[solute]["lateral_input_mass"] += lateral_mass
            self._totals[solute]["outlet_export_mass"] += outlet_mass

            storage_change = math.fsum(
                cell.volume_m3 * (after - before)
                for cell, before, after in zip(
                    self.cells, self._concentrations[solute], solved
                )
            )
            expected = boundary_mass + lateral_mass - outlet_mass
            step_record[f"{solute}_mass_residual"] = storage_change - expected
            step_record[f"{solute}_outlet_mass"] = outlet_mass

        self._water_totals["boundary_input_m3"] += dt_s * q[0]
        self._water_totals["lateral_input_m3"] += dt_s * math.fsum(
            source.flow_m3_s.at(start_s) for source in self.sources
        )
        self._water_totals["outlet_export_m3"] += dt_s * q[-1]

        self.max_advective_courant = max(
            self.max_advective_courant,
            max(
                q[i + 1] * dt_s / cell.volume_m3
                for i, cell in enumerate(self.cells)
            ),
        )
        self.max_diffusive_number = max(
            self.max_diffusive_number,
            max(
                (g[i] + g[i + 1]) * dt_s / cell.volume_m3
                for i, cell in enumerate(self.cells)
            ),
        )

        for solute, values in new.items():
            self._concentrations[solute] = values
        self._time_s = end_s
        self.steps += 1
        return step_record

    def run(
        self,
        duration_s: float,
        dt_s: float = 1.0,
        sample_s: float = 60.0,
    ) -> list[dict[str, Any]]:
        """Advance for duration_s with the same forcing-split, sample-split structure the heat solver uses."""
        duration_s = finite("duration_s", duration_s, minimum=0.0)
        dt_s = positive("dt_s", dt_s)
        sample_s = positive("sample_s", sample_s)

        start_s = self._time_s
        finish_s = finite("run finish time", start_s + duration_s)
        frames = [self.snapshot()]

        if duration_s > 0.0 and finish_s <= start_s:
            raise ValueError("duration is below clock resolution")

        sample_index = 1
        while self._time_s < finish_s:
            target_s = min(
                finish_s, start_s + sample_index * sample_s
            )
            if target_s <= self._time_s:
                raise ArithmeticError("sample clock failed to advance")
            while self._time_s < target_s:
                end_s = min(
                    target_s,
                    self._time_s + dt_s,
                    self._next_change(),
                )
                if end_s <= self._time_s:
                    raise ArithmeticError(
                        "integration clock failed to advance"
                    )
                self._advance_to(end_s)
            frames.append(self.snapshot())
            sample_index += 1
        return frames

    def snapshot(self) -> dict[str, Any]:
        return {
            "t_s": self._time_s,
            "chloride_mg_l": list(self._concentrations["chloride_mg_l"]),
            "arsenic_ug_l": list(self._concentrations["arsenic_ug_l"]),
            "boron_mg_l": list(self._concentrations["boron_mg_l"]),
            "mass_budget": self.mass_budget(),
        }

    def mass_budget(self) -> dict[str, Any]:
        """Cumulative inputs, outputs and storage change per solute, with closure."""
        water = dict(self._water_totals)
        water_residual = math.fsum((
            water["boundary_input_m3"],
            water["lateral_input_m3"],
            -water["outlet_export_m3"],
        ))
        water_scale = max(
            1.0,
            abs(water["boundary_input_m3"]),
            abs(water["lateral_input_m3"]),
            abs(water["outlet_export_m3"]),
        )
        result: dict[str, Any] = {
            "steps": self.steps,
            "water_balance_m3": water,
            "water_residual_m3": water_residual,
            "water_relative_residual": abs(water_residual) / water_scale,
            "max_advective_courant": self.max_advective_courant,
            "max_diffusive_number": self.max_diffusive_number,
            "solutes": {},
        }
        for solute, totals in self._totals.items():
            storage_change = math.fsum(
                cell.volume_m3 * (after - before)
                for cell, before, after in zip(
                    self.cells,
                    self._initial[solute],
                    self._concentrations[solute],
                )
            )
            expected = math.fsum((
                totals["boundary_input_mass"],
                totals["lateral_input_mass"],
                -totals["outlet_export_mass"],
            ))
            scale = max(
                1.0,
                abs(totals["boundary_input_mass"]),
                abs(totals["lateral_input_mass"]),
                abs(totals["outlet_export_mass"]),
                abs(storage_change),
            )
            residual = storage_change - expected
            result["solutes"][solute] = {
                **totals,
                "storage_change_mass": storage_change,
                "expected_change_mass": expected,
                "mass_residual": residual,
                "mass_relative_residual": abs(residual) / scale,
            }
        return result


# Habitat response thresholds and the suitability multiplier.

def _ramp(value: float, low: float, high: float) -> float:
    """Linear ramp from 1 at or below low to 0 at or above high."""
    value = _nonnegative("concentration", value)
    low = _nonnegative("low threshold", low)
    high = _nonnegative("high threshold", high)
    if high <= low:
        raise ValueError("ramp high must exceed low")
    if value <= low:
        return 1.0
    if value >= high:
        return 0.0
    return 1.0 - (value - low) / (high - low)


def solute_habitat_multiplier(
    chloride_mg_l: float,
    arsenic_ug_l: float,
    boron_mg_l: float,
    thresholds: dict[str, Any] | None = None,
) -> dict[str, float]:
    """Per-cell salmonid suitability multiplier from the three solute stressors."""
    chloride_mg_l = _nonnegative("chloride_mg_l", chloride_mg_l)
    arsenic_ug_l = _nonnegative("arsenic_ug_l", arsenic_ug_l)
    boron_mg_l = _nonnegative("boron_mg_l", boron_mg_l)
    if thresholds is None:
        thresholds = load_hydrothermal_solutes()["aquatic_toxicity_thresholds"]
    cl = thresholds["chloride_mg_l"]
    as_ = thresholds["arsenic_ug_l"]
    b = thresholds["boron_mg_l"]
    chloride_factor = _ramp(
        chloride_mg_l,
        cl["chronic_mg_l"],
        cl["acute_mg_l"],
    )
    arsenic_factor = _ramp(
        arsenic_ug_l,
        as_["chronic_ug_l"],
        as_["acute_ug_l"],
    )
    boron_factor = _ramp(
        boron_mg_l,
        b["no_effect_mg_l"],
        b["effect_mg_l"],
    )
    combined = chloride_factor * arsenic_factor * boron_factor
    return {
        "chloride_factor": chloride_factor,
        "arsenic_factor": arsenic_factor,
        "boron_factor": boron_factor,
        "combined": combined,
    }


def solute_sources_for_mapped_sources(
    mapped_sources: list[dict[str, Any]],
    data_document: dict[str, Any] | None = None,
) -> list[SoluteSource]:
    """Translate mapped river_world lateral sources into SoluteSource records."""
    if data_document is None:
        data_document = load_hydrothermal_solutes()
    mapping = data_document.get("mapping_notes", {})
    features = data_document.get("features", {})
    out: list[SoluteSource] = []
    for entry in mapped_sources:
        source_id = entry.get("id")
        cell_id = entry.get("cell_id")
        flow_m3_s = entry.get("flow_m3_s")
        if not isinstance(source_id, str) or source_id not in mapping:
            raise ValueError(
                f"mapped source {source_id!r} has no entry in "
                f"hydrothermal_solutes.mapping_notes; add one or supply the "
                f"source explicitly"
            )
        if not isinstance(cell_id, str) or not cell_id:
            raise ValueError(
                f"mapped source {source_id!r} missing cell_id"
            )
        if flow_m3_s is None:
            raise ValueError(
                f"mapped source {source_id!r} missing flow_m3_s"
            )
        feature_id = mapping[source_id]["feature_id"]
        if feature_id not in features:
            raise ValueError(
                f"mapping_notes.{source_id}.feature_id {feature_id!r} is not "
                f"in features"
            )
        feature = features[feature_id]
        concentrations: dict[str, float] = {}
        for key in ("chloride_mg_l", "arsenic_ug_l", "boron_mg_l"):
            entry = feature.get(key, {}) if isinstance(feature, dict) else {}
            value = entry.get("value") if isinstance(entry, dict) else None
            if value is None:
                status = (
                    entry.get("status")
                    if isinstance(entry, dict) else "missing"
                )
                raise ValueError(
                    f"feature {feature_id!r} has no verified value for "
                    f"{key} (status {status!r}); supply the source "
                    f"explicitly or add a verified sample to the data file"
                )
            concentrations[key] = _nonnegative(f"source {source_id} {key}", value)
        out.append(SoluteSource(
            id=source_id,
            cell_id=cell_id,
            flow_m3_s=flow_m3_s,
            concentrations=concentrations,
            status=(
                "authored_representative_from_literature_range"
            ),
        ))
    return out


def transport_from_mapped_replay(
    replay_document: dict[str, Any],
    data_document: dict[str, Any] | None = None,
    boundary_concentrations: BoundaryConcentrations | None = None,
) -> SoluteTransport:
    """Build a SoluteTransport from a mapped river replay document."""
    cells_raw = replay_document.get("cells") or []
    cells = tuple(
        Cell(
            id=record["id"],
            length_m=record["length_m"],
            width_m=record["width_m"],
            volume_m3=record["volume_m3"],
            initial_c=record.get("initial_c", 0.0),
            dispersion_m2_s=record.get("dispersion_m2_s", 0.0),
            exchange_w_m2_k=record.get("exchange_w_m2_k", 0.0),
            geometry_status=record.get("geometry_status", "mapped_replay"),
        )
        for record in cells_raw
    )
    forcing = replay_document.get("forcing", {})
    boundary_m3_s = forcing.get("boundary_m3_s")
    mapped_sources = []
    for entry in forcing.get("sources", []):
        mapped_sources.append({
            "id": entry["id"],
            "cell_id": entry["cell_id"],
            "flow_m3_s": entry["flow_m3_s"],
        })
    if data_document is None:
        data_document = load_hydrothermal_solutes()
    sources = tuple(
        solute_sources_for_mapped_sources(mapped_sources, data_document)
    )
    if boundary_concentrations is None:
        baseline = data_document["features"]["firehole_upstream_boundary"]
        baseline_values: dict[str, float] = {}
        for key in ("chloride_mg_l", "arsenic_ug_l", "boron_mg_l"):
            entry = baseline.get(key, {})
            value = entry.get("value") if isinstance(entry, dict) else None
            if value is None:
                status = (
                    entry.get("status")
                    if isinstance(entry, dict) else "missing"
                )
                raise ValueError(
                    f"firehole_upstream_boundary has no value for {key} "
                    f"(status {status!r}); supply boundary_concentrations "
                    f"explicitly"
                )
            baseline_values[key] = _nonnegative(f"boundary {key}", value)
        boundary_concentrations = BoundaryConcentrations(
            chloride_mg_l=baseline_values["chloride_mg_l"],
            arsenic_ug_l=baseline_values["arsenic_ug_l"],
            boron_mg_l=baseline_values["boron_mg_l"],
        )
    return SoluteTransport(
        cells=cells,
        boundary_m3_s=boundary_m3_s,
        boundary_concentrations=boundary_concentrations,
        sources=sources,
    )


def transport_summary(transport: SoluteTransport) -> dict[str, Any]:
    """Compact JSON-ready description of a SoluteTransport state and budget."""
    budget = transport.mass_budget()
    return {
        "schema": SCHEMA,
        "status": "fitted_not_validated_single_window",
        "n_cells": len(transport.cells),
        "n_sources": len(transport.sources),
        "time_s": transport.time_s,
        "steps": transport.steps,
        "concentrations": {
            key: list(transport.concentrations(key))
            for key in SOLUTE_KEYS
        },
        "mass_budget": budget,
        "cell_ids": [cell.id for cell in transport.cells],
        "provenance": {
            "data_file": str(DEFAULT_SOLUTE_DATA.relative_to(
                DEFAULT_SOLUTE_DATA.parents[2]
            )),
            "transport_scheme": (
                "backward_euler_upwind_advection_centered_dispersion"
            ),
        },
    }


def _series_at_index(series_or_scalar: Any, time_s: float) -> float:
    if isinstance(series_or_scalar, Series):
        return float(series_or_scalar.at(time_s))
    return float(series_or_scalar)


def chloride_from_specific_conductance(
    sc_us_cm: float,
    slope_mg_l_per_us_cm: float,
    intercept_mg_l: float,
) -> float:
    """Linear conductance to chloride map; chloride is clamped at zero at very low conductance."""
    sc = _nonnegative("sc_us_cm", sc_us_cm)
    slope = finite("slope_mg_l_per_us_cm", slope_mg_l_per_us_cm)
    intercept = finite("intercept_mg_l", intercept_mg_l)
    result = slope * sc + intercept
    if result < 0.0:
        return 0.0
    return result


def fit_chloride_from_conductance(
    paired_samples: list[dict[str, float]],
) -> dict[str, float]:
    """Ordinary least squares fit of chloride on specific conductance."""
    if len(paired_samples) < 2:
        raise ValueError("need at least two paired samples to fit")
    xs: list[float] = []
    ys: list[float] = []
    for entry in paired_samples:
        xs.append(_nonnegative("sc_us_cm", entry["sc_us_cm"]))
        ys.append(_nonnegative("chloride_mg_l", entry["chloride_mg_l"]))
    n = len(xs)
    mean_x = math.fsum(xs) / n
    mean_y = math.fsum(ys) / n
    sxx = math.fsum((x - mean_x) ** 2 for x in xs)
    sxy = math.fsum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    if sxx == 0.0:
        raise ValueError("paired samples have zero conductance variance")
    slope = sxy / sxx
    intercept = mean_y - slope * mean_x
    syy = math.fsum((y - mean_y) ** 2 for y in ys)
    if syy == 0.0:
        r2 = 1.0 if sxy == 0.0 else 0.0
    else:
        residual_ss = math.fsum(
            (y - (slope * x + intercept)) ** 2 for x, y in zip(xs, ys)
        )
        r2 = 1.0 - residual_ss / syy
    return {
        "slope_mg_l_per_us_cm": slope,
        "intercept_mg_l": intercept,
        "n": n,
        "r_squared": r2,
    }
