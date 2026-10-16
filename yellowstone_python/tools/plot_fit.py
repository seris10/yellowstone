"""Diagnostic PNGs from fit artifacts (Pillow only)."""

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw

W, H = 1200, 800
TITLE_H = 70
FOOTER_H = 60
MARGIN = 60

COLORS = [(70, 130, 180), (255, 140, 0), (60, 170, 80), (150, 150, 150),
          (180, 80, 160), (200, 60, 60)]


def new_canvas(title: str, footer: str, doc: dict | None = None):
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, TITLE_H], fill=(240, 240, 240))
    if doc is not None:
        tag = f"  schema={doc.get('schema')} status={doc.get('status')}"
        title = title + tag
    draw.text((MARGIN, 20), title[:160], fill="black")
    draw.text((MARGIN, H - FOOTER_H + 10), footer[:150], fill=(80, 80, 80))
    return img, draw


def bar_groups(draw, groups, top, bottom, annotate=()):
    """Draw grouped series with independent axis scales."""
    area_w = W - 2 * MARGIN
    n = len(groups)
    row_h = (bottom - top) // max(n, 1)
    for i, (glabel, series) in enumerate(groups):
        y0 = top + i * row_h
        draw.text((MARGIN, y0 + 4), glabel[:34], fill="black")
        mx = max(abs(v) for _, v in series) or 1.0
        bx = MARGIN + 330
        bw = area_w - 340
        for j, (slabel, v) in enumerate(series):
            by = y0 + 4 + j * 16
            w = int(abs(v) / mx * bw)
            draw.rectangle([bx, by, bx + w, by + 12],
                           fill=COLORS[j % len(COLORS)])
            draw.text((bx + w + 6, by - 2),
                      f"{slabel}={v:.4g}", fill="black")
    y = top + n * row_h + 8
    for line in annotate:
        draw.text((MARGIN, y), line[:120], fill=(60, 60, 60))
        y += 20
    return y


def _save(img, path: Path) -> Path:
    if path.exists():
        head = path.read_bytes()[:8]
        if head != b"\x89PNG\r\n\x1a\n":
            raise RuntimeError(f"output-exists-not-png: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    img.save(str(tmp), format="PNG")
    tmp.replace(path)
    return path


def _footer(doc: dict) -> str:
    ts = doc.get("fetched_at_utc") or doc.get("bundle_fetched_at_utc") or "?"
    return f"status={doc.get('status')} ts={ts} plot=Pillow"


def fig_reach_heat(doc: dict, out_dir: Path, stem: str) -> list:
    made = []
    top10 = doc.get("top10_train")
    if top10 is None:
        raise RuntimeError("missing-panel-data: top10_train for grid figure")
    champion = doc.get("champion") or {}
    if "holdout_rmse" not in champion:
        raise RuntimeError("missing-panel-data: champion.holdout_rmse")
    img, draw = new_canvas(f"{stem} top10 train/holdout RMSE",
                           _footer(doc), doc)
    groups = [(f"q{q['q_lat']} t{q['t_lat']} c{q['c_mult']}",
               [("train", q["train_rmse"]), ("holdout", q["holdout_rmse"])])
              for q in top10]
    bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 60,
               annotate=[f"champion holdout_rmse="
                         f"{champion['holdout_rmse']:.4f}"])
    made.append(_save(img, out_dir / f"{stem}_top10_rmse.png"))
    img, draw = new_canvas(f"{stem} champion vs nulls", _footer(doc), doc)
    nulls = [(m["name"], [("holdout", m["holdout_rmse"])])
             for m in doc.get("null_models", [])]
    groups = [("champion", [("holdout",
                             champion["holdout_rmse"])])] + nulls
    lag = doc.get("measured_lag", {})
    bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 60,
               annotate=[f"lag_s={lag.get('lag_s')} "
                         f"peak_corr={lag.get('peak_correlation')} "
                         f"budget_ok={champion.get('budget_ok')}"])
    made.append(_save(img, out_dir / f"{stem}_champion_vs_nulls.png"))
    grids = doc.get("grids")
    if grids and "q_lat" in grids and "t_lat" in grids:
        made.append(_save(fig_grid(doc, stem), out_dir /
                          f"{stem}_grid_holdout_rmse.png"))
    budget = (champion or {}).get("budget_totals")
    if isinstance(budget, dict) and budget:
        made.append(_save(fig_budget_waterfall(doc, stem), out_dir /
                          f"{stem}_budget_waterfall.png"))
    return made


def fig_grid(doc: dict, stem: str):
    """Heat strip of holdout RMSE over q_lat x t_lat at champion c_mult."""
    grids = doc["grids"]
    champion = doc["champion"]
    qs = list(grids["q_lat"])
    ts = list(grids["t_lat"])
    c_target = champion.get("c_mult")
    top10 = doc.get("top10_train", [])
    rmse = {(q["q_lat"], q["t_lat"]): q["holdout_rmse"]
            for q in top10 if q.get("c_mult") == c_target}
    img, draw = new_canvas(f"{stem} grid_holdout_rmse",
                           _footer(doc), doc)
    vals = [v for v in rmse.values() if v is not None]
    vmin = min(vals) if vals else 0.0
    vmax = max(vals) if vals else 1.0
    span = max(vmax - vmin, 1e-9)
    cell_w = max(40, (W - 2 * MARGIN) // max(len(qs), 1))
    cell_h = max(40, (H - TITLE_H - FOOTER_H - 60) // max(len(ts), 1))
    for i, t in enumerate(ts):
        for j, q in enumerate(qs):
            v = rmse.get((q, t))
            if v is None:
                color = (220, 220, 220)
            else:
                f = (v - vmin) / span
                color = (int(80 + 170 * f), int(170 * (1 - f)) + 40,
                         int(50 + 60 * (1 - f)))
            x0 = MARGIN + j * cell_w
            y0 = TITLE_H + 20 + i * cell_h
            draw.rectangle([x0, y0, x0 + cell_w - 2, y0 + cell_h - 2],
                           fill=color)
            if v is not None:
                draw.text((x0 + 4, y0 + 4), f"{v:.3f}", fill="white")
    cq = champion.get("q_lat")
    ct = champion.get("t_lat")
    if cq in qs and ct in ts:
        jm = qs.index(cq)
        im = ts.index(ct)
        x0 = MARGIN + jm * cell_w
        y0 = TITLE_H + 20 + im * cell_h
        draw.rectangle([x0, y0, x0 + cell_w - 2, y0 + cell_h - 2],
                       outline="white", width=3)
    legend_y = H - FOOTER_H - 30
    draw.text((MARGIN, legend_y),
              f"q_lat on columns, t_lat on rows, c_mult={c_target}; "
              f"holdout_rmse range [{vmin:.3f}, {vmax:.3f}]",
              fill=(60, 60, 60))
    return img


def fig_budget_waterfall(doc: dict, stem: str):
    """Bar chart of champion.budget_totals keyed in J."""
    champion = doc["champion"]
    budget = champion["budget_totals"]
    img, draw = new_canvas(f"{stem} budget_waterfall",
                           _footer(doc), doc)
    items = sorted(budget.items(),
                   key=lambda kv: -abs(float(kv[1])))
    series = [("J", float(v)) for _, v in items]
    groups = [(label, [series[i]]) for i, (label, _) in enumerate(items)]
    annotate = []
    hrr = champion.get("heat_relative_residual")
    if hrr is not None:
        annotate.append(f"heat_relative_residual={hrr:.3e}")
    bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 60,
               annotate=annotate)
    return img


def fig_snow(doc: dict, out_dir: Path, stem: str) -> list:
    made = []
    for triplet, site in doc.get("sites", {}).items():
        img, draw = new_canvas(f"{stem} {triplet} holdout vs nulls",
                               _footer(doc), doc)
        hold = site.get("holdout_swe_mm", {})
        groups = [("holdout", [("rmse", hold.get("rmse", 0.0))]),
                  ("null_persistence",
                   [("rmse", site.get("null_persistence_rmse_mm", 0.0))]),
                  ("null_nomelt",
                   [("rmse", site.get("null_nomelt_rmse_mm", 0.0))])]
        bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 100,
                   annotate=[
                       f"peak_timing_error_days="
                       f"{site.get('peak_timing_error_days')}",
                       f"ledger_residual_mm={site.get('ledger_residual_mm')}",
                       f"forcing_gaps={site.get('forcing_gaps')}"])
        safe = triplet.replace(":", "_")
        made.append(_save(img, out_dir / f"{stem}_{safe}_nulls.png"))
        made.append(_save(fig_peak_timing(doc, triplet, site, stem),
                          out_dir / f"{stem}_{safe}_peak_timing.png"))
    return made


def fig_peak_timing(doc: dict, triplet: str, site: dict, stem: str):
    """Per-site peak timing figure with ledger residual and gap annotations."""
    img, draw = new_canvas(f"{stem} {triplet} peak_timing",
                           _footer(doc), doc)
    pte = site.get("peak_timing_error_days")
    try:
        value = float(pte) if pte is not None else 0.0
    except (TypeError, ValueError):
        value = 0.0
    groups = [("peak_timing_error_days", [("days", value)])]
    annotate = [
        f"ledger_residual_mm={site.get('ledger_residual_mm')}",
        f"forcing_gaps.tavg_filled="
        f"{(site.get('forcing_gaps') or {}).get('tavg_filled')}"]
    bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 60,
               annotate=annotate)
    return img


def fig_aquatic(doc: dict, out_dir: Path, stem: str) -> list:
    img, draw = new_canvas(f"{stem} control vs pulse", _footer(doc))
    ctrl, pulse = doc.get("control", {}), doc.get("pulse", {})
    fields = [k for k in ctrl if k in pulse and
              isinstance(ctrl[k], (int, float))]
    groups = [(f, [("control", ctrl[f]), ("pulse", pulse[f])]) for f in fields]
    bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 80,
               annotate=[f"refuge_shift_m={doc.get('refuge_shift_m')} "
                         f"emergence_change={doc.get('emergence_change')} "
                         f"dipper_intake_change="
                         f"{doc.get('dipper_intake_change')}",
                         str(doc.get("landscape_window", ""))[:120]])
    return [_save(img, out_dir / f"{stem}_control_vs_pulse.png")]


def fig_uq(doc: dict, out_dir: Path, stem: str) -> list:
    made = []
    cov = doc.get("holdout_coverage", {})
    img, draw = new_canvas(f"{stem} holdout coverage vs nominal",
                           _footer(doc), doc)
    bar_groups(draw,
               [("coverage", [("inside/n", cov.get("coverage", 0.0))]),
                ("nominal", [("level", cov.get("nominal", 0.9))])],
               TITLE_H + 10, H - FOOTER_H - 120,
               annotate=[f"n={cov.get('n')} n_inside={cov.get('n_inside')} "
                         f"mean_width_c={cov.get('mean_width_c')}",
                         f"bands={doc.get('bands', {})}"])
    made.append(_save(img, out_dir / f"{stem}_coverage.png"))
    bands = _bands_source(doc)
    if bands is not None:
        made.append(_save(fig_bands(doc, bands, stem),
                          out_dir / f"{stem}_bands.png"))
    oat = doc.get("fit_oat", {}).get("ranking", [])
    if oat:
        img, draw = new_canvas(f"{stem} OAT ranking", _footer(doc), doc)
        groups = [(r.get("knob", "?"),
                   [("holdout_rmse", r.get("holdout_rmse", 0.0))])
                  for r in oat[:10]]
        bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 40)
        made.append(_save(img, out_dir / f"{stem}_oat_ranking.png"))
    return made


def _bands_source(doc: dict):
    """Return (lo, mid, hi) trajectories from members or bands.quantiles."""
    members = doc.get("members")
    if isinstance(members, list) and len(members) >= 3:
        rows = []
        for m in members:
            tr = m.get("trajectory") or m.get("modeled_c")
            if isinstance(tr, list) and tr:
                rows.append([float(v) for v in tr])
        if len(rows) >= 3:
            n = min(len(r) for r in rows)
            cols = list(zip(*[r[:n] for r in rows]))
            lo = [sorted(c)[int(0.05 * (len(c) - 1))] for c in cols]
            mid = [sorted(c)[len(c) // 2] for c in cols]
            hi = [sorted(c)[int(0.95 * (len(c) - 1))] for c in cols]
            return (lo, mid, hi)
    quantiles = (doc.get("bands") or {}).get("quantiles")
    if isinstance(quantiles, dict):
        lo = quantiles.get("0.05") or quantiles.get("p05")
        mid = quantiles.get("0.5") or quantiles.get("median")
        hi = quantiles.get("0.95") or quantiles.get("p95")
        if (isinstance(lo, list) and isinstance(mid, list)
                and isinstance(hi, list) and len(lo) == len(mid) == len(hi)):
            return (lo, mid, hi)
    return None


def fig_bands(doc: dict, bands: tuple, stem: str):
    """Ribbon of median plus 0.05/0.95 band."""
    lo, mid, hi = bands
    img, draw = new_canvas(f"{stem} bands", _footer(doc), doc)
    plot_x0 = MARGIN
    plot_y0 = TITLE_H + 20
    plot_x1 = W - MARGIN
    plot_y1 = H - FOOTER_H - 50
    width = plot_x1 - plot_x0
    height = plot_y1 - plot_y0
    n = len(mid)
    if n < 2:
        return img
    vmin = min(min(lo), min(mid), min(hi))
    vmax = max(max(lo), max(mid), max(hi))
    span = max(vmax - vmin, 1e-9)

    def px(i):
        return plot_x0 + int(width * i / (n - 1))

    def py(v):
        return plot_y1 - int(height * (v - vmin) / span)

    ribbon = [(px(i), py(hi[i])) for i in range(n)] + \
             [(px(i), py(lo[i])) for i in range(n - 1, -1, -1)]
    draw.polygon(ribbon, fill=(180, 200, 230))
    for i in range(n - 1):
        draw.line([(px(i), py(mid[i])), (px(i + 1), py(mid[i + 1]))],
                  fill=(60, 100, 170), width=2)
    cov = doc.get("holdout_coverage", {})
    coverage = cov.get("coverage")
    nominal = cov.get("nominal", 0.9)
    note = (f"coverage {coverage:.3f} vs nominal {nominal}"
            if coverage is not None else "coverage: unavailable")
    draw.text((plot_x0, plot_y1 + 10), note, fill=(80, 80, 80))
    return img


RENDERERS = {
    "yellowstone.reach_heat_fit.v1": fig_reach_heat,
    "yellowstone.snow_snotel_fit.v1": fig_snow,
    "yellowstone.aquatic_intervention.v1": fig_aquatic,
    "yellowstone.reach_uq.v1": fig_uq,
}


def render(artifact: Path, out_dir: Path, kind: str = "auto") -> list:
    doc = json.loads(artifact.read_text())
    schema = doc.get("schema")
    if kind == "auto":
        kind = schema
    renderer = RENDERERS.get(kind)
    if renderer is None:
        raise RuntimeError(f"unknown-schema: {schema!r}")
    return renderer(doc, out_dir, artifact.stem)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--type", default="auto",
                        choices=("auto", "reach_heat", "snow_snotel",
                                 "aquatic_intervention", "reach_uq"))
    args = parser.parse_args()
    names = {"reach_heat": "yellowstone.reach_heat_fit.v1",
             "snow_snotel": "yellowstone.snow_snotel_fit.v1",
             "aquatic_intervention": "yellowstone.aquatic_intervention.v1",
             "reach_uq": "yellowstone.reach_uq.v1"}
    kind = names.get(args.type, args.type)
    try:
        made = render(args.artifact, args.out_dir, kind)
    except (OSError, ValueError, RuntimeError) as exc:
        print(exc)
        return 1
    for p in made:
        print(f"{p.name}: {p.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
