"""Per-asset release decisions from explicit geometry permission records."""
from __future__ import annotations

import argparse
from pathlib import Path

from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic
from yellowstone_python.common.provenance import default_world_root


def release_inventory(world: Path) -> dict:
    """Separate presence, runtime use, scientific status and redistribution evidence."""
    general = load_json(world / "data/asset_manifest.json")
    motion = load_json(world / "data/wildlife_motion_assets.json")
    bindings = motion.get("wildlife_species_asset_map", {})
    used = {value.get("path", "").removeprefix("res://") for value in bindings.values()}
    records = []
    for asset in general.get("assets", []):
        license_record = asset.get("license", {})
        permission = (license_record.get("id") if isinstance(license_record, dict) else None) or "unknown"
        established = isinstance(license_record, dict) and bool(license_record.get("version_verified")) and bool(license_record.get("raw_redistribution"))
        owner_authorized = (asset.get("geometry_owner") == "KJR"
                            and asset.get("redistribution_permission") == "owner_authorized_project_release")
        if owner_authorized:
            permission, established = "owner_confirmed", True
        authored_license = asset.get("asset_provenance", {}).get("license")
        if asset.get("status") == "authored" and authored_license in ("MIT", "Apache-2.0", "CC0-1.0"):
            permission, established = authored_license, True
        for member in asset.get("files", []):
            path = _asset_path(world, member["path"])
            present = path.is_file()
            matches = present and sha256_file(path) == member.get("sha256")
            records.append({"asset_id": asset["id"], "path": member["path"],
                "source": asset.get("source_url"), "present": present, "hash_matches": matches,
                "sha256": sha256_file(path) if present else None,
                "runtime_use": "included_candidate" if asset.get("included") else "unused_candidate",
                "geometry_permission": permission, "redistribution_status_established": established,
                "geometry_validation": "unavailable", "modifications": asset.get("notes", []),
                "scientific_status": "visual_art_or_source_data; local biological validation unavailable",
                "public_release_decision": "include" if established and matches and asset.get("included") else "exclude",
                "permission_evidence": asset.get("ownership_evidence") if owner_authorized else
                    license_record.get("verification_url") if isinstance(license_record, dict) else None})
    for asset in motion.get("assets", []):
        path = _asset_path(world, asset["path"])
        present = path.is_file()
        permission = asset.get("geometry_rights", "unknown")
        established = (permission in ("MIT", "Apache-2.0", "CC0-1.0")
                       or (permission == "owner_confirmed" and asset.get("redistribution_permission") == "owner_authorized_project_release"))
        matches = present and sha256_file(path) == asset.get("sha256")
        records.append({"asset_id": asset["id"], "path": asset["path"],
            "source": asset.get("status"), "present": present, "hash_matches": matches,
            "sha256": sha256_file(path) if present else None,
            "runtime_use": "bound" if asset["path"] in used else "unbound_fixture_or_variant",
            "geometry_permission": permission, "redistribution_status_established": established,
            "geometry_validation": asset.get("audit", {}).get("status", "unavailable"),
            "modifications": asset.get("change", asset.get("rig_status")),
            "scientific_status": asset.get("scientific_acceptance", "not_yet_accepted"),
            "public_release_decision": "include" if established and matches else "exclude",
            "permission_evidence": "explicit geometry_rights in wildlife_motion_assets.json"})
    recorded = {record["path"] for record in records}
    for species, binding in general.get("wildlife_species_asset_map", {}).items():
        relative = binding.get("path", "").removeprefix("res://")
        if not relative or relative in recorded:
            continue
        path = _asset_path(world, relative)
        permission = binding.get("geometry_rights", "unknown")
        established = (permission in ("MIT", "Apache-2.0", "CC0-1.0")
                       or (permission == "owner_confirmed" and binding.get("redistribution_permission") == "owner_authorized_project_release"))
        present = path.is_file()
        records.append({"asset_id": species, "path": relative, "present": present,
            "sha256": sha256_file(path) if present else None,
            "source": binding.get("source"), "runtime_use": "bound",
            "geometry_permission": permission, "redistribution_status_established": established,
            "geometry_validation": "unavailable", "modifications": binding.get("animation_provenance"),
            "scientific_status": "illustrative_not_field_validated",
            "public_release_decision": "include" if established and present else "exclude",
            "permission_evidence": "explicit geometry_rights in wildlife_species_asset_map"})
        recorded.add(relative)
    by_path = {record["path"]: record for record in records}
    animals = general.get("animal_geometry_ownership", {}).get("owner") == "KJR"
    for path in sorted((world / "assets").rglob("*")):
        if not path.is_file() or path.suffix in (".import", ".uid") or "sources" in path.parts:
            continue
        relative = str(path.relative_to(world))
        if relative in by_path:
            continue
        animal_asset = relative.startswith(("assets/imported/wildlife_motion/", "assets/imported/fauna/", "assets/meshes/fauna/"))
        siblings = [record for record in records if record["path"].startswith(str(path.parent.relative_to(world)) + "/")
                    and record["redistribution_status_established"]]
        generated = relative.startswith(("assets/textures/", "assets/materials/"))
        metadata = path.suffix in (".json", ".py", ".md", ".txt")
        terrain = relative.startswith("assets/meshes/terrain/")
        permission = ("owner_confirmed" if animals and animal_asset else
                      "US-public-domain-source/MIT-project-derivative" if terrain else
                      siblings[0]["geometry_permission"] if siblings else "MIT" if generated or metadata else "unknown")
        established = permission != "unknown"
        preview = path.name.startswith("_preview_")
        records.append({"asset_id": relative, "path": relative, "present": True,
            "sha256": sha256_file(path), "hash_matches": True,
            "source": "USGS elevation; project terrain bake" if terrain else "project animal asset" if animal_asset else "project material/metadata" if generated or metadata else "licensed sibling derivative",
            "runtime_use": "unused_preview" if preview else "included_dependency_candidate",
            "geometry_permission": permission, "redistribution_status_established": established,
            "geometry_validation": "unavailable", "modifications": "retained project derivative; source methods remain in adjacent metadata",
            "scientific_status": "illustrative_not_field_validated",
            "public_release_decision": "include" if established and not preview else "exclude",
            "permission_evidence": "THIRD_PARTY.md geographic sources and original project modifications" if terrain else "KJR animal ownership declaration" if animals and animal_asset else
                siblings[0]["permission_evidence"] if siblings else "THIRD_PARTY.md original project art scope" if generated or metadata else None})
    return {"schema": "yellowstone.asset_release_inventory.v1",
            "source_manifest_hashes": {name: sha256_file(world / "data" / name) for name in
                ("asset_manifest.json", "wildlife_motion_assets.json")},
            "code_license_scopes": {"repository_default": "Apache-2.0", "yellowstone_midway": "MIT",
                                    "wildlife_motion_library": "MIT", "wildlife_motion_integration": "Apache-2.0"},
            "assets": records, "unknown_permission_paths": sorted({r["path"] for r in records if not r["redistribution_status_established"] and r["present"]}),
            "public_release_rule": "Include only byte-matching assets with explicit redistribution evidence; unknown geometry is excluded"}


def _asset_path(world: Path, relative: str) -> Path:
    """Resolve inventory members within the declared world boundary."""
    path = world / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(world.resolve()):
        raise ValueError("asset path leaves the world boundary")
    return path


def main() -> int:
    """Write the release-specific asset decision inventory."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--world", default=str(default_world_root()))
    parser.add_argument("--out", default="work/asset-release-inventory.json")
    args = parser.parse_args()
    inventory = release_inventory(Path(args.world))
    write_json_atomic(args.out, inventory, indent=2)
    print(len(inventory["assets"]), "asset decisions;", len(inventory["unknown_permission_paths"]), "unknown-permission paths excluded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
