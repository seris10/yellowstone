class_name YellowstoneWeatherSnapshotReader
extends Node

## Read local JSON weather and pass validated state to YellowstoneAtmosphereController.

## Freshness modes: wall_clock, simulation_clock, disabled. See the readme, Snapshot freshness.


const SUPPORTED_SCHEMA_VERSIONS: Array[int] = [1, 2]

const FRESHNESS_WALL_CLOCK := "wall_clock"
const FRESHNESS_SIMULATION_CLOCK := "simulation_clock"
const FRESHNESS_DISABLED := "disabled"

const REQUIRED_WEATHER_FIELDS: Array[String] = [
	"air_temperature_c",
	"relative_humidity",
	"wind_speed_mps",
	"wind_direction_deg",
	"cloud_fraction",
	"precipitation_rate_mm_h",
	"snow_fraction",
	"visibility_m",
]

const OPTIONAL_WEATHER_RANGES: Dictionary = {
	"dewpoint_c": Vector2(-80.0, 45.0),
	"cloud_base_agl_m": Vector2(100.0, 10000.0),
	"cloud_thickness_m": Vector2(100.0, 5000.0),
	"ground_wetness_fraction": Vector2(-1.0, 1.0),
}

const REQUIRED_WEATHER_RANGES: Dictionary = {
	"air_temperature_c": Vector2(-70.0, 60.0),
	"relative_humidity": Vector2(0.0, 1.0),
	"wind_speed_mps": Vector2(0.0, 65.0),
	"wind_direction_deg": Vector2(0.0, 360.0),
	"cloud_fraction": Vector2(0.0, 1.0),
	"precipitation_rate_mm_h": Vector2(0.0, 250.0),
	"snow_fraction": Vector2(0.0, 1.0),
	"visibility_m": Vector2(100.0, 100000.0),
}

@export_group("Snapshot")

## Poll live_snapshot_path when present; otherwise use the shipped snapshot.
@export var snapshot_path: String = "res://data/weather_snapshot.json"

## Live override written by the Python HTTP consumer; polled first when present.
@export var live_snapshot_path: String = "user://weather/latest.json"

@export_range(1.0, 600.0, 1.0)
var poll_interval_seconds: float = 15.0

@export_group("Freshness")

@export_enum("wall_clock", "simulation_clock", "disabled")
var freshness_mode: String = FRESHNESS_WALL_CLOCK

@export_range(60.0, 172800.0, 60.0)
var max_snapshot_age_seconds: float = 7200.0

@export_range(0.0, 86400.0, 60.0)
var allowed_future_seconds: float = 300.0

@export var warn_on_missing_snapshot: bool = true

@export_group("Validation")

@export var require_all_weather_fields: bool = true
@export var require_solar_pair: bool = true


var _controller: YellowstoneAtmosphereController
var _elapsed: float = 0.0

var _simulation_epoch_unix: float = 0.0
var _has_simulation_epoch: bool = false

# Content signature catches rapid atomic replacements on filesystems with coarse timestamp resolution.
var _last_signature: int = -1

var _warned_missing: bool = false
var _warned_stale: bool = false
var _warned_invalid: bool = false
var _warned_schema: bool = false


## Bind this reader to the atmosphere controller.
func bind(controller: YellowstoneAtmosphereController) -> void:
	_controller = controller
	poll_now()


## Supply the current simulation time when freshness_mode is "simulation_clock".
func set_simulation_epoch_unix(epoch_unix: float) -> void:
	if not _is_finite_number(epoch_unix):
		push_warning(
			"Weather reader received a non-finite simulation timestamp."
		)
		return

	_simulation_epoch_unix = float(epoch_unix)
	_has_simulation_epoch = true


## Clear simulation time; simulation_clock freshness rejects snapshots until time is supplied.
func clear_simulation_epoch() -> void:
	_has_simulation_epoch = false


func _process(delta: float) -> void:
	_elapsed += delta
	if _elapsed < maxf(poll_interval_seconds, 0.1):
		return

	_elapsed = 0.0
	poll_now()


## Poll and apply a new snapshot if one is available and valid.
func poll_now() -> bool:
	if _controller == null:
		return false

	var active_path: String = _resolve_active_snapshot_path()
	if active_path.is_empty():
		if warn_on_missing_snapshot and not _warned_missing:
			push_warning(
				("Weather snapshot not found at '%s' or '%s'; "
				+ "retaining the current atmosphere state.") % [live_snapshot_path, snapshot_path]
			)
			_warned_missing = true
		return false

	var bytes := _read_file_bytes(active_path)
	if bytes.is_empty():
		_warn_once(
			"invalid",
			("Could not read weather snapshot '%s'; "
			+ "retaining the last valid state.") % active_path
		)
		return false

	var signature := hash(bytes)
	if signature == _last_signature:
		return false

	var text := bytes.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)

	if parsed == null or not (parsed is Dictionary):
		_warn_once(
			"invalid",
			"Weather snapshot is not a JSON object; "
			+ "retaining the last valid state."
		)
		return false

	var root: Dictionary = parsed as Dictionary

	if not _validate_root(root):
		return false

	var freshness_result := _validate_freshness(root)
	if not freshness_result:
		return false

	var weather_variant: Variant = root.get("weather", null)
	if not (weather_variant is Dictionary):
		_warn_once(
			"invalid",
			"Weather snapshot 'weather' must be an object."
		)
		return false

	var weather: Dictionary = weather_variant as Dictionary
	if not _validate_weather(weather):
		return false

	var state: Dictionary = weather.duplicate(true)

	var solar_variant: Variant = root.get("solar", null)
	if solar_variant != null:
		if not (solar_variant is Dictionary):
			_warn_once(
				"invalid",
				"Weather snapshot 'solar' must be an object."
			)
			return false

		var solar: Dictionary = solar_variant as Dictionary
		if not _validate_solar(solar):
			return false

		state.merge(solar, true)

	var terrain_variant: Variant = root.get("terrain", null)
	if terrain_variant != null:
		if not (terrain_variant is Dictionary):
			_warn_once(
				"invalid",
				"Weather snapshot 'terrain' must be an object."
			)
			return false
		var terrain: Dictionary = (terrain_variant as Dictionary).duplicate(true)
		if not _validate_terrain(terrain):
			return false
		state["terrain"] = terrain

	_controller.set_weather_state(state)

	_last_signature = signature
	_warned_missing = false
	_warned_stale = false
	_warned_invalid = false
	_warned_schema = false

	return true


func _read_file_bytes(path: String) -> PackedByteArray:
	var file := FileAccess.open(path, FileAccess.READ)
	if file == null:
		return PackedByteArray()

	var length := file.get_length()
	if length <= 0:
		file.close()
		return PackedByteArray()

	var bytes := file.get_buffer(length)
	file.close()
	return bytes


func _validate_root(root: Dictionary) -> bool:
	var schema_value: Variant = root.get("schema_version", null)

	if not _is_number(schema_value):
		_warn_once(
			"schema",
			"Weather snapshot requires numeric schema_version."
		)
		return false

	var schema_int: int = int(schema_value)
	if not SUPPORTED_SCHEMA_VERSIONS.has(schema_int):
		_warn_once(
			"schema",
			"Unsupported weather snapshot schema_version %s; expected one of %s."
			% [str(schema_value), str(SUPPORTED_SCHEMA_VERSIONS)]
		)
		return false

	var generated_value: Variant = root.get("generated_at_unix", null)
	if not _is_finite_number(generated_value):
		_warn_once(
			"invalid",
			"Weather snapshot requires finite generated_at_unix."
		)
		return false

	# Schema 2 adds valid_time_unix and simulation_time_unix; if present, require finite numbers.
	if schema_int >= 2:
		for field_name in ["valid_time_unix", "simulation_time_unix"]:
			if root.has(field_name) and not _is_finite_number(root[field_name]):
				_warn_once(
					"invalid",
					"Weather snapshot '%s' must be a finite number." % field_name
				)
				return false

	return true


func _resolve_active_snapshot_path() -> String:
	var live_trim: String = live_snapshot_path.strip_edges()
	if not live_trim.is_empty() and FileAccess.file_exists(live_trim):
		return live_trim
	var baked: String = snapshot_path.strip_edges()
	if not baked.is_empty() and FileAccess.file_exists(baked):
		return baked
	return ""


func _validate_terrain(terrain: Dictionary) -> bool:
	# Optional per-field range check; a missing field is accepted (sentinel passthrough).
	var ranges: Dictionary = {
		"snow_cover_fraction": Vector2(0.0, 1.0),
		"snow_water_equivalent_mm": Vector2(0.0, 100000.0),
		"puddle_fraction": Vector2(0.0, 1.0),
		"soil_temperature_c": Vector2(-80.0, 60.0),
		"ground_wetness_fraction": Vector2(0.0, 1.0),
		"cloud_shadow_fraction": Vector2(0.0, 1.0),
		"steam_intensity": Vector2(0.0, 10.0),
		"insect_activity": Vector2(0.0, 10.0),
	}
	for field_name in terrain.keys():
		if not ranges.has(field_name):
			continue
		if not _validate_range_field(terrain, field_name, ranges[field_name]):
			return false
	return true


func _validate_freshness(root: Dictionary) -> bool:
	if freshness_mode == FRESHNESS_DISABLED:
		return true

	if freshness_mode == FRESHNESS_SIMULATION_CLOCK:
		if not _has_simulation_epoch:
			_warn_once(
				"stale",
				"Weather reader uses simulation_clock freshness, "
				+ "but no simulation timestamp has been supplied."
			)
			return false

	if freshness_mode != FRESHNESS_WALL_CLOCK \
	and freshness_mode != FRESHNESS_SIMULATION_CLOCK:
		push_warning(
			"Unknown weather freshness_mode '%s'; using wall_clock."
			% freshness_mode
		)
		freshness_mode = FRESHNESS_WALL_CLOCK

	var generated_at := float(root.get("valid_time_unix", root.get("simulation_time_unix", root["generated_at_unix"]))) if freshness_mode == FRESHNESS_SIMULATION_CLOCK else float(root["generated_at_unix"])
	var reference_time := Time.get_unix_time_from_system()

	if freshness_mode == FRESHNESS_SIMULATION_CLOCK:
		reference_time = _simulation_epoch_unix

	var age_seconds := reference_time - generated_at

	if age_seconds < -allowed_future_seconds:
		_warn_once(
			"stale",
			("Weather snapshot is from the future by %.0f seconds; "
			+ "retaining the last valid state.") % abs(age_seconds)
		)
		return false

	if age_seconds > max_snapshot_age_seconds:
		_warn_once(
			"stale",
			("Weather snapshot is %.0f seconds old; "
			+ "retaining the last valid state.") % age_seconds
		)
		return false

	return true


func _validate_weather(weather: Dictionary) -> bool:
	if require_all_weather_fields:
		for field_name in REQUIRED_WEATHER_FIELDS:
			if not weather.has(field_name):
				_warn_once(
					"invalid",
					"Weather snapshot is missing required field '%s'."
					% field_name
				)
				return false

	for field_name in REQUIRED_WEATHER_RANGES.keys():
		if not weather.has(field_name):
			continue

		if not _validate_range_field(
			weather,
			field_name,
			REQUIRED_WEATHER_RANGES[field_name]
		):
			return false

	for field_name in OPTIONAL_WEATHER_RANGES.keys():
		if not weather.has(field_name):
			continue

		if not _validate_range_field(
			weather,
			field_name,
			OPTIONAL_WEATHER_RANGES[field_name]
		):
			return false

	return true


func _validate_solar(solar: Dictionary) -> bool:
	var has_azimuth := solar.has("solar_azimuth_deg")
	var has_elevation := solar.has("solar_elevation_deg")

	if not has_azimuth and not has_elevation:
		return true

	if require_solar_pair and has_azimuth != has_elevation:
		_warn_once(
			"invalid",
			"Solar override requires both solar_azimuth_deg "
			+ "and solar_elevation_deg."
		)
		return false

	if has_azimuth:
		var azimuth_range := Vector2(0.0, 360.0)
		if not _validate_range_field(
			solar,
			"solar_azimuth_deg",
			azimuth_range,
			true
		):
			return false

	if has_elevation:
		var elevation_range := Vector2(-90.0, 90.0)
		if not _validate_range_field(
			solar,
			"solar_elevation_deg",
			elevation_range
		):
			return false

	return true


func _validate_range_field(
	values: Dictionary,
	field_name: String,
	bounds: Vector2,
	exclusive_upper: bool = false
) -> bool:
	var value: Variant = values.get(field_name, null)

	if not _is_finite_number(value):
		_warn_once(
			"invalid",
			"Weather field '%s' must be a finite number." % field_name
		)
		return false

	var number := float(value)
	var lower := bounds.x
	var upper := bounds.y

	var below_lower := number < lower
	var above_upper := (
		number >= upper if exclusive_upper else number > upper
	)

	if below_lower or above_upper:
		var upper_text := (
			"< %.4f" % upper
			if exclusive_upper
			else "<= %.4f" % upper
		)

		_warn_once(
			"invalid",
			"Weather field '%s' must satisfy %.4f <= value %s; got %.6f."
			% [field_name, lower, upper_text, number]
		)
		return false

	return true


func _is_number(value: Variant) -> bool:
	return value is int or value is float


func _is_finite_number(value: Variant) -> bool:
	if not _is_number(value):
		return false
	return is_finite(float(value))


func _warn_once(kind: String, message: String) -> void:
	match kind:
		"missing":
			if _warned_missing:
				return
			_warned_missing = true
		"stale":
			if _warned_stale:
				return
			_warned_stale = true
		"schema":
			if _warned_schema:
				return
			_warned_schema = true
		_:
			if _warned_invalid:
				return
			_warned_invalid = true

	push_warning(message)
