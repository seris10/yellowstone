"""Steady 2-D thermal plume: u.dT/dz = Dx.d2T/dx2 + Dz.d2T/dz2 - k.(T-ambient), scipy.sparse."""
from __future__ import annotations
from yellowstone_python.common.checks import finite as _finite

import math

import numpy as np

try:
    from scipy import sparse
    from scipy.sparse.linalg import spsolve
    _HAVE_SPARSE = True
except ImportError:  # pragma: no cover
    _HAVE_SPARSE = False

U_MAPPED_M_S = 0.73
U_PROVENANCE = "mapped_chain_representative_velocity_m_s"
D_LONG_M2_S = 84.7
D_LONG_PROVENANCE = "transferred_mapped_Fischer_median"
D_TRANS_M2_S = 0.12
D_TRANS_PROVENANCE = ("transferred_0.15_depth_u_formula_"
                      "authored_depth_1.1_m_mapped_u")
K_EXCH_PER_S = 1.0 / 18000.0
K_PROVENANCE = "transferred_chain_cooling_seconds_18000"
STATUS = "illustrative_not_calibrated"


def _require_sparse() -> None:
    if not _HAVE_SPARSE:
        raise ImportError("plume2d needs scipy.sparse")





def solve_steady(nx: int = 64, nz: int = 64, extent_m: float = 600.0,
                 u_m_s: float = U_MAPPED_M_S,
                 d_long_m2_s: float = D_LONG_M2_S,
                 d_trans_m2_s: float = D_TRANS_M2_S,
                 k_per_s: float = K_EXCH_PER_S,
                 ambient_c: float = 17.8, source_c: float = 19.1,
                 source_xz: tuple[float, float] = (0.0, -60.0),
                 source_r_m: float = 25.0) -> dict:
    """Steady plume field plus diagnostics. Returns dict with grid + field."""
    _require_sparse()
    for name, v in (("nx", nx), ("nz", nz)):
        if int(v) < 8:
            raise ValueError(f"{name} must be >= 8")
    extent_m = float(extent_m)
    d_long_m2_s = float(d_long_m2_s)
    d_trans_m2_s = float(d_trans_m2_s)
    u_m_s = float(u_m_s)
    k_per_s = float(k_per_s)
    source_c = float(source_c)
    source_r_m = float(source_r_m)
    if not math.isfinite(extent_m) or not math.isfinite(d_long_m2_s) or not math.isfinite(d_trans_m2_s) or not math.isfinite(u_m_s) or not math.isfinite(k_per_s) or not math.isfinite(source_c) or not math.isfinite(source_r_m):
        raise ValueError("extent_m, diffusivities, u_m_s, k_per_s, source_c, and source_r_m must be finite")
    if extent_m <= 0.0 or d_long_m2_s <= 0.0 or d_trans_m2_s <= 0.0:
        raise ValueError("extent_m and diffusivities must be > 0")
    if k_per_s < 0.0:
        raise ValueError("k_per_s must be >= 0")
    if u_m_s < 0.0:
        raise ValueError("u_m_s must be >= 0 (flow is +z)")
    source_xz = tuple(float(x) for x in source_xz)
    if len(source_xz) != 2 or not all(math.isfinite(x) for x in source_xz):
        raise ValueError("source_xz must have exactly two finite values")
    if source_r_m < 0.0:
        raise ValueError(f"source_r_m must be >= 0, got {source_r_m}")
    ambient_c = float(ambient_c)
    source_c = float(source_c)
    source_r_m = float(source_r_m)
    source_xz = tuple(float(x) for x in source_xz)
    if not (len(source_xz) == 2 and math.isfinite(source_xz[0]) and math.isfinite(source_xz[1])):
        raise ValueError("source_xz must have exactly two finite values")
    if not math.isfinite(source_r_m) or source_r_m < 0.0:
        raise ValueError(f"source_r_m must be finite and >= 0, got {source_r_m}")
    for name, v in (("ambient_c", ambient_c), ("source_c", source_c)):
        if not math.isfinite(float(v)):
            raise ValueError(f"{name} must be finite")
    nx, nz = int(nx), int(nz)
    dx = float(extent_m) / (nx - 1)
    dz = float(extent_m) / (nz - 1)
    xs = [(i / (nx - 1) - 0.5) * extent_m for i in range(nx)]
    zs = [(j / (nz - 1) - 0.5) * extent_m for j in range(nz)]

    def idx(i: int, j: int) -> int:
        return j * nx + i

    # Boundary conditions: north + sides fixed ambient; south zero-gradient.
    fixed: dict[int, float] = {}
    for j in range(nz):
        for i in range(nx):
            r = math.hypot(xs[i] - source_xz[0], zs[j] - source_xz[1])
            if r <= source_r_m:
                fixed[idx(i, j)] = float(source_c)
    # North edge (j == nz - 1): fixed ambient.
    for i in range(nx):
        if idx(i, nz - 1) not in fixed:
            fixed[idx(i, nz - 1)] = float(ambient_c)
    # South edge (j == 0): zero-gradient handled by the equation.
    for j in range(nz):
        for i in (0, nx - 1):
            if idx(i, j) not in fixed:
                fixed[idx(i, j)] = float(ambient_c)

    n = nx * nz
    mat = sparse.lil_matrix((n, n))
    rhs = np.zeros(n)
    cx = d_trans_m2_s / dx ** 2
    cz = d_long_m2_s / dz ** 2
    adv = u_m_s / dz
    for j in range(nz):
        for i in range(nx):
            row = idx(i, j)
            if row in fixed:
                mat[row, row] = 1.0
                rhs[row] = fixed[row]
                continue
            if j == 0:
                # South edge (upstream for +z flow): zero-gradient (Neumann).
                mat[row, row] = 1.0
                mat[row, idx(i, j + 1)] = -1.0
                rhs[row] = 0.0
                continue
            if j == nz - 1:
                # North edge (downstream): fixed ambient.
                mat[row, row] = 1.0
                rhs[row] = float(ambient_c)
                continue
            mat[row, row] = 2 * cx + 2 * cz + adv + k_per_s
            mat[row, idx(i - 1, j)] = -cx
            mat[row, idx(i + 1, j)] = -cx
            # Upwind advection in +z: upstream neighbor carries -cz - adv.
            mat[row, idx(i, j - 1)] = -cz - adv
            mat[row, idx(i, j + 1)] = -cz
            rhs[row] = k_per_s * ambient_c
    t = np.asarray(spsolve(mat.tocsr(), rhs)).reshape(nz, nx)
    if not np.all(np.isfinite(t)):
        raise ValueError("plume solve returned non-finite temperatures")
    field = [float(v) for v in t.ravel()]

    resid = _discrete_residual(t, nx, nz, dx, dz, u_m_s, d_trans_m2_s,
                               d_long_m2_s, k_per_s, ambient_c, fixed)
    return {"nx": nx, "nz": nz, "extent_m": float(extent_m),
            "dx_m": dx, "xs": xs, "zs": zs, "field": field,
            "discrete_residual_c_s": resid, "status": STATUS,
            "boundary_precedence": "source_cells_override_boundary",
            "boundary_design": "south_neumann_upstream; north_fixed_ambient; sides_ambient"}


def _discrete_residual(t: np.ndarray, nx: int, nz: int, dx: float,
                       dz: float, u: float, dtx: float, dlo: float,
                       k: float, ambient: float, fixed: dict) -> float:
    worst = 0.0
    for j in range(1, nz - 1):
        for i in range(1, nx - 1):
            if j * nx + i in fixed:
                continue
            lap = (dtx * (t[j, i - 1] - 2 * t[j, i] + t[j, i + 1]) / dx ** 2
                   + dlo * (t[j - 1, i] - 2 * t[j, i] + t[j + 1, i])
                   / dz ** 2)
            r = abs(u * (t[j, i] - t[j - 1, i]) / dz
                    - lap + k * (t[j, i] - ambient))
            worst = max(worst, r)
    return float(worst)


def centerline(field: list, nx: int, nz: int) -> list[float]:
    """South-running center column (x nearest 0)."""
    if nx < 1 or nz < 1:
        raise ValueError("nx and nz must be positive")
    if len(field) != nx * nz:
        raise ValueError(
            f"field length {len(field)} != nx*nz={nx*nz}")
    cx = nx // 2
    return [float(field[j * nx + cx]) for j in range(nz)]


def plume_metrics(sol: dict, ambient_c: float, u_m_s: float,
                  k_per_s: float, thresh_c: float = 1.0) -> dict:
    """Footprint scales from a solved field; lengths in meters."""
    nx, nz, dx = sol["nx"], sol["nz"], sol["dx_m"]
    zs, t = sol["zs"], sol["field"]
    prof = centerline(t, nx, nz)
    anom = [v - ambient_c for v in prof]
    peak = max(anom)
    if peak <= 0.0:
        raise ValueError("source_c must exceed ambient_c for warm-plume metrics")
    # Find contiguous threshold segments for footprint length.
    segments = []
    start_idx = None
    for j, value in enumerate(anom):
        if value >= thresh_c and start_idx is None:
            start_idx = j
        elif value < thresh_c and start_idx is not None:
            segments.append((start_idx, j - 1))
            start_idx = None
    if start_idx is not None:
        segments.append((start_idx, len(anom) - 1))
    longest = max(((zs[b] - zs[a]) for a, b in segments), default=0.0)
    foot_len = round(longest, 1)
    # Half-peak lateral half-width interpolates crossings on the peak row to reduce cell alignment bias.
    mouth = int(np.argmax(anom))
    row = [t[mouth * nx + i] - ambient_c for i in range(nx)]
    threshold = 0.5 * peak
    half = [i for i, v in enumerate(row) if v >= threshold]
    if not half:
        half_w = 0.0
    else:
        left_i, right_i = half[0], half[-1]
        if left_i > 0 and row[left_i - 1] < threshold < row[left_i]:
            frac = (threshold - row[left_i - 1]) / (row[left_i] - row[left_i - 1])
            left_pos = (left_i - 1) + frac
        else:
            left_pos = float(left_i)
        if right_i < nx - 1 and row[right_i + 1] < threshold < row[right_i]:
            frac = (row[right_i] - threshold) / (row[right_i] - row[right_i + 1])
            right_pos = right_i + frac
        else:
            right_pos = float(right_i)
        half_w = (right_pos - left_pos) * dx / 2.0
    if k_per_s == 0.0:
        exchange_length = None
    else:
        exchange_length = u_m_s / k_per_s
    return {"peak_anomaly_c": round(peak, 3),
            "footprint_length_m": round(foot_len, 1),
            "exchange_length_u_over_k_m": (
                round(exchange_length, 1)
                if exchange_length is not None else None),
            "exchange_length_status": (
                "undefined_when_k_zero" if exchange_length is None else "defined"),
            "half_width_m": round(half_w, 1),
            "threshold_c": thresh_c, "status": STATUS}


SCHEMA = "yellowstone.plume2d_excelsior.v1"
EXCELSIOR_M3S = 0.255
EXCELSIOR_C = 93.0


def mixing_rise_c(river_m3s: float, river_c: float) -> float:
    """Fully mixed rise from Excelsior discharge into river flow."""
    river_m3s = _finite("river_m3s", river_m3s)
    river_c = _finite("river_c", river_c)
    if river_m3s < 0.0:
        raise ValueError("river_m3s must be >= 0")
    total_q = EXCELSIOR_M3S + river_m3s
    if total_q <= 0.0:
        raise ValueError("total discharge must be > 0")
    return (EXCELSIOR_M3S * EXCELSIOR_C + river_m3s * river_c) / total_q - river_c


def run_experiment(nx: int = 128, nz: int = 128, extent_m: float = 600.0,
                   ambient_c: float = 17.8, source_c: float = 19.1,
                   source_r_m: float = 90.0,
                   river_m3s: float = 8.0) -> dict:
    """Solve at build settings plus validation anchors. Offline."""
    sol = solve_steady(nx=nx, nz=nz, extent_m=extent_m,
                       ambient_c=ambient_c, source_c=source_c,
                       source_xz=(0.0, -60.0), source_r_m=source_r_m)
    metrics = plume_metrics(sol, ambient_c, U_MAPPED_M_S, K_EXCH_PER_S)
    rise = mixing_rise_c(river_m3s, ambient_c)
    peak = metrics["peak_anomaly_c"]
    return {
        "schema": SCHEMA,
        "status": STATUS,
        "inputs": {
            "nx": nx, "nz": nz, "extent_m": extent_m,
            "u_m_s": U_MAPPED_M_S,
            "u_provenance": U_PROVENANCE,
            "d_long_m2_s": D_LONG_M2_S,
            "d_long_provenance": D_LONG_PROVENANCE,
            "d_trans_m2_s": D_TRANS_M2_S,
            "d_trans_provenance": D_TRANS_PROVENANCE,
            "k_per_s": K_EXCH_PER_S,
            "k_provenance": K_PROVENANCE,
            "ambient_c": ambient_c,
            "ambient_provenance": "build_excelsior_mixing_reach_temp",
            "source_c": source_c,
            "source_provenance": "build_excelsior_mixing_reach_temp",
            "source_xz_m": [0.0, -60.0],
            "source_xz_provenance": "authored_near_field_placement",
            "source_r_m": source_r_m,
            "source_r_provenance": "authored_carried_from_prior_sigma",
        },
        "closure": {
            "discrete_residual_c_s": sol["discrete_residual_c_s"],
            "verdict": ("SUPPORTED" if sol["discrete_residual_c_s"] < 1e-6
                        else "CONTRADICTED"),
        },
        "metrics": metrics,
        "anchors": {
            "excelsior_m3s": EXCELSIOR_M3S,
            "excelsior_m3s_provenance": "transferred_NPS_4050_gal_min",
            "excelsior_c": EXCELSIOR_C,
            "excelsior_c_provenance": "transferred_secondary_93C",
            "river_m3s": river_m3s,
            "river_m3s_provenance": "authored_baseline_boundary",
            "fully_mixed_rise_c": round(rise, 2),
            "peak_within_mixed_bound": bool(0.0 < peak <= rise + 1e-9),
            "mixing_verdict": ("SUPPORTED" if 0.0 < peak <= rise + 1e-9
                               else "CONTRADICTED"),
            "ir_gradient_zones": 'NOT TESTED (Burkhalter (1979) zone coordinates not digitized)',
            "fully_mixed_bound_interpretation": (
                "diagnostic upper-bound comparison; not a coupled heat-budget closure"),
        },
    }
