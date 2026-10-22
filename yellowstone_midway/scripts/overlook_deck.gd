extends RefCounted
## Raised Grand Prismatic overlook deck: platform, entry ramp, timber posts and rails with collision.

const DECK_X_M := -252.0
const DECK_Z_M := 159.0

## Build the deck group under parent from master-raster heights; owner_node owns nodes for packing.
static func build(parent: Node, height_field: RefCounted, routes: Array, materials: Dictionary, owner_node: Node = null) -> Node3D:
	var group := Node3D.new()
	group.name = "OverlookDeck"
	_own(group, parent, owner_node)
	var x := DECK_X_M
	var z := DECK_Z_M
	var y: float = height_field.sample(x,z)+.32
	var deck := BoxMesh.new()
	deck.size = Vector3(6.5,.18,4.5)
	deck.material = materials.deck
	var node := _add_geometry(deck,"ViewingPlatform",group,true,owner_node)
	node.position = Vector3(x,y,z)
	# Connect the eastern spur to the raised deck.
	var ramp_z:=160.05
	var ramp_start:=Vector3(x+5.0,height_field.sample(x+5.0,ramp_z)+.08,ramp_z)
	var nearest:=INF
	for route: Dictionary in routes:
		for point: Array in route.points:
			var d:=Vector2(float(point[0])-ramp_start.x,float(point[2])-ramp_z).length()
			if d<nearest:
				nearest=d
				ramp_start.y=float(point[1])+.002
	var ramp_end:=Vector3(x+3.15,y+.092,ramp_z)
	_add_geometry(_ramp(ramp_start,ramp_end,1.9,materials.wood),"OverlookEntryRamp",group,true,owner_node)
	# Explicit timber members with an open southern approach.
	var corners:=PackedVector3Array([Vector3(x-3.13,y+.09,z+2.05),Vector3(x-3.13,y+.09,z-2.05),Vector3(x+3.13,y+.09,z-2.05),Vector3(x+3.13,y+.09,z-.1)])
	for i in range(corners.size()-1):
		var a:=corners[i]
		var b:=corners[i+1]
		var count:=int(ceil(a.distance_to(b)/1.6))
		for j in range(count+1):
			var base:=a.lerp(b,float(j)/float(count))
			var post:=BoxMesh.new()
			post.size=Vector3(.12,1.08,.12)
			post.material=materials.post
			var post_node:=_add_geometry(post,"OverlookPost",group,true,owner_node)
			post_node.position=base+Vector3.UP*.54
		_beam_between(a+Vector3.UP*1.04,b+Vector3.UP*1.04,.12,group,materials.beam,owner_node)
		_beam_between(a+Vector3.UP*.52,b+Vector3.UP*.52,.09,group,materials.beam,owner_node)
	return group

static func _own(node: Node, parent: Node, owner_node: Node) -> void:
	parent.add_child(node)
	if owner_node != null:
		node.owner = owner_node

static func _add_geometry(mesh: Mesh, name: String, parent: Node, collision: bool, owner_node: Node) -> MeshInstance3D:
	var node := MeshInstance3D.new()
	node.mesh = mesh
	node.name = name
	_own(node,parent,owner_node)
	if collision:
		var body := StaticBody3D.new()
		_own(body,node,owner_node)
		var shape := CollisionShape3D.new()
		shape.shape = mesh.create_trimesh_shape()
		_own(shape,body,owner_node)
	return node

static func _beam_between(a: Vector3, b: Vector3, thickness: float, parent: Node, beam_material: Material, owner_node: Node) -> void:
	var beam:=BoxMesh.new()
	beam.size=Vector3(thickness,thickness,a.distance_to(b))
	beam.material=beam_material
	var node:=_add_geometry(beam,"TimberRail",parent,true,owner_node)
	node.position=(a+b)*.5
	node.look_at_from_position(node.position,b,Vector3.UP)

## Two-point ribbon with the bake ribbon layout: side offsets, arc-length UVs and white vertex color.
static func _ramp(start: Vector3, end: Vector3, width: float, ramp_material: Material) -> ArrayMesh:
	var points := PackedVector3Array([start, end])
	var vertices := PackedVector3Array()
	var normals := PackedVector3Array()
	var uvs := PackedVector2Array()
	var colors := PackedColorArray()
	var indices := PackedInt32Array()
	var arc := 0.0
	for i in points.size():
		var before := maxi(i-1,0)
		var after := mini(i+1,points.size()-1)
		var tangent := (points[after]-points[before]).normalized()
		var side := Vector3(-tangent.z,0,tangent.x).normalized()
		if i>0:
			arc += points[i].distance_to(points[i-1])
		for s in 2:
			vertices.append(points[i]+side*(float(s)-0.5)*width)
			normals.append(side.cross(tangent).normalized())
			uvs.append(Vector2(float(s),arc))
			colors.append(Color(1.0, 1, 1))
		if i>0:
			var a := (i-1)*2
			indices.append_array(PackedInt32Array([a,a+2,a+1,a+1,a+2,a+3]))
	var arrays := []
	arrays.resize(Mesh.ARRAY_MAX)
	arrays[Mesh.ARRAY_VERTEX] = vertices
	arrays[Mesh.ARRAY_NORMAL] = normals
	arrays[Mesh.ARRAY_TEX_UV] = uvs
	arrays[Mesh.ARRAY_INDEX] = indices
	arrays[Mesh.ARRAY_COLOR] = colors
	var mesh := ArrayMesh.new()
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arrays)
	mesh.surface_set_material(0,ramp_material)
	return mesh
