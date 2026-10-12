class_name YellowstoneWeatherSnapshotReader
extends Node

## Reads an externally produced JSON weather snapshot and passes it to the
## atmosphere renderer. It intentionally does not fetch data from the internet.
## Recommended producer: Python service that ingests HRRR/RTMA/stations, applies
## local corrections, computes solar geometry and atomically replaces the file.

@export var snapshot_path: String = "user://weather/latest.json"
@export_range(1.0, 600.0, 1.0) var poll_interval_seconds: float = 15.0
@export_range(60.0, 172800.0, 60.0) var max_snapshot_age_seconds: float = 7200.0
@export var warn_on_missing_snapshot: bool = true

var _controller: YellowstoneAtmosphereController
var _elapsed: float = 0.0
var _last_signature: int = -1
var _warned_missing: bool = false
var _warned_stale: bool = false


func bind(controller: YellowstoneAtmosphereController) -> void:
	_controller = controller
	poll_now()


func _process(delta: float) -> void:
	_elapsed += delta
	if _elapsed < poll_interval_seconds:
		return
	_elapsed = 0.0
	poll_now()


func poll_now() -> bool:
	if _controller == null:
		return false
	if not FileAccess.file_exists(snapshot_path):
		if warn_on_missing_snapshot and not _warned_missing:
			push_warning("Weather snapshot not found at '%s'; atmosphere keeps its current fallback state." % snapshot_path)
			_warned_missing = true
		return false

	var modified: int = FileAccess.get_modified_time(snapshot_path)
	if modified == _last_signature:
		return false
	var file: FileAccess = FileAccess.open(snapshot_path, FileAccess.READ)
	if file == null:
		push_warning("Could not open weather snapshot '%s'." % snapshot_path)
		return false
	var parsed: Variant = JSON.parse_string(file.get_as_text())
	file.close()
	if not parsed is Dictionary:
		push_warning("Weather snapshot is not a JSON object; retaining the last valid state.")
		return false
	var root: Dictionary = parsed as Dictionary
	if int(root.get("schema_version", 0)) != 1:
		push_warning("Unsupported weather snapshot schema_version. Expected 1.")
		return false
	if not root.has("generated_at_unix"):
		push_warning("Weather snapshot requires generated_at_unix as a Unix timestamp.")
		return false

	var age_seconds: float = Time.get_unix_time_from_system() - float(root["generated_at_unix"])
	if age_seconds < -300.0 or age_seconds > max_snapshot_age_seconds:
		if not _warned_stale:
			push_warning("Weather snapshot is outside the accepted age window (age %.0f seconds); retaining the last valid state." % age_seconds)
			_warned_stale = true
		return false

	var weather_variant: Variant = root.get("weather", {})
	if not weather_variant is Dictionary:
		push_warning("Weather snapshot 'weather' field must be a JSON object.")
		return false
	var state: Dictionary = (weather_variant as Dictionary).duplicate(true)
	var solar_variant: Variant = root.get("solar", {})
	if solar_variant is Dictionary:
		state.merge(solar_variant as Dictionary, true)
	_controller.set_weather_state(state)
	_last_signature = modified
	_warned_missing = false
	_warned_stale = false
	return true
