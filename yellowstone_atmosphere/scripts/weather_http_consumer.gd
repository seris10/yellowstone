class_name YellowstoneWeatherHttpConsumer
extends Node

## Fetches live weather from the Python llm_backend /api/weather endpoint
## and feeds it directly to a YellowstoneAtmosphereController. Optionally
## writes the fetched state to user://weather/latest.json so the existing
## WeatherSnapshotReader can also consume it.
##
## Usage:
##   var consumer = YellowstoneWeatherHttpConsumer.new()
##   consumer.name = "WeatherHttpConsumer"
##   add_child(consumer)
##   consumer.bind(controller, "http://127.0.0.1:8001")
##
## The endpoint returns {"source":"...","air_c":...,"humidity":...,
## "cloud":...,"wind_xz_mps":[vx,vz],"gust_mps":...,"bundle":...}.
## Solar angles are not returned by the endpoint; the controller keeps its
## simulation-clock solar model unless a snapshot file overrides it.

const DEFAULT_PORT: int = 8001

@export var endpoint_url: String = ""
@export var poll_interval_seconds: float = 30.0
@export var write_snapshot_file: bool = true
@export var snapshot_path: String = "user://weather/latest.json"

var _controller: YellowstoneAtmosphereController
var _http: HTTPRequest
var _elapsed: float = 0.0
var _base_url: String = ""

func bind(controller: YellowstoneAtmosphereController, base_url: String = "") -> void:
	_controller = controller
	_base_url = base_url if base_url != "" else ("http://127.0.0.1:%d" % DEFAULT_PORT)
	if endpoint_url == "":
		endpoint_url = "%s/api/weather" % _base_url
	# Ensure the HTTPRequest node exists
	if _http == null:
		_http = HTTPRequest.new()
		_http.name = "WeatherHTTPRequest"
		_http.timeout = 5.0
		_http.use_threads = true
		_http.connect("request_completed", Callable(self, "_on_request_completed"))
		add_child(_http)
	poll_now()

func _process(delta: float) -> void:
	_elapsed += delta
	if _elapsed < poll_interval_seconds:
		return
	_elapsed = 0.0
	poll_now()

func poll_now() -> void:
	if _controller == null or _http == null:
		return
	var url: String = endpoint_url
	if url.contains("?"):
		url += "&live_refetch=1"
	else:
		url += "?live_refetch=1"
	_http.request(url, ["Content-Type: application/json"])

func _on_request_completed(result: int, response_code: int, headers: PackedStringArray, body: PackedByteArray) -> void:
	if result != HTTPRequest.RESULT_SUCCESS:
		push_warning("Weather HTTP consumer: request failed (result=%d)." % result)
		return
	if response_code != 200:
		push_warning("Weather HTTP consumer: HTTP %d" % response_code)
		return
	var text: String = body.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null or not parsed is Dictionary:
		push_warning("Weather HTTP consumer: response is not a JSON object.")
		return
	var root: Dictionary = parsed as Dictionary
	_apply_response(root)
	if write_snapshot_file:
		_write_snapshot_file(root)

func _apply_response(root: Dictionary) -> void:
	if _controller == null:
		return
	# Map endpoint fields to controller weather state
	var state: Dictionary = {}

	# Temperature
	if root.has("air_c"):
		state["air_temperature_c"] = float(root["air_c"])

	# Humidity -> relative humidity
	if root.has("humidity"):
		state["relative_humidity"] = clampf(float(root["humidity"]), 0.0, 1.0)

	# Cloud fraction
	if root.has("cloud"):
		state["cloud_fraction"] = clampf(float(root["cloud"]), 0.0, 1.0)

	# Wind vector -> speed + direction FROM
	if root.has("wind_xz_mps"):
		var wind_variant: Variant = root["wind_xz_mps"]
		if wind_variant is Array and wind_variant.size() >= 2:
			var vx: float = float(wind_variant[0])
			var vz: float = float(wind_variant[1])
			var speed: float = sqrt(vx * vx + vz * vz)
			# Controller uses meteorological FROM direction. The endpoint's
			# vector is the flow direction; FROM is 180° opposite.
			var from_dir: float = fposmod(rad_to_deg(atan2(-vx, -vz)), 360.0)
			state["wind_speed_mps"] = speed
			state["wind_direction_deg"] = from_dir

	# Gust can be folded into wind speed or kept separate if the controller
	# ever supports gust. Currently just include it in provenance.
	if root.has("gust_mps"):
		# Not consumed by the controller directly; leave it out of state but
		# keep it visible in the snapshot file provenance if needed.
		pass

	# Visibility / fog: endpoint does not return visibility directly,
	# but we can derive a rough visibility from cloud + humidity if needed.
	# For now, leave visibility at controller default.

	# Snow fraction (wet-bulb based from endpoint)
	if root.has("snow_fraction"):
		state["snow_fraction"] = clampf(float(root["snow_fraction"]), 0.0, 1.0)

	# Precipitation rate (live hydrology link)
	if root.has("precipitation_rate_mm_h"):
		state["precipitation_rate_mm_h"] = clampf(float(root["precipitation_rate_mm_h"]), 0.0, 250.0)

	# Ground wetness (live soil saturation from hydrology)
	if root.has("ground_wetness_fraction"):
		state["ground_wetness_fraction"] = clampf(float(root["ground_wetness_fraction"]), -1.0, 1.0)

	# Solar: endpoint bundle does not return solar angles. The controller
	# keeps its simulation-clock solar model.

	if state.size() > 0:
		_controller.set_weather_state(state)

func _write_snapshot_file(root: Dictionary) -> void:
	# Convert endpoint response to the snapshot format the existing reader
	# expects (schema_version 1, generated_at_unix, weather, solar optional).
	var snapshot: Dictionary = {
		"schema_version": 1,
		"generated_at_unix": Time.get_unix_time_from_system(),
		"source": root.get("source", {"analysis": "open-meteo_hourly_bundle"}),
		"weather": {},
	}
	var weather: Dictionary = snapshot["weather"]
	if root.has("air_c"):
		weather["air_temperature_c"] = float(root["air_c"])
	if root.has("humidity"):
		weather["relative_humidity"] = clampf(float(root["humidity"]), 0.0, 1.0)
	if root.has("cloud"):
		weather["cloud_fraction"] = clampf(float(root["cloud"]), 0.0, 1.0)
	if root.has("wind_xz_mps"):
		var wind_variant: Variant = root["wind_xz_mps"]
		if wind_variant is Array and wind_variant.size() >= 2:
			var vx: float = float(wind_variant[0])
			var vz: float = float(wind_variant[1])
			var speed: float = sqrt(vx * vx + vz * vz)
			var from_dir: float = fposmod(rad_to_deg(atan2(-vx, -vz)), 360.0)
			weather["wind_speed_mps"] = speed
			weather["wind_direction_deg"] = from_dir
	# Hydrology-derived values from endpoint (validated patterns)
	weather["precipitation_rate_mm_h"] = float(root.get("precipitation_rate_mm_h", 0.0))
	weather["snow_fraction"] = float(root.get("snow_fraction", 0.0))
	weather["ground_wetness_fraction"] = float(root.get("ground_wetness_fraction", -1.0))

	# Visibility derives from cloud, humidity, and precipitation (weather-simulation.md).
	# Clear conditions (low cloud, low humidity, no rain) -> ~24000 m visibility.
	# Dense cloud + high humidity + rain -> significantly reduced visibility.
	var cloud_frac: float = float(root.get("cloud", 0.0))
	var humidity: float = float(root.get("humidity", 0.45))
	var precip: float = float(root.get("precipitation_rate_mm_h", 0.0))
	# Rough physically-aligned visibility model: base 24000m scaled by haze/cloud/rain
	var visibility: float = 24000.0 * max(0.05, (1.0 - cloud_frac * 0.7) * (1.0 - humidity * 0.3) * (1.0 - min(precip / 20.0, 0.9)))
	weather["visibility_m"] = visibility
	weather["cloud_base_agl_m"] = 1050.0
	weather["cloud_thickness_m"] = 600.0

	# Solar is not provided by the endpoint; leave it out (controller uses clock).

	# Ensure the directory exists
	var dir_path: String = "user://weather"
	if not DirAccess.dir_exists_absolute(dir_path):
		DirAccess.make_dir_absolute(dir_path)

	var file: FileAccess = FileAccess.open(snapshot_path, FileAccess.WRITE)
	if file != null:
		file.store_string(JSON.stringify(snapshot, "\t"))
		file.close()
