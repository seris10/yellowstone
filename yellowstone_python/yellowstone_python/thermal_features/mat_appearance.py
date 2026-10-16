"""Render-side appearance of the mat model on the thermal core."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic

import json
import os

import numpy as np

from yellowstone_python.thermal_features.microbial_mats import CAROTENOID_ENDPOINT_RGB, CLASS_ID_BY_NAME, CLASS_SINTER_DRY, CLASS_WATER_HOT_CLEAR, COMMUNITY_LEGEND, MatState, photosynthesis_limit_c

SCHEMA_MAT_APPEARANCE = "yellowstone.mat_appearance.v1"
APPEARANCE_STATUS = "fitted_from_imagery"

# Output pixels per 1 m core cell (0.5 m pigment png).
UPSAMPLE = 2
# Mat palette: Lab k-means cluster centers of apron satellite imagery, sRGB 0-255.
PALETTE_RGB = {
    "orange": (201, 113, 68),
    "light_orange": (221, 153, 105),
    "rust": (140, 98, 82),
    "dark": (98, 62, 50),
    "thin": (182, 139, 122),
    "pale": (230, 194, 148),
}
PALETTE_SOURCE = ("tools/fit_mat_palette.py k=6 over two Google satellite "
                  "screenshots of the Grand Prismatic apron (Airbus, Maxar), "
                  "shared by KJR 2026-10-13")
# Flow-fraction decades mapped onto flow intensity 0 to 1; authored.
FLOW_LOG10_MIN = -9.0
FLOW_LOG10_MAX = -1.0
# Imagery mat strength: warm-chroma margin over the sinter median, vegetation and shadow cutoffs; authored.
WARM_MARGIN = 2.0
WARM_TOP_PERCENTILE = 97.0
SINTER_MIN_L = 75.0
VEGETATION_MAX_A = -4.0
SHADOW_MAX_L = 35.0
# Mineral habitat threshold and model-presence dilation for the imagery region; authored.
MINERAL_MIN = 0.3
PRESENCE_DILATION_M = 6.0
# Hot-rim pale blend window in C, bracketing the Nugent orange to yellow-green edge.
PALE_BLEND_C = (60.0, 72.0)
# Streamline half-length in output pixels, streak contrast, edge softening and luminance window; authored.
STREAMLINE_STEPS = 8
STREAK_CONTRAST = 0.25
EDGE_SIGMA_M = 0.75
LUMINANCE_WINDOW_M = 6.0
# DEM smoothing before taking the downslope direction, in meters; authored.
DEM_SMOOTH_SIGMA_M = 2.0

_SRGB_TO_XYZ = np.array([[0.4124564, 0.3575761, 0.1804375],
                         [0.2126729, 0.7151522, 0.0721750],
                         [0.0193339, 0.1191920, 0.9503041]])
_D65_WHITE = np.array([0.95047, 1.0, 1.08883])


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Lab (D65 white) from sRGB in [0, 1]; last axis is the channel."""
    c = np.clip(np.asarray(rgb, dtype=np.float64), 0.0, 1.0)
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = (lin @ _SRGB_TO_XYZ.T) / _D65_WHITE
    eps = 216.0 / 24389.0
    kappa = 24389.0 / 27.0
    f = np.where(xyz > eps, np.cbrt(xyz), (kappa * xyz + 16.0) / 116.0)
    lab = np.empty(xyz.shape)
    lab[..., 0] = 116.0 * f[..., 1] - 16.0
    lab[..., 1] = 500.0 * (f[..., 0] - f[..., 1])
    lab[..., 2] = 200.0 * (f[..., 1] - f[..., 2])
    return lab


def flow_intensity(flow_fraction: np.ndarray) -> np.ndarray:
    """Routed flow fraction as a log-scaled intensity in [0, 1]."""
    ff = np.asarray(flow_fraction, dtype=np.float64)
    safe = np.where(np.isfinite(ff) & (ff > 0.0), ff, 1.0e-30)
    x = (np.log10(safe) - FLOW_LOG10_MIN) / (FLOW_LOG10_MAX - FLOW_LOG10_MIN)
    return np.clip(x, 0.0, 1.0)


def model_ramp_rgb(temperature_c: np.ndarray) -> np.ndarray:
    """Continuous legend color through the Nugent class temperature centers."""
    knots = sorted((e["temperature_c_center"], e["rgb"]) for e in COMMUNITY_LEGEND
                   if "temperature_c_center" in e)
    tk = np.array([k[0] for k in knots])
    ck = np.array([k[1] for k in knots], dtype=np.float64) / 255.0
    t = np.nan_to_num(np.asarray(temperature_c, dtype=np.float64), nan=tk[0])
    return np.stack([np.interp(t, tk, ck[:, i]) for i in range(3)], axis=-1)


def pigment_shift(rgb: np.ndarray, pigment: np.ndarray | float) -> np.ndarray:
    """Shift toward the carotenoid endpoint by pigment index (microbial_mats rule)."""
    p = np.clip(np.asarray(pigment, dtype=np.float64), 0.0, 1.0)[..., None]
    end = np.asarray(CAROTENOID_ENDPOINT_RGB)
    return rgb + (end - rgb) * p


def _smoothstep(lo: float, hi: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((np.asarray(x, dtype=np.float64) - lo) / (hi - lo), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def imagery_mat_strength(photo_rgb: np.ndarray,
                         region: np.ndarray) -> tuple[np.ndarray, dict]:
    """Continuous mat strength in [0, 1] from warm chroma above the sinter median.
Vegetation, shadow and pixels outside region read 0."""
    lab = srgb_to_lab(photo_rgb)
    lum, a, b = lab[..., 0], lab[..., 1], lab[..., 2]
    warm = 0.6 * b + 0.4 * a
    sinter = region & (lum > SINTER_MIN_L)
    pool = sinter if sinter.any() else region
    base = float(np.median(warm[pool])) if pool.any() else 0.0
    top = (float(np.percentile(warm[region], WARM_TOP_PERCENTILE))
           if region.any() else base + 1.0)
    span = max(top - base - WARM_MARGIN, 1.0)
    m = np.clip((warm - base - WARM_MARGIN) / span, 0.0, 1.0)
    m[(a < VEGETATION_MAX_A) | (lum < SHADOW_MAX_L) | ~region] = 0.0
    return _smoothstep(0.0, 1.0, m), {"sinter_warm_median": base,
                                      "warm_top": top}


def downslope_direction(dem: np.ndarray, cell_m: float = 1.0) -> np.ndarray:
    """Unit downslope direction (row, col) per cell from a smoothed DEM."""
    from scipy.ndimage import gaussian_filter
    h = gaussian_filter(np.asarray(dem, dtype=np.float64),
                        DEM_SMOOTH_SIGMA_M / cell_m)
    g_row, g_col = np.gradient(h, cell_m)
    mag = np.hypot(g_row, g_col)
    safe = np.where(mag > 1.0e-6, mag, 1.0)
    d = np.stack([-g_row / safe, -g_col / safe])
    d[:, mag <= 1.0e-6] = 0.0
    return d


def streamline_average(fields: np.ndarray, direction: np.ndarray,
                       rows: np.ndarray, cols: np.ndarray,
                       steps: int = STREAMLINE_STEPS,
                       step_px: float = 1.0) -> np.ndarray:
    """Mean of each field along the streamline through each point, both directions.
fields is (k, H, W); direction is (2, H, W) in (row, col) units."""
    from scipy.ndimage import map_coordinates

    def sample(arr, r, c):
        return map_coordinates(arr, [r, c], order=1, mode="nearest")

    k = fields.shape[0]
    r0 = rows.astype(np.float64)
    c0 = cols.astype(np.float64)
    acc = np.stack([sample(fields[i], r0, c0) for i in range(k)])
    count = 1
    for sign in (1.0, -1.0):
        r, c = r0.copy(), c0.copy()
        for _ in range(int(steps)):
            dr = sample(direction[0], r, c)
            dc = sample(direction[1], r, c)
            r = r + sign * dr * step_px
            c = c + sign * dc * step_px
            for i in range(k):
                acc[i] += sample(fields[i], r, c)
            count += 1
    return acc / count


def _palette(name: str) -> np.ndarray:
    return np.asarray(PALETTE_RGB[name], dtype=np.float64) / 255.0


def _mix(a: np.ndarray, b: np.ndarray, t: np.ndarray) -> np.ndarray:
    return a + (b - a) * np.asarray(t)[..., None]


def render_mat_appearance(state: MatState, temperature_c: np.ndarray,
                          flow_fraction: np.ndarray, dem: np.ndarray,
                          photo_rgb: np.ndarray, mineral: np.ndarray, *,
                          pigment_ref: float = 1.0, ph: float = 8.0,
                          seed: int = 0) -> tuple[np.ndarray, dict]:
    """Four-channel uint8 appearance at two pixels per cell edge, with metadata.
photo_rgb (sRGB 0 to 1) and mineral (0 to 1) are on the output grid."""
    from scipy.ndimage import binary_dilation, gaussian_filter, zoom
    classes = np.asarray(state.community_class)
    up = UPSAMPLE
    out_shape = (classes.shape[0] * up, classes.shape[1] * up)
    photo = np.asarray(photo_rgb, dtype=np.float64)
    if photo.shape[:2] != out_shape or np.shape(mineral) != out_shape:
        raise ValueError(f"photo_rgb and mineral must be {out_shape}")
    no_mat = [CLASS_ID_BY_NAME[CLASS_SINTER_DRY],
              CLASS_ID_BY_NAME[CLASS_WATER_HOT_CLEAR]]
    mat_cells = (classes >= 0) & ~np.isin(classes, no_mat)
    t = np.asarray(temperature_c, dtype=np.float64)
    t_floor = float(np.nanmin(t)) if np.isfinite(t).any() else 0.0
    t_filled = np.nan_to_num(t, nan=t_floor)
    photosynthetic = t_filled <= photosynthesis_limit_c(ph)
    ramp = model_ramp_rgb(t_filled)
    pig = np.where(photosynthetic, np.asarray(state.pigment_index), 0.0)
    # Model pigment departure from the imagery date's pigment state.
    delta = pigment_shift(ramp, pig) - pigment_shift(
        ramp, np.where(photosynthetic, pigment_ref, 0.0))

    sigma_px = EDGE_SIGMA_M * up
    presence = np.clip(gaussian_filter(
        zoom(mat_cells.astype(np.float64), up, order=1), sigma_px), 0.0, 1.0)
    dilated = binary_dilation(presence > 0.05,
                              iterations=int(PRESENCE_DILATION_M * up))
    region = dilated | (np.asarray(mineral) >= MINERAL_MIN)
    m, m_meta = imagery_mat_strength(photo, region)
    m = gaussian_filter(m, 0.5 * sigma_px)
    lab_photo = srgb_to_lab(photo)
    lum = lab_photo[..., 0]
    lum_rel = np.clip(lum / np.maximum(
        gaussian_filter(lum, LUMINANCE_WINDOW_M * up), 1.0), 0.6, 1.4)
    fi = np.clip(zoom(flow_intensity(flow_fraction), up, order=1), 0.0, 1.0)
    t_up = zoom(t_filled, up, order=1)
    delta_up = np.stack([zoom(delta[..., i], up, order=1) for i in range(3)],
                        axis=-1)

    active = _smoothstep(0.15, 0.85, fi) * presence
    shape3 = out_shape + (3,)
    color = _mix(np.broadcast_to(_palette("rust"), shape3),
                 _palette("orange"), active)
    color = _mix(color, _palette("light_orange"),
                 np.clip((lum_rel - 1.0) * 2.0, 0.0, 1.0) * active)
    color = _mix(np.broadcast_to(_palette("thin"), shape3),
                 color, _smoothstep(0.05, 0.45, np.maximum(m, 0.6 * presence)))
    color = _mix(color, _palette("dark"),
                 np.clip((0.9 - lum_rel) * 2.5, 0.0, 0.7))
    color = _mix(color, _palette("pale"),
                 _smoothstep(*PALE_BLEND_C, t_up) * presence)
    color = np.clip((color + delta_up)
                    * np.clip(lum_rel, 0.8, 1.15)[..., None], 0.0, 1.0)
    alpha = np.clip(m * (0.7 + 0.3 * presence)
                    + 0.45 * presence * (0.4 + 0.6 * active), 0.0, 0.95)
    # Open water, shadow and vegetation in the imagery carry no mat.
    alpha[(lab_photo[..., 0] < SHADOW_MAX_L)
          | (lab_photo[..., 1] < VEGETATION_MAX_A)] = 0.0

    rng = np.random.default_rng(seed)
    noise = gaussian_filter(rng.random(out_shape), 0.7)
    direction = zoom(downslope_direction(dem), (1, up, up), order=1)
    norm = np.hypot(direction[0], direction[1])
    direction = np.where(norm > 1.0e-6,
                         direction / np.where(norm > 0.0, norm, 1.0), 0.0)
    rows, cols = np.nonzero(alpha > 0.01)
    fields = np.concatenate([np.moveaxis(color * alpha[..., None], -1, 0),
                             alpha[None], noise[None]])
    avg = streamline_average(fields, direction, rows, cols)
    out_a = np.zeros(out_shape)
    out_rgb = np.zeros(shape3)
    out_a[rows, cols] = avg[3]
    safe_a = np.where(avg[3] > 1.0e-6, avg[3], 1.0)
    streak = avg[4]
    if streak.size:
        z = (streak - streak.mean()) / max(float(streak.std()), 1.0e-9)
        streak = 1.0 + STREAK_CONTRAST * np.clip(z, -2.0, 2.0) / 2.0
    for i in range(3):
        out_rgb[rows, cols, i] = avg[i] / safe_a * streak
    rgba = np.empty(out_shape + (4,), dtype=np.uint8)
    rgba[..., :3] = np.clip(out_rgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.clip(out_a * 255.0 + 0.5, 0, 255).astype(np.uint8)
    meta = {
        "schema": SCHEMA_MAT_APPEARANCE,
        "status": APPEARANCE_STATUS,
        "grid_cells": list(classes.shape),
        "upsample": up,
        "pigment_ref": float(pigment_ref),
        "imagery_mat_strength": m_meta,
        "palette_rgb_0_255": {k: list(v) for k, v in PALETTE_RGB.items()},
        "palette_source": PALETTE_SOURCE,
        "parameters": {
            "flow_log10_range": [FLOW_LOG10_MIN, FLOW_LOG10_MAX],
            "warm_margin": WARM_MARGIN,
            "warm_top_percentile": WARM_TOP_PERCENTILE,
            "mineral_min": MINERAL_MIN,
            "presence_dilation_m": PRESENCE_DILATION_M,
            "pale_blend_c": list(PALE_BLEND_C),
            "streamline_steps": STREAMLINE_STEPS,
            "streak_contrast": STREAK_CONTRAST,
            "edge_sigma_m": EDGE_SIGMA_M,
            "luminance_window_m": LUMINANCE_WINDOW_M,
            "dem_smooth_sigma_m": DEM_SMOOTH_SIGMA_M,
            "status": "authored",
        },
        "note": ("visual layer: mat geometry follows NAIP warm chroma inside "
                 "the mineral and model-mat region; model flow, temperature "
                 "and pigment set the color; model rasters are unchanged"),
    }
    return rgba, meta


def load_photo(path: str, size: int) -> np.ndarray:
    """Imagery resampled bilinearly to a size-square grid, sRGB in [0, 1]."""
    from PIL import Image
    img = Image.open(path).convert("RGB").resize((size, size),
                                                 Image.Resampling.BILINEAR)
    return np.asarray(img, dtype=np.float64) / 255.0


def load_mineral(habitat_mask_path: str, size: int, *, world_half_m: float,
                 core_half_m: float) -> np.ndarray:
    """Mineral channel of the world habitat mask cropped to the core and resampled."""
    from PIL import Image
    img = Image.open(habitat_mask_path).convert("RGB")
    w = img.width
    lo = (world_half_m - core_half_m) / (2.0 * world_half_m) * (w - 1)
    hi = (world_half_m + core_half_m) / (2.0 * world_half_m) * (w - 1)
    crop = img.resize((size, size), Image.Resampling.BILINEAR,
                      box=(lo, lo, hi, hi))
    return np.asarray(crop, dtype=np.float64)[..., 0] / 255.0


def write_mat_appearance_png(state: MatState, temperature_c: np.ndarray,
                             flow_fraction: np.ndarray, dem: np.ndarray,
                             photo_rgb: np.ndarray, mineral: np.ndarray,
                             path: str, *, legend_path: str | None = None,
                             pigment_ref: float = 1.0, ph: float = 8.0,
                             sources: list | None = None) -> dict:
    """Render and write the appearance png plus its metadata json."""
    from PIL import Image
    rgba, meta = render_mat_appearance(state, temperature_c, flow_fraction,
                                       dem, photo_rgb, mineral,
                                       pigment_ref=pigment_ref, ph=ph)
    meta["sources"] = list(sources or [])
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(path)
    if legend_path is not None:
        write_json_atomic(legend_path, meta, indent=2)
    return meta


__all__ = [
    "SCHEMA_MAT_APPEARANCE",
    "PALETTE_RGB",
    "srgb_to_lab",
    "flow_intensity",
    "model_ramp_rgb",
    "pigment_shift",
    "imagery_mat_strength",
    "downslope_direction",
    "streamline_average",
    "render_mat_appearance",
    "load_photo",
    "load_mineral",
    "write_mat_appearance_png",
]
