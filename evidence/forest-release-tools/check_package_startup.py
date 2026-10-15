"""Check packaged offline startup, errors and floor contacts."""
from pathlib import Path
import socket
import subprocess
import sys

package = Path(sys.argv[1]).resolve()
try:
    with socket.create_connection(("127.0.0.1", 8765), timeout=1):
        raise RuntimeError("offline startup requires the live service to be unavailable")
except (ConnectionRefusedError, TimeoutError):
    pass
command = ["godot", "--headless", "--path", str(package), "--fixed-fps", "60", "--quit-after", "1200", "--", "--smoke-test"]
result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
print(result.stdout, end="")
assert result.returncode == 0, result.returncode
assert "ERROR:" not in result.stdout and "Parse Error" not in result.stdout
for name in ("overlook", "boardwalk", "river", "trailhead"):
    assert "SMOKE anchor=" + name + " floor=true" in result.stdout
assert "SMOKE heat_budget_error=0.0" in result.stdout
print("PACKAGE_OFFLINE_STARTUP PASS; service unavailable; all anchors grounded; no script/resource errors")
