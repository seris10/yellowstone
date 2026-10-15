"""Build constants and shared model imports."""
from __future__ import annotations
from yellowstone_python.common.io import write_json_atomic
from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG
from yellowstone_python.common.checks import (fraction as _fraction, finite as _finite_number, nonnegative as _nonnegative_number, positive as _positive_finite, nonnegative as _nonnegative_finite)
import copy
import json
import math
from pathlib import Path
from typing import Any
from yellowstone_python.common.provenance import (CONTRACT_VERSION, WORLD_ID, build_id,
                                 default_world_root, resolve_code_rev,
                                 sha256_file, sha256_json, write_sidecar)
from yellowstone_python.validation.checks import (HYDRO_HEAT_LEDGER_TOL_J,
                                HYDRO_WATER_LEDGER_TOL_M3,
                                REPLAY_HEAT_RELATIVE_TOLERANCE,
                                REPLAY_WATER_RELATIVE_TOLERANCE,
                                SNOW_STORAGE_TOL_MM)
from yellowstone_python.exporters.to_ecosystem import merge_fragments, validate_for_godot
from yellowstone_python.registry.run_mode import normalize_run_mode, prescribed_quantities, predicted_quantities
from yellowstone_python.thermal_features.plume import (DEFAULT_TRIBUTARIES, plume_field,
                              render_plume_png)
from yellowstone_python.atmosphere.microclimate import air_temp, prevailing_direction, trace
from yellowstone_python.land.overland_flow import run_overland
from yellowstone_python.river.river_world import build_mapped_replay
from yellowstone_python.atmosphere.time_utils import epoch_unix_for_local, parse_simulation_start
PKG_ROOT = Path(__file__).resolve().parents[2]
REACH_EXCELSIOR = "excelsior_mixing"
REACH_BRIDGE = "bridge_downstream"
RIVER_FIREHOLE = "river_5856_0"
POOL_GRAND = "pool_1034_0"
PATCH_RIPARIAN = "bridge_riparian"
BISON_DEMO = "bison_01"
OUTFLOW_SITE_ALTITUDE_M = 2240.0
MAT_IMAGERY_DATE_UTC = "2022-07-19"
CANOPY_FALLBACK = 0.6
REPLAY_WEATHER_KEYS = ("night_air_c", "day_warming_c", "wind_xz_mps",
                       "gust_mps", "humidity", "cloud", "lag_hours")


def _find(items: list, key: str, value: str, what: str) -> dict:
    for it in items:
        if isinstance(it, dict) and it.get(key) == value:
            return it
    have = [str(it.get(key)) for it in items if isinstance(it, dict)][:12]
    raise ValueError(f"{what} {value!r} not found; have {have}")
