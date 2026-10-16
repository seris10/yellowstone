class_name MidwayPoolOverlay
extends Node
const ReleaseData = preload("res://scripts/release_data.gd")

const RAMP_DIR_PRIMARY := "res://assets/textures/pool_ramps/"
const RAMP_DIR_SECONDARY := "res://assets/textures/pool_ramps/"
const RAMP_SCHEMA := "yellowstone.pool_radiative_ramp.v1"
const POOL_SHELLS_PATH := "res://data/pool_shells.json"
const DISPLAY_CONFIG := "res://data/display/prismatic.json"
const DISPLAY_RAMP := "res://assets/textures/prismatic_water_display.png"

var applied_count: int = 0
var primary_applied: int = 0
var secondary_applied: int = 0
var skipped_schema_mismatch: int = 0

func _ready() -> void:
	reload()

func reload() -> void:
	applied_count = 0
	primary_applied = 0
	secondary_applied = 0
	skipped_schema_mismatch = 0
	for node: Node in get_tree().get_nodes_in_group("thermal_surfaces"):
		var mesh: MeshInstance3D = node as MeshInstance3D
		if mesh != null and mesh.mesh != null:
			var material: ShaderMaterial = mesh.mesh.surface_get_material(0) as ShaderMaterial
			if material != null:
				material.set_shader_parameter("ramp_mix", 0.0)
				material.set_shader_parameter("display_ramp_mix", 0.0)
				material.set_shader_parameter("display_band_ramp", null)
				material.remove_meta("pool_display_class")
				material.remove_meta("pool_display_sha256")
				material.set_shader_parameter("band_ramp", null)
				material.remove_meta("pool_ramp_path")
				material.remove_meta("pool_ramp_sha256")
	if not ReleaseData.file_exists(POOL_SHELLS_PATH):
		return
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string(POOL_SHELLS_PATH))
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
		_apply_display(sm, pool_id)
		# Published radiative-transfer ramp in the selected generation.
		var primary_png: String = RAMP_DIR_PRIMARY + "ramp_" + pool_id + ".png"
		var primary_json: String = RAMP_DIR_PRIMARY + "ramp_" + pool_id + ".json"
		if _apply_ramp(sm, primary_png, primary_json, pool_id):
			primary_applied += 1
			applied_count += 1
			continue
		# Authored fallback for a project without a selected generation.
		if not ReleaseData.active.is_empty():
			continue
		var secondary_png: String = RAMP_DIR_SECONDARY + pool_id + ".png"
		if ReleaseData.file_exists(secondary_png):
			sm.set_shader_parameter("band_ramp", ReleaseData.texture(secondary_png))
			sm.set_shader_parameter("ramp_mix", 1.0)
			secondary_applied += 1
			applied_count += 1
	print("pool_overlay: primary=%d secondary=%d skipped_schema_mismatch=%d" % [primary_applied, secondary_applied, skipped_schema_mismatch])

func _apply_ramp(sm: ShaderMaterial, png_path: String, json_path: String, pool_id: String) -> bool:
	if not ReleaseData.file_exists(png_path) or not ReleaseData.file_exists(json_path):
		return false
	var parsed: Variant = JSON.parse_string(ReleaseData.get_file_as_string(json_path))
	if not parsed is Dictionary or parsed.get("schema") != RAMP_SCHEMA or parsed.get("pool_id") != pool_id:
		skipped_schema_mismatch += 1
		push_warning("pool_overlay: incompatible ramp metadata on %s" % json_path)
		return false
	var texture: Texture2D = ReleaseData.texture(png_path)
	if texture == null:
		return false
	sm.set_shader_parameter("band_ramp", texture)
	sm.set_shader_parameter("ramp_mix", 1.0)
	sm.set_meta("pool_ramp_path", ReleaseData.resolve_path(png_path))
	sm.set_meta("pool_ramp_sha256", ReleaseData.get_sha256(png_path))
	return true

func _apply_display(sm: ShaderMaterial, pool_id: String) -> void:
	if not FileAccess.file_exists(DISPLAY_CONFIG):
		return
	var config: Variant = JSON.parse_string(FileAccess.get_file_as_string(DISPLAY_CONFIG))
	if not config is Dictionary or config.get("schema") != "yellowstone.spring_display.v1":
		return
	if config.get("pool_id") != pool_id or not ResourceLoader.exists(DISPLAY_RAMP):
		return
	var texture: Texture2D = load(DISPLAY_RAMP) as Texture2D
	if texture == null:
		return
	sm.set_shader_parameter("display_band_ramp", texture)
	sm.set_shader_parameter("display_ramp_mix", 1.0)
	sm.set_meta("pool_display_class", config.get("value_class", "authored_image_informed_display"))
	sm.set_meta("pool_display_sha256", FileAccess.get_sha256(DISPLAY_RAMP))
