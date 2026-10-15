"""Headless demo for hydrosim: drive the model with a rain schedule and plot.
Usage: python demo_hydrosim.py [--out path]; without --out the figure lands in derived/hydrology_demo/hydrosim_demo.png under the project root (first ancestor containing a derived/ sibling).
"""
import argparse
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from hydrosim import HydroSim, HydroConfig, RainField, Climate, make_terrain, default_soil_map

N, DX, DT = 128, 2.0, 2.0                       # grid, cell size (m), step (s)
HOURS = 3.0


def slider(t_s):
    """mm/h as a function of time: quiet, ramp up to a heavy burst, ease off, dry spell."""
    m = t_s / 60.0
    if m < 10:  return 0.0
    if m < 40:  return 70.0 * (m - 10) / 30.0
    if m < 60:  return 70.0
    if m < 90:  return 70.0 * (90 - m) / 30.0
    return 0.0


def main():
    z = make_terrain(N, N, DX, relief_m=2.5, tilt=0.03, seed=7)
    soil_map, names = default_soil_map(z)
    sim = HydroSim(z, DX, soil_map=soil_map, soil_names=names,
                   rain=RainField((N, N), DX, n_cells=6, seed=11), climate=Climate(), init_wetness=0.6)

    rec = {k: [] for k in ("t", "rate", "q_out", "surface", "soil", "gw", "err")}
    prev_out, snap_depth, snap_t, peak_surface = 0.0, None, 0.0, -1.0
    for k in range(int(HOURS * 3600 / DT)):
        t = k * DT
        rate = slider(t)
        sim.step(DT, rate)
        st = sim.storages()
        rec["t"].append(t / 60); rec["rate"].append(rate)
        rec["q_out"].append((sim.tot["outflow"] - prev_out) / DT); prev_out = sim.tot["outflow"]
        rec["surface"].append(st["surface"]); rec["soil"].append(st["soil"]); rec["gw"].append(st["groundwater"])
        rec["err"].append(sim.balance()["rel_error"])
        if st["surface"] > peak_surface:
            peak_surface, snap_depth, snap_t = st["surface"], sim.h.copy(), t / 60

    b = sim.balance()
    print("rain %.0f m3 | outflow %.0f m3 | ET %.0f m3 | storage change %.0f m3 | rel. balance error %.1e"
          % (b["rain"], b["outflow"], b["et_surface"] + b["et_soil"], b["d_storage"], b["rel_error"]))

    fig, ax = plt.subplots(2, 3, figsize=(15, 8.5))
    ext = [0, N * DX, N * DX, 0]
    im = ax[0, 0].imshow(z, extent=ext, cmap="terrain"); ax[0, 0].contour(
        (np.arange(N) + .5) * DX, (np.arange(N) + .5) * DX, sim.channel.astype(float), [0.5], colors="b", linewidths=0.6)
    ax[0, 0].set_title("Terrain (m) and channel network"); plt.colorbar(im, ax=ax[0, 0], shrink=.8)
    d = np.where(snap_depth > 1e-4, snap_depth * 1e3, np.nan)
    im = ax[0, 1].imshow(d, extent=ext, cmap="Blues", vmax=np.nanpercentile(d, 99)); ax[0, 1].set_facecolor("#ddd")
    ax[0, 1].set_title("Surface water depth (mm) at t = %.0f min" % snap_t); plt.colorbar(im, ax=ax[0, 1], shrink=.8)
    im = ax[0, 2].imshow(sim.soil_saturation(), extent=ext, cmap="YlGnBu", vmin=0.2, vmax=1.0)
    ax[0, 2].set_title("Root-zone saturation at end"); plt.colorbar(im, ax=ax[0, 2], shrink=.8)

    t = np.array(rec["t"])
    ax[1, 0].fill_between(t, rec["rate"], color="#9ecae1"); ax[1, 0].set_ylabel("rain slider (mm/h)", color="#3182bd")
    a2 = ax[1, 0].twinx(); a2.plot(t, rec["q_out"], "r"); a2.set_ylabel("outflow (m3/s)", color="r")
    ax[1, 0].set_xlabel("min"); ax[1, 0].set_title("Rain input and outlet hydrograph")
    s0 = rec["soil"][0]
    ax[1, 1].plot(t, rec["surface"], label="surface"); ax[1, 1].plot(t, np.array(rec["soil"]) - s0, label="soil (change)")
    ax[1, 1].plot(t, rec["gw"], label="groundwater"); ax[1, 1].legend(); ax[1, 1].set_xlabel("min"); ax[1, 1].set_ylabel("m3")
    ax[1, 1].set_title("Storages")
    ax[1, 2].semilogy(t, np.abs(rec["err"]) + 1e-18); ax[1, 2].set_xlabel("min")
    ax[1, 2].set_title("|relative water-balance error|")
    plt.tight_layout()
    out = _resolve_out()
    os.makedirs(os.path.dirname(out), exist_ok=True)
    plt.savefig(out, dpi=110)
    print("wrote", out)


def _resolve_out(explicit: str | None = None) -> str:
    """Resolve the demo output path under derived/hydrology_demo/."""
    if explicit:
        return explicit
    here = os.path.dirname(os.path.abspath(__file__))
    for ancestor in (here, os.path.dirname(here),
                     os.path.dirname(os.path.dirname(here))):
        if os.path.isdir(os.path.join(ancestor, "yellowstone_python",
                                      "derived")):
            return os.path.join(ancestor, "yellowstone_python", "derived",
                                "hydrology_demo", "hydrosim_demo.png")
    return os.path.join(here, "..", "yellowstone_python", "derived",
                        "hydrology_demo", "hydrosim_demo.png")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="hydrosim demo")
    ap.add_argument("--out", default=None,
                    help="output PNG path (default under derived/)")
    _cli = ap.parse_args()
    if _cli.out is not None:
        _original_resolve = _resolve_out
        _resolve_out = lambda explicit=None, _out=_cli.out: _out  # noqa: E731
    main()
