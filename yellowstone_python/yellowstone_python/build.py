"""Build pipeline: runs all modules and writes derived artifacts."""
from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from .common.provenance import (CONTRACT_VERSION, WORLD_ID, build_id,
                                 default_world_root, sha256_file,
                                 sha256_json, write_sidecar)
from .exporters.to_ecosystem import merge_fragments, validate_for_godot
from .run_mode import (normalize_run_mode, prescribed_quantities,
                       predicted_quantities)
from .hydro_thermal import (DEFAULT_TRIBUTARIES, plume_field,
                              render_plume_png, run_simulation)
from .microclimate import air_temp, prevailing_direction, trace
from .overland_flow import run_overland
from .replay.river_world import build_mapped_replay

PKG_ROOT = Path(__file__).resolve().parents[1]

# Authored topology: named lookups fail loudly (never silent wrong defaults).
REACH_EXCELSIOR = "excelsior_mixing"
REACH_BRIDGE = "bridge_downstream"
RIVER_FIREHOLE = "river_5856_0"
POOL_GRAND = "pool_1034_0"
PATCH_RIPARIAN = "bridge_riparian"
BISON_DEMO = "bison_01"


def _find(items: list, key: str, value: str, what: str) -> dict:
    for it in items:
        if isinstance(it, dict) and it.get(key) == value:
            return it
    have = [str(it.get(key)) for it in items if isinstance(it, dict)][:12]
    raise ValueError(f"{what} {value!r} not found; have {have}")


def load_config(path: Path) -> dict:
    import yaml
    cfg = yaml.safe_load(Path(path).read_text())
    if cfg is None or not isinstance(cfg, dict):
        raise ValueError("configuration root must be a mapping")
    return cfg


def _fraction(name: str, value, lo: float = 0.0, hi: float = 1.0) -> float:
    v = float(value)
    if not (lo <= v <= hi):
        raise ValueError(f"config {name}={value} outside [{lo}, {hi}]")
    return v


def _positive_finite(name, value):
    if isinstance(value, bool):
        raise ValueError(f"{name} must not be boolean")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if result <= 0:
        raise ValueError(f"{name} must be > 0")
    return result


def validate_config(cfg: dict) -> None:
    """Reject nonphysical config before any simulation (explicit, early)."""
    cfg["run_mode"] = normalize_run_mode(cfg.get("run_mode"))
    cfg.setdefault("world_root", str(default_world_root()))
    if not Path(cfg.get("world_root", "")).is_dir():
        raise ValueError(f"world_root {cfg.get('world_root')!r} is not a directory")
    h = float(cfg.get("clock_hour", 16.2))
    if not (0.0 <= h < 24.0):
        raise ValueError(f"clock_hour {h} outside [0, 24)")
    # Absent clock_hour falls back to the system clock at simulate time
    # (resolve_game_clock, range-safe by construction); only explicit
    # values are range-checked here.
    hydro = cfg.get("hydro", {})
    from .common.hydro_units import validate_hydro_units
    validate_hydro_units(hydro)
    _positive_finite("hydro.boundary_m3s", hydro.get("boundary_m3s", 8.0))
    bc = float(hydro.get("boundary_c", 17.5))
    if not (-10.0 <= bc <= 45.0):
        raise ValueError("hydro.boundary_c outside [-10, 45] °C")
    if float(hydro.get("simulate_seconds", 600.0)) < 0:
        raise ValueError("hydro.simulate_seconds must be ≥ 0")
    for key in ("humidity", "cloud"):
        if key in cfg.get("weather", {}):
            _fraction(f"weather.{key}", cfg["weather"][key])
    if "gust_mps" in cfg.get("weather", {}) and float(cfg["weather"]["gust_mps"]) < 0:
        raise ValueError("weather.gust_mps must be ≥ 0")
    w = cfg.get("weather", {}).get("wind_xz_mps", [1.8, 0.6])
    if len(w) != 2 or not all(isinstance(v, (int, float)) for v in w):
        raise ValueError("weather.wind_xz_mps must be a 2-vector of numbers")
    _fraction("insects.flowering_stage",
              cfg.get("insects", {}).get("flowering_stage", 0.6))
    for key in ("food", "cover"):
        if key in cfg.get("fish", {}):
            _fraction(f"fish.{key}", cfg["fish"][key])
    if "species" in cfg.get("fish", {}):
        from .fish import THERMAL_SPECIES
        if cfg["fish"]["species"] not in THERMAL_SPECIES:
            raise ValueError(
                f"fish.species {cfg['fish']['species']!r} unknown; "
                f"have {sorted(THERMAL_SPECIES)}")
    snow = cfg.get("snow", {})
    if int(snow.get("days", 30)) < 0 or float(snow.get("precip_mm_d", 2.0)) < 0:
        raise ValueError("snow.days/precip_mm_d must be ≥ 0")
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
    rcfg = cfg.get("replay", {})
    if "cross_sections_file" in rcfg and not isinstance(rcfg["cross_sections_file"], str):
        raise ValueError("replay.cross_sections_file must be a string path")
    if float(rcfg.get("duration_s", 7200.0)) <= 0:
        raise ValueError("replay.duration_s must be > 0")
    if float(rcfg.get("max_cell_m", 20.0)) <= 0:
        raise ValueError("replay.max_cell_m must be > 0")
    if float(rcfg.get("depth_m", 1.1)) <= 0:
        raise ValueError("replay.depth_m must be > 0")
    if float(rcfg.get("dispersion_m2_s", 1.0)) < 0:
        raise ValueError("replay.dispersion_m2_s must be ≥ 0")
    if float(rcfg.get("exchange_w_m2_k", 12.0)) < 0:
        raise ValueError("replay.exchange_w_m2_k must be ≥ 0")
    if float(rcfg.get("dt_s", 2.0)) <= 0:
        raise ValueError("replay.dt_s must be > 0")
    if float(rcfg.get("sample_s", 10.0)) <= 0:
        raise ValueError("replay.sample_s must be > 0")
    hyd = rcfg.get("hydraulics", {})
    if not isinstance(hyd, dict):
        raise ValueError("replay.hydraulics must be a mapping")
    if float(hyd.get("bank_slope_zh", 1.5)) < 0:
        raise ValueError("replay.hydraulics.bank_slope_zh must be ≥ 0")
    if float(hyd.get("manning_n", 0.035)) <= 0:
        raise ValueError("replay.hydraulics.manning_n must be > 0")
    olfg = cfg.get("overland", {})
    if olfg.get("enabled", False):
        if float(olfg.get("rain_mm_h", 0.0)) < 0:
            raise ValueError("overland.rain_mm_h must be >= 0")
        if float(olfg.get("dt_s", 60.0)) <= 0:
            raise ValueError("overland.dt_s must be > 0")
        if float(olfg.get("sim_s", 0.0)) < 0:
            raise ValueError("overland.sim_s must be >= 0")
        if int(olfg.get("grid", 256)) <= 0:
            raise ValueError("overland.grid must be > 0")
        if float(olfg.get("cell_m", 8.0)) <= 0:
            raise ValueError("overland.cell_m must be > 0")
    catch = cfg.get("hydro", {}).get("catchment", {}) or {}
    if catch.get("area_m2") is not None:
        _positive_finite("hydro.catchment.area_m2", catch["area_m2"])


def load_inputs(cfg: dict) -> tuple[dict, dict, dict, object]:
    """(baseline, world, deps, terrain_sample_fns). Content-complete hashes."""
    import hashlib
    from .vegetation import load_terrain, terrain_fns
    world_root = Path(cfg.get("world_root") or default_world_root())
    eco_path = world_root / "data" / "ecosystem.json"
    frozen = eco_path.with_suffix(".json.pre-python")
    if frozen.exists():
        eco_path = frozen  # idempotent rebuilds, never compounding
    baseline = json.loads(eco_path.read_text())
    world = json.loads((world_root / "data" / "world.json").read_text())
    code_hash = hashlib.sha256()
    for py in sorted((PKG_ROOT / "yellowstone_python").rglob("*.py")):
        code_hash.update(py.read_bytes())
    deps = {"ecosystem.json": sha256_file(eco_path),
            "world.json": sha256_file(world_root / "data" / "world.json"),
            "placements.json": sha256_file(world_root / "data" / "placements.json"),
            "species_catalogue.json": sha256_file(
                world_root / "data" / "species_catalogue.json"),
            "terrain.f32": sha256_file(world_root / "data" / "terrain.f32"),
            "code": code_hash.hexdigest()[:16],
            "config": sha256_json(cfg)}
    tfns = terrain_fns(load_terrain(str(world_root / "data" / "terrain.f32")))
    return baseline, world, deps, tfns


REPLAY_WEATHER_KEYS = ("night_air_c", "day_warming_c", "wind_xz_mps",
                       "gust_mps", "humidity", "cloud", "lag_hours")


def _prepare_replay_ecosystem(baseline: dict, cfg: dict, hour0: float | None = None,
                              weather: dict | None = None,
                              boundary_m3s: float | None = None) -> dict:
    """Apply config overrides to a deepcopy of the baseline for the replay solver.

    hour0 and weather carry the resolved game clock and the weather fragment
    the mixing chain receives, so the solver and the chain share one air
    forcing and one starting hour. boundary_m3s carries the effective
    discharge, including any snow-derived runoff increment.
    """
    eco = copy.deepcopy(baseline)
    hcfg = cfg.get("hydro", {})
    eco["boundary_m3s"] = float(hcfg.get("boundary_m3s", baseline["boundary_m3s"])
                                if boundary_m3s is None else boundary_m3s)
    eco["boundary_c"] = float(hcfg.get("boundary_c", baseline["boundary_c"]))
    if hour0 is not None:
        eco["clock_hour"] = float(hour0)
    if weather:
        injected = {k: copy.deepcopy(weather[k]) for k in REPLAY_WEATHER_KEYS
                    if k in weather}
        if injected:
            eco["weather"] = {**eco.get("weather", {}), **injected}
    tribs = {**DEFAULT_TRIBUTARIES, **hcfg.get("tributaries", {})}
    by_id = {r["id"]: r for r in eco["river_reaches"]}
    for rid, names in hcfg.get("attach", {}).items():
        if rid not in by_id:
            raise ValueError(f"hydro.attach reach {rid!r} not in chain "
                             f"{list(by_id)}")
        for n in names:
            t = tribs.get(n, {})
            if t.get("flow_m3s", 0.0) > 0:
                by_id[rid].setdefault("lateral_sources", []).append(
                    {"id": n, **t, "status": "illustrative tributary"})
    return eco


def run_replay_solver(cfg: dict, baseline: dict, world: dict,
                      hour0: float | None = None,
                      weather: dict | None = None,
                      boundary_m3s: float | None = None) -> dict:
    """Run the 1-D advection-dispersion solver on the Firehole chain.

    Returns the full replay document with timestamped frames and budget.
    """
    rcfg = cfg.get("replay", {})
    eco = _prepare_replay_ecosystem(baseline, cfg, hour0=hour0, weather=weather,
                                    boundary_m3s=boundary_m3s)
    cross_sections = {}
    if "cross_sections_file" in rcfg:
        cs_path = Path(rcfg["cross_sections_file"])
        if not cs_path.is_absolute():
            cs_path = PKG_ROOT / cs_path
        cross_sections = json.loads(cs_path.read_text())
    hyd = rcfg.get("hydraulics", {})
    doc = build_mapped_replay(
        world, eco,
        duration_s=float(rcfg.get("duration_s", 7200.0)),
        maximum_cell_m=float(rcfg.get("max_cell_m", 20.0)),
        depth_m=float(rcfg.get("depth_m", 1.1)),
        dispersion_m2_s=float(rcfg.get("dispersion_m2_s", 1.0)),
        exchange_w_m2_k=float(rcfg.get("exchange_w_m2_k", 12.0)),
        dt_s=float(rcfg.get("dt_s", 2.0)),
        sample_s=float(rcfg.get("sample_s", 10.0)),
        cross_sections=cross_sections if cross_sections else None,
        energy_budget=bool(rcfg.get("energy_budget", False)),
        bank_slope_zh=float(hyd.get("bank_slope_zh", 1.5)),
        manning_n=float(hyd.get("manning_n", 0.035)),
    )
    return doc


def simulate_all(cfg: dict, baseline: dict, world: dict, tfns) -> dict:
    """Pure scientific simulation: no files, no PNGs, no CLI. Returns state."""
    from .fish import check_trout_clear_of_pools, update_trout
    from .geochemistry import check_midway_shells
    from .grazers import (check_routes as check_grazer_routes, plan_path,
                          route_length as _rlen, update_grazers)
    from .insects_birds import (DEFAULT_DIETS, foraging_state, insect_activity,
                                step_compartments, step_resource,
                                update_wildlife, update_wildlife_from_intake)
    from .pool_crust import build_all as build_shells
    from .pool_crust import exclusion_violations as apron_violations
    from .pool_crust import in_apron as _in_apron
    from .snow_season import resolve_game_clock, run_season
    from .vegetation import (patch_step, propose_plantings_reviewed)

    world_root = Path(cfg.get("world_root") or default_world_root())
    wcfg = dict(cfg.get("weather", {}))
    scfg_early = cfg.get("snow", {})
    clock_info = resolve_game_clock(
        season_cfg=scfg_early.get("season"),
        clock_cfg=cfg.get("clock_hour", baseline.get("clock_hour")),
        date_cfg=scfg_early.get("as_of_date"))
    hour0 = clock_info["clock_hour"]

    # Weather forcing: measured bundle wins over authored defaults. The bundle
    # is written once by tools/fetch_met_forcing.py (Open-Meteo) and frozen, so
    # builds are reproducible; absent bundle = authored scenario, stated as
    # such. See microclimate.WEATHER_PROVENANCE for per-key provenance.
    from .microclimate import load_weather_bundle, bundle_weather
    # The build writes sidecars into yellowstone_python/derived/, so look for
    # the met bundle there rather than under the world checkout.
    met_path = PKG_ROOT / "derived" / "met.json"
    met_bundle = load_weather_bundle(str(met_path))
    if met_bundle:
        wcfg = {**wcfg, **bundle_weather(met_bundle, hour=hour0)}
    weather_provenance = ("open-meteo hourly bundle "
                          "(measured_remote_not_calibrated)" if met_bundle
                          else "authored defaults; no met bundle present")

    air0 = air_temp(hour0, wcfg.get("night_air_c", 7.0),
                    wcfg.get("day_warming_c", 15.0),
                    wcfg.get("lag_hours", 3.0))
    wind_trace = trace(seconds=60, hour0=hour0,
                       wind_xz_mps=tuple(wcfg.get("wind_xz_mps", [1.8, 0.6])),
                       gust_mps=wcfg.get("gust_mps", 0.45),
                       night_air_c=wcfg.get("night_air_c", 7.0),
                       day_warming_c=wcfg.get("day_warming_c", 15.0),
                       humidity=wcfg.get("humidity", 0.45),
                       cloud=wcfg.get("cloud", 0.16),
                       lag_hours=wcfg.get("lag_hours", 3.0),
                       seed=int(cfg.get("wind_seed", 11)))
    from .microclimate import condensation_potential
    weather_frag = {**wcfg,
                    "weather_provenance": weather_provenance,
                    "met_bundle": bool(met_bundle),
                    "prevailing_deg": prevailing_direction(
                        tuple(wcfg.get("wind_xz_mps", [1.8, 0.6]))),
                    "air_c_at_start": air0,
                    "godot_divergence_note": (
                        "published night/day params drive ecosystem.gd's "
                        "noon-peaking air; Python analysis uses a "
                        "15:00-lagging curve. Residual documented.")}
    wx, wz = weather_frag.get("wind_xz_mps", [1.8, 0.6])
    wind_mag = math.hypot(float(wx), float(wz))
    weather_frag["condensation_62C"] = condensation_potential(
        62.0, air0, wcfg.get("humidity", 0.45), wind_mag)

    hcfg = cfg.get("hydro", {})
    sim_s = float(hcfg.get("simulate_seconds", 600.0))

    # --- M03 shells ---
    shells = build_shells(world["pools"])
    _find(shells, "id", POOL_GRAND, "pool shell")
    substrate_failures = check_midway_shells(shells)

    def _excluded(x: float, z: float) -> bool:
        return any(_in_apron(x, z, s) for s in shells)

    # --- M04 vegetation + proposals ---
    vcfg = cfg.get("vegetation", {})
    patches0 = copy.deepcopy(baseline.get("patches", []))
    patches1, veg_ledger = patch_step(patches0, hour0, sim_s,
                                      grazers=vcfg.get("grazers"))
    prop_cfg = vcfg.get("proposal", {})
    proposals, review_log = propose_plantings_reviewed(
        prop_cfg.get("guild", "lodgepole_pine"),
        tuple(prop_cfg.get("center_xz", [-360, 260])),
        float(prop_cfg.get("radius_m", 30)),
        int(prop_cfg.get("count", 40)), int(prop_cfg.get("seed", 7)),
        habitat_id=prop_cfg.get("habitat_id", "forest_edge"),
        exclusion_test=_excluded, terrain_fn=tfns, patches=patches0,
        canopy=0.6,
        suitability_threshold=float(prop_cfg.get("suitability_threshold", 0.12)))
    prop_violations = apron_violations(
        [{"id": r["stable_id"], "x": r["x"], "z": r["z"]} for r in proposals],
        shells)

    # --- M08 season (before the river so its ledger reaches the boundary) ---
    scfg = cfg.get("snow", {})
    snow_days = int(scfg.get("days", 30))
    snow_air = scfg.get("air_c_by_day", [air0] * snow_days)
    patches2, snow_ledger = run_season(
        patches1, days=snow_days, air_c_by_day=snow_air,
        precip_mm_d=float(scfg.get("precip_mm_d", 2.0)),
        thermal_test=_excluded)
    season = clock_info["season"]  # explicit snow.season wins, else clock

    # --- M08b snow runoff as a discharge increment over the basin ---
    from .snow_season import catchment_runoff_m3_s
    catchment_area = hcfg.get("catchment", {}).get("area_m2")
    catchment = {"schema": "yellowstone.catchment_runoff.v1",
                 "enabled": catchment_area is not None,
                 "area_m2": catchment_area,
                 "status": "illustrative_not_calibrated"}
    if catchment_area is not None:
        runoff = catchment_runoff_m3_s(patches1, snow_ledger,
                                       catchment_area_m2=catchment_area)
        catchment.update(runoff)
    else:
        runoff = {"runoff_m3_s": 0.0}
        catchment["provenance"] = (
            "no catchment area configured; snow hydrology is storage-only "
            "and the river boundary stays at its prescribed baseflow")
    runoff_m3_s = float(runoff["runoff_m3_s"])

    # --- M01 hydro ---
    tribs = {**DEFAULT_TRIBUTARIES, **hcfg.get("tributaries", {})}
    reaches_in = copy.deepcopy(baseline["river_reaches"])
    by_id = {r["id"]: r for r in reaches_in}
    for rid, names in hcfg.get("attach", {}).items():
        if rid not in by_id:
            raise ValueError(f"hydro.attach reach {rid!r} not in chain "
                             f"{list(by_id)}")
        for n in names:
            t = tribs.get(n, {})
            if t.get("flow_m3s", 0.0) > 0:
                by_id[rid].setdefault("lateral_sources", []).append(
                    {"id": n, **t, "status": "illustrative tributary"})
    baseflow_m3s = float(hcfg.get("boundary_m3s", baseline["boundary_m3s"]))
    boundary_m3s = baseflow_m3s + runoff_m3_s
    river_state, hydro_ledger = run_simulation(
        reaches_in, boundary_m3s,
        hcfg.get("boundary_c", baseline["boundary_c"]), air0, sim_s)
    if not river_state:
        raise ValueError("river chain is empty after simulation")
    exc = _find(river_state, "id", REACH_EXCELSIOR, "reach")
    bridge = next((r for r in river_state if r["id"] == REACH_BRIDGE),
                  river_state[-1])

    # --- M01b 1-D advection-dispersion replay ---
    replay_doc = run_replay_solver(cfg, baseline, world,
                                   hour0=hour0, weather=weather_frag,
                                   boundary_m3s=boundary_m3s)

    # --- M05b aquatic food web: replay heat -> insect prey -> trout refuge -> dipper intake, 14-day run ---
    from .aquatic_foodweb import run_foodweb as run_aquatic_foodweb
    from .aquatic_foodweb import thermal_landscape
    fcfg_foodweb = cfg.get("fish", {})
    foodweb_species = str(fcfg_foodweb.get("species", "brown_trout"))
    foodweb_cover = float(fcfg_foodweb.get("cover", 0.6))
    foodweb_cfg = cfg.get("foodweb", {})
    foodweb_days = float(foodweb_cfg.get("days", 14.0))
    foodweb_dt_days = float(foodweb_cfg.get("dt_days", 1.0))
    foodweb_ne_turnover_days = float(foodweb_cfg.get("ne_turnover_days", 2.0))
    foodweb_shear_disturb_pa = float(foodweb_cfg.get("shear_disturb_pa", 20.0))
    try:
        aquatic_foodweb = run_aquatic_foodweb(
            thermal_landscape(replay_doc),
            days=foodweb_days,
            dt_days=foodweb_dt_days,
            trout_species=foodweb_species,
            cover=foodweb_cover,
            ne_turnover_days=foodweb_ne_turnover_days,
            shear_disturb_pa=foodweb_shear_disturb_pa)
    except ValueError as exc:
        raise ValueError(f"aquatic foodweb failed: {exc}") from exc

    # --- M05 insects (legacy activity + compartments) ---
    icfg = cfg.get("insects", {})
    flowering = float(icfg.get("flowering_stage", 0.6))
    riparian = _find(patches1, "id", PATCH_RIPARIAN, "patch")
    sun0 = max(0.0, math.sin((hour0 - 6.0) * math.pi / 12.0))
    act0 = insect_activity(
        sun=sun0, air_c=air0, cloud=weather_frag.get("cloud", 0.16),
        moisture=riparian.get("moisture", 0.85),
        resource=riparian.get("insect_resource", 0.8),
        wind_mps=wind_mag, flowering=flowering)
    for p in patches1:
        if p["id"] == PATCH_RIPARIAN:
            p["insect_resource"] = step_resource(
                float(p.get("insect_resource", 0.8)),
                float(p.get("insect_recovery_per_hour", 0.06)),
                sun=sun0, moisture=float(p.get("moisture", 0.85)),
                consumed=0.0, dt_s=sim_s)
    wildlife1 = update_wildlife(baseline.get("wildlife", []),
                                {PATCH_RIPARIAN: act0})
    prey = dict(icfg.get("initial", {"Nt": 0.5, "Nb": 0.5, "Ne": 0.2}))
    prey_ledgers = []
    _t = 0.0
    while _t < sim_s - 1e-9:
        _h = min(60.0, sim_s - _t)
        prey, _pl = step_compartments(
            prey, {"sun": sun0, "air_c": air0,
                   "cloud": weather_frag.get("cloud", 0.16),
                   "moisture": riparian.get("moisture", 0.85),
                   "wind_mps": wind_mag, "flowering": flowering,
                   "water_c": float(bridge.get("temperature_c", 18.0)),
                   "disturbance": 0.0},
            dt_s=_h, consumers=DEFAULT_DIETS)
        prey_ledgers.append(_pl)
        _t += _h
    prey_ledger = {"emergence_total": round(sum(l["emergence"] for l in prey_ledgers), 6),
                   "consumed_total": {k: round(sum(l["consumed_by"].get(k, 0.0) for l in prey_ledgers), 6)
                                      for k in DEFAULT_DIETS},
                   "final": prey}
    rates = {k: v / max(1e-9, sim_s / 3600.0)
             for k, v in prey_ledger["consumed_total"].items()}
    # The dipper shares its refuge cell with the trout, so its intake comes
    # from the replay food web; the raven has no cell and keeps the
    # compartment ledger.
    fw_dipper = aquatic_foodweb.get("dipper", {})
    intake_basis = {k: "insect_compartments" for k in rates}
    if "intake_per_day" in fw_dipper:
        rates["dipper"] = float(fw_dipper["intake_per_day"]) / 24.0
        intake_basis["dipper"] = "replay_foodweb"
    wildlife1 = update_wildlife_from_intake(wildlife1, rates, intake_basis)

    # --- M06 fish ---
    fcfg = cfg.get("fish", {})
    firehole = _find(world["rivers"], "id", RIVER_FIREHOLE, "river")
    wildlife2 = update_trout(wildlife1, river_state, firehole["points"],
                             weights=fcfg.get("weights"),
                             food=float(fcfg.get("food", 0.7)),
                             cover=float(fcfg.get("cover", 0.6)))
    # The replay solver owns the spatial thermal field, so the food web picks
    # the refuge cell and the rendered trout holds there.
    from .fish import (build_chainage, place_trout_at_chainage,
                       reach_membership, reach_z_windows)
    fh_ordered = reach_z_windows(river_state)
    fh_membership = reach_membership(firehole["points"], fh_ordered)
    fh_chainage = build_chainage(firehole["points"])
    fh_features = replay_doc.get("replay", replay_doc).get("river_features", {})
    fh_offset = float(fh_features.get(RIVER_FIREHOLE, {}).get("start_s_m", 0.0))
    if fh_offset or fh_features.get(RIVER_FIREHOLE):
        wildlife2 = place_trout_at_chainage(
            wildlife2, river_state, firehole["points"],
            aquatic_foodweb["trout"], chainage_offset_m=fh_offset)
    trout_blockers = check_trout_clear_of_pools(wildlife2, firehole["points"],
                                                shells)

    # --- M07 grazers ---
    wildlife3 = update_grazers(wildlife2, patches1)
    grazer_blockers = check_grazer_routes(wildlife3, shells)
    b1 = _find(wildlife3, "id", BISON_DEMO, "wildlife")
    # Re-walk the bison's ACTUAL authored route through the eligibility
    # planner, segment by segment, so the corridor is verified rather than
    # demonstrated on a two-point demo. Bounds come from the route itself.
    _leg = [tuple(p) for p in b1["path_xz"]]
    _xs = [p[0] for p in _leg]
    _zs = [p[1] for p in _leg]
    _bounds = (min(_xs) - 20, min(_zs) - 20, max(_xs) + 20, max(_zs) + 20)
    _corr = []
    _corr_ok = True
    for _a, _b in zip(_leg, _leg[1:]):
        try:
            _corr += plan_path(_a, _b, _excluded, cell_m=4.0, bounds=_bounds)
        except ValueError:
            _corr_ok = False
            break
    from .grazers import route_length as _rlen
    corridor = {"from": list(_leg[0]), "to": list(_leg[-1]),
                "length_m": round(_rlen(_corr), 1) if _corr else 0.0,
                "waypoints": len(_corr),
                "planner_ok": _corr_ok,
                "note": ("planner re-walk on apron grid over the authored "
                         "route; records not altered")}

    # --- M12 overland flow (rainfall / infiltration / runoff field) ---
    olfg = cfg.get("overland", {})
    if olfg.get("enabled", False):
        overland_field = run_overland(
            world_root,
            rain_mm_h=float(olfg.get("rain_mm_h", scfg.get("precip_mm_d", 2.0))),
            soil=str(olfg.get("soil", "sandy_loam")),
            dt_s=float(olfg.get("dt_s", 60.0)),
            sim_s=float(olfg.get("sim_s", sim_s)),
            grid=int(olfg.get("grid", 256)),
            cell_m=float(olfg.get("cell_m", 8.0)))
    else:
        overland_field = {"schema": "yellowstone.overland_flow.v1",
                          "enabled": False,
                          "surface_runoff": {"nonzero_cells": 0,
                                             "max_depth_m": 0.0,
                                             "outflow_m3": 0.0,
                                             "carries_runoff_signal": False,
                                             "note": "module disabled; no field "
                                                     "computed"},
                          "provenance": "M12 overland flow disabled; set "
                                        "overland.enabled: true to compute it"}

    # --- merge variant ---
    variant = merge_fragments(baseline, river_state,
                              {k: v for k, v in weather_frag.items()
                               if k in ("night_air_c", "day_warming_c",
                                        "wind_xz_mps", "gust_mps",
                                        "humidity", "cloud")},
                              clock_hour=hour0)
    variant["patches"] = patches2
    variant["wildlife"] = wildlife3
    godot_errors = validate_for_godot(variant)

    timeline = {
        "t0": "frozen baseline + config",
        "fast_window_s": sim_s,
        "fast_processes": ["river transport", "patch biomass",
                           "insect compartments", "trout refuge",
                           "grazer/bird timing"],
        "season_days": snow_days,
        "slow_processes": ["snowpack", "soil water", "phenology"],
        "wildlife_reference": ("timings from t0+fast conditions; "
                               "snow updates moisture afterwards"),
    }
    return {"hour0": hour0, "air0": air0, "sim_s": sim_s,
            "clock_info": clock_info, "season": season,
            "weather_frag": weather_frag, "wind_trace": wind_trace,
              "met_bundle": met_bundle, "weather_provenance": weather_provenance,
             "river_state": river_state, "hydro_ledger": hydro_ledger,
             "replay_doc": replay_doc, "aquatic_foodweb": aquatic_foodweb,
             "shells": shells, "substrate_failures": substrate_failures,
            "patches1": patches1, "veg_ledger": veg_ledger,
            "proposals": proposals, "review_log": review_log,
            "prop_cfg": prop_cfg, "prop_violations": prop_violations,
            "act0": act0, "wind_mag": wind_mag, "flowering": flowering,
            "prey_ledger": prey_ledger, "wildlife1": wildlife1,
            "wildlife2": wildlife2, "trout_blockers": trout_blockers,
            "wildlife3": wildlife3, "grazer_blockers": grazer_blockers,
            "corridor": corridor, "patches2": patches2,
            "snow_ledger": snow_ledger, "scfg": scfg,
            "variant": variant, "godot_errors": godot_errors,
            "timeline": timeline, "tfns": tfns, "patches0": patches0,
            "overland_field": overland_field,
            "firehole_points": firehole["points"],
            "fh_membership": fh_membership, "fh_chainage": fh_chainage,
            "fh_chainage_offset_m": fh_offset,
            "catchment": catchment, "baseflow_m3s": baseflow_m3s,
            "boundary_m3s": boundary_m3s}


def render_all(res: dict, out: Path, deps: dict, world_root: Path) -> None:
    """Visualization + export: PNGs and JSON sidecars from simulated state."""
    from .hydro_thermal import plume_field, render_plume_png
    from .pool_crust import render_apron_mask, render_apron_tiles, render_ramp
    from .pool_crust import render_cross_section
    from .fish import render_refuge_map
    from .grazers import render_tracks as render_grazer_tracks
    from .snow_season import render_snow_map
    from .vegetation import render_suitability_png
    from .geochemistry import rules_doc as substrate_rules

    river_state, shells = res["river_state"], res["shells"]
    render_refuge_map(river_state, res["wildlife2"],
                      str(out / "refuge_map.png"),
                      river_points=res["firehole_points"], shells=shells)
    render_grazer_tracks(res["wildlife3"], str(out / "grazer_tracks.png"))
    render_snow_map(shells, 256, str(out / "snow_map.png"),
                    snow_m=max((p.get("snow_depth_m", 0.0)
                                for p in res["patches2"]), default=0.0))
    exc = _find(river_state, "id", REACH_EXCELSIOR, "reach")
    river_ref = next(
        (r for r in river_state if r["id"] == REACH_BRIDGE),
        river_state[-1] if river_state else None)
    if river_ref is None:
        raise ValueError("river_state is empty; cannot render plume")
    field = plume_field(nx=128, nz=128, hot_c=float(exc["temperature_c"]),
                        river_c=float(river_ref["temperature_c"]))
    render_plume_png(field, 128, 128, str(out / "plume_map.png"))

    shells_doc = write_sidecar(
        out / "pool_shells.json", {"pool_shells": shells},
        sources=[{"file": "yellowstone_midway/data/world.json",
                  "sha256": deps["world.json"]}],
        params={"recipe": "RECIPES per pool name; depths/colors illustrative",
                "outline": "mapped water polygons preserved"})
    render_apron_mask(shells, 256, str(out / "apron_mask.png"))
    render_apron_tiles(shells, str(out / "apron_tiles"))
    rampdir = out / "pool_ramps"
    rampdir.mkdir(exist_ok=True)
    for s in shells:
        render_ramp(s, str(rampdir / f"{s['id']}.png"))
    gp = _find(shells, "id", POOL_GRAND, "pool shell")
    render_cross_section(gp, str(out / "pool_cross_section.png"))
    write_sidecar(out / "substrate_rules.json", substrate_rules(),
                  sources=[{"id": "NPS_G4",
                            "url": "https://www.nps.gov/yell/learn/nature/hydrothermal-features.htm"}],
                  params={"midway": "siliceous only; travertine refused"})

    prop_cfg, patches0 = res["prop_cfg"], res["patches0"]
    cx0, cz0 = prop_cfg.get("center_xz", [-360, 260])
    _rr = float(prop_cfg.get("radius_m", 30))
    render_suitability_png(prop_cfg.get("guild", "lodgepole_pine"), 128,
                           str(out / "suitability_demo.png"),
                           bbox=(cx0 - _rr, cz0 - _rr, cx0 + _rr, cz0 + _rr),
                           terrain_fn=res["tfns"], patches=patches0,
                           shells=shells)
    return shells_doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PKG_ROOT / "configs" / "baseline.yaml"))
    ap.add_argument("--out", default=str(PKG_ROOT / "derived"))
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    import os
    if os.environ.get("YELLOWSTONE_WORLD"):
        cfg["world_root"] = os.environ["YELLOWSTONE_WORLD"]
    cfg.setdefault("world_root", str(default_world_root()))
    validate_config(cfg)
    baseline, world, deps, tfns = load_inputs(cfg)
    bid = build_id(cfg, deps)
    out = Path(args.out) / bid
    out.mkdir(parents=True, exist_ok=True)

    res = simulate_all(cfg, baseline, world, tfns)
    shells_doc = render_all(res, out, deps, Path(cfg["world_root"]))
    _write_variant_and_gate(cfg, baseline, deps, res, out, bid,
                            shells_doc is not None)
    return 0 if json.loads((out / "CHECKS.json").read_text())["passed"] else 2


def _package_version(name: str) -> str:
    """Installed distribution version or not_installed."""
    from importlib.metadata import PackageNotFoundError, version
    try:
        return version(name)
    except PackageNotFoundError:
        return "not_installed"


def _code_commit() -> tuple:
    """VCS head hash or (None, reason) outside a checkout."""
    import subprocess
    try:
        out = subprocess.run(
            ["git", "-C", str(PKG_ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10)
        if out.returncode == 0:
            return out.stdout.strip(), "git_head"
        return None, "no_vcs_checkout"
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None, "no_vcs_checkout"


def build_manifest(cfg: dict, deps: dict, res: dict, checks: dict,
                   bid: str, mode: str, prescribed: list,
                   out: Path) -> dict:
    """Spec 10.1 run manifest. Existing keys are preserved."""
    from .claims import CLAIMS
    import os
    import platform

    commit, commit_status = _code_commit()
    lock = PKG_ROOT / "requirements.txt"
    world_label = Path(cfg.get("world_root") or "yellowstone_midway").name
    hydro = cfg.get("hydro", {})
    replay_cfg = cfg.get("replay", {})
    fish_cfg = cfg.get("fish", {})
    snow_cfg = cfg.get("snow", {})
    replay_doc = res.get("replay_doc", {})
    foodweb_cfg = cfg.get("foodweb", {})
    parameter_set = {
        "hydro": {k: hydro.get(k) for k in
                  ("boundary_m3s", "boundary_c", "tributaries",
                   "attach")},
        "replay": replay_cfg,
        "fish": {k: fish_cfg.get(k) for k in
                 ("weights", "food", "cover", "species")},
        "snow": {k: snow_cfg.get(k) for k in ("days", "precip_mm_d")},
        "foodweb": {k: foodweb_cfg.get(k) for k in
                    ("days", "dt_days", "ne_turnover_days",
                     "shear_disturb_pa")},
    }
    artifacts = {}
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "BUILD.json":
            artifacts[str(path.relative_to(out))] = sha256_file(path)
    return {
        "schema": "yellowstone.build_manifest.v1",
        "run_id": bid,
        "build_id": bid,
        "contract_version": CONTRACT_VERSION,
        "world_id": WORLD_ID,
        "run_mode": mode,
        "prescribed_quantities": prescribed,
        "predicted_quantities": predicted_quantities(cfg),
        "hydrology": {
            "baseflow_m3s": res["baseflow_m3s"],
            "snow_runoff_m3_s": res["catchment"].get("runoff_m3_s", 0.0),
            "effective_boundary_m3s": res["boundary_m3s"],
            "catchment_enabled": res["catchment"]["enabled"],
        },
        "claim_ids": [c["claim_id"] for c in CLAIMS],
        "code_commit": commit,
        "code_commit_status": commit_status,
        "code_sha256": deps.get("code"),
        "environment_lock": {
            "file": "requirements.txt",
            "sha256": (sha256_file(lock) if lock.is_file() else None),
            "note": ("requirements.txt carries version ranges; "
                     "external_solver_versions holds the authoritative "
                     "installed versions for this run"),
        },
        "external_solver_versions": {
            "python": platform.python_version(),
            "numpy": _package_version("numpy"),
            "scipy": _package_version("scipy"),
            "matplotlib": _package_version("matplotlib"),
            "pandas": _package_version("pandas"),
            "pyyaml": _package_version("pyyaml"),
            "pillow": _package_version("Pillow"),
            "pint": _package_version("pint"),
            "salib": _package_version("SALib"),
            "xarray": _package_version("xarray"),
            "netcdf4": _package_version("netCDF4"),
        },
        "input_datasets": {
            "ecosystem": {"file": f"{world_label}/data/ecosystem.json",
                          "sha256": deps.get("ecosystem.json")},
            "world": {"file": f"{world_label}/data/world.json",
                      "sha256": deps.get("world.json")},
            "placements": {"file": f"{world_label}/data/placements.json",
                           "sha256": deps.get("placements.json")},
            "species_catalogue": {
                "file": f"{world_label}/data/species_catalogue.json",
                "sha256": deps.get("species_catalogue.json")},
            "terrain": {"file": f"{world_label}/data/terrain.f32",
                        "sha256": deps.get("terrain.f32")},
        },
        "configuration_hash": deps.get("config"),
        "parameter_set": parameter_set,
        "parameter_set_sha256": sha256_json(parameter_set),
        "random_streams": {
            "wind_seed": int(cfg.get("wind_seed", 11)),
            "proposal_seed": int(res.get("prop_cfg", {}).get("seed", 7)),
            "generator": "stdlib random.Random, no global numpy RNG "
                         "in build path",
        },
        "grid_and_time_step": {
            "replay_duration_s": replay_cfg.get("duration_s"),
            "replay_dt_s": replay_cfg.get("dt_s"),
            "replay_sample_s": replay_cfg.get("sample_s"),
            "replay_max_cell_m": replay_cfg.get("max_cell_m"),
            "replay_depth_m": replay_cfg.get("depth_m"),
            "n_cells": len(replay_doc.get("cells", [])),
            "n_frames": len(replay_doc.get("frames", [])),
            "hydro_simulate_seconds": hydro.get("simulate_seconds"),
        },
        "solver_tolerances": {
            "replay_heat_relative": 1e-9,
            "replay_water_relative": 1e-12,
            "hydro_heat_ledger": 1e-9,
            "snow_storage_mm": 0.05,
        },
        "restart": {
            "support": "split-run same process; fresh object under "
                       "constant forcing",
            "benchmark": "restart_equivalence",
        },
        "hardware": {
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            "parallelism": "single process",
        },
        "checks_passed": checks["passed"],
        "warnings_and_failures": list(checks["failures"]),
        "output_artifact_hashes": artifacts,
        "deps": deps,
        "timeline": res.get("timeline"),
        "metrics": copy.deepcopy(checks["metrics"]),
    }


def _atomic_json_write(path: Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_variant_and_gate(cfg, baseline, deps, res, out, bid, _ok):
    eco_doc = write_sidecar(
        out / "ecosystem.variant.json", {"ecosystem": res["variant"]},
        sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                  "sha256": deps["ecosystem.json"]}],
        params={"air_c_at_start_C": res["air0"],
                "simulate_seconds": res.get("sim_s", 0.0),
                "heat_ledger": res["hydro_ledger"],
                "timeline": res["timeline"],
                "note": "drop-in replacement for data/ecosystem.json"})
    _atomic_json_write(out / "ecosystem.godot.json", res["variant"])
    _atomic_json_write(out / "river_state.json", res["river_state"])
    write_sidecar(out / "river_replay.json",
                  {"replay": res["replay_doc"]},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"method": "1-D finite-volume advection-dispersion",
                          "energy_budget": res["replay_doc"].get("model", {}).get("surface_flux", "newton_lumped"),
                          "status": "illustrative, not calibrated"})
    _atomic_json_write(out / "weather.json", {"weather": res["weather_frag"], "wind_trace_60s": res["wind_trace"]})
    if res["met_bundle"]:
        _atomic_json_write(out / "met.json", res["met_bundle"])
    write_sidecar(out / "overland_flow.json", res["overland_field"],
                  sources=[{"file": "yellowstone_midway/data/terrain.f32",
                            "sha256": deps["terrain.f32"]}],
                  params={"method": "hydrosim local-inertial shallow water, "
                          "block-mean of terrain.f32"},
                  status=res["overland_field"].get("status",
                                                   "illustrative_not_calibrated"))
    write_sidecar(out / "catchment_runoff.json", res["catchment"],
                  sources=[{"file": "configs/baseline.yaml",
                            "sha256": deps.get("config")}],
                  params={"method": "snow ledger runoff depth scaled to the "
                          "configured catchment area",
                          "baseflow_m3s": res["baseflow_m3s"],
                          "effective_boundary_m3s": res["boundary_m3s"]},
                  status=res["catchment"]["status"])
    _write_fragment_sidecars(cfg, baseline, deps, res, out)

    from .validation.checks import run_all
    from .aquatic_foodweb import thermal_landscape
    mode = normalize_run_mode(cfg.get("run_mode"))
    prescribed = prescribed_quantities(cfg)
    checks = run_all(river_state=res["river_state"], ledger=res["hydro_ledger"],
                     ecosystem_doc=eco_doc, build_id_a=bid,
                     run_mode=mode, prescribed=prescribed,
                     validated_quantities=(),
                      replay_doc=res["replay_doc"],
                      landscape=thermal_landscape(res["replay_doc"]),
                      membership=res["fh_membership"],
                      chainage=res["fh_chainage"],
                      chainage_offset_m=res["fh_chainage_offset_m"])
    checks["metrics"]["validation_claims"] = []
    if res["godot_errors"]:
        checks["passed"] = False
        checks["failures"] += ["godot: " + e for e in res["godot_errors"]]
    if res["prop_violations"]:
        checks["passed"] = False
        checks["failures"] += [f"apron: proposal inside exclusion: {v}"
                               for v in res["prop_violations"][:5]]
    if res["trout_blockers"]:
        checks["passed"] = False
        checks["failures"] += [f"refuge: trout route inside apron: {v}"
                               for v in res["trout_blockers"][:5]]
    if res["substrate_failures"]:
        checks["passed"] = False
        checks["failures"] += [f"substrate: {v}" for v in res["substrate_failures"]]
    if not (0.0 <= res["act0"] <= 1.0):
        checks["passed"] = False
        checks["failures"] += [f"insects: activity {res['act0']} out of [0,1]"]
    for p in res["patches1"]:
        if not (0.0 <= float(p["biomass"]) <= float(p.get("capacity", 1.0))):
            checks["passed"] = False
            checks["failures"] += [f"patch {p['id']}: biomass out of bounds"]
    if res["grazer_blockers"]:
        checks["passed"] = False
        checks["failures"] += [f"grazer: route violates habitat: {v}"
                               for v in res["grazer_blockers"][:5]]
    for p in res["patches2"]:
        if float(p.get("snow_mm", 0.0)) < 0:
            checks["passed"] = False
            checks["failures"] += [f"snow: negative storage {p['id']}"]
    snow_ledger = res["snow_ledger"]
    if abs(snow_ledger.get("storage_residual_mm", float("inf"))) > 0.05:
        checks["passed"] = False
        checks["failures"] += [
            f"snow: storage residual {snow_ledger.get('storage_residual_mm')} mm"]
    checks["metrics"]["n_proposals"] = len(res["proposals"])
    checks["metrics"]["n_shells"] = len(res["shells"])
    rb = res["replay_doc"].get("final_budget", {})
    checks["metrics"]["replay_heat_budget_error"] = rb.get("heat_residual_j", float("inf"))
    checks["metrics"]["replay_water_budget_error_m3"] = rb.get("water_residual_m3", float("inf"))
    checks["metrics"]["replay_n_cells"] = len(res["replay_doc"].get("cells", []))
    checks["metrics"]["replay_n_frames"] = len(res["replay_doc"].get("frames", []))
    hyd_sum = res["replay_doc"].get("hydraulics_summary", {})
    checks["metrics"]["replay_travel_time_s"] = hyd_sum.get("total_travel_time_s")
    checks["metrics"]["replay_manning_median"] = hyd_sum.get(
        "manning_consistency_ratio_median")
    checks["metrics"]["replay_flat_grade_cells"] = hyd_sum.get(
        "n_flat_or_adverse_grade_cells")
    sl = res["aquatic_foodweb"]["trout"]
    checks["metrics"]["foodweb_refuge_s_m"] = sl.get("s_m")
    checks["metrics"]["foodweb_refuge_temp_c"] = sl.get("temperature_c")
    checks["metrics"]["foodweb_refuge_U"] = sl.get("U")
    checks["metrics"]["foodweb_emergence_total"] = res["aquatic_foodweb"][
        "prey_totals"].get("emergence")
    checks["metrics"]["foodweb_dipper_per_day"] = res["aquatic_foodweb"][
        "dipper"].get("intake_per_day")
    if not res["replay_doc"].get("numerical_checks", {}).get("passed", False):
        checks["passed"] = False
        checks["failures"].append("replay: budget closure checks failed")
    from collections import Counter
    checks["metrics"]["phenology"] = dict(Counter(
        p.get("phenology", "?") for p in res["patches2"]))
    checks["metrics"]["substrate_ok"] = not res["substrate_failures"]
    from .replay.identifiability import run_diagnostics
    diagnostics = run_diagnostics()
    checks["metrics"]["identifiability_rank"] = diagnostics[
        "conditioning"]["rank"]
    checks["metrics"]["identifiability_max_cost"] = diagnostics[
        "multistart"]["max_cost"]
    checks["metrics"]["structural_surface_gap_c"] = diagnostics[
        "structural_surface"]["max_abs_gap_c"]
    _atomic_json_write(out / "CHECKS.json", checks)
    from .claims import CLAIMS
    from .coupling import EXCHANGES
    from .equations import COMPONENTS
    from .param_registry import PARAMS
    from .replay.benchmarks import run_all_benchmarks
    write_sidecar(out / "numerics_benchmarks.json",
                  run_all_benchmarks(),
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode})
    write_sidecar(out / "identifiability.json",
                  diagnostics,
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode})
    write_sidecar(out / "coupling.json",
                  {"schema": "yellowstone.coupling.v1",
                   "exchanges": EXCHANGES},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode})
    write_sidecar(out / "claims.json",
                  {"schema": "yellowstone.claims.v1", "claims": CLAIMS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode})
    write_sidecar(out / "param_registry.json",
                  {"schema": "yellowstone.param_registry.v1",
                   "params": PARAMS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode})
    write_sidecar(out / "equations.json",
                  {"schema": "yellowstone.equations.v1",
                   "components": COMPONENTS},
                  sources=[{"id": "code", "sha256": deps["code"]}],
                  params={"build_id": bid, "run_mode": mode})
    (out / "BUILD.json").write_text(json.dumps(
        build_manifest(cfg, deps, res, checks, bid, mode, prescribed,
                       out), indent=2))
    print(f"build {bid} passed={checks['passed']} → {out}")
    for f in checks["failures"]:
        print("FAIL:", f)


def _write_fragment_sidecars(cfg, baseline, deps, res, out):
    from .fish import THERMAL_SPECIES
    from .insects_birds import foraging_state
    world_root = Path(cfg.get("world_root") or default_world_root())
    write_sidecar(out / "patch_state.json", {"patches": res["patches1"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"veg_ledger": res["veg_ledger"],
                          "hours": res.get("sim_s", 0.0) / 3600.0})
    write_sidecar(out / "planting_proposal.json",
                  {"proposals": res["proposals"],
                   "review_log": res["review_log"],
                   "review": "merge reviewed rows into placement_overrides.json::{add}; never overwrite placements.json"},
                  sources=[{"file": "yellowstone_midway/data/placements.json",
                            "sha256": deps["placements.json"]}],
                  params={"guild": res["prop_cfg"].get("guild"),
                          "seed": res["prop_cfg"].get("seed"),
                          "n_accepted": len(res["proposals"]),
                          "n_rejected": sum(1 for r in res["review_log"]
                                            if r["decision"] == "reject")})
    write_sidecar(out / "insect_bird.json",
                  {"activity": res["act0"],
                   "state": foraging_state(res["act0"]),
                   "wind_mps": res["wind_mag"],
                   "flowering_stage": res["flowering"],
                   "compartments": res["prey_ledger"],
                   "wildlife": [r for r in res["wildlife1"]
                                if r.get("id") in ("dipper_01", "raven_01")]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"threshold": 0.035,
                          "note": "bird cadence from Holling intake + legacy activity gate"})
    write_sidecar(out / "fish.json",
                   {"wildlife": [r for r in res["wildlife2"] if "trout" in r["id"]],
                    "hydraulics": ("V=Q/A_trap trapezoidal diagnostic per "
                                   "replay cell (solver volumes still "
                                   "rectangular); Manning/Froude/Fischer + "
                                   "travel times in river_replay.json "
                                   "hydraulics_summary; illustrative, not "
                                   "calibrated"),
                    "thermal_species": {k: {
                        "t_opt_lo_c": v["t_opt_lo_c"],
                        "t_opt_hi_c": v["t_opt_hi_c"],
                        "t_feed_zero_c": v["t_feed_zero_c"],
                        "t_refuge_c": v["t_refuge_c"],
                        "t_uilt_c": v["t_uilt_c"],
                        "status": v["status"]} for k, v in
                        THERMAL_SPECIES.items()}},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"weights": cfg.get("fish", {}).get("weights", "defaults"),
                           "activity": "clamp((26-T)/8) visibility only",
                           "refuge": "chainage-window argmax suitability"})
    write_sidecar(out / "aquatic_foodweb.json",
                  {"foodweb": res["aquatic_foodweb"]},
                  sources=[{"file": "yellowstone_midway/data/world.json",
                            "sha256": deps["world.json"]}],
                  params={"method": "14-day insect/trout/dipper food web on "
                                    "replay time-mean thermal landscape",
                          "trout_species": res["aquatic_foodweb"].get(
                              "trout_species"),
                          "status": "illustrative, not calibrated"})
    write_sidecar(out / "grazer.json",
                  {"wildlife": [r for r in res["wildlife3"]
                                if r.get("kind") in ("bison", "elk")],
                   "planner_corridor": res["corridor"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"causal_claim": "none_single",
                          "note": "sparse authored loops; not abundance"})
    write_sidecar(out / "season.json",
                  {"patches": [{k: p[k] for k in
                                ("id", "snow_mm", "snow_depth_m", "moisture",
                                 "phenology", "pheno_stress", "gdd") if k in p}
                               for p in res["patches2"]],
                   "season": res["season"],
                   "season_source": res["clock_info"]["season_source"],
                   "clock_hour": res["clock_info"]["clock_hour"],
                   "clock_source": res["clock_info"]["clock_source"],
                   "as_of_local_date": res["clock_info"]["as_of_local_date"],
                   "date_source": res["clock_info"]["date_source"],
                   "ledger": res["snow_ledger"]},
                  sources=[{"file": "yellowstone_midway/data/ecosystem.json",
                            "sha256": deps["ecosystem.json"]}],
                  params={"method": "degree-day + soil bucket, verified ledger",
                          "geometry": "frozen; surfaces/phenology only"})


if __name__ == "__main__":
    raise SystemExit(main())
