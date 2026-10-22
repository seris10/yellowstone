"""Process-level stop and resume checks for the reference park runtime service."""
import os
import re
import signal
import subprocess
import sys
import time
import pytest
from tests.paths import REPO

SAVED = re.compile(r"Saved committed checkpoint at ([0-9.]+) physical seconds")


def run_until_signal(state, run_s, signum=signal.SIGTERM):
    """Start the service on a state file, send signum after run_s and return its output."""
    env = dict(os.environ, PYTHONPATH=str(REPO))
    process = subprocess.Popen(
        [sys.executable, "-m", "yellowstone_python.park_runtime", "--port", "0", "--state", str(state)],
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    try:
        first = process.stdout.readline()
        if "PermissionError" in first or process.poll() is not None:
            rest = process.stdout.read()
            if "PermissionError" in first + rest:
                pytest.skip("sandbox disallows loopback socket binding")
            raise AssertionError(first + rest)
        assert "Ctrl+C or SIGTERM saves committed state" in first
        time.sleep(run_s)
        process.send_signal(signum)
        output, _ = process.communicate(timeout=20)
    finally:
        if process.poll() is None:
            process.kill()
            process.communicate()
    return process.returncode, output


def test_sigterm_saves_and_restart_resumes(tmp_path):
    state = tmp_path / "park.sqlite3"
    code, output = run_until_signal(state, 2.5)
    assert code == 0, output
    first = float(SAVED.search(output).group(1))
    assert first >= 1.0 and state.exists()
    code, output = run_until_signal(state, 1.5)
    assert code == 0, output
    assert float(SAVED.search(output).group(1)) >= first


def test_sigint_save_is_unchanged(tmp_path):
    code, output = run_until_signal(tmp_path / "park.sqlite3", 1.5, signal.SIGINT)
    assert code == 0, output
    assert float(SAVED.search(output).group(1)) >= 1.0
