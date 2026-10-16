"""Optional installed or sibling-checkout hydrosim integration."""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path
from threading import RLock


_LOAD_LOCK = RLock()
_LOCAL_MODULE = "_yellowstone_external_hydrosim"


def import_hydrosim():
    """Return (module, provenance), or (None, reason) when hydrosim is unavailable."""
    try:
        return importlib.import_module("hydrosim"), "installed package"
    except ModuleNotFoundError as exc:
        if exc.name != "hydrosim":
            raise
    project = Path(__file__).resolve().parents[2]
    for directory in (project, project.parent / "hydrology"):
        candidate = directory / "hydrosim.py"
        if not candidate.is_file():
            continue
        with _LOAD_LOCK:
            module = sys.modules.get(_LOCAL_MODULE)
            if module is None:
                spec = importlib.util.spec_from_file_location(_LOCAL_MODULE, candidate)
                if spec is None or spec.loader is None:
                    continue
                module = importlib.util.module_from_spec(spec)
                sys.modules[_LOCAL_MODULE] = module
                try:
                    spec.loader.exec_module(module)
                except BaseException:
                    sys.modules.pop(_LOCAL_MODULE, None)
                    raise
        return module, f"sibling checkout at {directory}"
    return None, "hydrosim package or sibling checkout unavailable"
