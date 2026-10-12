"""Regression tests for tree_inventory.py CLI validation (no detection run)."""
import ast
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tree_inventory


class ArgValidationTests(unittest.TestCase):
    def _parse(self, *argv):
        old = sys.argv
        sys.argv = ["tree_inventory.py", *argv]
        try:
            return tree_inventory.parse_args()
        finally:
            sys.argv = old

    def test_duplicate_bands_rejected(self):
        with self.assertRaises(SystemExit):
            self._parse("img.png", "--bands", "1", "1", "1")

    def test_nonpositive_band_rejected(self):
        with self.assertRaises(SystemExit):
            self._parse("img.png", "--bands", "0", "2", "3")

    def test_distinct_bands_accepted(self):
        args = self._parse("img.png", "--bands", "3", "2", "1")
        self.assertEqual(args.bands, [3, 2, 1])

    def test_missing_metadata_fails_fast(self):
        old = sys.argv
        sys.argv = ["tree_inventory.py", "/nonexistent.png",
                    "--output", "/tmp/ti_failfast",
                    "--metadata-json", "/nonexistent_meta.json"]
        try:
            with self.assertRaisesRegex(ValueError, "metadata-json"):
                tree_inventory.run()
        finally:
            sys.argv = old

    def test_scatter_has_no_conflicting_colors(self):
        source = Path(__file__).with_name(
            "tree_inventory.py").read_text()
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "attr", "") == "scatter"):
                keywords = [k.arg for k in node.keywords
                            if k.arg is not None]
                self.assertFalse(
                    "c" in keywords and "facecolors" in keywords,
                    "scatter must not pass c and facecolors together",
                )


if __name__ == "__main__":
    unittest.main()
