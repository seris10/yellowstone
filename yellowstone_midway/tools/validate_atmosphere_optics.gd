extends SceneTree

const Optics = preload("res://scripts/atmosphere_optics.gd")
const Controller = preload("res://scripts/yellowstone_atmosphere.gd")
var checks: int = 0
var failures: Array[String] = []


func _init() -> void:
	call_deferred("_run")


func _check(condition: bool, label: String) -> void:
	checks += 1
	if not condition:
		failures.append(label)


func _run() -> void:
	var first: Vector3 = Optics.angles(1)
	var second: Vector3 = Optics.angles(2)
	_check(first.x > first.y and first.y > first.z, "primary red outside violet")
	_check(second.x < second.y and second.y < second.z, "secondary color reversal")
	_check(rad_to_deg(first.x) > 42.0 and rad_to_deg(first.x) < 43.0, "primary red angle")
	_check(rad_to_deg(first.z) > 40.0 and rad_to_deg(first.z) < 41.0, "primary violet angle")
	_check(rad_to_deg(second.x) > 50.0 and rad_to_deg(second.x) < 52.0, "secondary red angle")
	_check(rad_to_deg(second.z) > 53.0 and rad_to_deg(second.z) < 55.0, "secondary violet angle")
	_check(Optics.secondary_ratio() > 0.05 and Optics.secondary_ratio() < 0.5, "secondary lower radiance")
	for order: int in [1, 2]:
		for index: float in [1.331, 1.335, 1.343]:
			var best: float = INF
			var angle: float = 0.0
			for sample: int in range(1, 90000):
				var incidence: float = deg_to_rad(float(sample) * 0.001)
				var refraction: float = asin(sin(incidence) / index)
				var deviation: float = float(order) * PI + 2.0 * incidence - 2.0 * float(order + 1) * refraction
				if deviation < best:
					best = deviation
					angle = absf(PI - deviation)
			_check(absf(angle - Optics.stationary_angle(index, order)) < 1e-8, "independent Snell sweep %s %s" % [order, index])
	var dry: Dictionary = {"precipitation_rate_mm_h": 0.0, "cloud_fraction": 0.16, "relative_humidity": 1.0}
	var rain: Dictionary = {"precipitation_rate_mm_h": 8.0, "cloud_fraction": 0.8, "relative_humidity": 0.75, "cloud_base_agl_m": 1050.0}
	var snow: Dictionary = rain.duplicate()
	snow["snow_fraction"] = 1.0
	var origin := Vector3(0.0, 20.0, 0.0)
	var wind := Vector3(2.0, 0.0, 0.0)
	var model = Optics.new()
	model.advance(3600.0, dry, origin, wind)
	_check(model.optical_depth == 0.0 and not model.active, "humid clear startup contains no rain curtain")
	model.advance(300.0, snow, origin, wind)
	_check(model.optical_depth == 0.0 and not model.active, "snow produces no liquid curtain")
	var no_cloud: Dictionary = rain.duplicate()
	no_cloud["cloud_fraction"] = 0.0
	model.advance(300.0, no_cloud, origin, wind)
	_check(model.optical_depth == 0.0, "cloud-free forcing does not create rain")
	model.advance(0.0, rain, origin, wind)
	_check(model.optical_depth == 0.0, "weather change has no instantaneous bow")
	model.advance(120.0, rain, origin, wind)
	var wet_depth: float = model.optical_depth
	var wet_center: Vector3 = model.center
	_check(wet_depth > 0.4 and wet_depth < 0.8, "finite liquid build up")
	model.advance(20.0, dry, origin, wind)
	_check(model.optical_depth < wet_depth and model.optical_depth > 0.1, "post-rain persistence and decay")
	_check(model.center.distance_to(wet_center + wind * 20.0) < 0.001, "curtain advection")
	model.advance(1500.0, dry, origin, wind)
	_check(model.optical_depth == 0.0 and not model.active, "finite residence time")
	var coarse = Optics.new()
	var fine = Optics.new()
	coarse.advance(120.0, rain, origin, wind)
	for i: int in range(1200):
		fine.advance(0.1, rain, origin, wind)
	_check(absf(coarse.optical_depth - fine.optical_depth) < 1e-10, "time partition invariant optical history")
	_check(coarse.center.distance_to(fine.center) < 0.1, "time partition invariant advection")
	var repeated = Optics.new()
	for i: int in range(100):
		repeated.advance(0.0, rain, origin, wind)
		repeated.advance(0.0, dry, origin, wind)
	_check(repeated.optical_depth == 0.0 and not repeated.active, "toggle sequence cannot reseed or fabricate time")
	_check(Optics.daylight_gate(Vector3(0.0, -0.1, 0.99).normalized()) == 0.0, "night suppression")
	_check(Optics.daylight_gate(Vector3(0.0, 0.5, 0.866)) == 1.0, "sun above horizon")
	for axis: Vector3 in [Vector3.RIGHT, Vector3.UP, Vector3.BACK]:
		var coordinate := Vector3(0.123, 0.456, 0.789)
		_check(absf(Optics.volume_sample(coordinate) - Optics.volume_sample(coordinate + axis)) < 1e-5, "periodic cloud field")
	_check(Optics.cloud_texture().get_width() == 64 and Optics.cloud_texture().get_depth() == 64, "bounded cloud volume texture")
	var nonempty: int = 0
	var blocked: int = 0
	for x: int in range(40):
		for z: int in range(40):
			var pos := Vector2(float(x) * 0.17, float(z) * 0.17)
			var body: float = Optics.cloud_body(pos, 0.16, 0.68)
			_check(body >= 0.0 and body <= 1.0, "bounded cloud body")
			if body > 0.2:
				nonempty += 1
			var observer := Vector3(pos.x * 800.0, 0.0, pos.y * 800.0)
			var clear: float = Optics.cloud_transmission(observer, Vector3.UP, 1000.0, 600.0, 0.00125, Vector2.ZERO, 0.0, 0.68, 1.0)
			_check(clear == 1.0, "clear solar beam")
			var overcast: float = Optics.cloud_transmission(observer, Vector3.UP, 1000.0, 600.0, 0.00125, Vector2.ZERO, 1.0, 0.68, 1.0)
			if overcast < 0.05:
				blocked += 1
	_check(nonempty > 40 and nonempty < 600, "visible broken clouds at startup fraction")
	_check(blocked > 1400, "cloud optical depth blocks direct sun")
	var world := Node3D.new()
	root.add_child(world)
	var sun := DirectionalLight3D.new()
	var target := Camera3D.new()
	world.add_child(sun)
	world.add_child(target)
	var atmosphere = Controller.new()
	world.add_child(atmosphere)
	atmosphere.configure(sun, Environment.new(), target)
	atmosphere.set_process(false)
	_check(not atmosphere._rainbow.visible, "controller default rainbow absent")
	_check(atmosphere._cloud_shell.mesh is QuadMesh, "cloud layer independent of camera far clipping")
	_check(atmosphere._cloud_shell.scale == Vector3.ONE, "quad keeps unscaled culling bounds")
	_check(atmosphere._cloud_shell.material_override.render_priority < atmosphere._rainbow_material.render_priority, "rainbow composites before foreground transparency")
	var result := {"schema": "yellowstone.atmosphere_optics.v1", "checks": checks, "failures": failures, "primary_angles_deg": [rad_to_deg(first.x), rad_to_deg(first.y), rad_to_deg(first.z)], "secondary_angles_deg": [rad_to_deg(second.x), rad_to_deg(second.y), rad_to_deg(second.z)], "secondary_radiance_ratio": Optics.secondary_ratio(), "cloud_fraction_016_sampled_body_fraction": float(nonempty) / 1600.0, "overcast_blocked_fraction": float(blocked) / 1600.0, "scope": "native analytical and controller checks; authored spatial forcing; no measured rainbow frequency"}
	var path: String = "res://../evidence/atmosphere-optics.json"
	var file := FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(result, "  ") + "\n")
	file.close()
	print(JSON.stringify(result))
	world.queue_free()
	quit(0 if failures.is_empty() else 1)
