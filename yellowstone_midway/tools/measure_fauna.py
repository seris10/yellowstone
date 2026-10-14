"""Measure a quadruped mesh against published body measurements.
Runs inside Blender; emits report.json, report.md and profile.svg per run."""

from __future__ import annotations

import argparse
import datetime
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np

MIDWAY = Path(__file__).resolve().parent.parent
REFERENCES = MIDWAY / "references" / "fauna_reference_measurements.json"
DEFAULT_OUT = MIDWAY.parent / "research" / "fauna-measurements"
BODY_DENSITY_KG_M3 = 1000.0
BINS = 200
HEAD_EXCLUDE_FRACTION = 0.15
WITHERS_SEARCH_END_FRACTION = 0.55
TAIL_BASE_WIDTH_FRACTION = 0.35
RUMP_SEARCH_FRACTION = 0.30
BELLY_MIN_FRACTION = 0.15
LEG_CONTACT_FRACTION = 0.08


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    p = argparse.ArgumentParser(prog="measure-fauna", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("model", type=Path)
    p.add_argument("--species", default="bison")
    p.add_argument("--sex", choices=["male", "female", "both"], default="both")
    p.add_argument("--pose", choices=["rest", "frame"], default="rest",
                   help="rest = armature bind pose; frame = evaluated pose at --frame")
    p.add_argument("--frame", type=int, default=0)
    p.add_argument("--forward", choices=["auto", "+x", "-x", "+y", "-y"], default="auto",
                   help="direction the animal faces in Blender coordinates after import")
    p.add_argument("--units-per-meter", type=float, default=1.0)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    return p.parse_args(argv)


def load_model(path: Path, pose: str, frame: int) -> list:
    if not path.is_file():
        raise SystemExit(f"measure-fauna: no such file: {path}")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    scene = bpy.context.scene
    armatures = [o for o in scene.objects if o.type == "ARMATURE"]
    for arm in armatures:
        arm.data.pose_position = "REST" if pose == "rest" else "POSE"
    scene.frame_set(frame)
    return armatures


def collect_geometry(units_per_meter: float) -> tuple[np.ndarray, float, int, int]:
    """World-space vertices in meters, signed volume in m3, non-manifold edge count, mesh count."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    clouds, volume, nonmanifold, meshes = [], 0.0, 0, 0
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.hide_get():
            continue
        ev = obj.evaluated_get(depsgraph)
        me = ev.to_mesh()
        if len(me.vertices) == 0:
            ev.to_mesh_clear()
            continue
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        m = np.array(ev.matrix_world)
        clouds.append(co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3])
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.transform(ev.matrix_world)
        volume += bm.calc_volume(signed=True)
        nonmanifold += sum(1 for e in bm.edges if not e.is_manifold)
        bm.free()
        ev.to_mesh_clear()
        meshes += 1
    if not clouds:
        raise SystemExit("no mesh geometry found in the model")
    scale = 1.0 / units_per_meter
    return np.vstack(clouds) * scale, volume * scale ** 3, nonmanifold, meshes


def body_frame(pts: np.ndarray, forward: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Project onto (s along the body, t lateral, z above ground); s increases toward the head."""
    xy = pts[:, :2] - pts[:, :2].mean(axis=0)
    named = {"+x": (1.0, 0.0), "-x": (-1.0, 0.0), "+y": (0.0, 1.0), "-y": (0.0, -1.0)}
    if forward == "auto":
        eigval, eigvec = np.linalg.eigh(np.cov(xy.T))
        axis = eigvec[:, int(np.argmax(eigval))]
        method = "principal horizontal axis; head end = the half with the higher 95th-percentile top"
    else:
        axis = np.array(named[forward])
        method = f"forced {forward}"
    lateral = np.array([-axis[1], axis[0]])
    s, t = xy @ axis, xy @ lateral
    z = pts[:, 2] - pts[:, 2].min()
    if forward == "auto":
        mid = 0.5 * (s.min() + s.max())
        if np.percentile(z[s >= mid], 95) < np.percentile(z[s < mid], 95):
            s, t = -s, -t
    return s, t, z, {"method": method, "axis_xy": [round(float(a), 4) for a in axis]}


def profiles(s: np.ndarray, t: np.ndarray, z: np.ndarray) -> dict:
    edges = np.linspace(s.min(), s.max(), BINS + 1)
    idx = np.clip(np.digitize(s, edges) - 1, 0, BINS - 1)
    top, bottom, width = (np.full(BINS, np.nan) for _ in range(3))
    for b in range(BINS):
        sel = idx == b
        if sel.any():
            top[b], bottom[b] = z[sel].max(), z[sel].min()
            width[b] = t[sel].max() - t[sel].min()
    centers = 0.5 * (edges[:-1] + edges[1:])
    for arr in (top, bottom, width):
        ok = ~np.isnan(arr)
        arr[~ok] = np.interp(centers[~ok], centers[ok], arr[ok])
    return {"s": centers, "top": top, "bottom": bottom, "width": width}


def tail_from_bones(armatures: list, units_per_meter: float) -> float | None:
    total, found = 0.0, False
    for arm in armatures:
        for bone in arm.data.bones:
            if "tail" in bone.name.lower():
                total += bone.length * arm.matrix_world.to_scale()[0]
                found = True
    return total / units_per_meter if found else None


def leg_groups(sc: np.ndarray, bottom: np.ndarray, height: float, tail_base_s: float) -> list[tuple[float, float]]:
    """Rear-first profile bins within the ground-contact threshold."""
    contact = bottom < LEG_CONTACT_FRACTION * height
    groups, start = [], None
    for i, flag in enumerate(contact):
        if flag and start is None:
            start = i
        if (not flag or i == len(contact) - 1) and start is not None:
            end = i if flag else i - 1
            if end - start >= 1 and sc[end] > tail_base_s:
                groups.append((float(sc[start]), float(sc[end])))
            start = None
    return groups


def landmarks(prof: dict, s: np.ndarray, t: np.ndarray, z: np.ndarray, tail_bones: float | None) -> dict:
    sc, top, bottom, width = prof["s"], prof["top"], prof["bottom"], prof["width"]
    nose_s, rear_s = float(s.max()), float(s.min())
    extent = nose_s - rear_s
    from_nose = (nose_s - sc) / extent

    tail_base_bin = int(np.argmax(width >= TAIL_BASE_WIDTH_FRACTION * width.max()))
    tail_base_s = float(sc[tail_base_bin])
    head_body = nose_s - tail_base_s

    w_sel = (from_nose >= HEAD_EXCLUDE_FRACTION) & (from_nose <= WITHERS_SEARCH_END_FRACTION)
    w_bin = int(np.flatnonzero(w_sel)[np.argmax(top[w_sel])])
    withers_s, withers_h = float(sc[w_bin]), float(top[w_bin])

    legs = leg_groups(sc, bottom, withers_h, tail_base_s)
    hind_span: tuple[float, float] | None = None
    fore_span: tuple[float, float] | None = None

    def peak(sel: np.ndarray) -> tuple[float, float]:
        b = int(np.flatnonzero(sel)[np.argmax(top[sel])])
        return float(sc[b]), float(top[b])

    if len(legs) >= 2:
        hind_span = legs[0]
        fore_span = min(legs[1:], key=lambda g: abs(0.5 * (g[0] + g[1]) - withers_s))
        hip_s, hip_h = peak((sc >= hind_span[0]) & (sc <= hind_span[1]))
        barrel = (sc > hind_span[1]) & (sc < fore_span[0])
        hip_method = "highest point above the hind-leg ground contact"
    else:
        hip_s, hip_h = peak((sc >= tail_base_s) & (sc <= tail_base_s + RUMP_SEARCH_FRACTION * head_body))
        barrel = (sc > hip_s) & (sc < withers_s)
        hip_method = "highest point in the rear 30 percent of head and body (no separate leg contacts found)"
    under = bottom[barrel]
    under = under[under > BELLY_MIN_FRACTION * withers_h]
    belly = float(np.median(under)) if under.size else float("nan")
    body_width = float(width[barrel].max()) if barrel.any() else float("nan")

    if tail_bones is not None:
        tail_len, tail_method = tail_bones, "sum of armature bones named tail"
    else:
        base = np.array([tail_base_s, 0.0, float(top[tail_base_bin])])
        cand = (s <= tail_base_s + 0.03 * extent) & (np.abs(t - np.median(t)) < 0.15 * width.max())
        if cand.any():
            d = np.sqrt((s[cand] - base[0]) ** 2 + (t[cand] - base[1]) ** 2 + (z[cand] - base[2]) ** 2)
            tail_len = float(d.max())
        else:
            tail_len = float("nan")
        tail_method = "geometric straight line from tail base to farthest central rear vertex (low confidence)"

    return {
        "nose_s": nose_s, "rear_s": rear_s, "axis_extent_m": extent,
        "tail_base_s": tail_base_s, "head_body_length_m": head_body,
        "withers_s": withers_s, "shoulder_height_m": withers_h,
        "withers_from_nose_fraction": float((nose_s - withers_s) / extent),
        "hip_s": hip_s, "hip_height_m": hip_h, "hip_method": hip_method,
        "hind_leg_contact_s": list(hind_span) if hind_span else None,
        "fore_leg_contact_s": list(fore_span) if fore_span else None,
        "belly_clearance_m": belly, "chest_depth_m": withers_h - belly,
        "body_width_m": body_width,
        "tail_length_m": tail_len, "tail_method": tail_method,
        "total_length_m": head_body + tail_len,
        "leg_to_height_ratio": belly / withers_h if withers_h > 0 else float("nan"),
        "hip_to_shoulder_ratio": hip_h / withers_h if withers_h > 0 else float("nan"),
    }


def compare(lm: dict, mass_kg: float | None, ref: dict, sexes: list[str]) -> list[dict]:
    measured = {
        "shoulder_height_mm": lm["shoulder_height_m"] * 1000.0,
        "total_length_mm": lm["total_length_m"] * 1000.0,
        "tail_length_mm": lm["tail_length_m"] * 1000.0,
        "body_mass_kg": mass_kg,
    }

    def status(value: float | None, lo: float, hi: float) -> str:
        if value is None or not math.isfinite(value):
            return "not measured"
        if value < lo:
            return f"below by {100.0 * (lo - value) / lo:.0f}%"
        if value > hi:
            return f"above by {100.0 * (value - hi) / hi:.0f}%"
        return "within range"

    rows = []
    for key, value in measured.items():
        row: dict = {"measurement": key, "model": value}
        for sex in sexes:
            lo, hi = ref[sex][key]
            sh_lo, sh_hi = ref[sex]["shoulder_height_mm"]
            k = 0.5 * (sh_lo + sh_hi) / measured["shoulder_height_mm"]
            power = 3 if key.endswith("_kg") else 1
            scaled = None if value is None or not math.isfinite(value) else value * k ** power
            row[sex] = {"range": [lo, hi], "status": status(value, lo, hi),
                        "scale_to_mid_shoulder_height": k, "scaled_model": scaled,
                        "scaled_status": status(scaled, lo, hi)}
        rows.append(row)
    return rows


def svg_profile(prof: dict, lm: dict, title: str, note: str) -> str:
    h_px, m = 520, 60
    extent = lm["axis_extent_m"]
    zmax = float(prof["top"].max())
    k = (h_px - 2 * m - 40) / zmax
    w_px = max(760, int(2 * m + extent * k + 140))

    def x(sv: float) -> float:
        return m + (sv - lm["rear_s"]) * k

    def y(zv: float) -> float:
        return h_px - m - zv * k

    top = " ".join(f"{x(a):.1f},{y(b):.1f}" for a, b in zip(prof["s"], prof["top"]))
    bot = " ".join(f"{x(a):.1f},{y(b):.1f}" for a, b in zip(prof["s"], prof["bottom"]))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w_px}" height="{h_px}" '
        f'viewBox="0 0 {w_px} {h_px}" font-family="system-ui, sans-serif">',
        f'<rect width="{w_px}" height="{h_px}" fill="#ffffff"/>',
        f'<text x="{m}" y="30" font-size="18" font-weight="600" fill="#111">{title}</text>',
        f'<text x="{m}" y="52" font-size="14" fill="#444">{note}</text>',
        f'<line x1="{m}" y1="{y(0):.1f}" x2="{w_px - m}" y2="{y(0):.1f}" stroke="#888" stroke-width="1.5"/>',
        f'<polyline points="{bot}" fill="none" stroke="#9a9a9a" stroke-width="1.5"/>',
        f'<polyline points="{top}" fill="none" stroke="#1f5fa8" stroke-width="2.5"/>',
    ]

    def vline(sv: float, zv: float, label: str, color: str, z0: float = 0.0) -> None:
        parts.append(f'<line x1="{x(sv):.1f}" y1="{y(z0):.1f}" x2="{x(sv):.1f}" y2="{y(zv):.1f}" '
                     f'stroke="{color}" stroke-width="2" stroke-dasharray="6 4"/>')
        parts.append(f'<text x="{x(sv) + 6:.1f}" y="{y(zv) - 8:.1f}" font-size="14" '
                     f'fill="{color}">{label}</text>')

    vline(lm["withers_s"], lm["shoulder_height_m"], f'shoulder {lm["shoulder_height_m"]:.2f} m', "#b3261e")
    vline(lm["hip_s"], lm["hip_height_m"], f'hip {lm["hip_height_m"]:.2f} m', "#7a4f01")
    if math.isfinite(lm["belly_clearance_m"]):
        mid_s = 0.5 * (lm["withers_s"] + lm["hip_s"])
        vline(mid_s, lm["belly_clearance_m"], f'belly {lm["belly_clearance_m"]:.2f} m', "#2e7d32")
    yb = y(0) + 28
    xb, xn = x(lm["tail_base_s"]), x(lm["nose_s"])
    parts.append(f'<line x1="{xb:.1f}" y1="{yb:.1f}" x2="{xn:.1f}" y2="{yb:.1f}" stroke="#111" stroke-width="1.5"/>')
    parts.append(f'<text x="{xb:.1f}" y="{yb + 20:.1f}" font-size="14" fill="#111">head and body '
                 f'{lm["head_body_length_m"]:.2f} m (tail base to nose)</text>')
    parts.append("</svg>")
    return "\n".join(parts)


def fmt(v: float | None, unit: str) -> str:
    return "n/a" if v is None or not math.isfinite(v) else f"{v:,.0f} {unit}"


def main() -> None:
    args = parse_args()
    refs = json.loads(REFERENCES.read_text(encoding="utf-8"))["species"]
    if args.species not in refs:
        raise SystemExit(f"no reference measurements for species {args.species!r}; known: {sorted(refs)}")
    ref = refs[args.species]
    sexes = ["male", "female"] if args.sex == "both" else [args.sex]

    armatures = load_model(args.model, args.pose, args.frame)
    pts, volume_m3, nonmanifold, meshes = collect_geometry(args.units_per_meter)
    s, t, z, frame_info = body_frame(pts, args.forward)
    prof = profiles(s, t, z)
    lm = landmarks(prof, s, t, z, tail_from_bones(armatures, args.units_per_meter))
    closed = nonmanifold == 0
    mass_kg = abs(volume_m3) * BODY_DENSITY_KG_M3 if closed else None
    rows = compare(lm, mass_kg, ref, sexes)

    ref_mid = 0.5 * sum(ref["male"]["shoulder_height_mm"]) / 1000.0
    implied = ref_mid / lm["shoulder_height_m"] if lm["shoulder_height_m"] > 0 else float("nan")
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_dir = args.out / f"{args.model.stem}-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "model": str(args.model), "species": args.species, "scientific_name": ref["scientific_name"],
        "reference_source": ref["source"], "pose": args.pose, "frame": args.frame,
        "units_per_meter": args.units_per_meter, "vertices": int(len(pts)), "mesh_objects": meshes,
        "armatures": [a.name for a in armatures], "body_axis": frame_info,
        "closed_mesh": closed, "non_manifold_edges": int(nonmanifold),
        "volume_m3": volume_m3, "assumed_body_density_kg_m3": BODY_DENSITY_KG_M3,
        "mass_estimate_kg": mass_kg,
        "implied_scale_to_male_mid_shoulder_height": implied,
        "landmarks": lm, "comparison": rows,
        "caveats": [
            "Landmarks come from side-view profiles of the mesh, so fur and horns are part of the silhouette.",
            "Shoulder height is the highest point between 15 and 55 percent of the body length from the nose; "
            "check its position in profile.svg.",
            "Mass is reported only for a closed mesh, from volume times an assumed density of 1000 kg/m3.",
        ] + ref.get("context", []),
    }
    (out_dir / "report.json").write_text(json.dumps(report, indent=2, default=float) + "\n", encoding="utf-8")

    lines = [
        f"# {ref['scientific_name']} mesh measurement: {args.model.name}",
        "",
        f"Reference: {ref['source']['citation']}",
        f"Pose: {args.pose}; vertices: {len(pts):,}; meshes: {meshes}; closed mesh: {closed}; "
        f"body axis: {frame_info['method']}.",
        f"Implied scale to a mid-range adult male shoulder height: x{implied:.2f}"
        + (" (model units are probably not meters)" if not 0.7 <= implied <= 1.4 else ""),
        "",
        "",
        "As modeled compares the raw size. Scaled first resizes the model so its shoulder height equals the middle of",
        "that sex's published range, then compares the other measurements: that column checks proportions.",
        "",
        "| Measurement | Model | " + " | ".join(
            f"{sx.title()} range | {sx.title()} as modeled | {sx.title()} scaled" for sx in sexes) + " |",
        "|---|---|" + "---|" * (3 * len(sexes)),
    ]
    for row in rows:
        unit = "kg" if row["measurement"].endswith("_kg") else "mm"
        cells = " | ".join(
            f"{row[sx]['range'][0]:,} to {row[sx]['range'][1]:,} {unit} | {row[sx]['status']} | "
            f"{fmt(row[sx]['scaled_model'], unit)}, {row[sx]['scaled_status']}" for sx in sexes)
        lines.append(f"| {row['measurement'].replace('_', ' ')} | {fmt(row['model'], unit)} | {cells} |")
    lines += [
        "",
        "Proportions (no published range in the reference): "
        f"hip to shoulder {lm['hip_to_shoulder_ratio']:.2f}, "
        f"belly clearance to shoulder {lm['leg_to_height_ratio']:.2f}, "
        f"withers at {100 * lm['withers_from_nose_fraction']:.0f}% of length from the nose, "
        f"body width {lm['body_width_m']:.2f} m.",
        f"Tail: {lm['tail_method']}.",
        "",
        "Caveats:",
    ] + [f"- {c}" for c in report["caveats"]]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    note = f"{args.pose} pose; side view, head to the right; fur and horns included in the silhouette"
    (out_dir / "profile.svg").write_text(svg_profile(prof, lm, f"{args.model.name}: side profile and landmarks", note),
                                         encoding="utf-8")
    print(f"measure-fauna: wrote {out_dir}")
    print("\n".join(lines[:lines.index("Caveats:")]))


if __name__ == "__main__":
    main()
