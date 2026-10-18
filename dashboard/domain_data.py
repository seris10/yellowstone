"""Checked scientific datasets for public system workbenches."""

from __future__ import annotations

import hashlib
import json
import math
import struct
from datetime import datetime
from pathlib import Path


SYSTEMS = {
    "atmosphere": ("Atmosphere", "Scenario weather and the effect of hot water on downwind air.", "#8dcaca"),
    "snow": ("Snow and soil water", "Water stored in each snow and soil patch.", "#b8b4e9"),
    "thermal": ("Geothermal systems", "Temperature and heat flow around thermal features.", "#efa774"),
    "land": ("Terrestrial ecology", "Vegetation and resource stocks by patch.", "#8ed5aa"),
    "aquatic": ("Aquatic ecology", "River habitat and modeled food resources.", "#e2b6d1"),
    "wildlife": ("Wildlife", "Modeled mammal activity and authored population equivalents.", "#efbc78"),
    "canopy": ("Forest canopy", "Crown detections and canopy structure derived from LiDAR.", "#9ad58c"),
}


def _number(value):
    """Return a finite number or preserve an explicit missing value."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Scientific values must be finite numbers or null")
    return value


def _support(space, time="One saved state; no time series is available.", kind="static", interval=None):
    result = {"space": space, "time": time, "time_kind": kind, "uncertainty": "unknown"}
    if interval is not None:
        result["interval_s"] = list(interval)
    return result


class CheckedBuild:
    """Read artifacts with verified manifest hashes."""

    def __init__(self, build):
        self.path = Path(build).resolve()
        self.manifest = json.loads((self.path / "BUILD.json").read_text())
        self.cache = {}
        if self.manifest.get("checks_passed") is not True:
            raise ValueError("System datasets require a checked build")
        if self.document("CHECKS.json").get("passed") is not True:
            raise ValueError("Model checks failed")

    def has(self, name):
        return name in self.manifest.get("output_artifact_hashes", {})

    def binary(self, name):
        target = (self.path / name).resolve()
        if not target.is_relative_to(self.path) or not self.has(name):
            raise ValueError("Artifact is outside the checked build")
        payload = target.read_bytes()
        if hashlib.sha256(payload).hexdigest() != self.manifest["output_artifact_hashes"][name]:
            raise ValueError(f"Artifact hash mismatch: {name}")
        return payload

    def document(self, name):
        if name not in self.cache:
            self.cache[name] = json.loads(self.binary(name))
        return self.cache[name]

    def optional(self, name):
        return self.document(name) if self.has(name) else None

    def source(self, data, name, identity, label, origin="Checked model output"):
        if not any(item["id"] == identity for item in data["sources"]):
            data["sources"].append({"id": identity, "label": label,
                                    "sha256": self.manifest["output_artifact_hashes"][name], "origin": origin})
        return identity


def _dataset(checked, identity):
    title, summary, color = SYSTEMS[identity]
    return {"schema": "yellowstone.system.v1", "id": identity,
            "snapshot": checked.manifest["build_id"], "title": title, "summary": summary, "color": color,
            "epoch": checked.manifest["config"]["simulation"]["start_utc"],
            "run_mode": checked.manifest["run_mode"], "sources": [], "entities": [], "variables": [],
            "grids": [], "series": [], "profiles": [], "tables": [], "notes": [],
            "coordinates": "Local meters: x east, z south; height above the local vertical origin.",
            "scientific_acceptance": "Field validation remains incomplete."}


def _variable(data, identity, label, unit, source, description, support, role="direct_output", **extra):
    data["variables"].append({"id": identity, "label": label, "unit": unit, "role": role,
                              "description": description, "support": support, "source_id": source, **extra})


def _entity(identity, label, kind, position=None, **extra):
    x, z = (None, None) if position is None else position
    return {"id": identity, "label": label, "kind": kind, "x": _number(x), "z": _number(z), "values": {}, **extra}


def _series(data, identity, variable, entity_id, times, values, source, label=None, support=None):
    if not times:
        return
    if len(times) != len(values) or any(_number(t) is None for t in times):
        raise ValueError("Time-series dimensions differ")
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Saved times must increase")
    metadata = next(item for item in data["variables"] if item["id"] == variable)
    data["series"].append({"id": identity, "label": label or metadata["label"], "variable_id": variable,
                           "entity_id": entity_id, "unit": metadata["unit"], "role": metadata["role"],
                           "description": metadata["description"], "source_id": source,
                           "support": support or _support(metadata["support"]["space"],
                               "Instantaneous saved states at physical seconds from the UTC epoch.",
                               "trajectory", [times[0], times[-1]]),
                           "times": times, "values": [_number(value) for value in values]})


def _table(data, identity, label, columns, rows, **extra):
    data["tables"].append({"id": identity, "label": label,
                           "columns": [{"id": key, "label": title, "unit": unit} for key, title, unit in columns],
                           "rows": rows, **extra})


def _grid(data, identity, label, unit, source, description, grid, values, role="direct_output", support=None, **extra):
    nx, nz = grid["nx"], grid["nz"]
    if not isinstance(nx, int) or isinstance(nx, bool) or not isinstance(nz, int) or isinstance(nz, bool) or nx <= 0 or nz <= 0:
        raise ValueError("Grid dimensions must be positive integers")
    if values and isinstance(values[0], list):
        if len(values) != nz or any(len(row) != nx for row in values):
            raise ValueError("Grid row dimensions differ")
        values = [value for row in values for value in row]
    if len(values) != nx * nz:
        raise ValueError("Grid dimensions differ")
    spacing = grid.get("cell_m", grid.get("cell_size_m"))
    if _number(spacing) is None or spacing <= 0:
        raise ValueError("Grid spacing must be positive")
    origin = grid["origin_xz_m"]
    if len(origin) != 2 or any(_number(value) is None for value in origin):
        raise ValueError("Grid origin must contain two coordinates")
    order = grid.get("row_order")
    if order not in ["south_increases", "north_to_south", "z_increasing"]:
        raise ValueError("Grid orientation is unsupported")
    data["grids"].append({"id": identity, "label": label, "unit": unit, "role": role,
                          "description": description, "source_id": source,
                          "support": support or _support("Native grid cells; x east and z south."),
                          "grid": {"nx": nx, "nz": nz, "cell_m": spacing, "origin_xz_m": origin,
                                   "row_order": "z_increasing"},
                          "values": [_number(value) for value in values], **extra})


def _float_grid(checked, name, grid):
    payload = checked.binary(name)
    if len(payload) != grid["nx"] * grid["nz"] * 4:
        raise ValueError("Raster byte dimensions differ")
    return [None if math.isnan(value) else _number(value) for (value,) in struct.iter_unpack("<f", payload)]


def _frames(checked):
    document = checked.optional("ecosystem.godot.json")
    if document is None:
        return []
    frames = document.get("python_series", [])
    times = [frame["t_s"] for frame in frames]
    if any(_number(t) is None for t in times) or any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("Ecosystem saved times must increase")
    epoch = datetime.fromisoformat(checked.manifest["config"]["simulation"]["start_utc"].replace("Z", "+00:00")).timestamp()
    if any("epoch_unix" in frame and not math.isclose(frame["epoch_unix"], epoch + frame["t_s"], rel_tol=0, abs_tol=1e-6) for frame in frames):
        raise ValueError("Ecosystem physical times differ from the scenario epoch")
    return frames


def _atmosphere(checked, frames):
    data = _dataset(checked, "atmosphere")
    weather = checked.optional("weather.json")
    snapshot = checked.optional("weather_snapshot.json")
    entity = _entity("weather-forcing", "Scenario weather", "forcing")
    data["entities"].append(entity)
    source = None
    if frames:
        source = checked.source(data, "ecosystem.godot.json", "ecosystem", "Saved ecosystem trajectory", "Authored meteorological forcing")
        times = [frame["t_s"] for frame in frames]
        specs = [("air_temperature", "Air temperature", "C", "air_temperature_c"),
                 ("relative_humidity", "Relative humidity", "fraction", "relative_humidity"),
                 ("cloud_fraction", "Cloud cover", "fraction", "cloud_fraction"),
                 ("precipitation", "Precipitation rate", "mm/h", "precip_mm_h"),
                 ("wind_speed", "Wind speed", "m/s", None),
                 ("wind_x", "Eastward wind", "m/s", None), ("wind_z", "Southward wind", "m/s", None)]
        for identity, label, unit, key in specs:
            values = []
            for frame in frames:
                weather_frame = frame.get("weather", {})
                vector = weather_frame.get("wind_xz_mps", [None, None])
                if not isinstance(vector, list) or len(vector) != 2:
                    raise ValueError("Saved wind vectors must have two components")
                if key:
                    value = weather_frame.get(key)
                elif identity == "wind_speed":
                    value = math.hypot(*vector) if all(_number(component) is not None for component in vector) else None
                else:
                    value = vector[0 if identity == "wind_x" else 1]
                values.append(value)
            description = "Magnitude calculated as hypot(eastward wind, southward wind) from saved prescribed wind components." if identity == "wind_speed" else "Scenario weather input, not a record of local observations."
            _variable(data, identity, label, unit, source, description,
                      _support("Scenario-wide atmospheric forcing.", "Initial saved state.", "instantaneous", [times[0], times[0]]),
                      "diagnostic" if identity == "wind_speed" else "driver")
            entity["values"][identity] = _number(values[0])
            _series(data, "weather_" + identity, identity, entity["id"], times, values, source)
        data["notes"].append("Weather values are authored scenario forcing. Saved changes do not establish observed weather accuracy.")
    elif weather:
        source = checked.source(data, "weather.json", "weather", "Weather forcing diagnostic", "Authored meteorological forcing")
        trace = weather.get("wind_trace_60s", [])
        for identity, label, unit, key in [("air_temperature", "Air temperature", "C", "air_c"),
                                           ("wind_x", "Eastward wind", "m/s", "wind_x"),
                                           ("wind_z", "Southward wind", "m/s", "wind_z")]:
            if not trace:
                continue
            _variable(data, identity, label, unit, source, "Authored short diagnostic forcing trace.", _support("Scenario-wide forcing."), "driver")
            entity["values"][identity] = _number(trace[0].get(key))
            _series(data, "weather_" + identity, identity, entity["id"], [row["t"] for row in trace], [row.get(key) for row in trace], source)
    if snapshot:
        source = checked.source(data, "weather_snapshot.json", "weather-initial", "Initial atmospheric state", "Authored weather with calculated solar geometry")
        _table(data, "weather_initial", "Initial weather and solar geometry",
               [("quantity", "Quantity", ""), ("value", "Value", ""), ("unit", "Unit", ""), ("basis", "Basis", "")],
               [{"quantity": label, "value": snapshot.get(section, {}).get(key), "unit": unit, "basis": basis}
                for section, key, label, unit, basis in [
                    ("weather", "dewpoint_c", "Dew point", "C", "Calculated from authored weather"),
                    ("weather", "visibility_m", "Visibility", "m", "Authored"),
                    ("weather", "cloud_base_agl_m", "Cloud base", "m above ground", "Authored"),
                    ("solar", "solar_elevation_deg", "Solar elevation", "degree", "Calculated solar geometry"),
                    ("solar", "solar_azimuth_deg", "Solar azimuth", "degree", "Calculated solar geometry")]])
    steam = checked.optional("steam_microclimate.json")
    if steam:
        source = checked.source(data, "steam_microclimate.json", "steam", "Steam microclimate diagnostic", "Transferred structure with authored rates")
        item = _entity("steam-adjustment", "Downwind steam adjustment", "diagnostic")
        data["entities"].append(item)
        for identity, key, label, unit in [("steam_air_change", "delta_air_c", "Downwind air warming", "C"),
                                            ("steam_humidity_change", "delta_specific_humidity", "Specific humidity increase", "kg/kg"),
                                            ("steam_latent_heat", "latent_flux_w_m2", "Latent heat flux", "W/m2"),
                                            ("steam_sensible_heat", "sensible_flux_w_m2", "Sensible heat flux", "W/m2")]:
            _variable(data, identity, label, unit, source, "One modeled plume adjustment; no spatial weather field is available.",
                      _support("Combined modeled hot-water source area and downwind fetch."), "diagnostic")
            item["values"][identity] = _number(steam["report"].get(key))
    return data


def _patches(checked, frames, identity):
    data = _dataset(checked, identity)
    if frames:
        patches = frames[0].get("patches", [])
        source = checked.source(data, "ecosystem.godot.json", "ecosystem", "Saved ecosystem trajectory")
        times = [frame["t_s"] for frame in frames]
    else:
        document = checked.optional("patch_state.json")
        if document is None:
            return data
        patches = document["patches"]
        source = checked.source(data, "patch_state.json", "patch-state", "Patch state")
        times = []
    if identity == "snow":
        specs = [("snow_water", "Snow water equivalent", "mm", "snow_mm", "Water-equivalent snow storage."),
                 ("soil_water", "Soil water storage", "mm", "soil_mm", "Water depth in the shared soil bucket."),
                 ("soil_moisture", "Soil moisture", "fraction", "moisture", "Relative soil water availability."),
                 ("snow_depth", "Snow depth", "m", "snow_depth_m", "Modeled geometric snow depth."),
                 ("snow_cover", "Snow cover", "fraction", "snow_cover_fraction", "Patch snow-covered fraction.")]
    else:
        specs = [("biomass", "Vegetation biomass", "relative index", "biomass", "Normalized vegetation stock; not measured dry mass."),
                 ("insect_resource", "Insect resource", "relative index", "insect_resource", "Relative patch food resource; not an organism count."),
                 ("soil_moisture", "Soil moisture", "fraction", "moisture", "Shared soil-bucket water availability."),
                 ("nitrogen", "Nitrogen stock", "kg/ha", "nitrogen_kg_ha", "Modeled patch nitrogen stock with authored inputs."),
                 ("trampling", "Trampling damage", "relative index", "trampling_damage", "Modeled grazing disturbance index."),
                 ("capacity", "Biomass capacity", "relative index", "capacity", "Authored normalized carrying capacity.")]
    for key, label, unit, native, description in specs:
        _variable(data, key, label, unit, source, description,
                  _support("Individual authored land patch; display radius is not catchment area.",
                           "Initial state after declared preparation and snow/soil spin-up.", "instantaneous", [0, 0]),
                  "authored_parameter" if key == "capacity" else "direct_output")
    frames_by_patch = [{patch["id"]: patch for patch in frame.get("patches", [])} for frame in frames]
    for patch in patches:
        entity = _entity(patch["id"], patch["id"].replace("_", " ").title(), "patch", patch.get("center_xz"),
                         category=patch.get("habitat", "patch"), display_radius_m=patch.get("radius_m"))
        entity["values"] = {key: _number(patch.get(native)) for key, _, _, native, _ in specs}
        data["entities"].append(entity)
        for key, label, _, native, _ in specs:
            if times:
                _series(data, patch["id"] + "_" + key, key, patch["id"], times,
                        [frame.get(patch["id"], {}).get(native) for frame in frames_by_patch], source,
                        entity["label"] + ": " + label)
    if identity == "snow":
        season = checked.optional("season.json")
        if season and season.get("ledger"):
            source = checked.source(data, "season.json", "spinup", "Land water spin-up accounting")
            ledger = season["ledger"]
            keys = [("initial_mm", "Initial storage"), ("rain_mm", "Rain input"), ("accum_mm", "Snow input"),
                    ("et_mm", "Evapotranspiration"), ("surface_runoff_mm", "Liquid surface drainage"),
                    ("subsurface_drain_mm", "Subsurface drainage"), ("snow_export_mm", "Solid snow export"),
                    ("sublimation_mm", "Sublimation"), ("final_mm", "Final storage"), ("water_residual_mm", "Water residual")]
            _table(data, "spinup_accounting", "Spin-up accounting: sum of patch depths",
                   [("quantity", "Quantity", ""), ("value", "Depth sum", "mm"), ("phase", "Phase", "")],
                   [{"quantity": label, "value": _number(ledger.get(key)),
                     "phase": "solid" if key == "snow_export_mm" else "unavailable" if key == "sublimation_mm" else "water equivalent"}
                    for key, label in keys], source_id=source,
                   support=_support("Numerical sum of modeled patch depths; not an area-weighted basin balance.",
                                    "Pre-experiment snow/soil spin-up interval.", "interval",
                                    [ledger["interval_start_s"], ledger["interval_end_s"]]))
            data["notes"].append("Spin-up accounting sums patch depths. Without contributing areas, these sums cannot be converted to basin water volume.")
        et = checked.optional("evapotranspiration.json")
        if et:
            source = checked.source(data, "evapotranspiration.json", "reference-et", "Reference evapotranspiration", "Authored weather diagnostic")
            _variable(data, "reference_et", "Reference evapotranspiration", "mm/day", source,
                      "Reference atmospheric water demand. Actual water loss is accounted for in the snow and soil model.",
                      _support("Scenario reference surface."), "diagnostic")
            item = _entity("reference-et", "Reference surface", "diagnostic")
            item["values"]["reference_et"] = _number(et.get("et0_mm_d"))
            data["entities"].append(item)
    else:
        floor = checked.optional("forest_floor.json")
        if floor:
            source = checked.source(data, "forest_floor.json", "forest-floor", "Forest floor placement", "Authored display representatives")
            _table(data, "floor_context", "Forest floor display primitives",
                   [("kind", "Primitive", ""), ("count", "Count", "display primitives")],
                   [{"kind": kind.replace("_", " "), "count": count} for kind, count in floor.get("diagnostics", {}).get("counts", {}).items()], source_id=source)
            data["notes"].append("Forest floor counts describe authored display geometry; they do not measure understory density or tree mortality.")
    data["notes"].extend(["Patch centers and display radii are authored. Patch radius does not establish hydrologic contributing area.",
                          "Saved trajectories retain physical time. The earlier spin-up is a separate integration interval."])
    return data


def _thermal(checked):
    data = _dataset(checked, "thermal")
    heat = checked.optional("ground_heat.json")
    if heat:
        source = checked.source(data, "ground_heat.json", "ground-heat", "Ground heat field", "Authored magnitudes and mapped thermal pattern")
        _grid(data, "ground_heat", "Ground heat flux", "W/m2", source,
              "Authored heat-flux classes follow thermal aprons; this is not a measured heat-flux survey.", heat["grid"], heat["values_w_m2"], "authored_parameter")
    plume = checked.optional("plume_field.json")
    if plume:
        source = checked.source(data, "plume_field.json", "plume", "Steady thermal plume")
        xs, zs = plume["axes_x_m"], plume["axes_z_m"]
        if len(xs) != plume["nx"] or len(zs) != plume["nz"] or len(xs) < 2 or len(zs) < 2:
            raise ValueError("Plume axes differ from the grid")
        dx, dz = xs[1] - xs[0], zs[1] - zs[0]
        if not math.isclose(dx, dz, rel_tol=1e-10) or dx <= 0:
            raise ValueError("Plume grid spacing is unsupported")
        if any(not math.isclose(b - a, dx, rel_tol=1e-10) for a, b in zip(xs, xs[1:])) or any(not math.isclose(b - a, dz, rel_tol=1e-10) for a, b in zip(zs, zs[1:])):
            raise ValueError("Plume axes must be uniform")
        _grid(data, "plume_temperature", "Steady plume temperature", "C", source,
              "Steady two-dimensional advection-dispersion diagnostic; it is separate from the time-dependent channel solver.",
              {"nx": len(xs), "nz": len(zs), "cell_m": dx, "origin_xz_m": [xs[0] - dx / 2, zs[0] - dz / 2], "row_order": "z_increasing"},
              plume["temperature_grid_c"], "diagnostic", _support("Native sample nodes; display pixels extend halfway to neighboring samples, not physical control-volume bounds."),
              metadata={"sampling": "sample_nodes", "native_axis_x_m": xs, "native_axis_z_m": zs})
    outflow = checked.optional("outflow_temperature.json")
    if outflow and checked.has("outflow_temperature.f32"):
        raster_sha = checked.manifest["output_artifact_hashes"]["outflow_temperature.f32"]
        if outflow.get("sha256") != raster_sha:
            raise ValueError("Outflow raster metadata hash differs")
        source = checked.source(data, "outflow_temperature.f32", "outflow-temperature", "Native outflow temperature raster", "Modeled steady field; field validation incomplete")
        checked.source(data, "outflow_temperature.json", "outflow-support", "Outflow temperature support")
        _grid(data, "outflow_temperature", "Outflow temperature", "C", source,
              "Steady temperature calculated along routed outflows. Dry and unsupported pixels remain missing.",
              outflow["grid"], _float_grid(checked, "outflow_temperature.f32", outflow["grid"]),
              support=_support("Native wet cells on the thermal outflow grid.", "Steady field at the scenario forcing epoch; no trajectory.", "static"))
    pools = checked.optional("pools_state.json")
    world = checked.optional("world.runtime.json")
    if pools:
        source = checked.source(data, "pools_state.json", "pool-state", "Authored pool temperature profiles", "Authored steady pool parameters")
        locations = {}
        if world:
            checked.source(data, "world.runtime.json", "geography", "Mapped pool geography", "Mapped geographic inputs")
            locations = {item["id"]: item for item in world.get("pools", [])}
        for identity, label, unit, description in [
            ("pool_center", "Pool center temperature", "C", "Authored steady radial-profile center temperature."),
            ("pool_edge", "Pool edge temperature", "C", "Authored steady radial-profile edge temperature."),
            ("pool_radius", "Equivalent pool radius", "m", "Equivalent-area water radius; not a measured radial cross section.")]:
            _variable(data, identity, label, unit, source, description, _support("Individual mapped pool with authored radial structure."), "authored_parameter")
        for pool in pools["pools"]:
            mapped = locations.get(pool["id"], {})
            center = mapped.get("center")
            item = _entity(pool["id"], pool["name"].strip().title() or "Unnamed pool", "pool", [center[0], center[2]] if center else None,
                           category="thermal pool" if mapped.get("thermal") else "pool")
            item["values"] = {"pool_center": _number(pool["t_center_c"]), "pool_edge": _number(pool["t_edge_c"]), "pool_radius": _number(pool["r_water_m"])}
            data["entities"].append(item)
            name = "pool_ramps/ramp_" + pool["id"] + ".json"
            if checked.has(name):
                ramp = checked.document(name)
                profile_source = checked.source(data, name, "radial-" + pool["id"], item["label"] + " radial samples", "Authored radial structure")
                samples = ramp["samples"]
                positions = [_number(row["r_m"]) for row in samples]
                if any(b <= a for a, b in zip(positions, positions[1:])):
                    raise ValueError("Pool radial positions must increase")
                data["profiles"].append({"id": "radial_" + pool["id"], "label": item["label"] + ": radial temperature",
                    "unit": "C", "role": "authored_parameter", "description": "Authored radial temperature samples; submerged geometry is unmeasured.",
                    "support": _support("Radius from pool center; authored profile, not a measured transect."),
                    "source_id": profile_source, "entity_id": item["id"], "axis": {"id": "radius", "label": "Radius", "unit": "m"},
                    "positions": positions, "values": [_number(row["t_c"]) for row in samples]})
    data["notes"].extend(["Ground heat magnitudes, source discharges, and pool radial temperatures include authored assumptions.",
                          "Steady outflow, plume, and pool fields do not represent a common evolving temperature trajectory.",
                          "Missing raster pixels remain missing. Display sample areas are not additional physical observations."])
    return data


def _aquatic(checked, frames):
    data = _dataset(checked, "aquatic")
    replay = checked.optional("river_replay.json")
    if not replay:
        return data
    source = checked.source(data, "river_replay.json", "river-geometry", "Finite-volume channel geometry", "Mapped centerline with authored widths and depths")
    cells = replay["replay"]["cells"]
    by_id = {}
    for cell in cells:
        item = _entity(cell["id"], "Channel " + cell["id"].rsplit("_", 1)[-1], "river cell",
                       [cell["position_xyz"][0], cell["position_xyz"][2]], bounds_m=[cell["start_s_m"], cell["end_s_m"]],
                       metadata={"chainage_m": cell["center_s_m"]})
        by_id[item["id"]] = item
        data["entities"].append(item)
    specs = [
        ("river_oxygen.json", "oxygen", "oxygen", "Dissolved oxygen", "mg/L", "do_mg_l_by_cell",
         "Saved oxygen profile. The integration step is not an observation window."),
        ("periphyton.json", "periphyton", "periphyton", "Periphyton biomass", "mg C/m2", "biomass_mg_c_m2_by_cell",
         "Saved periphyton biomass after its stated integration step. A time series is unavailable.")]
    for name, source_id, identity, label, unit, field, description in specs:
        document = checked.optional(name)
        if document:
            source = checked.source(data, name, source_id, label + " profile")
            _variable(data, identity, label, unit, source, description, _support("Native channel cells; paired by stable cell identity."),
                      integration_step_s=document.get("dt_s"))
            for key, item in by_id.items():
                item["values"][identity] = _number(document[field].get(key))
    food = checked.optional("aquatic_foodweb.json")
    if food:
        source = checked.source(data, "aquatic_foodweb.json", "foodweb", "Aquatic food-web state", "Transferred structure with authored rates")
        duration = food["foodweb"].get("simulated_days", food["foodweb"].get("days", 0)) * 86400
        support = _support("Native channel cells under a quasi-steady thermal landscape.",
                           "Final saved food-web state after its independent integration interval.", "interval", [0, duration])
        for identity, label, key in [("ept_resource", "Mayfly, stonefly and caddisfly resource", "ept"),
                                      ("diptera_resource", "Dipteran resource", "dipt"),
                                      ("emergent_resource", "Emergent insect resource", "ne")]:
            _variable(data, identity, label, "relative stock", source, "Relative model food resource; not a measured organism density.", support)
            for row in food["foodweb"]["per_cell"]:
                if row["id"] in by_id:
                    by_id[row["id"]]["values"][identity] = _number(row.get(key))
        rows = []
        for row in food["foodweb"].get("stressor_factors_last_step", []):
            rows.append({key: row.get(key) for key in ["cell_id", "thermal_only_U", "combined_stressor_factor", "do_factor", "solute_factor", "predation_factor"]})
        _table(data, "stressor_factors", "Fish suitability factors",
               [("cell_id", "Channel cell", ""), ("thermal_only_U", "Thermal utility", "relative index"),
                ("combined_stressor_factor", "Combined factor", "fraction"), ("do_factor", "Oxygen factor", "fraction"),
                ("solute_factor", "Solute factor", "fraction"), ("predation_factor", "Predation factor", "fraction")], rows, source_id=source, support=support)
    benthic = checked.optional("benthic_grid.json")
    if benthic:
        source = checked.source(data, "benthic_grid.json", "benthic", "Benthic insect grid", "Transferred structure with authored rates")
        for identity, key, label in [("benthic_stock", "nb", "Benthic insect stock"),
                                    ("insect_emergence", "emergence", "Insect emergence"),
                                    ("disturbance_loss", "disturbance_loss", "Disturbance loss")]:
            _variable(data, identity, label, "relative stock", source, "Independent benthic model increment; absent cells remain missing.",
                      _support("Declared benthic channel subset."), integration_step_s=benthic.get("dt_s"))
            if len(benthic[key]) != len(benthic["cell_ids"]):
                raise ValueError("Benthic cell dimensions differ")
            for key_id, value in zip(benthic["cell_ids"], benthic[key]):
                if key_id in by_id:
                    by_id[key_id]["values"][identity] = _number(value)
    fish = checked.optional("fish.json")
    if fish:
        source = checked.source(data, "fish.json", "fish-thermal", "Fish thermal response anchors", "Literature transfer with authored response shapes")
        _table(data, "thermal_anchors", "Species thermal anchors",
               [("species", "Species", ""), ("t_opt_lo_c", "Optimum lower", "C"), ("t_opt_hi_c", "Optimum upper", "C"),
                ("t_feed_zero_c", "Feeding cutoff", "C"), ("t_refuge_c", "Refuge anchor", "C"), ("t_uilt_c", "Upper incipient lethal anchor", "C")],
               [{"species": key.replace("_", " ").title(), **{field: value for field, value in row.items() if field.startswith("t_")}}
                for key, row in fish.get("thermal_species", {}).items()], source_id=source)
    if frames and frames[0].get("feeding_by_species"):
        source = checked.source(data, "ecosystem.godot.json", "ecosystem", "Saved ecosystem trajectory")
        times = [frame["t_s"] for frame in frames]
        for species in frames[0]["feeding_by_species"]:
            identity = "feeding_" + species
            _variable(data, identity, species.replace("_", " ").title() + " feeding", "relative index", source,
                      "Temperature-dependent feeding response from species-specific thermal anchors; not observed consumption.",
                      _support("Native channel cells at the initial saved physical time.", "Initial saved state.", "instantaneous", [times[0], times[0]]), "diagnostic")
            for index, cell in enumerate(cells):
                if len(frames[0]["feeding_by_species"][species]) != len(cells):
                    raise ValueError("Feeding and channel dimensions differ")
                by_id[cell["id"]]["values"][identity] = _number(frames[0]["feeding_by_species"][species][index])
                if species == "brown_trout":
                    values = []
                    for frame in frames:
                        row = frame.get("feeding_by_species", {}).get(species)
                        if row is not None and len(row) != len(cells):
                            raise ValueError("Feeding and channel dimensions differ")
                        values.append(row[index] if row is not None else None)
                    _series(data, cell["id"] + "_brown_trout_feeding", identity, cell["id"], times, values, source,
                            by_id[cell["id"]]["label"] + ": brown trout feeding")
        data["notes"].append("Brown trout feeding retains every saved time and channel cell. Other species retain their initial spatial response and thermal anchors.")
    data["notes"].extend(["Oxygen, periphyton, benthic insects, and the food web have separate temporal support; their frozen profiles cannot be advanced with the river clock.",
                          "Relative prey stocks and feeding scores are model indices. They do not establish organism counts, survival, or field abundance."])
    return data


def _wildlife(checked, frames):
    data = _dataset(checked, "wildlife")
    document = checked.optional("mammals.json")
    if document is None:
        return data
    source = checked.source(data, "mammals.json", "mammals", "Mammal initial state and encounter routes", "Authored population proxies and display representatives")
    mammals = frames[0].get("ecology", {}).get("mammals", document["mammals"]) if frames else document["mammals"]
    catalog = checked.optional("mammal_catalogue.json")
    names = {}
    if catalog:
        checked.source(data, "mammal_catalogue.json", "mammal-catalogue", "Mammal occurrence and guild catalogue", "Primary park inventory with authored model traits")
        names = {row["species_id"]: row for row in catalog["species"]}
    specs = [("activity", "Activity", "relative index", "activity_index", "Authored guild response to habitat, season, and physical state."),
             ("population", "Population equivalents", "authored equivalents", "population_equivalents", "Authored proxy stock; not measured local animal abundance."),
             ("predation_risk", "Predation risk", "relative index", "predation_risk_index", "Guild-level modeled predation response with authored rates."),
             ("speed_multiplier", "Movement multiplier", "relative index", "speed_multiplier", "Authored encounter movement multiplier; not observed locomotion.")]
    for identity, label, unit, _, description in specs:
        _variable(data, identity, label, unit, source, description, _support("Individual display representative or species guild, as labeled.", "Initial saved state.", "instantaneous", [0, 0]))
    routes = {item["id"]: item for item in document.get("encounters", {}).get("actors", [])}
    for actor_id, actor in mammals.get("actors", {}).items():
        route = routes.get(actor_id, {})
        path = route.get("path_xz", [])
        item = _entity(actor_id, actor.get("kind", "mammal").replace("_", " ").title() + " " + actor_id.rsplit("_", 1)[-1],
                       "display representative", path[0] if path else None, category=actor.get("kind", "mammal"),
                       path_xz=path, metadata={"species_id": actor.get("species_id"), "patch_id": actor.get("patch_id"),
                           "position_basis": "Authored route start; not a tracked animal position.",
                           "route_qualified": route.get("route_support", {}).get("qualified")})
        item["values"] = {identity: _number(actor.get(key)) for identity, _, _, key, _ in specs if identity != "population"}
        data["entities"].append(item)
    for species_id, species in mammals.get("species", {}).items():
        record = names.get(species_id, {})
        label = ", ".join(record.get("common_names", [])[:1]) or species_id.replace("_", " ").title()
        item = _entity(species_id, label, "species guild", category=record.get("traits", {}).get("mammal_guild", "mammal"),
                       metadata={"scientific_name": record.get("scientific_name"), "park_occurrence": species.get("supported_park_occurrence"),
                                 "local_abundance": "unmeasured", "eligible_patch_ids": species.get("eligible_local_patches", [])})
        item["values"] = {identity: _number(species.get(key)) for identity, _, _, key, _ in specs if identity != "speed_multiplier"}
        data["entities"].append(item)
    if frames:
        series_source = checked.source(data, "ecosystem.godot.json", "ecosystem", "Saved ecosystem trajectory")
        times = [frame["t_s"] for frame in frames]
        for item in data["entities"]:
            field = "actors" if item["kind"] == "display representative" else "species"
            for identity, label, _, native, _ in specs:
                if identity not in item["values"]:
                    continue
                values = [frame.get("ecology", {}).get("mammals", {}).get(field, {}).get(item["id"], {}).get(native) for frame in frames]
                _series(data, item["id"] + "_" + identity, identity, item["id"], times, values, series_source,
                        item["label"] + ": " + label)
    _table(data, "population_by_patch", "Authored population equivalents by patch",
           [("patch", "Patch", ""), ("species", "Species", ""), ("value", "Population equivalents", "authored equivalents")],
           [{"patch": patch.replace("_", " ").title(), "species": (names.get(species, {}).get("common_names") or [species.replace("_", " ")])[0], "value": _number(value)}
            for patch, rows in mammals.get("by_patch", {}).items() for species, value in rows.items()], source_id=source)
    data["notes"].extend(["Park occurrence is distinct from local abundance. Population equivalents and encounter locations are authored.",
                          "Map points mark route starts. Route geometry does not establish an observed animal track or a time-dependent position.",
                          "Guild stocks and activity retain saved physical time. Their ecological rates remain uncalibrated."])
    return data


def _canopy(checked):
    data = _dataset(checked, "canopy")
    census = checked.optional("census.json")
    if census:
        source = checked.source(data, "census.json", "crown-census", "Dominant crown census", "USGS 3DEP 2020 LiDAR; derived crown detections, field validation unavailable")
        payload = census["payload"]
        support = _support("Detected dominant crown and its conservative crown core.", "2020 LiDAR acquisition; not the scenario epoch.", "static")
        for identity, label, unit, description in [
            ("height", "Detected crown height", "m", "LiDAR-derived height above ground at the detected dominant crown."),
            ("core_area", "Conservative crown core area", "m2", "Watershed and nearest-peak consensus area; full crown area remains unknown."),
            ("core_radius", "Equivalent crown core radius", "m", "Equivalent-area radius of the conservative core; not full crown width.")]:
            _variable(data, identity, label, unit, source, description, support)
        seen = set()
        for tree in payload["trees"]:
            identity = tree["stable_id"]
            if identity in seen:
                raise ValueError("Canopy crown identities must be unique")
            seen.add(identity)
            item = _entity(identity, identity.replace("census_lidar_", "Crown ").replace("_", " / "), "dominant crown", [tree["x"], tree["z"]])
            item["values"] = {"height": _number(tree.get("height_m")), "core_area": _number(tree.get("crown_area_m2")), "core_radius": _number(tree.get("crown_r_m"))}
            data["entities"].append(item)
        _table(data, "crown_density", "Dominant crown detections by reporting area",
               [("area", "Reporting area", ""), ("area_ha", "Area", "ha"), ("count", "Detected crowns", "count"), ("density", "Dominant crown density", "crowns/ha")],
               [{"area": key.replace("_", " "), "area_ha": row["area_ha"], "count": row["n"], "density": row["trees_per_ha"]}
                for key, row in payload.get("density", {}).items()], source_id=source)
        data["metadata"] = {"acquisition_start": payload.get("source", {}).get("acquisition_start"),
                            "acquisition_end": payload.get("source", {}).get("acquisition_end"),
                            "validation_availability": payload.get("validation_availability", "unknown"),
                            "count_scope": "Dominant crown detections; total and subcanopy stems unknown."}
    metadata = checked.optional("lidar_canopy/unresolved_render_canopy.json")
    if metadata and checked.has("lidar_canopy/cover_fraction.f32") and checked.has("lidar_canopy/valid_fraction.f32"):
        source = checked.source(data, "lidar_canopy/cover_fraction.f32", "canopy-cover", "Native canopy beyond crown cores", "Aggregated LiDAR surface after conservative crown-core exclusion")
        valid_source = checked.source(data, "lidar_canopy/valid_fraction.f32", "canopy-valid", "Native LiDAR support fraction", "Observed source support")
        checked.source(data, "lidar_canopy/unresolved_render_canopy.json", "canopy-grid", "Canopy grid support")
        grid = {"nx": metadata["width"], "nz": metadata["height"], "cell_m": metadata["cell_size_m"],
                "origin_xz_m": metadata["extent_m"][:2], "row_order": "z_increasing"}
        for key in ["cover_fraction", "valid_fraction"]:
            if metadata["artifacts"][key]["sha256"] != checked.manifest["output_artifact_hashes"]["lidar_canopy/" + key + ".f32"]:
                raise ValueError("Canopy raster metadata hash differs")
        valid = _float_grid(checked, "lidar_canopy/valid_fraction.f32", grid)
        cover = _float_grid(checked, "lidar_canopy/cover_fraction.f32", grid)
        _grid(data, "canopy_coverage", "Canopy outside crown cores", "fraction", source,
              "Observed above-threshold surface after conservative crown-core exclusion, as a fraction of each native grid cell. This is not total canopy cover. Zero valid source support remains missing.", grid,
              [value if fraction is not None and fraction > 0 else None for value, fraction in zip(cover, valid)],
              support=_support("Native aggregated residual LiDAR surface cells; conservative crown-core circles are excluded. Valid support is a separate field.", "2020 acquisition support; static field.", "static"),
              metadata={"valid_support_source_id": valid_source, "missing_rule": "Missing where valid support is zero or unavailable."})
        _grid(data, "canopy_valid_support", "Valid LiDAR support", "fraction", valid_source,
              "Fraction of each aggregated grid cell supported by usable source pixels; zero is not evidence of canopy absence.", grid, valid,
              support=_support("Native aggregated LiDAR support cells.", "2020 acquisition support; static field.", "static"))
    data["notes"].extend(["LiDAR detections describe dominant crowns. They do not identify species or establish total or subcanopy stem counts.",
                          "Conservative crown cores are separate from canopy coverage. Overlapping display crowns cannot be summed as measured cover.",
                          "The canopy surface grid excludes conservative crown cores. Zero residual surface does not establish canopy absence.",
                          "The LiDAR acquisition precedes the scenario epoch. Local detection error and field validation metrics remain unavailable."])
    return data


def _validate_dataset(data):
    entities = [item["id"] for item in data["entities"]]
    if len(entities) != len(set(entities)):
        raise ValueError("System entity identities must be unique")
    identities = [item["id"] for group in ["variables", "grids", "series", "profiles"] for item in data[group]]
    if len(identities) != len(set(identities)):
        raise ValueError("System field identities must be unique")
    sources = {item["id"] for item in data["sources"]}
    for group in ["variables", "grids", "series", "profiles"]:
        for item in data[group]:
            if item["source_id"] not in sources:
                raise ValueError("System field source is absent")
            if "entity_id" in item and item["entity_id"] not in entities:
                raise ValueError("System field entity is absent")
    for item in data["entities"]:
        if (item["x"] is None) != (item["z"] is None):
            raise ValueError("Entity coordinates must both be finite or absent")


def _prune_unavailable(data):
    data["series"] = [item for item in data["series"] if any(value is not None for value in item["values"])]
    available = {item["variable_id"] for item in data["series"]}
    available.update(key for item in data["entities"] for key, value in item["values"].items() if value is not None)
    missing = [item for item in data["variables"] if item["id"] not in available]
    if missing:
        data["unavailable"] = [{"id": item["id"], "label": item["label"], "reason": "No finite values are supplied in this generation."} for item in missing]
        data["variables"] = [item for item in data["variables"] if item["id"] in available]
        for item in data["entities"]:
            item["values"] = {key: value for key, value in item["values"].items() if key in available}


def export_systems(build: Path, root: Path | None = None) -> dict:
    """Extract native scientific fields from hash-checked selected-build artifacts."""
    checked = CheckedBuild(build)
    frames = _frames(checked)
    datasets = [_atmosphere(checked, frames), _patches(checked, frames, "snow"), _thermal(checked),
                _patches(checked, frames, "land"), _aquatic(checked, frames), _wildlife(checked, frames), _canopy(checked)]
    result = {}
    for data in datasets:
        _prune_unavailable(data)
        if data["variables"] or data["grids"] or data["series"] or data["tables"]:
            known = [item["id"] for item in data["variables"]]
            for item in data["entities"]:
                for identity in known:
                    item["values"].setdefault(identity, None)
            _validate_dataset(data)
            result[data["id"]] = data
    return result


def attach_system_datasets(snapshot: dict, datasets: dict) -> dict:
    """Bind the public catalog to sanitized content-addressed dataset bytes."""
    files = {}
    descriptors = []
    for identity, dataset in datasets.items():
        if dataset["snapshot"] != snapshot["snapshot"] or dataset["id"] != identity:
            raise ValueError("System dataset identity differs from the public snapshot")
        payload = (json.dumps(dataset, separators=(",", ":"), allow_nan=False) + "\n").encode()
        if len(payload) >= 24 * 1024 * 1024:
            raise ValueError(f"System dataset exceeds the publication size limit: {identity}")
        sha = hashlib.sha256(payload).hexdigest()
        path = f"data/{identity}-{sha}.json"
        files[path] = payload
        descriptors.append({key: dataset[key] for key in ["id", "title", "summary", "color"]} |
                           {"url": "/dashboard/" + path, "sha256": sha, "bytes": len(payload),
                            **{key: len(dataset[key]) for key in ["entities", "variables", "grids", "series", "profiles"]}})
    snapshot.setdefault("datasets", {})["systems"] = descriptors
    return files
