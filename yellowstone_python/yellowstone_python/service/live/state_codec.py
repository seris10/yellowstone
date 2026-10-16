"""Versioned JSON codec for live engine checkpoints.

Covers river, solute, ecological, forcing, configuration, mammal and history state."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.util
import json
import math
from functools import lru_cache

import numpy as np

from yellowstone_python.river.river_transport import RiverState, Series, Source, SurfaceBudget
from yellowstone_python.river.surface_flux import BudgetParams

SCHEMA = "yellowstone.live_engine_state.v1"
TAG = "$t"
EXTRA_MODULES = ("yellowstone_python.insects_birds", "yellowstone_python.river.surface_flux",
                 "yellowstone_python.land.mammal_catalogue", "yellowstone_python.common.mammal_forcing",
                 "yellowstone_python.service.live.state_codec")
DATACLASSES = {cls.__name__: cls for cls in (Series, Source, SurfaceBudget, BudgetParams)}
NONFINITE = {"nan": math.nan, "inf": math.inf, "-inf": -math.inf}
ARRAY_KINDS = "fiub"


class StateCodecError(ValueError):
    """Raised when a state document cannot be encoded or does not match the engine."""


class UnsupportedStateError(StateCodecError):
    """Raised for engine state that has no portable representation."""


def encode_value(value):
    """Return a JSON-compatible form of a value, tagging every non-JSON type."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        number = float(value)
        if math.isfinite(number):
            return number
        return {TAG: "float", "v": "nan" if math.isnan(number) else ("inf" if number > 0 else "-inf")}
    if isinstance(value, list):
        return [encode_value(item) for item in value]
    if isinstance(value, tuple):
        return {TAG: "tuple", "v": [encode_value(item) for item in value]}
    if isinstance(value, dict):
        if all(isinstance(key, str) for key in value) and TAG not in value:
            return {key: encode_value(item) for key, item in value.items()}
        return {TAG: "pairs", "v": [[encode_value(key), encode_value(item)] for key, item in value.items()]}
    if isinstance(value, np.ndarray):
        if value.dtype.kind not in ARRAY_KINDS:
            raise StateCodecError(f"unsupported array dtype {value.dtype}")
        return {TAG: "ndarray", "dtype": value.dtype.str, "shape": list(value.shape),
                "v": [encode_value(item) for item in value.ravel().tolist()]}
    if dataclasses.is_dataclass(value) and not isinstance(value, type) and type(value).__name__ in DATACLASSES:
        return {TAG: "dataclass", "name": type(value).__name__,
                "v": {field.name: encode_value(getattr(value, field.name)) for field in dataclasses.fields(value)}}
    raise StateCodecError(f"unsupported state value of type {type(value).__name__}")


def decode_value(value):
    """Rebuild a value produced by encode_value."""
    if isinstance(value, list):
        return [decode_value(item) for item in value]
    if not isinstance(value, dict):
        return value
    kind = value.get(TAG)
    if kind is None:
        return {key: decode_value(item) for key, item in value.items()}
    body = value.get("v")
    if kind == "float" and body in NONFINITE:
        return NONFINITE[body]
    if kind == "tuple" and isinstance(body, list):
        return tuple(decode_value(item) for item in body)
    if kind == "pairs" and isinstance(body, list):
        return {decode_value(key): decode_value(item) for key, item in body}
    if kind == "ndarray" and isinstance(body, list):
        dtype = np.dtype(value["dtype"])
        if dtype.kind not in ARRAY_KINDS:
            raise StateCodecError(f"unsupported array dtype {dtype}")
        array = np.asarray([decode_value(item) for item in body], dtype=dtype)
        return array.reshape(value["shape"])
    if kind == "dataclass" and value.get("name") in DATACLASSES and isinstance(body, dict):
        return DATACLASSES[value["name"]](**{key: decode_value(item) for key, item in body.items()})
    raise StateCodecError(f"unknown or malformed state tag {kind!r}")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _identical(left, right) -> bool:
    """Compare two plain values by type and content."""
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_identical(left[key], right[key]) for key in left)
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(_identical(a, b) for a, b in zip(left, right))
    return left == right


def config_delta(base: dict, current: dict) -> dict:
    """Return the encoded difference of a configuration from its build baseline."""
    if _identical(base, current):
        return {"op": "keep"}
    if isinstance(base, dict) and isinstance(current, dict):
        return {"op": "dict",
                "change": {key: config_delta(base[key], value) for key, value in current.items()
                           if key in base and not _identical(base[key], value)},
                "add": {key: encode_value(value) for key, value in current.items() if key not in base},
                "drop": sorted(key for key in base if key not in current)}
    return {"op": "set", "v": encode_value(current)}


def apply_config_delta(base, delta: dict):
    """Rebuild a configuration from a baseline and a config_delta result."""
    op = delta.get("op")
    if op == "keep":
        return copy.deepcopy(base)
    if op == "set":
        return decode_value(delta["v"])
    if op == "dict" and isinstance(base, dict):
        result = {key: copy.deepcopy(value) for key, value in base.items() if key not in delta["drop"]}
        for key, child in delta["change"].items():
            result[key] = apply_config_delta(base[key], child)
        for key, value in delta["add"].items():
            result[key] = decode_value(value)
        return result
    raise StateCodecError("configuration delta does not match the build baseline")


@lru_cache(maxsize=None)
def _module_sha256(module: str) -> str:
    spec = importlib.util.find_spec(module)
    if spec is None or spec.origin is None:
        raise StateCodecError(f"cannot locate module {module}")
    with open(spec.origin, "rb") as stream:
        return hashlib.sha256(stream.read()).hexdigest()


def model_versions(engine) -> dict:
    """Return the schema, mammal data hash and model source hashes."""
    from yellowstone_python.service.live.engine import MODEL_COMPONENTS
    modules = sorted({row["module"] for row in MODEL_COMPONENTS.values()} | set(EXTRA_MODULES))
    model = engine.ecology.get("mammal_model")
    return {"schema": SCHEMA, "source_sha256": {module: _module_sha256(module) for module in modules},
            "mammal_data_sha256": None if model is None else model.catalogue_sha}


def engine_identity(engine) -> dict:
    """Return the build, initial state and numerical policy a state belongs to."""
    return {"build_id": engine.build_id, "initial_state_id": engine.initial_state_id,
            "cell_ids": [cell.id for cell in engine.river.cells],
            "frame_interval_s": engine.frame_interval_s, "max_dt_s": engine.max_dt_s,
            "solver_dt_s": engine._solver_dt_s()}


def _segments(engine, state: dict) -> tuple[list, dict]:
    count = state["integration_segment_count"]
    segments = engine._integration_segments
    if count > len(segments):
        raise StateCodecError("integration segment history is shorter than the checkpoint requires")
    kept = copy.deepcopy(segments[:count])
    if kept and not math.isclose(kept[-1]["end_s"], state["river"].time_s, rel_tol=0, abs_tol=1e-6):
        raise StateCodecError("integration segment history diverged from the checkpoint time")
    keys = {segment["forcing_key"] for segment in kept}
    return kept, {key: encode_value(engine._forcing_catalog[key]) for key in sorted(keys)}


def encode_state(engine, state: dict, revision: int) -> dict:
    """Encode an engine checkpoint and its causal revision into a portable document."""
    if state["baseline"] is not None or state["measured_reference"] is not None:
        raise UnsupportedStateError("branch comparison and measured replay state have no portable form")
    ecology = dict(state["ecology"])
    model = ecology.pop("mammal_model", None)
    river = state["river"]
    solutes = state["solutes"]
    segments, catalog = _segments(engine, state)
    forcing = encode_value(river.forcing)
    return {"schema": SCHEMA, "identity": engine_identity(engine), "model_versions": model_versions(engine),
            "revision": int(revision), "time_s": river.time_s,
            "river": {field.name: encode_value(getattr(river, field.name)) for field in dataclasses.fields(river)},
            "forcing_sha256": _digest(forcing),
            "solutes": {"time_s": solutes._time_s, "steps": solutes.steps,
                        "max_advective_courant": solutes.max_advective_courant,
                        "max_diffusive_number": solutes.max_diffusive_number,
                        "concentrations": encode_value(solutes._concentrations),
                        "totals": encode_value(solutes._totals),
                        "water_totals": encode_value(solutes._water_totals)},
            "ecology": encode_value(ecology),
            "mammals": None if model is None else encode_value(model.checkpoint()),
            "config": config_delta(engine._initial_checkpoint["config"], state["config"]),
            "epoch_origin": state["epoch_origin"], "display_hour": state["display_hour"],
            "observation_samples": encode_value(state["observation_samples"]),
            "integration_segments": encode_value(segments), "forcing_catalog": catalog}


def _check_document(engine, document: dict, accept_source_drift: bool) -> None:
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise StateCodecError("unknown state schema; explicit save migration required")
    if document["identity"] != json.loads(_canonical(engine_identity(engine))):
        raise StateCodecError("state belongs to a different build, initial state or numerical policy")
    saved, current = document["model_versions"], model_versions(engine)
    if saved["mammal_data_sha256"] != current["mammal_data_sha256"]:
        raise StateCodecError("mammal data or model presence differs from the saved state")
    drift = sorted(module for module in current["source_sha256"]
                   if saved["source_sha256"].get(module) != current["source_sha256"][module])
    if drift and not accept_source_drift:
        raise StateCodecError("model source changed since the save: " + ", ".join(drift))


def decode_state(engine, document: dict, *, accept_source_drift: bool = False):
    """Return a native checkpoint, causal revision and segment history from a document.

    The engine supplies the build baseline, mammal model and solute geometry."""
    _check_document(engine, document, accept_source_drift)
    fields = {name: decode_value(value) for name, value in document["river"].items()}
    river = RiverState(**fields)
    if _digest(encode_value(river.forcing)) != document["forcing_sha256"]:
        raise StateCodecError("river forcing does not match its recorded digest")
    if river.cell_ids != tuple(cell.id for cell in engine.river.cells):
        raise StateCodecError("river cell geometry does not match the engine")
    if river.time_s != document["time_s"]:
        raise StateCodecError("river time does not match the document time")
    saved = document["solutes"]
    solutes = copy.copy(engine.solutes)
    solutes._concentrations = decode_value(saved["concentrations"])
    solutes._totals = decode_value(saved["totals"])
    solutes._water_totals = decode_value(saved["water_totals"])
    solutes._time_s, solutes.steps = saved["time_s"], saved["steps"]
    solutes.max_advective_courant = saved["max_advective_courant"]
    solutes.max_diffusive_number = saved["max_diffusive_number"]
    count = len(river.cell_ids)
    if any(len(values) != count for values in solutes._concentrations.values()):
        raise StateCodecError("solute state does not match the cell count")
    ecology = decode_value(document["ecology"])
    model = engine.ecology.get("mammal_model")
    if (document["mammals"] is None) != (model is None):
        raise StateCodecError("mammal model presence differs from the saved state")
    if model is not None:
        model = copy.deepcopy(model)
        model.restore(decode_value(document["mammals"]))
        ecology["mammal_model"] = model
    config = apply_config_delta(engine._initial_checkpoint["config"], document["config"])
    state = {"river": river, "ecology": ecology, "config": config,
             "epoch_origin": document["epoch_origin"], "display_hour": document["display_hour"],
             "start_operation": config.get("start_operation", "new_scenario"),
             "measured_reference": None, "observation_samples": decode_value(document["observation_samples"]),
             "baseline": None, "integration_segment_count": len(document["integration_segments"]),
             "solutes": solutes}
    history = {"integration_segments": decode_value(document["integration_segments"]),
               "forcing_catalog": {key: decode_value(value) for key, value in document["forcing_catalog"].items()}}
    return state, int(document["revision"]), history
