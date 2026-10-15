extends SceneTree

var world: Node3D
var atmosphere: Node3D
var camera: Camera3D
var output := "res://../work/atmosphere-world-rain"
var report := {"schema": "yellowstone.world_rain_history.v1", "scope": "Controlled weather and solar-override fixture in the actual saved world; no measured occurrence-frequency claim", "captures": [], "failures": []}

func _initialize() -> void:
 call_deferred("run")

func run() -> void:
 if DisplayServer.get_name() == "headless":
  quit(1)
  return
 create_timer(240, true, false, true).timeout.connect(func(): quit(1))
 ProjectSettings.set_setting("yellowstone/live_url", "http://127.0.0.1:1")
 root.size = Vector2i(1440, 900)
 root.content_scale_size = Vector2i(1440, 900)
 root.show()
 world = load("res://scenes/main.tscn").instantiate()
 root.add_child(world)
 current_scene = world
 for frame in range(12):
  await process_frame
 world.set_process(false)
 world.ecosystem.set_process(false)
 world.weather_snapshot_reader.set_process(false)
 atmosphere = world.atmosphere_controller
 atmosphere.set_process(false)
 atmosphere.smooth_weather_transitions = false
 world.player.enabled = false
 world.player.set_physics_process(false)
 world.player.set_process_input(false)
 world.overlay.visible = false
 world.menu.visible = false
 if world.live_client != null:
  world.live_client.set_process(false)
 if world.data_watcher != null:
  world.data_watcher.set_process(false)
 Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
 var anchor: Dictionary
 var pool: Dictionary
 for item: Dictionary in world.spec.anchors:
  if item.id == "overlook":
   anchor = item
 for item: Dictionary in world.spec.pools:
  if item.source_id == 1034:
   pool = item
 var origin := Vector3(anchor.position[0], anchor.position[1], anchor.position[2])
 var center := Vector3(pool.center[0], pool.center[1], pool.center[2])
 var toward := Vector3(center.x - origin.x, 0.0, center.z - origin.z).normalized()
 var sun_azimuth := fposmod(rad_to_deg(atan2(toward.x, -toward.z)) + 180.0, 360.0)
 world.player.place_at(origin, origin + toward)
 camera = world.player.camera
 camera.rotation.x = deg_to_rad(8.0)
 camera.fov = 72.0
 world.ecosystem.paused = true
 world.ecosystem.elapsed = 0.0
 atmosphere.reset_simulation_elapsed(0.0)
 world._sync_atmosphere_clock()
 var weather := {"cloud_fraction": 0.0, "cloud_base_agl_m": 1050.0, "cloud_thickness_m": 700.0,
  "solar_azimuth_deg": sun_azimuth, "solar_elevation_deg": 14.0, "precipitation_rate_mm_h": 0.0,
  "snow_fraction": 0.0, "relative_humidity": 0.55, "wind_direction_deg": sun_azimuth, "wind_speed_mps": 2.0,
  "visibility_m": 26000.0, "fog_density": 0.0, "ground_wetness_fraction": 0.15}
 atmosphere.set_weather_state(weather)
 atmosphere._update_atmosphere(0.0)
 Engine.time_scale = 0.0
 DirAccess.make_dir_recursive_absolute(output)
 report["conditions"] = {"rain_seconds": 120, "rain_rate_mm_h": 8, "rain_cloud_fraction": 0.8,
  "clear_seconds": 20, "clear_cloud_fraction": 0.0, "snow_fraction": 0.0, "relative_humidity": 0.55,
  "wind_speed_mps": 2.0, "wind_from_degrees": sun_azimuth, "solar_override_azimuth_deg": sun_azimuth,
  "solar_override_elevation_deg": 14.0, "weather_interpolation": false,
  "clock": "Production world._sync_atmosphere_clock from explicitly accepted elapsed seconds",
  "curtain_override": false, "camera_elevation_deg": 8.0, "vertical_fov_deg": camera.fov}
 if atmosphere._rainbow.visible or atmosphere._rain_curtain.optical_depth != 0.0:
  report.failures.append("Clear initial history contains a rainbow")
 await capture("world-clear-startup")
 atmosphere.set_weather_state({"cloud_fraction": 0.8, "precipitation_rate_mm_h": 8.0})
 for second in range(1, 121):
  world.ecosystem.elapsed = float(second)
  world._sync_atmosphere_clock()
  atmosphere._update_atmosphere(0.0)
 report["after_rain"] = atmosphere.get_render_state()
 atmosphere.set_weather_state({"cloud_fraction": 0.0, "precipitation_rate_mm_h": 0.0})
 for second in range(121, 141):
  world.ecosystem.elapsed = float(second)
  world._sync_atmosphere_clock()
  atmosphere._update_atmosphere(0.0)
 report["after_clear"] = atmosphere.get_render_state()
 if not atmosphere._rainbow.visible or atmosphere._rain_curtain.optical_depth <= 0.0:
  report.failures.append("Liquid weather history did not enable scattering")
 await capture("world-post-rain")
 atmosphere._rainbow.visible = false
 await capture("world-post-rain-layer-hidden")
 atmosphere._update_atmosphere(0.0)
 camera.rotation.x = deg_to_rad(-8.0)
 await capture("world-post-rain-spring-view")
 report["source_hashes"] = {}
 for path: String in ["scripts/yellowstone_atmosphere.gd", "scripts/atmosphere_optics.gd", "scripts/world.gd", "scripts/terrain_materials.gd", "shaders/rainbow.gdshader", "shaders/yellowstone_cloud_shell.gdshader", "scenes/authored_world.tscn", "assets/textures/color_mips/color_mips.json", "assets/imported/lodgepole/lodgepole_metadata.json", "data/release.json"]:
  report.source_hashes[path] = FileAccess.get_sha256("res://" + path)
 report["fixture_sha256"] = FileAccess.get_sha256("res://work/atmosphere-audit/world-rain-history.gd")
 report["godot"] = Engine.get_version_info().string
 report["renderer"] = RenderingServer.get_current_rendering_method()
 report["gpu"] = RenderingServer.get_video_adapter_name()
 report["passed"] = report.failures.is_empty()
 var file := FileAccess.open(output.path_join("report.json"), FileAccess.WRITE)
 file.store_string(JSON.stringify(report, "  ") + "\n")
 print("WORLD_RAIN_HISTORY ", JSON.stringify(report))
 quit(0 if report.passed else 1)

func capture(label: String) -> void:
 for frame in range(12):
  await process_frame
 await RenderingServer.frame_post_draw
 var image: Image = root.get_texture().get_image()
 var path := output.path_join(label + ".png")
 image.save_png(path)
 report.captures.append({"label": label, "path": path, "sha256": FileAccess.get_sha256(path),
  "camera_m": [camera.global_position.x, camera.global_position.y, camera.global_position.z],
  "size_px": [image.get_width(), image.get_height()], "draw_calls": Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME),
  "primitives": Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)})
