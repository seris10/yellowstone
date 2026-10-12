import unittest

from yellowstone_python.replay.river_world import (
    Channel,
    build_mapped_replay,
    cell_faces,
    firehole_chain,
    parse_cross_sections,
)

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
        doc = build_mapped_replay(world, ecosystem, duration_s=120.0,
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
            world, ecosystem, duration_s=120.0, maximum_cell_m=25.0,
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
        # Velocity now varies with the profiled area, not one depth.
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
            build_mapped_replay(world, ecosystem, duration_s=60.0,
                                cross_sections={"nope": {"depth_m": 1.0,
                                                         "status": "x"}})

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
        doc = build_mapped_replay(world, ecosystem, duration_s=120.0,
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
                build_mapped_replay(world, ecosystem, duration_s=60.0,
                                    extra_sources=[bad])

    def test_upstream_discharge_mean_drives_boundary(self):
        from yellowstone_python import overland_provider as op
        world, ecosystem = tiny_world_ecosystem()
        result = op.predict_discharge([10.0, 20.0], area_m2=360000.0,
                                      runoff_coefficient=0.5)
        doc = build_mapped_replay(world, ecosystem, duration_s=120.0,
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
            build_mapped_replay(world, ecosystem, duration_s=60.0,
                                upstream_discharge=result)
        with self.assertRaises(ValueError):
            build_mapped_replay(world, ecosystem, duration_s=60.0,
                                upstream_discharge={"method": "x"})


class SilicaDiagnosticTests(unittest.TestCase):
    def test_absent_by_default(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(world, ecosystem, duration_s=60.0)
        self.assertNotIn("silica_diagnostic", doc)

    def test_feature_obs_diagnose_final_temps(self):
        world, ecosystem = tiny_world_ecosystem()
        doc = build_mapped_replay(world, ecosystem, duration_s=60.0,
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
                build_mapped_replay(world, ecosystem, duration_s=60.0,
                                    silica_obs=bad)

if __name__ == "__main__":
    unittest.main()