"""Frozen numerical experiment and causal downstream response."""
from tools.reference_run import run_reference


def test_reference_run_is_repeatable_and_has_a_downstream_intervention():
    first = run_reference()
    assert first == run_reference()
    assert first["frames"][0]["control_c"] == first["frames"][0]["intervention_c"]
    assert first["frames"][-1]["intervention_c"][1] > first["frames"][-1]["control_c"][1]
    assert first["snow_phase_control"]["runoff_mm"] == 0.


def test_mapped_comparison_holds_initial_state_and_other_forcing_fixed():
    from yellowstone_python.river.river_transport import make_replay
    from tools.reference_run import mapped_comparison
    config = {"cells": [{"id": "a", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 15.},
                        {"id": "b", "length_m": 20., "width_m": 10., "volume_m3": 200., "initial_c": 15.}],
              "sources": [{"id": "outflow", "cell_id": "a", "flow_m3_s": 1.,
                           "temperature_c": {"times_s": [0., 30., 90.], "values": [20., 38., 20.]}}],
              "boundary_m3_s": 5., "boundary_c": 15., "air_c": 8.,
              "duration_s": 120., "dt_s": 1., "sample_s": 10.}
    replay = make_replay(config)
    replay["intervention"] = {"source_id": "outflow", "start_s": 30., "end_s": 90., "delta_c": 18.}
    comparison = mapped_comparison(replay)
    assert all(r["control_c"] == r["intervention_c"] for r in comparison["frames"] if r["t_s"] <= 30.)
    assert comparison["maximum_delta_c"] > 1.
    assert comparison["control_budget"]["water_relative_residual"] < 1e-12
