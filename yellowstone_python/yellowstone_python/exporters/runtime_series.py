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


def python_series(replay: dict, reaches: list[dict], patches: list[dict], weather: dict, *,
                  mammals: dict | None = None, actors=()) -> list[dict]:
    """Build weather, patch and reach trajectories at the replay frame times."""
    epoch = float(replay["simulation_time"]["start_epoch_unix"])
    hour0 = float(replay.get("clock_hour0", 16.2))
    trace = {float(row["t_s"]): row for row in replay.get("weather_trace", [])}
    current = copy.deepcopy(patches)
    previous = 0.0
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
        if time > previous:
            current, _ = patch_step(current, hour, time - previous)
        met = trace.get(time, {})
        air = met.get("air_c", air_temp(hour, weather.get("night_air_c", 7.0),
                                      weather.get("day_warming_c", 15.0),
                                      weather.get("lag_hours", 3.0)))
        wind = met.get("wind_xz_mps", wind_at(time, tuple(weather.get("wind_xz_mps", [1.8, 0.6])),
                                             weather.get("gust_mps", 0.45)))
        output.append({"t_s": time, "epoch_unix": epoch + time,
                       "feeding_by_species": frame["feeding_by_species"],
                       "weather": {"air_temperature_c": air, "air_c": air,
                                   "wind_xz_mps": list(wind),
                                   "relative_humidity": weather.get("humidity", 0.45),
                                   "cloud_fraction": weather.get("cloud", 0.16)},
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
