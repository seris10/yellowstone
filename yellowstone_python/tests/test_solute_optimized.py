"""Solute solver equivalence and live forcing cache invalidation checks."""
from dataclasses import replace

import numpy as np
import pytest

from yellowstone_python.river.river_transport import Cell, Series
from yellowstone_python.river.solute_transport import (
    SOLUTE_KEYS, BoundaryConcentrations, SoluteSource, SoluteTransport,
)


def _schedule(times, values):
    return {"times_s": times, "values": values}


def _transport(compiled):
    cells = tuple(Cell(id=f"c{i}", length_m=20.0 + 5.0 * i,
                       width_m=3.0 + i, volume_m3=80.0 + 20.0 * i,
                       initial_c=0.0, dispersion_m2_s=0.2 + 0.1 * i,
                       exchange_w_m2_k=0.0) for i in range(4))
    source = SoluteSource(
        id="spring", cell_id="c1", flow_m3_s=_schedule([0.0, 5.0, 11.0], [0.15, 0.0, 0.4]),
        concentrations={
            "chloride_mg_l": _schedule([0.0, 4.0, 9.0], [100.0, 40.0, 160.0]),
            "arsenic_ug_l": _schedule([0.0, 4.0, 9.0], [800.0, 80.0, 1200.0]),
            "boron_mg_l": _schedule([0.0, 4.0, 9.0], [0.3, 0.1, 2.0]),
        })
    transport = SoluteTransport(
        cells=cells, boundary_m3_s=_schedule([0.0, 3.0, 7.0], [1.2, 0.0, 2.1]),
        boundary_concentrations=BoundaryConcentrations(
            chloride_mg_l=_schedule([0.0, 6.0, 13.0], [2.0, 5.0, 3.0]),
            arsenic_ug_l=1.0, boron_mg_l=0.02), sources=(source,),
        initial_concentrations={key: (0.2, 0.5, 0.8, 1.2) for key in SOLUTE_KEYS})
    transport._compiled_solutes = compiled
    return transport


def _assert_frames_equal(actual, reference):
    assert len(actual) == len(reference)
    for frame, expected in zip(actual, reference):
        assert frame["t_s"] == expected["t_s"]
        for solute in SOLUTE_KEYS:
            np.testing.assert_allclose(frame[solute], expected[solute], rtol=1e-13, atol=1e-12)
        budget = frame["mass_budget"]
        expected_budget = expected["mass_budget"]
        assert budget["water_balance_m3"] == expected_budget["water_balance_m3"]
        assert budget["water_relative_residual"] < 1e-12
        for solute in SOLUTE_KEYS:
            assert budget["solutes"][solute] == pytest.approx(
                expected_budget["solutes"][solute], rel=1e-13, abs=1e-10)
            assert budget["solutes"][solute]["mass_relative_residual"] < 1e-12


@pytest.mark.parametrize("dt_s", [0.5, 2.7])
def test_compiled_solver_matches_reference_across_forcing_timelines(dt_s):
    actual, reference = _transport(True), _transport(False)
    frames = actual.run(15.0, dt_s=dt_s, sample_s=1.3)
    expected = reference.run(15.0, dt_s=dt_s, sample_s=1.3)
    _assert_frames_equal(frames, expected)
    steady = actual.steady_concentrations(time_s=15.0)
    steady_reference = reference.steady_concentrations(time_s=15.0)
    for solute in SOLUTE_KEYS:
        np.testing.assert_allclose(steady[solute], steady_reference[solute], rtol=1e-13, atol=1e-12)
    assert steady["chloride_mg_l"][-1] == pytest.approx((2.1 * 3.0 + 0.4 * 160.0) / 2.5)
    assert steady["arsenic_ug_l"][-1] == pytest.approx((2.1 * 1.0 + 0.4 * 1200.0) / 2.5)
    assert steady["boron_mg_l"][-1] == pytest.approx((2.1 * 0.02 + 0.4 * 2.0) / 2.5)


@pytest.mark.parametrize("change", ["source_groups", "boundary_flow", "both"])
def test_live_forcing_replacement_invalidates_cached_flow_and_matrix(change):
    actual, reference = _transport(True), _transport(False)
    _assert_frames_equal(actual.run(2.0, dt_s=0.5, sample_s=1.0),
                         reference.run(2.0, dt_s=0.5, sample_s=1.0))
    for transport in (actual, reference):
        if change in ("source_groups", "both"):
            source = replace(transport.sources[0], cell_id="c2",
                             flow_m3_s=_schedule([0.0, 8.0], [0.8, 0.1]),
                             concentrations={"chloride_mg_l": 180.0,
                                             "arsenic_ug_l": 200.0, "boron_mg_l": 2.0})
            transport.sources = (source,)
            transport._sources_by_cell = [[source] if cell.id == "c2" else []
                                          for cell in transport.cells]
        if change in ("boundary_flow", "both"):
            transport._boundary_q_series = Series.parse(_schedule([0.0, 10.0], [2.5, 1.7]))
        transport._forcing = (transport._boundary_q_series,
                              *transport._boundary_c_series.values(),
                              *(source.flow_m3_s for source in transport.sources),
                              *(series for source in transport.sources for series in source.concentrations.values()))
    boundary = 2.5 if change in ("boundary_flow", "both") else 1.2
    if change in ("source_groups", "both"):
        assert actual._face_flow_at(2.0) == pytest.approx(
            (boundary, boundary, boundary, boundary + 0.8, boundary + 0.8))
        assert actual._source_qc("chloride_mg_l", 2.0) == pytest.approx((0.0, 0.0, 144.0, 0.0))
    else:
        assert actual._face_flow_at(2.0) == pytest.approx(
            (boundary, boundary, boundary + 0.15, boundary + 0.15, boundary + 0.15))
    _assert_frames_equal(actual.run(12.0, dt_s=2.3, sample_s=1.3),
                         reference.run(12.0, dt_s=2.3, sample_s=1.3))
