"""Query a census analysis store and render confidence and map figures."""
import os
import sqlite3
from pathlib import Path

cands = []
if os.environ.get("ANALYSIS_STORE"):
    cands = [Path(os.environ["ANALYSIS_STORE"])]
else:
    cands = sorted(Path("derived").glob("analysis_*.sqlite"), key=lambda p: p.stat().st_mtime)
    if not cands:
        cands = sorted(Path("../derived").glob("analysis_*.sqlite"), key=lambda p: p.stat().st_mtime)
assert cands, "no analysis store found (set $ANALYSIS_STORE or build one with tools/build_store.py)"
STORE = cands[-1]
assert STORE.exists(), f"store not found: {STORE} (build one with tools/build_store.py)"
FIG_DIR = Path(os.environ.get("FIG_DIR", "."))
FIG_DIR.mkdir(parents=True, exist_ok=True)

# Read-only sqlite URI with query_only pragma: writes are refused.
con = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
con.execute("PRAGMA query_only=ON")
meta = con.execute("SELECT schema_version, build_id, status, created_utc FROM meta").fetchone()
n_trees = con.execute("SELECT COUNT(*) FROM census_trees").fetchone()[0]
print(f"store : {STORE}")
print(f"schema: {meta[0]}  build: {meta[1]}  status: {meta[2]}  created: {meta[3]}")
print(f"trees : {n_trees}")


def _pyplot():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    return plt


def _show(path):
    try:
        from IPython.display import Image, display
        display(Image(filename=str(path)))
    except ImportError:
        print(f"saved (no IPython here): {path}")


import math

ZONES = {
    "spring_0_50m": {"circle": (-94.7, -10.6, 50.0)},
    "apron_50_100m": {"ring": (-94.7, -10.6, 50.0, 100.0)},
    "transition_100_200m": {"ring": (-94.7, -10.6, 100.0, 200.0)},
    "outwash_200_400m": {"ring": (-94.7, -10.6, 200.0, 400.0)},
    "overlook_knoll_r120": {"circle": (-252.0, 159.0, 120.0)},
    "detail_full": {"box": (-640.0, -640.0, 640.0, 640.0)},
}


def zone_count(spec):
    ((kind, val),) = spec.items()
    if kind == "circle":
        cx, cz, r = val
        rows = con.execute(
            "SELECT x, z FROM census_trees WHERE x BETWEEN ? AND ? AND z BETWEEN ? AND ?",
            (cx - r, cx + r, cz - r, cz + r)).fetchall()
        n = sum(1 for x, z in rows if math.hypot(x - cx, z - cz) <= r)
        area_ha = math.pi * r ** 2 / 1e4
    elif kind == "ring":
        cx, cz, r0, r1 = val
        rows = con.execute(
            "SELECT x, z FROM census_trees WHERE x BETWEEN ? AND ? AND z BETWEEN ? AND ?",
            (cx - r1, cx + r1, cz - r1, cz + r1)).fetchall()
        n = sum(1 for x, z in rows if r0 < math.hypot(x - cx, z - cz) <= r1)
        area_ha = math.pi * (r1 ** 2 - r0 ** 2) / 1e4
    else:
        x0, z0, x1, z1 = val
        n = con.execute(
            "SELECT COUNT(*) FROM census_trees WHERE x BETWEEN ? AND ? AND z BETWEEN ? AND ?",
            (x0, x1, z0, z1)).fetchone()[0]
        area_ha = abs(x1 - x0) * abs(z1 - z0) / 1e4
    return n, round(area_ha, 2), round(n / area_ha, 1)


print(f"{'zone':<22}{'n':>8}{'area_ha':>10}{'per_ha':>9}")
for name, spec in ZONES.items():
    n, area_ha, per_ha = zone_count(spec)
    print(f"{name:<22}{n:>8}{area_ha:>10}{per_ha:>9}")


plt = _pyplot()

rows = con.execute("SELECT confidence, COUNT(*) FROM census_trees GROUP BY confidence").fetchall()
counts = {"low": 0, "medium": 0, "high": 0}
for k, v in rows:
    counts[k] = v
print(counts)

fig, ax = plt.subplots(figsize=(7, 4))
ax.bar(list(counts.keys()), list(counts.values()), color="#4682b4", edgecolor="black")
ax.set_title("crown confidence (NAIP-2022 detection, unreviewed)", fontsize=10)
ax.set_ylabel("crowns")
for k, v in counts.items():
    ax.text(k, v, str(v), ha="center", va="bottom", fontsize=8)
fig.tight_layout()
out = FIG_DIR / "confidence_hist.png"
fig.savefig(out, dpi=150)
plt.close(fig)
_show(out)


plt = _pyplot()
from matplotlib.patches import Circle

EXT = 640.0
rows = con.execute("SELECT x, z FROM census_trees").fetchall()
xs = [r[0] for r in rows]
zs = [r[1] for r in rows]

fig, ax = plt.subplots(figsize=(7, 7))
ax.scatter(xs, zs, s=1, c="0.25", linewidths=0)
for label, cx, cz, r in [("spring", -94.7, -10.6, 50.0), ("knoll", -252.0, 159.0, 120.0)]:
    ax.add_patch(Circle((cx, cz), r, fill=False, ec="red", lw=1.2))
    ax.text(cx - r, cz - r, label, color="red", fontsize=8)
ax.set_xlim(-EXT, EXT)
ax.set_ylim(-EXT, EXT)
ax.set_aspect("equal")
ax.set_title(f"census crowns from {STORE.name} (status: {meta[2]})", fontsize=9)
ax.set_xlabel("x (m)")
ax.set_ylabel("z (m)")
fig.tight_layout()
out = FIG_DIR / "census_map.png"
fig.savefig(out, dpi=150)
plt.close(fig)
_show(out)
con.close()
print("done: example read the store only (no JSON loaded)")

