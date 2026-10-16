extends Node3D
## Separate experimental scene. Does not replace main.tscn or claim Yellowstone visual parity.
const Frame = preload("res://scripts/park_runtime/world_frame.gd")
const Streamer = preload("res://scripts/park_runtime/terrain_streamer.gd")
const Monitor = preload("res://scripts/park_runtime/runtime_monitor.gd")
const Client = preload("res://scripts/park_runtime/park_client.gd")

@export_file("*.json") var catalog_path: String = "res://data/park_demo/catalog.json"
@export var title: String = "PARK RUNTIME / SYNTHETIC STREAMING FIXTURE"
@export var start_position := Vector3(-160,65,150)
var frame = Frame.new()
var stream = Streamer.new()
var observer := Camera3D.new()
var monitor = Monitor.new()
var client = Client.new()
var _velocity := Vector3.ZERO
var _pitch: float = -0.15

func _ready() -> void:
    var env := WorldEnvironment.new()
    var settings := Environment.new()
    settings.background_mode = Environment.BG_COLOR
    settings.background_color = Color(0.56,0.68,0.73)
    settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
    settings.ambient_light_color = Color(0.75,0.81,0.78)
    settings.ambient_light_energy = 0.6
    env.environment = settings
    add_child(env)
    var sun := DirectionalLight3D.new()
    sun.rotation_degrees = Vector3(-48,-35,0)
    sun.light_energy = 1.2
    add_child(sun)
    observer.position = start_position
    observer.rotation.y = -0.6
    observer.rotation.x = _pitch
    observer.near = 0.15
    observer.far = 30000.0
    observer.fov = 72.0
    add_child(observer)
    observer.make_current()
    frame.register_root(observer)
    add_child(stream)
    if not stream.configure(catalog_path,frame,observer):
        push_error("Prepare the demo elevation pack first; see README")
        set_process(false)
        return
    monitor.streamer = stream
    monitor.title = title
    monitor.client = client
    add_child(client)
    add_child(monitor)

func _unhandled_input(event: InputEvent) -> void:
    if event is InputEventMouseMotion and Input.is_mouse_button_pressed(MOUSE_BUTTON_RIGHT):
        observer.rotate_y(-event.relative.x*0.002)
        _pitch = clampf(_pitch-event.relative.y*0.002,-1.45,1.45)
        observer.rotation.x = _pitch

func _physics_process(delta: float) -> void:
    frame.maybe_rebase(observer)
    var direction := Vector3(float(Input.is_physical_key_pressed(KEY_D))-float(Input.is_physical_key_pressed(KEY_A)),
        float(Input.is_physical_key_pressed(KEY_E))-float(Input.is_physical_key_pressed(KEY_Q)),
        float(Input.is_physical_key_pressed(KEY_S))-float(Input.is_physical_key_pressed(KEY_W)))
    var speed: float = 65.0 if Input.is_physical_key_pressed(KEY_SHIFT) else 18.0
    _velocity = observer.global_basis*direction.limit_length()*speed
    observer.global_position += _velocity*delta
    stream.velocity = _velocity
