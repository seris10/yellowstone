class_name MidwayPoolOverlay
extends Node
## Runtime shim: assigns Python-authored pigment ramps to baked thermal pools.
## Reads res://data/pool_shells.json and res://assets/textures/pool_ramps/<shell_id>.png.
## Guarded: without sidecars, two-color water look is used.
func _ready() -> void:
	var shells_path := "res://data/pool_shells.json"
	if not FileAccess.file_exists(shells_path):
		return
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(shells_path))
	if not parsed is Dictionary or not parsed.has("pool_shells"):
		push_warning("pool_overlay: pool_shells.json has no pool_shells array.")
		return
	var by_name: Dictionary = {}
	for shell: Dictionary in parsed["pool_shells"]:
		by_name[str(shell.get("name", ""))] = shell
	var applied := 0
	for node in get_tree().get_nodes_in_group("thermal_surfaces"):
		if not node.has_meta("feature_name"):
			continue
		var shell: Dictionary = by_name.get(str(node.get_meta("feature_name")), {})
		if shell.is_empty():
			continue
		var ramp_path := "res://assets/textures/pool_ramps/%s.png" % str(shell.get("id", ""))
		if not ResourceLoader.exists(ramp_path):
			continue
		var mesh_instance := node as MeshInstance3D
		if mesh_instance == null or mesh_instance.mesh == null:
			continue
		var mat: Material = mesh_instance.mesh.surface_get_material(0)
		if mat is ShaderMaterial:
			(mat as ShaderMaterial).set_shader_parameter("band_ramp", load(ramp_path))
			(mat as ShaderMaterial).set_shader_parameter("ramp_mix", 1.0)
			applied += 1
	print("pool_overlay: applied %d authored pigment ramps." % applied)
