"""Real-time rainfall, infiltration, runoff and soil-water model on a regular grid.
NumPy-only; usable from godot-python, a Godot 4 Python extension, or a sidecar. Units SI (meters, seconds); rain rates arrive in mm/h at the API boundary. HydroSim.balance() verifies mass conservation.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

G = 9.81
MM_H_TO_M_S = 1.0 / 3.6e6

# Columns: porosity, suction psi (mm), Green-Ampt effective Ks (mm/h), theta_fc, theta_wp.
SOILS = {
    "sand":         (0.437,    49.5,   117.8,     0.10,     0.04),
    "sandy_loam":   (0.453,   110.1,    10.9,     0.21,     0.09),
    "loam":         (0.463,    88.9,     3.4,     0.27,     0.12),
    "silt_loam":    (0.501,   166.8,     6.5,     0.33,     0.13),
    "clay_loam":    (0.464,   208.8,     1.0,     0.36,     0.20),
    "clay":         (0.475,   316.3,     0.3,     0.40,     0.27),
    "sinter_apron": (0.10,      0.0,     0.1,     0.05,     0.02),
    "andic_meadow": (0.65,    180.0,    30.0,     0.40,     0.15),
}


# Rain microphysics helpers for particle visuals; the water balance uses the rate only.
def marshall_palmer(rate_mm_h: float):
    """Return (N0 [m^-3 mm^-1], Lambda [mm^-1]) for the Marshall-Palmer distribution."""
    r = max(float(rate_mm_h), 1e-3)
    return 8000.0, 4.1 * r ** -0.21


def sample_drop_diameters(rate_mm_h: float, n: int, rng: np.random.Generator,
                          d_min: float = 0.3, d_max: float = 6.0) -> np.ndarray:
    """Drop diameters in mm, exponential (Marshall-Palmer) truncated to [d_min, d_max]."""
    _, lam = marshall_palmer(rate_mm_h)
    d = rng.exponential(1.0 / lam, n)
    bad = (d < d_min) | (d > d_max)
    while bad.any():
        d[bad] = rng.exponential(1.0 / lam, int(bad.sum()))
        bad = (d < d_min) | (d > d_max)
    return d


def terminal_velocity(d_mm):
    """Raindrop terminal velocity in m/s (Atlas et al. 1973 fit): ~6.5 m/s at 2 mm."""
    d = np.asarray(d_mm, dtype=float)
    return np.maximum(9.65 - 10.3 * np.exp(-0.6 * d), 0.0)


# Rain field.
class RainField:
    """Per-cell rain intensity field in m/s from a scalar mm/h slider.
    mode uniform applies the same rate everywhere; mode cells drifts a handful of Gaussian storm cells (sin^2 life-cycle), normalized by a slow running mean so the domain-average rate tracks the slider while the pattern stays patchy and intermittent. Slider 0 gives zero rain.
    """

    def __init__(self, shape, dx, mode="cells", n_cells=5, radius_m=None,
                 wind_mps=(1.5, 0.5), lifetime_s=900.0, seed=0):
        if mode not in ("uniform", "cells"):
            raise ValueError("mode must be 'uniform' or 'cells'")
        ny, nx = shape
        self.shape = (ny, nx)
        self.mode = mode
        self.Lx, self.Ly = nx * dx, ny * dx
        xs = (np.arange(nx) + 0.5) * dx
        ys = (np.arange(ny) + 0.5) * dx
        self.X, self.Y = np.meshgrid(xs, ys)
        self.rng = np.random.default_rng(seed)
        self.wind = np.asarray(wind_mps, float)
        self.lifetime = float(lifetime_s)
        self.radius = float(radius_m) if radius_m else 0.18 * min(self.Lx, self.Ly)
        n = int(n_cells)
        self.cx = self.rng.uniform(0, self.Lx, n)
        self.cy = self.rng.uniform(0, self.Ly, n)
        self.life = self.lifetime * self.rng.uniform(0.7, 1.3, n)
        self.age = self.rng.uniform(0, 1, n) * self.life
        self.amp = self.rng.gamma(2.0, 0.5, n)
        self.rad = self.radius * self.rng.uniform(0.6, 1.4, n)
        self._norm: Optional[float] = None

    def _respawn(self, idx):
        k = len(idx)
        self.cx[idx] = self.rng.uniform(0, self.Lx, k)
        self.cy[idx] = self.rng.uniform(0, self.Ly, k)
        self.life[idx] = self.lifetime * self.rng.uniform(0.7, 1.3, k)
        self.age[idx] = 0.0
        self.amp[idx] = self.rng.gamma(2.0, 0.5, k)
        self.rad[idx] = self.radius * self.rng.uniform(0.6, 1.4, k)

    def update(self, dt: float, rate_mm_h: float) -> np.ndarray:
        """Advance storm cells by dt seconds and return the rain field in m/s."""
        rate = max(float(rate_mm_h), 0.0) * MM_H_TO_M_S
        if self.mode == "uniform":
            return np.full(self.shape, rate)

        self.cx = (self.cx + self.wind[0] * dt) % self.Lx
        self.cy = (self.cy + self.wind[1] * dt) % self.Ly
        self.age += dt
        dead = np.flatnonzero(self.age >= self.life)
        if dead.size:
            self._respawn(dead)

        field = np.zeros(self.shape)
        for cx, cy, a, r, age, life in zip(self.cx, self.cy, self.amp, self.rad, self.age, self.life):
            ddx = (self.X - cx + self.Lx / 2) % self.Lx - self.Lx / 2
            ddy = (self.Y - cy + self.Ly / 2) % self.Ly - self.Ly / 2
            env = math.sin(math.pi * min(age / life, 1.0)) ** 2
            field += a * env * np.exp(-(ddx * ddx + ddy * ddy) / (2.0 * r * r))

        m = float(field.mean())
        if self._norm is None:
            self._norm = max(m, 1e-9)
        else:
            alpha = min(1.0, dt / self.lifetime)
            self._norm = max((1 - alpha) * self._norm + alpha * m, 1e-9)
        return field * (rate / self._norm)


# Terrain and drainage network helpers.
def make_terrain(nx, ny, dx, relief_m=3.0, tilt=0.03, beta=3.0, pit_fill=0.7, seed=0) -> np.ndarray:
    """Fractal terrain by spectral synthesis plus a regional tilt that drains toward the last row (south edge); relief_m is the noise standard deviation in meters.
    pit_fill blends raw surface toward pit-filled (0 raw, 1 fully drained); raw fractal terrain traps rain in closed depressions, and about 0.7 keeps some ponds while letting most of the catchment drain.
    """
    rng = np.random.default_rng(seed)
    spec = np.fft.fft2(rng.standard_normal((ny, nx)))
    fy = np.fft.fftfreq(ny)[:, None]
    fx = np.fft.fftfreq(nx)[None, :]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    spec *= f ** (-beta / 2.0)
    spec[0, 0] = 0.0
    noise = np.real(np.fft.ifft2(spec))
    noise = (noise - noise.mean()) / (noise.std() + 1e-12) * relief_m
    z = noise + tilt * dx * (ny - 1 - np.arange(ny))[:, None]
    if pit_fill > 0.0:
        z = z + float(pit_fill) * (priority_flood(z) - z)
    return z


def priority_flood(z: np.ndarray, eps: float = 1e-4) -> np.ndarray:
    """Barnes et al. (2014) Priority-Flood + epsilon: fills pits and gives flats a gradient."""
    ny, nx = z.shape
    filled = z.astype(float).copy()
    seen = np.zeros((ny, nx), bool)
    heap = []
    for i in range(ny):
        for j in range(nx):
            if i in (0, ny - 1) or j in (0, nx - 1):
                seen[i, j] = True
                heapq.heappush(heap, (filled[i, j], i, j))
    nbrs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    while heap:
        zc, i, j = heapq.heappop(heap)
        for di, dj in nbrs:
            a, b = i + di, j + dj
            if 0 <= a < ny and 0 <= b < nx and not seen[a, b]:
                seen[a, b] = True
                filled[a, b] = max(filled[a, b], zc + eps)
                heapq.heappush(heap, (filled[a, b], a, b))
    return filled


def flow_accumulation(z: np.ndarray) -> np.ndarray:
    """D8 flow accumulation (cell counts) on the pit-filled surface. Edges drain outward."""
    ny, nx = z.shape
    filled = priority_flood(z)
    pad = np.pad(filled, 1, mode="edge")
    for sl in (np.s_[0, :], np.s_[-1, :], np.s_[:, 0], np.s_[:, -1]):
        pad[sl] -= 1e-3  # outside the domain is slightly lower than the edge cell
    offs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    drops = []
    for di, dj in offs:
        dist = math.hypot(di, dj)
        nb = pad[1 + di:ny + 1 + di, 1 + dj:nx + 1 + dj]
        drops.append((filled - nb) / dist)
    best = np.argmax(np.stack(drops), axis=0)
    ii, jj = np.meshgrid(np.arange(ny), np.arange(nx), indexing="ij")
    di = np.array([o[0] for o in offs])[best]
    dj = np.array([o[1] for o in offs])[best]
    ti, tj = ii + di, jj + dj
    inside = (ti >= 0) & (ti < ny) & (tj >= 0) & (tj < nx)
    target = np.where(inside, ti * nx + tj, -1).ravel().astype(np.int64)

    # Kahn topological sweep in level batches: priority_flood guarantees strict monotonic descent so every edge runs upstream-to-downstream, and each batch is the cells with zero remaining in-degree processed with np.add.at.
    n = ny * nx
    acc = np.ones(n, dtype=np.float64)
    valid = target >= 0
    in_deg = np.zeros(n, dtype=np.int64)
    np.add.at(in_deg, target[valid], 1)

    processed = np.zeros(n, dtype=bool)
    frontier = np.flatnonzero(in_deg == 0)
    while frontier.size:
        processed[frontier] = True
        with_target = frontier[target[frontier] >= 0]
        if with_target.size:
            np.add.at(acc, target[with_target], acc[with_target])
            np.add.at(in_deg, target[with_target], -1)
        frontier = np.flatnonzero((in_deg == 0) & ~processed)
    return acc.reshape(ny, nx)


def channel_mask_from_terrain(z: np.ndarray, acc_threshold: Optional[int] = None,
                              min_fraction: float = 0.01) -> np.ndarray:
    acc = flow_accumulation(z)
    n = z.size
    thr = acc_threshold if acc_threshold else max(20, int(0.01 * n))
    mask = acc >= thr
    if mask.sum() < min_fraction * n:
        k = max(1, int(min_fraction * n))
        cut = np.partition(acc.ravel(), -k)[-k]
        mask = acc >= cut
    return mask


def default_soil_map(z: np.ndarray):
    """Sandy loam on the upper third of elevations, loam in the middle, clay loam in the low third."""
    names = ["sandy_loam", "loam", "clay_loam"]
    lo, hi = np.quantile(z, [1 / 3, 2 / 3])
    idx = np.where(z >= hi, 0, np.where(z >= lo, 1, 2))
    return idx, names


def midway_soil_map(z: np.ndarray, sinter_mask: np.ndarray | None = None):
    """Sinter apron where mask is True; andic meadow elsewhere."""
    names = ["sinter_apron", "andic_meadow"]
    if sinter_mask is None:
        return np.ones_like(z, dtype=int), names
    mask = np.asarray(sinter_mask, dtype=bool)
    idx = np.where(mask, 0, 1).astype(int)
    return idx, names


# Climate and configuration.
@dataclass
class Climate:
    """Inputs for FAO-56 Penman-Monteith. Radiation follows a simple day/night cycle."""
    temp_c: float = 20.0
    rel_humidity: float = 60.0
    wind_u2: float = 2.0            # m/s at 2 m height
    rn_mj_m2_day: float = 14.0      # daily-mean net radiation
    elevation_m: float = 100.0
    diurnal: bool = True
    start_hour: float = 8.0

    def et0_mm_day(self, t_s: float) -> float:
        tod = ((self.start_hour * 3600.0 + t_s) % 86400.0) / 86400.0
        rn = self.rn_mj_m2_day * (1.0 - math.cos(2 * math.pi * tod)) if self.diurnal else self.rn_mj_m2_day
        T = self.temp_c
        es = 0.6108 * math.exp(17.27 * T / (T + 237.3))
        ea = es * self.rel_humidity / 100.0
        delta = 4098.0 * es / (T + 237.3) ** 2
        P = 101.3 * ((293.0 - 0.0065 * self.elevation_m) / 293.0) ** 5.26
        gamma = 0.000665 * P
        num = 0.408 * delta * rn + gamma * 900.0 / (T + 273.0) * self.wind_u2 * (es - ea)
        den = delta + gamma * (1.0 + 0.34 * self.wind_u2)
        return max(num / den, 0.0)


@dataclass
class HydroConfig:
    infiltration: str = "green_ampt"      # "green_ampt" | "horton" | "constant" | "none"
    horton_f0_mm_h: float = 100.0
    horton_fc_mm_h: float = 5.0
    horton_k_per_h: float = 1.0
    recovery_time_s: float = 1800.0       # capacity recovery e-folding time when no water is ponded
    root_depth_m: float = 0.5
    manning_overland: float = 0.08
    manning_channel: float = 0.035
    open_edges: Sequence[str] = ("N", "E", "S", "W")   # edges that discharge; others are walls
    outflow_slope: float | str = 0.01     # fixed value, or "auto" to derive from terrain
    cfl_alpha: float = 0.7
    max_substeps: int = 40                # per step; the last substep absorbs any remainder
    h_min: float = 1e-5                   # m; below this a face is treated as dry
    froude_max: float = 1.0
    enable_et: bool = True
    depletion_p: float = 0.5              # FAO-56 allowable depletion fraction
    perc_factor: float = 1.0              # scales drainage to groundwater (0 disables)
    perc_exponent: float = 3.0
    gw_recession_time_s: float = 86400.0
    channel_acc_threshold: Optional[int] = None
    # Thin-film sheet-flow switch (Chow 1959 sec 7-5; Katul, Wiberg, Albertson, Hornberger 2002, Water Resour. Res. 38(11):1250). Below Re = |q|/nu the Manning friction formula loses its empirical basis and the face flux follows the laminar Navier-Stokes thin-film form q = -g h^3/(3 nu) * grad.
    reynolds_switch: float = 500.0
    kinematic_viscosity_m2_s: float = 1.0e-6


# The simulation.
class HydroSim:
    def __init__(self, z, dx, soil_map=None, soil_names=None, config: Optional[HydroConfig] = None,
                 climate: Optional[Climate] = None, rain: Optional[RainField] = None,
                 kc=0.8, init_wetness=0.5, init_depth=None, channel_mask=None):
        self.cfg = config or HydroConfig()
        self.climate = climate or Climate()
        self.z = np.asarray(z, dtype=np.float64).copy()
        self.ny, self.nx = self.z.shape
        self.dx = float(dx)
        self.area = self.dx * self.dx
        self.t = 0.0
        shape = self.z.shape
        self.rain = rain or RainField(shape, self.dx)

        # soil parameters per cell
        names = list(soil_names) if soil_names else ["loam"]
        smap = np.zeros(shape, int) if soil_map is None else np.asarray(soil_map, int)
        tab = np.array([SOILS[n] for n in names])[smap]
        cc = np.ascontiguousarray
        self.por = cc(tab[..., 0])
        self.psi = cc(tab[..., 1] * 1e-3)
        self.Ks = cc(tab[..., 2] * MM_H_TO_M_S)
        Zr = self.cfg.root_depth_m
        self.S_sat = cc(self.por * Zr)
        self.S_fc = cc(tab[..., 3] * Zr)
        self.S_wp = cc(tab[..., 4] * Zr)
        self.kc = np.broadcast_to(np.asarray(kc, float), shape).copy()

        # state
        self.h = np.zeros(shape) if init_depth is None else np.broadcast_to(np.asarray(init_depth, float), shape).copy()
        self.S = self.S_wp + float(init_wetness) * (self.S_fc - self.S_wp)
        self.F = np.zeros(shape)          # Green-Ampt cumulative infiltration (m)
        self.Th = np.zeros(shape)         # Horton effective time (s)
        # Green-Ampt event state per Chu 1978 and Mein-Larson 1973.
        self.theta_i_event = (self.S / self.cfg.root_depth_m).copy()
        self.rain_hiatus_s = np.zeros(shape)
        self.Vg = 0.0                     # lumped groundwater volume (m^3)
        self.qx = np.zeros((self.ny, self.nx - 1))
        self.qy = np.zeros((self.ny - 1, self.nx))

        # Channels and roughness; baseflow weights follow Freeze and Cherry 1979 sec 6.5, concentrating aquifer discharge at low-elevation channel cells weighted by flow accumulation.
        if channel_mask is None:
            self._acc = flow_accumulation(self.z)
            thr = (self.cfg.channel_acc_threshold
                   if self.cfg.channel_acc_threshold
                   else max(20, int(0.01 * self.z.size)))
            mask = self._acc >= thr
            if mask.sum() < 0.01 * self.z.size:
                k = max(1, int(0.01 * self.z.size))
                cut = np.partition(self._acc.ravel(), -k)[-k]
                mask = self._acc >= cut
            self.channel = mask
        else:
            self.channel = np.asarray(channel_mask, bool)
            self._acc = None
        self._baseflow_weights = self._compute_baseflow_weights()
        self.n_map = np.where(self.channel, self.cfg.manning_channel, self.cfg.manning_overland)
        self._n2x = (0.5 * (self.n_map[:, :-1] + self.n_map[:, 1:])) ** 2
        self._n2y = (0.5 * (self.n_map[:-1, :] + self.n_map[1:, :])) ** 2

        # Resolve outflow_slope: numeric value, or auto from edge terrain gradient (Chow 1959 section 5-5 normal-depth boundary).
        self._outflow_slope = self._resolve_outflow_slope()
        self._boundary_condition = ("closed" if not self.cfg.open_edges
                                    else "open_" + "".join(
                                        sorted(self.cfg.open_edges)).lower())

        self.tot = dict(rain=0.0, outflow=0.0, et_surface=0.0, et_soil=0.0)
        self._storage0 = self._storage_total()
        self._rain_field = np.zeros(shape)
        self._rain_sum = 0.0

    def _compute_baseflow_weights(self) -> np.ndarray:
        """Normalized per-cell weights for groundwater baseflow return."""
        if self._acc is not None:
            w = np.where(self.channel, self._acc, 0.0)
            total = float(w.sum())
            if total > 0.0:
                return (w / total).astype(np.float64)
        nch = int(self.channel.sum())
        if nch > 0:
            return self.channel.astype(np.float64) / float(nch)
        return np.zeros_like(self.z, dtype=np.float64)

    def _resolve_outflow_slope(self) -> float:
        """Return a numeric slope; derive from terrain if cfg says 'auto'."""
        slope = self.cfg.outflow_slope
        if isinstance(slope, (int, float)):
            return float(slope)
        if slope != "auto":
            raise ValueError(f"outflow_slope must be a number or 'auto', "
                             f"got {slope!r}")
        edges = set(self.cfg.open_edges)
        if not edges:
            return 0.0
        samples = []
        if "S" in edges and self.ny >= 2:
            samples.append((self.z[-2, :] - self.z[-1, :]).mean())
        if "N" in edges and self.ny >= 2:
            samples.append((self.z[1, :] - self.z[0, :]).mean())
        if "E" in edges and self.nx >= 2:
            samples.append((self.z[:, -2] - self.z[:, -1]).mean())
        if "W" in edges and self.nx >= 2:
            samples.append((self.z[:, 1] - self.z[:, 0]).mean())
        if not samples:
            return 0.0
        s = float(np.mean(samples)) / self.dx
        return float(max(s, 1e-6))

    # ---------------- bookkeeping ----------------
    def storages(self) -> dict:
        return dict(surface=float(self.h.sum() * self.area),
                    soil=float(self.S.sum() * self.area),
                    groundwater=float(self.Vg))

    def _storage_total(self) -> float:
        return sum(self.storages().values())

    def balance(self) -> dict:
        """rain - outflow - ET - delta_storage should be ~0 (float round-off only)."""
        d_storage = self._storage_total() - self._storage0
        err = self.tot["rain"] - self.tot["outflow"] - self.tot["et_surface"] - self.tot["et_soil"] - d_storage
        scale = max(self.tot["rain"], abs(self._storage0), 1e-12)
        return dict(self.tot, d_storage=d_storage, error=err, rel_error=err / scale)

    # ---------------- outputs for rendering ----------------
    def depth_map(self) -> np.ndarray:
        return self.h.astype(np.float32)

    def soil_saturation(self) -> np.ndarray:
        return (self.S / self.S_sat).astype(np.float32)

    def flow_vectors(self):
        """Cell-centred unit discharge (m^2/s) as (ux, uy); divide by depth for velocity."""
        qxp = np.pad(self.qx, ((0, 0), (1, 1)))
        qyp = np.pad(self.qy, ((1, 1), (0, 0)))
        return (0.5 * (qxp[:, :-1] + qxp[:, 1:])).astype(np.float32), \
               (0.5 * (qyp[:-1, :] + qyp[1:, :])).astype(np.float32)

    # ---------------- stepping ----------------
    def _cfl_dt(self) -> float:
        hmax = max(float(self.h.max()), 1e-3)
        return self.cfg.cfl_alpha * self.dx / math.sqrt(G * hmax)

    def step(self, dt: float, rain_rate_mm_h: float = 0.0) -> dict:
        """Advance exactly dt seconds. Returns diagnostics."""
        if dt <= 0:
            return dict(substeps=0, cfl_exceeded=False,
                        cfl_exceeded_count=0,
                        boundary_condition=self._boundary_condition,
                        outflow_slope=self._outflow_slope)
        self._rain_field = self.rain.update(dt, rain_rate_mm_h)
        self._rain_sum = float(self._rain_field.sum())
        remaining, n, exceeded = float(dt), 0, 0
        while remaining > 1e-12:
            ds = min(remaining, self._cfl_dt())
            n += 1
            if n >= self.cfg.max_substeps and ds < remaining:
                exceeded += 1
                ds = remaining
            self.h += self._rain_field * ds
            self.tot["rain"] += self._rain_sum * ds * self.area
            self._infiltrate(ds)
            self._flow(ds)
            remaining -= ds
            self.t += ds
        self._slow_processes(dt)
        return dict(substeps=n, cfl_exceeded=bool(exceeded),
                    cfl_exceeded_count=exceeded,
                    boundary_condition=self._boundary_condition,
                    outflow_slope=self._outflow_slope)

    # ---------------- infiltration ----------------
    @staticmethod
    def _ga_increment(F, A, K, ds):
        """Exact Green-Ampt capacity depth over one step.
        Solves g(Fn) = g(F) + K*ds with g(x) = x - A*ln(1 + x/A); the function is convex and increasing on x>=0, so eight Newton steps from sqrt(2*A*rhs) converge to machine precision.
        """
        for name, arr in (("F", F), ("A", A), ("K", K)):
            if not np.all(np.isfinite(arr)):
                raise ValueError(f"Green-Ampt input {name} must be finite")
        if np.any(np.asarray(ds) < 0):
            raise ValueError("Green-Ampt time step ds must be >= 0")
        A = np.maximum(A, 1e-6)
        rhs = (F - A * np.log1p(F / A)) + K * ds
        x = np.sqrt(2.0 * A * rhs)
        for _ in range(8):
            gx = x - A * np.log1p(x / A)
            x = x - (gx - rhs) * (A + x) / np.maximum(x, 1e-14)
        resid = np.abs(x - A * np.log1p(x / A) - rhs)
        tol = 1e-10 * np.maximum(np.abs(rhs), 1.0)
        if np.any(resid > tol):
            raise RuntimeError("Green-Ampt Newton did not converge to tolerance")
        return np.maximum(x - F, 0.0)

    def _infiltrate(self, ds):
        cfg = self.cfg
        h, S, F, Th = self.h.ravel(), self.S.ravel(), self.F.ravel(), self.Th.ravel()   # views
        theta_i = self.theta_i_event.ravel()
        hiatus = self.rain_hiatus_s.ravel()
        Zr = cfg.root_depth_m
        wet = h > 1e-9
        # Dry hiatus >= recovery_time_s followed by ponded water starts a new event: reset pre-event moisture and clear accumulators (Chu 1978; Mein and Larson 1973).
        new_event = wet & (hiatus >= cfg.recovery_time_s)
        if np.any(new_event):
            theta_i[new_event] = S[new_event] / Zr
            F[new_event] = 0.0
            Th[new_event] = 0.0
        active = np.flatnonzero(wet)
        if active.size == 0:
            hiatus += ds
            return
        ha = h[active]
        Ssat = self.S_sat.ravel()[active]
        Ka = self.Ks.ravel()[active]
        room = np.maximum(Ssat - S[active], 0.0)
        th_advance = ds
        if cfg.infiltration == "green_ampt":
            Fa = F[active]
            # Green-Ampt deficit is theta_s - theta_i_event, frozen during an event.
            theta_s_a = self.por.ravel()[active]
            dtheta = np.maximum(theta_s_a - theta_i[active], 1e-6)
            cap = self._ga_increment(Fa, self.psi.ravel()[active] * dtheta, Ka, ds)
        elif cfg.infiltration == "horton":
            f0 = cfg.horton_f0_mm_h * MM_H_TO_M_S
            fc = cfg.horton_fc_mm_h * MM_H_TO_M_S
            k = cfg.horton_k_per_h / 3600.0
            T = Th[active]
            cap = fc * ds + (f0 - fc) / k * (np.exp(-k * T) - np.exp(-k * (T + ds)))
            # Mein and Larson 1973 correction: advance effective time by the water-limited fraction so capacity does not decay under rain below infiltrability.
            avail = np.minimum(cap, ha)
            th_advance = ds * np.where(cap > 1e-18, avail / cap, 0.0)
        elif cfg.infiltration == "constant":
            cap = Ka * ds
        elif cfg.infiltration == "none":
            hiatus[wet] = 0.0
            hiatus[~wet] = hiatus[~wet] + ds
            return
        else:
            raise ValueError("unknown infiltration model: %s" % cfg.infiltration)
        inf = np.minimum(np.minimum(cap, ha), room)
        h[active] -= inf
        S[active] += inf
        F[active] += inf
        Th[active] += th_advance
        # Hiatus bookkeeping: wet cells reset, dry cells accumulate dry time.
        hiatus[wet] = 0.0
        hiatus[~wet] = hiatus[~wet] + ds

    # ---------------- overland flow ----------------
    def _face_update(self, q, hf, grad, n2, ds):
        cfg = self.cfg
        wet = hf > cfg.h_min
        hs = np.where(wet, hf, cfg.h_min)
        num = q - G * hs * ds * grad
        den = 1.0 + G * ds * n2 * np.abs(q) / hs ** (7.0 / 3.0)
        qn_manning = np.where(wet, num / den, 0.0)
        # Thin-film laminar branch (Chow 1959 sec 7-5; Katul et al. 2002); the switch requires the Manning-derived and the laminar Reynolds numbers to both lie below reynolds_switch, with the second gate stopping deep water from being driven by the laminar expression that becomes unbounded at large h.
        nu = cfg.kinematic_viscosity_m2_s
        q_lam = np.where(wet, -G * hs ** 3 / (3.0 * nu) * grad, 0.0)
        re_manning = np.abs(qn_manning) / max(nu, 1e-18)
        re_laminar = np.abs(q_lam) / max(nu, 1e-18)
        use_laminar = (wet
                       & (re_manning < cfg.reynolds_switch)
                       & (re_laminar < cfg.reynolds_switch))
        qn = np.where(use_laminar, q_lam, qn_manning)
        lim = cfg.froude_max * hs * np.sqrt(G * hs)
        return np.clip(qn, -lim, lim)

    def _edge_out(self, depth, n):
        cfg = self.cfg
        q = depth ** (5.0 / 3.0) / n * math.sqrt(self._outflow_slope)
        return np.where(depth > cfg.h_min, q, 0.0)

    def _flow(self, ds):
        cfg, z, h, dx = self.cfg, self.z, self.h, self.dx
        ny, nx = self.ny, self.nx
        eta = z + h

        hfx = np.maximum(eta[:, :-1], eta[:, 1:]) - np.maximum(z[:, :-1], z[:, 1:])
        qx = self._face_update(self.qx, hfx, (eta[:, 1:] - eta[:, :-1]) / dx, self._n2x, ds)
        hfy = np.maximum(eta[:-1, :], eta[1:, :]) - np.maximum(z[:-1, :], z[1:, :])
        qy = self._face_update(self.qy, hfy, (eta[1:, :] - eta[:-1, :]) / dx, self._n2y, ds)

        qxf = np.zeros((ny, nx + 1))
        qyf = np.zeros((ny + 1, nx))
        qxf[:, 1:-1], qyf[1:-1, :] = qx, qy
        edges = set(cfg.open_edges)
        nm = self.n_map
        if "W" in edges: qxf[:, 0] = -self._edge_out(h[:, 0], nm[:, 0])
        if "E" in edges: qxf[:, -1] = self._edge_out(h[:, -1], nm[:, -1])
        if "N" in edges: qyf[0, :] = -self._edge_out(h[0, :], nm[0, :])
        if "S" in edges: qyf[-1, :] = self._edge_out(h[-1, :], nm[-1, :])

        # positivity limiter: a cell cannot export more than it holds
        out = (np.maximum(qxf[:, 1:], 0) + np.maximum(-qxf[:, :-1], 0)
               + np.maximum(qyf[1:, :], 0) + np.maximum(-qyf[:-1, :], 0)) * (ds / dx)
        f = np.where(out > h, h / np.maximum(out, 1e-300), 1.0)
        fp = np.pad(f, 1, constant_values=1.0)
        qxf *= np.where(qxf > 0, fp[1:-1, 0:nx + 1], fp[1:-1, 1:nx + 2])
        qyf *= np.where(qyf > 0, fp[0:ny + 1, 1:-1], fp[1:ny + 2, 1:-1])

        self.h = h - (ds / dx) * ((qxf[:, 1:] - qxf[:, :-1]) + (qyf[1:, :] - qyf[:-1, :]))
        np.maximum(self.h, 0.0, out=self.h)   # clears round-off only; limiter guarantees >= 0
        self.qx, self.qy = qxf[:, 1:-1].copy(), qyf[1:-1, :].copy()

        leaving = (np.maximum(-qxf[:, 0], 0).sum() + np.maximum(qxf[:, -1], 0).sum()
                   + np.maximum(-qyf[0, :], 0).sum() + np.maximum(qyf[-1, :], 0).sum())
        self.tot["outflow"] += float(leaving) * dx * ds

    # ---------------- evapotranspiration, drainage, groundwater ----------------
    def _slow_processes(self, dt):
        cfg = self.cfg
        if cfg.enable_et:
            et0 = self.climate.et0_mm_day(self.t) * 1e-3 / 86400.0     # m/s
            e_surf = np.minimum(self.h, et0 * dt)
            self.h -= e_surf
            self.tot["et_surface"] += float(e_surf.sum()) * self.area

            taw = np.maximum(self.S_fc - self.S_wp, 1e-9)
            raw = cfg.depletion_p * taw
            dr = self.S_fc - self.S
            ks = np.where(dr <= raw, 1.0, np.clip((taw - dr) / np.maximum(taw - raw, 1e-9), 0.0, 1.0))
            eta = np.minimum(ks * self.kc * et0 * dt, np.maximum(self.S - self.S_wp, 0.0))
            self.S -= eta
            self.tot["et_soil"] += float(eta.sum()) * self.area

        if cfg.perc_factor > 0:
            rel = np.clip((self.S - self.S_fc) / np.maximum(self.S_sat - self.S_fc, 1e-9), 0.0, 1.0)
            drain = np.minimum(cfg.perc_factor * self.Ks * dt * rel ** cfg.perc_exponent,
                               np.maximum(self.S - self.S_fc, 0.0))
            self.S -= drain
            self.Vg += float(drain.sum()) * self.area

        if self.Vg > 0.0:
            new = self.Vg * math.exp(-dt / cfg.gw_recession_time_s)
            base = self.Vg - new
            self.Vg = new
            # Baseflow concentrates at low-elevation channel cells per Freeze and Cherry 1979 sec 6.5, weighted by D8 flow accumulation.
            self.h += self._baseflow_weights * (base / self.area)
