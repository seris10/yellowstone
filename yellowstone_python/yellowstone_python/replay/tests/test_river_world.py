import unittest
from datetime import datetime, timezone

from yellowstone_python.replay.river_transport import Series
from yellowstone_python.replay.river_world import (
    Channel,
    _weather_times,
    add_temperature_pulse,
    build_mapped_replay,
    cell_faces,
    energy_met_series,
    firehole_chain,
    parse_cross_sections,
    parse_simulation_start,
    physical_weather,
    timestamp_metadata,
    validate_source_record,
    validate_weather_configuration,
)
from yellowstone_python.time_utils import epoch_unix_for_local

# Fixed replay epoch so the clock is deterministic across runs.
REPLAY_START = {"simulation_start_epoch_unix": 1784000000.0}

def feature(identifier, upstream, downstream, points):
    return {
        "id": identifier,
        "name": "FIREHOLE RIVER",
        "width": 22.0,
        "endpoint_node_ids": [upstream, downstream],
        "points": points,
    }

class RiverWorldTests(unittest.TestCase):
    def test_chain_uses_nodes_not_input_order(self):
        upstream = feature(
            "upstream", "a", "b",
            [[0, 2, 100], [0, 1, 50]],
        )
        downstream = feature(
            "downstream", "b", "c",
            [[0, 1, 50], [0, 0, 0]],
        )
        chain = firehole_chain({
            "rivers": [downstream, upstream]
        })
        self.assertEqual(
            [row["id"] for row in chain],
            ["upstream", "downstream"],
        )

    def test_original_vertex_chainage_survives_join(self):
        channel = Channel([
            feature("a", "n0", "n1", [[0, 2, 100], [0, 1, 50]]),
            feature("b", "n1", "n2", [[0, 1, 50], [0, 0, 0]]),
        ])
        self.assertEqual(channel.features["b"]["point_s_m"], [50, 100])
        self.assertEqual(channel.position_at(75), [0, 0.5, 25])
        self.assertEqual(channel.chainage_at_z(25), 75)

    def test_declared_junction_with_bad_coordinates_fails(self):
        with self.assertRaises(ValueError):
            Channel([
                feature("a", "n0", "n1", [[0, 2, 100], [0, 1, 50]]),
                feature("b", "n1", "n2", [[1, 1, 50], [0, 0, 0]]),
            ])

    def test_branch_is_rejected(self):
        with self.assertRaises(ValueError):
            firehole_chain({
                "rivers": [
                    feature("a", "n0", "n1", [[0, 0, 2], [0, 0, 1]]),
                    feature("b", "n1", "n2", [[0, 0, 1], [0, 0, 0]]),
                    feature("c", "n1", "n3", [[0, 0, 1], [1, 0, 0]]),
                ]
            })

    def test_ambiguous_legacy_z_is_rejected(self):
        channel = Channel([
            feature(
                "curve", "n0", "n1",
                [[0, 2, 100], [10, 1, 0], [20, 0, 100]],
            )
        ])
        with self.assertRaises(ValueError):
            channel.chainage_at_z(50)

    def test_source_is_exact_face_and_cells_are_bounded(self):
        faces = cell_faces(101.0, [37.0], 20.0)
        self.assertIn(37.0, faces)
        self.assertEqual(faces[0], 0.0)
        self.assertEqual(faces[-1], 101.0)
        self.assertTrue(all(
            0 < b - a <= 20.0
            for a, b in zip(faces, faces[1:])
        ))


def tiny_world_ecosystem():
    world = {
        "georeference": {"note": "test"},
        "rivers": [
            {
                "id": "seg_a",
                "name": "FIREHOLE RIVER",
                "width": 10.0,
                "endpoint_node_ids": ["n0", "n1"],
                "points": [[0, 0, 100], [0, 0, 0]],
            },
            {
                "id": "seg_b",
                "name": "FIREHOLE RIVER",
                "width": 20.0,
                "endpoint_node_ids": ["n1", "n2"],
                "points": [[0, 0, 0], [0, 0, -50]],
            },
        ],
    }
    ecosystem = {
        "boundary_m3s": 5.0,
        "boundary_c": 15.0,
        "clock_hour": 12.0,
        "weather": {},
        "river_reaches": [],
    }
    return world, ecosystem


class CrossSectionTests(unittest.TestCase):
    def test_default_path_uses_assumed_depth_everywhere(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=120.0,
                                  maximum_cell_m=25.0)
        for record in doc["cells"]:
            self.assertEqual(
                record["geometry_status"],
                "mapped_centerline_authored_width_assumed_rectangular_depth")
            self.assertAlmostEqual(
                record["volume_m3"],
                record["length_m"] * record["width_m"] * 1.1)
            self.assertEqual(record["depth_m"], 1.1)
            self.assertEqual(record["depth_status"],
                             "assumed_rectangular_depth_no_bathymetry")
        self.assertTrue(doc["numerical_checks"]["passed"])

    def test_profiles_override_per_feature_volume_and_status(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(
            world, ecosystem, **REPLAY_START, duration_s=120.0, maximum_cell_m=25.0,
            cross_sections={
                "seg_b": {"depth_m": 2.0,
                          "status": "authored_estimate",
                          "source": "hand profile"},
            })
        by_river = {}
        for record in doc["cells"]:
            by_river.setdefault(record["river_id"], []).append(record)
        for record in by_river["seg_a"]:
            self.assertEqual(record["depth_m"], 1.1)
            self.assertIn("assumed", record["geometry_status"])
        for record in by_river["seg_b"]:
            self.assertEqual(record["depth_m"], 2.0)
            self.assertEqual(
                record["geometry_status"],
                "mapped_centerline_authored_width_profile_depth")
            self.assertEqual(record["depth_status"], "authored_estimate")
            self.assertEqual(record["depth_source"], "hand profile")
            self.assertAlmostEqual(
                record["volume_m3"],
                record["length_m"] * 20.0 * 2.0)
        # Velocity varies with the profiled area.
        vel = {rid: rows[0]["representative_velocity_m_s"]
               for rid, rows in by_river.items()}
        self.assertNotAlmostEqual(vel["seg_a"], vel["seg_b"])
        self.assertTrue(doc["numerical_checks"]["passed"])
        self.assertEqual(
            doc["parameter_notes"]["cross_sections"],
            {"seg_b": {"depth_m": 2.0, "status": "authored_estimate",
                       "source": "hand profile"}})

    def test_unknown_feature_rejected(self):
        world, ecosystem = tiny_world_ecosystem()
        with self.assertRaises(ValueError):
            build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                cross_sections={"nope": {"depth_m": 1.0,
                                                         "status": "x"}})

    def test_real_measurement_site_accepts_gauge_id_string(self):
        parsed = parse_cross_sections({
            "seg_a": {"depth_m": 1.0, "status": "ok",
                      "real_measurement_site": "06036805"},
        })
        self.assertEqual(parsed["seg_a"]["real_measurement_site"], "06036805")

    def test_real_measurement_site_rejects_bool_and_bad_strings(self):
        for bad in (True, False, "abc", "123", "12345678901234567",
                    "0603680a", 6036805):
            with self.assertRaises(ValueError, msg=str(bad)):
                parse_cross_sections({
                    "seg_a": {"depth_m": 1.0, "status": "ok",
                              "real_measurement_site": bad},
                })

    def test_bad_profiles_rejected(self):
        for bad in ({"seg_a": {"depth_m": 0.0, "status": "x"}},
                    {"seg_a": {"depth_m": -2.0, "status": "x"}},
                    {"seg_a": {"depth_m": "deep", "status": "x"}},
                    {"seg_a": {"depth_m": 1.0}},
                    {"seg_a": {"depth_m": 1.0, "status": "  "}},
                    {"seg_a": {"depth_m": 1.0, "status": "x",
                               "wobble": 1}}):
            with self.assertRaises(ValueError, msg=str(bad)):
                parse_cross_sections(bad)
        with self.assertRaises(ValueError):
            parse_cross_sections([])


class ProviderInputTests(unittest.TestCase):
    def test_extra_sources_land_in_cells_and_budget(self):
        from yellowstone_python.groundwater_provider import (
            riv_reaches_to_sources, with_chainage)
        world, ecosystem = tiny_world_ecosystem()
        laterals = riv_reaches_to_sources([{
            "source_id": "gw_riv_0", "cell_id": "any",
            "gw_cell": [0, 0, 1], "flow_m3_s": 0.5,
            "temperature_c": 30.0}])
        extra = with_chainage(laterals, {"gw_riv_0": 60.0})
        doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=120.0,
                                  maximum_cell_m=25.0,
                                  extra_sources=extra)
        ids = [s["id"] for s in doc["forcing"]["sources"]]
        self.assertIn("gw_riv_0", ids)
        inventory = doc["hydraulics_summary"]["thermal_inventory"]
        self.assertEqual(inventory["n_sources"], 1)
        self.assertTrue(doc["numerical_checks"]["passed"])

    def test_extra_sources_rejected(self):
        world, ecosystem = tiny_world_ecosystem()
        good = {"id": "gw", "s_m": 10.0, "flow_m3_s": 0.5,
                "temperature_c": 30.0, "status": "s"}
        for bad in ({**good, "s_m": 500.0},
                    {**good, "flow_m3_s": -1.0},
                    {**good, "temperature_c": {"times_s": [1.0],
                                               "values": [1.0]}},
                    {**good, "status": "  "},
                    {**good, "id": ""}):
            with self.assertRaises(ValueError, msg=str(bad)):
                build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                    extra_sources=[bad])

    def test_upstream_discharge_mean_drives_boundary(self):
        from yellowstone_python import overland_provider as op
        world, ecosystem = tiny_world_ecosystem()
        result = op.predict_discharge([10.0, 20.0], area_m2=360000.0,
                                      runoff_coefficient=0.5)
        doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=120.0,
                                  maximum_cell_m=25.0,
                                  upstream_discharge=result)
        self.assertAlmostEqual(doc["forcing"]["boundary_m3_s"], 0.75)
        note = doc["parameter_notes"]["upstream_discharge"]
        self.assertEqual(note["method"], "area_runoff_coefficient")
        self.assertEqual(note["n_steps"], 2)
        self.assertTrue(doc["numerical_checks"]["passed"])

    def test_upstream_discharge_rejected(self):
        from yellowstone_python import overland_provider as op
        world, ecosystem = tiny_world_ecosystem()
        result = op.predict_discharge([10.0], area_m2=100.0)
        del result["method"]
        with self.assertRaises(ValueError):
            build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                upstream_discharge=result)
        with self.assertRaises(ValueError):
            build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                upstream_discharge={"method": "x"})


class SilicaDiagnosticTests(unittest.TestCase):
    def test_absent_by_default(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0)
        self.assertNotIn("silica_diagnostic", doc)

    def test_feature_obs_diagnose_final_temps(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                  silica_obs={"seg_a": 40.0})
        diag = doc["silica_diagnostic"]
        self.assertEqual(diag["n_cells"], len(doc["cells"]))
        pairs = list(zip(doc["cells"], diag["rows"]))
        seg_a = [r for c, r in pairs if c["river_id"] == "seg_a"]
        seg_b = [r for c, r in pairs if c["river_id"] == "seg_b"]
        self.assertTrue(seg_a and seg_b)
        self.assertTrue(all(r["flag"] != "no_observation" for r in seg_a))
        self.assertTrue(all(r["flag"] == "no_observation" for r in seg_b))
        self.assertEqual(diag["n_observed"], len(seg_a))

    def test_bad_obs_rejected(self):
        world, ecosystem = tiny_world_ecosystem()
        for bad in ({"seg_a": -1.0}, {"seg_a": 0.0},
                    {"nope": 10.0}, {"seg_a": "x"}, ["seg_a"]):
            with self.assertRaises(ValueError, msg=str(bad)):
                build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                    silica_obs=bad)


class LandscapePocketTests(unittest.TestCase):
    def test_pockets_do_not_enter_solver_cells(self):
        world, ecosystem = tiny_world_ecosystem()
        pockets = [{
            "id": "pocket_a", "river_id": "seg_a",
            "chainage_m": 50.0, "flow_m3_s": 0.1,
            "temperature_c": 11.5,
            "status": "measured_pocket_illustrative",
        }]
        doc = build_mapped_replay(
            world, ecosystem, **REPLAY_START, duration_s=60.0,
            maximum_cell_m=25.0, landscape_pockets=pockets,
        )
        cell_ids = [cell["id"] for cell in doc["cells"]]
        self.assertNotIn("pocket_a", cell_ids)
        self.assertEqual(doc["landscape_pockets"]["n"], 1)
        record = doc["landscape_pockets"]["records"][0]
        self.assertEqual(record["kind"], "pocket")
        self.assertEqual(record["conservation"], "non_conservative")
        self.assertEqual(len(record["position_xyz"]), 3)
        self.assertTrue(doc["numerical_checks"]["passed"])

    def test_pocket_scheduled_flow_rejected(self):
        world, ecosystem = tiny_world_ecosystem()
        with self.assertRaises(ValueError):
            build_mapped_replay(
                world, ecosystem, **REPLAY_START, duration_s=60.0,
                landscape_pockets=[{
                    "id": "pocket_a", "river_id": "seg_a",
                    "chainage_m": 10.0,
                    "flow_m3_s": {"times_s": [0.0], "values": [0.1]},
                    "temperature_c": 11.5, "status": "x",
                }],
            )

    def test_pocket_conservative_claim_rejected(self):
        world, ecosystem = tiny_world_ecosystem()
        with self.assertRaises(ValueError):
            build_mapped_replay(
                world, ecosystem, **REPLAY_START, duration_s=60.0,
                landscape_pockets=[{
                    "id": "pocket_a", "river_id": "seg_a",
                    "chainage_m": 10.0, "flow_m3_s": 0.1,
                    "temperature_c": 11.5, "status": "x",
                    "conservation": "conservative",
                }],
            )


class ReplayFrameFlowTests(unittest.TestCase):
    def test_frames_carry_per_cell_discharge(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(
            world, ecosystem, **REPLAY_START,
            duration_s=60.0, maximum_cell_m=25.0)
        n_cells = len(doc["cells"])
        for frame in doc["frames"]:
            self.assertIn("q_cells_m3s", frame)
            self.assertEqual(len(frame["q_cells_m3s"]), n_cells)
        # Downstream face flows define each cell's discharge.
        self.assertEqual(
            doc["frames"][0]["q_cells_m3s"],
            doc["face_flow_m3_s"][1:],
        )

    def test_frames_carry_per_cell_depth(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(
            world, ecosystem, **REPLAY_START,
            duration_s=60.0, maximum_cell_m=25.0)
        depths = [record["depth_m"] for record in doc["cells"]]
        for frame in doc["frames"]:
            self.assertIn("depth_m_cells", frame)
            self.assertEqual(frame["depth_m_cells"], depths)

    def test_frames_depth_tracks_profile_overrides(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(
            world, ecosystem, **REPLAY_START,
            duration_s=60.0, maximum_cell_m=25.0,
            cross_sections={
                "seg_b": {"depth_m": 2.0,
                          "status": "authored_estimate",
                          "source": "hand profile"},
            })
        for frame in doc["frames"]:
            for depth, record in zip(frame["depth_m_cells"], doc["cells"]):
                self.assertAlmostEqual(depth, record["depth_m"])


class CellBedElevationTests(unittest.TestCase):
    def test_bed_elevation_is_surface_minus_depth(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(
            world, ecosystem, **REPLAY_START,
            duration_s=60.0, maximum_cell_m=25.0)
        for record in doc["cells"]:
            self.assertIn("bed_elevation_m", record)
            self.assertAlmostEqual(
                record["bed_elevation_m"],
                record["position_xyz"][1] - record["depth_m"],
            )

    def test_bed_elevation_reflects_profile_depth(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(
            world, ecosystem, **REPLAY_START,
            duration_s=60.0, maximum_cell_m=25.0,
            cross_sections={
                "seg_b": {"depth_m": 2.0,
                          "status": "authored_estimate",
                          "source": "hand profile"},
            })
        for record in doc["cells"]:
            expected = record["position_xyz"][1] - record["depth_m"]
            self.assertAlmostEqual(record["bed_elevation_m"], expected)
            if record["river_id"] == "seg_b":
                self.assertAlmostEqual(record["depth_m"], 2.0)
class SimulationClockTests(unittest.TestCase):
    def test_start_requires_timezone(self):
        with self.assertRaises(ValueError):
            parse_simulation_start(simulation_start_utc="2026-07-15T22:20:00")

    def test_start_normalizes_to_utc(self):
        result = parse_simulation_start(
            simulation_start_utc="2026-07-15T16:20:00-06:00")
        self.assertEqual(result.isoformat(), "2026-07-15T22:20:00+00:00")

    def test_start_accepts_z_suffix(self):
        result = parse_simulation_start(
            simulation_start_utc="2026-07-15T22:20:00Z")
        self.assertEqual(result.isoformat(), "2026-07-15T22:20:00+00:00")

    def test_start_rejects_two_representations(self):
        with self.assertRaises(ValueError):
            parse_simulation_start(
                simulation_start_utc="2026-07-15T22:20:00Z",
                simulation_start_epoch_unix=1784000000.0,
            )

    def test_start_required_by_replay(self):
        world, ecosystem = tiny_world_ecosystem()
        with self.assertRaises(ValueError):
            build_mapped_replay(world, ecosystem, duration_s=60.0)

    def test_epoch_and_utc_agree(self):
        by_text = parse_simulation_start(
            simulation_start_utc="2026-07-15T22:20:00Z")
        by_epoch = parse_simulation_start(
            simulation_start_epoch_unix=by_text.timestamp())
        self.assertEqual(by_epoch, by_text)

    def test_metadata_covers_the_run(self):
        meta = timestamp_metadata(
            parse_simulation_start(simulation_start_utc="2026-07-15T22:20:00Z"),
            7200.0,
        )
        self.assertEqual(meta["start_utc"], "2026-07-15T22:20:00Z")
        self.assertEqual(meta["duration_s"], 7200.0)
        self.assertAlmostEqual(
            meta["end_epoch_unix"] - meta["start_epoch_unix"], 7200.0)

    def test_local_epoch_round_trip(self):
        epoch = epoch_unix_for_local("2026-07-15", 16.5, -6.0)
        start = datetime.fromtimestamp(epoch, tz=timezone.utc)
        self.assertEqual((start.day, start.hour, start.minute), (15, 22, 30))

    def test_local_epoch_rejects_bad_hour(self):
        with self.assertRaises(ValueError):
            epoch_unix_for_local("2026-07-15", 24.0, -6.0)

    def test_replay_document_carries_the_clock(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(
            world, ecosystem, simulation_start_utc="2026-07-15T22:20:00Z",
            duration_s=120.0, maximum_cell_m=25.0)
        self.assertEqual(doc["simulation_time"]["start_utc"],
                         "2026-07-15T22:20:00Z")
        self.assertAlmostEqual(
            doc["forcing_time_reference"]["start_epoch_unix"],
            doc["simulation_time"]["start_epoch_unix"])
        self.assertIn("air_temperature", doc["weather_forcing"])
        self.assertEqual(
            doc["parameter_notes"]["simulation_time"]["authority"],
            "UTC epoch timestamp")

    def test_sample_interval_below_time_step_rejected(self):
        world, ecosystem = tiny_world_ecosystem()
        with self.assertRaises(ValueError):
            build_mapped_replay(
                world, ecosystem, **REPLAY_START,
                duration_s=60.0, dt_s=5.0, sample_s=2.0)


class WeatherScheduleTests(unittest.TestCase):
    def test_weather_times_include_exact_final_time(self):
        self.assertEqual(_weather_times(125.0, 60.0),
                         [0.0, 60.0, 120.0, 125.0])

    def test_weather_times_land_on_final_time(self):
        self.assertEqual(_weather_times(120.0, 60.0), [0.0, 60.0, 120.0])

    def test_scheduled_air_temperature_is_used(self):
        ecosystem = {
            "clock_hour": 12.0,
            "weather": {
                "air_temperature_c": {
                    "times_s": [0.0, 60.0],
                    "values": [2.0, 12.0],
                }
            },
        }
        series, records = physical_weather(
            ecosystem, duration_s=120.0, interval_s=60.0)
        self.assertAlmostEqual(series.at(0.0), 2.0)
        self.assertAlmostEqual(series.at(60.0), 12.0)
        self.assertAlmostEqual(records[-1]["t_s"], 120.0)
        self.assertEqual(records[0]["air_source"],
                         "scheduled_weather.air_temperature_c")

    def test_authored_curve_still_used_without_schedule(self):
        _, records = physical_weather(
            {"clock_hour": 12.0, "weather": {}}, duration_s=60.0)
        self.assertEqual(records[0]["air_source"],
                         "authored_diurnal_approximation")

    def test_budget_honors_scheduled_met(self):
        ecosystem = {
            "clock_hour": 12.0,
            "weather": {
                "relative_humidity": {"times_s": [0.0, 60.0],
                                      "values": [0.2, 0.9]},
                "wind_speed_mps": {"times_s": [0.0, 60.0],
                                   "values": [1.0, 9.0]},
                "cloud_fraction": {"times_s": [0.0, 60.0],
                                   "values": [0.0, 1.0]},
                "shortwave_w_m2": {"times_s": [0.0, 60.0],
                                   "values": [100.0, 800.0]},
            },
        }
        spec = energy_met_series(ecosystem, duration_s=60.0,
                                 interval_s=60.0)
        self.assertAlmostEqual(spec["rh"]["values"][0], 0.2)
        self.assertAlmostEqual(spec["rh"]["values"][-1], 0.9)
        self.assertAlmostEqual(spec["wind_mps"]["values"][-1], 9.0)
        self.assertAlmostEqual(spec["shortwave_w_m2"]["values"][-1], 800.0)
        self.assertAlmostEqual(spec["cloud"]["values"][-1], 1.0)

    def test_weather_configuration_rejects_out_of_range(self):
        ecosystem = {"weather": {"humidity": 1.4}}
        with self.assertRaises(ValueError):
            validate_weather_configuration(ecosystem)

    def test_weather_configuration_rejects_bad_wind(self):
        with self.assertRaises(ValueError):
            validate_weather_configuration({"weather": {"wind_xz_mps": [1.0]}})


class SourceForcingTests(unittest.TestCase):
    def test_temperature_pulse_preserves_schedule(self):
        source = Series((0.0, 100.0), (60.0, 70.0))
        result = add_temperature_pulse(
            source, start_s=30.0, end_s=80.0, delta_c=10.0)
        self.assertEqual(result.times_s, (0.0, 30.0, 80.0, 100.0))
        self.assertAlmostEqual(result.at(0.0), 60.0)
        self.assertAlmostEqual(result.at(30.0), 70.0)
        self.assertAlmostEqual(result.at(50.0), 70.0)
        self.assertAlmostEqual(result.at(80.0), 60.0)

    def test_temperature_pulse_follows_a_step_change(self):
        source = Series((0.0, 100.0), (62.0, 70.0))
        result = add_temperature_pulse(
            source, start_s=30.0, end_s=80.0, delta_c=10.0)
        self.assertAlmostEqual(result.at(10.0), 62.0)
        self.assertAlmostEqual(result.at(60.0), 72.0)
        self.assertAlmostEqual(result.at(120.0), 70.0)

    def test_temperature_pulse_requires_ordered_window(self):
        source = Series((0.0, 10.0), (60.0, 10.0))
        with self.assertRaises(ValueError):
            add_temperature_pulse(source, start_s=80.0, end_s=30.0, delta_c=5.0)

    def test_temperature_pulse_rejects_above_upper_guard(self):
        source = Series((0.0, 100.0), (60.0, 70.0))
        with self.assertRaisesRegex(ValueError, "upper guard"):
            add_temperature_pulse(
                source, start_s=30.0, end_s=80.0, delta_c=120.0)

    def test_scheduled_source_flow_is_rejected(self):
        source = {
            "id": "source_a",
            "flow_m3s": {"times_s": [0.0, 60.0], "values": [1.0, 2.0]},
            "temperature_c": 20.0,
        }
        with self.assertRaises(ValueError) as caught:
            validate_source_record(source, "test source")
        self.assertIn("cannot be scheduled", str(caught.exception))

    def test_scheduled_source_temperature_is_accepted(self):
        source = {
            "id": "source_a",
            "flow_m3s": 0.25,
            "temperature_c": {"times_s": [0.0, 900.0],
                              "values": [62.0, 80.0]},
        }
        validate_source_record(source, "test source")

    def test_duplicate_reach_ids_rejected(self):
        world, ecosystem = tiny_world_ecosystem()
        ecosystem["river_reaches"] = [{"id": "a"}, {"id": "a"}]
        with self.assertRaises(ValueError):
            build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0)

    def test_mapped_replay_rejects_scheduled_source_flow(self):
        world, ecosystem = tiny_world_ecosystem()
        ecosystem["river_reaches"] = [{
            "id": "r1",
            "lateral_sources": [{
                "id": "src",
                "flow_m3s": {"times_s": [0.0], "values": [1.0]},
                "temperature_c": 20.0,
            }],
        }]
        with self.assertRaises(ValueError):
            build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0)

    def test_feature_at_rejects_chainage_past_the_channel(self):
        world, _ = tiny_world_ecosystem()
        channel = Channel(firehole_chain(world))
        with self.assertRaises(ValueError):
            channel.feature_at(channel.length_m + 1.0)

    def test_feature_records_are_ordered_downstream(self):
        world, _ = tiny_world_ecosystem()
        channel = Channel(firehole_chain(world))
        starts = [record["start_s_m"] for record in channel._feature_records]
        self.assertEqual(starts, sorted(starts))


if __name__ == "__main__":
    unittest.main()