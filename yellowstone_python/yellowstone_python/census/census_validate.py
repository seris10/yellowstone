"""Blind validation for the canopy census."""
from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

from yellowstone_python.common.io import write_json_atomic

from yellowstone_python.common.io import sha256_file as _sha

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.common.checks import finite, positive, positive_int
from yellowstone_python.common.io import load_json

PKG = Path(__file__).resolve().parents[2]
VDIR = PKG / "data" / "census_validation"
DETAIL = str(default_world_root() / "references/midway_orthophoto_detail.jpg")




def _load(p: Path):
    return json.loads(p.read_text())


def _save(p: Path, obj) -> None:
    write_json_atomic(p, obj, indent=1)


def cmd_freeze(args) -> int:
    if VDIR.exists():
        raise SystemExit("validation/ already frozen; remove it to start over.")
    census_src = Path(args.census)
    census = _load(census_src)
    VDIR.mkdir(parents=True)
    (VDIR / "census_frozen.json").write_text(census_src.read_text())
    code = sorted((PKG / "yellowstone_python").rglob("*.py"))  # fd-ok
    ch = hashlib.sha256()
    for py in code:
        ch.update(py.read_bytes())
    # Detector params and image metadata hashed into the freeze.
    from yellowstone_python.census.canopy_census import PX_M, DETAIL_HALF
    detector_params = {
        "exg_min": 0.05, "crown_dark_max": 0.55,
        "min_px": 3, "peak_distance_m": 2.0,
        "px_m": PX_M, "detail_half_m": DETAIL_HALF,
    }
    pkg_versions: dict[str, str] = {}
    for mod_name in ("numpy", "scipy", "PIL"):
        try:
            mod = __import__(mod_name)
            pkg_versions[mod_name] = getattr(mod, "__version__", "unknown")
        except ImportError:
            pkg_versions[mod_name] = "unavailable"
    world_path = default_world_root() / "data" / "world.json"
    try:
        world_sha = _sha(world_path)
    except OSError:
        world_sha = "unavailable"
    source_meta = census.get("source", {})
    _save(VDIR / "manifest.json", {
        "census_sha256": _sha(census_src),
        "detail_sha256": _sha(Path(DETAIL)),
        "world_pools_sha256": world_sha,
        "code_sha256": ch.hexdigest(),
        "detector_params": detector_params,
        "package_versions": pkg_versions,
        "source_metadata": source_meta,
        "n_automated": census["n"],
        "status": "frozen_before_review",
    })
    logger.info(f"frozen {census['n']} detections -> {VDIR}")
    return 0


def cmd_sample(args) -> int:
    if args.plots <= 0:
        raise SystemExit("--plots must be > 0")
    if args.cell_px <= 0:
        raise SystemExit("--cell-px must be > 0")
    from PIL import Image
    census = _load(VDIR / "census_frozen.json")
    img = Image.open(DETAIL).convert("RGB")
    W, H = img.size
    # Census source extent is the source for the world window.
    src = census.get("source", {})
    extent = src.get("extent_m", [-640.0, -640.0, 640.0, 640.0])
    x0_m, z0_m, x1_m, z1_m = (float(v) for v in extent)
    ext_w = max(1e-9, x1_m - x0_m)
    ext_h = max(1e-9, z1_m - z0_m)
    cell = args.cell_px
    cols = list(range(0, W, cell))
    rows = list(range(0, H, cell))
    if args.plots > len(cols) * len(rows):
        raise SystemExit(
            f"--plots must be <= frame population ({len(cols) * len(rows)})")
    frame = []
    counts: dict[tuple, int] = {}
    for t in census["trees"]:
        ix = int((t["x"] - x0_m) / ext_w * W)
        iz = int((t["z"] - z0_m) / ext_h * H)
        counts[(iz // cell, ix // cell)] = counts.get((iz // cell, ix // cell), 0) + 1
    for r, y0 in enumerate(rows):
        for c, x0 in enumerate(cols):
            frame.append({"plot_id": f"P{r:02d}{c:02d}", "x0": x0, "y0": y0,
                          "x1": min(W, x0 + cell), "y1": min(H, y0 + cell),
                          "model_count": counts.get((r, c), 0)})
    rng = np.random.default_rng(args.seed)
    idx = sorted(rng.choice(len(frame), size=args.plots, replace=False).tolist())
    sample = [dict(frame[i], reference_count="") for i in idx]
    crops = VDIR / "blind_crops"
    crops.mkdir(exist_ok=True)
    for plot in sample:
        img.crop((plot["x0"], plot["y0"], plot["x1"], plot["y1"])).save(
            crops / f"{plot['plot_id']}.png")
    _save(VDIR / "frame.json", frame)
    _save(VDIR / "sample.json", sample)
    # Freeze tolerances into the sampling plan so evaluate uses the pre-registered set.
    main_tol_px = 6
    tolerances_frozen = [4, main_tol_px, 10]
    _save(VDIR / "sampling_plan.json", {
        "design": "SRSWOR whole-image cells (plots never used for tuning)",
        "population_cells": len(frame), "sample_cells": len(sample),
        "cell_px": cell, "seed": args.seed,
        "image_dims_px": [W, H],
        "extent_m": [x0_m, z0_m, x1_m, z1_m],
        "main_tolerance_px": main_tol_px,
        "tolerances_frozen_px": tolerances_frozen,
        "main_tolerance_basis": (
            "approx one crown radius at 0.625 m/px; fixed before results"),
        "selected": [p["plot_id"] for p in sample]})
    _save(VDIR / "reference_points.json", [])
    logger.info(f"sampled {len(sample)}/{len(frame)} plots -> {crops} (BLIND: no dots)")
    return 0


WEB_PAGE = """<!doctype html><html><head><meta charset=utf-8><title>Blind crown annotation</title>
<style>body{font-family:sans-serif;background:#111;color:#eee;text-align:center}
#im{max-width:92vw;max-height:78vh;cursor:crosshair;border:1px solid #555}
.dot{position:absolute;border-radius:50%;border:1px solid #000;pointer-events:none}
#cursor{position:absolute;border-radius:50%;border:2px solid #fff;pointer-events:none;z-index:5}
#legend{position:fixed;top:8px;right:8px;background:rgba(0,0,0,.85);padding:10px 14px;
 border:1px solid #888;border-radius:8px;font-size:14px;text-align:left;display:none}
#legend div{margin:3px 0}#legend .sw{display:inline-block;width:14px;height:14px;border-radius:50%;margin-right:8px}
#wrap{position:relative;display:inline-block}
button{font-size:16px;margin:6px;padding:6px 18px}</style></head><body>
<h2 id="title"></h2><div id="wrap"><img id="im"><div id="dots"></div></div><br>
<div id="legend"></div>
<button onclick="zoom(1)">1x</button><button onclick="zoom(2)">2x</button><button onclick="zoom(3)">3x</button><button onclick="zoom(4)">4x</button>
<button onclick="undo()">Undo last</button>
<button onclick="clearAll()">Clear plot</button>
<button onclick="next(true)">Accept plot &amp; next</button>
<p>Click EVERY visible crown centre. Yellow dots are yours (no model overlay).
Accept explicitly even when the plot holds zero trees.</p>
<script>
let plots=[], idx=0, pts=[];
const CLASSES=[
 {name:'S', color:'#4dd2ff', px:5, label:'S — small, under ~4 m crown'},
 {name:'M', color:'#ffe93c', px:8, label:'M — medium, ~4-6 m crown'},
 {name:'L', color:'#ff9a2e', px:12, label:'L — large, ~7-10 m crown'},
 {name:'XL', color:'#ff4444', px:18, label:'XL — very large, 10 m+ crown'}];
let cls=1;
function renderLegend(){
  const L=document.getElementById('legend');
  L.style.display='block';
  L.innerHTML='<b>Scroll = size class</b><br>'+CLASSES.map((c,i)=>
    `<div><span class="sw" style="background:${c.color}"></span>${i===cls?'▶ ':''}${c.label}</div>`).join('');
}
let _wheelAcc=0,_wheelLast=0;
document.addEventListener('wheel',e=>{
  if(e.ctrlKey||e.metaKey) return;  // pinch-to-zoom: let the browser have it
  e.preventDefault();
  const now=performance.now();
  if(now-_wheelLast<250){_wheelAcc=0;return;}  // one class step per gesture
  _wheelAcc+=e.deltaY;
  if(Math.abs(_wheelAcc)<30) return;
  cls=(cls+(_wheelAcc>0?1:CLASSES.length-1))%CLASSES.length;
  _wheelAcc=0; _wheelLast=now;
  renderLegend(); moveCursor(e);},{passive:false});
function moveCursor(e){
  let cur=document.getElementById('cursor');
  if(!cur){cur=document.createElement('div');cur.id='cursor';document.getElementById('wrap').appendChild(cur);}
  const rim=document.getElementById('im').getBoundingClientRect();
  const c=CLASSES[cls];
  cur.style.width=cur.style.height='4px';
  cur.style.margin='-2px';
  cur.style.background=c.color;
  cur.style.boxShadow='0 0 0 1px #000';
  cur.style.left=(e.clientX-rim.left)+'px'; cur.style.top=(e.clientY-rim.top)+'px';
}
document.addEventListener('mousemove',moveCursor);
async function load(){plots=await (await fetch('/plots')).json(); show();}
function show(){
  pts=[];
  document.getElementById('title').textContent =
    `Plot ${plots[idx].plot_id} (${idx+1}/${plots.length}) — already accepted: ${plots[idx].done}`;
  const im=document.getElementById('im');
  im.src='/crop/'+plots[idx].plot_id+'?t='+Date.now();
  document.getElementById('dots').innerHTML='';
  im.onload=()=>{zoom(3);};
}
function im_click(e){
  const im=document.getElementById('im');
  const r=im.getBoundingClientRect();
  const fx=im.naturalWidth/r.width, fy=im.naturalHeight/r.height;
  const x=(e.clientX-r.left)*fx, y=(e.clientY-r.top)*fy;
  pts.push([x,y,cls]); draw();
}
function draw(){
  renderLegend();
  const box=document.getElementById('dots');
  box.innerHTML='';
  const im=document.getElementById('im');
  const r=im.getBoundingClientRect();
  const fx=r.width/im.naturalWidth, fy=r.height/im.naturalHeight;
  pts.forEach(p=>{
    const c=CLASSES[p[2]===undefined?1:p[2]];
    const d=document.createElement('div'); d.className='dot';
    d.style.width=d.style.height='4px'; d.style.margin='-2px';
    d.style.background=c.color;
    d.style.left=(p[0]*fx)+'px'; d.style.top=(p[1]*fy)+'px';
    box.appendChild(d);
  });
  document.getElementById('title').textContent += '';
}
function undo(){pts.pop(); draw();}
let _zwrap=null;
function zoom(f){
  const im=document.getElementById('im');
  if(!_zwrap){_zwrap=document.createElement('div');_zwrap.style.overflow='auto';_zwrap.style.maxHeight='78vh';
    im.parentNode.insertBefore(_zwrap,im);_zwrap.appendChild(im);}
  im.style.width=(im.naturalWidth*f)+'px'; im.style.maxWidth='none'; draw();
}
function clearAll(){pts=[]; draw();}
async function next(){
  await fetch('/submit',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({plot_id:plots[idx].plot_id,points:pts})});
  idx++;
  if(idx>=plots.length){document.body.innerHTML='<h1>Done — all plots annotated.</h1>';return;}
  show();
}
document.getElementById('im').addEventListener('click',im_click);
window.addEventListener('resize',draw);
load();
</script></body></html>"""


def cmd_annotate_web(args) -> int:
    """Browser annotator: blind crops, click-to-add, server-side progress."""
    import json as _json
    from http.server import BaseHTTPRequestHandler, HTTPServer
    sample = _load(VDIR / "sample.json")
    refs = _load(VDIR / "reference_points.json")
    done = {r["plot_id"] for r in refs}
    todo = [p for p in sample if p["plot_id"] not in done]
    if not todo:
        logger.info("all plots already annotated")
        return 0
    plots = [{"plot_id": p["plot_id"], "done": False} for p in todo]
    by_id = {p["plot_id"]: p for p in sample}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else _json.dumps(body).encode()
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/":
                return self._send(WEB_PAGE.encode(), "text/html")
            if self.path == "/plots":
                for pl in plots:
                    pl["done"] = pl["plot_id"] in {r["plot_id"] for r in refs}
                return self._send(plots)
            if self.path.startswith("/crop/"):
                pid = self.path.split("/")[2].split("?")[0]
                if pid not in by_id:
                    return self.send_error(404, "unknown plot id")
                crop_path = VDIR / "blind_crops" / f"{pid}.png"
                # Path traversal guard: resolve and verify under blind_crops.
                resolved = crop_path.resolve()
                blind_dir = (VDIR / "blind_crops").resolve()
                try:
                    resolved.relative_to(blind_dir)
                except ValueError:
                    return self.send_error(404, "invalid crop path")
                return self._send(resolved.read_bytes(), "image/png")
            self.send_error(404)

        def do_POST(self):
            if self.path != "/submit":
                return self.send_error(404)
            n = int(self.headers.get("Content-Length", 0))
            payload = _json.loads(self.rfile.read(n) or b"{}")
            pid = payload.get("plot_id")
            if not pid or pid not in by_id:
                return self.send_error(400, "invalid plot_id")
            plot = by_id[pid]
            nonlocal_refs = [r for r in refs if r["plot_id"] != pid]
            _CL = ["S", "M", "L", "XL"]
            _pts = payload.get("points", [])
            if not isinstance(_pts, list):
                return self.send_error(400, "points must be a list")
            crop_w = int(plot["x1"]) - int(plot["x0"])
            crop_h = int(plot["y1"]) - int(plot["y0"])
            new = []
            for i, pt in enumerate(_pts, 1):
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    return self.send_error(400, f"point {i}: expected [x, y, ...]")
                try:
                    x, y = float(pt[0]), float(pt[1])
                except (TypeError, ValueError):
                    return self.send_error(400, f"point {i}: non-numeric coordinates")
                if not (math.isfinite(x) and math.isfinite(y)):
                    return self.send_error(400, f"point {i}: non-finite coordinates")
                if not (0.0 <= x <= crop_w and 0.0 <= y <= crop_h):
                    return self.send_error(
                        400, f"point {i}: ({x}, {y}) outside crop "
                             f"[0, 0, {crop_w}, {crop_h}]")
                rest = pt[2:]
                c_raw = rest[0] if rest else 1
                try:
                    c = int(c_raw)
                except (TypeError, ValueError):
                    c = 1
                if not (0 <= c < len(_CL)):
                    c = 1  # default to M
                new.append({"reference_id": f"{pid}_R{i:04d}", "plot_id": pid,
                            "pixel_x": round(x + plot["x0"], 1),
                            "pixel_y": round(y + plot["y0"], 1),
                            "size_class": _CL[c]})
            # Record a submission marker even for zero-point plots.
            marker_path = VDIR / "reference_submissions.json"
            try:
                marks = _load(marker_path) if marker_path.exists() else []
            except (OSError, ValueError):
                marks = []
            marks = [m for m in marks if m.get("plot_id") != pid]
            marks.append({"plot_id": pid, "submitted": True, "n": len(new)})
            _save(marker_path, marks)
            refs[:] = nonlocal_refs + new
            for p in sample:
                if p["plot_id"] == pid:
                    p["reference_count"] = len(new)
            _save(VDIR / "reference_points.json", refs)
            _save(VDIR / "sample.json", sample)
            logger.info(f"{pid}: {len(new)} crowns")
            return self._send({"ok": True, "n": len(new)})

    srv = HTTPServer(("127.0.0.1", 8766), H)
    import webbrowser
    webbrowser.open("http://127.0.0.1:8766/")
    logger.info("annotator at http://127.0.0.1:8766/ (Ctrl-C when the page says done)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


def cmd_annotate(_args) -> int:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    sample = _load(VDIR / "sample.json")
    refs = _load(VDIR / "reference_points.json")
    have = {r["plot_id"] for r in refs}
    crops = VDIR / "blind_crops"
    for plot in sample:
        if plot["plot_id"] in have or plot["reference_count"] != "":
            continue
        img = plt.imread(crops / f"{plot['plot_id']}.png")
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.imshow(img)
        ax.set_title(f"{plot['plot_id']}: click EVERY crown centre. "
                     "Left=add Right=remove last. Close window when done.")
        pts: list = []

        def on_click(event):
            if event.inaxes != ax or event.xdata is None:
                return
            if event.button == 1:
                pts.append((float(event.xdata), float(event.ydata)))
                ax.plot(event.xdata, event.ydata, "yo", ms=4)
                fig.canvas.draw_idle()
            elif event.button == 3 and pts:
                pts.pop()
                ax.lines.pop()
                fig.canvas.draw_idle()

        fig.canvas.mpl_connect("button_press_event", on_click)
        plt.show()
        n = len([r for r in refs if r["plot_id"] == plot["plot_id"]])
        refs = [r for r in refs if r["plot_id"] != plot["plot_id"]]
        refs.extend({"reference_id": f"{plot['plot_id']}_R{i:04d}",
                     "plot_id": plot["plot_id"],
                     "pixel_x": round(x + plot["x0"], 1),
                     "pixel_y": round(y + plot["y0"], 1)}
                    for i, (x, y) in enumerate(pts, start=n + 1))
        plot["reference_count"] = len(pts)
        _save(VDIR / "reference_points.json", refs)
        _save(VDIR / "sample.json", sample)
        logger.info(f"{plot['plot_id']}: {len(pts)} crowns recorded")
    logger.info("annotation complete")
    return 0


def _hungarian(pred, ref, tol):
    from scipy.optimize import linear_sum_assignment
    from scipy.spatial.distance import cdist
    pred = np.asarray(pred, float).reshape(-1, 2)
    ref = np.asarray(ref, dtype=float).reshape(-1, 2)
    p, r = len(pred), len(ref)
    if p == 0 or r == 0:
        return 0, p, r, []
    d = cdist(pred, ref)
    big = min(p, r) + 1.0
    cost = np.full((p, r + p), big)
    cost[:, :r] = np.where(d <= tol, d / tol, 2 * big)
    rows, cols = linear_sum_assignment(cost)
    ok = cols < r
    dists = [float(d[i, j]) for i, j in zip(rows[ok], cols[ok])
             if d[i, j] <= tol]
    tp = len(dists)
    return tp, p - tp, r - tp, dists


def cmd_evaluate(args) -> int:
    import math
    if not args.tolerances or any(
        not math.isfinite(t) or t <= 0 for t in args.tolerances
    ):
        raise SystemExit("tolerances must be finite and > 0")
    if len(set(args.tolerances)) != len(args.tolerances):
        raise SystemExit("tolerances must be unique")
    from scipy import stats
    census = _load(VDIR / "census_frozen.json")
    sample = _load(VDIR / "sample.json")
    refs = _load(VDIR / "reference_points.json")
    frame = _load(VDIR / "frame.json")
    plan_path = VDIR / "sampling_plan.json"
    plan = _load(plan_path) if plan_path.exists() else {}
    # Main evaluation uses preregistered frozen tolerances; other CLI tolerances are exploratory.
    frozen = plan.get("tolerances_frozen_px")
    user_tol = list(args.tolerances)
    tolerance_basis = plan.get(
        "main_tolerance_basis",
        "approx one crown radius at 0.625 m/px; fixed before results")
    if frozen:
        exploratory = sorted(set(user_tol) - set(frozen))
        if exploratory:
            tolerance_basis = (
                f"{tolerance_basis}; exploratory tolerances this run: "
                f"{exploratory}")
    # Point labels and explicit empty-plot records establish reference submissions.
    submitted_plots = {r["plot_id"] for r in refs}
    plan_zero_marked = set(plan.get("zero_point_plots", []))
    sample_zero_marked = {p["plot_id"] for p in sample
                          if type(p.get("reference_count")) is int and p["reference_count"] == 0}
    submitted_from_marks = set()
    markers_path = VDIR / "reference_submissions.json"
    if markers_path.exists():
        try:
            marks = _load(markers_path)
            submitted_from_marks = {m["plot_id"] for m in marks
                                    if m.get("submitted") is True
                                    and type(m.get("n")) is int and m["n"] == 0}
        except (OSError, ValueError):
            pass
    completed = submitted_plots | plan_zero_marked | sample_zero_marked | submitted_from_marks
    unresolved = [p["plot_id"] for p in sample if p["plot_id"] not in completed]
    if not sample or len(unresolved) == len(sample):
        report = {
            "schema": "yellowstone.naip_blind_evaluation.v1",
            "status": "derived_not_field_validated", "validation_availability": "unavailable",
            "reference_target": "visible crown centers (blind plots)",
            "reason": "No explicit reference point or empty-plot submissions",
            "unresolved_plots": unresolved,
            "main_tolerance_px": plan.get("main_tolerance_px", 6),
            "tolerances_run_px": user_tol, "tolerances_frozen_px": frozen,
            "evaluations": [], "corrected_total": None,
        }
        _save(VDIR / "validation_report.json", report)
        logger.info(json.dumps(report, indent=1))
        return 0
    if unresolved:
        raise SystemExit(f"reference submissions are unresolved: {unresolved}")
    # Pixel mapping anchored to the census source extent and the frozen image dims.
    src = census.get("source", {})
    extent = src.get("extent_m", [-640.0, -640.0, 640.0, 640.0])
    x0_m, z0_m, x1_m, z1_m = (float(v) for v in extent)
    ext_w = max(1e-9, x1_m - x0_m)
    ext_h = max(1e-9, z1_m - z0_m)
    plan_dims = plan.get("image_dims_px", [2048, 2048])
    W, H = int(plan_dims[0]), int(plan_dims[1])
    by_plot: dict[str, list] = {}
    for t in census["trees"]:
        ix = int((t["x"] - x0_m) / ext_w * W)
        iz = int((t["z"] - z0_m) / ext_h * H)
        for p in sample:
            if p["x0"] <= ix < p["x1"] and p["y0"] <= iz < p["y1"]:
                by_plot.setdefault(p["plot_id"], []).append((ix, iz))
    evaluations = []
    for tol in args.tolerances:
        tp = fp = fn = 0
        dists: list[float] = []
        for p in sample:
            pred = by_plot.get(p["plot_id"], [])
            ref = [(r["pixel_x"], r["pixel_y"]) for r in refs
                   if r["plot_id"] == p["plot_id"]]
            a, b, c, dd = _hungarian(pred, ref, tol)
            tp, fp, fn = tp + a, fp + b, fn + c
            dists += dd
        evaluations.append({
            "tolerance_px": tol, "tp": tp, "fp": fp, "fn": fn,
            "precision": round(tp / (tp + fp), 3) if tp + fp else None,
            "recall": round(tp / (tp + fn), 3) if tp + fn else None,
            "f1": round(2 * tp / (2 * tp + fp + fn), 3)
            if 2 * tp + fp + fn else None,
            "matched_rmse_px": round(float(np.sqrt(np.mean(np.square(dists)))), 2)
            if dists else None})
    residuals = []
    for p in sample:
        ref_n = sum(1 for r in refs if r["plot_id"] == p["plot_id"])
        residuals.append(ref_n - len(by_plot.get(p["plot_id"], [])))
    residuals = np.asarray(residuals, float)
    n, N = len(sample), len(frame)
    model_total = sum(f["model_count"] for f in frame)
    correction = N * float(residuals.mean())
    estimate = float(model_total + correction)
    var = N ** 2 * (1 - n / N) * float(residuals.var(ddof=1)) / n if n > 1 else 0.0
    se = math.sqrt(max(0.0, var))
    hw = float(stats.t.ppf(0.975, n - 1)) * se if n > 1 else 0.0
    report = {
        "schema": "yellowstone.naip_blind_evaluation.v1",
        "status": "derived_not_field_validated", "validation_availability": "submitted_hand_labels",
        "reference_target": "visible crown centers (blind plots)",
        "main_tolerance_px": plan.get("main_tolerance_px", 6),
        "main_tolerance_basis": tolerance_basis,
        "tolerances_run_px": user_tol,
        "tolerances_frozen_px": frozen,
        "evaluations": evaluations,
        "corrected_total": {
            "method": "fixed-prediction difference estimator SRSWOR",
            "automated_total": model_total,
            "estimated_total": round(estimate, 1),
            "se": round(se, 1),
            "approx_95_interval": [round(estimate - hw, 1), round(estimate + hw, 1)],
        },
        "limits": ["reference labels can err; interval excludes annotation/scale error",
                   "plots excluded from all detector tuning"],
    }
    _save(VDIR / "validation_report.json", report)
    logger.info(json.dumps(report, indent=1))
    return 0






LIDAR_DENSITY_CLASSES = ("under_600", "600_to_2200", "over_2200")


def lidar_density_class(density_per_ha: float) -> str:
    """Classify visible dominant-crown density per ha using the frozen boundaries."""
    density = finite("density_per_ha", density_per_ha, minimum=0)
    if density < 600:
        return LIDAR_DENSITY_CLASSES[0]
    if density <= 2200:
        return LIDAR_DENSITY_CLASSES[1]
    return LIDAR_DENSITY_CLASSES[2]


def _lidar_json(value, expect: type):
    """Read a JSON path or copy an object of the required type."""
    if isinstance(value, (str, Path)):
        return load_json(value, expect=expect)
    if not isinstance(value, expect):
        raise ValueError(f"value must contain {expect.__name__}")
    return json.loads(json.dumps(value, allow_nan=False))


def _lidar_object_sha(value) -> str:
    """Hash a JSON object with a deterministic representation."""
    data = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _lidar_geometry(extent, dims):
    """Validate the source extent and return metric pixel dimensions."""
    if not isinstance(extent, (list, tuple)) or len(extent) != 4:
        raise ValueError("extent_m must contain [x0, z0, x1, z1]")
    bounds = [finite(f"extent_m[{i}]", value) for i, value in enumerate(extent)]
    width = positive_int("image width", dims[0])
    height = positive_int("image height", dims[1])
    sx = positive("extent width", bounds[2] - bounds[0]) / width
    sz = positive("extent height", bounds[3] - bounds[1]) / height
    return bounds, sx, sz


def _lidar_tree_points(census, bounds):
    """Validate detection coordinates against the source extent."""
    trees = census.get("trees")
    if not isinstance(trees, list):
        raise ValueError("census trees must be a list")
    points = []
    for index, tree in enumerate(trees):
        if not isinstance(tree, dict):
            raise ValueError(f"tree {index} must be an object")
        x = finite(f"tree {index} x", tree.get("x"))
        z = finite(f"tree {index} z", tree.get("z"))
        if not (bounds[0] <= x < bounds[2] and bounds[1] <= z < bounds[3]):
            raise ValueError(f"tree {index} is outside the source extent")
        points.append((x, z))
    return points


def sample_lidar_blind_crops(census, image_path, out_dir, *, extent_m=None,
                           cell_px=128, plots_per_class=3, seed=0,
                           tolerances_m=(2.0, 4.0, 6.0), main_tolerance_m=4.0,
                           source_paths=None, imagery_metadata=None) -> dict:
    """Freeze density-stratified plain imagery crops for visible dominant-crown review."""
    from PIL import Image
    cell_px = positive_int("cell_px", cell_px)
    plots_per_class = positive_int("plots_per_class", plots_per_class)
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)) or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    tolerances = [positive("tolerance_m", value) for value in tolerances_m]
    main = positive("main_tolerance_m", main_tolerance_m)
    if not tolerances or len(set(tolerances)) != len(tolerances) or main not in tolerances:
        raise ValueError("tolerances_m must be unique and include main_tolerance_m")
    doc = _lidar_json(census, dict)
    source = doc.get("source", {})
    if not isinstance(source, dict):
        raise ValueError("census source must be an object")
    with Image.open(image_path) as opened:
        image = opened.convert("RGB")
    bounds, sx, sz = _lidar_geometry(
        extent_m if extent_m is not None else source.get("extent_m"), image.size)
    points = _lidar_tree_points(doc, bounds)
    counts = {}
    for x, z in points:
        cell = (math.floor((z - bounds[1]) / sz) // cell_px,
                math.floor((x - bounds[0]) / sx) // cell_px)
        counts[cell] = counts.get(cell, 0) + 1
    frame = []
    for row, y0 in enumerate(range(0, image.height, cell_px)):
        for col, x0 in enumerate(range(0, image.width, cell_px)):
            x1, y1 = min(image.width, x0 + cell_px), min(image.height, y0 + cell_px)
            area = (x1 - x0) * sx * (y1 - y0) * sz
            count = counts.get((row, col), 0)
            density = count * 10000 / area
            frame.append({"plot_id": f"L{row:04d}{col:04d}",
                          "x0": x0, "y0": y0, "x1": x1, "y1": y1,
                          "area_m2": area, "model_count": count,
                          "selection_density_proxy_per_ha": density,
                          "selection_density_proxy_class": lidar_density_class(density)})
    rng = np.random.default_rng(int(seed))
    selected = []
    strata = {}
    for name in LIDAR_DENSITY_CLASSES:
        eligible = [i for i, plot in enumerate(frame)
                    if plot["selection_density_proxy_class"] == name]
        n = min(plots_per_class, len(eligible))
        selected.extend(rng.choice(eligible, size=n, replace=False).tolist())
        strata[name] = {"population_plots": len(eligible), "selected_plots": n}
    sample = [{key: value for key, value in frame[i].items()
               if key in ("plot_id", "x0", "y0", "x1", "y1", "area_m2")}
              for i in sorted(selected)]
    hashes = {"review_image": _sha(Path(image_path)),
              "validation_module": _sha(Path(__file__)),
              "census_object": _lidar_object_sha(doc)}
    if isinstance(census, (str, Path)):
        hashes["census_file"] = _sha(Path(census))
    for name, path in (source_paths or {}).items():
        if not isinstance(name, str) or not name or name in hashes:
            raise ValueError("source_paths keys must be unique nonempty source names")
        hashes[name] = _sha(Path(path))
    metadata = _lidar_json(imagery_metadata or {}, dict)
    plan = {
        "schema": "yellowstone.lidar_blind_sampling.v1",
        "status": "derived_not_field_validated", "freeze_state": "frozen_before_review",
        "reference_target": "visible dominant crown centers",
        "density_class_quantity": "visible dominant crowns per ha",
        "density_boundaries_per_ha": [600, 2200],
        "density_boundary_rule": "under 600; 600 through 2200 inclusive; over 2200",
        "design": "SRSWOR within detector-density proxy classes",
        "selection_basis": "detector proxy classes select crops; submitted labels define evaluation classes",
        "total_stem_density_status": "unknown",
        "subcanopy_stem_density_status": "unknown",
        "cell_px": cell_px, "seed": int(seed), "plots_per_class": plots_per_class,
        "population_plots": len(frame), "sample_plots": len(sample),
        "selection_proxy_strata": strata,
        "selected": [plot["plot_id"] for plot in sample],
        "extent_m": bounds, "image_dims_px": list(image.size),
        "pixel_size_xz_m": [sx, sz],
        "reference_coordinates": "whole-image pixel_x right and pixel_y down; half-open crop bounds",
        "main_tolerance_m": main, "tolerances_frozen_m": tolerances,
        "source_hashes": hashes, "source_metadata": source,
        "imagery_metadata": metadata,
        "epoch_limitation": "Lidar and review imagery acquisition epochs can differ; crown changes affect matching",
        "model_overlays": False,
    }
    directory = Path(out_dir)
    if directory.exists():
        raise ValueError(f"blind validation directory already exists: {directory}")
    directory.mkdir(parents=True)
    crops = directory / "blind_crops"
    crops.mkdir()
    for plot in sample:
        image.crop((plot["x0"], plot["y0"], plot["x1"], plot["y1"])).save(
            crops / f"{plot['plot_id']}.png")
    for name, value in (("census_frozen.json", doc), ("frame.json", frame),
                        ("sample.json", sample), ("sampling_plan.json", plan),
                        ("reference_points.json", []), ("reference_submissions.json", [])):
        write_json_atomic(directory / name, value)
    frozen = [directory / name for name in
              ("census_frozen.json", "frame.json", "sample.json", "sampling_plan.json")]
    frozen.extend(crops / f"{plot['plot_id']}.png" for plot in sample)
    write_json_atomic(directory / "manifest.json", {
        "schema": "yellowstone.lidar_blind_manifest.v1", "status": "derived_not_field_validated",
        "freeze_state": "frozen_before_review",
        "artifact_sha256": {str(path.relative_to(directory)): _sha(path) for path in frozen},
        "source_hashes": hashes})
    return plan


def _lidar_frozen_inputs(directory):
    """Verify frozen geometry, detections, selection, and crop hashes."""
    manifest = load_json(directory / "manifest.json")
    hashes = manifest.get("artifact_sha256", {})
    required = {"census_frozen.json", "frame.json", "sample.json", "sampling_plan.json"}
    if not required.issubset(hashes):
        raise ValueError("blind manifest is missing frozen artifact hashes")
    for relative, expected in hashes.items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()):
            raise ValueError("blind manifest path is outside the validation directory")
        if not path.is_file() or _sha(path) != expected:
            raise ValueError(f"frozen blind artifact hash mismatch: {relative}")
    plan = load_json(directory / "sampling_plan.json")
    sample = load_json(directory / "sample.json", expect=list)
    census = load_json(directory / "census_frozen.json")
    if plan.get("schema") != "yellowstone.lidar_blind_sampling.v1":
        raise ValueError("sampling plan must use the lidar blind schema")
    ids = [plot["plot_id"] for plot in sample]
    if not ids or len(set(ids)) != len(ids) or ids != plan.get("selected"):
        raise ValueError("frozen sample must contain unique plots matching the selected plan")
    if any(f"blind_crops/{pid}.png" not in hashes for pid in ids):
        raise ValueError("blind manifest is missing selected crop hashes")
    if plan.get("source_hashes") != manifest.get("source_hashes"):
        raise ValueError("blind manifest source hashes differ from the sampling plan")
    return plan, sample, census


def _lidar_hand_labels(refs, submissions, sample):
    """Require explicit completed submissions and unique in-crop reference points."""
    plots = {plot["plot_id"]: plot for plot in sample}
    markers = {}
    for marker in submissions:
        if not isinstance(marker, dict):
            raise ValueError("reference submission must be an object")
        pid = marker.get("plot_id")
        if pid not in plots:
            raise ValueError("reference submission has an unknown plot_id")
        if pid in markers:
            raise ValueError(f"duplicate reference submission: {pid}")
        count = marker.get("n")
        if (marker.get("submitted") is not True or isinstance(count, bool)
                or not isinstance(count, int) or count < 0):
            raise ValueError(f"reference submission must explicitly declare submitted=True and n: {pid}")
        markers[pid] = count
    grouped = {pid: [] for pid in plots}
    ids, coordinates = set(), set()
    for ref in refs:
        if not isinstance(ref, dict):
            raise ValueError("reference point must be an object")
        pid, rid = ref.get("plot_id"), ref.get("reference_id")
        if pid not in plots or not isinstance(rid, str) or not rid:
            raise ValueError("reference point must have a known plot_id and nonempty reference_id")
        if rid in ids:
            raise ValueError(f"duplicate reference_id: {rid}")
        x = finite("reference pixel_x", ref.get("pixel_x"))
        y = finite("reference pixel_y", ref.get("pixel_y"))
        plot = plots[pid]
        if not (plot["x0"] <= x < plot["x1"] and plot["y0"] <= y < plot["y1"]):
            raise ValueError(f"reference point is outside its crop: {rid}")
        coordinate = (pid, x, y)
        if coordinate in coordinates:
            raise ValueError(f"duplicate reference point coordinates: {pid}")
        ids.add(rid)
        coordinates.add(coordinate)
        grouped[pid].append((x, y))
    unresolved = sorted(set(plots) - set(markers))
    if unresolved:
        raise ValueError(f"reference submissions are unresolved: {unresolved}")
    for pid, count in markers.items():
        if len(grouped[pid]) != count:
            raise ValueError(f"reference submission count differs from points: {pid}")
    return grouped


def _lidar_metrics(tp, fp, fn, distances):
    """Return matching counts and ratios with undefined ratios recorded as null."""
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
            "matched_rmse_m": math.sqrt(sum(d * d for d in distances) / len(distances))
            if distances else None}


def evaluate_lidar_blind_crops(validation_dir, *, reference_points=None,
                              reference_submissions=None, out_path=None) -> dict:
    """Evaluate submitted hand labels by visible dominant-crown density class."""
    directory = Path(validation_dir)
    plan, sample, census = _lidar_frozen_inputs(directory)
    refs = _lidar_json(reference_points if reference_points is not None
                       else directory / "reference_points.json", list)
    submissions = _lidar_json(reference_submissions if reference_submissions is not None
                              else directory / "reference_submissions.json", list)
    report = {"schema": "yellowstone.lidar_blind_evaluation.v1",
              "status": "derived_not_field_validated",
              "reference_target": plan["reference_target"],
              "density_class_quantity": plan["density_class_quantity"],
              "total_stem_density_status": "unknown", "subcanopy_stem_density_status": "unknown",
              "source_hashes": plan["source_hashes"],
              "source_metadata": plan["source_metadata"], "imagery_metadata": plan["imagery_metadata"],
              "reference_points_sha256": _lidar_object_sha(refs),
              "reference_submissions_sha256": _lidar_object_sha(submissions),
              "epoch_limitation": plan["epoch_limitation"],
              "main_tolerance_m": plan["main_tolerance_m"],
              "tolerances_frozen_m": plan["tolerances_frozen_m"],
              "evaluations": [], "plots": []}
    if not refs and not submissions:
        report.update(validation_availability="unavailable", reason="No explicit hand-label submissions")
    else:
        grouped = _lidar_hand_labels(refs, submissions, sample)
        bounds, sx, sz = _lidar_geometry(plan["extent_m"], plan["image_dims_px"])
        points = _lidar_tree_points(census, bounds)
        predictions = {}
        for plot in sample:
            pid = plot["plot_id"]
            predictions[pid] = [(x, z) for x, z in points
                                if plot["x0"] <= (x - bounds[0]) / sx < plot["x1"]
                                and plot["y0"] <= (z - bounds[1]) / sz < plot["y1"]]
            count = len(grouped[pid])
            area = positive("plot area_m2", plot["area_m2"])
            density = count * 10000 / area
            report["plots"].append({"plot_id": pid, "area_m2": area,
                                    "reference_count": count, "reference_density_per_ha": density,
                                    "reference_density_class": lidar_density_class(density)})
        for tolerance in plan["tolerances_frozen_m"]:
            totals = {name: [0, 0, 0, []] for name in LIDAR_DENSITY_CLASSES}
            for plot in report["plots"]:
                pid = plot["plot_id"]
                reference = [(bounds[0] + x * sx, bounds[1] + y * sz) for x, y in grouped[pid]]
                tp, fp, fn, distances = _hungarian(predictions[pid], reference, tolerance)
                values = totals[plot["reference_density_class"]]
                values[0] += tp
                values[1] += fp
                values[2] += fn
                values[3].extend(distances)
            by_class = {}
            for name, values in totals.items():
                members = [plot for plot in report["plots"] if plot["reference_density_class"] == name]
                by_class[name] = dict(_lidar_metrics(*values), n_plots=len(members),
                                     area_m2=sum(plot["area_m2"] for plot in members),
                                     reference_count=sum(plot["reference_count"] for plot in members))
            overall = _lidar_metrics(sum(value[0] for value in totals.values()),
                                     sum(value[1] for value in totals.values()),
                                     sum(value[2] for value in totals.values()),
                                     [d for value in totals.values() for d in value[3]])
            report["evaluations"].append({"tolerance_m": tolerance, "overall": overall,
                                           "by_reference_density_class": by_class})
        report["validation_availability"] = "submitted_hand_labels"
        report["limits"] = ["Visible dominant crowns exclude hidden subcanopy stems",
                              "Sample metrics exclude annotation and acquisition-epoch uncertainty",
                              "Detector proxy strata do not establish reference density classes"]
    if out_path is not None:
        output = Path(out_path)
        if output.exists():
            raise ValueError(f"evaluation output already exists: {output}")
        write_json_atomic(output, report)
    return report


def main() -> int:
    """Run the command-line interface."""
    from yellowstone_python.cli.census_validate import main as command
    return command()


if __name__ == "__main__":
    raise SystemExit(main())
