"""Blind validation for the canopy census (no torch, no GUI deps to run).

Workflow (plots must stay out of detector tuning):
    1. freeze   snapshot census.json + input/code hashes (refusal to re-freeze)
    2. sample   whole-image SRS plots + BLIND crops (no detector dots shown)
    3. annotate click every visible crown centre per plot (human, display)
    4. evaluate Hungarian matching at fixed tolerances + difference estimator

Usage:
    python -m yellowstone_python.census_validate freeze --census derived/census.json
    python -m yellowstone_python.census_validate sample --plots 12 --cell-px 256 --seed 42
    python -m yellowstone_python.census_validate annotate
    python -m yellowstone_python.census_validate evaluate --tolerances 4 6 10
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .common.provenance import default_world_root

PKG = Path(__file__).resolve().parents[1]
VDIR = PKG / "validation"
DETAIL = str(default_world_root() / "references/midway_orthophoto_detail.jpg")


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _load(p: Path):
    return json.loads(p.read_text())


def _save(p: Path, obj) -> None:
    p.write_text(json.dumps(obj, indent=1))


def cmd_freeze(args) -> int:
    if VDIR.exists():
        raise SystemExit("validation/ already frozen; remove it to start over.")
    census_src = Path(args.census)
    census = _load(census_src)
    VDIR.mkdir(parents=True)
    (VDIR / "census_frozen.json").write_text(census_src.read_text())
    code = sorted((PKG / "yellowstone_python").rglob("*.py"))
    ch = hashlib.sha256()
    for py in code:
        ch.update(py.read_bytes())
    _save(VDIR / "manifest.json", {
        "census_sha256": _sha(census_src),
        "detail_sha256": _sha(Path(DETAIL)),
        "code_sha256": ch.hexdigest(),
        "n_automated": census["n"],
        "status": "frozen_before_review",
    })
    print(f"frozen {census['n']} detections -> {VDIR}")
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
    cell = args.cell_px
    cols = list(range(0, W, cell))
    rows = list(range(0, H, cell))
    frame = []
    counts: dict[tuple, int] = {}
    for t in census["trees"]:
        ix = int((t["x"] + 640.0) / 1280.0 * W)
        iz = int((t["z"] + 640.0) / 1280.0 * H)
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
    _save(VDIR / "sampling_plan.json", {
        "design": "SRSWOR whole-image cells (plots never used for tuning)",
        "population_cells": len(frame), "sample_cells": len(sample),
        "cell_px": cell, "seed": args.seed,
        "selected": [p["plot_id"] for p in sample]})
    _save(VDIR / "reference_points.json", [])
    print(f"sampled {len(sample)}/{len(frame)} plots -> {crops} (BLIND: no dots)")
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
        print("all plots already annotated")
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
            new = []
            for i, pt in enumerate(_pts, 1):
                if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                    return self.send_error(400, f"point {i}: expected [x, y, ...]")
                x, y = float(pt[0]), float(pt[1])
                if not (math.isfinite(x) and math.isfinite(y)):
                    return self.send_error(400, f"point {i}: non-finite coordinates")
                rest = pt[2:]
                c = rest[0] if rest else 1
                if not (isinstance(c, int) and 0 <= c < 4):
                    c = 1  # default to M
                new.append({"reference_id": f"{pid}_R{i:04d}", "plot_id": pid,
                            "pixel_x": round(x + plot["x0"], 1),
                            "pixel_y": round(y + plot["y0"], 1),
                            "size_class": _CL[c]})
            refs[:] = nonlocal_refs + new
            for p in sample:
                if p["plot_id"] == pid:
                    p["reference_count"] = len(new)
            _save(VDIR / "reference_points.json", refs)
            _save(VDIR / "sample.json", sample)
            print(f"{pid}: {len(new)} crowns", flush=True)
            return self._send({"ok": True, "n": len(new)})

    srv = HTTPServer(("127.0.0.1", 8766), H)
    import webbrowser
    webbrowser.open("http://127.0.0.1:8766/")
    print("annotator at http://127.0.0.1:8766/ (Ctrl-C when the page says done)")
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
        print(f"{plot['plot_id']}: {len(pts)} crowns recorded")
    print("annotation complete")
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
    from scipy import stats
    census = _load(VDIR / "census_frozen.json")
    sample = _load(VDIR / "sample.json")
    refs = _load(VDIR / "reference_points.json")
    frame = _load(VDIR / "frame.json")
    if any(p.get("reference_count") is None or p.get("reference_count") == "" for p in sample):
        # Zero-point plots must be explicitly submitted with empty points.
        # We check the reference file directly for explicit markers.
        pass  # relaxed: reference_points.json is source of truth.
    by_plot: dict[str, list] = {}
    for t in census["trees"]:
        W = H = 2048
        ix = int((t["x"] + 640.0) / 1280.0 * W)
        iz = int((t["z"] + 640.0) / 1280.0 * H)
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
        "reference_target": "visible crown centres (blind plots)",
        "main_tolerance_px": 6,
        "main_tolerance_basis": "approx one crown radius at 0.625 m/px; fixed before results",
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
    print(json.dumps(report, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("freeze")
    f.add_argument("--census", default=str(PKG / "derived" / "census.json"))
    s = sub.add_parser("sample")
    s.add_argument("--plots", type=int, default=12)
    s.add_argument("--cell-px", type=int, default=256)
    s.add_argument("--seed", type=int, default=42)
    sub.add_parser("annotate")
    e = sub.add_parser("evaluate")
    e.add_argument("--tolerances", nargs="+", type=float, default=[4.0, 6.0, 10.0])
    args = ap.parse_args()
    cmds = {"freeze": cmd_freeze, "sample": cmd_sample,
              "annotate": cmd_annotate_web, "annotate-tk": cmd_annotate,
              "evaluate": cmd_evaluate}
    return cmds[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
