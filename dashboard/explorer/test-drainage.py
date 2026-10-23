"""Source-bound and synthetic tests for the DEM drainage export."""
import hashlib
import os
import importlib.util
import json
from collections import deque
from pathlib import Path
import unittest

import numpy as np

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('drainage', HERE / 'export-drainage.py')
drainage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(drainage)


class SyntheticTests(unittest.TestCase):
    def test_depression_fills_to_spill_without_mutating_source(self):
        dem = np.full((7, 7), 10.0)
        dem[1:-1, 1:-1] = 0
        original = dem.copy()
        routed = drainage.route(dem)
        np.testing.assert_array_equal(dem, original)
        np.testing.assert_array_equal(routed['filled'], np.full((7, 7), 10))
        self.assertEqual(routed['area'][routed['receiver'] < 0].sum(), 576)
        self.assertFalse(drainage.visible_links(dem, routed).any())

    def test_open_spill_level_and_acyclic_flat_routing(self):
        dem = np.full((7, 7), 10.0)
        dem[1:-1, 1:-1] = 0
        dem[0, 3] = 3
        routed = drainage.route(dem)
        np.testing.assert_array_equal(routed['filled'][1:-1, 1:-1], np.full((5, 5), 3))
        receivers = routed['receiver']
        for start in range(dem.size):
            seen = set()
            while start >= 0:
                self.assertNotIn(start, seen)
                seen.add(start)
                start = int(receivers[start])

    def test_steepest_d8_descent_and_original_slope_filter(self):
        r, c = np.mgrid[:7, :7]
        dem = 20.0 - r - c
        routed = drainage.route(dem)
        self.assertEqual(routed['receiver'][3 * 7 + 3], 4 * 7 + 4)
        self.assertTrue(drainage.visible_links(dem, routed)[3 * 7 + 3])
        flat = np.ones((7, 7))
        self.assertFalse(drainage.visible_links(flat, drainage.route(flat)).any())

    def test_equal_and_unequal_strahler_confluences(self):
        receiver = np.array([4, 4, 5, 5, 6, 6, -1])
        actual = drainage.channel_order(receiver, np.arange(6, -1, -1), np.ones(7, dtype=bool))
        np.testing.assert_array_equal(actual, [1, 1, 1, 1, 2, 2, 3])
        receiver = np.array([3, 3, 4, 5, 5, -1])
        actual = drainage.channel_order(receiver, np.arange(5, -1, -1), np.ones(6, dtype=bool))
        np.testing.assert_array_equal(actual, [1, 1, 1, 2, 1, 2])

    def test_nonfinite_dem_rejected(self):
        dem = np.ones((3, 3))
        dem[1, 1] = np.nan
        with self.assertRaises(ValueError):
            drainage.route(dem)


class SourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(os.environ.get('YELLOWSTONE_ROOT', '.')).resolve()
        cls.source = root / drainage.SOURCE
        cls.raw = np.fromfile(cls.source, dtype='<f4').reshape(1025, 1025).astype(np.float64)
        cls.raw_before = cls.raw.copy()
        cls.routed = drainage.route(cls.raw)
        cls.output = json.loads((HERE / 'data/drainage.json').read_text())
        cls.manifest = json.loads((HERE / 'data/manifest.json').read_text())

    def test_source_identity_asset_hash_and_source_preservation(self):
        actual = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.assertEqual(actual, drainage.SOURCE_HASH)
        self.assertEqual(self.output['source_sha256'], actual)
        self.assertEqual(self.manifest['sources'][drainage.SOURCE], actual)
        self.assertEqual(self.manifest['assets']['drainage.json']['sha256'], drainage.digest(HERE / 'data/drainage.json'))
        np.testing.assert_array_equal(self.raw, self.raw_before)

    def test_independent_kahn_acyclicity_accumulation_and_mass_balance(self):
        receivers = self.routed['receiver']
        indegree = np.bincount(receivers[receivers >= 0], minlength=self.raw.size)
        queue = deque(np.flatnonzero(indegree == 0))
        accumulated = self.routed['support'].ravel().copy()
        visited = 0
        while queue:
            i = queue.popleft()
            visited += 1
            j = receivers[i]
            if j >= 0:
                accumulated[j] += accumulated[i]
                indegree[j] -= 1
                if indegree[j] == 0:
                    queue.append(j)
        self.assertEqual(visited, self.raw.size)
        np.testing.assert_array_equal(accumulated, self.routed['area'])
        self.assertEqual(accumulated[receivers < 0].sum(), 4096 ** 2)

    def test_every_exported_vertex_and_link_matches_real_source(self):
        raw = self.raw.ravel()
        receivers = self.routed['receiver']
        area = self.routed['area']
        visible = drainage.visible_links(self.raw, self.routed)
        for level in self.output['levels']:
            threshold = level['threshold_ha'] * 10000
            active = area >= threshold
            orders = drainage.channel_order(receivers, self.routed['order'], active)
            seen = set()
            for branch in level['branches']:
                points = np.asarray(branch['points'])
                cols = (points[:, 0] + 2048) / 4
                rows = (points[:, 1] + 2048) / 4
                self.assertTrue(np.equal(cols, cols.astype(int)).all())
                self.assertTrue(np.equal(rows, rows.astype(int)).all())
                self.assertTrue(((cols >= 0) & (cols <= 1024) & (rows >= 0) & (rows <= 1024)).all())
                ids = (rows.astype(int) * 1025 + cols.astype(int))
                np.testing.assert_array_equal(points[:, 2], raw[ids])
                np.testing.assert_array_equal(points[:, 3], area[ids])
                self.assertEqual(branch['order'], orders[ids[0]])
                self.assertTrue((np.diff(points[:, 3]) > 0).all())
                for i, j in zip(ids[:-1], ids[1:]):
                    self.assertEqual(receivers[i], j)
                    self.assertTrue(visible[i])
                    self.assertGreaterEqual(area[i], threshold)
                    self.assertNotIn(int(i), seen)
                    seen.add(int(i))
            expected = set(np.flatnonzero(visible & active).tolist())
            self.assertSetEqual(seen, expected)
            self.assertEqual(len(seen), level['edge_count'])

    def test_metadata_and_nested_thresholds(self):
        stats = self.output['statistics']
        depths = self.routed['filled'] - self.raw
        self.assertEqual(stats['filled_samples'], int((depths > 0).sum()))
        self.assertEqual(stats['max_fill_depth_m'], float(depths.max()))
        self.assertEqual(stats['domain_area_m2'], 4096 ** 2)
        self.assertEqual(self.output['method']['min_display_slope'], 0.002)
        levels = self.output['levels']
        self.assertEqual([level['threshold_ha'] for level in levels], [0.5, 2, 8])
        self.assertGreater(levels[0]['edge_count'], levels[1]['edge_count'])
        self.assertGreater(levels[1]['edge_count'], levels[2]['edge_count'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
