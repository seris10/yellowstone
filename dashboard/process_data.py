"""Process-specific views of checked outputs and native system datasets."""

from collections import Counter
import math
import struct


def process_views(checked, systems):
    """Describe direct process results without substituting a neighboring process."""
    catalog = {}

    def native(process, system, quantity, label=None, **selection):
        data = systems.get(system)
        if not data:
            return
        field_group, field = next(((group, row) for group in ["variables", "grids", "profiles", "tables"]
                      for row in data[group] if row["id"] == quantity), (None, None))
        if field:
            catalog.setdefault(process, []).append({"id": quantity, "kind": "native", "system": system,
                "quantity": quantity, "field_group": field_group, "label": label or field["label"], **selection})

    def inline(process, identity, label, unit, artifact, description, points=None, times=None, values=None, **extra):
        checked.document(artifact)
        view = {"id": identity, "kind": "series" if times is not None else "values", "label": label,
                "unit": unit, "description": description, "role": "diagnostic",
                "sources": [{"id": identity, "label": label,
                    "sha256": checked.manifest["output_artifact_hashes"][artifact], "origin": "Checked model output"}],
                "support": {"space": "As labeled for each saved result.",
                    "time": "Saved diagnostic; no time series is available.", "time_kind": "static", "uncertainty": "unknown"},
                **extra}
        if times is not None:
            view.update(times=times, values=values)
            view["support"] = {"space": description, "time": "Saved physical seconds from the scenario start.",
                "time_kind": "trajectory", "interval_s": [times[0], times[-1]], "uncertainty": "unknown"}
        else:
            view["points"] = [{"label": str(name).replace("_", " "), "y": value} for name, value in points or []]
        catalog.setdefault(process, []).append(view)
        return view

    for process, system, quantities in [
        ("weather", "atmosphere", ["air_temperature", "wind_speed", "relative_humidity", "cloud_fraction", "precipitation"]),
        ("steam", "atmosphere", ["steam_air_temperature", "steam_relative_humidity", "steam_air_change", "steam_humidity_change", "steam_latent_heat", "steam_sensible_heat"]),
        ("snow", "snow", ["soil_water", "snow_water", "soil_moisture", "snow_depth", "snow_cover", "spinup_accounting"]),
        ("et", "snow", ["reference_et"]),
        ("vegetation", "land", ["biomass", "soil_moisture", "nitrogen", "trampling", "insect_resource", "capacity"]),
        ("mammals", "wildlife", ["activity", "population", "predation_risk"]),
        ("canopy", "canopy", ["height", "core_area", "canopy_coverage", "canopy_valid_support", "crown_density"]),
        ("ground", "thermal", ["ground_heat"]), ("plume", "thermal", ["plume_temperature"]),
        ("outflow_cooling", "thermal", ["outflow_temperature"]),
        ("oxygen", "aquatic", ["oxygen"]), ("periphyton", "aquatic", ["periphyton"]),
        ("fish", "aquatic", ["feeding_brown_trout", "stressor_factors", "thermal_anchors"]),
        ("taxa", "aquatic", ["benthic_stock", "insect_emergence", "disturbance_loss", "ept_resource", "diptera_resource", "emergent_resource"]),
    ]:
        for quantity in quantities:
            native(process, system, quantity)

    thermal = systems.get("thermal", {})
    profiles = thermal.get("profiles", [])
    if profiles:
        first = next((row for row in profiles if "prismatic" in row["label"].lower()), profiles[0])
        native("pool", "thermal", first["id"], "Radial temperature profile", collection="profiles")
    for quantity in ["pool_center", "pool_edge", "pool_radius"]:
        native("pool", "thermal", quantity)

    steam = checked.optional("steam_microclimate.json")
    if steam:
        report = steam["report"]
        for suffix, unit, keys in [("temperature", "°C", ["upwind_air_c", "downwind_air_c"]),
                                   ("humidity", "%", ["upwind_rh", "downwind_rh"])]:
            # Keep both values tied to the same frozen diagnostic, not ambient trajectories.
            inline("steam", "steam_" + suffix, "Upwind and downwind " + suffix, unit, "steam_microclimate.json",
                "Upwind and downwind conditions from the same plume calculation; these are modeled estimates.",
                [(name, report.get(key) * (100 if suffix == "humidity" else 1) if report.get(key) is not None else None)
                 for name, key in zip(["Upwind", "Downwind"], keys)])
        # Put the matched upwind/downwind comparison before individual diagnostic scalars.
        catalog["steam"] = catalog["steam"][-2:] + catalog["steam"][:-2]

    frames_doc = checked.optional("ecosystem.godot.json")
    frames = frames_doc.get("python_series", []) if frames_doc else []
    if frames:
        for reach in frames[0].get("reaches", []):
            values = [next((r.get("temperature_c") for r in f.get("reaches", []) if r["id"] == reach["id"]), None) for f in frames]
            inline("mixing", reach["id"], reach["id"].replace("_", " ").title(), "°C", "ecosystem.godot.json",
                "Flow-weighted temperature for this reporting reach, taken from the channel solver; this is not a separate mixing-model run.",
                times=[f["t_s"] for f in frames], values=values)

    replay_doc = checked.optional("river_replay.json")
    if replay_doc:
        replay = replay_doc["replay"]
        frames = replay["frames"]
        times = [f["t_s"] for f in frames]
        cells = replay["cells"]
        for process, key, title, unit, factor, meaning in [
            ("surface", "surface_exchange_j", "Net surface heat transfer", "MJ", 1e-6,
             "Cumulative heat transferred across the river surface. Positive values warm the water. This run uses lumped Newton exchange, not separate radiation and evaporation outputs."),
            ("hyporheic", "hyporheic_exchange_j", "Channel–storage heat transfer", "MJ", 1e-6,
             "Cumulative heat exchanged with the modeled bed-water store; positive values add heat to the channel."),
            ("outlet", "outlet_export_m3", "Cumulative water export", "m³", 1,
             "Water volume exported at the downstream boundary since the scenario start."),
            ("outlet", "outlet_export_j", "Cumulative sensible heat export", "MJ", 1e-6,
             "Sensible heat exported at the downstream boundary, using the solver's temperature reference."),
        ]:
            if all(key in f.get("budget", {}) for f in frames):
                inline(process, key, title, unit, "river_replay.json", meaning,
                    times=times, values=[f["budget"][key] * factor for f in frames])
        if cells:
            inline("outlet", "outlet_temperature", "Downstream water temperature", "°C", "river_replay.json",
                "Temperature in the last saved channel cell.", times=times, values=[f["temperature_c"][-1] for f in frames])
            catalog["outlet"].insert(0, catalog["outlet"].pop())
            bed = frames[-1].get("budget", {}).get("hyporheic", {}).get("storage_temperature_c")
            if bed is not None:
                if len(bed) != len(cells):
                    raise ValueError("Storage temperature and river cell dimensions differ")
                view = inline("hyporheic", "storage_temperature", "Final bed-water temperature", "°C", "river_replay.json",
                    "Final saved temperature in the storage zone paired with each channel cell.",
                    [(c["id"], value) for c, value in zip(cells, bed)])
                view.update(kind="profile", positions=[c["center_s_m"] for c in cells], values=bed, x_unit="m downstream")
                view["support"]["time"] = f"Final saved state at {times[-1]} seconds after the scenario start."
        forcing = replay.get("forcing", {})
        for key, title, unit in [("boundary_m3_s", "Upstream discharge", "m³/s"), ("boundary_c", "Upstream temperature", "°C")]:
            if isinstance(forcing.get(key), (int, float)):
                inline("boundary", key, title, unit, "river_replay.json", "Prescribed upstream input for this saved scenario.",
                    [("Upstream boundary", forcing[key])], role="driver")
            elif isinstance(forcing.get(key), dict) and forcing[key].get("times_s"):
                row = forcing[key]
                if len(row["times_s"]) != len(row["values"]):
                    raise ValueError("Boundary forcing sample dimensions differ")
                if len(row["times_s"]) == 1:
                    inline("boundary", key, title, unit, "river_replay.json", "Prescribed value held for this saved scenario.",
                           [("Upstream boundary", row["values"][0])], role="driver")
                else:
                    inline("boundary", key, title, unit, "river_replay.json", "Prescribed upstream forcing samples.",
                           times=row["times_s"], values=row["values"], role="driver")
        sources = replay.get("source_connections", [])
        for key, title, unit in [("ecosystem_entry_c", "Baseline source temperature", "°C"), ("ecosystem_flow_m3_s", "Source discharge", "m³/s")]:
            if sources:
                inline("tributaries", key, title, unit, "river_replay.json",
                    "Prescribed source connection values. The baseline temperature does not include a time-dependent intervention.",
                    [(row["source_id"], row.get(key)) for row in sources], role="driver")

    solutes = checked.optional("solute_transport.json")
    if solutes and replay_doc:
        cells_by_id = {row["id"]: row for row in replay_doc["replay"]["cells"]}
        ids = solutes["cell_ids"]
        if any(identity not in cells_by_id for identity in ids):
            raise ValueError("Solute cells are absent from the river geometry")
        for key, unit in [("chloride_mg_l", "mg/L"), ("arsenic_ug_l", "µg/L"), ("boron_mg_l", "mg/L")]:
            values = solutes["concentrations"].get(key)
            if values is None:
                continue
            if len(values) != len(ids):
                raise ValueError("Solute concentration and cell dimensions differ")
            view = inline("solutes", key, key.split("_")[0].title(), unit, "solute_transport.json",
                "Final modeled concentration; source chemistry is incomplete and this run is not field validated.")
            view.update(kind="profile", positions=[cells_by_id[identity]["center_s_m"] for identity in ids], values=values, x_unit="m downstream")
            view["support"]["time"] = f"Final saved profile at {solutes['time_s']} seconds."

    grazer = checked.optional("grazer.json")
    if grazer:
        routes = [{"id": row["id"], "label": row["id"].replace("_", " ").title(), "points": row["path_xz"]}
                  for row in grazer["wildlife"] if row.get("path_xz")]
        if routes:
            view = inline("grazers", "grazer_routes", "Grazing routes", "m", "grazer.json",
                "Authored animal routes, not observed movement tracks.")
            view.update(kind="routes", routes=routes)

    insects = checked.optional("insect_bird.json")
    if insects:
        compartments = insects["compartments"]
        names = {"Nb": "Benthic stock", "Ne": "Emergent stock", "Nt": "Terrestrial stock"}
        inline("insects", "insect_stocks", "Insect compartment stocks", "relative stock", "insect_bird.json",
            "Final compartment model stocks. These are model indices, not measured insect counts.",
            [(names.get(k, k), v) for k, v in compartments["final"].items()])
        inline("aerial", "insect_consumption", "Insect consumption by consumer", "relative stock", "insect_bird.json",
            "Accumulated modeled insect consumption; trout are excluded from this above-water consumer view.",
            [(k.replace("_", " ").title(), v) for k, v in compartments["consumed_total"].items() if k != "trout"])

    predators = checked.optional("piscivores.json")
    if predators:
        for key, title, unit in [("mortality_rate_per_day", "Predation mortality rate", "1/day"), ("depth_m", "Refuge depth", "m")]:
            inline("predation", key, title, unit, "piscivores.json",
                "Authored predation model evaluated at each represented trout refuge; not a measured mortality rate.",
                [(row["trout_id"], row.get(key)) for row in predators["reports"]])

    food = checked.optional("outflow_foodweb.json")
    if food:
        inline("outflow", "fly_rates", "Fly recruitment and losses", "modeled flies/day", "outflow_foodweb.json",
            "Steady modeled rates based on authored mat biomass and discharge variability. These do not measure a local fly population.",
            [("Recruitment", food["recruitment_total_per_day"]), ("Predation", food["predation_total_per_day"]), ("Mite parasitism", food["mite_parasitism_total_per_day"])])
        inline("outflow", "fly_stock", "Fly stock", "modeled flies", "outflow_foodweb.json",
            "Calculated stock from authored biomass and ecological rates; not a field count.", [("Thermal-area flies", food["fly_stock_count"])])

    mat = checked.optional("mat_state.json")
    if mat and checked.has("mat_community.i16"):
        raster = mat["rasters"]["community"]
        payload = checked.binary("mat_community.i16")
        if len(payload) != mat["grid"]["nx"] * mat["grid"]["nz"] * 2 or raster["sha256"] != checked.manifest["output_artifact_hashes"]["mat_community.i16"]:
            raise ValueError("Mat raster support or identity differs")
        counts = Counter(value for (value,) in struct.iter_unpack("<h", payload) if value != raster["nodata"])
        names = {"sinter_dry": "Dry sinter", "brown_green_mixed_photosynthetic": "Brown-green photosynthetic mat",
                 "orange_cyanobacteria_chromatiaceae": "Orange mat: cyanobacteria / Chromatiaceae",
                 "yellow_green_cyanobacteria_chloroflexus": "Yellow-green mat: cyanobacteria / Chloroflexus",
                 "yellow_cyanobacteria": "Yellow cyanobacterial mat", "pink_chemolithotroph": "Pink chemolithotrophs",
                 "white_chemolithotroph": "White chemolithotrophs", "water_hot_clear": "Clear hot water"}
        labels = {row["class_id"]: names.get(row["name"], row["name"].replace("_", " ")) for row in mat["legend"]}
        if counts.keys() - labels.keys():
            raise ValueError("Mat raster has an unknown community class")
        area = mat["grid"]["cell_size_m"] ** 2
        view = inline("mat", "community_area", "Area by modeled surface class", "m²", "mat_state.json",
            "Native classified cell counts multiplied by cell area. Includes non-mat surface classes; colors and community assignments are modeled.",
            [(labels[key], count * area) for key, count in sorted(counts.items())])
        view["sources"].append({"id": "mat-grid", "label": "Classified surface raster", "sha256": raster["sha256"], "origin": "Checked model output"})

    if "mixing" in catalog:
        def amplitude(row):
            values = [value for value in row["values"] if value is not None]
            return max(values) - min(values) if values else 0
        catalog["mixing"].sort(key=amplitude, reverse=True)
    for views in catalog.values():
        for view in views:
            if view["kind"] == "native":
                continue
            numbers = view.get("values", []) + view.get("times", []) + view.get("positions", []) + [row["y"] for row in view.get("points", [])]
            if any(value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)) for value in numbers):
                raise ValueError("Process data requires finite numbers or explicit missing values")
            axis = view.get("times", view.get("positions"))
            if axis is not None and (len(axis) != len(view["values"]) or not axis or
                    any(value is None for value in axis) or any(b <= a for a, b in zip(axis, axis[1:]))):
                raise ValueError("Process sample dimensions or ordering differ")
            for route in view.get("routes", []):
                if any(len(point) != 2 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in point) for point in route["points"]):
                    raise ValueError("Route coordinates must contain finite x/z pairs")
    return catalog
