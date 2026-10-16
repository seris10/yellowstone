"""Physical-time river and ecology engine with checkpointed lookahead frames."""
from __future__ import annotations

import copy
from bisect import bisect_right
import datetime as dt
import json
import math
from pathlib import Path
import queue
import threading
import time
import uuid

from yellowstone_python.common.checks import finite, fraction, positive
from yellowstone_python.common.io import load_json, write_json_atomic
from yellowstone_python.common.site import SITE_LAT_DEG, SITE_LON_DEG, SITE_ELEVATION_M
from yellowstone_python.common.mammal_forcing import environmental_forcing, apply_consumption
from yellowstone_python.river.river_transport import River, Series, SurfaceBudget, river_from_config, series_dict
from yellowstone_python.river.river_world import energy_met_series
from yellowstone_python.river.solute_transport import transport_from_mapped_replay, SOLUTE_KEYS, BoundaryConcentrations, load_hydrothermal_solutes
from yellowstone_python.river.obs_model import UPSTREAM_GAUGE, DOWNSTREAM_GAUGE
from yellowstone_python.aquatic.aquatic_foodweb import foodweb_state, step_foodweb, build_tributary_cell, TRIBUTARY_CANDIDATES
from yellowstone_python.aquatic.fish import suitability_with_stressors, thermal_performance
from yellowstone_python.registry.run_mode import normalize_run_mode
from yellowstone_python.study_mode import PRESETS, _validate, control_schema
from yellowstone_python import insects_birds
import yellowstone_python.atmosphere.microclimate as microclimate
import yellowstone_python.aquatic.river_oxygen as river_oxygen
import yellowstone_python.aquatic.periphyton as periphyton
import yellowstone_python.land.snow_season as snow_season
import yellowstone_python.land.vegetation as vegetation
import yellowstone_python.thermal_features.ground_heat as ground_heat

from yellowstone_python.pipeline import stage_contracts
from yellowstone_python.pipeline.dependencies import CONTROL_DEPENDENCIES as DEPENDENCIES

DOMAIN_OUTPUTS = {"display": "weather_frag", "weather": "weather_frag", "solar": "weather_frag", "river": "replay_doc",
                  "hydraulics": "replay_doc", "insects": "act0", "snow": "snow_ledger",
                  "soil": "soil_t_by_patch", "runoff": "catchment", "oxygen": "oxygen_doc",
                  "periphyton": "periphyton_doc", "foodweb": "aquatic_foodweb",
                  "solutes": "solute_doc", "vegetation": "patches1", "mammals": "mammal_doc"}


def live_stage_contracts():
    """Resolve live control domains to the build stages that produce their state."""
    contracts = stage_contracts()
    producers = {name: contract["name"] for contract in contracts for name in contract["writes"]}
    required = {domain for domains in DEPENDENCIES.values() for domain in domains}
    missing = [domain for domain in required if DOMAIN_OUTPUTS.get(domain) not in producers]
    if missing:
        raise ValueError(f"live domains lack a build stage producer: {sorted(missing)}")
    return {"stages": contracts, "domains": {domain: producers[DOMAIN_OUTPUTS[domain]]
                                              for domain in sorted(required)}}


STATIC_COMPONENTS = ("terrain", "census", "outflow_network", "mat_rasters", "pool_shells",
                     "geochemistry", "calibration")
MODEL_COMPONENTS = {
    "temperature_c": {"module": "yellowstone_python.river.river_transport", "equation_component": "1-D advection-dispersion replay", "provenance": "derived", "input_status": "prescribed forcing and estimated geometry"},
    "depth_m": {"module": "yellowstone_python.river.river_transport", "equation_component": "1-D advection-dispersion replay", "provenance": "authored_estimate", "input_status": "fixed DEM-derived cell volume divided by surface area"},
    "velocity_mps": {"module": "yellowstone_python.river.river_transport", "equation_component": "1-D advection-dispersion replay", "provenance": "derived", "input_status": "prescribed face discharge divided by estimated cross-section"},
    "oxygen_mg_l": {"module": "yellowstone_python.aquatic.river_oxygen", "equation_component": "river dissolved oxygen", "provenance": "derived", "input_status": "authored initial saturation and transfer coefficients"},
    "shading_factor": {"module": "yellowstone_python.aquatic.river_shading", "equation_component": "river shading", "provenance": "authored", "input_status": "scenario shortwave multiplier"},
    "snow": {"module": "yellowstone_python.land.snow_season", "equation_component": "snow and soil water", "provenance": "derived", "input_status": "weather forcing with authored degree-day and soil-bucket coefficients"},
    "snow_mm": {"module": "yellowstone_python.land.snow_season", "equation_component": "snow and soil water", "provenance": "derived", "input_status": "weather forcing with authored degree-day coefficients"},
    "soil_water_mm": {"module": "yellowstone_python.land.snow_season", "equation_component": "snow and soil water", "provenance": "derived", "input_status": "authored soil-bucket capacity, drainage and evaporation"},
    "runoff_mm": {"module": "yellowstone_python.service.live.engine", "equation_component": "snow and soil water", "provenance": "derived", "input_status": "bucket overflow plus drainage; catchment area defaults to zero"},
    "soil_temperature_c": {"module": "yellowstone_python.thermal_features.ground_heat", "equation_component": "ground heat flux and soil temperature", "provenance": "derived", "input_status": "published spatial ground heat with authored conductivity and fixed sampling depth"},
    "biomass": {"module": "yellowstone_python.land.vegetation", "equation_component": "patch biomass", "provenance": "derived", "input_status": "published initial biomass with authored growth and grazing coefficients"},
    "vegetation": {"module": "yellowstone_python.land.vegetation", "equation_component": "patch biomass", "provenance": "derived", "input_status": "published initial biomass with authored growth and grazing coefficients"},
    "periphyton": {"module": "yellowstone_python.aquatic.periphyton", "equation_component": "periphyton biomass", "provenance": "derived", "input_status": "authored initial biomass and growth coefficients"},
    "solutes": {"module": "yellowstone_python.river.solute_transport", "equation_component": "replay solute transport", "provenance": "derived", "input_status": "frozen source chemistry; authored zero baseline for unknown upstream solutes"},
    "trout": {"module": "yellowstone_python.aquatic.fish", "equation_component": "trout suitability and refuge", "provenance": "derived", "input_status": "thermal anchors and authored habitat weights"},
    "trout_suitability_u": {"module": "yellowstone_python.aquatic.fish", "equation_component": "trout suitability and refuge", "provenance": "derived", "input_status": "chronic exposure temperature with authored habitat weights"},
    "refuge_drive": {"module": "yellowstone_python.aquatic.fish", "equation_component": "trout suitability and refuge", "provenance": "derived", "input_status": "species-specific instantaneous temperature performance"},
    "feeding": {"module": "yellowstone_python.aquatic.fish", "equation_component": "trout suitability and refuge", "provenance": "derived", "input_status": "species-specific instantaneous temperature performance"},
    "foodweb": {"module": "yellowstone_python.aquatic.aquatic_foodweb", "equation_component": "insect compartments", "provenance": "derived", "input_status": "authored initial prey stocks and transfer rates"},
    "mammals": {"module": "yellowstone_python.land.mammals", "equation_component": "mammal guild ecology", "provenance": "authored", "input_status": "primary-source occurrence catalogue; authored populations, resource demand and encounter probabilities; local abundance unknown"},
    "weather": {"module": "yellowstone_python.atmosphere.microclimate", "equation_component": "surface heat exchange", "provenance": "authored_or_observed", "input_status": "scenario weather or labeled frozen meteorological series"},
}

for _component in MODEL_COMPONENTS.values():
    _component["component_id"] = _component["equation_component"]
    _component["source_file"] = _component["module"].replace(".", "/") + ".py"


def _set_config(config: dict, key: str, value) -> None:
    node = config
    parts = key.split(".")
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = copy.deepcopy(value)



def replay_config(document: dict) -> dict:
    """Recover the solver config from a published mapped replay."""
    if "solver_config" in document:
        return copy.deepcopy(document["solver_config"])
    fields = ("id", "length_m", "width_m", "volume_m3", "initial_c", "dispersion_m2_s",
              "exchange_w_m2_k", "geometry_status")
    forcing = document["forcing"]
    config = {"cells": [{key: cell[key] for key in fields if key in cell}
                        for cell in document["cells"]],
              "boundary_m3_s": forcing["boundary_m3_s"], "boundary_c": forcing["boundary_c"],
              "air_c": forcing["air_c"], "sources": forcing.get("sources", []),
              "net_heat_flux_w_m2": forcing.get("additional_heat_flux_w_m2", 0.0),
              "cell_heat_w": forcing.get("cell_heat_w", {}), "initialize_steady": False}
    model = document.get("model", {})
    settings = model.get("surface_solver", {})
    for published, solver in (("max_iterations", "max_surface_iterations"),
                              ("temperature_tolerance_c", "surface_tolerance_c"),
                              ("relaxation", "surface_relaxation")):
        if published in settings:
            config[solver] = settings[published]
    if "rho_cp_j_m3_k" in model:
        config["rho_cp_j_m3_k"] = model["rho_cp_j_m3_k"]
    if forcing.get("surface_budget") is not None:
        config["surface_budget"] = forcing["surface_budget"]
    return config


class LiveEngine:
    """Compute and publish checkpointed frames from a worker-owned model state."""

    def __init__(self, river: River, config: dict | None = None, *, cells: list | None = None,
                 geometry: dict | None = None, build_id: str = "synthetic", claim_ids=(),
                 epoch_unix: float = 1782064800.0, horizon_s: float = 600.0,
                 frame_interval_s: float = 60.0, max_dt_s: float = 2.0,
                 time_scale: float = 1.0, log_dir: Path | None = None,
                 observation_bundle: dict | None = None, calibration_params: dict | None = None,
                 start_worker: bool = False):
        self.river = river
        self._cell_index = {cell.id: i for i, cell in enumerate(river.cells)}
        self.config = copy.deepcopy({key: value for key, value in (config or {}).items()
                                     if key != "python_series"})
        self.config["run_mode"] = normalize_run_mode(self.config.get("run_mode", "scenario"))
        weather_config = self.config.setdefault("weather", {})
        for key, value in {"night_air_c": 7., "day_warming_c": 15., "lag_hours": 3.,
                           "humidity": .45, "cloud": .16, "wind_xz_mps": [1.8, .6],
                           "gust_mps": .45, "precip_mm_h": 0.}.items():
            weather_config.setdefault(key, value)
        wx, wz = weather_config["wind_xz_mps"]
        weather_config.setdefault("wind_speed_mps", math.hypot(wx, wz))
        weather_config.setdefault("wind_direction_deg", microclimate.wind_from_direction((wx, wz)))
        self.config.setdefault("fish", {}).setdefault("cover", .6)
        self.config["fish"].setdefault("food", .5)
        self.config.setdefault("hydro", {}).setdefault("boundary_m3s", river._boundary_q_series.at(0))
        self.config["hydro"].setdefault("boundary_c", river.boundary_c.at(0))
        source = next((source for source in river.sources if "excelsior" in source.id), None)
        thermal_config = self.config.setdefault("thermal", {})
        thermal_config.setdefault("excelsior_enabled", source is not None and source.flow_m3_s.at(river.time_s) > 0.)
        thermal_config.setdefault("excelsior_c", source.temperature_c.at(river.time_s) if source is not None else 62.)
        self.config.setdefault("aquatic", {"tributary_pockets": False, "pocket_temperature_c": 11.0})
        self.config.setdefault("grazing", {"bison_count": 0})
        self.geometry = copy.deepcopy({key: value for key, value in (geometry or {}).items()
            if key in ("river_features", "legacy_queries", "pool_shells", "ground_heat_parameters")})
        self._ground_shells = self.geometry.get("pool_shells", [])
        self._ground_heat_parameters = self.geometry.get("ground_heat_parameters", {})
        self._patch_heat_flux = {patch["id"]: ground_heat.heat_flux_at(*patch.get("center_xz", [0., 0.]),
            self._ground_shells, **self._ground_heat_parameters) for patch in self.config.get("patches", [])}
        default_cells = []
        chainage = 0.
        for cell in river.cells:
            center = chainage + .5 * cell.length_m
            default_cells.append({"id": cell.id, "center_s_m": center,
                "depth_m": cell.volume_m3 / cell.surface_area_m2, "position_xyz": [0., 0., center]})
            chainage += cell.length_m
        self.cells = copy.deepcopy(cells if cells is not None else default_cells)
        self.build_id, self.claim_ids = build_id, list(claim_ids)
        self._stage_contracts = live_stage_contracts()
        self.session_id = uuid.uuid4().hex
        self.epoch_origin = finite("epoch_unix", epoch_unix)
        self.horizon_s = positive("horizon_s", horizon_s)
        self.frame_interval_s = positive("frame_interval_s", frame_interval_s)
        self.max_dt_s = positive("max_dt_s", max_dt_s)
        self.time_scale = min(600., positive("time_scale", time_scale))
        self._compute_rate_sps = None
        self._compute_samples = []
        self._max_dt_samples = []
        self._max_dt_capacity_sps = None
        self.paused = False
        self.player_t_s = river.time_s
        self.revision = 0
        self.truncate_after_t_s = None
        self.dirty_stages = []
        self.timings = {}
        self.worker_error = None
        self.session_events = []
        self.log_path = None if log_dir is None else Path(log_dir) / f"{self.session_id}.jsonl"
        self.observation_bundle = observation_bundle
        self.calibration_params = copy.deepcopy(calibration_params or {
            "volume_m3": 300000., "area_m2": 120000., "q_lat": .26, "t_lat": 62., "c_mult": 1.,
            "status": "authored_effective_geometry"})
        self.measured_reference = None
        self.observation_samples = []
        self._baseline = None
        self._integration_segments = []
        self._forcing_catalog = {}
        self._lock = threading.RLock()
        self._commands = queue.Queue()
        self._stop = threading.Event()
        self._worker = None
        self._last_wall = time.monotonic()
        self._clock_started = False
        self._clock_debt_s = 0.
        self.display_hour = None
        self._weather_cache = {}
        self._source_base_flows = {source.id: source.flow_m3_s.at(river.time_s) for source in river.sources}
        self.food_settings = {"delta_u_switch": .1, "movement_cost_per_m": .00001,
                              "thermal_curve_form": self.config.get("fish", {}).get("thermal_curve_form", "piecewise_linear")}
        live_settings = self.config.setdefault("live", {})
        live_settings.setdefault("weather_policy", "scenario_weather" if (config or {}).get("weather") else "preserve_published")
        live_settings.setdefault("solute_dt_s", 10.)
        live_settings.setdefault("aquatic_interval_s", 60.)
        self._periphyton_params = periphyton.PeriphytonParams()
        self.ecology = {"last_aquatic_t_s": river.time_s, "initial_trout": None,
            "exposure_c": list(river.temperature_c), "oxygen_mg_l": [
            river_oxygen.saturation_mg_l(t) for t in river.temperature_c],
            "periphyton": [50.] * len(river.cells), "insects": {"Nt": .5, "Nb": .5, "Ne": .2},
            "snow_mm": 0., "soil_mm": 60., "soil_temperature_c": 7.,
            "patches": copy.deepcopy(self.config.get("patches", [])),
            "last_foodweb_t_s": river.time_s, "last_land_t_s": river.time_s,
            "foodweb_report": None, "refuge_by_species": {}, "species_selection_t_s": {}}
        from dataclasses import asdict
        solute_data = load_hydrothermal_solutes()
        boundary = solute_data["features"]["firehole_upstream_boundary"]
        explicit_boundary = self.config.get("solutes", {}).get("boundary", {})
        self.solute_boundary_provenance = {key: boundary.get(key, {}).get("status", "unknown")
                                           for key in SOLUTE_KEYS}
        values = {}
        for key in SOLUTE_KEYS:
            value = explicit_boundary.get(key, boundary.get(key, {}).get("value"))
            if value is None:
                value = 0.
                self.solute_boundary_provenance[key] = "authored_zero_baseline_unknown_observation"
            values[key] = value
        self.solutes = transport_from_mapped_replay({"cells": [asdict(cell) for cell in self.river.cells],
            "forcing": {"boundary_m3_s": self.river._boundary_q_series,
                        "sources": [{"id": source.id, "cell_id": source.cell_id,
                                     "flow_m3_s": source.flow_m3_s} for source in self.river.sources]}},
            data_document=solute_data, boundary_concentrations=BoundaryConcentrations(**values))
        self._update_land_temperature(self._weather(river.time_s)["air_c"])
        self.ecology["snow_mm"] = self._patch_mean("snow_mm", 0.)
        self.ecology["soil_mm"] = self._patch_mean("soil_mm", 60.)
        self.ecology["foodweb"] = foodweb_state(self._landscape())
        self.ecology["last_mammal_t_s"] = river.time_s
        settings = self.config.get("mammals") or {}
        if not isinstance(settings, dict):
            raise ValueError("mammals must be a mapping")
        if "enabled" in settings and not isinstance(settings["enabled"], bool):
            raise ValueError("mammals.enabled must be boolean")
        if settings.get("enabled", False):
            from yellowstone_python.land.mammals import MammalEcology
            self.ecology["mammal_model"] = MammalEcology(
                self.ecology["patches"], actors=self.config.get("wildlife", []),
                seed=settings.get("seed", 54173))
            self._update_mammals(0.0)
        self._frames = [self._frame()]
        self._checkpoints = {river.time_s: self._checkpoint()}
        self._initial_checkpoint = self._checkpoint()
        from yellowstone_python.common.provenance import sha256_json
        self.initial_state_id = sha256_json({"river": self.solver_config(),
                                             "patches": self.ecology["patches"]})
        self._log("session_start", {"config": self.config, "solver_config": self.solver_config(),
                                    "epoch_unix": self.epoch_origin, "build_id": build_id,
                                    "max_dt_s": self.max_dt_s, "frame_interval_s": self.frame_interval_s})
        self._publish_snapshot()
        if start_worker:
            self.start()

    @classmethod
    def from_build(cls, path: Path, **kwargs):
        """Resume the published river strategy, initial state and forcing."""
        path = Path(path)
        manifest = load_json(path / "BUILD.json")
        replay_doc = load_json(path / "river_replay.json")
        document = replay_doc.get("replay", replay_doc)
        cfg = load_json(path / "ecosystem.godot.json")
        weather_path = path / "weather.json"
        if weather_path.exists():
            built_weather = load_json(weather_path)
            cfg["weather"] = built_weather.get("weather", cfg.get("weather", {}))
        document = copy.deepcopy(document)
        shells_path = path / "pool_shells.json"
        if shells_path.exists():
            document["pool_shells"] = load_json(shells_path).get("pool_shells", [])
        ground_path = path / "ground_heat.json"
        if ground_path.exists():
            parameters = load_json(ground_path).get("parameters", {})
            document["ground_heat_parameters"] = {key: parameters[key] for key in
                ("background_w_m2", "apron_w_m2", "pool_w_m2") if key in parameters}
        solver = replay_config(document)
        epoch = document["simulation_time"]["start_epoch_unix"]
        cfg["simulation_start_epoch_unix"] = epoch
        cfg["replay"] = copy.deepcopy(manifest.get("config", {}).get("replay", {}))
        cfg["live"] = {**manifest.get("live", {}), "weather_policy": "preserve_published"}
        cfg["start_operation"] = "resume_published"
        cfg["published_weather"] = {key: copy.deepcopy(document[key]) for key in
            ("forcing", "weather_trace", "clock_hour0") if key in document}
        cfg["land_thermal_flux_mm_d_by_patch"] = manifest.get("land_thermal_flux_mm_d_by_patch", {})
        cfg["model_variant_id"] = manifest.get("model_variant_id")
        cfg["scenario_id"] = manifest.get("scenario_id", manifest["build_id"])
        obs_path = path.parent / "firehole_obs.json"
        obs = load_json(obs_path) if obs_path.exists() else None
        live_cfg = manifest.get("live", {})
        calibration_path = path.parent / "reach_polished_fit_v300k.json"
        params = None
        if calibration_path.exists():
            fit = load_json(calibration_path)
            params = {**fit["effective_geometry"],
                      **{key: fit["polished"][key] for key in ("q_lat", "t_lat", "c_mult")},
                      "status": fit["status"], "source": str(calibration_path)}
        return cls(river_from_config(solver), cfg, cells=document["cells"], geometry=document,
                   build_id=manifest["build_id"], claim_ids=manifest.get("claim_ids", []),
                   epoch_unix=epoch, log_dir=path.parent / "live", observation_bundle=obs,
                   calibration_params=params,
                   frame_interval_s=kwargs.pop("frame_interval_s", cfg["replay"].get("sample_s", 60.)),
                   max_dt_s=kwargs.pop("max_dt_s", live_cfg.get("max_dt_s", 2.0)), **kwargs)

    def _forcing_config(self, start_s=None, end_s=None):
        from dataclasses import asdict
        river = self.river
        def schedule(series):
            if start_s is None:
                return series_dict(series)
            first = bisect_right(series.times_s, start_s)
            stop = bisect_right(series.times_s, end_s)
            return {"times_s": [0., *series.times_s[first:stop]],
                    "values": [series.at(start_s), *series.values[first:stop]]}
        config = {"boundary_m3_s": schedule(river._boundary_q_series),
                  "boundary_c": schedule(river.boundary_c), "air_c": schedule(river.air_c),
                  "net_heat_flux_w_m2": schedule(river.net_heat_flux),
                  "sources": [{"id": source.id, "cell_id": source.cell_id,
                               "flow_m3_s": schedule(source.flow_m3_s),
                               "temperature_c": schedule(source.temperature_c), "status": source.status}
                              for source in river.sources],
                  "cell_heat_w": {cell.id: schedule(forcing) for cell, forcing
                                  in zip(river.cells, river._cell_heat) if forcing is not None},
                  "shortwave_multiplier": dict(zip([cell.id for cell in river.cells],
                                                   river._cell_shortwave_multiplier)),
                  "surface_relaxation": river.surface_relaxation}
        if river.surface_budget is not None:
            budget = river.surface_budget
            config["surface_budget"] = {name: schedule(getattr(budget, name)) for name in
                ("rh", "wind_mps", "shortwave_w_m2", "cloud")}
            config["surface_budget"]["params"] = asdict(budget.params)
        return config

    def solver_config(self) -> dict:
        """Return a serializable forcing and initial-state configuration."""
        from dataclasses import asdict
        return {"cells": [asdict(cell) for cell in self.river.cells],
                "hyporheic_zones": {cell.id: asdict(zone) for cell, zone in
                    zip(self.river.cells, self.river._hyporheic_zones) if zone is not None},
                **self._forcing_config()}

    def _log(self, kind: str, value: dict) -> None:
        event = {"wall_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                 "t_s": self.river.time_s, "kind": kind, **copy.deepcopy(value)}
        self.session_events.append(event)
        if self.log_path is not None:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event, allow_nan=False, separators=(",", ":")) + "\n")

    def _solute_checkpoint(self):
        """Copy mutable solute state while sharing immutable geometry and forcing."""
        state = copy.copy(self.solutes)
        state._concentrations = {key: value.copy() for key, value in self.solutes._concentrations.items()}
        state._totals = copy.deepcopy(self.solutes._totals)
        state._water_totals = copy.deepcopy(self.solutes._water_totals)
        return state

    def _checkpoint(self):
        return {"river": self.river.checkpoint(), "ecology": copy.deepcopy(self.ecology),
                "config": copy.deepcopy(self.config), "epoch_origin": self.epoch_origin,
                "display_hour": self.display_hour,
                "start_operation": self.config.get("start_operation", "new_scenario"),
                "measured_reference": copy.deepcopy(self.measured_reference),
                "observation_samples": copy.deepcopy(self.observation_samples),
                "baseline": self._baseline._checkpoint() if self._baseline is not None else None,
                "integration_segment_count": len(self._integration_segments),
                "solutes": self._solute_checkpoint()}

    def _restore(self, checkpoint):
        self.river.restore(checkpoint["river"])
        self.solutes = copy.copy(checkpoint["solutes"])
        self.solutes._concentrations = {key: value.copy() for key, value in checkpoint["solutes"]._concentrations.items()}
        self.solutes._totals = copy.deepcopy(checkpoint["solutes"]._totals)
        self.solutes._water_totals = copy.deepcopy(checkpoint["solutes"]._water_totals)
        self.ecology = copy.deepcopy(checkpoint["ecology"])
        self.config = copy.deepcopy(checkpoint["config"])
        self.epoch_origin = checkpoint["epoch_origin"]
        self.display_hour = checkpoint.get("display_hour")
        self.measured_reference = copy.deepcopy(checkpoint["measured_reference"])
        self._integration_segments = self._integration_segments[:checkpoint.get("integration_segment_count", 0)]
        self.observation_samples = copy.deepcopy(checkpoint.get("observation_samples", []))
        if self._baseline is not None and checkpoint.get("baseline") is not None:
            self._baseline._restore(checkpoint["baseline"])
        self._weather_cache.clear()

    @property
    def worker_running(self) -> bool:
        """Report whether a background worker owns advancement."""
        return self._worker is not None

    def snapshot_at_frontier(self) -> dict:
        """Return an independent copy of the latest completed frame."""
        with self._lock:
            return copy.deepcopy(self._frames[-1])

    def checkpoint_state(self) -> dict:
        """Return an in-memory checkpoint of the state at the completed frontier."""
        with self._lock:
            return self._checkpoint()

    def restore_state(self, state: dict, *, revision: int | None = None,
                      frames: list | None = None) -> None:
        """Restore a checkpoint and root the retained history at its time.

        Frames default to a frame rebuilt from the restored state."""
        with self._lock:
            self._restore(state)
            if revision is not None:
                self.revision = revision
            self._frames = copy.deepcopy(frames) if frames is not None else [self._frame()]
            self._checkpoints = {self.river.time_s: self._checkpoint()}
            self._publish_snapshot()

    def trim_history(self, keep_from_s: float) -> None:
        """Drop frames and checkpoints earlier than the given time."""
        with self._lock:
            self._frames = [frame for frame in self._frames if frame["t_s"] >= keep_from_s]
            self._checkpoints = {t: value for t, value in self._checkpoints.items() if t >= keep_from_s}
            self._publish_snapshot()

    def export_state(self, state: dict, *, revision: int) -> dict:
        """Return a versioned JSON-compatible document for a checkpoint_state result."""
        from yellowstone_python.service.live import state_codec
        with self._lock:
            return state_codec.encode_state(self, state, revision)

    def import_state(self, document: dict, *, accept_source_drift: bool = False) -> None:
        """Restore the state held in an export_state document."""
        from yellowstone_python.service.live import state_codec
        with self._lock:
            state, revision, history = state_codec.decode_state(
                self, document, accept_source_drift=accept_source_drift)
            self._integration_segments = history["integration_segments"]
            self._forcing_catalog.update(history["forcing_catalog"])
            self.restore_state(state, revision=revision)

    def _landscape(self):
        flows = self.river._face_flow_at(self.river.time_s)[1:]
        rows = [{"id": cell.id, "s_m": record.get("center_s_m", i * cell.length_m),
                 "temperature_c": self.ecology["exposure_c"][i] if hasattr(self, "ecology") else cell.initial_c,
                 "depth_m": cell.volume_m3 / cell.surface_area_m2,
                 "velocity_m_s": flows[i] / cell.cross_section_m2,
                 "shear_pa": record.get("hydraulics", {}).get("bed_shear_pa"),
                 "position_xyz": record.get("position_xyz", [0., 0., 0.])}
                for i, (cell, record) in enumerate(zip(self.river.cells, self.cells))]
        if self.config["aquatic"].get("tributary_pockets"):
            pocket_t = self.config["aquatic"].get("pocket_temperature_c", 11.0)
            for spec in TRIBUTARY_CANDIDATES:
                pocket = build_tributary_cell(spec, temperature_c=pocket_t)
                nearest = min(rows, key=lambda cell: abs(cell["s_m"] - pocket["s_m"]))
                rows.append({**pocket, "position_xyz": nearest["position_xyz"]})
        return rows

    def _weather(self, t_s):
        key = (self.revision, t_s)
        if key in self._weather_cache:
            return self._weather_cache[key]
        epoch = self.epoch_origin + t_s
        hour = (epoch / 3600.0 - 6.0) % 24.0
        cfg = self.config["weather"]
        air = microclimate.air_temp(hour, cfg.get("night_air_c", 7.),
                                   cfg.get("day_warming_c", 15.), cfg.get("lag_hours", 3.))
        wind = microclimate.wind_at(t_s, cfg.get("wind_xz_mps", [1.8, .6]), cfg.get("gust_mps", .45))
        if self.config.get("live", {}).get("weather_policy", "preserve_published") == "preserve_published":
            air = self.river.air_c.at(t_s)
        if self.river.surface_budget is not None and self.config.get("live", {}).get("weather_policy", "preserve_published") == "preserve_published":
            met = self.river.surface_budget.met_at(t_s, air)
            humidity, cloud = met.rh, met.cloud
            wind = [met.wind_mps, 0.]
        else:
            humidity, cloud = cfg.get("humidity", .45), cfg.get("cloud", .16)
        if self.config.get("published_weather") and self.config.get("live", {}).get("weather_policy") == "preserve_published":
            from yellowstone_python.exporters.runtime_series import replay_weather
            prescribed = replay_weather(self.config["published_weather"], cfg, t_s)
            air, wind = prescribed["air_c"], prescribed["wind_xz_mps"]
            humidity, cloud = prescribed["relative_humidity"], prescribed["cloud_fraction"]
        snapshot_cfg = {**cfg, "night_air_c": air, "day_warming_c": 0., "humidity": humidity,
                        "cloud": cloud, "wind_xz_mps": list(wind)}
        snapshot = microclimate.weather_snapshot(epoch, snapshot_cfg)
        value = {**snapshot["weather"], "solar": snapshot["solar"], "source": snapshot["source"],
                 "air_c": air, "humidity": humidity, "relative_humidity": humidity,
                 "cloud": cloud, "cloud_fraction": cloud, "wind_xz_mps": list(wind),
                 "wind_speed_mps": math.hypot(*wind), "precip_mm_h": cfg.get("precip_mm_h", 0.),
                 "valid_time_unix": epoch, "epoch_unix": epoch, "clock_hour": hour,
                 "dewpoint_c": microclimate.dewpoint_c(air, humidity) if humidity > 0. else None}
        self._weather_cache[key] = value
        return value

    def _prepare_weather(self, end_s):
        if (self.config.get("run_mode") == "observed_replay"
                or self.config.get("live", {}).get("weather_policy", "preserve_published") == "preserve_published"):
            return
        times = [self.river.time_s + i * 60.0 for i in range(int((end_s - self.river.time_s) / 60) + 2)]
        from pvlib.location import Location
        import pandas as pd
        epoch_times = pd.to_datetime([self.epoch_origin + t for t in times], unit="s", utc=True)
        site = Location(SITE_LAT_DEG, SITE_LON_DEG, altitude=SITE_ELEVATION_M, tz="UTC")
        clear = site.get_clearsky(epoch_times, model="ineichen")["ghi"].to_numpy()
        for t, sw in zip(times, clear):
            weather = self._weather(t)
            self._weather_cache[(self.revision, t)]["shortwave_w_m2"] = float(sw) * (1. - .75 * weather["cloud"] ** 3.4)
        schedules = {"air_c": [], "rh": [], "wind_mps": [], "cloud": [], "shortwave_w_m2": []}
        for t in times:
            weather = self._weather(t)
            for name, value in (("air_c", weather["air_c"]), ("rh", weather["humidity"]),
                                ("wind_mps", weather["wind_speed_mps"]), ("cloud", weather["cloud"]),
                                ("shortwave_w_m2", weather["shortwave_w_m2"])):
                schedules[name].append(value)
        for name, values in schedules.items():
            if name != "air_c" and self.river.surface_budget is None:
                continue
            original = self.river.air_c if name == "air_c" else getattr(self.river.surface_budget, name)
            kept = [(t, v) for t, v in zip(original.times_s, original.values) if t < self.river.time_s]
            kept.extend(zip(times, values))
            schedule = Series(tuple(t for t, _ in kept), tuple(v for _, v in kept))
            if name == "air_c":
                self.river.air_c = schedule
            else:
                from dataclasses import replace
                self.river.surface_budget = replace(self.river.surface_budget, **{name: schedule})
        self.river._rebuild_forcing()

    def _solver_dt_s(self):
        """Resolve a physical solver step independent of playback speed."""
        step = self.config.get("live", {}).get("dt_s", self.config.get("replay", {}).get("dt_s", .1))
        return min(self.max_dt_s, positive("solver dt_s", step))

    def _advance(self, end_s):
        if end_s <= self.river.time_s:
            return
        before = time.perf_counter()
        start = self.river.time_s
        dt_s = self._solver_dt_s()
        forcing = self._forcing_config(start, end_s)
        import hashlib
        forcing_key = hashlib.sha256(json.dumps(forcing, sort_keys=True).encode()).hexdigest()
        self._forcing_catalog.setdefault(forcing_key, forcing)
        self._integration_segments.append({"start_s": start, "end_s": end_s,
                                           "dt_s": dt_s, "forcing_key": forcing_key})
        self.river.run(end_s - start, dt_s=dt_s, sample_s=end_s - start)
        from dataclasses import replace
        self.solutes._boundary_q_series = self.river._boundary_q_series
        flows = {source.id: source.flow_m3_s for source in self.river.sources}
        self.solutes.sources = tuple(replace(source, flow_m3_s=flows[source.id]) for source in self.solutes.sources)
        self.solutes._sources_by_cell = [[source for source in self.solutes.sources if source.cell_id == cell.id]
                                        for cell in self.river.cells]
        self.solutes._forcing = (self.solutes._boundary_q_series,
                                 *self.solutes._boundary_c_series.values(),
                                 *(source.flow_m3_s for source in self.solutes.sources),
                                 *(schedule for source in self.solutes.sources for schedule in source.concentrations.values()))
        self.solutes.run(end_s - start,
                         dt_s=self.config.get("live", {}).get("solute_dt_s", self.frame_interval_s),
                         sample_s=end_s - start)
        self.timings["river"] = (time.perf_counter() - before) * 1000.
        span = end_s - start
        before = time.perf_counter()
        tau_s = positive("tau_exposure_h", self.config.get("live", {}).get("tau_exposure_h", 1.0)) * 3600.
        retain = math.exp(-span / tau_s)
        self.ecology["exposure_c"] = [current + (old - current) * retain
                                      for old, current in zip(self.ecology["exposure_c"], self.river.temperature_c)]
        weather = self._weather(end_s)
        sw = self.river.surface_budget.shortwave_w_m2.at(start) if self.river.surface_budget else 0.
        if end_s - self.ecology["last_aquatic_t_s"] >= self.config.get("live", {}).get("aquatic_interval_s", 60.):
            aquatic_span = end_s - self.ecology["last_aquatic_t_s"]
            oxygen_cells = []
            for i, cell in enumerate(self.river.cells):
                temp = self.river.temperature_c[i]
                biomass = periphyton.step_biomass(self.ecology["periphyton"][i], sw * self.river._cell_shortwave_multiplier[i],
                                                 temp, 0., aquatic_span, self._periphyton_params)["biomass_mg_c_m2"]
                self.ecology["periphyton"][i] = biomass
                oxygen_cells.append(river_oxygen.OxygenCell(cell.id, cell.length_m, cell.width_m,
                    cell.volume_m3 / cell.surface_area_m2, self.river._face_flow_at(start)[i + 1] / cell.cross_section_m2,
                    temp, self.ecology["oxygen_mg_l"][i], biomass, sw))
            oxygen = river_oxygen.advect_cells(oxygen_cells, river_oxygen.saturation_mg_l(self.river.boundary_c.at(start)), aquatic_span, periphyton_params=self._periphyton_params)
            self.ecology["oxygen_mg_l"] = [row["do_mg_l"] for row in oxygen["cells"]]
            self.ecology["last_aquatic_t_s"] = end_s
        self.ecology["insects"], self.ecology["insect_ledger"] = insects_birds.step_compartments(
            self.ecology["insects"], {"sun": insects_birds.sunlight(weather["clock_hour"]),
            "air_c": weather["air_c"], "cloud": weather["cloud"], "wind_mps": weather["wind_speed_mps"],
            "water_c": sum(self.river.temperature_c) / len(self.river.cells),
            "flowering": self.config.get("insects", {}).get("flowering_stage", .5)}, span)
        self.timings["oxygen_periphyton_insects"] = (time.perf_counter() - before) * 1000.
        before = time.perf_counter()
        landscape = self._landscape()
        food_interval = self.config.get("live", {}).get("foodweb_interval_s", 3600.)
        if end_s - self.ecology["last_foodweb_t_s"] >= food_interval:
            elapsed = end_s - self.ecology["last_foodweb_t_s"]
            food_state = self.ecology["foodweb"]
            if food_state["cell_ids"] != [cell["id"] for cell in landscape]:
                old = dict(zip(food_state["cell_ids"], food_state["stocks"]))
                food_state["cell_ids"] = [cell["id"] for cell in landscape]
                food_state["stocks"] = [old.get(cell["id"], {"ept": .5, "dipt": .5, "ne": .2}) for cell in landscape]
            self.food_settings["do_mg_l_by_cell"] = dict(zip([cell.id for cell in self.river.cells], self.ecology["oxygen_mg_l"]))
            self.food_settings["cover"] = self.config.get("fish", {}).get("cover", .6)
            self.food_settings["solute_concentrations"] = {cell.id: {key: self.solutes._concentrations[key][i]
                for key in SOLUTE_KEYS} for i, cell in enumerate(self.river.cells)}
            self.ecology["foodweb_report"] = step_foodweb(food_state, landscape, elapsed / 86400., self.food_settings)
            self.ecology["last_foodweb_t_s"] = end_s
        self.timings["foodweb"] = (time.perf_counter() - before) * 1000.
        if end_s - self.ecology["last_land_t_s"] >= 3600.:
            days = (end_s - self.ecology["last_land_t_s"]) / 86400.
            patches = self.ecology["patches"]
            working_patches = patches or [{"id": "background", "center_xz": [0., 0.],
                "snow_mm": self.ecology["snow_mm"], "soil_mm": self.ecology["soil_mm"]}]
            working_patches, totals = snow_season.step_land(working_patches, days * 86400.,
                weather["air_c"], weather["precip_mm_h"] * 24., weather["wind_speed_mps"],
                interval_start_s=self.ecology["last_land_t_s"],
                thermal_flux_mm_d_by_patch={p["id"]: ground_heat.thermal_melt_mm_d_from_ghf(
                    self._patch_heat_flux.get(p["id"], ground_heat.GHF_BACKGROUND_W_M2)) for p in working_patches} if not self.config.get("land_thermal_flux_mm_d_by_patch") else self.config["land_thermal_flux_mm_d_by_patch"])
            ledger = {key: value / len(working_patches) if key.endswith("_mm") and isinstance(value, (int, float))
                      else value for key, value in totals.items()}
            self.ecology["patches"] = working_patches if patches else []
            patches = self.ecology["patches"]
            self.ecology["snow_mm"] = sum(p["snow_mm"] for p in working_patches) / len(working_patches)
            self.ecology["soil_mm"] = sum(p["soil_mm"] for p in working_patches) / len(working_patches)
            self.ecology["land_ledger"] = ledger
            self._update_land_temperature(weather["air_c"])
            runoff = ledger["runoff_mm"]
            catchment_area = self.config.get("live", {}).get("catchment_area_m2", 0.)
            runoff_q = runoff / 1000. * catchment_area / (days * 86400.)
            if catchment_area > 0. and self.config.get("run_mode") != "observed_replay":
                self.river.set_forcing("boundary_m3_s", end_s, self.config["hydro"]["boundary_m3s"] + runoff_q)
            self.ecology["last_land_t_s"] = end_s
        patches = self.ecology["patches"]
        grazers = {"bison": {"active": True, "patch_id": self.config["grazing"].get("patch_id", patches[0]["id"]),
                            "rate_per_second": self.config["grazing"].get("bison_count", 0) * .00001}} if patches else None
        self.ecology["patches"], _ = vegetation.patch_step(patches, weather["clock_hour"], span, grazers=grazers)
        if end_s - self.ecology["last_mammal_t_s"] >= self.frame_interval_s:
            before = time.perf_counter()
            self._update_mammals(end_s - self.ecology["last_mammal_t_s"])
            self.ecology["last_mammal_t_s"] = end_s
            self.timings["mammals"] = (time.perf_counter() - before) * 1000.0
        if self._baseline is not None:
            self._baseline.time_scale = self.time_scale
            self._baseline.max_dt_s = self.max_dt_s
            self._baseline._advance(end_s)

    def _patch_mean(self, key, default):
        patches = self.ecology["patches"]
        return sum(p.get(key, default) for p in patches) / len(patches) if patches else default

    def _update_mammals(self, dt_s):
        """Advance mammal ecology with the current weather and patch forcing."""
        model = self.ecology.get("mammal_model")
        if model is None:
            return
        epoch = self.epoch_origin + self.river.time_s
        forcing = environmental_forcing(self.ecology["patches"], self._weather(self.river.time_s), epoch)
        report = model.step(dt_s, forcing)
        self.ecology["patches"], ledger = apply_consumption(
            self.ecology["patches"], report["consumption_by_patch"])
        report["vegetation_coupling"] = ledger
        self.ecology["mammal_report"] = report

    def _update_land_temperature(self, air_c):
        """Apply the published steady conductive profile at each patch center."""
        for patch in self.ecology["patches"]:
            patch["soil_temperature_c"] = ground_heat.soil_temperature_c(air_c,
                self._patch_heat_flux[patch["id"]], site_elevation_m=SITE_ELEVATION_M)
        self.ecology["soil_temperature_c"] = self._patch_mean("soil_temperature_c",
            ground_heat.soil_temperature_c(air_c, ground_heat.GHF_BACKGROUND_W_M2, site_elevation_m=SITE_ELEVATION_M))

    def _trout(self):
        landscape = self._landscape()
        report = self.ecology.get("foodweb_report")
        if report is not None:
            trout = copy.deepcopy(report["trout"])
            selected = next((cell for cell in landscape if cell["id"] == trout["cell_id"]), None)
        else:
            trout = self.ecology.get("initial_trout")
            if trout is None:
                scores = [(suitability_with_stressors(.5, .6, cell["temperature_c"], cell["velocity_m_s"],
                            cell["depth_m"], species="brown_trout", refuge_weight=1.)["U"], cell) for cell in landscape]
                score, selected = max(scores, key=lambda row: row[0])
                perf = thermal_performance(selected["temperature_c"])
                trout = {"cell_id": selected["id"], "s_m": selected["s_m"], "U": score,
                         "temperature_c": selected["temperature_c"], **perf}
                self.ecology["initial_trout"] = copy.deepcopy(trout)
                self.ecology["foodweb"]["chosen_cell_id"] = selected["id"]
            else:
                trout = copy.deepcopy(trout)
                selected = next(cell for cell in landscape if cell["id"] == trout["cell_id"])
                trout.update(thermal_performance(selected["temperature_c"]))
                trout["temperature_c"] = selected["temperature_c"]
        if selected is not None:
            position = selected["position_xyz"]
            trout["target_xz_m"] = [position[0], position[2]]
            trout["position_xyz"] = position
        if selected is not None:
            current = self._instantaneous_cell_temperature(selected)
            trout["exposure_temperature_c"] = selected["temperature_c"]
            trout["temperature_c"] = current
            trout.update(thermal_performance(current, "brown_trout", self.food_settings["thermal_curve_form"]))
            trout["thermal_performance_basis"] = "instantaneous temperature"
        trout["swim_speed_multiplier"] = float(trout["feeding"])
        return trout

    def _instantaneous_cell_temperature(self, selected):
        index = self._cell_index.get(selected["id"])
        return self.river.temperature_c[index] if index is not None else selected["temperature_c"]

    def _actor_trout(self, summary):
        """Map actor IDs to species-specific refuge rankings on shared prey stocks."""
        landscape = self._landscape()
        food_state = self.ecology["foodweb"]
        stocks = dict(zip(food_state["cell_ids"], food_state["stocks"]))
        foods = {cell["id"]: (stocks.get(cell["id"], {}).get("ne", .2)
                              + .5 * (stocks.get(cell["id"], {}).get("ept", .5)
                                      + stocks.get(cell["id"], {}).get("dipt", .5)))
                              * cell.get("food_scale", 1.) for cell in landscape}
        ceiling = max(foods.values()) or 1.
        records = []
        for actor in self.config.get("wildlife", []):
            species = actor.get("species_id", actor.get("kind"))
            if species not in ("brown_trout", "rainbow_trout"):
                continue
            if species == "brown_trout":
                selected_id, score = summary["cell_id"], summary["U"]
            else:
                selected_id = self.ecology["refuge_by_species"].get(species)
                update_time = self.ecology["last_foodweb_t_s"]
                if selected_id is None or self.ecology["species_selection_t_s"].get(species) != update_time:
                    scored = [(suitability_with_stressors(foods[cell["id"]] / ceiling,
                               self.config["fish"]["cover"], cell["temperature_c"], cell["velocity_m_s"],
                               cell["depth_m"], species=species, refuge_weight=1.,
                               thermal_curve_form=self.food_settings["thermal_curve_form"])["U"], cell)
                              for cell in landscape]
                    score, selected = max(scored, key=lambda row: row[0])
                    previous = next((row for row in scored if row[1]["id"] == selected_id), None)
                    if previous is not None:
                        distance = abs(previous[1]["s_m"] - selected["s_m"])
                        if score - previous[0] <= self.food_settings["delta_u_switch"] + self.food_settings["movement_cost_per_m"] * distance:
                            score, selected = previous
                    selected_id = selected["id"]
                    self.ecology["refuge_by_species"][species] = selected_id
                    self.ecology["species_selection_t_s"][species] = update_time
                    self.ecology.setdefault("species_selection_u", {})[species] = score
                else:
                    score = self.ecology["species_selection_u"][species]
            selected = next(cell for cell in landscape if cell["id"] == selected_id)
            position = selected["position_xyz"]
            current = self._instantaneous_cell_temperature(selected)
            perf = thermal_performance(current, species, self.food_settings["thermal_curve_form"])
            records.append({"id": actor["id"], "species_id": species,
                "refuge_cell_id": selected_id, "cell_id": selected_id,
                "refuge_s_m": selected["s_m"], "s_m": selected["s_m"], "U": score,
                "feeding": perf["feeding"], "refuge_drive": perf["refuge_drive"],
                "temperature_c": current, "exposure_temperature_c": selected["temperature_c"],
                "thermal_performance_basis": "instantaneous temperature", "target_xz_m": [position[0], position[2]],
                "position_xyz": position, "selection_scope": "shared modeled prey stock", "status": "illustrative"})
        return records

    def _header(self):
        return {"run_mode": self.config.get("run_mode", "scenario"), "build_id": self.build_id,
                "session_id": self.session_id, "time_scale": self.time_scale,
                "claims": [{"claim_id": claim, "review_status": "not_yet_accepted"} for claim in self.claim_ids],
                "model_components": MODEL_COMPONENTS, "stage_contracts": self._stage_contracts, "solute_boundary_provenance": self.solute_boundary_provenance,
                "static_from_build": {name: self.build_id for name in STATIC_COMPONENTS},
                "timings": copy.deepcopy(self.timings), "dirty_stages": list(self.dirty_stages),
                "dt_s": self._solver_dt_s(),
                "exchange_strategy": "explicit_surface_budget" if self.river.surface_budget else "newton_exchange",
                "model_variant_id": self.config.get("model_variant_id") or ("mapped_fv_explicit" if self.river.surface_budget else "mapped_fv_newton"),
                "scenario_id": self.config.get("scenario_id", self.build_id),
                "start_operation": self.config.get("start_operation", "new_live_run"),
                "display_hour": self.display_hour,
                "initial_state_id": getattr(self, "initial_state_id", None),
                "max_dt_s": self.max_dt_s, "paused": self.paused,
                "compute_rate_sps": self._compute_rate_sps,
                "max_dt_capacity_sps": self._max_dt_capacity_sps,
                "clock_debt_s": self._clock_debt_s,
                "computing": self._clock_debt_s > 0.,
                "clock_held": self._clock_debt_s > 0. and not self.paused,
                "max_supported_time_scale": self._supported_scale(),
                "frame_interval_s": self.frame_interval_s,
                "health": {"max_advective_courant": self.river.max_advective_courant,
                           "max_surface_iterations_used": self.river.max_surface_iterations_used,
                           "surface_iteration_failures": self.river.surface_iteration_failures,
                           "worker_error": self.worker_error}}

    def _frame(self):
        landscape = self._landscape()
        rows = []
        for i, cell in enumerate(landscape[:len(self.river.cells)]):
            perf = thermal_performance(self.river.temperature_c[i], "brown_trout",
                                       self.food_settings["thermal_curve_form"])
            exposure_perf = thermal_performance(self.ecology["exposure_c"][i])
            score = suitability_with_stressors(self.config.get("fish", {}).get("food", .5),
                self.config.get("fish", {}).get("cover", .6), self.ecology["exposure_c"][i],
                cell["velocity_m_s"], cell["depth_m"], species="brown_trout", refuge_weight=1.)["U"]
            rows.append({"cell_id": cell["id"], "id": cell["id"], "s_m": cell["s_m"],
                         "temperature_c": self.river.temperature_c[i], "depth_m": cell["depth_m"],
                         "velocity_mps": cell["velocity_m_s"], "velocity_m_s": cell["velocity_m_s"],
                         "oxygen_mg_l": self.ecology["oxygen_mg_l"][i],
                         "shading_factor": self.river._cell_shortwave_multiplier[i],
                         "feeding": perf["feeding"], "stress": perf["stress"],
                         "solutes": {key: self.solutes._concentrations[key][i] for key in SOLUTE_KEYS},
                         "trout_suitability_u": score, "refuge_drive": perf["refuge_drive"],
                         "exposure_temperature_c": self.ecology["exposure_c"][i],
                         "exposure_refuge_drive": exposure_perf["refuge_drive"],
                         "thermal_performance_basis": "instantaneous temperature", "species_id": "brown_trout"})
        trout_summary = self._trout()
        frame = {"t_s": self.river.time_s, "epoch_unix": self.epoch_origin + self.river.time_s,
                 "temperature_c": list(self.river.temperature_c),
                 "q_cells_m3s": list(self.river._face_flow_at(self.river.time_s)[1:]),
                 "depth_m_cells": [row["depth_m"] for row in rows], "cells": rows,
                 "trout": self._actor_trout(trout_summary), "trout_summary": trout_summary,
                 "feeding_by_species": {species: [thermal_performance(temp, species,
                     self.food_settings["thermal_curve_form"])["feeding"] for temp in self.river.temperature_c]
                     for species in ("brown_trout", "rainbow_trout")}, "weather": copy.deepcopy(self._weather(self.river.time_s)),
                 "ecology": {"snow": {"swe_mm": self.ecology["snow_mm"]},
                             "soil": {"water_mm": self.ecology["soil_mm"], "temperature_c": self.ecology["soil_temperature_c"]},
                             "patches": copy.deepcopy(self.ecology["patches"]),
                             "insects": copy.deepcopy(self.ecology["insects"]),
                             "foodweb": copy.deepcopy(self.ecology["foodweb_report"])},
                 "health": {"max_advective_courant": self.river.max_advective_courant,
                            "max_surface_iterations_used": self.river.max_surface_iterations_used,
                            "surface_iteration_failures": self.river.surface_iteration_failures,
                            "worker_error": self.worker_error}, "header": self._header()}
        frame["trout_records"] = frame["trout"]
        if "mammal_report" in self.ecology:
            frame["ecology"]["mammals"] = copy.deepcopy(self.ecology["mammal_report"])
        if self.measured_reference is not None:
            frame["observations"] = self._measured_frame()
        return frame

    def compute_until(self, end_s):
        """Fill the lookahead buffer through a requested physical time."""
        with self._lock:
            if end_s <= self.river.time_s:
                return
            compute_started = time.perf_counter()
            compute_start_s = self.river.time_s
            self._prepare_weather(end_s)
            if self._baseline is not None:
                self._baseline._prepare_weather(end_s)
            while self.river.time_s < end_s - 1e-9:
                target = min(end_s, self.river.time_s + self.frame_interval_s)
                self._advance(target)
                self._frames.append(self._frame())
                self._checkpoints[target] = self._checkpoint()
                if self._baseline is not None:
                    self._baseline._frames.append(self._baseline._frame())
                    self._baseline._checkpoints[target] = self._baseline._checkpoint()
                self._publish_snapshot()
            span = self.river.time_s - compute_start_s
            if span >= self.frame_interval_s:
                elapsed = time.perf_counter() - compute_started
                self._compute_samples.append((span, elapsed))
                self._compute_samples = self._compute_samples[-256:]
                self._compute_rate_sps = sum(row[0] for row in self._compute_samples) / sum(row[1] for row in self._compute_samples)
                if self._solver_dt_s() == self.max_dt_s:
                    self._record_max_dt_capacity(span, elapsed)
            self._publish_snapshot()

    def _record_max_dt_capacity(self, span_s, elapsed_s):
        self._max_dt_samples.append((span_s, elapsed_s))
        self._max_dt_samples = self._max_dt_samples[-256:]
        self._max_dt_capacity_sps = sum(row[0] for row in self._max_dt_samples) / sum(row[1] for row in self._max_dt_samples)

    def _capacity_clone(self, source):
        clone = LiveEngine(copy.deepcopy(source.river), source.config, cells=source.cells,
            geometry=source.geometry, build_id=source.build_id, claim_ids=source.claim_ids,
            epoch_unix=source.epoch_origin, max_dt_s=source.max_dt_s, time_scale=600.,
            horizon_s=source.horizon_s, frame_interval_s=source.frame_interval_s,
            observation_bundle=source.observation_bundle, calibration_params=source.calibration_params)
        clone.ecology = copy.deepcopy(source.ecology)
        clone.solutes = source._solute_checkpoint()
        clone.measured_reference = copy.deepcopy(source.measured_reference)
        clone.observation_samples = copy.deepcopy(source.observation_samples)
        clone._frames = [clone._frame()]
        clone._checkpoints = {clone.river.time_s: clone._checkpoint()}
        return clone

    def _assess_max_dt_capacity(self):
        """Measure a cloned model at the validated maximum timestep with clock held."""
        trial = self._capacity_clone(self)
        if self._baseline is not None:
            trial._baseline = self._capacity_clone(self._baseline)
        span = max(600., self.horizon_s)
        trial.compute_until(trial.river.time_s + span)
        started = time.perf_counter()
        trial.compute_until(trial.river.time_s + span)
        self._max_dt_samples.clear()
        self._record_max_dt_capacity(span, time.perf_counter() - started)

    def _supported_scale(self):
        """Return a clock preset with twenty percent compute headroom."""
        capacity = self._max_dt_capacity_sps if self._max_dt_capacity_sps is not None else self._compute_rate_sps
        limit = 600. if capacity is None else .8 * capacity
        return max(scale for scale in (1., 60., 600., 3600.) if scale <= max(1., limit))

    def _publish_snapshot(self):
        """Publish immutable frame references and a matching service header."""
        self._tick_clock()
        self._published_view = (tuple(self._frames), self._header(), self.revision,
                                self.truncate_after_t_s, self.player_t_s)

    def _tick_clock(self):
        """Retain elapsed-time debt while completed frames limit clock advancement."""
        if not self._clock_started or threading.current_thread() is not self._worker:
            return
        wall = time.monotonic()
        if not self.paused:
            self._clock_debt_s += (wall - self._last_wall) * self.time_scale
            last = self._frames[-1]["t_s"]
            reserve = 0. if self.measured_reference is not None and last >= self._measured_limit_t_s else self.frame_interval_s
            available = max(0., last - reserve - self.player_t_s)
            advance = min(available, self._clock_debt_s)
            self.player_t_s += advance
            self._clock_debt_s -= advance
        self._last_wall = wall

    def frames(self, after_t_s=-1., player_t_s=None):
        """Read completed immutable frames while the model computes lookahead."""
        after_t_s = finite("after_t_s", after_t_s)
        if player_t_s is not None:
            self._client_player_t_s = finite("client player_t_s", player_t_s, minimum=0.)
        frames, header, revision, truncate, player = self._published_view
        selected = [frame for frame in frames if frame["t_s"] > after_t_s]
        return {"frames": copy.deepcopy(selected), "header": copy.deepcopy(header),
                "player_t_s": player, "buffer_headroom_s": frames[-1]["t_s"] - player,
                "revision": revision, "truncate_after_t_s": truncate,
                "retained_after_t_s": frames[0]["t_s"],
                "reset_required": after_t_s >= 0. and after_t_s < frames[0]["t_s"]}

    def _at_time(self, at_s):
        at_s = finite("at_s", at_s, minimum=0.)
        if at_s < min(self._checkpoints):
            raise ValueError("control time precedes retained checkpoint window")
        if at_s > self.river.time_s:
            self.compute_until(at_s)
        nearest = max(t for t in self._checkpoints if t <= at_s)
        self._restore(self._checkpoints[nearest])
        if self.river.time_s < at_s:
            self._advance(at_s)
        self._frames = [frame for frame in self._frames if frame["t_s"] <= at_s]
        self._checkpoints = {t: value for t, value in self._checkpoints.items() if t <= at_s}
        if not self._frames or self._frames[-1]["t_s"] < at_s:
            self._frames.append(self._frame())
        self._checkpoints[at_s] = self._checkpoint()
        if self._baseline is not None:
            self._baseline._frames = [frame for frame in self._baseline._frames if frame["t_s"] <= at_s]
            self._baseline._checkpoints = {t: value for t, value in self._baseline._checkpoints.items() if t <= at_s}
        return at_s

    def _control(self, payload):
        changes = copy.deepcopy(payload.get("changes", {payload.get("key"): payload.get("value")}))
        pocket = changes.get("aquatic.tributary_pockets") if isinstance(changes, dict) else None
        if isinstance(pocket, dict):
            if set(pocket) != {"enabled", "temperature_c"}:
                raise ValueError("tributary_pockets requires enabled and temperature_c")
            changes["aquatic.tributary_pockets"] = pocket["enabled"]
            changes["aquatic.pocket_temperature_c"] = pocket["temperature_c"]
        grazing = changes.get("grazing.bison_count") if isinstance(changes, dict) else None
        grazing_patch_id = None
        if isinstance(grazing, dict):
            if set(grazing) != {"patch_id", "count"}:
                raise ValueError("grazing.bison_count requires patch_id and count")
            grazing_patch_id = grazing["patch_id"]
            if grazing_patch_id not in {patch["id"] for patch in self.ecology["patches"]}:
                raise ValueError("grazing.bison_count names an unknown patch")
            changes["grazing.bison_count"] = grazing["count"]
        if not isinstance(changes, dict) or not changes:
            raise ValueError("changes must be a nonempty object")
        for key, value in changes.items():
            _validate(key, value)
            if key not in DEPENDENCIES:
                raise ValueError(f"control {key!r} does not have a live model dependency")
        shade = changes.get("river.shade")
        if shade and set(shade["cell_ids"]) - {cell.id for cell in self.river.cells}:
            raise ValueError("river.shade names unknown cells")
        if any(key.startswith("thermal.excelsior") for key in changes) and not any(
                "excelsior" in source.id for source in self.river.sources):
            raise ValueError("base build contains no Excelsior source")
        if "snow.as_of_date" in changes or any(key in changes for key in
                ("snow.days", "snow.air_c_by_day", "snow.season")):
            return self._reset({"changes": changes})
        if set(changes) == {"clock_hour"}:
            self.display_hour = float(changes["clock_hour"])
            self.dirty_stages = ["display"]
            self._log("display_clock", {"display_hour": self.display_hour})
            return {"ok": True, "operation": "display", "display_hour": self.display_hour,
                    "dirty_stages": ["display"], "controls": changes, "revision": self.revision}
        at_s = self._at_time(payload.get("at_s", payload.get("t_s", self.player_t_s)))
        self.revision += 1
        self.truncate_after_t_s = at_s
        if grazing_patch_id is not None:
            self.config["grazing"]["patch_id"] = grazing_patch_id
        self.dirty_stages = list(dict.fromkeys(stage for key in changes for stage in DEPENDENCIES[key]
            if stage != "mammals" or "mammal_model" in self.ecology))
        if any(key.startswith("weather.") for key in changes):
            self.config["live"]["weather_policy"] = "scenario_weather"
        for key, value in changes.items():
            if key == "clock_hour":
                self.display_hour = float(value)
                continue
            _set_config(self.config, key, value)
            if key in ("hydro.boundary_c", "hydro.boundary_m3s"):
                self.river.set_forcing("boundary_c" if key.endswith("boundary_c") else "boundary_m3_s", at_s, value)
            elif key in ("thermal.excelsior_enabled", "thermal.excelsior_c"):
                source = next((s for s in self.river.sources if "excelsior" in s.id), None)
                if source is None:
                    raise ValueError("base build contains no Excelsior source")
                field = "flow_m3_s" if key.endswith("enabled") else "temperature_c"
                actual = self._source_base_flows[source.id] * int(value) if field == "flow_m3_s" else value
                self.river.set_forcing(f"source.{source.id}.{field}", at_s, actual)
            elif key == "river.shade":
                multipliers = list(self.river._cell_shortwave_multiplier)
                for i, cell in enumerate(self.river.cells):
                    if cell.id in value["cell_ids"]:
                        multipliers[i] = value["multiplier"]
                self.river._cell_shortwave_multiplier = tuple(multipliers)
                self.river._cell_shortwave_multiplier_applied = any(v != 1. for v in multipliers)
            elif key == "weather.wind_speed_mps" or key == "weather.wind_direction_deg":
                wind = self.config["weather"]
                speed = wind.get("wind_speed_mps", math.hypot(*wind.get("wind_xz_mps", [1.8, .6])))
                direction = math.radians(wind.get("wind_direction_deg", 0.))
                wind["wind_xz_mps"] = [-speed * math.sin(direction), speed * math.cos(direction)]
            elif key == "weather.wind_xz_mps":
                wind = self.config["weather"]
                wind["wind_speed_mps"] = math.hypot(*value)
                wind["wind_direction_deg"] = microclimate.wind_from_direction(value)
        self._weather_cache.clear()
        self._update_land_temperature(self._weather(at_s)["air_c"])
        self.ecology["soil_mm"] = self._patch_mean("soil_mm", self.ecology["soil_mm"])
        if changes.get("aquatic.tributary_pockets") is False:
            self.ecology["foodweb_report"] = None
            self.ecology["initial_trout"] = None
            self.ecology["refuge_by_species"] = {}
            self.ecology["species_selection_t_s"] = {}
        self._prepare_weather(at_s + self.horizon_s)
        self._update_mammals(0.0)
        from yellowstone_python.common.provenance import sha256_json
        parent_scenario = self.config.get("scenario_id", self.build_id)
        self.config["scenario_id"] = sha256_json({"parent": parent_scenario, "at_s": at_s,
            "initial_state_id": self.initial_state_id, "changes": changes, "solver": self.solver_config()})
        self.config["start_operation"] = "controlled_branch"
        self._frames = [frame for frame in self._frames if frame["t_s"] < at_s]
        self._frames.append(self._frame())
        self._checkpoints[at_s] = self._checkpoint()
        self._log("control", {"changes": changes, "at_s": at_s, "dirty_stages": self.dirty_stages,
                              "solver_config": self.solver_config(),
                              "location_xyz_m": payload.get("location_xyz_m"), "grazing_patch_id": grazing_patch_id})
        return {"ok": True, "revision": self.revision, "truncate_after_t_s": at_s,
                "dirty_stages": self.dirty_stages, "controls": changes,
                "scenario_id": self.config["scenario_id"], "parent_scenario_id": parent_scenario}

    def _reset(self, payload):
        """Restore the identified initial state and apply one scenario spin-up."""
        changes = copy.deepcopy(payload.get("changes", {}))
        if not isinstance(changes, dict):
            raise ValueError("reset changes must be an object")
        for key, value in changes.items():
            _validate(key, value)
            if key not in DEPENDENCIES:
                raise ValueError("reset control lacks a live dependency")
        shade = changes.get("river.shade")
        if shade and set(shade["cell_ids"]) - {cell.id for cell in self.river.cells}:
            raise ValueError("river.shade names unknown cells")
        if any(key.startswith("thermal.excelsior") for key in changes) and not any(
                "excelsior" in source.id for source in self.river.sources):
            raise ValueError("base build contains no Excelsior source")
        config = copy.deepcopy(self._initial_checkpoint["config"])
        for key, value in changes.items():
            if key != "clock_hour":
                _set_config(config, key, value)
        snow = config.get("snow", {})
        date_text = snow.get("as_of_date")
        days = snow.get("days", 0)
        epoch = self._initial_checkpoint["epoch_origin"]
        if date_text is not None:
            date = dt.date.fromisoformat(date_text)
            origin = dt.datetime.fromtimestamp(epoch, dt.timezone(dt.timedelta(hours=-6)))
            epoch = dt.datetime.combine(date, origin.timetz()).timestamp()
            days = (date - dt.date(date.year if date.month >= 10 else date.year - 1, 10, 1)).days
        patches = self._initial_checkpoint["ecology"]["patches"]
        patched, ledger = patches, None
        if patches:
            air = snow.get("air_c_by_day", [config["weather"].get("night_air_c", 7.)] * days)
            patched, ledger = snow_season.run_season(patches, days, air,
                precip_mm_d=snow.get("precip_mm_d", 0.0))
        self._baseline = None
        self._restore(self._initial_checkpoint)
        self.config = config
        self.epoch_origin = epoch
        self.config["start_operation"] = "scenario_reset"
        if "clock_hour" in changes:
            self.display_hour = float(changes["clock_hour"])
        self.ecology["patches"] = patched
        if ledger is not None:
            self.ecology["snow_spinup"] = {"days": days, "ledger": ledger,
                "initial_state_id": self.initial_state_id, "provenance": "authored seasonal forcing"}
        self.ecology["snow_mm"] = self._patch_mean("snow_mm", 0.0)
        self.ecology["soil_mm"] = self._patch_mean("soil_mm", 60.0)
        self.player_t_s = self.river.time_s
        other = {key: value for key, value in changes.items() if not key.startswith("snow.") and key != "clock_hour"}
        if other:
            self._control({"changes": other, "at_s": self.player_t_s})
        self.config["start_operation"] = "scenario_reset"
        self._clock_debt_s = 0.0
        self._weather_cache.clear()
        self.revision += 1
        self.truncate_after_t_s = self.player_t_s
        self.dirty_stages = list(DOMAIN_OUTPUTS)
        from yellowstone_python.common.provenance import sha256_json
        self.config["scenario_id"] = sha256_json({"initial": self.initial_state_id, "changes": changes, "epoch": epoch})
        self._frames = [self._frame()]
        self._checkpoints = {self.player_t_s: self._checkpoint()}
        self._log("reset", {"changes": changes, "initial_state_id": self.initial_state_id})
        return {"ok": True, "operation": "scenario_reset", "revision": self.revision,
                "truncate_after_t_s": self.player_t_s, "initial_state_id": self.initial_state_id}

    def _advance_time(self, payload):
        """Integrate the requested elapsed physical interval and retain pause state."""
        seconds = finite("elapsed_s", payload.get("elapsed_s"), minimum=0.0)
        target = self.player_t_s + seconds
        self.compute_until(target)
        self.player_t_s = target
        return {"ok": True, "operation": "advance", "player_t_s": target}

    def _clock(self, payload):
        if "time_scale" in payload:
            scale = positive("time_scale", payload["time_scale"])
            if scale not in (1., 60., 600., 3600.):
                raise ValueError("time_scale must be one of 1, 60, 600, 3600")
            if scale > self._supported_scale():
                self._assess_max_dt_capacity()
                self._tick_clock()
            actual = min(scale, self._supported_scale())
            if actual != self.time_scale:
                self._compute_samples.clear()
                self._compute_rate_sps = None
            self.time_scale = actual
        if "paused" in payload:
            if not isinstance(payload["paused"], bool):
                raise ValueError("paused must be boolean")
            self.paused = payload["paused"]
        if payload.get("step"):
            self.paused = True
            self.player_t_s += self.frame_interval_s
            self.compute_until(self.player_t_s + self.horizon_s)
        self._last_wall = time.monotonic()
        self._log("clock", {"time_scale": self.time_scale, "paused": self.paused})
        return {"ok": True, "time_scale": self.time_scale, "requested_time_scale": payload.get("time_scale"),
                "max_supported_time_scale": self._supported_scale(),
                "paused": self.paused, "player_t_s": self.player_t_s,
                "clock_held": self._clock_debt_s > 0. and not self.paused,
                "computing": self._clock_debt_s > 0., "clock_debt_s": self._clock_debt_s}

    def _preset(self, payload):
        name = payload.get("name")
        if name not in PRESETS:
            raise ValueError(f"unknown preset {name!r}")
        if name == "measured_weather_day":
            dates = self.measured_dates()
            if not dates:
                raise ValueError("no measured forcing dates available")
            return self._measured({"date": payload.get("date", dates[0])})
        changes = copy.deepcopy(PRESETS[name].get("set", {}))
        if name == "hot_surge":
            source = next((s for s in self.river.sources if "excelsior" in s.id), None)
            if source is None:
                raise ValueError("base build contains no Excelsior source")
            at_s = self._at_time(payload.get("at_s", self.player_t_s))
            self.river.set_forcing(f"source.{source.id}.flow_m3_s", at_s, 2. * self._source_base_flows[source.id])
            self.revision += 1
            self.truncate_after_t_s = at_s
            self.dirty_stages = list(DEPENDENCIES["thermal.excelsior_enabled"])
            self._log("source_surge", {"source_id": source.id, "flow_multiplier": 2., "at_s": at_s,
                                       "solver_config": self.solver_config()})
            self._checkpoints[at_s] = self._checkpoint()
            return {"ok": True, "revision": self.revision, "truncate_after_t_s": at_s, "dirty_stages": self.dirty_stages}
        return self._control({"changes": changes, "at_s": payload.get("at_s", self.player_t_s)})

    def _mark(self, payload):
        at_s = self._at_time(payload.get("at_s", self.player_t_s))
        baseline = LiveEngine(copy.deepcopy(self.river), self.config, cells=self.cells,
            geometry=self.geometry, build_id=self.build_id, claim_ids=self.claim_ids,
            epoch_unix=self.epoch_origin, max_dt_s=self.max_dt_s, time_scale=self.time_scale,
            horizon_s=self.horizon_s, frame_interval_s=self.frame_interval_s)
        baseline.ecology = copy.deepcopy(self.ecology)
        baseline.solutes = copy.deepcopy(self.solutes)
        baseline._frames = [baseline._frame()]
        baseline._checkpoints = {at_s: baseline._checkpoint()}
        self._baseline = baseline
        self._checkpoints[at_s] = self._checkpoint()
        self._log("mark", {"at_s": at_s})
        return {"ok": True, "marked_at_s": at_s}

    def compare(self, at_s=None):
        """Compare branch frames and ecology at the same retained frame time."""
        with self._lock:
            if self._baseline is None:
                raise ValueError("Mark A before comparing branches")
            requested = self.river.time_s if at_s is None else finite("compare at_s", at_s, minimum=0.)
            a_times = {frame["t_s"] for frame in self._baseline._frames if frame["t_s"] <= requested}
            available = [frame["t_s"] for frame in self._frames if frame["t_s"] in a_times]
            if not available:
                raise ValueError("compare time precedes the marked branch")
            sample_time = max(available)
            a = next(frame for frame in self._baseline._frames if frame["t_s"] == sample_time)
            b = next(frame for frame in self._frames if frame["t_s"] == sample_time)
            ar = self._baseline._checkpoints[sample_time]["ecology"]["foodweb"]
            br = self._checkpoints[sample_time]["ecology"]["foodweb"]
            return {"A": copy.deepcopy(a), "B": copy.deepcopy(b),
                    "a_frames": copy.deepcopy(self._baseline._frames), "b_frames": copy.deepcopy(self._frames),
                    "compare_t_s": sample_time, "metrics": {
                "refuge_shift_m": b["trout_summary"]["s_m"] - a["trout_summary"]["s_m"],
                "emergence_change": br["totals"]["emergence"] - ar["totals"]["emergence"],
                "dipper_intake_change": br["totals"]["dipper_eaten"] - ar["totals"]["dipper_eaten"]}}

    def measured_dates(self):
        """List local dates fully covered by frozen river and meteorology forcing."""
        bundle = self.observation_bundle
        if bundle is None:
            return []
        series = [bundle["sites"][UPSTREAM_GAUGE]["series"][key]
                  for key in ("temperature_c", "discharge_m3_s")]
        series += [bundle["sites"][DOWNSTREAM_GAUGE]["series"]["temperature_c"], bundle["met"]["hourly"]]
        start, end = max(rows[0][0] for rows in series), min(rows[-1][0] for rows in series)
        zone = dt.timezone(dt.timedelta(hours=-6))
        day = dt.datetime.fromtimestamp(start, zone).date()
        last = dt.datetime.fromtimestamp(end, zone).date()
        dates = []
        while day <= last:
            midnight = dt.datetime.combine(day, dt.time(), tzinfo=zone).timestamp()
            if start <= midnight and midnight + 86400. <= end:
                dates.append(day.isoformat())
            day += dt.timedelta(days=1)
        return dates

    def _measured(self, payload):
        date = payload.get("date")
        if date not in self.measured_dates():
            raise ValueError("date lies outside frozen measured forcing coverage")
        from yellowstone_python.river.calibrate import fit_forcing_arrays, build_fit_river
        arrays = fit_forcing_arrays(self.observation_bundle, 900.)
        epoch0 = arrays["grid"][0]
        requested = dt.datetime.fromisoformat(date).replace(tzinfo=dt.timezone(dt.timedelta(hours=-6))).timestamp()
        offset = requested - epoch0
        params = self.calibration_params
        reference = build_fit_river(params["volume_m3"], params["area_m2"], arrays["up_q_series"], arrays["up_t_series"],
                                   params["q_lat"], params["t_lat"], arrays["met_series"], params["c_mult"], initial_c=arrays["up_t"][0])
        reference.run(offset, dt_s=900., sample_s=900.)
        at_s = self._at_time(self.player_t_s)
        def shifted(series):
            initial = series.at(offset)
            pairs = [(at_s, initial)] + [(at_s + t - offset, v) for t, v in zip(series.times_s, series.values) if t > offset]
            if at_s > 0.:
                pairs.insert(0, (0., initial))
            return Series(tuple(t for t, _ in pairs), tuple(v for _, v in pairs))
        self.river._boundary_q_series = shifted(arrays["up_q_series"])
        self.river.boundary_c = shifted(arrays["up_t_series"])
        self.river.air_c = shifted(arrays["met_series"]["air_c"])
        self.river.surface_budget = SurfaceBudget(shifted(arrays["met_series"]["rh"]),
            shifted(arrays["met_series"]["wind_mps"]), shifted(arrays["met_series"]["sw"]), shifted(arrays["met_series"]["cloud"]))
        self.river._rebuild_forcing()
        self.config["run_mode"] = "observed_replay"
        self.config["live"]["weather_policy"] = "preserve_published"
        self.config["model_variant_id"] = "mapped_fv_explicit_measured_forcing"
        self.config["scenario_id"] = "observed_replay:" + date
        self.epoch_origin = requested - at_s
        self.measured_reference = {"river": reference, "offset": offset, "marked_at_s": at_s,
                                   "epoch0": epoch0, "grid_s": 900., "date": date}
        self._measured_limit_t_s = at_s + 86400.
        self.revision += 1
        self.truncate_after_t_s = at_s
        self._checkpoints[at_s] = self._checkpoint()
        self._log("measured", {"date": date, "at_s": at_s,
                                "solver_config": self.solver_config()})
        return {"ok": True, "run_mode": "observed_replay", "date": date,
                "revision": self.revision, "truncate_after_t_s": at_s,
                "prescribed_quantities": ["discharge", "upstream_temperature"]}

    def _measured_frame(self):
        from yellowstone_python.river.calibrate import interp_series
        ref = self.measured_reference
        target = ref["offset"] + self.river.time_s - ref["marked_at_s"]
        river = ref["river"]
        while river.time_s + ref["grid_s"] <= target + 1e-9:
            river.run(ref["grid_s"], dt_s=ref["grid_s"], sample_s=ref["grid_s"])
        epoch = ref["epoch0"] + river.time_s
        observed = interp_series(self.observation_bundle["sites"][DOWNSTREAM_GAUGE]["series"]["temperature_c"], [epoch])[0]
        modeled = river.temperature_c[0]
        sample = {"epoch_unix": epoch, "modeled_c": modeled, "observed_c": observed}
        if not self.observation_samples or self.observation_samples[-1]["epoch_unix"] != epoch:
            self.observation_samples.append(sample)
        rmse = math.sqrt(sum((row["modeled_c"] - row["observed_c"]) ** 2 for row in self.observation_samples) / len(self.observation_samples))
        return {**sample, "gauge": DOWNSTREAM_GAUGE, "rmse_c": rmse,
                "model": "calibrate.build_fit_river", "parameters": self.calibration_params,
                "status": self.calibration_params["status"], "prescribed_quantities": ["discharge", "upstream_temperature"]}

    def schema(self):
        """Return control metadata and immutable world geometry for the renderer."""
        controls = [row for row in control_schema(self.config) if row["key"] in DEPENDENCIES]
        for row in controls:
            if row["key"] == "weather.wind_direction_deg":
                row["bound_source"] = "meteorological wind-from bearing: north 0, east 90, south 180, west 270 deg"
        return {"controls": controls, "presets": [
            {"name": name, "description": value["about"],
             "expected_response": value.get("expected_response", value["about"])} for name, value in PRESETS.items()],
            "time_scales": [1, 60, 600, 3600], "frame_interval_s": self.frame_interval_s,
            "max_dt_s": self.max_dt_s, "max_supported_time_scale": self._supported_scale(),
            "build_id": self.build_id, "session_id": self.session_id,
            "cells": copy.deepcopy(self.cells), "river_features": copy.deepcopy(self.geometry.get("river_features", {})),
            "legacy_queries": copy.deepcopy(self.geometry.get("legacy_queries", [])),
            "measured_dates": self.measured_dates(), "player_t_s": self.player_t_s,
            "header": self._header()}

    def command(self, kind, payload):
        """Run a validated command on the model worker and return its result."""
        if self._worker is None or threading.current_thread() is self._worker:
            with self._lock:
                result = getattr(self, "_" + kind)(payload)
                self._publish_snapshot()
                return result
        event = threading.Event()
        result = {}
        self._commands.put((kind, payload, event, result))
        if not event.wait(30.):
            raise RuntimeError("live worker command timed out")
        if "error" in result:
            raise result["error"]
        return result["value"]

    def start(self):
        """Start the model worker and its lookahead maintenance loop."""
        if self._worker is not None:
            return
        self._last_wall = time.monotonic()
        self._worker = threading.Thread(target=self._work, name="yellowstone-live", daemon=True)
        self._worker.start()

    def _work(self):
        try:
            self.compute_until(self.player_t_s + self.horizon_s)
            self._compute_rate_sps = None
            self._compute_samples.clear()
            self._max_dt_samples.clear()
            self._max_dt_capacity_sps = None
            self.compute_until(self.player_t_s + 2. * self.horizon_s)
            if min(self.max_dt_s, max(.1, self.time_scale / 150.)) < self.max_dt_s:
                self._assess_max_dt_capacity()
                self._publish_snapshot()
        except Exception as error:
            self.worker_error = f"{type(error).__name__}: {error}"
            self.paused = True
            self._publish_snapshot()
        self._last_wall = time.monotonic()
        self._clock_started = True
        while not self._stop.is_set():
            try:
                with self._lock:
                    self._publish_snapshot()
                    while not self._commands.empty():
                        kind, payload, event, result = self._commands.get_nowait()
                        try:
                            result["value"] = getattr(self, "_" + kind)(payload)
                            self._publish_snapshot()
                        except Exception as error:
                            result["error"] = error
                        finally:
                            event.set()
                    goal = math.ceil((self.player_t_s + self._clock_debt_s + self.horizon_s) / self.frame_interval_s) * self.frame_interval_s
                    if self.measured_reference is not None:
                        goal = min(goal, self._measured_limit_t_s)
                        if self.player_t_s >= self._measured_limit_t_s:
                            self.player_t_s = self._measured_limit_t_s
                            self.paused = True
                    if self.worker_error is None:
                        self.compute_until(goal)
                    supported = self._supported_scale()
                    if self.time_scale > supported:
                        self.time_scale = supported
                        self._log("clock", {"time_scale": self.time_scale, "paused": self.paused,
                                            "reason": "measured compute headroom"})
                    retained_time = max(self.player_t_s - self.horizon_s,
                        min(self.player_t_s, self.river.time_s,
                            getattr(self, "_client_player_t_s", self.player_t_s)))
                    keep = max((t for t in self._checkpoints if t <= retained_time),
                               default=min(self._checkpoints))
                    self._frames = [frame for frame in self._frames if frame["t_s"] >= keep]
                    self._checkpoints = {t: value for t, value in self._checkpoints.items() if t >= keep}
                    self._weather_cache = {key: value for key, value in self._weather_cache.items() if key[1] >= keep}
                    if self._baseline is not None:
                        self._baseline._frames = [frame for frame in self._baseline._frames if frame["t_s"] >= keep]
                        self._baseline._checkpoints = {t: value for t, value in self._baseline._checkpoints.items() if t >= keep}
                        self._baseline._weather_cache = {key: value for key, value in self._baseline._weather_cache.items() if key[1] >= keep}
                    self._publish_snapshot()
            except Exception as error:
                self.worker_error = f"{type(error).__name__}: {error}"
                self.paused = True
                self._publish_snapshot()
            self._stop.wait(.02)

    def close(self):
        """Stop the worker and preserve the append-only session log."""
        self._stop.set()
        if self._worker is not None:
            self._worker.join(timeout=5.)
        self._log("session_end", {"player_t_s": self.player_t_s, "final_t_s": self.river.time_s,
                                  "solver_config": self.solver_config(), "final_temperature_c": list(self.river.temperature_c),
                                  "integration_segments": self._integration_segments,
                                  "forcing_catalog": self._forcing_catalog})

    def export_scenario(self, path):
        """Write the recorded forcing schedule as a reproducible scenario config."""
        import yaml
        with self._lock:
            document = {"run_mode": "scenario", "live": {"session_id": self.session_id,
                "build_id": self.build_id, "epoch_unix": self.epoch_origin,
                "events": self.session_events, "duration_s": self.river.time_s,
                "dt_s": self._solver_dt_s(),
                "exchange_strategy": "explicit_surface_budget" if self.river.surface_budget else "newton_exchange",
                "model_variant_id": self.config.get("model_variant_id") or ("mapped_fv_explicit" if self.river.surface_budget else "mapped_fv_newton"),
                "scenario_id": self.config.get("scenario_id", self.build_id),
                "display_hour": self.display_hour,
                "initial_state_id": getattr(self, "initial_state_id", None),
                "frame_interval_s": self.frame_interval_s, "solver_config": self.solver_config(),
                "initial_solver_config": self.session_events[0]["solver_config"],
                "integration_segments": self._integration_segments,
                "forcing_catalog": {key: self._forcing_catalog[key]
                                    for key in {segment["forcing_key"] for segment in self._integration_segments}}}}
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
            return destination


def run_exported_scenario(live_config: dict) -> dict:
    """Reproduce a session's numerical step segments and scheduled forcing."""
    from yellowstone_python.river.river_transport import make_replay
    initial = live_config.get("initial_solver_config", live_config["solver_config"])
    river = river_from_config(initial)
    document = make_replay({**initial, "duration_s": 0.})
    frames = [{"t_s": river.time_s, "temperature_c": list(river.temperature_c)}]
    catalog = live_config.get("forcing_catalog", {})
    segments = live_config.get("integration_segments", [])
    if not segments:
        document = make_replay({**live_config["solver_config"],
                               "duration_s": live_config["duration_s"],
                               "dt_s": live_config["dt_s"],
                               "sample_s": live_config["frame_interval_s"]})
    else:
        for segment in segments:
            if abs(segment["start_s"] - river.time_s) > 1e-9:
                raise ValueError("session integration segments must form a continuous clock")
            scheduled = river_from_config({"cells": initial["cells"], **catalog[segment["forcing_key"]]})
            for attr in ("_boundary_q_series", "boundary_c", "air_c", "net_heat_flux", "sources",
                         "surface_budget", "_cell_heat", "_cell_shortwave_multiplier", "surface_relaxation"):
                setattr(river, attr, getattr(scheduled, attr))
            river._rebuild_forcing()
            river.run(segment["end_s"] - river.time_s, dt_s=segment["dt_s"],
                      sample_s=segment["end_s"] - segment["start_s"])
            frames.append({"t_s": river.time_s, "temperature_c": list(river.temperature_c),
                           "q_cells_m3s": list(river._face_flow_at(river.time_s)[1:])})
        document["frames"] = frames
        document["final_budget"] = river.budget()
        document["numerical_checks"]["passed"] = river.budget()["heat_relative_residual"] <= 1e-9
    epoch = live_config["epoch_unix"]
    for frame in document["frames"]:
        frame["epoch_unix"] = epoch + frame["t_s"]
    document["simulation_time"] = {"start_epoch_unix": epoch, "end_epoch_unix": epoch + river.time_s,
                                   "duration_s": river.time_s}
    document["session_id"] = live_config.get("session_id")
    return document
