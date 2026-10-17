class_name YellowstoneRiverTerrain
extends RefCounted
## Authored channel beds and spatial water-height display fields.

const WIDE_DEPTH_M := 0.53
const NARROW_DEPTH_M := 0.45
const BANK_BLEND_M := 1.5
const STAGE_SUPPORT_M := 64.0
const STAGE_GRID_M := 4.0

static func segments(rivers: Array, include_thermal: bool = true) -> Array:
	var result: Array = []
	for river: Dictionary in rivers:
		if not include_thermal and bool(river.get("thermal", false)):
			continue
		var points: Array = river.get("points", [])
		var width := float(river.get("width", 0.0))
		if points.size() < 2 or width <= 0.0:
			push_error("River display geometry requires points and positive width")
			return []
		for i: int in range(1, points.size()):
			var a := Vector3(points[i - 1][0], points[i - 1][1], points[i - 1][2])
			var b := Vector3(points[i][0], points[i][1], points[i][2])
			if Vector2(b.x - a.x, b.z - a.z).length_squared() > 0.000001:
				result.append({"a": a, "b": b, "half": width * 0.5,
					"depth": WIDE_DEPTH_M if width > 8.0 else NARROW_DEPTH_M})
	return result

static func projection(point: Vector2, segment: Dictionary) -> Vector3:
	var a: Vector3 = segment.a
	var b: Vector3 = segment.b
	var delta := Vector2(b.x - a.x, b.z - a.z)
	var t := clampf((point - Vector2(a.x, a.z)).dot(delta) / delta.length_squared(), 0.0, 1.0)
	var nearest := Vector2(a.x, a.z) + delta * t
	return Vector3(point.distance_squared_to(nearest), lerpf(a.y, b.y, t), t)

static func carve(heights: PackedFloat32Array, nx: int, nz: int, origin: Vector2,
		step: float, rivers: Array) -> Dictionary:
	var original := heights.duplicate()
	for segment: Dictionary in segments(rivers):
		var a: Vector3 = segment.a
		var b: Vector3 = segment.b
		var radius: float = segment.half + BANK_BLEND_M
		var lo := Vector2i(maxi(0, floori((minf(a.x, b.x) - radius - origin.x) / step)),
			maxi(0, floori((minf(a.z, b.z) - radius - origin.y) / step)))
		var hi := Vector2i(mini(nx - 1, ceili((maxf(a.x, b.x) + radius - origin.x) / step)),
			mini(nz - 1, ceili((maxf(a.z, b.z) + radius - origin.y) / step)))
		for z: int in range(lo.y, hi.y + 1):
			for x: int in range(lo.x, hi.x + 1):
				var sample := projection(origin + Vector2(x, z) * step, segment)
				var distance := sqrt(sample.x)
				if distance > radius:
					continue
				var weight := 1.0 - smoothstep(float(segment.half), radius, distance)
				var index := z * nx + x
				var target := lerpf(original[index], sample.y - float(segment.depth), weight)
				heights[index] = minf(heights[index], target)
	var count := 0
	var maximum := 0.0
	for index: int in heights.size():
		var cut := original[index] - heights[index]
		if cut > 0.000001:
			count += 1
			maximum = maxf(maximum, cut)
	return {"value_class": "authored_render_bed", "uncertainty": "unknown",
		"changed_vertices": count, "maximum_lowering_m": maximum,
		"wide_depth_m": WIDE_DEPTH_M, "narrow_depth_m": NARROW_DEPTH_M,
		"bank_blend_m": BANK_BLEND_M}

static func stage_image(rivers: Array, origin: Vector2, extent: Vector2,
		step: float = STAGE_GRID_M) -> Image:
	var size := Vector2i(ceili(extent.x / step), ceili(extent.y / step))
	var image := Image.create(size.x, size.y, false, Image.FORMAT_RGF)
	image.fill(Color(0.0, 0.0, 0.0, 1.0))
	var nearest := PackedFloat32Array()
	nearest.resize(size.x * size.y)
	nearest.fill(INF)
	for segment: Dictionary in segments(rivers, false):
		var a: Vector3 = segment.a
		var b: Vector3 = segment.b
		var lo := Vector2i(maxi(0, floori((minf(a.x, b.x) - STAGE_SUPPORT_M - origin.x) / step)),
			maxi(0, floori((minf(a.z, b.z) - STAGE_SUPPORT_M - origin.y) / step)))
		var hi := Vector2i(mini(size.x - 1, ceili((maxf(a.x, b.x) + STAGE_SUPPORT_M - origin.x) / step)),
			mini(size.y - 1, ceili((maxf(a.z, b.z) + STAGE_SUPPORT_M - origin.y) / step)))
		for z: int in range(lo.y, hi.y + 1):
			for x: int in range(lo.x, hi.x + 1):
				var sample := projection(origin + (Vector2(x, z) + Vector2.ONE * 0.5) * step, segment)
				var index := z * size.x + x
				if sample.x <= STAGE_SUPPORT_M * STAGE_SUPPORT_M and sample.x < nearest[index]:
					nearest[index] = sample.x
					image.set_pixel(x, z, Color(sample.y, 1.0, 0.0, 1.0))
	return image
