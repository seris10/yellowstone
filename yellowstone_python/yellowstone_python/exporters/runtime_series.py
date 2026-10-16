"""Replay-derived reach summaries and Python trajectories for Godot playback."""
from __future__ import annotations

import copy

from yellowstone_python.atmosphere.microclimate import air_temp, wind_at
from yellowstone_python.aquatic.fish import thermal_performance, THERMAL_SPECIES
from yellowstone_python.land.vegetation import patch_step
from yellowstone_python.common.mammal_forcing import environmental_forcing, apply_consumption


def reach_summaries(replay: dict, reaches: list[dict], frame: dict | None = None) -> list[dict]:
    """Return flow-weighted reach temperatures from mapped chainage cells."""
    frame = frame if frame is not None else replay["frames"][-1]
    cells = replay["cells"]
    queries = {row["reach_id"]: float(row["s_m"]) for row in replay["legacy_queries"]}
    centers = [queries[reach["id"]] for reach in reaches]
    limits = [float(cells[0]["start_s_m"])]
    limits += [(a + b) / 2.0 for a, b in zip(centers, centers[1:])]
    limits += [float(cells[-1]["end_s_m"])]
    flows = frame.get("q_cells_m3s", [cell["q_out_m3_s"] for cell in cells])
    result = copy.deepcopy(reaches)
    for index, reach in enumerate(result):
        selected = [i for i, cell in enumerate(cells)
                    if limits[index] <= float(cell["center_s_m"]) < limits[index + 1]]
        if not selected:
            raise ValueError(f"reach {reach['id']} has no mapped replay cells")
        total_flow = sum(float(flows[i]) for i in selected)
        reach["temperature_c"] = sum(float(frame["temperature_c"][i]) * float(flows[i])
                                     for i in selected) / total_flow
        reach["flow_m3s"] = total_flow / len(selected)
        reach["temperature_source"] = "river_transport.flow_weighted_cells"
        reach["fish_activity"] = thermal_performance(reach["temperature_c"], "brown_trout")["feeding"]
    return result


def replay_weather(replay: dict, weather: dict, time_s: float) -> dict:
    """Sample the published forcing and weather trace at physical time."""
    from yellowstone_python.river.river_transport import Series, SurfaceBudget
    from bisect import bisect_right
    hour = (float(replay.get("clock_hour0", 16.2)) + time_s / 3600.0) % 24.0
    forcing = replay.get("forcing", {})
    air = Series.parse(forcing["air_c"]).at(time_s) if "air_c" in forcing else air_temp(
        hour, weather.get("night_air_c", 7.0), weather.get("day_warming_c", 15.0), weather.get("lag_hours", 3.0))
    wind = list(wind_at(time_s, tuple(weather.get("wind_xz_mps", [1.8, .6])), weather.get("gust_mps", .45)))
    trace = replay.get("weather_trace", [])
    if trace:
        times = [float(row["t_s"]) for row in trace]
        index = max(0, bisect_right(times, time_s) - 1)
        a, b = trace[index], trace[min(index + 1, len(trace) - 1)]
        span = float(b["t_s"]) - float(a["t_s"])
        weight = (time_s - float(a["t_s"])) / span if span > 0.0 else 0.0
        wind = [float(x) + (float(y) - float(x)) * weight for x, y in zip(a["wind_xz_mps"], b["wind_xz_mps"])]
    humidity, cloud = weather.get("humidity", .45), weather.get("cloud", .16)
    if forcing.get("surface_budget"):
        met = SurfaceBudget.parse(forcing["surface_budget"]).met_at(time_s, air)
        humidity, cloud = met.rh, met.cloud
    return {"air_temperature_c": air, "air_c": air, "wind_xz_mps": wind,
            "relative_humidity": humidity, "cloud_fraction": cloud,
            "precip_mm_h": weather.get("precip_mm_h", 0.0), "clock_hour": hour}


def python_series(replay: dict, reaches: list[dict], patches: list[dict], weather: dict, *,
                  mammals: dict | None = None, actors=(),
                  thermal_flux_mm_d_by_patch: dict | None = None) -> list[dict]:
    """Build weather, patch and reach trajectories at the replay frame times."""
    epoch = float(replay["simulation_time"]["start_epoch_unix"])
    hour0 = float(replay.get("clock_hour0", 16.2))
    trace = {float(row["t_s"]): row for row in replay.get("weather_trace", [])}
    current = copy.deepcopy(patches)
    previous = 0.0
    last_land_s = 0.0
    output = []
    mammal_model = None
    if mammals and mammals.get("enabled", False):
        from yellowstone_python.land.mammals import MammalEcology
        mammal_model = MammalEcology(current, actors=actors, seed=mammals.get("seed", 54173))
    for frame in replay["frames"]:
        time = float(frame["t_s"])
        frame["epoch_unix"] = epoch + time
        frame["feeding_by_species"] = {
            species: [thermal_performance(float(temperature), species)["feeding"]
                      for temperature in frame["temperature_c"]]
            for species in THERMAL_SPECIES
        }
        hour = (hour0 + time / 3600.0) % 24.0
        met = replay_weather(replay, weather, time)
        if time - last_land_s >= 3600.0:
            from yellowstone_python.land.snow_season import step_land
            import math
            current, land_ledger = step_land(current, time - last_land_s, met["air_c"],
                met["precip_mm_h"] * 24.0, math.hypot(*met["wind_xz_mps"]),
                interval_start_s=last_land_s, thermal_flux_mm_d_by_patch=thermal_flux_mm_d_by_patch)
            last_land_s = time
        if time > previous:
            current, _ = patch_step(current, hour, time - previous)
        output.append({"t_s": time, "epoch_unix": epoch + time,
                       "feeding_by_species": frame["feeding_by_species"], "weather": met,
                       "patches": copy.deepcopy(current),
                       "reaches": reach_summaries(replay, reaches, frame)})
        if mammal_model is not None:
            forcing = environmental_forcing(current, output[-1]["weather"], epoch + time)
            report = mammal_model.step(time - previous, forcing)
            current, ledger = apply_consumption(current, report["consumption_by_patch"])
            report["vegetation_coupling"] = ledger
            output[-1]["patches"] = copy.deepcopy(current)
            output[-1]["ecology"] = {"mammals": report}
        previous = time
    return output


def mapped_comparison(replay: dict) -> dict:
    """Hold mapped state and forcing fixed while removing one temperature pulse."""
    import copy
    from yellowstone_python.common.provenance import sha256_json
    from yellowstone_python.river.river_transport import Series, river_from_config
    intervention = replay["intervention"]
    control_config = copy.deepcopy(replay["solver_config"])
    changed = 0
    for source in control_config["sources"]:
        if source["id"] == intervention["source_id"]:
            schedule = source["temperature_c"]
            schedule["values"] = [value - intervention["delta_c"]
                if intervention["start_s"] <= time < intervention["end_s"] else value
                for time, value in zip(schedule["times_s"], schedule["values"])]
            changed += 1
    if changed != 1:
        raise ValueError("comparison requires exactly one source intervention")
    river = river_from_config(control_config)
    frames = river.run(control_config["duration_s"], dt_s=control_config["dt_s"], sample_s=control_config["sample_s"])
    pulse_frames = replay["frames"]
    if [r["t_s"] for r in frames] != [r["t_s"] for r in pulse_frames]:
        raise ValueError("comparison clocks differ")
    deltas = [max(abs(a-b) for a,b in zip(control["temperature_c"], pulse["temperature_c"]))
              for control, pulse in zip(frames, pulse_frames)]
    if any(delta > 1e-11 for delta, frame in zip(deltas, frames) if frame["t_s"] <= intervention["start_s"]):
        raise ValueError("comparison initial trajectory differs before intervention")
    if max(deltas) <= 1e-6:
        raise ValueError("intervention has no downstream response")
    budget = river.budget()
    if budget["water_relative_residual"] > 1e-12 or budget["heat_relative_residual"] > 1e-7:
        raise ValueError("comparison budget closure failed")
    source_cell = next(s["cell_id"] for s in control_config["sources"] if s["id"] == intervention["source_id"])
    index = next(i for i,c in enumerate(replay["cells"]) if c["id"] == source_cell)
    probe_index = min(index + 3, len(replay["cells"]) - 1)
    schedule = next(s["temperature_c"] for s in replay["solver_config"]["sources"] if s["id"] == intervention["source_id"])
    series = Series.parse(schedule)
    return {"schema": "yellowstone.portfolio_comparison.v1", "intervention": intervention,
            "model_variant_id": "mapped_fv_explicit" if control_config.get("surface_budget") else "mapped_fv_newton",
            "control_scenario_id": sha256_json(control_config), "intervention_input_id": replay["input_sha256"],
            "probe_cell": replay["cells"][probe_index], "control_budget": budget,
            "initial_state": "same resolved equilibrium cells; identical nonintervention forcing",
            "frames": [{"t_s": c["t_s"], "control_c": c["temperature_c"][probe_index],
                        "intervention_c": p["temperature_c"][probe_index], "input_c": series.at(c["t_s"])}
                       for c,p in zip(frames,pulse_frames)],
            "maximum_delta_c": max(deltas), "preintervention_tolerance_c": 1e-11,
            "scientific_status": "scenario_numerical_experiment_not_field_validation"}
