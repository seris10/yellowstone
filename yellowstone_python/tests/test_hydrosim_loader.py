"""Optional hydrology imports and isolated sibling module loading."""
import sys
from types import SimpleNamespace

import pytest

from yellowstone_python.land import hydrosim_loader


def _missing_installed(monkeypatch, tmp_path):
    def unavailable(name):
        raise ModuleNotFoundError(name=name)

    monkeypatch.setattr(hydrosim_loader.importlib, "import_module", unavailable)
    monkeypatch.setattr(hydrosim_loader, "__file__", str(
        tmp_path / "project" / "yellowstone_python" / "land" / "loader.py"))
    monkeypatch.delitem(sys.modules, hydrosim_loader._LOCAL_MODULE, raising=False)


def test_installed_module_preserves_import_path(monkeypatch):
    module = SimpleNamespace()
    monkeypatch.setattr(hydrosim_loader.importlib, "import_module", lambda name: module)
    before = list(sys.path)
    result, provenance = hydrosim_loader.import_hydrosim()
    assert result is module
    assert provenance == "installed package"
    assert sys.path == before


def test_missing_optional_hydrology_has_explicit_status(monkeypatch, tmp_path):
    _missing_installed(monkeypatch, tmp_path)
    before = list(sys.path)
    module, reason = hydrosim_loader.import_hydrosim()
    assert module is None
    assert reason == "hydrosim package or sibling checkout unavailable"
    assert sys.path == before


def test_sibling_file_loads_with_isolated_name(monkeypatch, tmp_path):
    _missing_installed(monkeypatch, tmp_path)
    sibling = tmp_path / "hydrology"
    sibling.mkdir()
    (sibling / "hydrosim.py").write_text("IDENTITY = 'sibling hydrology'\n")
    before = list(sys.path)
    module, provenance = hydrosim_loader.import_hydrosim()
    assert module.IDENTITY == "sibling hydrology"
    assert module.__name__ == hydrosim_loader._LOCAL_MODULE
    assert "sibling checkout" in provenance
    assert hydrosim_loader.import_hydrosim()[0] is module
    assert sys.path == before
    monkeypatch.delitem(sys.modules, hydrosim_loader._LOCAL_MODULE)


def test_nested_dependency_failure_propagates_and_cleans_module(monkeypatch, tmp_path):
    _missing_installed(monkeypatch, tmp_path)
    sibling = tmp_path / "hydrology"
    sibling.mkdir()
    (sibling / "hydrosim.py").write_text("import yellowstone_missing_dependency_for_test\n")
    before = list(sys.path)
    with pytest.raises(ModuleNotFoundError) as exc:
        hydrosim_loader.import_hydrosim()
    assert exc.value.name == "yellowstone_missing_dependency_for_test"
    assert hydrosim_loader._LOCAL_MODULE not in sys.modules
    assert sys.path == before
