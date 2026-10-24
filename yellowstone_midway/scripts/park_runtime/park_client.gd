extends Node
## Optional timestamped service transport. A missing server never freezes the render loop.
signal snapshot_received(packet: Dictionary)
signal command_queued(command_id: String)
signal connection_problem(message: String)

@export var base_url: String = "http://127.0.0.1:8766"
@export var poll_interval_s: float = 0.25
@export var focus_interval_s: float = 1.0
var packet: Dictionary = {}
var residency: Dictionary = {}
var focus_sequence: int = 0
var session_id: String = ""
var revision: int = -1
var stale: bool = true
var _http: HTTPRequest
var _busy: bool = false
var _kind: String = ""
var _elapsed: float = 0.0
var _since_receive: float = 0.0
var _interest: Dictionary = {}
var _commands: Array[Dictionary] = []
var _interest_sequence: int = 0
var _focus: Dictionary = {}
var _since_focus: float = INF

func _ready() -> void:
    _http = HTTPRequest.new()
    _http.use_threads = true
    _http.timeout = 2.0
    _http.body_size_limit = 16*1024*1024
    add_child(_http)
    _http.request_completed.connect(_completed)

func set_interest(region_ids: Array[String]) -> void:
    _interest_sequence += 1
    _interest = {"sequence":_interest_sequence,"region_ids":region_ids}

## Position is absolute local-frame meters as float64 scalars; the latest call is sent each focus interval.
func set_focus(x_m: float,y_m: float,z_m: float,velocity_mps: Vector3,view_dir: Vector3,fov_deg: float) -> void:
    _focus = {"position_m":[x_m,y_m,z_m],"velocity_mps":[velocity_mps.x,velocity_mps.y,velocity_mps.z],
        "view_dir":[view_dir.x,view_dir.y,view_dir.z],"fov_deg":fov_deg}

func queue_command(kind: String,payload: Dictionary) -> bool:
    if not kind in ["clock","intervene"] or _commands.size()>=16:
        return false
    _commands.append({"kind":kind,"payload":payload.duplicate(true)})
    return true

func _process(delta: float) -> void:
    _elapsed += delta
    _since_receive += delta
    _since_focus += delta
    stale = _since_receive>maxf(2.0,poll_interval_s*4.0)
    if _busy or _elapsed<poll_interval_s:
        return
    _elapsed = 0.0
    if not _commands.is_empty():
        var command: Dictionary = _commands.pop_front()
        _request(command.kind,command.payload)
    elif not _interest.is_empty():
        _request("interest",_interest)
        _interest = {}
    elif not _focus.is_empty() and _since_focus>=focus_interval_s:
        focus_sequence += 1
        _focus.sequence = focus_sequence
        _request("focus",_focus)
        _focus = {}
        _since_focus = 0.0
    else:
        _request("state",{})

func _request(kind: String,payload: Dictionary) -> void:
    _kind = kind
    _busy = true
    var get_state: bool = kind=="state"
    var error: Error = _http.request(base_url+"/api/park/"+kind,
        PackedStringArray(["Content-Type: application/json"]),
        HTTPClient.METHOD_GET if get_state else HTTPClient.METHOD_POST,
        "" if get_state else JSON.stringify(payload))
    if error!=OK:
        _busy = false
        connection_problem.emit(error_string(error))

func _completed(result: int,code: int,_headers: PackedStringArray,body: PackedByteArray) -> void:
    _busy = false
    if result!=HTTPRequest.RESULT_SUCCESS or code not in [200,202]:
        connection_problem.emit("Park service unavailable or rejected request: HTTP %d" % code)
        return
    var parsed: Variant = JSON.parse_string(body.get_string_from_utf8())
    if not parsed is Dictionary:
        connection_problem.emit("Park service returned a non-object response")
        return
    var data: Dictionary = parsed
    if _kind!="state":
        command_queued.emit(str(data.get("command_id","")))
        return
    if data.get("schema")!="yellowstone.park_runtime.v1" or not data.get("bracket") is Array:
        return
    var next_session: String = str(data.get("session_id",""))
    var next_revision: int = int(data.get("revision",-1))
    if next_session==session_id and next_revision<revision:
        return
    if data.bracket.is_empty() or data.bracket.size()>2:
        return
    session_id = next_session
    revision = next_revision
    packet = data
    var report: Variant = data.get("residency",{})
    residency = report if report is Dictionary else {}
    _since_receive = 0.0
    stale = false
    snapshot_received.emit(packet)

func presentation_time_s() -> float:
    if packet.is_empty():
        return NAN
    var t: float = float(packet.presentation_s)
    if not bool(packet.get("paused",true)) and not bool(packet.get("clock_held",true)) and not stale:
        t += _since_receive*float(packet.get("time_scale",1.0))
    var last: Dictionary = packet.bracket[-1]
    return minf(t,float(last.t_s)) # No extrapolation beyond the received scientific bracket.

func _exit_tree() -> void:
    if is_instance_valid(_http):
        _http.cancel_request()
