extends SceneTree
## Polls a running park service (option --url) and checks snapshots and clock commands.
const Client = preload("res://scripts/park_runtime/park_client.gd")
var failures: int = 0
var checks: int = 0
var client

func _initialize() -> void:
    call_deferred("run")

func check(condition: bool, message: String) -> void:
    checks += 1
    if not condition:
        failures += 1
        push_error(message)

func option(name: String, fallback: String) -> String:
    for argument: String in OS.get_cmdline_user_args():
        if argument.begins_with("--" + name + "="):
            return argument.substr(name.length() + 3)
    return fallback

func wait_for(condition: Callable, seconds: float) -> bool:
    var deadline: int = Time.get_ticks_msec() + int(seconds * 1000.0)
    while Time.get_ticks_msec() < deadline:
        if condition.call():
            return true
        await create_timer(0.05).timeout
    return false

func run() -> void:
    client = Client.new()
    client.base_url = option("url", "http://127.0.0.1:8766")
    client.poll_interval_s = 0.1
    root.add_child(client)
    var got: bool = await wait_for(func() -> bool: return not client.packet.is_empty(), 8.0)
    check(got, "no snapshot received")
    if not got:
        quit(1)
        return
    check(client.packet.schema == "yellowstone.park_runtime.v1", "schema differs")
    check(client.session_id.length() > 0 and client.revision >= 0, "session or revision missing")
    check(not client.stale, "fresh snapshot marked stale")
    var first: float = client.presentation_time_s()
    check(is_finite(first), "presentation time not finite")
    check(client.queue_command("clock", {"paused": true}), "clock command refused")
    var paused: bool = await wait_for(func() -> bool: return bool(client.packet.get("paused", false)), 6.0)
    check(paused, "service never reported paused")
    var held: float = client.presentation_time_s()
    await create_timer(1.0).timeout
    check(absf(client.presentation_time_s() - held) < 0.001, "paused clock advanced")
    check(client.queue_command("clock", {"paused": false}), "resume command refused")
    var resumed: bool = await wait_for(func() -> bool: return not bool(client.packet.get("paused", true)), 6.0)
    check(resumed, "service never resumed")
    check(not client.queue_command("shutdown", {}), "unsupported command accepted")
    print("PARK_CLIENT_SERVICE checks=", checks, " failures=", failures, " first_t=", first)
    client.queue_free()
    await process_frame
    quit(1 if failures else 0)
