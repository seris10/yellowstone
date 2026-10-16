class_name YellowstoneWeatherHttpConsumer
extends Node

## Fetches weather from a Python HTTP endpoint and forwards normalized state to YellowstoneAtmosphereController.

## The consumer accepts the normalized nested snapshot or the flat endpoint shape and writes the normalized format to snapshot_path.

const DEFAULT_PORT: int = 8765
const SCHEMA_VERSION: int = 2

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

const DEFAULT_WEATHER: Dictionary = {
	"air_temperature_c": 8.0,
	"dewpoint_c": 1.0,
	"relative_humidity": 0.55,
	"wind_speed_mps": 2.0,
	"wind_direction_deg": 270.0,
	"cloud_fraction": 0.28,
	"cloud_base_agl_m": 1050.0,
	"cloud_thickness_m": 600.0,
	"precipitation_rate_mm_h": 0.0,
	"snow_fraction": 0.0,
	"visibility_m": 24000.0,
	"ground_wetness_fraction": -1.0,
}

@export_group("HTTP")

@export var endpoint_url: String = ""

@export var poll_interval_seconds: float = 30.0

@export_range(1.0, 60.0, 1.0)
var request_timeout_seconds: float = 5.0

@export_group("Snapshot output")

@export var write_snapshot_file: bool = true

@export var snapshot_path: String = "user://weather/latest.json"

@export_group("Fallbacks")

## Default used when the endpoint omits the corresponding optional field.
@export var default_visibility_m: float = 24000.0
@export var default_cloud_base_agl_m: float = 1050.0
@export var default_cloud_thickness_m: float = 600.0


var _controller: YellowstoneAtmosphereController
var _http: HTTPRequest

var _base_url: String = ""
var _elapsed: float = 0.0
var _request_in_flight: bool = false


func bind(
	controller: YellowstoneAtmosphereController,
	base_url: String = ""
) -> void:
	_controller = controller

	_base_url = (
		base_url
		if base_url.strip_edges() != ""
		else str(ProjectSettings.get_setting("yellowstone/live_url", "http://127.0.0.1:%d" % DEFAULT_PORT))
	)

	if endpoint_url.strip_edges() == "":
		endpoint_url = "%s/api/weather" % _base_url

	_ensure_http_request()
	poll_now()


func _process(delta: float) -> void:
	if _controller == null:
		return

	_elapsed += delta

	if _elapsed < maxf(poll_interval_seconds, 1.0):
		return

	_elapsed = 0.0
	poll_now()


func _ensure_http_request() -> void:
	if _http != null:
		return

	_http = HTTPRequest.new()
	_http.name = "WeatherHTTPRequest"
	_http.timeout = maxf(request_timeout_seconds, 1.0)
	_http.use_threads = true

	_http.request_completed.connect(_on_request_completed)

	add_child(_http)


func poll_now() -> void:
	if _controller == null:
		return

	_ensure_http_request()

	if _request_in_flight:
		return

	var url := endpoint_url.strip_edges()

	if url == "":
		push_warning("Weather HTTP consumer has no endpoint URL.")
		return

	if url.contains("?"):
		url += "&live_refetch=1"
	else:
		url += "?live_refetch=1"

	_request_in_flight = true

	var error := _http.request(
		url,
		[
			"Accept: application/json",
			"Cache-Control: no-cache",
		]
	)

	if error != OK:
		_request_in_flight = false
		push_warning(
			"Weather HTTP request could not start: %s"
			% error_string(error)
		)


func _on_request_completed(
	result: int,
	response_code: int,
	headers: PackedStringArray,
	body: PackedByteArray
) -> void:
	_request_in_flight = false

	if result != HTTPRequest.RESULT_SUCCESS:
		push_warning(
			"Weather HTTP request failed: result=%d"
			% result
		)
		return

	if response_code < 200 or response_code >= 300:
		push_warning(
			"Weather HTTP endpoint returned HTTP %d."
			% response_code
		)
		return

	var text := body.get_string_from_utf8()

	if text.strip_edges() == "":
		push_warning("Weather HTTP endpoint returned an empty response.")
		return

	var parsed: Variant = JSON.parse_string(text)

	if parsed == null or not (parsed is Dictionary):
		push_warning(
			"Weather HTTP endpoint did not return a JSON object."
		)
		return

	var root: Dictionary = parsed as Dictionary
	var snapshot := _normalize_response(root)

	if snapshot.is_empty():
		push_warning(
			"Weather HTTP response could not be normalized; "
			+ "retaining the last valid weather state."
		)
		return

	var weather: Dictionary = snapshot["weather"]
	var solar: Dictionary = snapshot.get("solar", {})
	var terrain: Dictionary = snapshot.get("terrain", {})

	# Controller consumes the flat weather state; the persisted file uses the normalized nested snapshot schema.
	var controller_state := weather.duplicate(true)

	if not solar.is_empty():
		controller_state.merge(solar, true)

	if not terrain.is_empty():
		controller_state["terrain"] = terrain

	if _controller != null:
		_controller.set_weather_state(controller_state)

	if write_snapshot_file:
		if not _write_snapshot_atomically(snapshot):
			push_warning(
				"Weather state was applied to the controller, "
				+ "but the snapshot file could not be written."
			)


func _normalize_response(root: Dictionary) -> Dictionary:
	var weather := _extract_weather(root)

	if weather.is_empty():
		return {}

	var normalized_weather := _normalize_weather(weather)

	if not _has_required_weather_fields(normalized_weather):
		push_warning(
			"Normalized HTTP weather response is missing required fields."
		)
		return {}

	var server_generated: bool = root.has("generated_at_unix")
	var source_block: Dictionary = _source_metadata(root)
	# Record provenance when the server omits a timestamp so downstream readers can distinguish observed data from a client-timed snapshot.
	source_block["client_generated"] = not server_generated
	var generated_at_unix: float = _generated_timestamp(root)
	var snapshot: Dictionary = {
		"schema_version": SCHEMA_VERSION,
		"generated_at_unix": generated_at_unix,
		"valid_time_unix": float(root.get("valid_time_unix", generated_at_unix)),
		"simulation_time_unix": float(root.get("simulation_time_unix", generated_at_unix)),
		"source": source_block,
		"weather": normalized_weather,
	}

	var solar := _extract_solar(root)

	if not solar.is_empty():
		if not _validate_solar_pair(solar):
			push_warning(
				"HTTP response supplied an incomplete or invalid solar override; "
				+ "solar data will be omitted."
			)
		else:
			snapshot["solar"] = solar

	var terrain_variant: Variant = root.get("terrain", null)
	if terrain_variant is Dictionary:
		snapshot["terrain"] = (terrain_variant as Dictionary).duplicate(true)

	return snapshot


func _extract_weather(root: Dictionary) -> Dictionary:
	# Prefer the normalized nested format.
	var nested: Variant = root.get("weather", null)

	if nested is Dictionary:
		return (nested as Dictionary).duplicate(true)

	# Fall back to the older flat endpoint format.
	var weather: Dictionary = {}

	_copy_if_present(root, weather, "air_c", "air_temperature_c")
	_copy_if_present(root, weather, "dewpoint_c", "dewpoint_c")
	_copy_if_present(root, weather, "humidity", "relative_humidity")
	_copy_if_present(root, weather, "cloud", "cloud_fraction")
	_copy_if_present(root, weather, "snow_fraction", "snow_fraction")
	_copy_if_present(
		root,
		weather,
		"precipitation_rate_mm_h",
		"precipitation_rate_mm_h"
	)
	_copy_if_present(
		root,
		weather,
		"ground_wetness_fraction",
		"ground_wetness_fraction"
	)
	_copy_if_present(root, weather, "visibility_m", "visibility_m")
	_copy_if_present(root, weather, "cloud_base_agl_m", "cloud_base_agl_m")
	_copy_if_present(
		root,
		weather,
		"cloud_thickness_m",
		"cloud_thickness_m"
	)

	# A normalized flat endpoint may already provide these names.
	_copy_if_present(
		root,
		weather,
		"air_temperature_c",
		"air_temperature_c"
	)
	_copy_if_present(
		root,
		weather,
		"relative_humidity",
		"relative_humidity"
	)
	_copy_if_present(
		root,
		weather,
		"wind_speed_mps",
		"wind_speed_mps"
	)
	_copy_if_present(
		root,
		weather,
		"wind_direction_deg",
		"wind_direction_deg"
	)
	_copy_if_present(root, weather, "cloud_fraction", "cloud_fraction")

	var wind_vector: Variant = root.get("wind_xz_mps", null)

	if wind_vector is Array and (wind_vector as Array).size() >= 2:
		var wind_result := _wind_vector_to_weather(wind_vector as Array)

		if not wind_result.is_empty():
			weather.merge(wind_result, true)

	return weather


func _normalize_weather(input: Dictionary) -> Dictionary:
	var weather := DEFAULT_WEATHER.duplicate(true)

	for key in input.keys():
		if weather.has(key):
			weather[key] = input[key]

	# Scalar wind speed with no direction keeps the documented default; a wind vector is converted by _extract_weather().

	if not input.has("visibility_m"):
		weather["visibility_m"] = default_visibility_m

	if not input.has("cloud_base_agl_m"):
		weather["cloud_base_agl_m"] = default_cloud_base_agl_m

	if not input.has("cloud_thickness_m"):
		weather["cloud_thickness_m"] = default_cloud_thickness_m

	# Normalize and validate scalar values before writing or applying them.
	weather["air_temperature_c"] = float(weather["air_temperature_c"])
	weather["relative_humidity"] = clampf(
		float(weather["relative_humidity"]),
		0.0,
		1.0
	)
	weather["wind_speed_mps"] = maxf(
		float(weather["wind_speed_mps"]),
		0.0
	)
	weather["wind_direction_deg"] = fposmod(
		float(weather["wind_direction_deg"]),
		360.0
	)
	weather["cloud_fraction"] = clampf(
		float(weather["cloud_fraction"]),
		0.0,
		1.0
	)
	weather["precipitation_rate_mm_h"] = maxf(
		float(weather["precipitation_rate_mm_h"]),
		0.0
	)
	weather["snow_fraction"] = clampf(
		float(weather["snow_fraction"]),
		0.0,
		1.0
	)
	weather["visibility_m"] = maxf(
		float(weather["visibility_m"]),
		100.0
	)
	weather["cloud_base_agl_m"] = maxf(
		float(weather["cloud_base_agl_m"]),
		100.0
	)
	weather["cloud_thickness_m"] = maxf(
		float(weather["cloud_thickness_m"]),
		100.0
	)

	if weather.has("dewpoint_c"):
		weather["dewpoint_c"] = float(weather["dewpoint_c"])

	if weather.has("ground_wetness_fraction"):
		weather["ground_wetness_fraction"] = clampf(
			float(weather["ground_wetness_fraction"]),
			-1.0,
			1.0
		)

	return weather


func _extract_solar(root: Dictionary) -> Dictionary:
	var solar_variant: Variant = root.get("solar", null)

	if solar_variant is Dictionary:
		return (solar_variant as Dictionary).duplicate(true)

	# Support a flat endpoint if one is introduced later.
	var solar := {}

	if root.has("solar_azimuth_deg"):
		solar["solar_azimuth_deg"] = root["solar_azimuth_deg"]

	if root.has("solar_elevation_deg"):
		solar["solar_elevation_deg"] = root["solar_elevation_deg"]

	return solar


func _wind_vector_to_weather(wind: Array) -> Dictionary:
	if wind.size() < 2:
		return {}

	if not _is_finite_number(wind[0]) \
	or not _is_finite_number(wind[1]):
		return {}

	var vx := float(wind[0])
	var vz := float(wind[1])
	var speed := sqrt(vx * vx + vz * vz)

	if speed <= 0.000001:
		return {
			"wind_speed_mps": 0.0,
			"wind_direction_deg": 0.0,
		}

	# World axes: +X east, +Z south. The vector points toward the destination; meteorological direction is reported as the compass bearing from which the wind originates, clockwise from north.
	var direction_from := fposmod(
		rad_to_deg(atan2(-vx, -vz)),
		360.0
	)

	return {
		"wind_speed_mps": speed,
		"wind_direction_deg": direction_from,
	}


func _has_required_weather_fields(weather: Dictionary) -> bool:
	for field_name in REQUIRED_WEATHER_FIELDS:
		if not weather.has(field_name):
			return false

		if not _is_finite_number(weather[field_name]):
			return false

	return true


func _validate_solar_pair(solar: Dictionary) -> bool:
	if not solar.has("solar_azimuth_deg") \
	or not solar.has("solar_elevation_deg"):
		return false

	var azimuth: Variant = solar["solar_azimuth_deg"]
	var elevation: Variant = solar["solar_elevation_deg"]

	if not _is_finite_number(azimuth) \
	or not _is_finite_number(elevation):
		return false

	var azimuth_value := float(azimuth)
	var elevation_value := float(elevation)

	return (
		azimuth_value >= 0.0
		and azimuth_value < 360.0
		and elevation_value >= -90.0
		and elevation_value <= 90.0
	)


func _generated_timestamp(root: Dictionary) -> float:
	var candidate: Variant = root.get(
		"generated_at_unix",
		Time.get_unix_time_from_system()
	)

	if _is_finite_number(candidate) and float(candidate) >= 0.0:
		return float(candidate)

	return Time.get_unix_time_from_system()


func _source_metadata(root: Dictionary) -> Dictionary:
	var source: Variant = root.get("source", {})

	if source is Dictionary:
		return (source as Dictionary).duplicate(true)

	return {
		"source": str(source)
	}


func _copy_if_present(
	source: Dictionary,
	destination: Dictionary,
	source_key: String,
	destination_key: String
) -> void:
	if source.has(source_key):
		destination[destination_key] = source[source_key]


func _is_finite_number(value: Variant) -> bool:
	if not (value is int or value is float):
		return false

	return is_finite(float(value))


func _write_snapshot_atomically(snapshot: Dictionary) -> bool:
	var directory := snapshot_path.get_base_dir()

	if not DirAccess.dir_exists_absolute(directory):
		var make_error := DirAccess.make_dir_recursive_absolute(directory)

		if make_error != OK:
			push_warning(
				"Could not create weather snapshot directory '%s'."
				% directory
			)
			return false

	var temporary_path := snapshot_path + ".tmp"

	var file := FileAccess.open(temporary_path, FileAccess.WRITE)

	if file == null:
		push_warning(
			"Could not open temporary weather snapshot '%s'."
			% temporary_path
		)
		return false

	file.store_string(JSON.stringify(snapshot, "\t"))
	file.flush()
	file.close()

	var rename_error := DirAccess.rename_absolute(
		temporary_path,
		snapshot_path
	)

	if rename_error != OK:
		push_warning(
			"Could not atomically install weather snapshot: %s"
			% error_string(rename_error)
		)
		return false

	return true