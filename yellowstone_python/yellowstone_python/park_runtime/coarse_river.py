"""Coarse river segments: consecutive fine cells merged into conservative control volumes.

The coarse segment runs the same river heat solver; its state is labeled coarse."""
from __future__ import annotations
import dataclasses
import math
from yellowstone_python.river.river_transport import Cell, River
from .firehole_split import RiverSegmentDomain

COARSE_MODEL_ID = "yellowstone.river_segment_coarse.v1"

def coarse_groups(count: int, cells_per_coarse: int, breaks=()) -> list[tuple[int, int]]:
    """Return local fine-cell ranges, the last regular range taking the remainder.

    Each break index starts a range, so a lateral inflow mixes only into cells downstream of it."""
    if isinstance(cells_per_coarse, bool) or not isinstance(cells_per_coarse, int) or cells_per_coarse < 1:
        raise ValueError("cells_per_coarse must be a positive integer")
    edges = list(range(0, count, cells_per_coarse))
    if len(edges) > 1 and count - edges[-1] < cells_per_coarse:
        edges.pop()
    edges = sorted(set(edges) | {b for b in breaks if 0 < b < count} | {count})
    return [(lo, hi) for lo, hi in zip(edges, edges[1:])]

def coarse_river(segment: River, cells_per_coarse: int) -> tuple[River, list[tuple[int, int]]]:
    """Return the coarse river of an unstepped fine segment and its fine-cell groups."""
    if segment.time_s != 0.0 or segment.steps:
        raise ValueError("coarsen an unstepped segment")
    if any(series is not None for series in segment._cell_heat):
        raise NotImplementedError("coarse restriction of prescribed cell heat is not implemented")
    if any(value != 1.0 for value in segment._cell_shortwave_multiplier):
        raise NotImplementedError("coarse restriction of shortwave multipliers is not implemented")
    if any(zone is not None for zone in segment._hyporheic_zones):
        raise NotImplementedError("coarse restriction of hyporheic storage is not implemented")
    index = {cell.id: i for i, cell in enumerate(segment.cells)}
    groups = coarse_groups(len(segment.cells), cells_per_coarse, [index[s.cell_id] for s in segment.sources])
    cells, owner = [], {}
    for lo, hi in groups:
        members = segment.cells[lo:hi]
        length = math.fsum(c.length_m for c in members)
        area = math.fsum(c.surface_area_m2 for c in members)
        volume = math.fsum(c.volume_m3 for c in members)
        heat = math.fsum(c.volume_m3 * t for c, t in zip(members, segment.temperature_c[lo:hi]))
        cell_id = f"coarse:{members[0].id}:{members[-1].id}"
        cells.append(Cell(cell_id, length, area / length, volume, heat / volume,
                          dispersion_m2_s=math.fsum(c.dispersion_m2_s * c.length_m for c in members) / length,
                          exchange_w_m2_k=math.fsum(c.exchange_w_m2_k * c.surface_area_m2 for c in members) / area,
                          geometry_status="coarse_aggregate_of_fine_cells"))
        owner.update({c.id: cell_id for c in members})
    sources = [dataclasses.replace(source, cell_id=owner[source.cell_id]) for source in segment.sources]
    river = River(cells, segment.boundary_q_series, segment.boundary_c, sources=sources,
                  air_c=segment.air_c, net_heat_flux_w_m2=segment.net_heat_flux, rho_cp_j_m3_k=segment.rho_cp,
                  surface_budget=segment.surface_budget, max_surface_iterations=segment.max_surface_iterations,
                  surface_tolerance_c=segment.surface_tolerance_c, surface_relaxation=segment.surface_relaxation)
    return river, groups

def restrict_temperatures(fine_cells, temperatures, groups) -> list[float]:
    """Return volume-weighted coarse temperatures in C."""
    result = []
    for lo, hi in groups:
        volume = math.fsum(c.volume_m3 for c in fine_cells[lo:hi])
        result.append(math.fsum(c.volume_m3 * t for c, t in zip(fine_cells[lo:hi], temperatures[lo:hi])) / volume)
    return result

def prolong_temperatures(fine_cells, shape, coarse, groups, rho_cp) -> tuple[list[float], list[float]]:
    """Shift a fine profile per coarse cell to the coarse heat; return temperatures and shifts in J."""
    result, reconciliation_j = list(shape), []
    for (lo, hi), target_c in zip(groups, coarse):
        volume = math.fsum(c.volume_m3 for c in fine_cells[lo:hi])
        held = math.fsum(c.volume_m3 * t for c, t in zip(fine_cells[lo:hi], shape[lo:hi]))
        offset = target_c - held / volume
        for i in range(lo, hi):
            result[i] = shape[i] + offset
        reconciliation_j.append(rho_cp * volume * offset)
    return result, reconciliation_j

class CoarseRiverSegmentDomain(RiverSegmentDomain):
    """River segment on merged control volumes, advanced at one step per runtime quantum."""
    model_id = COARSE_MODEL_ID
    representation = "coarse"
