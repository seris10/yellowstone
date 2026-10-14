"""Thermal-spring outflow routing on a 1 m DEM with MFD on filled terrain."""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Iterable

import numpy as np


SCHEMA = "yellowstone.outflow_network.v1"

CORE_CELL_M = 1.0
CORE_SIZE = 1280
CORE_HALF_M = 640.0

MFD_EXPONENT = 1.1

MIN_SEGMENT_LENGTH_M = 2.0
MIN_SPUR_FLOW_FRACTION = 0.1
TERMINAL_FLOW_PRESERVATION_TOLERANCE = 0.05

WEIR_CD_BROAD_CREST = 0.544
WEIR_G_M_S2 = 9.81
LIDAR_RIM_RMSE_Z_M = 0.1

METHOD_SOURCES = {
    "routing": {
        "name": "multiple_flow_direction_freeman_1991",
        "exponent": MFD_EXPONENT,
        "citation": ("Freeman, T. G. (1991). Calculating catchment area with "
                     "divergent flow based on a regular grid. Computers and "
                     "Geosciences 17, 413 to 422. doi:10.1016/0098-3004(91)90048-I."),
        "citation_verified": "partial",
    },
    "depression_fill": {
        "name": "priority_flood_epsilon",
        "citation": ("Barnes, R., Lehman, C., Mulla, D. (2014). Priority-flood: "
                     "an optimal depression-filling and watershed-labeling "
                     "algorithm for digital elevation models. Computers and "
                     "Geosciences 62, 117 to 127. doi:10.1016/j.cageo.2013.04.024."),
        "citation_verified": "yes",
    },
    "rim_injection": {
        "name": "broad_crested_weir_rim_overflow",
        "equation": "q_i = C_d * sqrt(g) * H_i^(3/2) per unit rim length",
        "C_d": WEIR_CD_BROAD_CREST,
        "g_m_s2": WEIR_G_M_S2,
        "citation": ("Chow, V. T. (1959). Open-Channel Hydraulics. McGraw-Hill, "
                     "section 3-7 broad-crested weir; Henderson, F. M. (1966). "
                     "Open Channel Flow. Macmillan, chapter 6."),
        "citation_verified": "partial",
        "rim_elevation_rmse_z_m": LIDAR_RIM_RMSE_Z_M,
        "rim_elevation_rmse_z_source": "USGS 3DEP QL2 1 m lidar RMSEz 0.10 m.",
    },
}


def weir_rim_injection(rim_elevations_m: Iterable[float],
                       discharge_m3_s: float,
                       cell_width_m: float = 1.0,
                       cd: float = WEIR_CD_BROAD_CREST,
                       g_m_s2: float = WEIR_G_M_S2,
                       max_head_m: float = 5.0,
                       tol_m: float = 1e-6) -> dict:
    """Rim-cell overflow weights by broad-crested weir equation."""
    z = np.asarray(list(rim_elevations_m), dtype=np.float64)
    if z.size == 0:
        raise ValueError("weir_rim_injection: rim is empty")
    if not np.all(np.isfinite(z)):
        raise ValueError("weir_rim_injection: rim elevations must be finite")
    if discharge_m3_s < 0:
        raise ValueError("weir_rim_injection: discharge must be non-negative")

    def _total(h: float) -> float:
        head = np.maximum(0.0, h - z)
        return float(cd * np.sqrt(g_m_s2)
                     * (head ** 1.5).sum() * cell_width_m)

    low = float(z.min())
    high = low + max_head_m
    while _total(high) < discharge_m3_s:
        high += max_head_m
        if high - low > 1000.0:
            raise ValueError(
                f"weir solver cannot bracket discharge {discharge_m3_s}")
    for _ in range(200):
        mid = 0.5 * (low + high)
        if _total(mid) < discharge_m3_s:
            low = mid
        else:
            high = mid
        if (high - low) < tol_m:
            break
    h_pool = 0.5 * (low + high)
    head = np.maximum(0.0, h_pool - z)
    flows = cd * np.sqrt(g_m_s2) * (head ** 1.5) * cell_width_m
    total = float(flows.sum())
    weights = (flows / total) if total > 0 else np.zeros_like(flows)
    active = int(np.count_nonzero(head > 0.0))
    return {
        "pool_stage_m": h_pool,
        "pool_stage_above_lowest_rim_m": h_pool - float(z.min()),
        "head_m": head.tolist(),
        "flows_m3_s": flows.tolist(),
        "weights": weights.tolist(),
        "n_rim": int(z.size),
        "n_active_rim": active,
        "cd": cd,
        "g_m_s2": g_m_s2,
        "cell_width_m": cell_width_m,
        "discharge_m3_s": discharge_m3_s,
        "total_m3_s": total,
    }


def rim_injection_sensitivity(rim_elevations_m: Iterable[float],
                              discharge_m3_s: float,
                              rmse_z_m: float = LIDAR_RIM_RMSE_Z_M,
                              cell_width_m: float = 1.0,
                              cd: float = WEIR_CD_BROAD_CREST,
                              g_m_s2: float = WEIR_G_M_S2,
                              n_samples: int = 20,
                              seed: int = 1) -> dict:
    """Weir distribution sensitivity under Gaussian elevation noise."""
    def _summary(z_shifted):
        res = weir_rim_injection(z_shifted, discharge_m3_s,
                                 cell_width_m=cell_width_m, cd=cd,
                                 g_m_s2=g_m_s2)
        weights = np.asarray(res["weights"], dtype=np.float64)
        order = np.argsort(-weights)
        cum = np.cumsum(weights[order])
        total_len = float(len(weights)) * cell_width_m
        active_len = float(res["n_active_rim"]) * cell_width_m
        idx_50 = int(np.searchsorted(cum, 0.5)) + 1
        idx_90 = int(np.searchsorted(cum, 0.9)) + 1
        return {
            "pool_stage_above_lowest_rim_m": round(
                res["pool_stage_above_lowest_rim_m"], 4),
            "n_active_rim": res["n_active_rim"],
            "active_rim_length_m": round(active_len, 3),
            "rim_length_carrying_50pct_m": round(idx_50 * cell_width_m, 3),
            "rim_length_carrying_90pct_m": round(idx_90 * cell_width_m, 3),
            "rim_length_total_m": round(total_len, 3),
        }
    z = np.asarray(list(rim_elevations_m), dtype=np.float64)
    nominal = _summary(z)
    rng = np.random.default_rng(seed)
    len_50: list[float] = []
    len_90: list[float] = []
    active: list[int] = []
    stage: list[float] = []
    for _ in range(n_samples):
        noise = rng.normal(0.0, rmse_z_m, size=z.shape)
        s = _summary(z + noise)
        len_50.append(s["rim_length_carrying_50pct_m"])
        len_90.append(s["rim_length_carrying_90pct_m"])
        active.append(s["n_active_rim"])
        stage.append(s["pool_stage_above_lowest_rim_m"])
    return {
        "rmse_z_m": rmse_z_m,
        "nominal": nominal,
        "noise_samples": n_samples,
        "noise_seed": seed,
        "monte_carlo": {
            "rim_length_carrying_50pct_m_min": round(float(min(len_50)), 3),
            "rim_length_carrying_50pct_m_median": round(
                float(np.median(len_50)), 3),
            "rim_length_carrying_50pct_m_max": round(float(max(len_50)), 3),
            "rim_length_carrying_90pct_m_min": round(float(min(len_90)), 3),
            "rim_length_carrying_90pct_m_median": round(
                float(np.median(len_90)), 3),
            "rim_length_carrying_90pct_m_max": round(float(max(len_90)), 3),
            "n_active_rim_min": int(min(active)),
            "n_active_rim_max": int(max(active)),
            "pool_stage_above_lowest_rim_m_min": round(float(min(stage)), 4),
            "pool_stage_above_lowest_rim_m_max": round(float(max(stage)), 4),
        },
    }


@dataclass(frozen=True)
class Grid:
    """1 m core grid in local meters; row index increases southward."""

    cell_m: float = CORE_CELL_M
    size: int = CORE_SIZE
    half_m: float = CORE_HALF_M

    def cell_center_xz(self, j: int, i: int) -> tuple[float, float]:
        """Return the (x, z) center of cell at row j, column i."""
        x = -self.half_m + 0.5 * self.cell_m + i * self.cell_m
        z = -self.half_m + 0.5 * self.cell_m + j * self.cell_m
        return x, z

    def world_to_index(self, x: float, z: float) -> tuple[int, int]:
        """Return (row j, column i) for a point in local meters."""
        i = int(math.floor((x + self.half_m) / self.cell_m))
        j = int(math.floor((z + self.half_m) / self.cell_m))
        return j, i

    def in_bounds(self, j: int, i: int) -> bool:
        return 0 <= j < self.size and 0 <= i < self.size


# Row and column offsets for the 8 neighbors (N, NE, E, SE, S, SW, W, NW).
_NEIGHBORS = (
    (-1, 0), (-1, 1), (0, 1), (1, 1),
    (1, 0), (1, -1), (0, -1), (-1, -1),
)


def _neighbor_distances(cell_m: float) -> np.ndarray:
    """Planar distances to each of the 8 neighbors in meters."""
    d = np.array([math.hypot(dj, di) for dj, di in _NEIGHBORS], dtype=np.float64)
    return d * cell_m


def polygon_mask(ring: Iterable[tuple[float, float]], grid: Grid) -> np.ndarray:
    """Rasterize a polygon ring (local xz meters) to a boolean mask."""
    pts = np.asarray(list(ring), dtype=np.float64)
    if pts.shape[0] < 3:
        raise ValueError("pool ring requires at least three points")
    xs = -grid.half_m + 0.5 * grid.cell_m + np.arange(grid.size) * grid.cell_m
    zs = -grid.half_m + 0.5 * grid.cell_m + np.arange(grid.size) * grid.cell_m
    mask = np.zeros((grid.size, grid.size), dtype=bool)
    n = pts.shape[0]
    for j, z in enumerate(zs):
        row = np.zeros(grid.size, dtype=bool)
        k = n - 1
        for m in range(n):
            x0, z0 = pts[m]
            x1, z1 = pts[k]
            if (z0 > z) != (z1 > z):
                xcross = (x1 - x0) * (z - z0) / (z1 - z0) + x0
                row ^= xs < xcross
            k = m
        mask[j, :] = row
    return mask


def rim_mask(pool: np.ndarray) -> np.ndarray:
    """Cells inside the pool mask with at least one neighbor outside."""
    out = np.zeros_like(pool, dtype=bool)
    h, w = pool.shape
    for dj, di in _NEIGHBORS:
        shifted = np.zeros_like(pool, dtype=bool)
        j0_src = max(0, -dj)
        j1_src = h - max(0, dj)
        i0_src = max(0, -di)
        i1_src = w - max(0, di)
        j0_dst = max(0, dj)
        j1_dst = h - max(0, -dj)
        i0_dst = max(0, di)
        i1_dst = w - max(0, -di)
        shifted[j0_dst:j1_dst, i0_dst:i1_dst] = pool[j0_src:j1_src, i0_src:i1_src]
        out |= pool & ~shifted
    return out & pool


def outer_rim_mask(pool: np.ndarray) -> np.ndarray:
    """Cells outside the pool mask with at least one neighbor inside the pool."""
    out = np.zeros_like(pool, dtype=bool)
    h, w = pool.shape
    for dj, di in _NEIGHBORS:
        shifted = np.zeros_like(pool, dtype=bool)
        j0_src = max(0, -dj)
        j1_src = h - max(0, dj)
        i0_src = max(0, -di)
        i1_src = w - max(0, di)
        j0_dst = max(0, dj)
        j1_dst = h - max(0, -dj)
        i0_dst = max(0, di)
        i1_dst = w - max(0, -di)
        shifted[j0_dst:j1_dst, i0_dst:i1_dst] = pool[j0_src:j1_src, i0_src:i1_src]
        out |= shifted & ~pool
    return out


def fill_depressions(dem: np.ndarray, epsilon: float = 1e-3) -> np.ndarray:
    """Priority-flood depression fill with an epsilon tilt on flats; float64 out."""
    if dem.ndim != 2:
        raise ValueError("dem must be 2D")
    h, w = dem.shape
    out = np.full_like(dem, np.inf, dtype=np.float64)
    closed = np.zeros_like(dem, dtype=bool)
    heap: list[tuple[float, int, int, int]] = []
    counter = 0
    for j in range(h):
        for i in (0, w - 1):
            heapq.heappush(heap, (float(dem[j, i]), counter, j, i))
            counter += 1
            closed[j, i] = True
    for i in range(w):
        for j in (0, h - 1):
            if not closed[j, i]:
                heapq.heappush(heap, (float(dem[j, i]), counter, j, i))
                counter += 1
                closed[j, i] = True
    while heap:
        elev, _, j, i = heapq.heappop(heap)
        out[j, i] = elev
        for dj, di in _NEIGHBORS:
            nj, ni = j + dj, i + di
            if 0 <= nj < h and 0 <= ni < w and not closed[nj, ni]:
                closed[nj, ni] = True
                raised = max(float(dem[nj, ni]), elev + epsilon)
                heapq.heappush(heap, (raised, counter, nj, ni))
                counter += 1
    return out


def mfd_weights(filled: np.ndarray, cell_m: float = CORE_CELL_M,
                exponent: float = MFD_EXPONENT,
                boundary_drop_m: float = 1e-3) -> np.ndarray:
    """Per-cell MFD weights to the 8 neighbors with an outward edge drop."""
    h, w = filled.shape
    weights = np.zeros((h, w, 8), dtype=np.float64)
    distances = _neighbor_distances(cell_m)
    edge_len = np.array([1.0, 1.0 / math.sqrt(2.0), 1.0,
                         1.0 / math.sqrt(2.0), 1.0,
                         1.0 / math.sqrt(2.0), 1.0,
                         1.0 / math.sqrt(2.0)]) * cell_m
    for k, (dj, di) in enumerate(_NEIGHBORS):
        src_j0 = max(0, -dj)
        src_j1 = h - max(0, dj)
        src_i0 = max(0, -di)
        src_i1 = w - max(0, di)
        dst_j0 = max(0, dj)
        dst_j1 = h - max(0, -dj)
        dst_i0 = max(0, di)
        dst_i1 = w - max(0, -di)
        # Default dst elevation is source minus the boundary drop (off-grid sink).
        dst_full = filled - boundary_drop_m
        dst_full[src_j0:src_j1, src_i0:src_i1] = filled[dst_j0:dst_j1, dst_i0:dst_i1]
        drop = filled - dst_full
        slope = np.maximum(drop, 0.0) / distances[k]
        weights[:, :, k] = (slope ** exponent) * edge_len[k]
    total = weights.sum(axis=2, keepdims=True)
    safe = total > 0
    weights = np.where(safe, weights / np.where(safe, total, 1.0), 0.0)
    return weights.astype(np.float32)


def propagate_discharge(weights: np.ndarray, filled: np.ndarray,
                        injections: Iterable[tuple[int, int, int, float]],
                        absorber_mask: np.ndarray | None = None,
                        ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Solve for discharge, dominant spring and exported amount via sparse solve."""
    from scipy.sparse import csr_matrix, eye as sp_eye
    from scipy.sparse.linalg import spsolve_triangular

    h, w = filled.shape
    inj_list = list(injections)
    if not inj_list:
        return (np.zeros((0, h, w), dtype=np.float32),
                np.full((h, w), -1, dtype=np.int16),
                np.zeros(0, dtype=np.float32))
    n_springs = max(s for s, _, _, _ in inj_list) + 1
    n_cells = h * w
    weights_flat = weights.reshape(n_cells, 8).astype(np.float64)
    if absorber_mask is not None:
        weights_flat = weights_flat.copy()
        weights_flat[absorber_mask.ravel()] = 0.0
    neighbor_flat = _build_neighbor_flat(h, w)
    # Rank cells by descending elevation to build a lower-triangular system.
    order_flat = np.argsort(-filled, axis=None, kind="stable")
    rank_of = np.empty(n_cells, dtype=np.int64)
    rank_of[order_flat] = np.arange(n_cells)
    rows = []
    cols = []
    data = []
    export_fraction = np.zeros(n_cells, dtype=np.float64)
    for k in range(8):
        wk = weights_flat[:, k]
        nbr = neighbor_flat[:, k]
        in_bound = nbr >= 0
        src_cells = np.where(in_bound & (wk > 0))[0]
        if src_cells.size > 0:
            rows.append(rank_of[nbr[src_cells]])
            cols.append(rank_of[src_cells])
            data.append(wk[src_cells])
        off_mask = (~in_bound) & (wk > 0)
        export_fraction += wk * off_mask
    if rows:
        rows_cat = np.concatenate(rows)
        cols_cat = np.concatenate(cols)
        data_cat = np.concatenate(data)
    else:
        rows_cat = np.zeros(0, dtype=np.int64)
        cols_cat = np.zeros(0, dtype=np.int64)
        data_cat = np.zeros(0, dtype=np.float64)
    sparse_w = csr_matrix((data_cat, (rows_cat, cols_cat)),
                          shape=(n_cells, n_cells))
    system = (sp_eye(n_cells, format="csr") - sparse_w).tocsr()
    per_spring_injections: list[np.ndarray] = []
    for _ in range(n_springs):
        per_spring_injections.append(np.zeros(n_cells, dtype=np.float64))
    for s, j, i, amount in inj_list:
        flat = j * w + i
        per_spring_injections[s][rank_of[flat]] += float(amount)
    accum_cube = np.zeros((n_springs, h, w), dtype=np.float32)
    exported = np.zeros(n_springs, dtype=np.float64)
    inverse_rank = order_flat  # rank -> flat index
    for s in range(n_springs):
        rhs = per_spring_injections[s]
        if rhs.sum() == 0:
            continue
        ranked_accum = spsolve_triangular(system, rhs, lower=True)
        flat_accum = np.zeros(n_cells, dtype=np.float64)
        flat_accum[inverse_rank] = ranked_accum
        accum_cube[s] = flat_accum.astype(np.float32).reshape(h, w)
        exported[s] = float((flat_accum * export_fraction).sum())
    dominant = np.full((h, w), -1, dtype=np.int16)
    if n_springs > 0:
        max_val = np.full((h, w), 0.0, dtype=np.float32)
        for s in range(n_springs):
            mask = accum_cube[s] > max_val
            dominant = np.where(mask, s, dominant).astype(np.int16)
            max_val = np.where(mask, accum_cube[s], max_val)
    return accum_cube, dominant, exported.astype(np.float32)


def _build_neighbor_flat(h: int, w: int) -> np.ndarray:
    """Precompute the flat neighbor index per cell per direction, -1 if off-grid."""
    n_cells = h * w
    out = np.full((n_cells, 8), -1, dtype=np.int64)
    j_grid, i_grid = np.meshgrid(np.arange(h), np.arange(w), indexing="ij")
    for k, (dj, di) in enumerate(_NEIGHBORS):
        nj = j_grid + dj
        ni = i_grid + di
        valid = (nj >= 0) & (nj < h) & (ni >= 0) & (ni < w)
        flat_nbr = nj * w + ni
        out[:, k] = np.where(valid.ravel(), flat_nbr.ravel(), -1)
    return out


def flow_length_raster(weights: np.ndarray, filled: np.ndarray,
                       sources: Iterable[tuple[int, int]],
                       cell_m: float = CORE_CELL_M) -> np.ndarray:
    """Shortest MFD-path length (meters) from any source cell."""
    from scipy.sparse import csr_matrix
    from scipy.sparse.csgraph import dijkstra

    h, w = filled.shape
    n_cells = h * w
    distances = _neighbor_distances(cell_m)
    neighbor_flat = _build_neighbor_flat(h, w)
    weights_flat = weights.reshape(n_cells, 8)
    rows = []
    cols = []
    data = []
    for k in range(8):
        wk = weights_flat[:, k]
        nbr = neighbor_flat[:, k]
        valid = (nbr >= 0) & (wk > 0)
        src_cells = np.where(valid)[0]
        if src_cells.size == 0:
            continue
        rows.append(src_cells)
        cols.append(nbr[src_cells])
        data.append(np.full(src_cells.size, distances[k], dtype=np.float64))
    if rows:
        rows_cat = np.concatenate(rows)
        cols_cat = np.concatenate(cols)
        data_cat = np.concatenate(data)
    else:
        rows_cat = np.zeros(0, dtype=np.int64)
        cols_cat = np.zeros(0, dtype=np.int64)
        data_cat = np.zeros(0, dtype=np.float64)
    graph = csr_matrix((data_cat, (rows_cat, cols_cat)),
                       shape=(n_cells, n_cells))
    src_flat = []
    for j, i in sources:
        if 0 <= j < h and 0 <= i < w:
            src_flat.append(int(j) * w + int(i))
    if not src_flat:
        return np.full((h, w), np.nan, dtype=np.float32)
    dist = dijkstra(graph, directed=True, indices=np.asarray(src_flat),
                    min_only=True)
    out = dist.astype(np.float32)
    out[np.isinf(out)] = np.nan
    return out.reshape(h, w)


def slope_magnitude(filled: np.ndarray, cell_m: float = CORE_CELL_M) -> np.ndarray:
    """Central-difference slope magnitude in m per m."""
    grad = np.gradient(filled.astype(np.float64), cell_m)
    gz, gx = grad[0], grad[1]
    return np.hypot(gx, gz).astype(np.float32)


def classify_wet_mask(rgb01: np.ndarray, thermal_mask: np.ndarray,
                      thresholds: dict | None = None) -> tuple[np.ndarray, dict]:
    """Imagery classifier for wet mat and outflow water inside the thermal mask.

RGB expected in [0, 1] on the core grid. Returns (bool mask, parameters).
"""
    if rgb01.ndim != 3 or rgb01.shape[2] != 3:
        raise ValueError("rgb01 must be a (h, w, 3) float array in [0, 1]")
    if rgb01.shape[:2] != thermal_mask.shape:
        raise ValueError("thermal_mask shape must match rgb01")
    th = {
        "min_saturation": 0.14,
        "min_red": 0.18,
        "max_luminance": 0.78,
        "status": "authored",
    }
    if thresholds:
        th.update(thresholds)
    r = rgb01[..., 0]
    g = rgb01[..., 1]
    b = rgb01[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.where(mx > 0, (mx - mn) / np.where(mx > 0, mx, 1.0), 0.0)
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    wet = (
        thermal_mask
        & (lum <= th["max_luminance"])
        & ((sat >= th["min_saturation"]) | (r >= th["min_red"]))
    )
    return wet.astype(bool), th


def thermal_proximity_mask(grid: Grid, pool_centers_xz: Iterable[tuple[float, float]],
                           radius_m: float = 220.0) -> np.ndarray:
    """Cells within radius_m of any thermal pool center."""
    xs = -grid.half_m + 0.5 * grid.cell_m + np.arange(grid.size) * grid.cell_m
    zs = -grid.half_m + 0.5 * grid.cell_m + np.arange(grid.size) * grid.cell_m
    xx, zz = np.meshgrid(xs, zs)
    out = np.zeros((grid.size, grid.size), dtype=bool)
    for cx, cz in pool_centers_xz:
        out |= (xx - cx) ** 2 + (zz - cz) ** 2 <= radius_m ** 2
    return out


def _steepest_successor(weights: np.ndarray, j: int, i: int) -> tuple[int, int, float]:
    """Return (nj, ni, weight) of the maximum-weight downslope neighbor."""
    cell = weights[j, i]
    k = int(np.argmax(cell))
    wk = float(cell[k])
    if wk == 0:
        return -1, -1, 0.0
    dj, di = _NEIGHBORS[k]
    return j + dj, i + di, wk


def river_and_grid_fractions(weights: np.ndarray, filled: np.ndarray,
                             injections: Iterable[tuple[int, int, int, float]],
                             river_mask: np.ndarray
                             ) -> list[dict]:
    """Per-spring split of injection into river sink and grid-boundary sink."""
    inj_list = list(injections)
    if not inj_list:
        return []
    n_springs = max(s for s, _, _, _ in inj_list) + 1
    totals = np.zeros(n_springs, dtype=np.float64)
    for s, _j, _i, amount in inj_list:
        totals[s] += float(amount)
    absorbed_acc, _dominant, exported = propagate_discharge(
        weights, filled, inj_list, absorber_mask=river_mask)
    out: list[dict] = []
    for s in range(n_springs):
        inj = float(totals[s])
        river_sum = float(absorbed_acc[s][river_mask].sum()) if inj > 0 else 0.0
        grid_sum = float(exported[s])
        if inj > 0:
            river_fraction = river_sum / inj
            grid_fraction = grid_sum / inj
        else:
            river_fraction = 0.0
            grid_fraction = 0.0
        out.append({
            "spring_index": s,
            "river_inflow_fraction": round(river_fraction, 6),
            "grid_exit_fraction": round(grid_fraction, 6),
            "river_plus_grid": round(river_fraction + grid_fraction, 6),
            "injected_fraction": round(inj, 6),
        })
    return out


def river_inflow_points(discharge: np.ndarray, weights: np.ndarray,
                        river_mask: np.ndarray, grid: Grid,
                        min_flow: float = 1e-4) -> list[dict]:
    """Per-spring exit cells into the river with their flow fractions."""
    n_springs = discharge.shape[0] if discharge.ndim == 3 else 1
    h = grid.size
    points: list[dict] = []
    neighbor_flat = _build_neighbor_flat(h, h)
    weights_flat = weights.reshape(h * h, 8)
    river_flat = river_mask.ravel()
    for s in range(n_springs):
        acc_flat = discharge[s].ravel()
        for cell_idx in range(h * h):
            if acc_flat[cell_idx] == 0:
                continue
            if river_flat[cell_idx]:
                continue
            w_to_river = 0.0
            for k in range(8):
                nbr = int(neighbor_flat[cell_idx, k])
                if nbr < 0:
                    continue
                if river_flat[nbr]:
                    w_to_river += float(weights_flat[cell_idx, k])
            if w_to_river == 0:
                continue
            exit_flow = float(acc_flat[cell_idx]) * w_to_river
            if exit_flow < min_flow:
                continue
            j, i = divmod(cell_idx, h)
            x, z = grid.cell_center_xz(j, i)
            points.append({
                "spring_index": s,
                "xz": [round(x, 3), round(z, 3)],
                "flow_fraction": round(exit_flow, 6),
            })
    return points


def rasterize_rivers_mask(rivers: Iterable[dict], grid: Grid) -> np.ndarray:
    """Rasterize river polylines (points with x, y, z and width) to a mask."""
    mask = np.zeros((grid.size, grid.size), dtype=bool)
    xs = -grid.half_m + 0.5 * grid.cell_m + np.arange(grid.size) * grid.cell_m
    zs = -grid.half_m + 0.5 * grid.cell_m + np.arange(grid.size) * grid.cell_m
    xx, zz = np.meshgrid(xs, zs)
    for river in rivers:
        pts = river.get("points", [])
        half_width = max(0.5, float(river.get("width", 2.0)) * 0.5)
        for a, b in zip(pts, pts[1:]):
            x0, z0 = float(a[0]), float(a[2])
            x1, z1 = float(b[0]), float(b[2])
            if (max(x0, x1) < -grid.half_m or min(x0, x1) > grid.half_m
                    or max(z0, z1) < -grid.half_m or min(z0, z1) > grid.half_m):
                continue
            dx = x1 - x0
            dz = z1 - z0
            length2 = dx * dx + dz * dz
            if length2 == 0:
                continue
            tx = xx - x0
            tz = zz - z0
            u = np.clip((tx * dx + tz * dz) / length2, 0.0, 1.0)
            px = x0 + u * dx
            pz = z0 + u * dz
            dist2 = (xx - px) ** 2 + (zz - pz) ** 2
            mask |= dist2 <= half_width ** 2
    return mask


def extract_channels(spring_entries: list[dict], weights: np.ndarray,
                     discharge: np.ndarray, slope: np.ndarray,
                     wet: np.ndarray, grid: Grid,
                     river_mask: np.ndarray,
                     flow_threshold: float = 0.005,
                     width_fallback_m: float = 1.0,
                     width_max_m: float = 12.0) -> list[dict]:
    """Thin MFD channel cells to a D8 skeleton split at confluences and terminals."""
    segments: list[dict] = []
    seg_counter = 0
    h = grid.size
    for s_idx, spring in enumerate(spring_entries):
        acc = discharge[s_idx]
        pool_mask = spring["pool_mask"]
        rim_mask_arr = spring["rim_mask"]
        pool_interior = pool_mask & ~rim_mask_arr
        channel_mask = (acc > flow_threshold) & ~pool_interior
        if not channel_mask.any():
            continue
        channel_coords = np.argwhere(channel_mask)
        successor = np.full((h, h), -1, dtype=np.int64)
        indegree = np.zeros((h, h), dtype=np.int32)
        termination = {}
        for jj, ii in channel_coords:
            nj, ni, _ = _steepest_successor(weights, int(jj), int(ii))
            if nj < 0:
                termination[(int(jj), int(ii))] = "dry"
                continue
            if not (0 <= nj < h and 0 <= ni < h):
                termination[(int(jj), int(ii))] = "grid"
                continue
            if river_mask[nj, ni]:
                termination[(int(jj), int(ii))] = "river"
                continue
            if not channel_mask[nj, ni]:
                termination[(int(jj), int(ii))] = "dry"
                continue
            successor[jj, ii] = int(nj) * h + int(ni)
            indegree[nj, ni] += 1
        # Rim cells with no upstream channel predecessor are heads.
        heads: list[tuple[int, int]] = []
        confluences: list[tuple[int, int]] = []
        for jj, ii in channel_coords:
            if rim_mask_arr[jj, ii] and indegree[jj, ii] == 0:
                heads.append((int(jj), int(ii)))
            if indegree[jj, ii] >= 2:
                confluences.append((int(jj), int(ii)))
        starts: list[tuple[int, int, str]] = []
        for c in heads:
            starts.append((c[0], c[1], "head"))
        for c in confluences:
            starts.append((c[0], c[1], "confluence"))
        # Downstream endpoint of each parent segment maps to a confluence cell.
        parent_at_cell: dict[tuple[int, int], list[dict]] = {}
        seg_rows: list[dict] = []
        for start_j, start_i, start_kind in starts:
            path = [(start_j, start_i)]
            j, i = start_j, start_i
            terminator = termination.get((j, i))
            while True:
                succ = int(successor[j, i])
                if succ < 0:
                    break
                nj, ni = divmod(succ, h)
                if indegree[nj, ni] >= 2:
                    path.append((nj, ni))
                    terminator = "confluence"
                    break
                path.append((nj, ni))
                j, i = nj, ni
                terminator = termination.get((nj, ni))
                if terminator:
                    break
            if terminator in ("river", "dry", "grid") and len(path) < 2:
                last_j, last_i = path[-1]
                nj, ni, _wk = _steepest_successor(weights, last_j, last_i)
                if 0 <= nj < h and 0 <= ni < h:
                    path.append((int(nj), int(ni)))
                elif terminator == "grid":
                    dj = 0 if last_j not in (0, h - 1) else (-1 if last_j == 0 else 1)
                    di = 0 if last_i not in (0, h - 1) else (-1 if last_i == 0 else 1)
                    if dj == 0 and di == 0:
                        di = 1 if last_i < h - 1 else -1
                    ghost_j = last_j - dj
                    ghost_i = last_i - di
                    path.append((int(ghost_j), int(ghost_i)))
            seg_id = f"seg_{seg_counter:04d}"
            seg_counter += 1
            points_xz = [list(grid.cell_center_xz(pj, pi)) for pj, pi in path]
            length_m = 0.0
            for a, b2 in zip(points_xz, points_xz[1:]):
                length_m += math.hypot(a[0] - b2[0], a[1] - b2[1])
            mean_slope = float(np.mean([slope[pj, pi] for pj, pi in path]))
            width_m, width_source = _estimate_width(path, wet, width_fallback_m,
                                                    width_max_m, grid)
            imagery_wet_fraction = _imagery_wet_fraction(path, wet)
            downstream_cell = path[-1]
            flow_fraction = float(acc[downstream_cell[0], downstream_cell[1]])
            seg_row = {
                "id": seg_id,
                "spring_index": s_idx,
                "upstream_id": None,
                "points_xz": [[round(x, 3), round(z, 3)] for x, z in points_xz],
                "length_m": round(length_m, 3),
                "mean_slope": round(mean_slope, 6),
                "width_m": round(width_m, 3),
                "width_source": width_source,
                "flow_fraction": round(flow_fraction, 6),
                "imagery_wet_fraction": round(imagery_wet_fraction, 4),
                "leaves_core_grid": terminator == "grid",
                "reaches_river": terminator == "river",
                "terminator": terminator or "dry",
                "upstream_endpoint_xz": [round(points_xz[0][0], 3),
                                         round(points_xz[0][1], 3)],
                "downstream_endpoint_xz": [round(points_xz[-1][0], 3),
                                           round(points_xz[-1][1], 3)],
                "upstream_endpoint_kind": start_kind,
            }
            seg_rows.append(seg_row)
            if start_kind == "confluence":
                parent_at_cell.setdefault((start_j, start_i), []).append(seg_row)
        # Link each downstream segment to its best parent at its upstream confluence.
        for seg in seg_rows:
            if seg["upstream_endpoint_kind"] != "confluence":
                continue
            parents = parent_at_cell.get(
                (int((seg["upstream_endpoint_xz"][1] + grid.half_m)
                     // grid.cell_m),
                 int((seg["upstream_endpoint_xz"][0] + grid.half_m)
                     // grid.cell_m)), [])
        # Map confluence-terminated segments by their downstream cell for parents.
        downstream_cell_to_seg: dict[tuple[int, int], dict] = {}
        for seg in seg_rows:
            dj = int((seg["downstream_endpoint_xz"][1] + grid.half_m)
                     // grid.cell_m)
            di = int((seg["downstream_endpoint_xz"][0] + grid.half_m)
                     // grid.cell_m)
            if seg["terminator"] == "confluence":
                downstream_cell_to_seg.setdefault((dj, di), seg)
        parents_by_cell: dict[tuple[int, int], list[dict]] = {}
        for seg in seg_rows:
            if seg["terminator"] != "confluence":
                continue
            dj = int((seg["downstream_endpoint_xz"][1] + grid.half_m)
                     // grid.cell_m)
            di = int((seg["downstream_endpoint_xz"][0] + grid.half_m)
                     // grid.cell_m)
            parents_by_cell.setdefault((dj, di), []).append(seg)
        for seg in seg_rows:
            if seg["upstream_endpoint_kind"] != "confluence":
                continue
            uj = int((seg["upstream_endpoint_xz"][1] + grid.half_m)
                     // grid.cell_m)
            ui = int((seg["upstream_endpoint_xz"][0] + grid.half_m)
                     // grid.cell_m)
            parents = parents_by_cell.get((uj, ui), [])
            if not parents:
                continue
            main_parent = max(parents, key=lambda p: p["flow_fraction"])
            seg["upstream_id"] = main_parent["id"]
            seg["tributary_upstream_ids"] = [p["id"] for p in parents
                                             if p["id"] != main_parent["id"]]
        segments.extend(seg_rows)
    return segments


def cleanup_segments(segments: list[dict], slope: np.ndarray, grid: Grid,
                     min_segment_length_m: float = MIN_SEGMENT_LENGTH_M,
                     min_spur_flow_fraction: float = MIN_SPUR_FLOW_FRACTION
                     ) -> tuple[list[dict], dict]:
    """Prune short low-flow spurs, merge degree-2 chains, absorb main stems."""
    report: dict = {"min_segment_length_m": min_segment_length_m,
                    "min_spur_flow_fraction": min_spur_flow_fraction,
                    "ratio_status": "authored",
                    "pre_count": len(segments)}
    pre_terminal_sums: dict[int, float] = {}
    for seg in segments:
        if seg.get("reaches_river"):
            pre_terminal_sums[seg["spring_index"]] = (
                pre_terminal_sums.get(seg["spring_index"], 0.0)
                + float(seg["flow_fraction"]))
    survivors = [dict(seg) for seg in segments]
    # Map every removed id to the surviving replacement or its parent id.
    removed_redirect: dict[str, str | None] = {}
    # Prune short low-flow interior shortcuts; preserve every rim head.
    pruned_ids: set[str] = set()
    pruned_originals: dict[str, dict] = {}
    for seg in survivors:
        if seg.get("reaches_river"):
            continue
        if seg.get("leaves_core_grid"):
            continue
        if seg.get("upstream_endpoint_kind") == "head":
            singleton = len(seg["points_xz"]) < 2
            if singleton:
                pruned_ids.add(seg["id"])
                pruned_originals[seg["id"]] = seg
            continue
        length_short = seg["length_m"] < min_segment_length_m
        flow_small = seg["flow_fraction"] < min_spur_flow_fraction
        singleton = len(seg["points_xz"]) < 2
        if (length_short and flow_small) or singleton:
            pruned_ids.add(seg["id"])
            pruned_originals[seg["id"]] = seg
    for pid in pruned_ids:
        removed_redirect[pid] = pruned_originals[pid].get("upstream_id")
    survivors = [seg for seg in survivors if seg["id"] not in pruned_ids]
    # Merge degree-2 chains iteratively until stable.
    merged_count = 0
    while True:
        starts_at: dict[tuple[float, float], list[dict]] = {}
        ends_at: dict[tuple[float, float], list[dict]] = {}
        for seg in survivors:
            u = tuple(seg["upstream_endpoint_xz"])
            d = tuple(seg["downstream_endpoint_xz"])
            if seg.get("upstream_endpoint_kind") == "confluence":
                starts_at.setdefault(u, []).append(seg)
            if seg.get("terminator") == "confluence":
                ends_at.setdefault(d, []).append(seg)
        merge_cells = []
        for cell, starts in starts_at.items():
            ends = ends_at.get(cell, [])
            if len(starts) == 1 and len(ends) == 1:
                merge_cells.append((cell, ends[0], starts[0]))
        if not merge_cells:
            break
        merged_this_pass: set[str] = set()
        for _cell, parent, child in merge_cells:
            if parent["id"] in merged_this_pass or child["id"] in merged_this_pass:
                continue
            merged_this_pass.add(child["id"])
            merged_this_pass.add(parent["id"])
            removed_redirect[child["id"]] = parent["id"]
            parent_cells = [(int((p[1] + grid.half_m) // grid.cell_m),
                             int((p[0] + grid.half_m) // grid.cell_m))
                            for p in parent["points_xz"]]
            child_cells = [(int((p[1] + grid.half_m) // grid.cell_m),
                            int((p[0] + grid.half_m) // grid.cell_m))
                           for p in child["points_xz"]]
            merged_points = parent["points_xz"] + child["points_xz"][1:]
            merged_cells = parent_cells + child_cells[1:]
            total_len = parent["length_m"] + child["length_m"]
            total_count = max(1, len(merged_cells))
            mean_slope = float(np.mean([slope[pj, pi]
                                        for pj, pi in merged_cells]))
            parent["points_xz"] = merged_points
            parent["length_m"] = round(total_len, 3)
            parent["mean_slope"] = round(mean_slope, 6)
            parent["downstream_endpoint_xz"] = child["downstream_endpoint_xz"]
            parent["terminator"] = child["terminator"]
            parent["reaches_river"] = child.get("reaches_river", False)
            parent["leaves_core_grid"] = child.get("leaves_core_grid", False)
            parent["flow_fraction"] = child["flow_fraction"]
            parent["width_m"] = max(parent["width_m"], child["width_m"])
            parent["imagery_wet_fraction"] = round(
                (parent["imagery_wet_fraction"] * len(parent_cells)
                 + child["imagery_wet_fraction"] * len(child_cells))
                / total_count, 4)
            for other in survivors:
                if other.get("upstream_id") == child["id"]:
                    other["upstream_id"] = parent["id"]
                other["tributary_upstream_ids"] = [
                    parent["id"] if t == child["id"] else t
                    for t in other.get("tributary_upstream_ids", [])]
            merged_count += 1
        survivors = [seg for seg in survivors if seg["id"] not in merged_this_pass
                     or seg["id"] in {parent["id"] for _cell, parent, _child in merge_cells}]
    # Absorb main-stem outbound segments into their dominant-flow parent.
    absorbed_count = 0
    while True:
        starts_at = {}
        ends_at = {}
        for seg in survivors:
            u = tuple(seg["upstream_endpoint_xz"])
            d = tuple(seg["downstream_endpoint_xz"])
            if seg.get("upstream_endpoint_kind") == "confluence":
                starts_at.setdefault(u, []).append(seg)
            if seg.get("terminator") == "confluence":
                ends_at.setdefault(d, []).append(seg)
        absorbed_ids: set[str] = set()
        for cell, outs in starts_at.items():
            parents = ends_at.get(cell, [])
            if len(outs) != 1 or not parents:
                continue
            out_seg = outs[0]
            main_parent = max(parents, key=lambda p: p["flow_fraction"])
            if main_parent["id"] == out_seg["id"]:
                continue
            parent_cells = [(int((p[1] + grid.half_m) // grid.cell_m),
                             int((p[0] + grid.half_m) // grid.cell_m))
                            for p in main_parent["points_xz"]]
            child_cells = [(int((p[1] + grid.half_m) // grid.cell_m),
                            int((p[0] + grid.half_m) // grid.cell_m))
                           for p in out_seg["points_xz"]]
            merged_points = main_parent["points_xz"] + out_seg["points_xz"][1:]
            merged_cells = parent_cells + child_cells[1:]
            main_parent["points_xz"] = merged_points
            main_parent["length_m"] = round(main_parent["length_m"]
                                            + out_seg["length_m"], 3)
            main_parent["mean_slope"] = round(float(np.mean([
                slope[pj, pi] for pj, pi in merged_cells])), 6)
            main_parent["downstream_endpoint_xz"] = out_seg["downstream_endpoint_xz"]
            main_parent["terminator"] = out_seg["terminator"]
            main_parent["reaches_river"] = out_seg.get("reaches_river", False)
            main_parent["leaves_core_grid"] = out_seg.get("leaves_core_grid", False)
            main_parent["flow_fraction"] = out_seg["flow_fraction"]
            main_parent["width_m"] = max(main_parent["width_m"], out_seg["width_m"])
            main_parent["imagery_wet_fraction"] = round(
                (main_parent["imagery_wet_fraction"] * len(parent_cells)
                 + out_seg["imagery_wet_fraction"] * len(child_cells))
                / max(1, len(merged_cells)), 4)
            for other in survivors:
                if other.get("upstream_id") == out_seg["id"]:
                    other["upstream_id"] = main_parent["id"]
                other["tributary_upstream_ids"] = [
                    main_parent["id"] if t == out_seg["id"] else t
                    for t in other.get("tributary_upstream_ids", [])]
            # Remaining parents at the confluence become main-stem tributaries.
            tribs = main_parent.get("tributary_upstream_ids", [])
            for p in parents:
                if p["id"] != main_parent["id"] and p["id"] not in tribs:
                    tribs.append(p["id"])
            main_parent["tributary_upstream_ids"] = tribs
            removed_redirect[out_seg["id"]] = main_parent["id"]
            absorbed_ids.add(out_seg["id"])
            absorbed_count += 1
        if not absorbed_ids:
            break
        survivors = [seg for seg in survivors if seg["id"] not in absorbed_ids]
    report["absorbed_count"] = absorbed_count
    # Drop any remaining singleton segments that are not river terminals.
    survivors = [seg for seg in survivors
                 if len(seg["points_xz"]) >= 2 or seg.get("reaches_river")]
    # Follow removed_redirect to the nearest surviving ancestor.
    survivor_ids_final = {seg["id"] for seg in survivors}

    def _resolve(target: str | None) -> tuple[str | None, int, str]:
        """Follow removed_redirect to a surviving id, None, or orphan."""
        if target is None:
            return None, 0, "chain_ends_at_rim"
        if target in survivor_ids_final:
            return target, 0, "direct"
        hops = 0
        seen: set[str] = set()
        while target is not None and target not in survivor_ids_final:
            if target in seen:
                return None, hops, "cycle_fallback_null"
            seen.add(target)
            if target in removed_redirect:
                target = removed_redirect[target]
                hops += 1
            else:
                return None, hops, "orphan_no_ancestor"
        if target is None:
            return None, hops, "chain_ends_at_rim"
        return target, hops, "redirected_to_ancestor"

    redirect_counts = {"direct": 0, "redirected_to_ancestor": 0,
                       "chain_ends_at_rim": 0,
                       "promoted_from_tributary": 0,
                       "orphan_no_ancestor": 0, "cycle_fallback_null": 0}
    tributary_resolution = {"direct": 0, "redirected_to_ancestor": 0,
                            "dropped_chain_ends_at_rim": 0,
                            "dropped_orphan": 0, "dropped_cycle": 0}
    orphan_dropped_count = 0
    # Resolve-and-drop loop: resolve references then drop non-head orphans.
    while True:
        survivor_ids_final = {seg["id"] for seg in survivors}
        survivor_by_id = {seg["id"]: seg for seg in survivors}
        pass_counts = {"direct": 0, "redirected_to_ancestor": 0,
                       "chain_ends_at_rim": 0,
                       "promoted_from_tributary": 0,
                       "orphan_no_ancestor": 0, "cycle_fallback_null": 0}
        pass_trib_counts = {"direct": 0, "redirected_to_ancestor": 0,
                            "dropped_chain_ends_at_rim": 0,
                            "dropped_orphan": 0, "dropped_cycle": 0}
        for seg in survivors:
            original = seg.get("upstream_id")
            resolved, hops, reason = _resolve(original)
            new_tribs: list[str] = []
            dropped_tribs: list[dict] = []
            for trib in seg.get("tributary_upstream_ids", []):
                r, _h, rr = _resolve(trib)
                if r is None:
                    dropped_tribs.append({"original": trib, "reason": rr})
                    key = ("dropped_chain_ends_at_rim"
                           if rr == "chain_ends_at_rim"
                           else ("dropped_cycle" if rr == "cycle_fallback_null"
                                 else "dropped_orphan"))
                    pass_trib_counts[key] = pass_trib_counts.get(key, 0) + 1
                else:
                    new_tribs.append(r)
                    pass_trib_counts["direct" if rr == "direct"
                                     else "redirected_to_ancestor"] += 1
            seen_ids: set[str] = set()
            deduped: list[str] = []
            for t in new_tribs:
                if t == seg["id"] or t in seen_ids:
                    continue
                seen_ids.add(t)
                deduped.append(t)
            if (resolved is None
                    and seg.get("upstream_endpoint_kind") != "head"
                    and deduped):
                tribs_with_flow = [(survivor_by_id[t]["flow_fraction"], t)
                                   for t in deduped if t in survivor_by_id]
                if tribs_with_flow:
                    tribs_with_flow.sort(reverse=True)
                    promoted = tribs_with_flow[0][1]
                    resolved = promoted
                    reason = "promoted_from_tributary"
                    deduped = [t for t in deduped if t != promoted]
                    seg["upstream_id_original"] = original
                    seg["upstream_id_promoted_from"] = promoted
            pass_counts[reason] = pass_counts.get(reason, 0) + 1
            seg["upstream_id"] = resolved
            if resolved != original or reason != "direct":
                seg["upstream_id_resolution"] = reason
                if hops > 0:
                    seg["upstream_id_hops"] = hops
                    seg.setdefault("upstream_id_original", original)
            seg["tributary_upstream_ids"] = deduped
            if dropped_tribs:
                seg["tributary_upstream_ids_dropped"] = dropped_tribs
        # Link each preserved terminal to the nearest surviving head.
        heads_by_spring: dict[int, list[dict]] = {}
        for seg in survivors:
            if (seg.get("upstream_endpoint_kind") == "head"
                    and seg.get("upstream_id") is None):
                heads_by_spring.setdefault(int(seg["spring_index"]),
                                           []).append(seg)
        for seg in survivors:
            if seg.get("upstream_id") is not None:
                continue
            if seg.get("upstream_endpoint_kind") == "head":
                continue
            if not (seg.get("reaches_river") or seg.get("leaves_core_grid")):
                continue
            heads = heads_by_spring.get(int(seg["spring_index"]), [])
            if not heads:
                continue
            x0 = float(seg["upstream_endpoint_xz"][0])
            z0 = float(seg["upstream_endpoint_xz"][1])

            def _dist(h: dict, x: float = x0, z: float = z0) -> float:
                return math.hypot(
                    float(h["upstream_endpoint_xz"][0]) - x,
                    float(h["upstream_endpoint_xz"][1]) - z,
                )

            nearest = min(heads, key=_dist)
            seg["upstream_id"] = nearest["id"]
            seg["upstream_id_resolution"] = "linked_to_nearest_surviving_head"
            seg.setdefault("upstream_id_original", None)
            pass_counts["redirected_to_ancestor"] = pass_counts.get(
                "redirected_to_ancestor", 0) + 1
            pass_counts["chain_ends_at_rim"] = max(
                0, pass_counts.get("chain_ends_at_rim", 0) - 1)
        # Drop non-head orphans so the next iteration propagates removal.
        orphan_ids = {seg["id"] for seg in survivors
                      if seg.get("upstream_id") is None
                      and seg.get("upstream_endpoint_kind") != "head"
                      and not seg.get("reaches_river")
                      and not seg.get("leaves_core_grid")}
        if not orphan_ids:
            for key, value in pass_counts.items():
                redirect_counts[key] = redirect_counts.get(key, 0) + value
            for key, value in pass_trib_counts.items():
                tributary_resolution[key] = tributary_resolution.get(key, 0) + value
            break
        for orphan_id in orphan_ids:
            removed_redirect[orphan_id] = None
        orphan_dropped_count += len(orphan_ids)
        survivors = [seg for seg in survivors if seg["id"] not in orphan_ids]
    report["dangling_references"] = {
        "upstream_id_resolution_counts": redirect_counts,
        "tributary_resolution_counts": tributary_resolution,
        "orphan_segments_dropped": orphan_dropped_count,
        "note": ("References are redirected to the nearest surviving "
                 "ancestor through the removal chain, promoted from a "
                 "surviving tributary at the same confluence when the "
                 "main parent is gone, or dropped (orphan_segments_dropped) "
                 "when the segment is a non-head reach with no surviving "
                 "upstream. upstream_id is None only on head segments."),
    }
    post_terminal_sums: dict[int, float] = {}
    for seg in survivors:
        if seg.get("reaches_river"):
            post_terminal_sums[seg["spring_index"]] = (
                post_terminal_sums.get(seg["spring_index"], 0.0)
                + float(seg["flow_fraction"]))
    deltas: dict[str, float] = {}
    for s_idx, pre in pre_terminal_sums.items():
        post = post_terminal_sums.get(s_idx, 0.0)
        deltas[str(s_idx)] = round(post - pre, 6)
    report.update({
        "post_count": len(survivors),
        "pruned_count": report["pre_count"] - len(survivors),
        "merged_count": merged_count,
        "terminal_flow_sum_pre": {str(k): round(v, 6)
                                  for k, v in pre_terminal_sums.items()},
        "terminal_flow_sum_post": {str(k): round(v, 6)
                                   for k, v in post_terminal_sums.items()},
        "terminal_flow_delta": deltas,
    })
    return survivors, report


def segment_length_histogram(segments: list[dict]) -> dict:
    """Bucket counts of segment lengths in meters for reporting."""
    buckets = [(0.0, 1.0), (1.0, 2.0), (2.0, 5.0), (5.0, 10.0),
               (10.0, 25.0), (25.0, 50.0), (50.0, 100.0), (100.0, float("inf"))]
    labels = ["[0,1)", "[1,2)", "[2,5)", "[5,10)", "[10,25)", "[25,50)",
              "[50,100)", "[100,inf)"]
    out = {label: 0 for label in labels}
    for seg in segments:
        length = float(seg["length_m"])
        for (low, high), label in zip(buckets, labels):
            if low <= length < high:
                out[label] += 1
                break
    return out


def junction_conservation(segments: list[dict], _grid: Grid,
                          tolerance: float = 1e-6) -> dict:
    """Report whether each confluence's outbound flow matches the maximum parent."""
    starts_at: dict[tuple[float, float], list[dict]] = {}
    ends_at: dict[tuple[float, float], list[dict]] = {}
    for seg in segments:
        if seg.get("upstream_endpoint_kind") == "confluence":
            starts_at.setdefault(tuple(seg["upstream_endpoint_xz"]), []).append(seg)
        if seg.get("terminator") == "confluence":
            ends_at.setdefault(tuple(seg["downstream_endpoint_xz"]), []).append(seg)
    violations: list[dict] = []
    for cell, starts in starts_at.items():
        parents = ends_at.get(cell, [])
        if not parents or not starts:
            continue
        parent_max = max(p["flow_fraction"] for p in parents)
        for out_seg in starts:
            # Flag when outbound flow is smaller than the dominant parent.
            if out_seg["flow_fraction"] + tolerance < parent_max:
                violations.append({
                    "cell_xz": list(cell),
                    "outbound_id": out_seg["id"],
                    "outbound_flow": out_seg["flow_fraction"],
                    "parent_max_flow": parent_max,
                })
    return {"tolerance": tolerance,
            "n_junctions": len(ends_at),
            "n_violations": len(violations),
            "violations": violations[:10]}


def _estimate_width(path: list[tuple[int, int]], wet: np.ndarray,
                    fallback_m: float, max_m: float, grid: Grid) -> tuple[float, str]:
    """Wet-pixel crosssection width measured perpendicular at path midpoint."""
    if len(path) < 3 or wet is None:
        return fallback_m, "fallback_default_authored"
    mid = len(path) // 2
    pj, pi = path[mid]
    pj_prev, pi_prev = path[max(0, mid - 1)]
    pj_next, pi_next = path[min(len(path) - 1, mid + 1)]
    tj = pj_next - pj_prev
    ti = pi_next - pi_prev
    tn = math.hypot(tj, ti)
    if tn == 0:
        return fallback_m, "fallback_default_authored"
    perp_j = -ti / tn
    perp_i = tj / tn
    width_cells = 0
    for s in range(1, int(max_m / grid.cell_m) + 1):
        hit = 0
        for sign in (-1, 1):
            jj = int(round(pj + sign * s * perp_j))
            ii = int(round(pi + sign * s * perp_i))
            if 0 <= jj < wet.shape[0] and 0 <= ii < wet.shape[1] and wet[jj, ii]:
                hit += 1
        if hit == 0:
            break
        width_cells += hit
    if width_cells == 0:
        return fallback_m, "imagery_estimate_no_wet_pixels_fallback"
    return float(width_cells) * grid.cell_m / 2.0, "imagery_estimate"


def _imagery_wet_fraction(path: list[tuple[int, int]], wet: np.ndarray) -> float:
    if wet is None or not path:
        return 0.0
    hits = sum(1 for pj, pi in path if 0 <= pj < wet.shape[0]
               and 0 <= pi < wet.shape[1] and wet[pj, pi])
    return hits / len(path)


def spring_index_raster(dominant: np.ndarray, in_pool: np.ndarray,
                        discharge: np.ndarray, threshold: float) -> np.ndarray:
    """Int16 spring index, -1 outside pools where total discharge is below threshold."""
    total = discharge.sum(axis=0) if discharge.ndim == 3 else discharge
    out = np.full(dominant.shape, -1, dtype=np.int16)
    live = (total >= threshold) & ~in_pool
    out[live] = dominant[live]
    return out


def flow_fraction_raster(discharge: np.ndarray) -> np.ndarray:
    """Per-cell max spring fraction across springs."""
    if discharge.ndim != 3:
        raise ValueError("discharge must be (n_springs, h, w)")
    return discharge.max(axis=0).astype(np.float32)


def orientation_agreement(segments: list[dict], wet: np.ndarray,
                          grid: Grid) -> dict:
    """Fraction of segment length on wet pixels, overall and per spring."""
    def _accumulate(seg_list: list[dict]) -> tuple[float, float]:
        on_wet = 0.0
        total = 0.0
        for seg in seg_list:
            for a, b in zip(seg["points_xz"], seg["points_xz"][1:]):
                step = math.hypot(a[0] - b[0], a[1] - b[1])
                total += step
                jm = int(((a[1] + b[1]) * 0.5 + grid.half_m) / grid.cell_m)
                im = int(((a[0] + b[0]) * 0.5 + grid.half_m) / grid.cell_m)
                if 0 <= jm < wet.shape[0] and 0 <= im < wet.shape[1] and wet[jm, im]:
                    on_wet += step
        return on_wet, total
    on_wet_all, total_all = _accumulate(segments)
    per_spring: dict[int, dict] = {}
    springs = sorted({seg["spring_index"] for seg in segments})
    for s in springs:
        seg_sub = [seg for seg in segments if seg["spring_index"] == s]
        on_wet_s, total_s = _accumulate(seg_sub)
        per_spring[s] = {
            "fraction_on_wet_pixels": round((on_wet_s / total_s) if total_s > 0 else 0.0, 4),
            "total_segment_length_m": round(total_s, 3),
            "on_wet_length_m": round(on_wet_s, 3),
        }
    return {
        "fraction_on_wet_pixels": round((on_wet_all / total_all)
                                        if total_all > 0 else 0.0, 4),
        "total_segment_length_m": round(total_all, 3),
        "on_wet_length_m": round(on_wet_all, 3),
        "per_spring": {str(k): v for k, v in per_spring.items()},
    }
