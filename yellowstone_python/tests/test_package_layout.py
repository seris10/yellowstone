"""Package-layout gates for yellowstone_python."""
from __future__ import annotations

import importlib
import importlib.util
import pkgutil

import yellowstone_python


def test_no_orphan_packages():
    """Each importable non-test subpackage exports a non-dunder name."""
    orphans = []
    for module_info in pkgutil.walk_packages(
            yellowstone_python.__path__, prefix="yellowstone_python."):
        if not module_info.ispkg:
            continue
        if module_info.name.endswith(".tests"):
            continue
        try:
            mod = importlib.import_module(module_info.name)
        except ImportError:
            continue
        names = [name for name in vars(mod) if not name.startswith("_")]
        if not names:
            orphans.append(module_info.name)
    assert orphans == [], f"empty subpackages: {orphans}"


def test_weather_ingest_absent():
    assert importlib.util.find_spec("yellowstone_python.weather_ingest") is None
