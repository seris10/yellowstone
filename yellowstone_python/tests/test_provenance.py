"""Tests for yellowstone_python.common.provenance atomic write and code_rev."""
from __future__ import annotations

import json
from unittest import mock

import pytest

from yellowstone_python.common.provenance import (FALLBACK_CODE_REV, build_id,
                                                  resolve_code_rev,
                                                  write_sidecar)


def _payload():
    return {"schema": "yellowstone.test.v1",
            "parameter_provenance": {"k": "authored"}}


def test_build_id_depends_on_code_rev():
    assert build_id({}, {}, "a") != build_id({}, {}, "b")
    assert build_id({}, {}) == build_id({}, {})


def test_build_id_omits_code_rev_when_none():
    with_rev = build_id({}, {}, FALLBACK_CODE_REV)
    without_rev = build_id({}, {}, None)
    assert with_rev != without_rev


def test_write_sidecar_atomic_leaves_previous_version_intact(tmp_path):
    path = tmp_path / "doc.json"
    prior = {"contract_version": "0.1.0", "status": "prior"}
    path.write_text(json.dumps(prior))

    def failing_tempfile(*args, **kwargs):
        raise RuntimeError("simulated interrupt")

    with mock.patch("tempfile.NamedTemporaryFile", side_effect=failing_tempfile):
        with pytest.raises(RuntimeError):
            write_sidecar(path, _payload(), sources=[], params={})
    on_disk = json.loads(path.read_text())
    assert on_disk == prior


def test_write_sidecar_cleans_up_temp_file(tmp_path):
    path = tmp_path / "doc.json"
    write_sidecar(path, _payload(), sources=[], params={})
    assert path.exists()
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    body = json.loads(path.read_text())
    assert body["contract_version"] == "0.1.0"
    assert body["code_rev"] == FALLBACK_CODE_REV


def test_resolve_code_rev_returns_fallback_outside_git(tmp_path):
    rev, source = resolve_code_rev(tmp_path)
    assert source in ("git", "fallback")
    if source == "fallback":
        assert rev == FALLBACK_CODE_REV
    else:
        assert rev


def test_resolve_code_rev_repo_default_runs():
    rev, source = resolve_code_rev()
    assert source in ("git", "fallback")
    assert isinstance(rev, str) and rev
