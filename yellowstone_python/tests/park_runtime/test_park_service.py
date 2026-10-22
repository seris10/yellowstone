import json
import threading
import time
import urllib.request
import pytest
from tests.park_runtime.test_park_runtime import domain
from yellowstone_python.park_runtime.runtime import ParkRuntime
from yellowstone_python.park_runtime.service import RuntimeService,make_server


def test_service_continues_and_filters_without_render_dependency():
    runtime=ParkRuntime([domain("visible"),domain("hidden")],quantum_s=.1,history_s=1,max_frames=128)
    service=RuntimeService(runtime,horizon_s=.5,time_scale=1.)
    service.start()
    try:
        time.sleep(.25)
        service.submit("interest",{"sequence":1,"region_ids":["visible"]})
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            data=json.loads(service.publication())
            if data["interest_sequence"]==1 and data["presentation_s"]>.1: break
            time.sleep(.01)
        assert data["worker_error"] is None
        assert data["presentation_s"]>.1
        assert list(data["bracket"][0]["regions"])==["visible"]
        assert runtime.domains["hidden"].time_s>.1
        assert len(runtime._frames)<40
    finally:
        service.close()


def test_http_contract():
    runtime=ParkRuntime([domain()]); service=RuntimeService(runtime)
    try:
        server=make_server(service,port=0)
    except PermissionError:
        pytest.skip("sandbox disallows loopback socket binding")
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start(); service.start()
    base=f"http://127.0.0.1:{server.server_address[1]}"
    try:
        with urllib.request.urlopen(base+"/api/park/state",timeout=3) as response:
            data=json.load(response)
        assert data["schema"]=="yellowstone.park_runtime.v1"
        request=urllib.request.Request(base+"/api/park/clock",data=b'{"paused":true}',headers={"Content-Type":"application/json"})
        with urllib.request.urlopen(request,timeout=3) as response:
            assert response.status==202
            command_id=json.load(response)["command_id"]
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            result=service.result(command_id)
            if result["status"]=="done": break
            time.sleep(.01)
        assert result["status"]=="done"
    finally:
        server.shutdown(); server.server_close(); thread.join(3); service.close()


def test_intervention_retry_with_previous_revision_is_idempotent():
    runtime=ParkRuntime([domain()]); runtime.compute_until(5)
    service=RuntimeService(runtime); service.presentation_s=4.
    payload={"session_id":runtime.session_id,"revision":0,"event_id":"retry",
             "domain_id":"river","at_s":4.,"changes":{"inputs":{}}}
    first=service._command("intervene",payload)
    runtime.compute_until(6); service.presentation_s=5.
    second=service._command("intervene",payload)
    assert first==second and runtime.revision==1 and service.presentation_s==5.


def test_rejected_http_clock_preserves_state():
    service = RuntimeService(ParkRuntime([domain()]))
    server = make_server(service, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    service.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"

    def get(path):
        with urllib.request.urlopen(base + path, timeout=3) as response:
            return json.load(response)

    def post(kind, payload):
        request = urllib.request.Request(base + "/api/park/" + kind,
                                         data=json.dumps(payload).encode(),
                                         headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.load(response)["command_id"]

    try:
        before = get("/api/park/state")
        rejected = post("clock", {"paused": True, "time_scale": -1})
        post("interest", {"sequence": 9, "region_ids": ["river"]})
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            after = get("/api/park/state")
            if after["interest_sequence"] == 9:
                break
            time.sleep(0.01)
        assert after["interest_sequence"] == 9
        result = get("/api/park/commands/" + rejected)
        assert result["status"] == "rejected"
        assert "time_scale" in result["error"]
        assert after["paused"] == before["paused"]
        assert after["time_scale"] == before["time_scale"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)
        service.close()
