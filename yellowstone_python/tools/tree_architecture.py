"""Seeded lodgepole architecture export."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

from yellowstone_python.authoring.tree_architecture import ArchitectureParameters, generate_architecture, display_dimensions
from yellowstone_python.common.io import write_json_atomic

FALLBACKS = {
    "dense": dict(height_m=18., dbh_m=.26, crown_radius_m=2.5, crown_ratio=.70),
    "edge": dict(height_m=18., dbh_m=.32, crown_radius_m=2.7, crown_ratio=.78),
    "open": dict(height_m=16., dbh_m=.44, crown_radius_m=3.15, crown_ratio=.85),
    "sapling": dict(height_m=5., dbh_m=.07, crown_radius_m=.8, crown_ratio=.86),
    "snag": dict(height_m=14., dbh_m=.24, crown_radius_m=.8, crown_ratio=0.),
}
VALUE_CLASSES = {"measured", "derived_not_field_validated", "transferred", "authored", "unavailable"}


def read_json(path):
    """Read finite JSON values from a bounded local source file."""
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("input JSON exceeds the 64 MiB export budget")
    def invalid(value):
        raise ValueError("input JSON contains a nonfinite constant: " + value)
    return json.loads(path.read_text(), parse_constant=invalid)


def input_records(value):
    """Read record objects from a tree list, census wrapper, or individual record."""
    if isinstance(value, dict) and "payload" in value:
        value = value["payload"]
    if isinstance(value, dict):
        if any(key in value for key in ["trees", "records", "add"]):
            value = value.get("trees", value.get("records", value.get("add")))
        else:
            value = [value]
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("input requires a tree record object or list")
    return value


def main(argv=None):
    """Export bounded reproducible tree graphs with retained input provenance."""
    parser = argparse.ArgumentParser()
    for key in ["height-m", "dbh-m", "crown-radius-m", "crown-ratio"]:
        parser.add_argument("--" + key, type=float)
    parser.add_argument("--input", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--parameters", type=Path)
    parser.add_argument("--archetype", choices=tuple(FALLBACKS), default="dense")
    parser.add_argument("--identity")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--variants", type=int, default=4)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.variants <= 8:
        parser.error("variants must lie in [1,8]")
    if args.input and args.record:
        parser.error("input and record are mutually exclusive")
    manual = dict(height_m=args.height_m, dbh_m=args.dbh_m,
                  crown_radius_m=args.crown_radius_m, crown_ratio=args.crown_ratio)
    try:
        parameters = read_json(args.parameters) if args.parameters else {}
        if not isinstance(parameters, dict) or set(parameters) - set(asdict(ArchitectureParameters())):
            raise ValueError("parameters require known ArchitectureParameters keys")
        options = ArchitectureParameters(**parameters)
        options.validate()
        source = args.input or args.record
        if source and any(value is not None for value in manual.values()):
            raise ValueError("source records and manual dimensions are mutually exclusive")
        if source:
            records = input_records(read_json(source))
            if args.identity:
                records = [row for row in records if str(row.get("stable_id", row.get("id", ""))) == args.identity]
                if len(records) != 1:
                    raise ValueError("identity must select exactly one source tree")
            if args.limit is not None:
                if not 1 <= args.limit <= 16:
                    raise ValueError("limit must lie in [1,16]")
                records = records[:args.limit]
            if not records or len(records) > 16 or len(records) * args.variants > 64:
                raise ValueError("export requires 1..16 records and at most 64 total variants; select an identity or limit")
        else:
            if any(value is None for value in manual.values()):
                raise ValueError("manual export requires height, DBH, crown radius and crown ratio")
            if args.limit is not None:
                raise ValueError("limit requires a record input")
            records = [None]
        selected_ids = [str(row.get("stable_id", row.get("id", ""))) for row in records if row]
        if len(set(selected_ids)) != len(selected_ids):
            raise ValueError("source identities must be unique within the selected records")
        exported = []
        component_count = 0
        for record in records:
            identity = str(record.get("stable_id", record.get("id", ""))) if record else (args.identity or "lodgepole")
            if not identity:
                raise ValueError("source tree requires an existing stable_id or id")
            form = "snag" if record and record.get("kind") == "snag" else args.archetype
            display = display_dimensions(record, FALLBACKS[form]) if record else None
            dimensions = {key: display[key] for key in manual} if display else manual
            variants = []
            for index in range(args.variants):
                graph = generate_architecture(dimensions, f"{identity}:{index}", options)
                component_count += len(graph["axes"]) + len(graph["shoots"])
                if component_count > 250000:
                    raise ValueError("export exceeds the 250000 component budget")
                variants.append(graph)
            source_class = record.get("source_class", "unavailable") if record else "authored"
            exported.append({"identity": identity, "input_record": record,
                             "display_envelope": display, "variants": variants,
                             "source_evidence_class": source_class if source_class in VALUE_CLASSES else "unavailable",
                             "fallback_dimensions": FALLBACKS[form] if record else None,
                             "fallback_evidence_class": "authored"})

    except (ValueError, OSError, TypeError) as error:
        parser.error(str(error))
    artifact = {"schema": "yellowstone.tree_architecture_library.v1",
                "parameters": asdict(options), "records": exported,
                "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest() if source else None,
                "parameter_sha256": hashlib.sha256(args.parameters.read_bytes()).hexdigest() if args.parameters else None,
                "status": "illustrative_not_locally_validated", "uncertainty": "unknown"}
    if len(exported) == 1:
        artifact.update(variants=exported[0]["variants"], input_record=exported[0]["input_record"],
                        display_dimensions=exported[0]["display_envelope"])
    write_json_atomic(args.out, artifact, indent=2)


if __name__ == "__main__":
    main()
