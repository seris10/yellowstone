"""publish: transactional release of a validated build.
Verifies CHECKS, backs up targets, copies, hash-verifies, writes a receipt."""
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from yellowstone_python.common.io import write_json_atomic

from yellowstone_python.common.io import sha256_file as _sha

import datetime
import hashlib
import json
import shutil
from pathlib import Path

from yellowstone_python.common.provenance import CONTRACT_VERSION, WORLD_ID, default_world_root
from yellowstone_python.common.io import load_json
from yellowstone_python.exporters.godot_sidecars import produce_all as produce_sidecars
from yellowstone_python.exporters.to_ecosystem import validate_for_godot
from yellowstone_python.common.canopy_artifacts import CANOPY_RENDER_FILES, FOREST_FLOOR_FILE

FILES = [
    ("ecosystem.godot.json", "data/ecosystem.json", True),
    # Unread artifacts stay in build sidecars; data/ carries runtime files.
    ("pool_shells.json", "data/pool_shells.json", False),
    ("snow_map.png", "assets/textures/snow_map.png", False),
    ("season.json", "data/season.json", False),
    # Missing optional build artifacts are recorded as publish gaps.
    ("plume_field.json", "data/plume_field.json", False),
    ("geochemistry.json", "data/geochemistry.json", False),
    ("calibration_summary.json", "data/calibration_summary.json", False),
    ("pools_state.json", "data/pools_state.json", False),
    ("snow_cover.json", "data/snow_cover.json", False),
    ("overland_field.json", "data/overland_field.json", False),
    ("groundwater_field.json", "data/groundwater_field.json", False),
    ("census.json", "data/census.json", False),
    # Weather snapshot (schema v2) consumed by yellowstone_midway/scripts/weather_snapshot_reader.gd.
    ("weather_snapshot.json", "data/weather_snapshot.json", False),
    # Replay files refresh the study-scene comparison pair when a build produces them.
    ("firehole_control.json", "data/firehole_control.json", False),
    ("firehole_pulse.json", "data/firehole_pulse.json", False),
    # and integration sidecars.
    ("ground_heat.json", "data/ground_heat.json", False),
    ("soil_temperature.json", "data/soil_temperature.json", False),
    ("evapotranspiration.json", "data/evapotranspiration.json", False),
    ("winter_grazing.json", "data/winter_grazing.json", False),
    ("mammals.json", "data/mammals.json", False),
    ("mammal_catalogue.json", "data/mammal_catalogue.json", False),
    ("piscivores.json", "data/piscivores.json", False),
    ("steam_microclimate.json", "data/steam_microclimate.json", False),
    # per-cell replay stressor sidecars.
    ("river_shading.json", "data/river_shading.json", False),
    ("river_oxygen.json", "data/river_oxygen.json", False),
    ("periphyton.json", "data/periphyton.json", False),
    ("solute_transport.json", "data/solute_transport.json", False),
    # outflow chain and mat state outputs.
    ("outflow_temperature.json", "data/outflow_temperature.json", False),
    ("outflow_temperature.f32", "data/outflow_temperature.f32", False),
    ("mat_state.json", "data/mat_state.json", False),
    ("mat_community.i16", "data/mat_community.i16", False),
    ("mat_pigment.png", "data/mat_pigment.png", False),
    ("outflow_to_replay_lateral.json", "data/outflow_to_replay_lateral.json",
     False),
    ("outflow_foodweb.json", "data/outflow_foodweb.json", False),
    ("pool_ramps.json", "data/pool_ramps.json", False),
    ("river_replay.json", "data/river_replay.json", True),
    ("world.runtime.json", "data/world.json", False),
    ("equations.json", "data/equations.json", False),
    ("param_registry.json", "data/param_registry.json", False),
    ("claims.json", "data/claims.json", False),
    ("species_catalogue.json", "data/species_catalogue.json", False),
    ("substrate_rules.json", "data/substrate_rules.json", False),
]
FILES.extend((f"lidar_canopy/{name}", f"data/lidar_canopy/{name}", False)
             for name in CANOPY_RENDER_FILES)
FILES.append((FOREST_FLOOR_FILE, f"data/{FOREST_FLOOR_FILE}", False))
# Study replays carry a build_id that must resolve to a build dir under derived/.
STUDY_REPLAY_FILES = ("firehole_control.json", "firehole_pulse.json")
DIRS = [
    ("pool_ramps", "assets/textures/pool_ramps"),
]


def consumer_manifest_errors(world_root: Path, files=None) -> list[str]:
    """Require published files to name an existing script consumer."""
    try:
        manifest = load_json(world_root / "data" / "consumers.json")
    except ValueError as exc:
        return [str(exc)]
    consumers = manifest.get("consumers", {})
    errors = []
    for _, target, _ in FILES if files is None else files:
        readers = consumers.get(target)
        if not isinstance(readers, list) or not readers:
            errors.append(f"{target}: no registered consumer")
            continue
        for reader in readers:
            path = world_root / reader
            if not path.is_file():
                errors.append(f"{target}: missing consumer {reader}")
    return errors




def _study_replay_build_id_ok(path: Path,
                              derived_root: Path) -> tuple[str, str]:
    """Verdict for a study-replay file: (status, detail).
'ok' when source_build_id names a sibling build dir; 'refused' otherwise."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return "refused", f"could not read {path.name}: {exc}"
    if not isinstance(doc, dict):
        return "refused", f"{path.name} is not a JSON object"
    source_bid = doc.get("source_build_id")
    if not isinstance(source_bid, str) or not source_bid.strip():
        return "refused", (
            f"{path.name} lacks source_build_id; the study runner must "
            f"carry forward the build_id of the derived/ build it "
            f"consumed (fixes-33 item 15 runner side)")
    target = derived_root / source_bid
    if not target.is_dir():
        return "refused", (
            f"study replay source_build_id {source_bid!r} has no "
            f"matching build dir at {target}")
    return "ok", (f"{path.name} source_build_id {source_bid!r} "
                  f"resolves to {target}")


def _load_json_or_refuse(path: Path, label: str) -> tuple[dict | None, int]:
    try:
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
    except FileNotFoundError:
        logger.error(f"refusing: missing {label} at {path}")
        return None, 3
    except json.JSONDecodeError as exc:
        logger.error(f"refusing: invalid JSON in {label} ({path}): {exc}")
        return None, 3
    if not isinstance(value, dict):
        logger.error(f"refusing: {label} is not a JSON object")
        return None, 3
    return value, 0






def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.publish import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
