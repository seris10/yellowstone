import unittest
import numpy as np

from scientific_addons import match_points, difference_estimate


class ScientificTests(unittest.TestCase):
    def test_empty_reference(self):
        tp, fp, fn, distances = match_points(
            [[1, 1]], [], tolerance=2
        )
        self.assertEqual((tp, fp, fn), (0, 1, 0))
        self.assertEqual(distances, [])

    def test_one_to_one_matching(self):
        # First prediction can match either reference.
        # Second can match only [2, 0].
        # A correct assignment therefore matches both.
        tp, fp, fn, _ = match_points(
            [[0, 0], [4, 0]],
            [[2, 0], [-2, 0]],
            tolerance=2,
        )
        self.assertEqual((tp, fp, fn), (2, 0, 0))

    def test_difference_estimator(self):
        result = difference_estimate(
            model_total=40,
            population_cells=4,
            residuals=np.array([2.0, -2.0]),
            area_ha=1.0,
        )
        self.assertAlmostEqual(
            result["estimated_reference_total"], 40.0
        )
        self.assertAlmostEqual(
            result["estimated_sampling_standard_error"],
            np.sqrt(32.0),
        )
    def test_census_has_no_sampling_variance(self):
        result = difference_estimate(
            model_total=40,
            population_cells=2,
            residuals=[2.0, 4.0],
            area_ha=None,
        )
        self.assertAlmostEqual(
            result["estimated_reference_total"], 46.0
        )
        self.assertEqual(
            result["estimated_sampling_standard_error"], 0.0
        )

    def test_zero_tolerance_rejected(self):
        for bad in (0, -1.0, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                match_points([[0, 0]], [[0, 0]], tolerance=bad)

    def test_nonpositive_area_rejected(self):
        for bad in (0.0, -1.0, float("nan")):
            with self.assertRaises(ValueError):
                difference_estimate(
                    model_total=10,
                    population_cells=4,
                    residuals=[1.0, -1.0],
                    area_ha=bad,
                )

    def test_roi_tamper_detected(self):
        import json
        import tempfile
        from pathlib import Path

        from scientific_addons import check_frozen_inputs, file_sha256

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "analysis_rgb.png").write_bytes(b"rgb")
            (directory / "analysis_mask.npy").write_bytes(b"mask")
            (directory / "automated_trees.csv").write_bytes(b"trees")
            (directory / "roi.json").write_text(json.dumps({"include": None}))
            manifest = {
                "archived_rgb_sha256": file_sha256(
                    directory / "analysis_rgb.png"),
                "mask_sha256": file_sha256(
                    directory / "analysis_mask.npy"),
                "automated_trees_sha256": file_sha256(
                    directory / "automated_trees.csv"),
                "roi_sha256": file_sha256(directory / "roi.json"),
            }
            (directory / "manifest.json").write_text(json.dumps(manifest))
            check_frozen_inputs(directory)  # intact archive passes
            (directory / "roi.json").write_text(json.dumps({"include": []}))
            with self.assertRaisesRegex(ValueError, "roi.json"):
                check_frozen_inputs(directory)
            del manifest["roi_sha256"]
            (directory / "manifest.json").write_text(json.dumps(manifest))
            with self.assertRaisesRegex(ValueError, "predates"):
                check_frozen_inputs(directory)


if __name__ == "__main__":
    unittest.main()
