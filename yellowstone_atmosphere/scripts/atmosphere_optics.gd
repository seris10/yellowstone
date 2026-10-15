class_name YellowstoneAtmosphereOptics
extends RefCounted

## Spherical-drop optics and an authored advected rain curtain.

const DROP_INDICES := Vector3(1.331, 1.335, 1.343)
const CURTAIN_RADIUS_M: float = 1050.0
const BUILD_SECONDS: float = 75.0
const FALL_SPEED_MPS: float = 6.0
const MAX_STEP_SECONDS: float = 2.0

var optical_depth: float = 0.0
var center: Vector3 = Vector3.ZERO
var base_y_m: float = 0.0
var top_y_m: float = 800.0
var elapsed_seconds: float = 0.0
var active: bool = false


static func stationary_angle(index: float, reflections: int) -> float:
	var order: float = float(reflections + 1)
	var incidence: float = acos(sqrt((index * index - 1.0) / (order * order - 1.0)))
	var refraction: float = asin(sin(incidence) / index)
	var deviation: float = float(reflections) * PI + 2.0 * incidence - 2.0 * order * refraction
	return absf(PI - deviation)


static func angles(reflections: int) -> Vector3:
	return Vector3(stationary_angle(DROP_INDICES.x, reflections), stationary_angle(DROP_INDICES.y, reflections), stationary_angle(DROP_INDICES.z, reflections))


static func reflection_energy(index: float, reflections: int) -> float:
	var order: float = float(reflections + 1)
	var incidence: float = acos(sqrt((index * index - 1.0) / (order * order - 1.0)))
	var refraction: float = asin(sin(incidence) / index)
	var rs: float = pow(sin(incidence - refraction) / sin(incidence + refraction), 2.0)
	var rp: float = pow(tan(incidence - refraction) / tan(incidence + refraction), 2.0)
	return 0.5 * (pow(1.0 - rs, 2.0) * pow(rs, reflections) + pow(1.0 - rp, 2.0) * pow(rp, reflections))


static func secondary_ratio() -> float:
	var first: Vector3 = angles(1)
	var second: Vector3 = angles(2)
	var solid_angle_ratio: float = sin(first.y) * absf(first.x - first.z) / (sin(second.y) * absf(second.x - second.z))
	return reflection_energy(DROP_INDICES.y, 2) / reflection_energy(DROP_INDICES.y, 1) * solid_angle_ratio


func advance(seconds: float, weather: Dictionary, observer: Vector3, wind_mps: Vector3) -> void:
	if not is_finite(seconds) or seconds <= 0.0:
		return
	var remaining: float = seconds
	while remaining > 0.0:
		var step: float = minf(remaining, MAX_STEP_SECONDS)
		_step(step, weather, observer, wind_mps)
		remaining -= step


func _step(seconds: float, weather: Dictionary, observer: Vector3, wind_mps: Vector3) -> void:
	elapsed_seconds += seconds
	var liquid_rate: float = maxf(0.0, float(weather.get("precipitation_rate_mm_h", 0.0))) * (1.0 - clampf(float(weather.get("snow_fraction", 0.0)), 0.0, 1.0))
	var cloud_fraction: float = clampf(float(weather.get("cloud_fraction", 0.0)), 0.0, 1.0)
	liquid_rate *= smoothstep(0.08, 0.5, cloud_fraction)
	if liquid_rate > 0.02 and not active:
		var bearing: Vector3 = wind_mps.normalized() if wind_mps.length() > 0.05 else Vector3(0.8, 0.0, -0.6)
		var transverse: Vector3 = Vector3(-bearing.z, 0.0, bearing.x)
		center = observer + bearing * 1550.0 + transverse * 650.0
		base_y_m = observer.y - 25.0
		top_y_m = observer.y + clampf(float(weather.get("cloud_base_agl_m", 1050.0)), 100.0, 2200.0)
		active = true
	if not active:
		return
	center += wind_mps * seconds
	var humidity: float = clampf(float(weather.get("relative_humidity", 0.55)), 0.0, 1.0)
	var fall_time: float = (top_y_m - base_y_m) / FALL_SPEED_MPS
	var lifetime: float = minf(fall_time, lerpf(35.0, 170.0, humidity))
	var target: float = clampf(0.24 * sqrt(liquid_rate), 0.0, 1.8)
	var time_constant: float = BUILD_SECONDS if target > optical_depth else maxf(lifetime, 15.0)
	optical_depth = lerpf(optical_depth, target, 1.0 - exp(-seconds / time_constant))
	if optical_depth < 0.0001 and liquid_rate <= 0.02:
		optical_depth = 0.0
		active = false


static func daylight_gate(sun_direction: Vector3) -> float:
	return smoothstep(0.0, sin(deg_to_rad(4.0)), sun_direction.y)


static var _cloud_slices: Array[Image] = []
static var _cloud_texture: ImageTexture3D
const CLOUD_TEXTURE_SIZE: int = 64


static func cloud_texture() -> ImageTexture3D:
	if _cloud_texture != null:
		return _cloud_texture
	var noise_source := FastNoiseLite.new()
	noise_source.seed = 445011
	noise_source.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	noise_source.frequency = 0.045
	noise_source.fractal_type = FastNoiseLite.FRACTAL_FBM
	noise_source.fractal_octaves = 3
	_cloud_slices = noise_source.get_seamless_image_3d(CLOUD_TEXTURE_SIZE, CLOUD_TEXTURE_SIZE, CLOUD_TEXTURE_SIZE, false, 0.2, true)
	_cloud_texture = ImageTexture3D.new()
	_cloud_texture.create(_cloud_slices[0].get_format(), CLOUD_TEXTURE_SIZE, CLOUD_TEXTURE_SIZE, CLOUD_TEXTURE_SIZE, false, _cloud_slices)
	return _cloud_texture


static func volume_sample(uvw: Vector3) -> float:
	cloud_texture()
	var p: Vector3 = uvw * float(CLOUD_TEXTURE_SIZE) - Vector3.ONE * 0.5
	var cell: Vector3i = Vector3i(p.floor())
	var fraction: Vector3 = p - p.floor()
	var value: float = 0.0
	for z: int in range(2):
		for y: int in range(2):
			for x: int in range(2):
				var sample_value: float = _cloud_slices[posmod(cell.z + z, CLOUD_TEXTURE_SIZE)].get_pixel(posmod(cell.x + x, CLOUD_TEXTURE_SIZE), posmod(cell.y + y, CLOUD_TEXTURE_SIZE)).r
				value += sample_value * (fraction.x if x else 1.0 - fraction.x) * (fraction.y if y else 1.0 - fraction.y) * (fraction.z if z else 1.0 - fraction.z)
	return value


static func cloud_shape(p: Vector2, detail: float, y01: float = 0.32) -> float:
	var uvw := Vector3(p.x / 8.0, y01 * 0.35 + 0.1, p.y / 8.0)
	var broad: float = volume_sample(uvw)
	return lerpf(broad, broad * 0.85 + volume_sample(uvw * 2.01 + Vector3(0.17, 0.29, 0.41)) * 0.15, detail)


static func cloud_body(p: Vector2, coverage: float, detail: float, y01: float = 0.32) -> float:
	if coverage <= 0.001:
		return 0.0
	var threshold: float = lerpf(0.75, 0.24, coverage)
	var body: float = smoothstep(threshold - 0.065, threshold + 0.065, cloud_shape(p, detail, y01) - pow((y01 - 0.32) * 1.3, 2.0) * 0.22)
	return lerpf(body, 1.0, smoothstep(0.85, 1.0, coverage))


static func cloud_transmission(origin: Vector3, sun: Vector3, base: float, thickness: float, scale_m_inv: float, offset: Vector2, cover: float, detail: float, density: float) -> float:
	if sun.y <= 0.0:
		return 0.0
	var optical_column: float = 0.0
	for i: int in range(4):
		var height: float = base + thickness * (float(i) + 0.5) / 4.0
		var distance: float = maxf(0.0, (height - origin.y) / sun.y)
		var p: Vector3 = origin + sun * distance
		optical_column += cloud_body(Vector2(p.x, p.z) * scale_m_inv + offset, cover, detail, (float(i) + 0.5) / 4.0) / 4.0
	return exp(-optical_column * 3.4 * density / maxf(sun.y, 0.08))
