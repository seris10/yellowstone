"""Replay-derived runtime exports and actor authority."""
import json
import pytest

from yellowstone_python.exporters.runtime_series import reach_summaries
from yellowstone_python.exporters.godot_sidecars import write_plume_field_json


def test_reach_summary_uses_flow_weighted_cells():
    replay = {"cells": [{"start_s_m": 0, "end_s_m": 10, "center_s_m": 5, "q_out_m3_s": 1},
                         {"start_s_m": 10, "end_s_m": 20, "center_s_m": 15, "q_out_m3_s": 3}],
              "legacy_queries": [{"reach_id": "reach", "s_m": 10}],
              "frames": [{"t_s": 0, "temperature_c": [10, 20]}]}
    assert reach_summaries(replay, [{"id": "reach"}])[0]["temperature_c"] == 17.5


def test_plume_uses_source_and_bridge_replay_temperatures(tmp_path):
    replay = {"cells": [{"center_s_m": 5}, {"center_s_m": 15}],
              "frames": [{"temperature_c": [35.0, 19.0]}],
              "source_connections": [{"source_id": "excelsior", "s_m": 5}],
              "legacy_queries": [{"reach_id": "bridge_downstream", "s_m": 15}]}
    (tmp_path / "river_replay.json").write_text(json.dumps({"replay": replay}))
    path = write_plume_field_json(tmp_path)
    result = json.loads(path.read_text())
    assert result["hot_source_c"] == 35.0
    assert result["river_c"] == 19.0
