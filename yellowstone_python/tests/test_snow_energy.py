"""Offline tests for snow_energy (synthetic forcing only)."""
import pytest

pytestmark = pytest.mark.needs_science
se = pytest.importorskip("yellowstone_python.land.snow_energy")


def test_toa_annual_cycle():
    jun = se.clear_sky_toa_w_m2(172, 44.6)
    dec = se.clear_sky_toa_w_m2(355, 44.6)
    assert jun > dec > 0
    assert se.clear_sky_toa_w_m2(355, 75.0) == 0.0
    eq = se.clear_sky_toa_w_m2(80, 0.0)
    assert 400 < eq < 480


def test_cloud_factor_shape():
    assert se.cloud_factor(0.0) == pytest.approx(0.25)
    assert se.cloud_factor(100.0) == pytest.approx(1.0)
    assert se.cloud_factor(5.0) < se.cloud_factor(15.0)


def test_accumulation_matches_step_snow():
    from yellowstone_python.land.snow_season import step_snow
    eb = se.step_snow_eb(50.0, 0.7, -2.0, 0.0, -4.0, 10.0,
                         200.0, 0.3, 5.0)
    dd = step_snow(50.0, -2.0, 10.0, k_melt=0.0,
                   aspect_retention=1.0, canopy_keep=1.0,
                   wind_loss=0.0, thermal_flux_mm_d=0.0)
    assert eb[2] == pytest.approx(dd[2])
    assert eb[3] == pytest.approx(dd[3])
    assert eb[4] == pytest.approx(dd[4])


def test_energy_conservation_deep_pack():
    snow, melt, *_ = se.step_snow_eb(5000.0, 0.6, 8.0, 14.0, 2.0,
                                     0.0, 450.0, 0.3, 5.0)
    alb = max(se.ALB_FLOOR, 0.6 - se.ALB_DECAY_DAY)
    sw = 0.3 * 450.0 * se.cloud_factor(12.0) * (1.0 - alb)
    net = sw + se.C0_W_M2 + 5.0 * 8.0
    assert melt == pytest.approx(net * 86400.0 / 334000.0, rel=1e-9)


def test_no_melt_cold_dark():
    snow, melt, *_ = se.step_snow_eb(100.0, 0.6, -10.0, -8.0,
                                     -12.0, 0.0, 0.0, 0.5, 5.0)
    assert melt == 0.0
    assert snow == pytest.approx(100.0)


def test_melt_monotonic_in_forcing():
    base = dict(snow_mm=500.0, albedo=0.6, tmax_c=10.0, tmin_c=0.0,
                precip_mm_d=0.0, toa_w_m2=400.0, c_t=5.0, wind_loss=0.0)
    cold = se.step_snow_eb(air_c=2.0, s_rad=0.2, **base)[1]
    warm = se.step_snow_eb(air_c=12.0, s_rad=0.2, **base)[1]
    dim = se.step_snow_eb(air_c=12.0, s_rad=0.0, **base)[1]
    assert warm >= cold >= 0.0
    assert warm >= dim


def test_gap_rules():
    dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
    with pytest.raises(ValueError):
        se.prepare_forcing_eb(dates, [None, None, None, None][:3],
                              [30.0] * 3, [20.0] * 3, [0.0] * 3)
    out = se.prepare_forcing_eb(dates, [30.0, None, 32.0],
                                [35.0] * 3, [25.0] * 3, [None, 0.1, 0.0])
    assert out[0][1] == pytest.approx(out[0][0])
    assert out[3][0] == 0.0
    assert out[5]["prcp_zeroed"] == 1


def test_fit_recovers_synthetic():
    import random
    rng = random.Random(7)
    n = 120
    air = [-5.0 + 20.0 * k / (n - 1) for k in range(n)]
    tmax = [a + rng.uniform(3, 8) for a in air]
    tmin = [a - rng.uniform(3, 8) for a in air]
    prcp = [4.0 if a < 1.0 else 0.0 for a in air]
    dois = [(k % 365) + 1 for k in range(n)]
    obs = se.daily_swe_series_eb(44.6, air, tmax, tmin, prcp,
                                 dois, 0.3, 6.0)
    assert max(obs) > 50.0
    assert obs[-1] == 0.0
    fit = se.fit_eb_params(44.6, air, tmax, tmin, prcp, dois,
                           obs, list(range(n)),
                           s_grid=[0.1, 0.3, 0.5],
                           ct_grid=[2.0, 6.0, 10.0])
    assert (fit["best_s_rad"], fit["best_c_turb_w_m2_k"]) == (0.3, 6.0)
    assert len(fit["runners_up"]) == 2
    assert "parameter_at_grid_boundary" in fit
    assert "near_tie_count" in fit


def test_fixed_params_reject_off_grid(tmp_path):
    import json
    bad = {"sites": {"x": {"fitted": {"s_rad": 99.0,
                                      "c_turb_w_m2_k": 1.0}}}}
    p = tmp_path / "bad.json"
    p.write_text(json.dumps(bad))
    with pytest.raises(ValueError):
        se.load_fixed_params(str(p))


def test_fixed_eval_carries_degree_day_reference(tmp_path):
    import datetime
    import json
    base = datetime.date(2025, 10, 1)
    days = {}
    for k in range(90):
        d = (base + datetime.timedelta(days=k)).isoformat()
        tavg = 30.0 + 20.0 * k / 89
        days[d] = {"WTEQ": 0.0, "PRCP": 0.0, "SNWD": 0.0,
                   "TAVG": tavg, "TMAX": tavg + 5.0, "TMIN": tavg - 5.0}
    bundle = {"schema": "yellowstone.snotel_obs.v1",
              "fetched_at_utc": "2026-10-11T00:00:00Z",
              "window": {"begin": "2025-10-01", "end": "2025-12-29"},
              "sites": {"t": {"latitude": 44.6, "days": days}}}
    p = tmp_path / "bundle.json"
    p.write_text(json.dumps(bundle))
    art = se.evaluate_fixed_params(
        str(p), {"t": {"s_rad": 0.1, "c_turb_w_m2_k": 2.0}},
        split="2025-11-15")
    site = art["sites"]["t"]
    assert "degree_day_holdout_rmse_mm" in site
    assert isinstance(site["beats_degree_day"], bool)
    assert isinstance(site["beats_both_nulls"], bool)
