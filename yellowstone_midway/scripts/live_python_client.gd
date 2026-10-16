class_name YellowstoneLivePythonClient
extends Node

signal mode_selected(live: bool)
signal schema_received(schema: Dictionary)
signal frames_received(payload: Dictionary)
signal control_received(payload: Dictionary)
signal response_received(kind: String, payload: Dictionary)
signal failed(message: String)
var live: bool = false
var schema: Dictionary = {}
var after_t_s: float = -1.0
var player_t_s: float = 0.0
var time_scale: float = 1.0
var revision: int = -1
var computing: bool = false
var expected_build_id: String = ""
var expected_model_variant_id: String = ""
var _http: HTTPRequest
var _kind: String = ""
var _pending: Array[Dictionary] = []
var _elapsed: float = 0.0
var _url: String

func _ready() -> void:
	_url = str(ProjectSettings.get_setting("yellowstone/live_url", "http://127.0.0.1:8765")).trim_suffix("/")
	_http = HTTPRequest.new()
	_http.use_threads = true
	_http.timeout = 1.0
	_http.body_size_limit = 32 * 1024 * 1024
	add_child(_http)
	_http.request_completed.connect(_completed)
	_request("schema", "/api/live/schema")

func _request(kind: String, path: String, body: Dictionary = {}) -> void:
	if not _kind.is_empty():
		_pending.append({"kind": kind, "path": path, "body": body})
		return
	_kind = kind
	_http.timeout = 1.0 if kind == "schema" else 10.0
	var headers: PackedStringArray = PackedStringArray(["Content-Type: application/json"])
	var token: String = OS.get_environment("YS_LIVE_TOKEN")
	if not token.is_empty():
		headers.append("X-Yellowstone-Token: " + token)
	var error: int = _http.request(_url + path, headers,HTTPClient.METHOD_GET if body.is_empty() else HTTPClient.METHOD_POST, "" if body.is_empty() else JSON.stringify(body))
	if error != OK:
		_kind = ""
		failed.emit("Python request failed: %s" % error_string(error))
		if kind == "schema":
			mode_selected.emit(false)

func _completed(result: int, code: int, _headers: PackedStringArray, bytes: PackedByteArray) -> void:
	var kind: String = _kind
	_kind = ""
	var parsed: Variant = JSON.parse_string(bytes.get_string_from_utf8()) if not bytes.is_empty() and code in [200, 400] else null
	if result != HTTPRequest.RESULT_SUCCESS or code != 200 or not parsed is Dictionary:
		if kind == "schema":
			live = false
			mode_selected.emit(false)
		else:
			computing = false
			failed.emit("Python %s failed (HTTP %d, transport %d): %s" % [kind, code, result, parsed.get("error", "") if parsed is Dictionary else ""])
	else:
		var payload: Dictionary = parsed
		if kind == "schema":
			schema = payload
			live = payload.get("controls") is Array
			var identity: Dictionary = payload.get("header", {})
			if not expected_build_id.is_empty() and (str(identity.get("build_id", "")) != expected_build_id or str(identity.get("model_variant_id", "")) != expected_model_variant_id or identity.get("start_operation") != "resume_published"):
				live = false
				failed.emit("Python service has a different scenario or model variant; baked release retained.")
			schema_received.emit(schema)
			mode_selected.emit(live)
		elif kind == "frames":
			if bool(payload.get("reset_required", false)):
				after_t_s = float(payload.get("retained_after_t_s", player_t_s)) - 0.000001
			var received_revision: int = int(payload.get("revision", revision))
			if revision >= 0 and received_revision != revision and payload.has("truncate_after_t_s"):
				after_t_s = float(payload.truncate_after_t_s)
			revision = received_revision
			var frames: Array = payload.get("frames", [])
			if not frames.is_empty():
				after_t_s = float(frames[-1].t_s)
			var header: Dictionary = payload.get("header", {})
			computing = bool(header.get("clock_held", false)) or bool(header.get("computing", false)) or float(payload.get("buffer_headroom_s", 1.0)) <= 0.0
			frames_received.emit(payload)
		elif kind in ["control", "preset", "measured", "intervention", "reset", "advance_time"]:
			revision = int(payload.get("revision", revision))
			after_t_s = float(payload.get("truncate_after_t_s", player_t_s)) - 0.000001
			control_received.emit(payload)
		response_received.emit(kind, payload)
	if not _pending.is_empty():
		var queued: Dictionary = _pending.pop_front()
		_request(queued.kind, queued.path, queued.body)

func _process(delta: float) -> void:
	_elapsed += delta
	if not live:
		if _elapsed >= 5.0 and _kind.is_empty():
			_elapsed = 0.0
			_request("schema", "/api/live/schema")
		return
	if _elapsed >= 0.25 and _kind.is_empty() and _pending.is_empty():
		_elapsed = fmod(_elapsed, 0.25)
		_request("frames", "/api/live/frames?after_t_s=%.6f&player_t_s=%.6f&time_scale=%.0f" % [after_t_s, player_t_s, time_scale])

func control(changes: Dictionary, location_xyz_m: Array = []) -> void:
	if live:
		computing = true
		_request("control", "/api/live/control", {"at_s": player_t_s, "changes": changes, "location_xyz_m": location_xyz_m})

func command(kind: String, payload: Dictionary) -> void:
	if live:
		var body: Dictionary = payload.duplicate(true)
		body["at_s"] = player_t_s
		if kind in ["preset", "measured", "intervention"]:
			computing = true
		_request(kind, "/api/live/" + kind, body)

func _exit_tree() -> void:
	_pending.clear()
	if is_instance_valid(_http):
		_http.cancel_request()
