class_name MidwayPoolOverlay
extends Node

const RAMP_DIR_PRIMARY := "res://data/pool_ramps/"
const RAMP_DIR_SECONDARY := "res://assets/textures/pool_ramps/"
const RAMP_SCHEMA := "yellowstone.pool_radiative_ramp.v1"
const POOL_SHELLS_PATH := "res://data/pool_shells.json"

var applied_count: int = 0
var primary_applied: int = 0
var secondary_applied: int = 0
var skipped_schema_mismatch: int = 0

func _ready() -> void:
	if not FileAccess.file_exists(POOL_SHELLS_PATH):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(POOL_SHELLS_PATH))
	if not parsed is Dictionary or not parsed.has("pool_shells"):
		push_warning("pool_overlay: pool_shells.json has no pool_shells array.")
		return
	var by_name: Dictionary = {}
	var by_id: Dictionary = {}
	for shell in parsed["pool_shells"]:
		if shell is Dictionary:
			by_name[str((shell as Dictionary).get("name", ""))] = shell
			by_id[str((shell as Dictionary).get("id", ""))] = shell
	for node in get_tree().get_nodes_in_group("thermal_surfaces"):
		if not node.has_meta("feature_name"):
			continue
		var feature: String = str(node.get_meta("feature_name"))
		var shell: Dictionary = by_name.get(feature, {})
		if shell.is_empty():
			continue
		var pool_id: String = str(shell.get("id", ""))
		if pool_id.is_empty():
			continue
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var mat: Material = mesh_instance.mesh.surface_get_material(0)
		if not mat is ShaderMaterial:
			continue
		var sm: ShaderMaterial = mat as ShaderMaterial
		# Primary: WP-B published ramp under data/pool_ramps/.
		var primary_png: String = RAMP_DIR_PRIMARY + "ramp_" + pool_id + ".png"
		var primary_json: String = RAMP_DIR_PRIMARY + "ramp_" + pool_id + ".json"
		if _apply_ramp(sm, primary_png, primary_json):
			primary_applied += 1
			applied_count += 1
			continue
		# Secondary: prior-wave authored PNG under assets/textures/pool_ramps/.
		var secondary_png: String = RAMP_DIR_SECONDARY + pool_id + ".png"
		if ResourceLoader.exists(secondary_png):
			sm.set_shader_parameter("band_ramp", load(secondary_png))
			sm.set_shader_parameter("ramp_mix", 1.0)
			secondary_applied += 1
			applied_count += 1
	print("pool_overlay: primary=%d secondary=%d skipped_schema_mismatch=%d" % [primary_applied, secondary_applied, skipped_schema_mismatch])

func _apply_ramp(sm: ShaderMaterial, png_path: String, json_path: String) -> bool:
	if not ResourceLoader.exists(png_path):
		return false
	if ResourceLoader.exists(json_path):
		var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(json_path))
		if parsed is Dictionary:
			var schema: String = str((parsed as Dictionary).get("schema", ""))
			if not schema.is_empty() and schema != RAMP_SCHEMA:
				skipped_schema_mismatch += 1
				push_warning("pool_overlay: schema mismatch on %s (%s)" % [json_path, schema])
				return false
	sm.set_shader_parameter("band_ramp", load(png_path))
	sm.set_shader_parameter("ramp_mix", 1.0)
	return true
