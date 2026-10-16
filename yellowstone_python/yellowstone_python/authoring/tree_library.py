"""Canonical tree graph interchange and versioned layout migration."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from yellowstone_python.authoring.tree_architecture import ArchitectureParameters, validate_architecture
from yellowstone_python.common.io import sha256_file, write_json_atomic
from yellowstone_python.common.provenance import sha256_json

SCHEMA = "yellowstone.tree_architecture_library.v2"
LEGACY_SCHEMA = "yellowstone.tree_architecture_library.v1"


def canonical_library(document: dict) -> dict:
    """Read canonical variants or migrate either maintained version-one layout."""
    if not isinstance(document, dict) or document.get("schema") not in (SCHEMA, LEGACY_SCHEMA):
        raise ValueError("Unsupported tree architecture library schema")
    if document["schema"] == SCHEMA:
        result = copy.deepcopy(document)
    else:
        result = {key: copy.deepcopy(value) for key, value in document.items() if key not in ("records", "variants", "schema")}
        variants, records = [], []
        legacy_records = document.get("records")
        if legacy_records is None:
            legacy_records = [{"identity": document.get("identity", "library"),
                "input_record": document.get("input_record"), "variants": document.get("variants", [])}]
        for record in legacy_records:
            identifiers = []
            for index, item in enumerate(record.get("variants", [])):
                graph = item.get("graph", item)
                identity = str(graph.get("identity", ""))
                record_id = str(item.get("archetype", record.get("identity", identity)))
                variant = {"variant_id": identity, "record_id": record_id,
                    "variant_index": int(item.get("variant", index)), "archetype": item.get("archetype", record.get("archetype")),
                    "source_record": copy.deepcopy(record.get("input_record")),
                    "resolved_parameters": copy.deepcopy(graph.get("parameters", document.get("parameters", {}))),
                    "graph": copy.deepcopy(graph),
                    "representation": {"kind": "branch_axis_graph", "units": "m", "space": "tree_local",
                        "graph_sha256": sha256_json(graph)},
                    "legacy_variant_metadata": {key: copy.deepcopy(value) for key, value in item.items()
                        if key not in graph and key != "graph"}}
                variants.append(variant)
                identifiers.append(identity)
            records.append({**{key: copy.deepcopy(value) for key, value in record.items() if key != "variants"},
                            "variant_ids": identifiers})
        result.update(schema=SCHEMA, variants=variants, records=records,
            migration={"source_schema": LEGACY_SCHEMA, "adapter": "records_raw_graphs_or_mesh_variant_wrappers"})
    variants = result.get("variants")
    if not isinstance(variants, list) or not 1 <= len(variants) <= 256:
        raise ValueError("Tree libraries require 1..256 canonical variants")
    identities = set()
    for variant in variants:
        required = ("variant_id", "record_id", "variant_index", "source_record", "archetype", "resolved_parameters", "graph", "representation")
        if not isinstance(variant, dict) or any(key not in variant for key in required):
            raise ValueError("Incomplete canonical tree variant")
        identity = variant["variant_id"]
        if not isinstance(identity, str) or not identity or identity in identities:
            raise ValueError("Tree variant identities must be nonempty and unique")
        identities.add(identity)
        graph = variant["graph"]
        if graph.get("schema") != "yellowstone.tree_architecture.v1" or str(graph.get("identity")) != identity:
            raise ValueError("Tree variant graph schema or identity differs")
        ArchitectureParameters(**variant["resolved_parameters"]).validate()
        if graph.get("parameters") != variant["resolved_parameters"]:
            raise ValueError("Resolved parameters differ from the selected source graph")
        if variant["representation"].get("graph_sha256") != sha256_json(graph):
            raise ValueError("Tree graph content differs from its representation identity")
        validate_architecture(graph)
    return result


def read_library(path: Path) -> dict:
    """Read a bounded, finite graph library through the canonical adapter."""
    path = Path(path)
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("Tree library exceeds the 64 MiB budget")
    def invalid(value):
        raise ValueError("Nonfinite tree library value: " + value)
    return canonical_library(json.loads(path.read_text(), parse_constant=invalid))


def write_library(path: Path, document: dict) -> dict:
    """Write canonical records while archiving replaced library source bytes."""
    path = Path(path)
    resolved = canonical_library(document)
    if path.is_file():
        archive = path.parent / "library_history" / (sha256_file(path) + ".json")
        archive.parent.mkdir(parents=True, exist_ok=True)
        if not archive.exists():
            archive.write_bytes(path.read_bytes())
    write_json_atomic(path, resolved, indent=1)
    return resolved
