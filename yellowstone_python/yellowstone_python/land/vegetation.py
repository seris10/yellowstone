"""vegetation: suitability fields, patch biomass, planting proposals.
Proposals are stable records; thermal/water exclusions via aprons."""
from __future__ import annotations

from yellowstone_python.common.checks import finite as _finite_value, nonnegative as _nonnegative_value

import copy
import math
import random
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np  # typing only; terrain helpers import numpy lazily.


def _require_numpy():
    """Return the imported numpy module, with a stated error when missing."""
    try:
        import numpy as _np
    except ImportError as exc:
        raise ImportError(
            "numpy is required for terrain and raster helpers "
            "(load_terrain, terrain_fns, render_suitability_png)"
        ) from exc
    return _np


GRID = 1025
STEP = 4.0
HALF = 2048.0

# Candidate-cell cap for propose_plantings_reviewed; larger grids are coarsened.
GRID_BUDGET = 25000

# Per-guild coefficients, authored.
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

# Coefficients are authored.
VEGETATION_PROVENANCE = {
    "status": "authored_illustrative_coefficients_not_inferred_from_field_data",
    "real_data_gap": ("Guild parameters (lambda0, slope_max, min_sep, needs, excluded) "
                      "are authored scenario values. Real integration requires field surveys "
                      "or remote-sensing-derived suitability from actual vegetation maps."),
    "coefficients": {k: v for k, v in GUILDS.items()},
}


def _reject_nonfinite(name: str, value) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not boolean")
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(out):
        raise ValueError(f"{name} must be finite")
    return out


def suitability(lambda0: float = 0.9, m_habitat: float = 1.0,
                factors: dict = None,
                m_exclusion: float = 1.0) -> float:
    """lambda_s(p): all terms in [0,1]; returns [0,1] density potential."""
    lambda0 = _reject_nonfinite("lambda0", lambda0)
    lambda0 = min(1.0, max(0.0, lambda0))
    f = 1.0
    for v in (factors or {}).values():
        f *= min(1.0, max(0.0, _reject_nonfinite("factor", v)))
    m_hab = min(1.0, max(0.0, _reject_nonfinite("m_habitat", m_habitat)))
    m_exc = min(1.0, max(0.0, _reject_nonfinite("m_exclusion", m_exclusion)))
    return float(lambda0 * m_hab * f * m_exc)


def guild_suitability(guild: str, habitat_id: str, slope_deg: float,
                      moisture: float, canopy: float = 0.5,
                      in_exclusion: bool = False) -> float:
    """Convenience evaluator used by proposal review + tests."""
    moisture = _reject_nonfinite("moisture", moisture)
    canopy = _reject_nonfinite("canopy", canopy)
    if not 0.0 <= moisture <= 1.0:
        raise ValueError(f"moisture must be in [0, 1], got {moisture}")
    if not 0.0 <= canopy <= 1.0:
        raise ValueError(f"canopy must be in [0, 1], got {canopy}")
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


# Authored nitrogen promotion slope on patch growth; direction supported by cited work.
NITROGEN_GROWTH_ALPHA = 0.02
# Authored nitrogen mineralization time scale.
NITROGEN_DECAY_TAU_S = 90.0 * 86400.0
# Authored trampling recovery time scale.
TRAMPLING_RECOVERY_TAU_S = 60.0 * 86400.0
# Authored sinter deposition rate within the NPS Cistern Spring range.
SINTER_DEPOSITION_MM_PER_S = 1.0 / 86400.0 / 365.0  # 1 mm/yr
# Authored thinning depth per unit trampling fraction in a thermal patch.
SINTER_THINNING_MM_PER_UNIT = 2.0
NUTRIENT_SOURCE = (
    "Authored within cited ranges. Frank and McNaughton 1993 Oecologia 96, "
    "157-161 doi:10.1007/BF00317727 (promotion of grassland production by "
    "grazers); Frank, Inouye, Huntly, Minshall, Anderson 1994 "
    "Biogeochemistry 26, 163-188 doi:10.1007/BF02182072 (N flow 8.1 to "
    "45.6 kg/ha/yr, mean 27.0, in Yellowstone grazed range).")
TRAMPLING_SOURCE = (
    "Authored. Direction and order of magnitude supported by the "
    "ecosystem-management ungulate literature; specific tau values are "
    "authored. Weisberg, Hobbs, Ellis, Coughenour 2002 J. Env. Manage. "
    "65, 181-197 doi:10.1006/jema.2002.0552.")
SINTER_SOURCE = (
    "Authored within NPS Yellowstone Cistern Spring observation of up to "
    "12 mm/yr sinter deposition versus 12 to 25 mm/century at typical "
    "features (NPS visitor material). Thinning magnitude per unit "
    "trampling fraction is authored.")


def patch_step(patches: list, hour: float, dt_s: float,
               grazers: dict | None = None,
               nutrient_return_by_patch: dict | None = None,
               trampling_by_patch: dict | None = None,
               thermal_patch_ids: set | None = None) -> tuple[list, dict]:
    """Advance patch biomass (growth and grazing).
Returns (updated_patches, ledger{growth, consumed, consumed_by_patch})."""
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
    # Pre-aggregate grazing demand per patch; unknown patch_id raises before growth.
    demand_by_patch: dict = {}
    if grazers:
        for gid, g in grazers.items():
            if not g.get("active"):
                continue
            pid = g.get("patch_id")
            if pid not in seen_ids:
                raise ValueError(
                    f"grazer {gid!r} targets unknown patch_id {pid!r}")
            rate = _nonnegative_value(
                f"grazer {gid!r} rate_per_second",
                g.get("rate_per_second", 0.0))
            demand_by_patch[pid] = demand_by_patch.get(pid, 0.0) + rate * dt_s
    sun = sunlight(hour)
    hours = dt_s / 3600.0
    tot_growth = tot_eaten = 0.0
    consumed_by_patch: dict = {}
    nitrogen_added_total = 0.0
    trampling_added_total = 0.0
    sinter_thin_total_mm = 0.0
    sinter_deposit_total_mm = 0.0
    thermal_ids = set(thermal_patch_ids or ())
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
        # Nitrogen stock decays and accepts new return; promotes growth linearly.
        nitrogen_prior = _nonnegative_value(
            f"patch {p.get('id')!r} nitrogen_kg_ha",
            p.get("nitrogen_kg_ha", 0.0))
        decay = math.exp(-dt_s / NITROGEN_DECAY_TAU_S)
        nitrogen_new = 0.0
        if nutrient_return_by_patch is not None:
            raw_n = nutrient_return_by_patch.get(p["id"], 0.0)
            nitrogen_new = _nonnegative_value(
                f"nutrient_return_by_patch[{p['id']!r}]", raw_n)
        nitrogen_stock = nitrogen_prior * decay + nitrogen_new
        growth_boost = 1.0 + NITROGEN_GROWTH_ALPHA * nitrogen_stock
        growth = max(0.0, rate * growth_boost * sun * m * b * (1.0 - b / k) * hours)
        growth = min(growth, max(0.0, k - b))
        # Trampling damage decays over its recovery scale; new fraction removes biomass.
        trampling_prior = _nonnegative_value(
            f"patch {p.get('id')!r} trampling_damage",
            p.get("trampling_damage", 0.0))
        if trampling_prior > 1.0:
            raise ValueError(
                f"patch {p.get('id')!r} trampling_damage must be in [0, 1]")
        trampling_decay = math.exp(-dt_s / TRAMPLING_RECOVERY_TAU_S)
        trampling_new = 0.0
        if trampling_by_patch is not None:
            raw_t = trampling_by_patch.get(p["id"], 0.0)
            trampling_new = _nonnegative_value(
                f"trampling_by_patch[{p['id']!r}]", raw_t)
            if trampling_new > 1.0:
                raise ValueError(
                    f"trampling_by_patch[{p['id']!r}] must be in [0, 1]")
        trampling_damage = min(1.0, trampling_prior * trampling_decay
                               + trampling_new)
        trample_loss = min(b + growth, (b + growth) * trampling_new)
        demand = demand_by_patch.get(p["id"], 0.0)
        eaten = min(b + growth - trample_loss, demand)
        p["biomass"] = max(0.0, b + growth - eaten - trample_loss)
        p["nitrogen_kg_ha"] = round(nitrogen_stock, 4)
        p["trampling_damage"] = round(trampling_damage, 4)
        # Sinter crust state: loss from trampling in thermal patches, recovery from deposition.
        is_thermal = p["id"] in thermal_ids
        sinter_prior = _nonnegative_value(
            f"patch {p.get('id')!r} sinter_crust_mm",
            p.get("sinter_crust_mm", 0.0))
        thin_mm = 0.0
        deposit_mm = 0.0
        if is_thermal:
            thin_mm = SINTER_THINNING_MM_PER_UNIT * trampling_new
            deposit_mm = SINTER_DEPOSITION_MM_PER_S * dt_s
            new_sinter = max(0.0, sinter_prior + deposit_mm - thin_mm)
            p["sinter_crust_mm"] = round(new_sinter, 4)
        else:
            p["sinter_crust_mm"] = round(sinter_prior, 4)
        tot_growth += growth
        tot_eaten += eaten
        nitrogen_added_total += nitrogen_new
        trampling_added_total += trampling_new
        sinter_thin_total_mm += thin_mm
        sinter_deposit_total_mm += deposit_mm
        if eaten > 0.0:
            consumed_by_patch[p["id"]] = eaten
    return out, {"growth": tot_growth, "consumed": tot_eaten,
                 "consumed_by_patch": consumed_by_patch,
                 "nitrogen_return_total_kg_ha": nitrogen_added_total,
                 "trampling_added_total": trampling_added_total,
                 "sinter_thin_total_mm": sinter_thin_total_mm,
                 "sinter_deposit_total_mm": sinter_deposit_total_mm,
                 "nitrogen_decay_tau_s": NITROGEN_DECAY_TAU_S,
                 "trampling_recovery_tau_s": TRAMPLING_RECOVERY_TAU_S,
                 "sinter_deposition_mm_per_s": SINTER_DEPOSITION_MM_PER_S,
                 "sinter_thinning_mm_per_unit": SINTER_THINNING_MM_PER_UNIT,
                 "nutrient_source": NUTRIENT_SOURCE,
                 "trampling_source": TRAMPLING_SOURCE,
                 "sinter_source": SINTER_SOURCE,
                 "units": "dimensionless_index (not kg)"}






def propose_plantings(guild: str, center_xz: tuple, radius_m: float,
                      count: int, seed: int, start_index: int = 0,
                      habitat_id: str = "forest_edge",
                      exclusion_test=None) -> list:
    """Deterministic proposal grid plus jitter with per-guild min separation.
Prefer propose_plantings_reviewed for enforced output."""
    del start_index  # used for backward call-site compatibility
    accepted, _ = propose_plantings_reviewed(
        guild, center_xz, radius_m, count, seed, habitat_id=habitat_id,
        exclusion_test=exclusion_test, terrain_fn=None, moisture=0.5,
        canopy=0.5, suitability_threshold=0.0)
    return accepted


def load_terrain(path: str) -> "np.ndarray":
    """Little-endian float32 grid-sized array; row zero is north (matches height_field)."""
    np = _require_numpy()
    h = np.fromfile(path, dtype="<f4")
    if h.size != GRID * GRID:
        raise ValueError(f"terrain size {h.size}, expected {GRID * GRID}")
    if not np.isfinite(h).all():
        raise ValueError("terrain contains NaN or infinite values")
    return h.reshape(GRID, GRID)


def terrain_fns(h: "np.ndarray"):
    """(sample, slope_deg) closures matching height_field.gd diagonal and normal_at.
Grid coordinates clamp to the nearest edge; h must be the full grid and finite."""
    np = _require_numpy()
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
    """Nearest patch covering (x, z) returns (habitat, moisture).
Selection by center distance; order independent."""
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
                               suitability_threshold: float = 0.12,
                               constraints=None
                               ) -> tuple[list, list]:
    """Suitability-linked, separation-enforced proposals with a review ledger.
Returns (accepted_records, review_log). Grids above GRID_BUDGET are coarsened and logged."""
    if constraints is not None and not callable(getattr(constraints,
                                                        "excluded", None)):
        raise TypeError(
            "constraints must expose an excluded(x, z) -> bool method")
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
            if constraints is not None and constraints.excluded(x, z):
                log.append({"cell": cell, "decision": "reject",
                            "reason": "placement_constraints_exclusion"})
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
                "author_note": (f"reviewed proposal; suitability {suit:.2f}; "
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
    """Suitability field evaluated per pixel from DEM slope, patch moisture, aprons, and habitat.
bbox is (x0, z0, x1, z1) in meters."""
    from PIL import Image
    from yellowstone_python.thermal_features.pool_crust import in_apron
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
