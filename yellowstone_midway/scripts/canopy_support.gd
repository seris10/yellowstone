class_name YellowstoneCanopySupport
extends RefCounted
## Authored canopy connections to rendered bole centerlines.

const Lodgepole = preload("res://scripts/lodgepole_library.gd")
const SEARCH_M := 2.0

static func prepare(records: Array) -> Dictionary:
	var profiles: Dictionary = {}
	var bins: Dictionary = {}
	for record: Dictionary in records:
		if str(record.get("kind", "")) != "pine":
			continue
		var form := Lodgepole.archetype(record)
		if not profiles.has(form):
			var rings: Dictionary = {}
			var heights: Array[float] = []
			for row: Dictionary in Lodgepole.metadata().get("lods", []):
				if str(row.archetype) == form and int(row.lod) == 0:
					for pair: Array in row.bole_profile_m:
						heights.append(float(pair[0]))
			var local := Transform3D.IDENTITY
			for asset: Array in Lodgepole.load_assets(form):
				if str(asset[4]) != "Bole" or float(asset[2]) != 0.0:
					continue
				local = asset[1]
				var vertices: PackedVector3Array = asset[0].surface_get_arrays(0)[Mesh.ARRAY_VERTEX]
				for point: Vector3 in vertices:
					var key := 0
					for index: int in heights.size():
						if absf(heights[index] - point.y) < absf(heights[key] - point.y):
							key = index
					if not rings.has(key):
						rings[key] = []
					rings[key].append(point)
			var keys: Array = rings.keys()
			keys.sort()
			var points := PackedVector3Array()
			for key: int in keys:
				var center := Vector3.ZERO
				var ring: Array = rings[key]
				for point: Vector3 in ring:
					center += point
				points.append(center / float(ring.size()))
			profiles[form] = {"points": points, "local": local}
		var position: Array = record.position
		var transform: Transform3D = Transform3D(Basis(Vector3.UP, float(record.yaw)), Vector3(position[0], position[1], position[2])) * Lodgepole.local_transform(record, "Bole") * profiles[form].local
		var points: PackedVector3Array = profiles[form].points
		if points.size() < 2:
			continue
		var key := Vector2i(floori(float(position[0]) / SEARCH_M), floori(float(position[2]) / SEARCH_M))
		if not bins.has(key):
			bins[key] = []
		bins[key].append({"transform": transform, "profile": points, "base": transform.origin, "top_y": (transform * points[-1]).y})
	return bins

static func connection(top: Vector3, ground_y: float, bins: Dictionary) -> Dictionary:
	var key := Vector2i(floori(top.x / SEARCH_M), floori(top.z / SEARCH_M))
	var nearest := SEARCH_M * SEARCH_M
	var result := {"point": Vector3(top.x, ground_y - 0.04, top.z), "attached": false}
	for z: int in range(key.y - 1, key.y + 2):
		for x: int in range(key.x - 1, key.x + 2):
			for host: Dictionary in bins.get(Vector2i(x, z), []):
				if host.top_y < top.y - 2.0 or host.base.y >= top.y - 0.1:
					continue
				var distance_squared := Vector2(top.x - host.base.x, top.z - host.base.z).length_squared()
				if distance_squared > nearest:
					continue
				var patch_base := top.y - minf((top.y - ground_y) * 0.70, 2.0) * 1.05
				var target_y := clampf(patch_base - 0.12, host.base.y + 0.1, host.top_y - 0.1)
				var local_y: float = (target_y - host.transform.origin.y) / host.transform.basis.y.y
				var points: PackedVector3Array = host.profile
				for index: int in range(1, points.size()):
					if local_y < points[index - 1].y or local_y > points[index].y:
						continue
					var weight := (local_y - points[index - 1].y) / (points[index].y - points[index - 1].y)
					var point: Vector3 = host.transform * points[index - 1].lerp(points[index], weight)
					if Vector2(top.x - point.x, top.z - point.z).length() > SEARCH_M:
						continue
					result = {"point": point, "attached": true}
					nearest = distance_squared
					break
	return result
