extends SceneTree
## Saved river clearance against authored core render and collision beds.

const Core := preload("res://scripts/core_terrain.gd")
const Ground := preload("res://scripts/rendered_ground.gd")
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var ground := Ground.new()
	var core := Core.new()
	if not ground.valid() or not core._load_metadata() or not core._load_heights():
		push_error("River bed source cannot load")
		quit(1)
		return
	core._build_collision_tile()
	var collision: HeightMapShape3D = core._tile_collision_body.get_child(0).shape
	if collision.map_data != core._heights_full:
		failures.append("Collision heightfield differs from authored bed")
	var world: Node = load("res://scenes/authored_world.tscn").instantiate()
	var water: Node = world.get_node("ConnectedWater")
	var measurements: Array = []
	for id: String in ["river_5856_0", "authored_excelsior_outflow_01"]:
		var node: MeshInstance3D = water.get_node(id)
		var vertices: PackedVector3Array = node.mesh.surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
		var stations := int(node.get_meta("station_count"))
		var total := 0
		var buried := 0
		var minimum_clearance := INF
		for index: int in stations:
			var point := (vertices[index * 2] + vertices[index * 2 + 1]) * 0.5
			if absf(point.x - 61.0) > 75.0 or absf(point.z + 280.0) > 75.0:
				continue
			total += 1
			var clearance := point.y - ground.sample(point.x, point.z)
			minimum_clearance = minf(minimum_clearance, clearance)
			if clearance <= 0.0:
				buried += 1
		if total == 0 or buried > 0:
			failures.append("%s has %d buried of %d bridge stations" % [id, buried, total])
		measurements.append({"id":id,"stations":total,"buried":buried,"minimum_clearance_m":minimum_clearance})
	world.free()
	core.free()
	print("RIVER_BED_CLEARANCE ", JSON.stringify({"ok":failures.is_empty(),"failures":failures,"measurements":measurements}))
	quit(0 if failures.is_empty() else 1)
