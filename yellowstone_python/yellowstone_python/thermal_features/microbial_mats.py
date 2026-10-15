"""Microbial mat community and pigment model for thermal springs.
Produces community class, pigment index, reflectance RGB and pool color ramps."""
from __future__ import annotations

from yellowstone_python.common.io import write_json_atomic

from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG

from yellowstone_python.common.checks import finite as _finite

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

SCHEMA_MAT_STATE = "yellowstone.mat_state.v1"
SCHEMA_POOL_RAMP = "yellowstone.pool_radiative_ramp.v1"

CORE_GRID_SIZE = 1280
CORE_CELL_M = 1.0
CORE_HALF_M = 640.0

MAT_PIGMENT_PIXEL_M = 0.5
MAT_PIGMENT_SIZE = 2560

PHOTOSYNTHESIS_LIMIT_NEUTRAL_C = 75.0
PHOTOSYNTHESIS_LIMIT_ACIDIC_C = 56.0
PH_ACIDIC_THRESHOLD = 5.0
PH_NEUTRAL_THRESHOLD = 6.0

CLASS_WHITE = "white_chemolithotroph"
CLASS_PINK = "pink_chemolithotroph"
CLASS_YELLOW = "yellow_cyanobacteria"
CLASS_YELLOW_GREEN = "yellow_green_cyanobacteria_chloroflexus"
CLASS_ORANGE = "orange_cyanobacteria_chromatiaceae"
CLASS_BROWN_GREEN = "brown_green_mixed_photosynthetic"
CLASS_SINTER_DRY = "sinter_dry"
CLASS_WATER_HOT_CLEAR = "water_hot_clear"

COMMUNITY_LEGEND = [
    {"class_id": 0, "name": CLASS_SINTER_DRY,
     "rgb": [184, 168, 138], "status": "authored"},
    {"class_id": 1, "name": CLASS_BROWN_GREEN,
     "rgb": [95, 110, 60], "status": "literature",
     "temperature_c_center": 43.0,
     "temperature_source": "Nugent 2015 Appl. Opt. 54(4) B128 Table 1"},
    {"class_id": 2, "name": CLASS_ORANGE,
     "rgb": [201, 115, 46], "status": "literature",
     "temperature_c_center": 57.0,
     "temperature_source": "Nugent 2015 Appl. Opt. 54(4) B128 Table 1"},
    {"class_id": 3, "name": CLASS_YELLOW_GREEN,
     "rgb": [196, 180, 70], "status": "literature",
     "temperature_c_center": 68.0,
     "temperature_source": "Nugent 2015 Appl. Opt. 54(4) B128 Table 1"},
    {"class_id": 4, "name": CLASS_YELLOW,
     "rgb": [220, 200, 90], "status": "literature",
     "temperature_c_center": 75.0,
     "temperature_source": "Nugent 2015 Appl. Opt. 54(4) B128 Table 1"},
    {"class_id": 5, "name": CLASS_PINK,
     "rgb": [220, 170, 170], "status": "literature",
     "temperature_c_center": 83.0,
     "temperature_source": "Nugent 2015 Appl. Opt. 54(4) B128 Table 1"},
    {"class_id": 6, "name": CLASS_WHITE,
     "rgb": [240, 240, 240], "status": "literature",
     "temperature_c_center": 85.0,
     "temperature_source": "Nugent 2015 Appl. Opt. 54(4) B128 Table 1"},
    {"class_id": 7, "name": CLASS_WATER_HOT_CLEAR,
     "rgb": [40, 110, 160], "status": "authored"},
]
CLASS_ID_BY_NAME = {entry["name"]: entry["class_id"] for entry in COMMUNITY_LEGEND}

# Band edges are authored midpoints between the Nugent Table 1 temperatures.
CLASS_BAND_EDGES_STATUS = "authored_from_table"
CLASS_BAND_EDGES_C: tuple[tuple[float, str], ...] = (
    (50.0, CLASS_BROWN_GREEN),
    (62.0, CLASS_ORANGE),
    (70.0, CLASS_YELLOW_GREEN),
    (80.0, CLASS_YELLOW),
    (84.0, CLASS_PINK),
    (float("inf"), CLASS_WHITE),
)
CLASS_BAND_EDGES_LEGEND = [
    {"upper_t_c": edge, "class": name, "status": CLASS_BAND_EDGES_STATUS}
    for edge, name in CLASS_BAND_EDGES_C[:-1]
] + [{"upper_t_c": None, "class": CLASS_BAND_EDGES_C[-1][1],
      "status": CLASS_BAND_EDGES_STATUS}]

NUGENT_2015_CITATION = (
    "Nugent, Shaw, Vollmer (2015) Appl. Opt. 54(4) B128, Table 1")
BROCK_1978_CITATION = (
    "Brock (1978) Thermophilic Microorganisms and Life at High Temperatures,"
    " Springer, upper photosynthesis limit in acidic springs")
POPE_FRY_1997_CITATION = (
    "Pope and Fry (1997) Appl. Opt. 36(33) 8710 Table 2")
MOREL_1974_CITATION = (
    "Morel (1974) Optical properties of pure water and pure sea water")

POPE_FRY_PURE_WATER_ABSORPTION_M_INV = {
    "r_650nm": 0.340,
    "g_550nm": 0.0565,
    "b_450nm": 0.00922,
    "status": "literature",
    "source": POPE_FRY_1997_CITATION + " Table 2 (380-700 nm)",
}
AUTHORED_SCATTERING_M_INV = {
    "r_650nm": 0.0008,
    "g_550nm": 0.0015,
    "b_450nm": 0.0035,
    "status": "authored",
    "source": "authored three-band total scattering proxy; equal forward and backward hemispheres",
}

AUTHORED_SCATTER_TINT_RGB = (1.0, 1.0, 1.0)
AUTHORED_SURFACE_REFLECTION = 0.02
CLEAR_SKY_IRRADIANCE_RATIO = 0.1

PIGMENT_SATURATION_SW_W_M2 = 350.0
PIGMENT_SATURATION_STATUS = "authored"
PIGMENT_RELAXATION_TAU_DAYS = 7.0
PIGMENT_RELAXATION_TAU_STATUS = "authored"
# Carotenoids rise with irradiance (photoprotection); orange endpoint RGB authored.
CAROTENOID_ENDPOINT_RGB = (0.90, 0.45, 0.15)
CAROTENOID_ENDPOINT_STATUS = "authored"
PHOTOACCLIMATION_CITATION = (
    "Nugent, Shaw, Vollmer (2015) Appl. Opt. 54(4) B128 Section 1,"
    " seasonal color variation driven by water temperature and"
    " UV-visible irradiance")
KASTEN_CZEPLAK_1980_CITATION = (
    "Kasten and Czeplak (1980) Solar Energy 24(2) 177, cloud attenuation"
    " G/G_clear = 1 - 0.75 (N/8)^3.4 with N in oktas")




def photosynthesis_limit_c(ph: float) -> float:
    """Upper temperature of oxygenic photosynthesis for the given pH.
Neutral above pH 6, acidic at or below pH 5, linear between."""
    ph_v = _finite("ph", ph)
    if ph_v >= PH_NEUTRAL_THRESHOLD:
        return PHOTOSYNTHESIS_LIMIT_NEUTRAL_C
    if ph_v <= PH_ACIDIC_THRESHOLD:
        return PHOTOSYNTHESIS_LIMIT_ACIDIC_C
    frac = (ph_v - PH_ACIDIC_THRESHOLD) / (
        PH_NEUTRAL_THRESHOLD - PH_ACIDIC_THRESHOLD)
    return (PHOTOSYNTHESIS_LIMIT_ACIDIC_C
            + frac * (PHOTOSYNTHESIS_LIMIT_NEUTRAL_C
                      - PHOTOSYNTHESIS_LIMIT_ACIDIC_C))


def classify_cell(t_c: float, ph: float = 8.0) -> str:
    """Community class name for one cell."""
    if math.isnan(t_c):
        return CLASS_SINTER_DRY
    t_v = float(t_c)
    photo_limit = photosynthesis_limit_c(ph)
    if t_v > photo_limit:
        if t_v > 84.0:
            return CLASS_WHITE
        if t_v > 80.0:
            return CLASS_PINK
        return CLASS_WATER_HOT_CLEAR
    for edge, name in CLASS_BAND_EDGES_C:
        if t_v <= edge:
            return name
    return CLASS_WHITE


def classify_temperature_field(t_c: np.ndarray,
                               ph: float = 8.0) -> np.ndarray:
    """Vectorized classification; returns int16 class ids with nodata -1."""
    arr = np.asarray(t_c, dtype=np.float64)
    out = np.full(arr.shape, -1, dtype=np.int16)
    photo_limit = photosynthesis_limit_c(ph)
    valid = ~np.isnan(arr)
    valid_vals = arr[valid]
    hot_white = valid_vals > 84.0
    hot_pink = (valid_vals > 80.0) & (valid_vals <= 84.0)
    hot_clear = (valid_vals > photo_limit) & (valid_vals <= 80.0)
    mat_mask = valid_vals <= photo_limit
    classes = np.empty(valid_vals.shape, dtype=np.int16)
    classes[hot_white] = CLASS_ID_BY_NAME[CLASS_WHITE]
    classes[hot_pink] = CLASS_ID_BY_NAME[CLASS_PINK]
    classes[hot_clear] = CLASS_ID_BY_NAME[CLASS_WATER_HOT_CLEAR]
    if mat_mask.any():
        mat_temps = valid_vals[mat_mask]
        edges = np.array([e for e, _ in CLASS_BAND_EDGES_C[:-1]])
        band_names = [n for _, n in CLASS_BAND_EDGES_C]
        band_ids = np.array([CLASS_ID_BY_NAME[n] for n in band_names],
                            dtype=np.int16)
        idx = np.searchsorted(edges, mat_temps, side="left")
        idx = np.clip(idx, 0, len(band_ids) - 1)
        classes[mat_mask] = band_ids[idx]
    out[valid] = classes
    return out


def kasten_czeplak_cloud_attenuation(cloud_fraction: float) -> float:
    """All-sky to clear-sky shortwave ratio from the Kasten and Czeplak relation.
Cloud fraction is a daily mean in [0, 1]; oktas N = 8 * cloud_fraction."""
    c = _finite("cloud_fraction", cloud_fraction)
    if c < 0.0 or c > 1.0:
        raise ValueError("cloud_fraction must be in [0, 1]")
    return 1.0 - 0.75 * c ** 3.4


def daily_mean_insolation_w_m2(
    date_utc: object,
    latitude: float,
    longitude: float,
    daily_cloud_fraction: float,
    *,
    altitude_m: float | None = None,
    hours: int = 24,
) -> dict:
    """Daily mean all-sky shortwave at the site from pvlib clear-sky and cloud.
Returns clear_mean_w_m2, cloud_factor, all_sky_mean_w_m2 and sources."""
    import pandas as pd
    from pvlib import location as pv_location
    cloud = _finite("daily_cloud_fraction", daily_cloud_fraction)
    if cloud < 0.0 or cloud > 1.0:
        raise ValueError("daily_cloud_fraction must be in [0, 1]")
    if isinstance(date_utc, str):
        start = pd.Timestamp(date_utc, tz="UTC").normalize()
    else:
        ts = pd.Timestamp(date_utc)
        start = (ts.tz_localize("UTC") if ts.tzinfo is None
                 else ts.tz_convert("UTC")).normalize()
    times = pd.date_range(start=start, periods=int(hours),
                          freq="1h", tz="UTC")
    site = pv_location.Location(latitude=float(latitude),
                                longitude=float(longitude),
                                altitude=float(altitude_m or 0.0),
                                tz="UTC")
    cs = site.get_clearsky(times, model="ineichen")
    clear_mean = float(cs["ghi"].mean())
    attenuation = kasten_czeplak_cloud_attenuation(cloud)
    all_sky = clear_mean * attenuation
    return {
        "clear_mean_w_m2": clear_mean,
        "cloud_fraction": cloud,
        "cloud_factor": attenuation,
        "all_sky_mean_w_m2": all_sky,
        "latitude_deg": float(latitude),
        "longitude_deg": float(longitude),
        "altitude_m": float(altitude_m or 0.0),
        "sources": [
            "pvlib get_clearsky Ineichen Perez model",
            KASTEN_CZEPLAK_1980_CITATION,
        ],
    }


def instantaneous_shortwave_w_m2(
    epoch_utc_s: float,
    latitude: float,
    longitude: float,
    cloud_fraction: float,
    *,
    altitude_m: float | None = None,
) -> dict:
    """All-sky global horizontal shortwave at one instant.
pvlib Ineichen-Perez clear sky times the Kasten and Czeplak cloud factor."""
    import pandas as pd
    from pvlib import location as pv_location
    epoch = _finite("epoch_utc_s", epoch_utc_s)
    cloud = _finite("cloud_fraction", cloud_fraction)
    if cloud < 0.0 or cloud > 1.0:
        raise ValueError("cloud_fraction must be in [0, 1]")
    times = pd.DatetimeIndex([pd.Timestamp(epoch, unit="s", tz="UTC")])
    site = pv_location.Location(latitude=float(latitude),
                                longitude=float(longitude),
                                altitude=float(altitude_m or 0.0), tz="UTC")
    clear = float(site.get_clearsky(times, model="ineichen")["ghi"].iloc[0])
    attenuation = kasten_czeplak_cloud_attenuation(cloud)
    return {
        "epoch_utc_s": epoch,
        "clear_ghi_w_m2": clear,
        "cloud_fraction": cloud,
        "cloud_factor": attenuation,
        "all_sky_w_m2": clear * attenuation,
        "sources": [
            "pvlib get_clearsky Ineichen Perez model",
            KASTEN_CZEPLAK_1980_CITATION,
        ],
    }


def steady_state_pigment_index(daily_mean_shortwave_w_m2: float) -> float:
    """Steady-state carotenoid-to-chlorophyll index in [0, 1].
Linear in daily mean all-sky shortwave up to the authored saturation."""
    sw = max(0.0, _finite("daily_mean_shortwave_w_m2",
                          daily_mean_shortwave_w_m2))
    return float(min(1.0, sw / PIGMENT_SATURATION_SW_W_M2))


def relax_pigment(previous_index: float,
                  steady_index: float,
                  dt_days: float,
                  tau_days: float = PIGMENT_RELAXATION_TAU_DAYS) -> float:
    """Advance the pigment index by one implicit-Euler step of dP/dt = (P_ss-P)/tau.
Unconditional stability on large steps."""
    tau = _finite("tau_days", tau_days)
    if tau <= 0.0:
        raise ValueError("tau_days must be > 0")
    dt = _finite("dt_days", dt_days)
    if dt < 0.0:
        raise ValueError("dt_days must be >= 0")
    prev = _finite("previous_index", previous_index)
    target = _finite("steady_index", steady_index)
    weight = dt / (dt + tau)
    return prev + weight * (target - prev)


def integrate_pigment(initial_index: float,
                      steady_values: Sequence[float],
                      dt_days: float,
                      tau_days: float = PIGMENT_RELAXATION_TAU_DAYS
                      ) -> list[float]:
    """Integrate the pigment index over a sequence of steady targets."""
    history = [float(initial_index)]
    current = float(initial_index)
    for target in steady_values:
        current = relax_pigment(current, float(target), dt_days,
                                tau_days=tau_days)
        history.append(current)
    return history


def _mat_rgb_for_class(name: str) -> tuple[float, float, float]:
    """Linear-light proxy decoded from the authored sRGB class palette."""
    for entry in COMMUNITY_LEGEND:
        if entry["name"] == name:
            rgb = entry["rgb"]
            return tuple(_srgb_to_linear(c / 255.0) for c in rgb)
    return 0.0, 0.0, 0.0


def apply_pigment_shift(base_rgb: tuple[float, float, float],
                        pigment_index: float
                        ) -> tuple[float, float, float]:
    """Shift a chlorophyll-dominant RGB toward a carotenoid-dominant RGB.

Index 0 keeps the base reflectance; index 1 pushes toward orange-red.
"""
    idx = max(0.0, min(1.0, _finite("pigment_index", pigment_index)))
    carotenoid = (0.90, 0.45, 0.15)
    r = base_rgb[0] + (carotenoid[0] - base_rgb[0]) * idx
    g = base_rgb[1] + (carotenoid[1] - base_rgb[1]) * idx
    b = base_rgb[2] + (carotenoid[2] - base_rgb[2]) * idx
    return r, g, b


def _absorption_rgb() -> tuple[float, float, float]:
    """Pure-water absorption coefficients packed as RGB in m^-1."""
    tbl = POPE_FRY_PURE_WATER_ABSORPTION_M_INV
    return tbl["r_650nm"], tbl["g_550nm"], tbl["b_450nm"]


def _scattering_rgb() -> tuple[float, float, float]:
    """Authored total scattering coefficients packed as RGB in m^-1."""
    tbl = AUTHORED_SCATTERING_M_INV
    return tbl["r_650nm"], tbl["g_550nm"], tbl["b_450nm"]


def _srgb_to_linear(value: float) -> float:
    """Decode one normalized IEC sRGB channel."""
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(value: float) -> float:
    """Encode one normalized linear-light channel as IEC sRGB."""
    value = min(1.0, max(0.0, value))
    return 12.92 * value if value <= 0.0031308 else 1.055 * value ** (1.0 / 2.4) - 0.055


def radiative_transfer_color(
    depth_m: float,
    mat_rgb: tuple[float, float, float],
    *,
    surface_reflection: float = AUTHORED_SURFACE_REFLECTION,
    scatter_tint: tuple[float, float, float] = AUTHORED_SCATTER_TINT_RGB,
    sky_irradiance_ratio: float = CLEAR_SKY_IRRADIANCE_RATIO,
) -> tuple[float, float, float]:
    """Three-band linear-light form of the Nugent (2015) pool model.
Integrates b/2 over attenuation 2a+b; palette and scattering values are proxies."""
    d = max(0.0, _finite("depth_m", depth_m))
    sr = max(0.0, min(1.0, _finite("surface_reflection", surface_reflection)))
    sky = _finite("sky_irradiance_ratio", sky_irradiance_ratio)
    if not 0.0 <= sky <= 1.0:
        raise ValueError("sky_irradiance_ratio must be in [0, 1]")
    channels = []
    for mat, tint, a, b in zip(mat_rgb, scatter_tint, _absorption_rgb(), _scattering_rgb(), strict=True):
        if not all(math.isfinite(c) and 0.0 <= c <= 1.0 for c in (mat, tint)):
            raise ValueError("mat_rgb and scatter_tint must contain finite values in [0, 1]")
        extinction = 2.0 * a + b
        transmission = math.exp(-extinction * d)
        integral = -math.expm1(-extinction * d) / extinction if extinction > 0.0 else d
        column = tint * 0.5 * b * integral
        channels.append(sr * sky + (1.0 - sr) ** 2 * (mat * transmission + column))
    return tuple(channels)


def pool_ramp(shell: dict,
              *,
              n_samples: int = 128,
              surface_reflection: float = AUTHORED_SURFACE_REFLECTION,
              scatter_tint: tuple[float, float, float] = AUTHORED_SCATTER_TINT_RGB,
              ph: float = 8.0,
              ) -> dict:
    """Depth-and-temperature color ramp for one pool shell.
Samples center-to-rim radii and runs the radiative-transfer model."""
    import yellowstone_python.thermal_features.pool_crust as pool_crust
    if n_samples < 2:
        raise ValueError("n_samples must be >= 2")
    r_water = float(shell["r_water_m"])
    t_center = float(shell["t_center_c"])
    t_edge = float(shell["t_edge_c"])
    depth_center = float(shell["depth_center_m"])
    shelf_depth = float(shell["shelf_depth_m"])
    shelf_ratio = float(shell.get("r_shelf_m", r_water * 1.18)) / r_water
    yellow_bottom = shell.get("name") == "Grand Prismatic Spring"
    samples = []
    for i in range(n_samples):
        r = r_water * i / (n_samples - 1)
        t_here = pool_crust.radial_temp(r, r_water, t_center, t_edge)
        d_here = pool_crust.depth_at(r, r_water, depth_center, shelf_depth,
                                     shelf_mult=max(1.001, shelf_ratio))
        class_name = classify_cell(t_here, ph=ph)
        if yellow_bottom:
            class_name = CLASS_YELLOW
            d_here = depth_center * (1.0 - i / (n_samples - 1))
        base_rgb = _mat_rgb_for_class(class_name)
        rgb = radiative_transfer_color(
            d_here, base_rgb,
            surface_reflection=surface_reflection,
            scatter_tint=scatter_tint,
        )
        samples.append({
            "fraction": i / (n_samples - 1),
            "r_m": r,
            "depth_m": d_here,
            "t_c": t_here,
            "class": class_name,
            "rgb01": [round(c, 4) for c in rgb],
            "color": "#%02x%02x%02x" % tuple(
                int(round(_linear_to_srgb(c) * 255.0)) for c in rgb),
        })
    return {
        "schema": SCHEMA_POOL_RAMP,
        "color_space": "linear_rgb",
        "texture_color_space": "srgb",
        "palette_status": "authored sRGB colors decoded to linear-light reflectance proxies",
        "method": "Nugent (2015) equations 1-3, three-band continuum approximation",
        "local_color_uncertainty": "unknown; no site spectroradiometric calibration",
        "bottom_basis": (NUGENT_2015_CITATION + " Section 3A: uniform yellow mat and conical optical depth"
                         if yellow_bottom else "authored radial temperature classes and shell depth"),
        "optical_depth_status": "authored display profile; submerged bathymetry unmeasured",
        "pool_id": shell.get("id"),
        "name": shell.get("name"),
        "samples": samples,
        "parameters": {
            "surface_reflection": surface_reflection,
            "scatter_tint_rgb": list(scatter_tint),
            "absorption_m_inv": POPE_FRY_PURE_WATER_ABSORPTION_M_INV,
            "scattering_m_inv": AUTHORED_SCATTERING_M_INV,
            "sky_irradiance_ratio": CLEAR_SKY_IRRADIANCE_RATIO,
            "sky_ratio_source": NUGENT_2015_CITATION + " Section 2, approximate clear-sky ratio",
            "ph": ph,
        },
        "sources": [POPE_FRY_1997_CITATION, MOREL_1974_CITATION,
                    NUGENT_2015_CITATION],
        "status": "authored",
    }


def write_pool_ramp_png(ramp: dict, path: str, width: int = 256,
                        height: int = 1) -> str:
    """Encode the linear-light pool ramp into an sRGB PNG."""
    from PIL import Image
    if width < 2:
        raise ValueError("ramp width must be >= 2")
    if height < 1:
        raise ValueError("ramp height must be >= 1")
    img = Image.new("RGB", (width, height))
    px = img.load()
    samples = ramp["samples"]
    fractions = np.array([s["fraction"] for s in samples])
    reds = np.array([s["rgb01"][0] for s in samples])
    greens = np.array([s["rgb01"][1] for s in samples])
    blues = np.array([s["rgb01"][2] for s in samples])
    for ix in range(width):
        f = ix / (width - 1)
        r = float(np.interp(f, fractions, reds))
        g = float(np.interp(f, fractions, greens))
        b = float(np.interp(f, fractions, blues))
        rgb = tuple(int(round(_linear_to_srgb(c) * 255.0)) for c in (r, g, b))
        for iy in range(height):
            px[ix, iy] = rgb
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(path)
    return path


@dataclass
class MatState:
    """Dense state of one build of the mat model on the core grid."""

    community_class: np.ndarray
    pigment_index: np.ndarray
    reflectance_rgb: np.ndarray
    legend: list = field(default_factory=lambda: list(COMMUNITY_LEGEND))

    def to_sidecar(self, *, forcing_epoch_utc: float | None,
                   daily_mean_shortwave_w_m2: float,
                   daily_cloud_fraction: float | None,
                   ph: float,
                   insolation_detail: dict | None = None,
                   status: str = "authored") -> dict:
        """Produce the mat_state.json body for this build."""
        return {
            "schema": SCHEMA_MAT_STATE,
            "reflectance_color_space": "srgb_authoring_palette",
            "reflectance_status": "authored display colors; no measured spectral reflectance",
            "status": status,
            "grid": {
                "origin_xz_m": [-CORE_HALF_M, -CORE_HALF_M],
                "cell_size_m": CORE_CELL_M,
                "nx": CORE_GRID_SIZE,
                "nz": CORE_GRID_SIZE,
                "row_order": "north_to_south",
            },
            "legend": self.legend,
            "class_band_edges_c": CLASS_BAND_EDGES_LEGEND,
            "band_edges_status": CLASS_BAND_EDGES_STATUS,
            "forcing_epoch_utc": forcing_epoch_utc,
            "daily_mean_shortwave_w_m2": daily_mean_shortwave_w_m2,
            "daily_cloud_fraction": daily_cloud_fraction,
            "insolation_detail": insolation_detail,
            "ph_assumed": ph,
            "pigment_saturation_sw_w_m2": PIGMENT_SATURATION_SW_W_M2,
            "pigment_saturation_status": PIGMENT_SATURATION_STATUS,
            "carotenoid_endpoint_rgb_0_1": list(CAROTENOID_ENDPOINT_RGB),
            "carotenoid_endpoint_status": CAROTENOID_ENDPOINT_STATUS,
            "photoacclimation_direction_source": PHOTOACCLIMATION_CITATION,
            "pigment_relaxation_tau_days": PIGMENT_RELAXATION_TAU_DAYS,
            "pigment_tau_status": PIGMENT_RELAXATION_TAU_STATUS,
            "citations": [NUGENT_2015_CITATION, BROCK_1978_CITATION,
                          POPE_FRY_1997_CITATION, MOREL_1974_CITATION,
                          PHOTOACCLIMATION_CITATION,
                          KASTEN_CZEPLAK_1980_CITATION],
        }


def build_mat_state(
    temperature_c: np.ndarray,
    *,
    previous_pigment: np.ndarray | None = None,
    daily_mean_shortwave_w_m2: float,
    dt_days: float,
    ph: float = 8.0,
    tau_days: float = PIGMENT_RELAXATION_TAU_DAYS,
) -> MatState:
    """One build of the mat state from a temperature field.
Pigment relaxes toward the irradiance-driven steady state."""
    temperature = np.asarray(temperature_c, dtype=np.float64)
    if temperature.ndim != 2:
        raise ValueError("temperature_c must be a 2-D array")
    classes = classify_temperature_field(temperature, ph=ph)
    steady = steady_state_pigment_index(daily_mean_shortwave_w_m2)
    if previous_pigment is None:
        pigment = np.full(temperature.shape, steady, dtype=np.float32)
    else:
        prior = np.asarray(previous_pigment, dtype=np.float64)
        if prior.shape != temperature.shape:
            raise ValueError("previous_pigment shape must match temperature")
        weight = dt_days / (dt_days + tau_days)
        pigment = (prior + weight * (steady - prior)).astype(np.float32)

    r_end, g_end, b_end = CAROTENOID_ENDPOINT_RGB
    rgb = np.zeros(temperature.shape + (3,), dtype=np.float32)
    for entry in COMMUNITY_LEGEND:
        mask = classes == entry["class_id"]
        if not mask.any():
            continue
        rgb_list = entry["rgb"]
        base = (rgb_list[0] / 255.0, rgb_list[1] / 255.0, rgb_list[2] / 255.0)
        if entry["name"] in (CLASS_YELLOW_GREEN, CLASS_YELLOW, CLASS_ORANGE,
                             CLASS_BROWN_GREEN):
            shifted_r = base[0] + (r_end - base[0]) * pigment[mask]
            shifted_g = base[1] + (g_end - base[1]) * pigment[mask]
            shifted_b = base[2] + (b_end - base[2]) * pigment[mask]
            rgb[mask, 0] = shifted_r
            rgb[mask, 1] = shifted_g
            rgb[mask, 2] = shifted_b
        else:
            rgb[mask, 0] = base[0]
            rgb[mask, 1] = base[1]
            rgb[mask, 2] = base[2]
    return MatState(community_class=classes,
                    pigment_index=pigment,
                    reflectance_rgb=rgb)


def write_mat_state(state: MatState, out_dir: str, *,
                    sidecar_extra: dict | None = None) -> dict:
    """Serialize a MatState to community.i16, pigment.f32, reflectance.f32."""
    import hashlib
    os.makedirs(out_dir, exist_ok=True)
    paths = {}
    community = np.ascontiguousarray(state.community_class.astype("<i2"))
    community_path = os.path.join(out_dir, "mat_community.i16")
    community.tofile(community_path)
    paths["community"] = {
        "path": "mat_community.i16",
        "dtype": "int16",
        "nodata": -1,
        "sha256": hashlib.sha256(community.tobytes()).hexdigest(),
    }
    pigment = np.ascontiguousarray(state.pigment_index.astype("<f4"))
    pigment_path = os.path.join(out_dir, "mat_pigment.f32")
    pigment.tofile(pigment_path)
    paths["pigment"] = {
        "path": "mat_pigment.f32",
        "dtype": "float32",
        "nodata": "NaN",
        "sha256": hashlib.sha256(pigment.tobytes()).hexdigest(),
    }
    reflectance = np.ascontiguousarray(state.reflectance_rgb.astype("<f4"))
    reflectance_path = os.path.join(out_dir, "mat_reflectance_rgb.f32")
    reflectance.tofile(reflectance_path)
    paths["reflectance_rgb"] = {
        "path": "mat_reflectance_rgb.f32",
        "dtype": "float32",
        "layout": "interleaved_rgb",
        "sha256": hashlib.sha256(reflectance.tobytes()).hexdigest(),
    }
    sidecar = dict(sidecar_extra or {})
    sidecar.setdefault("schema", SCHEMA_MAT_STATE)
    sidecar["rasters"] = paths
    sidecar.setdefault("legend", list(state.legend))
    write_json_atomic(os.path.join(out_dir, "mat_state.json"), sidecar, indent=2)
    return sidecar


def write_mat_pigment_png(state: MatState, path: str,
                          legend_path: str | None = None,
                          *,
                          season: str | None = None,
                          status: str = "authored") -> str:
    """Render the mat RGB field to the 2560x2560 world-space PNG.
Each core cell writes a 2x2 pixel block at 0.5 m per pixel."""
    from PIL import Image
    if state.reflectance_rgb.shape[0] != CORE_GRID_SIZE:
        raise ValueError("mat state must be on the core grid")
    rgb = (np.clip(state.reflectance_rgb, 0.0, 1.0) * 255.0).astype(np.uint8)
    big = np.repeat(np.repeat(rgb, 2, axis=0), 2, axis=1)
    # Alpha 0 marks no mat: dry sinter and nodata (-1) cells.
    no_mat = ((state.community_class == CLASS_ID_BY_NAME[CLASS_SINTER_DRY])
              | (state.community_class < 0))
    alpha = np.where(no_mat, 0, 255).astype(np.uint8)
    alpha_big = np.repeat(np.repeat(alpha, 2, axis=0), 2, axis=1)
    rgba = np.concatenate([big, alpha_big[..., None]], axis=-1)
    img = Image.fromarray(rgba, mode="RGBA")
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    img.save(path)
    if legend_path is not None:
        legend = {
            "schema": "yellowstone.mat_pigment_png.v1",
            "extent_xz_m": [-CORE_HALF_M, -CORE_HALF_M,
                            CORE_HALF_M, CORE_HALF_M],
            "pixel_size_m": MAT_PIGMENT_PIXEL_M,
            "size_px": [MAT_PIGMENT_SIZE, MAT_PIGMENT_SIZE],
            "row_zero_z_m": -CORE_HALF_M,
            "class_colors_rgb_0_255": [
                {"name": e["name"], "rgb": e["rgb"]}
                for e in COMMUNITY_LEGEND
            ],
            "season": season,
            "status": status,
            "citations": [NUGENT_2015_CITATION],
        }
        parent = os.path.dirname(os.path.abspath(legend_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        write_json_atomic(legend_path, legend, indent=2)
    return path


__all__ = [
    "SCHEMA_MAT_STATE",
    "SCHEMA_POOL_RAMP",
    "CORE_GRID_SIZE",
    "COMMUNITY_LEGEND",
    "CLASS_BAND_EDGES_C",
    "CLASS_BAND_EDGES_LEGEND",
    "CLASS_BAND_EDGES_STATUS",
    "CLASS_ID_BY_NAME",
    "PHOTOSYNTHESIS_LIMIT_NEUTRAL_C",
    "PHOTOSYNTHESIS_LIMIT_ACIDIC_C",
    "PIGMENT_RELAXATION_TAU_DAYS",
    "PIGMENT_SATURATION_SW_W_M2",
    "CAROTENOID_ENDPOINT_RGB",
    "PHOTOACCLIMATION_CITATION",
    "KASTEN_CZEPLAK_1980_CITATION",
    "MatState",
    "photosynthesis_limit_c",
    "classify_cell",
    "classify_temperature_field",
    "steady_state_pigment_index",
    "kasten_czeplak_cloud_attenuation",
    "daily_mean_insolation_w_m2",
    "instantaneous_shortwave_w_m2",
    "relax_pigment",
    "integrate_pigment",
    "radiative_transfer_color",
    "pool_ramp",
    "write_pool_ramp_png",
    "build_mat_state",
    "write_mat_state",
    "write_mat_pigment_png",
]
