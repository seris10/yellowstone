class_name YellowstoneVerificationReceipt
extends RefCounted
## Source hashes for serialized instance verification.

const SCHEMA := "yellowstone.multimesh_validation.v2"
## Binary bake preferred by the runtime loader.
const SCENE_BINARY := "res://scenes/authored_world.scn"
## Text scene fallback when no binary bake exists.
const SCENE_TEXT := "res://scenes/authored_world.tscn"
const INPUTS := [
	"res://data/world.json",
	"res://data/placements.json", "res://data/placement_overrides.json",
	"res://data/forest_floor.json", "res://data/lidar_canopy/unresolved_render_canopy.json",
	"res://data/lidar_canopy/unresolved_cells_excluded.u8",
	"res://assets/imported/lodgepole/lodgepole_metadata.json",
	"res://scripts/lodgepole_library.gd", "res://scripts/canopy_surface.gd",
	"res://scripts/forest_floor.gd", "res://scripts/forest_floor_geometry.gd",
	"res://scripts/river_terrain.gd", "res://scripts/rendered_ground.gd",
	"res://scripts/core_terrain.gd", "res://scripts/canopy_support.gd",
	"res://tools/bake_world.gd", "res://data/terrain.f32",
	"res://data/core_terrain/core_terrain.json",
	"res://data/core_terrain/core_heightfield.f32", "res://data/core_terrain/core_microrelief.f32", "res://shaders/canopy_surface.gdshader",
	"res://scripts/verification_receipt.gd", "res://tools/validate_multimesh.gd",
]

static func scene_path() -> String:
	# Match the world loader: binary bake first, text scene as fallback.
	return SCENE_BINARY if ResourceLoader.exists(SCENE_BINARY) else SCENE_TEXT

static func source_hashes() -> Dictionary:
	var result: Dictionary = {}
	var scene := scene_path()
	result[scene] = FileAccess.get_sha256(scene)
	for path: String in INPUTS:
		result[path] = FileAccess.get_sha256(path)
	var header_path := "res://data/lidar_canopy/unresolved_render_canopy.json"
	var header: Variant = JSON.parse_string(FileAccess.get_file_as_string(header_path))
	if header is Dictionary:
		for artifact: Dictionary in header.get("artifacts", {}).values():
			var path := header_path.get_base_dir().path_join(str(artifact.get("path", "")))
			result[path] = FileAccess.get_sha256(path)
	return result

static func valid(report: Dictionary) -> bool:
	if report.get("schema", "") != SCHEMA or not report.get("ok", false) or int(report.get("failure_count", -1)) != 0:
		return false
	if int(report.get("actual_instance_slots", 0)) <= 0 or report.get("actual_instance_slots") != report.get("expected_instance_slots"):
		return false
	var hashes := source_hashes()
	for path: String in hashes:
		if str(hashes[path]).is_empty() or report.get("source_sha256", {}).get(path, "") != hashes[path]:
			return false
	return true
