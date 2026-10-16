"""Offline verification for replay.plume2d (synthetic grids only)."""
import math

import pytest

pytestmark = pytest.mark.needs_science
plume2d = pytest.importorskip("yellowstone_python.river.plume2d")


from yellowstone_python.river.plume2d import K_EXCH_PER_S, U_MAPPED_M_S


def _sol(**kw):
    args = {"nx": 33, "nz": 33, "extent_m": 600.0}
    args.update(kw)
    return plume2d.solve_steady(**args)


def _met(sol, ambient=17.8):
    return plume2d.plume_metrics(sol, ambient, U_MAPPED_M_S, K_EXCH_PER_S)


def test_closure_residual_small():
    sol = _sol()
    assert sol["discrete_residual_c_s"] < 1e-6


def test_bounded_by_boundary_values():
    sol = _sol(ambient_c=17.0, source_c=20.0)
    assert min(sol["field"]) >= 17.0 - 1e-9
    assert max(sol["field"]) <= 20.0 + 1e-9


def test_zero_flow_is_symmetric():
    sol = _sol(u_m_s=0.0, source_xz=(0.0, 0.0))
    nx, nz, t = sol["nx"], sol["nz"], sol["field"]
    mid = nz // 2
    for k in range(1, nx // 2):
        a = t[mid * nx + nx // 2 - k]
        b = t[mid * nx + nx // 2 + k]
        assert abs(a - b) < 1e-6


def test_centerline_decays_downstream():
    sol = _sol()
    prof = plume2d.centerline(sol["field"], sol["nx"], sol["nz"])
    peak = prof.index(max(prof))
    for a, b in zip(prof[peak:-1], prof[peak + 1:]):
        assert b <= a + 1e-9


def test_finer_grid_agrees():
    coarse = _sol(nx=25, nz=25, source_r_m=90.0)
    fine = _sol(nx=49, nz=49, source_r_m=90.0)
    mc = _met(coarse)
    mf = _met(fine)
    assert abs(mc["peak_anomaly_c"] - mf["peak_anomaly_c"]) < 0.05
    assert abs(mc["footprint_length_m"] - mf["footprint_length_m"]) < 60.0
    assert mc["half_width_m"] == pytest.approx(mf["half_width_m"], rel=0.2)
    assert (mc["exchange_length_u_over_k_m"]
            == mf["exchange_length_u_over_k_m"] == pytest.approx(0.73 * 18000))


def test_metrics_footprint_positive():
    sol = _sol()
    m = _met(sol)
    assert m["peak_anomaly_c"] > 0
    assert m["footprint_length_m"] > 0
    assert m["exchange_length_u_over_k_m"] == pytest.approx(0.73 * 18000)
    assert m["half_width_m"] > 0


def test_bad_inputs_raise():
    with pytest.raises(ValueError):
        _sol(nx=4)
    with pytest.raises(ValueError):
        _sol(d_trans_m2_s=0.0)
    with pytest.raises(ValueError):
        _sol(u_m_s=-1.0)
    with pytest.raises(ValueError):
        _sol(ambient_c=math.inf)
