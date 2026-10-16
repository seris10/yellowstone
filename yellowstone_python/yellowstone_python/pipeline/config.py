"""Config build operations."""
from __future__ import annotations

from yellowstone_python.pipeline.shared import Path, _finite_number, _fraction, _nonnegative_finite, _positive_finite, copy, default_world_root, normalize_run_mode

def load_config(path: Path) -> dict:
    import yaml
    cfg = yaml.safe_load(Path(path).read_text())
    if cfg is None or not isinstance(cfg, dict):
        raise ValueError("configuration root must be a mapping")
    return cfg


def _nonnegative_int(name: str, value) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean")
    if not isinstance(value, int):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


def normalized_config(cfg: dict) -> dict:
    """Non-mutating normalization used for hashing and simulation."""
    result = copy.deepcopy(cfg)
    result["run_mode"] = normalize_run_mode(result.get("run_mode"))
    result.setdefault("world_root", str(default_world_root()))
    return result


def validate_config(cfg: dict) -> dict:
    """Reject nonphysical config before any simulation. Returns a normalized copy.
Numeric fields pass through _finite_number so NaN, inf, bool, and string values raise."""
    normalized = normalized_config(cfg)
    mammals = normalized.get("mammals", {}) or {}
    if not isinstance(mammals, dict):
        raise ValueError("mammals must be a mapping")
    if "enabled" in mammals and not isinstance(mammals["enabled"], bool):
        raise ValueError("mammals.enabled must be boolean")
    if "seed" in mammals:
        _nonnegative_int("mammals.seed", mammals["seed"])
    if not Path(normalized.get("world_root", "")).is_dir():
        raise ValueError(
            f"world_root {normalized.get('world_root')!r} is not a directory")
    if "clock_hour" in normalized:
        h = _finite_number("clock_hour", normalized["clock_hour"])
        if not (0.0 <= h < 24.0):
            raise ValueError(f"clock_hour {h} outside [0, 24)")
    # Absent clock_hour falls back to the system clock at simulate time via resolve_game_clock.
    hydro = normalized.get("hydro", {}) or {}
    from yellowstone_python.common.units import TEMPERATURE_RANGE_C, validate_hydro_units
    validate_hydro_units(hydro)
    _positive_finite("hydro.boundary_m3s", hydro.get("boundary_m3s", 8.0))
    _finite_number("hydro.boundary_c", hydro.get("boundary_c", 17.5),
                   minimum=TEMPERATURE_RANGE_C[0], maximum=TEMPERATURE_RANGE_C[1])
    _nonnegative_finite("hydro.simulate_seconds",
                        hydro.get("simulate_seconds", 600.0))
    weather = normalized.get("weather", {}) or {}
    if "use_met_bundle" in weather and not isinstance(weather["use_met_bundle"], bool):
        raise ValueError("weather.use_met_bundle must be boolean")
    if weather.get("use_met_bundle") is False and weather.get("met_bundle"):
        raise ValueError("a met bundle path requires weather.use_met_bundle")
    for key in ("humidity", "cloud"):
        if key in weather:
            _fraction(f"weather.{key}", weather[key])
    if "gust_mps" in weather:
        _nonnegative_finite("weather.gust_mps", weather["gust_mps"])
    if "lag_hours" in weather:
        _finite_number("weather.lag_hours", weather["lag_hours"])
    if "night_air_c" in weather:
        _finite_number("weather.night_air_c", weather["night_air_c"])
    if "day_warming_c" in weather:
        _finite_number("weather.day_warming_c", weather["day_warming_c"])
    w = weather.get("wind_xz_mps", [1.8, 0.6])
    if not isinstance(w, (list, tuple)) or len(w) != 2:
        raise ValueError("weather.wind_xz_mps must be a 2-vector of numbers")
    _finite_number("weather.wind_xz_mps[0]", w[0])
    _finite_number("weather.wind_xz_mps[1]", w[1])
    _fraction("insects.flowering_stage",
              normalized.get("insects", {}).get("flowering_stage", 0.6))
    for key in ("food", "cover"):
        if key in normalized.get("fish", {}):
            _fraction(f"fish.{key}", normalized["fish"][key])
    if "species" in normalized.get("fish", {}):
        from yellowstone_python.aquatic.fish import THERMAL_SPECIES
        if normalized["fish"]["species"] not in THERMAL_SPECIES:
            raise ValueError(
                f"fish.species {normalized['fish']['species']!r} unknown; "
                f"have {sorted(THERMAL_SPECIES)}")
    snow = normalized.get("snow", {}) or {}
    _nonnegative_int("snow.days", snow.get("days", 30))
    _nonnegative_finite("snow.precip_mm_d", snow.get("precip_mm_d", 2.0))
    if snow.get("season") is not None and snow["season"] not in (
            "summer", "autumn", "winter", "spring"):
        raise ValueError(f"unknown snow.season {snow['season']!r}")
    if snow.get("as_of_date") is not None:
        import datetime
        try:
            datetime.date.fromisoformat(str(snow["as_of_date"]))
        except ValueError:
            raise ValueError(f"snow.as_of_date {snow['as_of_date']!r} "
                             f"is not YYYY-MM-DD")
    rcfg = normalized.get("replay", {}) or {}
    if "cross_sections_file" in rcfg and not isinstance(
            rcfg["cross_sections_file"], str):
        raise ValueError("replay.cross_sections_file must be a string path")
    _positive_finite("replay.duration_s", rcfg.get("duration_s", 7200.0))
    _positive_finite("replay.max_cell_m", rcfg.get("max_cell_m", 20.0))
    _positive_finite("replay.depth_m", rcfg.get("depth_m", 1.1))
    _nonnegative_finite("replay.dispersion_m2_s",
                        rcfg.get("dispersion_m2_s", 1.0))
    _nonnegative_finite("replay.exchange_w_m2_k",
                        rcfg.get("exchange_w_m2_k", 12.0))
    _positive_finite("replay.dt_s", rcfg.get("dt_s", 2.0))
    _positive_finite("replay.sample_s", rcfg.get("sample_s", 10.0))
    intervention = rcfg.get("intervention")
    if intervention is not None:
        if not isinstance(intervention, dict) or set(intervention) != {"source_id", "start_s", "end_s", "delta_c"}:
            raise ValueError("replay.intervention requires source_id, start_s, end_s and delta_c")
        if not isinstance(intervention["source_id"], str) or not intervention["source_id"]:
            raise ValueError("replay.intervention.source_id must be nonempty")
        start = _positive_finite("intervention.start_s", intervention["start_s"])
        end = _positive_finite("intervention.end_s", intervention["end_s"])
        if not start < end < float(rcfg.get("duration_s", 7200.)):
            raise ValueError("intervention must lie inside the replay window")
        _finite_number("intervention.delta_c", intervention["delta_c"])
    hyd = rcfg.get("hydraulics", {})
    if not isinstance(hyd, dict):
        raise ValueError("replay.hydraulics must be a mapping")
    _nonnegative_finite("replay.hydraulics.bank_slope_zh",
                        hyd.get("bank_slope_zh", 1.5))
    _positive_finite("replay.hydraulics.manning_n",
                     hyd.get("manning_n", 0.035))
    olfg = normalized.get("overland", {}) or {}
    if olfg.get("enabled", False):
        _nonnegative_finite("overland.rain_mm_h", olfg.get("rain_mm_h", 0.0))
        _positive_finite("overland.dt_s", olfg.get("dt_s", 60.0))
        _nonnegative_finite("overland.sim_s", olfg.get("sim_s", 0.0))
        from yellowstone_python.common.checks import positive_int
        grid_val = positive_int("overland.grid", olfg.get("grid", 256))
        if grid_val <= 0:
            raise ValueError("overland.grid must be > 0")
        _positive_finite("overland.cell_m", olfg.get("cell_m", 8.0))
    catch = (normalized.get("hydro", {}) or {}).get("catchment", {}) or {}
    if catch.get("area_m2") is not None:
        _positive_finite("hydro.catchment.area_m2", catch["area_m2"])
    sim = normalized.get("simulation", {}) or {}
    if "start_epoch_unix" in sim:
        _finite_number("simulation.start_epoch_unix", sim["start_epoch_unix"])
    if "utc_offset_hours" in sim:
        _finite_number("simulation.utc_offset_hours",
                       sim["utc_offset_hours"])
    if "wind_seed" in normalized:
        _nonnegative_int("wind_seed", normalized["wind_seed"])
    # Measured-mode builds require an explicit simulation start; no system-clock date fallback.
    if normalized["run_mode"] in ("hindcast", "observed_replay"):
        has_explicit = (
            "start_epoch_unix" in sim or "start_utc" in sim
            or snow.get("as_of_date") is not None)
        if not has_explicit:
            raise ValueError(
                "run_mode "
                f"{normalized['run_mode']!r} requires an explicit "
                "simulation start: set simulation.start_epoch_unix, "
                "simulation.start_utc, or snow.as_of_date")
    return normalized
