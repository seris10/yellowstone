import unittest

from river_world import Channel, cell_faces, firehole_chain

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

if __name__ == "__main__":
    unittest.main()