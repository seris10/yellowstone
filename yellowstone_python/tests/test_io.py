"""Atomic JSON failure paths and checked file reads."""
import hashlib
import pytest

from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic


def test_serialization_failure_preserves_destination(tmp_path):
    path = tmp_path / "state.json"
    path.write_text('{"old": 1}')
    with pytest.raises(ValueError):
        write_json_atomic(path, {"bad": float("nan")})
    assert path.read_text() == '{"old": 1}'
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_roundtrip_and_hash(tmp_path):
    path = tmp_path / "state.json"
    assert write_json_atomic(path, {"value": 2}) == path
    assert load_json(path) == {"value": 2}
    assert sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="state.json"):
        load_json(path, expect=list)
    with pytest.raises(ValueError, match="absent.json"):
        load_json(tmp_path / "absent.json")
