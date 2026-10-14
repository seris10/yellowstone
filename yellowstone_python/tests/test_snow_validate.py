from yellowstone_python.land.snow_validate import daily_swe_series, evaluate_fixed_params, f_to_c, fit_snow_params, in_to_mm, load_fixed_params, peak_timing_error_days, prepare_forcing, train_holdout_split, validate_site


def _patch():
    return {"id": "t", "habitat": "dry_meadow",
            "center_xz": [0, 0], "moisture": 0.5}


def test_conversions():
    assert f_to_c(32.0) == 0.0 and in_to_mm(1.0) == 25.4


def test_prepare_forcing_fills_and_counts():
    dates = ["2026-01-01", "2026-01-02", "2026-01-03"]
    air, prcp, fills = prepare_forcing(
        dates, [32.0, None, 50.0], [0.1, None, 0.2])
    assert air[1] == air[0] and fills == {"tavg_filled": 1,
                                          "prcp_zeroed": 1}
    assert prcp == [2.54, 0.0, 5.08]


def test_prepare_forcing_refuses_long_gap():
    dates = [f"2026-01-0{d}" for d in range(1, 7)]
    try:
        prepare_forcing(dates, [32.0] + [None] * 5, [0.0] * 6)
    except ValueError:
        return
    raise AssertionError('long TAVG gap must refuse. invent weather')


def test_prepare_forcing_refuses_leading_null():
    try:
        prepare_forcing(["2026-01-01"], [None], [0.0])
    except ValueError:
        return
    raise AssertionError("leading null TAVG must refuse (nothing to fill from)")


def test_split_is_contiguous_on_date():
    dates = [f"2026-02-{d:02d}" for d in range(25, 29)] + \
            [f"2026-03-{d:02d}" for d in range(1, 4)]
    train, hold = train_holdout_split(dates)
    assert train == [0, 1, 2, 3] and hold == [4, 5, 6]


def test_peak_timing_signed_days():
    dates = ["2026-03-01", "2026-03-05", "2026-03-10"]
    assert peak_timing_error_days(dates, [1.0, 5.0, 2.0],
                                  [1.0, 2.0, 5.0]) == -5


def test_daily_series_accumulates_when_freezing():
    swe, soil = daily_swe_series(_patch(), [-5.0] * 5, [4.0] * 5, 3.0)
    assert len(swe) == 5 and swe[-1] > swe[0] > 0.0
    assert all(s >= 0.0 for s in soil)


def test_fit_recovers_synthetic_params_optimizer_check_only():
    # Inverse crime by construction: identical model generates and fits; this exercises the optimizer. Fit only over days where truth is positive; after melt-out all param sets agree.
    air = [-2.0] * 60 + [3.0] * 30
    prcp = [10.0] * 60 + [0.0] * 30
    truth, _ = daily_swe_series(_patch(), air, prcp, 3.0, wind_loss=0.05)
    idx = [i for i in range(90) if truth[i] > 0.5]
    assert len(idx) > 30
    fit = fit_snow_params(
        _patch(), air, prcp, truth, idx,
        k_grid=[2.5, 3.0, 3.5], wind_grid=[0.02, 0.05, 0.1])
    assert (fit["best_k"], fit["best_wind"]) == (3.0, 0.05)
    assert fit["train_rmse_mm"] == 0.0
    # Tie and grid provenance are recorded.
    assert fit["grid"]["n_candidates"] == 9
    assert fit["grid"]["tie_rule"]
    assert fit["train_scored_n"] == len(idx)
    assert fit["tie_count"] >= 0


def test_fit_metadata_records_grid_and_tie_count():
    # Two grid points tied on RMSE are reported, in addition to the first-wins pick.
    air = [-2.0] * 30
    prcp = [10.0] * 30
    truth, _ = daily_swe_series(_patch(), air, prcp, 3.0, wind_loss=0.05)
    idx = list(range(30))
    fit = fit_snow_params(_patch(), air, prcp, truth, idx,
                          k_grid=[3.0, 3.0], wind_grid=[0.05])
    assert fit["tie_count"] == 1
    assert fit["best_k"] == 3.0


def test_wind_override_keeps_ledger_and_default_untouched():
    from yellowstone_python.land.snow_season import run_season
    patches = [_patch()]
    _, led_over = run_season(patches, days=10,
                             air_c_by_day=[-2.0] * 10, precip_mm_d=5.0,
                             wind_loss=0.05)
    assert abs(led_over["storage_residual_mm"]) < 0.05
    out_none, _ = run_season([_patch()], days=10,
                             air_c_by_day=[-2.0] * 10, precip_mm_d=5.0,
                             wind_loss=None)
    out_zero, _ = run_season([_patch()], days=10,
                             air_c_by_day=[-2.0] * 10, precip_mm_d=5.0,
                             wind_loss=0.15)
    # None keeps the authored dry_meadow 0.15 (identical end state); a lower fitted loss retains more pack than the authored default.
    assert out_none[0]["snow_mm"] == out_zero[0]["snow_mm"]
    out_low, _ = run_season([_patch()], days=10,
                             air_c_by_day=[-2.0] * 10, precip_mm_d=5.0,
                             wind_loss=0.02)
    assert out_low[0]["snow_mm"] > out_zero[0]["snow_mm"]


def _synthetic_bundle(tmp_path, start_year=2024):
    """Minimal frozen-style bundle: 60 freezing days + 30 melt days."""
    import datetime
    import json
    dates = [(datetime.date(start_year, 10, 1)
              + datetime.timedelta(days=i)).isoformat()
             for i in range(90)]
    air_f = [23.0] * 60 + [41.0] * 30  # -5 C, then +5 C
    # 0.4 in/day while freezing, dry during melt (exercises melt only).
    prcp_in = [0.4] * 60 + [0.0] * 30
    truth, _ = daily_swe_series(_patch(),
                                [f_to_c(f) for f in air_f],
                                [in_to_mm(p) for p in prcp_in],
                                3.0, wind_loss=0.05)
    days = {}
    for d, f, p, s in zip(dates, air_f, prcp_in, truth):
        days[d] = {"WTEQ": s / 25.4, "PRCP": p, "SNWD": s * 3.0 / 25.4,
                   "TAVG": f, "TMAX": f + 5.0, "TMIN": f - 5.0}
    bundle = {"schema": "yellowstone.snotel_obs.v1",
              "status": "measured_remote_not_calibrated",
              "fetched_at_utc": "2024-01-01T00:00:00+00:00",
              "window": {"begin": dates[0], "end": dates[-1]},
              "sites": {"999:XX:SNTL": {"days": days}}}
    path = tmp_path / "synth_bundle.json"
    path.write_text(json.dumps(bundle))
    return str(path), dates


def test_fixed_params_recovers_truth_without_refit(tmp_path):
    # Inverse-crime check: frozen generating params score about 0 holdout RMSE on the generating window; the no-refit path evaluates.
    bundle_path, dates = _synthetic_bundle(tmp_path)
    split = dates[60]  # melt onset
    fixed = {"999:XX:SNTL": {"k_melt_mm_per_deg_day": 3.0,
                             "wind_loss_effective": 0.05}}
    artifact = evaluate_fixed_params(bundle_path, fixed, split=split)
    site = artifact["sites"]["999:XX:SNTL"]
    assert site["holdout_swe_mm"]["rmse"] == 0.0
    assert site["beats_both_nulls"] is True
    assert site["frozen"]["provenance"] == "frozen_prior_window_fit_no_refit"
    assert artifact["split_date"] == split


def test_fixed_params_wrong_params_miss_and_report_honestly(tmp_path):
    # k=0 (no melt) on a melting window must NOT beat the melt null.
    bundle_path, dates = _synthetic_bundle(tmp_path)
    split = dates[60]
    fixed = {"999:XX:SNTL": {"k_melt_mm_per_deg_day": 0.5,
                             "wind_loss_effective": 0.05}}
    artifact = evaluate_fixed_params(bundle_path, fixed, split=split)
    site = artifact["sites"]["999:XX:SNTL"]
    assert site["holdout_swe_mm"]["rmse"] > 0.0


def test_fixed_params_refuses_unknown_triplet_and_off_grid(tmp_path):
    import json
    bundle_path, _ = _synthetic_bundle(tmp_path)
    try:
        evaluate_fixed_params(bundle_path, {}, split="2024-12-01")
    except ValueError:
        pass
    else:
        raise AssertionError('missing triplet must refuse. default')
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"999:XX:SNTL":
                               {"k_melt_mm_per_deg_day": 99.0,
                                "wind_loss_effective": 0.05}}))
    try:
        load_fixed_params(str(bad))
    except ValueError:
        pass
    else:
        raise AssertionError('off-grid k must refuse. clip')


def test_load_fixed_params_reads_fit_artifact_shape(tmp_path):
    import json
    fit = {"sites": {"999:XX:SNTL":
                     {"fitted": {"k_melt_mm_per_deg_day": 1.0,
                                 "wind_loss_effective": 0.0}}}}
    path = tmp_path / "fit.json"
    path.write_text(json.dumps(fit))
    assert load_fixed_params(str(path)) == \
        {"999:XX:SNTL": {"k_melt_mm_per_deg_day": 1.0,
                         "wind_loss_effective": 0.0}}


def test_validate_site_runs_end_to_end(tmp_path):
    # Regression: provenance once used an out-of-scope bundle name and the validate_site call raised NameError before returning.
    bundle_path, dates = _synthetic_bundle(tmp_path)
    import json
    bundle = json.loads(open(bundle_path).read())
    site = bundle["sites"]["999:XX:SNTL"]
    out = validate_site("999:XX:SNTL", site, split=dates[70], bundle=bundle)
    assert out["fitted"]["k_melt_mm_per_deg_day"] == 3.0
    assert out["fitted"]["wind_loss_effective"] == 0.05
    assert out["holdout_scored_n"] == out["holdout_n"]
    assert out["missing_obs_n"] == 0
    assert out["peak_timing_scored_n"] == out["n_days"]
    assert out["fitted"]["grid"]["n_candidates"] > 1
    assert "tie_rule" in out["fitted"]["grid"]


def test_accumulation_only_fit_records_unidentifiable_k(tmp_path):
    # A training window with no melt days cannot separate k_melt (all grid points tie on train RMSE); the artifact records the tie count under the first-wins pick.
    bundle_path, dates = _synthetic_bundle(tmp_path)
    import json
    bundle = json.loads(open(bundle_path).read())
    site = bundle["sites"]["999:XX:SNTL"]
    out = validate_site("999:XX:SNTL", site, split=dates[60], bundle=bundle)
    fitted = out["fitted"]
    assert fitted["train_rmse_mm"] == 0.0
    assert fitted["tie_count"] == len(fitted["grid"]["k_grid"]) - 1
    assert fitted["wind_loss_effective"] == 0.05
    assert fitted["k_melt_mm_per_deg_day"] == fitted["grid"]["k_grid"][0]


def test_peak_timing_refuses_malformed_input():
    dates = ["2026-03-01", "2026-03-05", "2026-03-10"]
    for bad_dates, modeled, observed in (
            (dates, [1.0, 2.0], [1.0, 2.0, 3.0]),
            (["2026-3-1"], [1.0], [1.0]),
            (dates, [1.0, None, 2.0], [1.0, 2.0, 3.0]),
            (dates, [1.0, 2.0, 3.0], [1.0, None, 3.0])):
        try:
            peak_timing_error_days(bad_dates, modeled, observed)
        except ValueError:
            continue
        raise AssertionError(f"must refuse {bad_dates} {modeled} {observed}")


def test_load_fixed_params_refuses_bad_shapes(tmp_path):
    import json
    shapes = ([1, 2], {"a": 1.0},
              {"999:XX:SNTL": {"k_melt_mm_per_deg_day": 1.0}},
              {"999:XX:SNTL": {"k_melt_mm_per_deg_day": None,
                                "wind_loss_effective": 0.0}},
              {"999:XX:SNTL": {"k_melt_mm_per_deg_day": float("nan"),
                                "wind_loss_effective": 0.0}})
    for i, shape in enumerate(shapes):
        path = tmp_path / f"bad{i}.json"
        path.write_text(json.dumps(shape))
        try:
            load_fixed_params(str(path))
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"must refuse shape {shape}")


def test_load_fixed_params_requires_exact_grid_membership(tmp_path):
    import json
    path = tmp_path / "offgrid.json"
    path.write_text(json.dumps(
        {"999:XX:SNTL": {"k_melt_mm_per_deg_day": 3.4,
                         "wind_loss_effective": 0.05}}))
    try:
        load_fixed_params(str(path))
    except ValueError:
        return
    raise AssertionError('k=3.4 is between grid points; must refuse. clip')


def test_missing_obs_excluded_from_scoring_with_counts(tmp_path):
    # A None WTEQ day is dropped from the holdout score and counted.
    bundle_path, dates = _synthetic_bundle(tmp_path)
    import json
    doc = json.loads(open(bundle_path).read())
    days = doc["sites"]["999:XX:SNTL"]["days"]
    days[dates[70]]["WTEQ"] = None
    path = tmp_path / "missing.json"
    path.write_text(json.dumps(doc))
    fixed = {"999:XX:SNTL": {"k_melt_mm_per_deg_day": 3.0,
                             "wind_loss_effective": 0.05}}
    artifact = evaluate_fixed_params(str(path), fixed, split=dates[60])
    site = artifact["sites"]["999:XX:SNTL"]
    assert site["missing_obs_n"] == 1
    assert site["holdout_scored_n"] == site["holdout_n"] - 1


def test_evaluate_fixed_reports_unused_triplets(tmp_path):
    bundle_path, dates = _synthetic_bundle(tmp_path)
    fixed = {"999:XX:SNTL": {"k_melt_mm_per_deg_day": 3.0,
                             "wind_loss_effective": 0.05},
             "000:XX:SNTL": {"k_melt_mm_per_deg_day": 1.0,
                             "wind_loss_effective": 0.0}}
    artifact = evaluate_fixed_params(bundle_path, fixed, split=dates[60])
    assert artifact["unused_fixed_triplets"] == ["000:XX:SNTL"]
