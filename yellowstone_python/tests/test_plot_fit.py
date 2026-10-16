"""Tests for tools/plot_fit.py (synthetic/offline, Pillow only)."""

import json
import sys
from pathlib import Path

import pytest

from tools.plot_fit import render

TOOL = Path(__file__).resolve().parents[1] / "tools" / "plot_fit.py"
LIVE = Path(__file__).resolve().parents[1] / "derived"


def _reach(top10=True):
    doc = {"schema": "yellowstone.reach_heat_fit.v1",
           "status": "fitted_not_validated_single_window",
           "fetched_at_utc": "2026-10-10T00:00:00+00:00",
           "champion": {"q_lat": 3.5, "t_lat": 30.0, "c_mult": 1.0,
                        "train_rmse": 0.5, "holdout_rmse": 0.6,
                        "budget_ok": True},
           "null_models": [{"name": "upstream_persistence",
                            "holdout_rmse": 6.9}],
           "measured_lag": {"lag_s": 900.0, "peak_correlation": 0.96}}
    if top10:
        doc["top10_train"] = [{"q_lat": 3.5, "t_lat": 30.0, "c_mult": 1.0,
                               "train_rmse": 0.5, "holdout_rmse": 0.6}]
    return doc


def _write(tmp_path, name, doc):
    p = tmp_path / name
    p.write_text(json.dumps(doc))
    return p


def test_manifest_lists_all_figures(tmp_path):
    made = render(_write(tmp_path, "fit.json", _reach()), tmp_path / "out")
    assert len(made) == 2
    for p in made:
        assert p.exists() and p.stat().st_size > 10_000


def test_reach_heat_grid_figure_present(tmp_path):
    doc = _reach()
    doc["grids"] = {"q_lat": [1, 2, 3, 4, 5, 6, 7],
                    "t_lat": [10, 15, 20, 25, 30, 35, 40],
                    "c_mult": [1.0]}
    doc["top10_train"].append({"q_lat": 2, "t_lat": 20, "c_mult": 1.0,
                                "train_rmse": 1.1, "holdout_rmse": 1.2})
    doc["champion"]["budget_totals"] = {
        "advection_in": 100.0, "advection_out": -90.0,
        "surface_flux": -10.0, "heat_relative_residual": 2.28e-06}
    made = render(_write(tmp_path, "fit.json", doc), tmp_path / "out")
    names = {p.name for p in made}
    assert any("grid_holdout_rmse" in n for n in names), names
    assert any("budget_waterfall" in n for n in names), names
    for p in made:
        assert p.stat().st_size > 5_000


def test_reach_heat_renders_without_grids(tmp_path):
    """Fit JSONs that carry only top10_train still render the two core figs."""
    made = render(_write(tmp_path, "noheat.json", _reach()),
                  tmp_path / "out")
    names = {p.name for p in made}
    assert not any("grid_holdout_rmse" in n for n in names), names


def test_snow_peak_timing_figure(tmp_path):
    doc = {"schema": "yellowstone.snow_snotel_fit.v1",
           "status": "fitted_not_validated_single_window",
           "bundle_fetched_at_utc": "2026-10-10T00:00:00+00:00",
           "sites": {"609:MT:SNTL": {
               "holdout_swe_mm": {"rmse": 112.02},
               "null_persistence_rmse_mm": 293.29,
               "null_nomelt_rmse_mm": 471.58,
               "peak_timing_error_days": 48,
               "ledger_residual_mm": -0.001,
               "forcing_gaps": {"tavg_filled": 0}}}}
    made = render(_write(tmp_path, "snow.json", doc), tmp_path / "out")
    names = {p.name for p in made}
    assert any("_peak_timing.png" in n for n in names), names


def test_uq_bands_figure(tmp_path):
    doc = {"schema": "yellowstone.reach_uq.v1",
           "status": "fitted_not_validated_single_window",
           "bundle_fetched_at_utc": "2026-10-10T00:00:00+00:00",
           "holdout_coverage": {"coverage": 0.343, "nominal": 0.9,
                                "n": 100, "n_inside": 34,
                                "mean_width_c": 0.5},
           "members": [{"trajectory": [float(j + i * 0.1)
                                        for j in range(20)]}
                       for i in range(5)]}
    made = render(_write(tmp_path, "uq.json", doc), tmp_path / "out")
    names = {p.name for p in made}
    assert any("_bands.png" in n for n in names), names


def test_title_carries_schema_and_status(tmp_path):
    """new_canvas embeds schema and status in the title line."""
    from tools.plot_fit import new_canvas
    img, _ = new_canvas("test", "footer",
                        {"schema": "yellowstone.reach_heat_fit.v1",
                         "status": "fitted_not_validated_single_window"})
    assert img.size == (1200, 800)


def test_v3e5_refuses_grid_figure(tmp_path):
    with pytest.raises(RuntimeError, match="missing-panel-data"):
        render(_write(tmp_path, "v3e5.json", _reach(top10=False)),
               tmp_path / "out")


def test_footer_carries_status(tmp_path):
    from PIL import Image
    made = render(_write(tmp_path, "fit.json", _reach()), tmp_path / "out")
    im = Image.open(str(made[0]))
    assert im.size == (1200, 800)
    assert im.mode == "RGB"


def test_snow_null_values(tmp_path):
    doc = {"schema": "yellowstone.snow_snotel_fit.v1",
           "status": "fitted_not_validated_single_window",
           "bundle_fetched_at_utc": "2026-10-10T00:00:00+00:00",
           "sites": {"609:MT:SNTL": {
               "holdout_swe_mm": {"rmse": 112.02},
               "null_persistence_rmse_mm": 293.29,
               "null_nomelt_rmse_mm": 471.58,
               "peak_timing_error_days": 48,
               "ledger_residual_mm": -0.001,
               "forcing_gaps": {"tavg_filled": 0}}}}
    made = render(_write(tmp_path, "snow.json", doc), tmp_path / "out")
    assert len(made) >= 1
    for p in made:
        assert p.stat().st_size > 5_000, p


def test_refuses_overwrite_non_png(tmp_path):
    out = tmp_path / "out"
    out.mkdir()
    (out / "fit_top10_rmse.png").write_text("{}")
    with pytest.raises(RuntimeError, match="output-exists-not-png"):
        render(_write(tmp_path, "fit.json", _reach()), out)


def test_unknown_schema(tmp_path):
    with pytest.raises(RuntimeError, match="unknown-schema"):
        render(_write(tmp_path, "x.json", {"schema": "yellowstone.nope.v1"}),
               tmp_path / "out")


def test_live_artifacts_render(tmp_path):
    for name in ("reach_heat_fit_v300k.json",
                 "snow_degree_day_fit.json",
                 "aquatic_intervention.json",
                 "reach_ensemble_uq_v300k.json"):
        made = render(LIVE / name, tmp_path / "out")
        assert made, name
        for p in made:
            assert p.stat().st_size > 10_000, p


def test_missing_champion_panel_data(tmp_path):
    doc = _reach()
    del doc["champion"]
    with pytest.raises(RuntimeError, match="missing-panel-data"):
        render(_write(tmp_path, "nochamp.json", doc), tmp_path / "out")
