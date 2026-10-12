"""Diagnostic PNGs from fit artifacts (Pillow only — no matplotlib).

Every figure carries the source artifact's status + timestamp as footer text
so figures never circulate unlabeled. Panels render stored summaries only;
nothing is interpolated or invented (reach_uq stores no trajectories and
reach_heat stores no per-grid holdouts, so those panels show the stored
top-10 / band summaries). See tooling-spec-plot-fit.md.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image, ImageDraw

W, H = 1200, 800
TITLE_H = 70
FOOTER_H = 60
MARGIN = 60

COLORS = [(70, 130, 180), (255, 140, 0), (60, 170, 80), (150, 150, 150),
          (180, 80, 160), (200, 60, 60)]


def new_canvas(title: str, footer: str):
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, W, TITLE_H], fill=(240, 240, 240))
    draw.text((MARGIN, 20), title[:110], fill="black")
    draw.text((MARGIN, H - FOOTER_H + 10), footer[:150], fill=(80, 80, 80))
    return img, draw


def bar_groups(draw, groups, top, bottom, annotate=()):
    """groups: [(group_label, [(series_label, value), ...])], each group
    scaled independently; values printed. Returns y cursor."""
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
                           _footer(doc))
    groups = [(f"q{q['q_lat']} t{q['t_lat']} c{q['c_mult']}",
               [("train", q["train_rmse"]), ("holdout", q["holdout_rmse"])])
              for q in top10]
    bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 60,
               annotate=[f"champion holdout_rmse="
                         f"{champion['holdout_rmse']:.4f}"])
    made.append(_save(img, out_dir / f"{stem}_top10_rmse.png"))
    img, draw = new_canvas(f"{stem} champion vs nulls", _footer(doc))
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
    return made


def fig_snow(doc: dict, out_dir: Path, stem: str) -> list:
    made = []
    for triplet, site in doc.get("sites", {}).items():
        img, draw = new_canvas(f"{stem} {triplet} holdout vs nulls",
                               _footer(doc))
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
    return made


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
                           _footer(doc))
    bar_groups(draw,
               [("coverage", [("inside/n", cov.get("coverage", 0.0))]),
                ("nominal", [("level", cov.get("nominal", 0.9))])],
               TITLE_H + 10, H - FOOTER_H - 120,
               annotate=[f"n={cov.get('n')} n_inside={cov.get('n_inside')} "
                         f"mean_width_c={cov.get('mean_width_c')}",
                         f"bands={doc.get('bands', {})}"])
    made.append(_save(img, out_dir / f"{stem}_coverage.png"))
    oat = doc.get("fit_oat", {}).get("ranking", [])
    if oat:
        img, draw = new_canvas(f"{stem} OAT ranking", _footer(doc))
        groups = [(r.get("knob", "?"),
                   [("holdout_rmse", r.get("holdout_rmse", 0.0))])
                  for r in oat[:10]]
        bar_groups(draw, groups, TITLE_H + 10, H - FOOTER_H - 40)
        made.append(_save(img, out_dir / f"{stem}_oat_ranking.png"))
    return made


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
