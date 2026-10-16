extends SceneTree
## Validate exported mesh/collision resources. Detects reversed rows, wrong offsets and seams.
var failures: Array[String] = []
var max_edge := 0.0
var max_normal := 0.0
var max_collision := 0.0

func _initialize() -> void:
	call_deferred("verify")

func verify() -> void:
	var world: Node3D=load("res://scenes/authored_world.tscn").instantiate()
	get_root().add_child(world)
	var tiles: Node=world.get_node("TerrainTiles")
	for z in 16:
		for x in 16:
			var tile: MeshInstance3D=tiles.get_node("Terrain_%02d_%02d"%[x,z])
			var arrays: Array=tile.mesh.surface_get_arrays(0)
			var v: PackedVector3Array=arrays[Mesh.ARRAY_VERTEX]
			var n: PackedVector3Array=arrays[Mesh.ARRAY_NORMAL]
			var shape: CollisionShape3D=tile.get_node("Ground").get_child(0)
			var heights: PackedFloat32Array=shape.shape.map_data
			for row in 65:
				for col in 65:
					var i:=row*65+col
					var collision_vertex:=shape.position+shape.scale*Vector3(float(col)-32.0,heights[i],float(row)-32.0)
					max_collision=maxf(max_collision,collision_vertex.distance_to(v[i]))
			if x<15:
				var other: MeshInstance3D=tiles.get_node("Terrain_%02d_%02d"%[x+1,z])
				var oa: Array=other.mesh.surface_get_arrays(0)
				for row in 65:
					max_edge=maxf(max_edge,(tile.position+v[row*65+64]).distance_to(other.position+oa[Mesh.ARRAY_VERTEX][row*65]))
					max_normal=maxf(max_normal,n[row*65+64].distance_to(oa[Mesh.ARRAY_NORMAL][row*65]))
			if z<15:
				var other: MeshInstance3D=tiles.get_node("Terrain_%02d_%02d"%[x,z+1])
				var oa: Array=other.mesh.surface_get_arrays(0)
				for col in 65:
					max_edge=maxf(max_edge,(tile.position+v[64*65+col]).distance_to(other.position+oa[Mesh.ARRAY_VERTEX][col]))
					max_normal=maxf(max_normal,n[64*65+col].distance_to(oa[Mesh.ARRAY_NORMAL][col]))
	if max_edge>.0005:failures.append("Terrain tile seam")
	if max_normal>.0001:failures.append("Terrain normal seam")
	if max_collision>.0005:failures.append("Collision differs from visual surface")
	var result: Dictionary={"ok":failures.is_empty(),"max_tile_edge_error_m":max_edge,"max_normal_error":max_normal,"max_collision_vertex_error_m":max_collision,"tile_count":tiles.get_child_count(),"failures":failures}
	FileAccess.open("res://tests/baked_validation.json",FileAccess.WRITE).store_string(JSON.stringify(result,"  "))
	print("BAKED_VALIDATION ",JSON.stringify(result))
	quit(0 if failures.is_empty() else 1)
