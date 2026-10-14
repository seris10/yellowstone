Below is a drop-in replacement for `weather_snapshot_reader.gd`. It adds:

- Required-field validation.
- Numeric, finite, and range checks.
- Optional solar-pair validation.
- Live-clock, simulation-clock, and disabled freshness modes.
- Content-based change detection instead of modification time alone.
- Safe retention of the last valid weather state.
- Future timestamp rejection.
- Warning throttling.
- Optional simulation timestamp binding.

```gdscript
class_name YellowstoneWeatherSnapshotReader
extends Node

## Reads a normalized weather snapshot from JSON and passes valid state to
## YellowstoneAtmosphereController.
##
## This node never fetches weather from the network.
##
## Supported freshness modes:
## - "wall_clock": compare generated_at_unix with the computer clock.
## - "simulation_clock": compare generated_at_unix with a supplied simulation time.
## - "disabled": accept snapshots without age validation.
##
## The producer should write a complete temporary file and atomically replace
## the target snapshot. The reader retains the last valid state if a file is
## missing, malformed, stale, or invalid.

const SUPPORTED_SCHEMA_VERSION: int = 1

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

@export var snapshot_path: String = "user://weather/latest.json"

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

# Content signature. A file modification time alone can miss rapid atomic
# replacements on filesystems with coarse timestamp resolution.
var _last_signature: int = -1

var _warned_missing: bool = false
var _warned_stale: bool = false
var _warned_invalid: bool = false
var _warned_schema: bool = false


## Bind this reader to the atmosphere controller.
func bind(controller: YellowstoneAtmosphereController) -> void:
	_controller = controller
	poll_now()


## Supply the current simulation time when freshness_mode is
## "simulation_clock".
func set_simulation_epoch_unix(epoch_unix: float) -> void:
	if not _is_finite_number(epoch_unix):
		push_warning(
			"Weather reader received a non-finite simulation timestamp."
		)
		return

	_simulation_epoch_unix = float(epoch_unix)
	_has_simulation_epoch = true


## Clear the simulation timestamp. The reader will reject simulation-clock
## freshness checks until another timestamp is supplied.
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

	if not FileAccess.file_exists(snapshot_path):
		if warn_on_missing_snapshot and not _warned_missing:
			push_warning(
				"Weather snapshot not found at '%s'; "
				+ "retaining the current atmosphere state."
				% snapshot_path
			)
			_warned_missing = true
		return false

	var bytes := _read_file_bytes(snapshot_path)
	if bytes.is_empty():
		_warn_once(
			"invalid",
			"Could not read weather snapshot '%s'; "
			+ "retaining the last valid state." % snapshot_path
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

	if int(schema_value) != SUPPORTED_SCHEMA_VERSION:
		_warn_once(
			"schema",
			"Unsupported weather snapshot schema_version %s; expected %d."
			% [str(schema_value), SUPPORTED_SCHEMA_VERSION]
		)
		return false

	var generated_value: Variant = root.get("generated_at_unix", null)
	if not _is_finite_number(generated_value):
		_warn_once(
			"invalid",
			"Weather snapshot requires finite generated_at_unix."
		)
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

	var generated_at := float(root["generated_at_unix"])
	var reference_time := Time.get_unix_time_from_system()

	if freshness_mode == FRESHNESS_SIMULATION_CLOCK:
		reference_time = _simulation_epoch_unix

	var age_seconds := reference_time - generated_at

	if age_seconds < -allowed_future_seconds:
		_warn_once(
			"stale",
			"Weather snapshot is from the future by %.0f seconds; "
			+ "retaining the last valid state." % abs(age_seconds)
		)
		return false

	if age_seconds > max_snapshot_age_seconds:
		_warn_once(
			"stale",
			"Weather snapshot is %.0f seconds old; "
			+ "retaining the last valid state." % age_seconds
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
		var elevation_range := Vector2(-18.0, 90.0)
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
```

## Required integration change

The current integration should pass the simulation timestamp when running in replay mode:

```gdscript
weather_snapshot_reader.set_simulation_epoch_unix(
	simulation_epoch_unix
)
```

For example:

```gdscript
func _process(delta: float) -> void:
	simulation_epoch_unix += delta * simulation_rate

	weather_snapshot_reader.set_simulation_epoch_unix(
		simulation_epoch_unix
	)
```

Set the reader to simulation-clock mode:

```gdscript
weather_snapshot_reader.freshness_mode = "simulation_clock"
```

For live gameplay, retain:

```gdscript
weather_snapshot_reader.freshness_mode = "wall_clock"
```

For a fully deterministic replay where snapshot age should not reject a known input:

```gdscript
weather_snapshot_reader.freshness_mode = "disabled"
```

One important semantic distinction remains: `generated_at_unix` should describe when the normalized snapshot was produced, while a replay should ideally also contain a separate `valid_time_unix` or `observation_time_unix`. That prevents a weather record generated today for historical conditions from being incorrectly rejected based on its generation time.

---

../../weather_snapshot_reader.gd