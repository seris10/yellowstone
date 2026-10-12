"""M04 vegetation: suitability fields + patch biomass + planting proposals.

Paper forms:
    λs(p) = λs,0 · Mhabitat(p) · fs(soil, moisture, slope, aspect, canopy,
             disturbance) · Mexclusion(p)      (artist/science inputs)
    dB/dt = r · flight · fwater · B(1−B/K) − G  (dimensionless index form)

Rules: proposals are STABLE records with persistent IDs (never a runtime
probability field, never a resample of data/placements.json). Thermal/water
exclusions via M03 aprons. Separation is ENFORCED per guild (spatial hash),
suitability is EVALUATED per candidate from terrain slope + moisture +
canopy + exclusion (never assumed), and randomness is per-candidate
(seed:guild:cell) so rejections cannot shift other candidates.
"""
from __future__ import annotations

import copy
import math
import random
from pathlib import Path

import numpy as np

GRID = 1025
STEP = 4.0
HALF = 2048.0

# Maximum candidate cells scanned per propose_plantings_reviewed call. Existing
# pipeline grids peak at ~22k cells (meadow r=110); anything larger is
# coarsened (see function docstring) instead of burning minutes.
GRID_BUDGET = 25000

# Per-guild coefficients: authored inputs, not inferred from field data.
GUILDS = {
    "lodgepole_pine": {"lambda0": 0.9, "min_sep_m": 6.0,
                       "slope_max_deg": 25.0, "needs": ["forest_lodgepole",
                                                        "forest_edge", "forest_moist"],
                       "excluded": ["thermal_core", "thermal_outflow_hot",
                                    "river_pool", "river_riffle"]},
    "meadow_grass": {"lambda0": 0.8, "min_sep_m": 1.5,
                     "slope_max_deg": 12.0, "needs": ["dry_meadow",
                                                      "wet_meadow", "river_bank"],
                     "excluded": ["thermal_core", "thermal_outflow_hot"]},
    "riparian_sedge": {"lambda0": 0.7, "min_sep_m": 1.0,
                       "slope_max_deg": 8.0, "needs": ["river_bank",
                                                      "cold_wetland", "wet_meadow"],
    "excluded": ["thermal_core", "thermal_outflow_hot",
                                 "sinter_dry"]},
}

# Coefficients are authored, not inferred from field data.
VEGETATION_PROVENANCE = {
    "status": "authored_illustrative_coefficients_not_inferred_from_field_data",
    "real_data_gap": ("Guild parameters (lambda0, slope_max, min_sep, needs, excluded) "
                      "are authored scenario values. Real integration requires field surveys "
                      "or remote-sensing-derived suitability from actual vegetation maps."),
    "coefficients": {k: v for k, v in GUILDS.items()},
}


def suitability(lambda0: float = 0.9, m_habitat: float = 1.0,
                factors: dict = None,
                m_exclusion: float = 1.0) -> float:
    """λs(p): all terms in [0,1]; returns [0,1] density potential."""
    lambda0 = min(1.0, max(0.0, float(lambda0)))
    f = 1.0
    for v in (factors or {}).values():
        f *= min(1.0, max(0.0, float(v)))
    return float(lambda0 * min(1.0, max(0.0, float(m_habitat))) * f
                 * min(1.0, max(0.0, float(m_exclusion))))


def guild_suitability(guild: str, habitat_id: str, slope_deg: float,
                      moisture: float, canopy: float = 0.5,
                      in_exclusion: bool = False) -> float:
    """Convenience evaluator used by proposal review + tests."""
    g = GUILDS[guild]
    if habitat_id in g["excluded"] or in_exclusion:
        return 0.0
    m_hab = 1.0 if habitat_id in g["needs"] else 0.25
    slope_f = max(0.0, 1.0 - slope_deg / g["slope_max_deg"]) if g["slope_max_deg"] else 1.0
    return suitability(g.get("lambda0"), m_hab,
                       {"moisture": 0.3 + 0.7 * moisture,
                        "slope": slope_f, "canopy": 1.0 - 0.5 * canopy},
                       1.0)


def sunlight(hour: float) -> float:
    return max(0.0, math.sin((float(hour) - 6.0) * math.pi / 12.0))


def patch_step(patches: list, hour: float, dt_s: float,
               grazers: dict | None = None) -> tuple[list, dict]:
    """Advance patch biomass like ecosystem.gd::_advance_patches (growth part).

    grazers: {grazer_id: {patch_id, active, rate_per_second}}. The rate is
    a biomass-index decrement per second, so demand is in the same
    dimensionless index units as biomass (no kg conversion exists).
    Returns (updated_patches, ledger{consumed, growth}).
    """
    dt_s = _finite_value("dt_s", dt_s)
    if dt_s < 0:
        raise ValueError("dt_s must be >= 0")
    hour = _finite_value("hour", hour)
    out = copy.deepcopy(patches)
    seen_ids = set()
    for p in out:
        pid = p.get("id")
        if pid in seen_ids:
            raise ValueError(f"duplicate patch id {pid!r}")
        seen_ids.add(pid)
    sun = sunlight(hour)
    hours = dt_s / 3600.0
    tot_growth = tot_eaten = 0.0
    for p in out:
        b = _nonnegative_value(f"patch {p.get('id')!r} biomass",
                               p["biomass"])
        k = _finite_value(f"patch {p.get('id')!r} capacity",
                          p.get("capacity", 1.0))
        if k <= 0:
            k = 1.0
        m = min(1.0, max(0.0, _finite_value(
            f"patch {p.get('id')!r} moisture", p.get("moisture", 0.5))))
        rate = _nonnegative_value(f"patch {p.get('id')!r} growth_per_hour",
                                  p.get("growth_per_hour", 0.012))
        growth = max(0.0, rate * sun * m * b * (1.0 - b / k) * hours)
        growth = min(growth, max(0.0, k - b))
        demand = 0.0
        if grazers:
            for g in grazers.values():
                if g.get("patch_id") == p["id"] and g.get("active"):
                    demand += _nonnegative_value(
                        f"grazer {g.get('patch_id')!r} rate_per_second",
                        g.get("rate_per_second", 0.0)) * dt_s
        eaten = min(b + growth, demand)
        p["biomass"] = b + growth - eaten
        tot_growth += growth
        tot_eaten += eaten
    return out, {"growth": tot_growth, "consumed": tot_eaten,
                 "units": "dimensionless_index (not kg)"}


def _finite_value(name: str, value) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, not boolean")
    try:
        value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def _nonnegative_value(name: str, value) -> float:
    value = _finite_value(name, value)
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def propose_plantings(guild: str, center_xz: tuple, radius_m: float,
                      count: int, seed: int, start_index: int = 0,
                      habitat_id: str = "forest_edge",
                      exclusion_test=None) -> list:
    """Deterministic proposal grid+jitter with per-guild min separation. Separation is best-effort here; prefer propose_plantings_reviewed() for enforced output. Preserves stable ids verbatim."""
    accepted, _ = propose_plantings_reviewed(
        guild, center_xz, radius_m, count, seed, habitat_id=habitat_id,
        exclusion_test=exclusion_test, terrain_fn=None, moisture=0.5,
        canopy=0.5, suitability_threshold=0.0)
    seen = {r["stable_id"] for r in accepted}
    legacy_prefix = f"prop_{guild}_{start_index:05d}"
    collisions = any(r["stable_id"].startswith(legacy_prefix) for r in accepted)
    if collisions:
        for i, rec in enumerate(accepted):
            rec["stable_id"] = f"prop_{guild}_{start_index + i:05d}"
    return accepted


def load_terrain(path: str) -> np.ndarray:
    """Little-endian float32 GRID×GRID, row zero north (matches height_field)."""
    h = np.fromfile(path, dtype="<f4")
    if h.size != GRID * GRID:
        raise ValueError(f"terrain size {h.size}, expected {GRID * GRID}")
    if not np.isfinite(h).all():
        raise ValueError("terrain contains NaN or infinite values")
    return h.reshape(GRID, GRID)


def terrain_fns(h: np.ndarray):
    """(sample, slope_deg) closures matching height_field.gd diagonal + normal_at.

    Both closures clamp their grid coordinates, so a query outside the DEM
    reads the nearest edge cell: sample clamps to [0, GRID-1) for its
    diagonal interpolation, slope_deg to [1, GRID-3] for its central
    difference. The h array must be (GRID, GRID) and finite.
    """
    h = np.asarray(h)
    if h.shape != (GRID, GRID):
        raise ValueError(f"terrain shape {h.shape}, expected {(GRID, GRID)}")
    if not np.isfinite(h).all():
        raise ValueError("terrain contains NaN or infinite values")

    def sample(x: float, z: float) -> float:
        gx = min(max((x + HALF) / STEP, 0.0), float(GRID - 1) - 1e-5)
        gz = min(max((z + HALF) / STEP, 0.0), float(GRID - 1) - 1e-5)
        ix, iz = math.floor(gx), math.floor(gz)
        fx, fz = gx - ix, gz - iz
        a, b = h[iz, ix], h[iz, ix + 1]
        c, d = h[iz + 1, ix], h[iz + 1, ix + 1]
        if fx + fz <= 1.0:
            return float(a + fx * (b - a) + fz * (c - a))
        return float(d + (1.0 - fx) * (c - d) + (1.0 - fz) * (b - d))

    def slope_deg(x: float, z: float) -> float:
        ix = min(max(math.floor((x + HALF) / STEP), 1), GRID - 3)
        iz = min(max(math.floor((z + HALF) / STEP), 1), GRID - 3)
        dhdx = (float(h[iz, ix + 1]) - float(h[iz, ix - 1])) / (2 * STEP)
        dhdz = (float(h[iz + 1, ix]) - float(h[iz - 1, ix])) / (2 * STEP)
        return math.degrees(math.atan(math.hypot(dhdx, dhdz)))
    return sample, slope_deg


def habitat_moisture_at(x: float, z: float, patches: list,
                        default_habitat: str = "unsuitable_matrix",
                        default_moisture: float = 0.2) -> tuple:
    """Nearest patch covering (x, z) -> (habitat, moisture).

    Selection is by center distance, so overlapping patches resolve the
    same way regardless of their order in the list. Proposal generation
    and rendering both read patches through this helper.
    """
    best = None
    for p in patches:
        cx, cz = p.get("center_xz", [None, None])
        if cx is None:
            continue
        dist = math.hypot(x - float(cx), z - float(cz))
        if dist <= float(p.get("radius_m", 0.0)) and (best is None
                                                     or dist < best[0]):
            best = (dist, p)
    if best is None:
        return default_habitat, default_moisture
    patch = best[1]
    return (str(patch.get("habitat", default_habitat)),
            float(patch.get("moisture", default_moisture)))


def moisture_at(x: float, z: float, patches: list,
                default: float = 0.3) -> float:
    return habitat_moisture_at(x, z, patches, "unsuitable_matrix",
                               default)[1]


def propose_plantings_reviewed(guild: str, center_xz: tuple, radius_m: float,
                               count: int, seed: int,
                               habitat_id: str = "forest_edge",
                               exclusion_test=None, terrain_fn=None,
                               patches: list | None = None,
                               moisture: float = 0.5, canopy: float = 0.5,
                               suitability_threshold: float = 0.12
                               ) -> tuple[list, list]:
    """Suitability-linked, separation-enforced proposals + review ledger.

    Per-candidate randomness (seed:guild:cell) is independent: a rejection
    consumes nothing shared, so later candidates never shift. Returns
    (accepted_records, review_log[{stable_id|cell, decision, reason}]).

    DoS guard: candidate grids larger than GRID_BUDGET cells are coarsened
    (wider spacing, guild separation still enforced) and the coarsening is
    logged; grids at/below the cap scan exactly as before.
    """
    if guild not in GUILDS:
        raise ValueError(f"unknown guild {guild!r}; have {list(GUILDS)}")
    # Geometry/input validation.
    radius_m = float(radius_m)
    if not math.isfinite(radius_m) or radius_m <= 0 or radius_m > 500:
        raise ValueError("radius_m must be positive and <= 500")
    center = tuple(center_xz)
    if len(center) < 2 or not all(math.isfinite(float(v)) for v in center[:2]):
        raise ValueError("center_xz must be [x, z] with finite coordinates")
    seed = int(seed)
    if seed < 0 or seed > 99999:
        raise ValueError("seed must be nonnegative and reasonable")
    suitability_threshold = float(suitability_threshold)
    if not (0.0 <= suitability_threshold <= 1.0):
        raise ValueError("suitability_threshold must be in [0, 1]")
    canopy = float(canopy)
    if not (0.0 <= canopy <= 1.0):
        raise ValueError("canopy must be in [0, 1]")
    moisture = float(moisture)
    if not (0.0 <= moisture <= 1.0):
        raise ValueError("moisture must be in [0, 1]")
    for _name, _val in (("suitability_threshold", suitability_threshold),
                        ("canopy", canopy)):
        if isinstance(_val, bool):
            raise ValueError(f"{_name} must be a number, not boolean")
        try:
            _f = float(_val)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{_name} must be a number ({exc})") from exc
        if not math.isfinite(_f):
            raise ValueError(f"{_name} must be finite")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        raise ValueError("count must be a positive integer")
    g = GUILDS[guild]
    sample, slope = terrain_fn if terrain_fn else (None, None)
    step = g["min_sep_m"]
    grid_step = step
    per_row = max(1, math.ceil((2 * radius_m) / grid_step))
    while (per_row + 1) ** 2 > GRID_BUDGET:
        grid_step *= 2.0
        per_row = max(1, math.ceil((2 * radius_m) / grid_step))
    accepted, log, kept_cells = [], [], []
    if grid_step != step:
        log.append({"cell": "*", "decision": "coarsened",
                    "reason": f"grid coarsened to {(per_row + 1) ** 2} "
                              f"candidates (spacing {grid_step:.1f} m, "
                              f"cap {GRID_BUDGET})",
                    "original_spacing_m": step,
                    "effective_spacing_m": grid_step,
                    "original_candidate_count": (per_row + 1) ** 2})

    def cell_ok(x, z) -> bool:
        for kx, kz in kept_cells:
            if math.hypot(x - kx, z - kz) < step:
                return False
        return True

    for row in range(per_row + 1):
        for col in range(per_row + 1):
            rng = random.Random(f"{seed}:{guild}:{col}:{row}")
            x = center_xz[0] - radius_m + col * grid_step + (rng.random() - 0.5) * grid_step * 0.6
            z = center_xz[1] - radius_m + row * grid_step + (rng.random() - 0.5) * grid_step * 0.6
            cell = f"{col}:{row}"
            if math.hypot(x - center_xz[0], z - center_xz[1]) > radius_m:
                log.append({"cell": cell, "decision": "reject",
                            "reason": "outside review radius"})
                continue
            if exclusion_test is not None and exclusion_test(x, z):
                log.append({"cell": cell, "decision": "reject",
                            "reason": "thermal/water exclusion"})
                continue
            sl = slope(x, z) if slope else 0.0
            mo = (moisture_at(x, z, patches) if patches is not None else moisture)
            suit = guild_suitability(guild, habitat_id, sl, mo, canopy,
                                     in_exclusion=False)
            if suit < suitability_threshold:
                log.append({"cell": cell, "decision": "reject", "reason":
                            f"suitability {suit:.3f} < {suitability_threshold}"})
                continue
            if not cell_ok(x, z):
                log.append({"cell": cell, "decision": "reject",
                            "reason": f"separation < {step} m"})
                continue
            y = sample(x, z) if sample else 0.0
            rec = {
                "stable_id": f"prop_{guild}_{seed}_{col:03d}_{row:03d}",
                "guild": guild, "habitat": habitat_id,
                "x": round(x, 3), "y": round(y, 3), "z": round(z, 3),
                "slope_deg": round(sl, 1), "suitability": round(suit, 3),
                "yaw": round(rng.random() * 2 * math.pi, 3),
                "scale": round(0.8 + rng.random() * 0.4, 3),
                "variation_key": rng.randint(0, 2),
                "evidence_class": "habitat-based authored candidate",
                "author_note": (f"M04 reviewed proposal; suitability {suit:.2f}; "
                                f"review against NAIP + habitat {habitat_id}; seed {seed}"),
            }
            accepted.append(rec)
            kept_cells.append((x, z))
            log.append({"cell": cell, "decision": "accept",
                        "stable_id": rec["stable_id"]})
            if len(accepted) >= count:
                break
    return accepted[:count], log


def render_suitability_png(guild: str, size: int, path: str, *,
                           bbox: tuple, terrain_fn, patches: list,
                           shells: list, canopy: float = 0.6) -> str:
    """Suitability field rendered FROM the model: DEM slope + patch moisture +
    apron exclusion + habitat eligibility, evaluated per pixel. bbox =
    (x0, z0, x1, z1) local metres."""
    from PIL import Image
    from .pool_crust import in_apron
    if guild not in GUILDS:
        raise ValueError(f"unknown guild {guild!r}; have {list(GUILDS)}")
    size = int(size)
    if size < 2:
        raise ValueError(f"suitability image size must be >= 2, got {size}")
    canopy = _finite_value("canopy", canopy)
    if not 0.0 <= canopy <= 1.0:
        raise ValueError("canopy must be in [0, 1]")
    try:
        x0, z0, x1, z1 = (float(v) for v in bbox)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"bbox must hold four numbers, got {bbox!r}") from exc
    if not all(math.isfinite(v) for v in (x0, z0, x1, z1)):
        raise ValueError("bbox coordinates must be finite")
    if not (x1 > x0 and z1 > z0):
        raise ValueError(f"bbox needs x1>x0 and z1>z0, got {bbox!r}")
    _, slope = terrain_fn
    img = Image.new("L", (size, size), 0)
    px = img.load()
    for iz in range(size):
        z = z0 + (z1 - z0) * iz / max(1, size - 1)
        for ix in range(size):
            x = x0 + (x1 - x0) * ix / max(1, size - 1)
            excl = any(in_apron(x, z, s) for s in shells)
            hab, mo = habitat_moisture_at(x, z, patches)
            v = guild_suitability(guild, hab, slope(x, z), mo, canopy,
                                  in_exclusion=excl)
            px[ix, iz] = int(min(1.0, max(0.0, v)) * 255)
    parent = Path(path).expanduser().parent
    if str(parent):
        parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path
