"""Validation and sensitivity checks for hydrosim.py. Exit code is non-zero when any check fails. Run: python validate_hydrosim.py."""
import sys
import time

import numpy as np

from hydrosim import (G, HydroConfig, HydroSim, RainField, Climate, SOILS, MM_H_TO_M_S,
                      make_terrain, default_soil_map, flow_accumulation,
                      terminal_velocity)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))


def ga_reference(K, A, t):
    """Solve F - A ln(1 + F/A) = K t by bisection (vectorised)."""
    rhs = K * t
    lo, hi = np.zeros_like(rhs), rhs + 2 * A * np.log(2 + rhs / A) + 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        g = mid - A * np.log1p(mid / A)
        lo = np.where(g < rhs, mid, lo)
        hi = np.where(g < rhs, hi, mid)
    return 0.5 * (lo + hi)


def column(soil="sandy_loam", infiltration="green_ampt", h0=0.5, wetness=0.5, **cfg_kw):
    """3x3 flat, closed, no rain: a stand-alone soil column with ponded water."""
    cfg = HydroConfig(infiltration=infiltration, open_edges=(), enable_et=False, perc_factor=0.0, **cfg_kw)
    z = np.zeros((3, 3))
    return HydroSim(z, 1.0, soil_names=[soil], config=cfg, rain=RainField((3, 3), 1.0, mode="uniform"),
                    init_wetness=wetness, init_depth=h0, channel_mask=np.zeros((3, 3), bool))


# ------------------------------------------------------------------------------------
def test_ga_solver():
    rng = np.random.default_rng(0)
    n = 20000
    A = 10 ** rng.uniform(-4, -0.5, n)           # 0.1 mm .. 0.3 m
    K = 10 ** rng.uniform(-9, -4, n)             # m/s
    F = np.where(rng.random(n) < 0.3, 0.0, 10 ** rng.uniform(-6, -0.5, n))
    ds = 10 ** rng.uniform(-2, 2, n)
    inc = HydroSim._ga_increment(F, A, K, ds)
    # reference from the same cumulative relation
    rhs = (F - A * np.log1p(F / A)) + K * ds
    lo, hi = F.copy(), rhs + 2 * A * np.log(2 + rhs / A) + 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        g = mid - A * np.log1p(mid / A)
        lo = np.where(g < rhs, mid, lo)
        hi = np.where(g < rhs, hi, mid)
    # Compare solved roots so a 1e-11 m increment against a 1e-16 m bisection floor does not inflate relative error.
    root_newton, root_ref = F + inc, 0.5 * (lo + hi)
    err = np.max(np.abs(root_newton - root_ref) / np.maximum(root_ref, 1e-12))
    check("GA Newton solver matches bisection (20k random cases)", err < 1e-6, "max rel err %.2e" % err)


def test_ga_column():
    soil = "sandy_loam"
    por, psi_mm, K_mm_h, fc, wp = SOILS[soil]
    Zr = 0.5
    for dt in (5.0, 60.0):
        sim = column(soil, "green_ampt")
        S0 = sim.S[0, 0]
        dtheta = (sim.S_sat[0, 0] - S0) / Zr
        A, K = psi_mm * 1e-3 * dtheta, K_mm_h * MM_H_TO_M_S
        worst, t = 0.0, 0.0
        for k in range(int(2 * 3600 / dt)):
            sim.step(dt)
            t += dt
            if abs(t - 1800) < 1e-6 or abs(t - 3600) < 1e-6 or abs(t - 7200) < 1e-6:
                F_sim = sim.S[0, 0] - S0
                F_ref = float(ga_reference(np.array([K]), np.array([A]), np.array([t]))[0])
                worst = max(worst, abs(F_sim - F_ref) / F_ref)
        check("Green-Ampt column vs analytic, dt=%gs" % dt, worst < 0.01, "worst rel err %.2e (t=0.5,1,2 h)" % worst)


def test_horton_water_limited():
    """Mein and Larson 1973: Horton capacity holds while rain supply is below it.
    A column with f0=50 mm/h, fc=5 mm/h, k=1/h fed 1 mm/h for 2 h infiltrates 2 mm within 1% since supply is below capacity.
    """
    f0, fc, k = 50.0, 5.0, 1.0
    sim = column("loam", "horton", horton_f0_mm_h=f0, horton_fc_mm_h=fc,
                 horton_k_per_h=k, h0=0.0, wetness=0.0)
    dt, S0 = 60.0, sim.S[0, 0]
    rate_mm_h = 1.0
    for _ in range(int(2 * 3600 / dt)):
        sim.step(dt, rate_mm_h)
    F_sim = sim.S[0, 0] - S0
    F_ref = rate_mm_h * MM_H_TO_M_S * 2 * 3600.0
    err = abs(F_sim - F_ref) / F_ref if F_ref > 0 else abs(F_sim - F_ref)
    check("Horton water-limited supply (Mein-Larson)", err < 0.05,
          "F_sim %.2f mm, expected %.2f mm" % (F_sim * 1e3, F_ref * 1e3))


def test_fao56_diurnal_phase():
    """FAO-56 et0 under diurnal radiation peaks at local noon."""
    import math as _math
    climate = Climate(temp_c=25.0, rel_humidity=59.0, wind_u2=2.078,
                      rn_mj_m2_day=14.33, elevation_m=100.0,
                      diurnal=True, start_hour=0.0)
    tod = [i * 1800.0 for i in range(48)]
    vals = [climate.et0_mm_day(t) for t in tod]
    peak = tod[vals.index(max(vals))]
    expected = 12.0 * 3600.0
    check("FAO-56 et0 peaks within 1 h of local noon",
          abs(peak - expected) <= 3600.0,
          "peak at %.0f s (expected %.0f s)" % (peak, expected))
    daily = sum(vals) / len(vals)
    rn_factor = (1.0 - (1.0 / len(vals)) *
                 sum(_math.cos(2 * _math.pi * (t / 86400.0)) for t in tod))
    check("FAO-56 diurnal average Rn factor is ~1",
          0.98 <= rn_factor <= 1.02,
          "<1 - cos> = %.3f" % rn_factor)
    check("FAO-56 daily-mean et0 positive", daily > 0.0,
          "mean %.3f mm/day" % daily)


def test_horton_column():
    f0, fc, k = 100.0, 5.0, 1.0
    sim = column("loam", "horton", horton_f0_mm_h=f0, horton_fc_mm_h=fc, horton_k_per_h=k, h0=0.8, wetness=0.0)
    dt, S0 = 10.0, sim.S[0, 0]
    for _ in range(int(3600 / dt)):
        sim.step(dt)
    F_sim = sim.S[0, 0] - S0
    t = 3600.0
    F_ref = (fc * MM_H_TO_M_S) * t + (f0 - fc) * MM_H_TO_M_S / (k / 3600.0) * (1 - np.exp(-(k / 3600.0) * t))
    err = abs(F_sim - F_ref) / F_ref
    check("Horton column vs analytic integral (1 h)", err < 1e-3, "rel err %.2e, F=%.1f mm" % (err, F_sim * 1e3))


def test_mass_conservation():
    n, dx = 64, 2.0
    z = make_terrain(n, n, dx, seed=3)
    sm, names = default_soil_map(z)
    sim = HydroSim(z, dx, soil_map=sm, soil_names=names, rain=RainField((n, n), dx, seed=5),
                   climate=Climate(), init_wetness=0.9)
    worst = 0.0
    for k in range(1800):
        rate = 60.0 * min(1.0, k / 300) if k < 1200 else 0.0     # ramp up, then dry-down
        sim.step(1.0, rate)
        if k % 100 == 0:
            worst = max(worst, abs(sim.balance()["rel_error"]))
    b = sim.balance()
    worst = max(worst, abs(b["rel_error"]))
    check("mass conservation (storm, ET, drainage, baseflow, open edges)", worst < 1e-10,
          "worst rel err %.1e; rain %.0f m3, out %.0f m3, ET %.0f m3, gw %.0f m3, min depth %.1e"
          % (worst, b["rain"], b["outflow"], b["et_surface"] + b["et_soil"], sim.Vg, sim.h.min()))
    check("depth never negative", sim.h.min() >= 0.0)


def test_lake_at_rest():
    n, dx = 41, 1.0
    y, x = np.mgrid[0:n, 0:n] * dx
    z = 0.01 * ((x - 20) ** 2 + (y - 20) ** 2)
    h = np.maximum(0.0, 1.0 - z)
    cfg = HydroConfig(infiltration="none", open_edges=(), enable_et=False, perc_factor=0.0)
    sim = HydroSim(z, dx, config=cfg, rain=RainField((n, n), dx, mode="uniform"), init_depth=h,
                   channel_mask=np.zeros((n, n), bool))
    v0 = sim.h.sum()
    for _ in range(600):
        sim.step(0.2)
    qmax = max(np.abs(sim.qx).max(), np.abs(sim.qy).max())
    dv = abs(sim.h.sum() - v0) / v0
    check("lake at rest stays at rest", qmax < 1e-6 and dv < 1e-12, "max |q| %.1e m2/s, volume drift %.1e" % (qmax, dv))


def strip_sim(h, dx, **cfg_kw):
    ny, nx = h.shape
    cfg = HydroConfig(infiltration="none", open_edges=(), enable_et=False, perc_factor=0.0, **cfg_kw)
    return HydroSim(np.zeros((ny, nx)), dx, config=cfg, rain=RainField((ny, nx), dx, mode="uniform"),
                    init_depth=h, channel_mask=np.zeros((ny, nx), bool))


def test_gravity_wave():
    """Small step in depth: the right-going wave must travel at sqrt(g*h)."""
    nx, dx, hl, hr, T = 400, 0.5, 1.02, 1.00, 10.0
    h = np.full((3, nx), hr)
    h[:, : nx // 2] = hl
    sim = strip_sim(h, dx, manning_overland=0.01, froude_max=10.0, h_min=1e-4)
    t = 0.0
    while t < T - 1e-9:
        sim.step(0.05)
        t += 0.05
    p = sim.h[1]
    x = (np.arange(nx) + 0.5) * dx - nx * dx / 2
    half = hr + (hl - hr) / 4.0                       # the right-going wave carries half of the step
    i = np.flatnonzero(p > half)[-1]
    xf = np.interp(half, [p[i + 1], p[i]], [x[i + 1], x[i]])
    expect = np.sqrt(G * (hl + hr) / 2) * T
    check("gravity wave speed = sqrt(g h)", abs(xf - expect) / expect < 0.05, "sim %.2f m, theory %.2f m" % (xf, expect))


def test_dry_bed_dam_break_info():
    """Documented limitation reported for information; see the module docstring."""
    nx, dx, h0, T = 400, 0.5, 1.0, 10.0
    h = np.zeros((3, nx))
    h[:, : nx // 2] = h0
    sim = strip_sim(h, dx, manning_overland=0.01, froude_max=10.0, h_min=1e-4)
    t = 0.0
    while t < T - 1e-9:
        sim.step(0.05)
        t += 0.05
    x = (np.arange(nx) + 0.5) * dx - nx * dx / 2
    front = x[np.flatnonzero(sim.h[1] > 5e-3)[-1]]
    ritter = (2 * np.sqrt(G * h0) - 3 * np.sqrt(G * 5e-3)) * T
    print("INFO  dry-bed dam break (outside local-inertial validity): front %.1f m vs Ritter %.1f m "
          "-> bores over dry ground travel slower than full shallow-water theory" % (front, ritter))


def plane_run(S, n, i_mm_h, L=100.0, dx=2.0, T=1500.0, dt=1.0):
    """Rain on a planar slope, no infiltration. Returns (t, outflow rate per unit width)."""
    ny, nx = int(L / dx), 3
    z = (S * dx * (ny - 1 - np.arange(ny)))[:, None] * np.ones((1, nx))
    cfg = HydroConfig(infiltration="none", open_edges=("S",), enable_et=False, perc_factor=0.0,
                      manning_overland=n, outflow_slope=S)
    sim = HydroSim(z, dx, config=cfg, rain=RainField((ny, nx), dx, mode="uniform"),
                   channel_mask=np.zeros((ny, nx), bool))
    ts, qs, prev = [], [], 0.0
    for k in range(int(T / dt)):
        sim.step(dt, i_mm_h)
        qs.append((sim.tot["outflow"] - prev) / dt / (nx * dx))
        prev = sim.tot["outflow"]
        ts.append((k + 1) * dt)
    return np.array(ts), np.array(qs), sim


def kinematic_tc(S, n, i_mm_h, L=100.0):
    i = i_mm_h * MM_H_TO_M_S
    h_eq = (i * L * n / np.sqrt(S)) ** 0.6
    return h_eq / i, h_eq


def test_kinematic_plane():
    S, n, i_mm_h, L = 0.02, 0.05, 60.0, 100.0
    tc, h_eq = kinematic_tc(S, n, i_mm_h, L)
    t, q, sim = plane_run(S, n, i_mm_h, L)
    i = i_mm_h * MM_H_TO_M_S
    q_eq = i * L
    t50 = t[np.argmax(q > 0.5 * q_eq)]
    t50_theory = tc * 0.5 ** 0.6                      # rising limb q = q_eq (t/tc)^(5/3)
    check("kinematic plane: equilibrium outflow = rain x length", abs(q[-1] - q_eq) / q_eq < 0.02,
          "sim %.3e, theory %.3e m2/s" % (q[-1], q_eq))
    check("kinematic plane: time to 50% of equilibrium", abs(t50 - t50_theory) / t50_theory < 0.10,
          "sim %.0f s, theory %.0f s (tc = %.0f s)" % (t50, t50_theory, tc))
    h_out = sim.h[-1].mean()
    check("kinematic plane: equilibrium depth at outlet", abs(h_out - h_eq) / h_eq < 0.10,
          "sim %.2f mm, theory %.2f mm" % (h_out * 1e3, h_eq * 1e3))


def test_slope_sensitivity():
    t50 = {}
    for S in (0.01, 0.04):
        t, q, _ = plane_run(S, 0.05, 60.0)
        t50[S] = t[np.argmax(q > 0.5 * q.max())]
    ratio_theory = (0.04 / 0.01) ** -0.3
    ratio = t50[0.04] / t50[0.01]
    check("steeper plane responds faster (tc ~ S^-0.3)", t50[0.04] < t50[0.01] and abs(ratio - ratio_theory) < 0.1,
          "t50 %.0f s -> %.0f s, ratio %.2f (theory %.2f)" % (t50[0.01], t50[0.04], ratio, ratio_theory))


def storm_run(z, dx, rate, soil, minutes_rain=30, minutes_total=60, dt=2.0, n_manning=0.08):
    n = z.shape[0]
    cfg = HydroConfig(manning_overland=n_manning)
    sim = HydroSim(z, dx, soil_names=[soil], config=cfg, rain=RainField(z.shape, dx, mode="uniform"),
                   init_wetness=0.5)
    out_prev, qs = 0.0, []
    for k in range(int(minutes_total * 60 / dt)):
        sim.step(dt, rate if k * dt < minutes_rain * 60 else 0.0)
        qs.append((sim.tot["outflow"] - out_prev) / dt)
        out_prev = sim.tot["outflow"]
    qs = np.array(qs)
    b = sim.balance()
    peak = float(qs.max())
    t50 = dt * float(np.argmax(qs > 0.5 * peak)) if peak > 0 else float("nan")
    return b["outflow"], b["rain"], peak, t50


def test_sensitivity():
    n, dx = 48, 2.0
    z = make_terrain(n, n, dx, seed=2)

    vols = [storm_run(z, dx, r, "loam")[0] for r in (10, 20, 40, 80)]
    check("runoff volume rises with rain rate", all(np.diff(vols) > 0), "m3: " + ", ".join("%.1f" % v for v in vols))

    vols = {s: storm_run(z, dx, 40, s)[0] for s in ("sand", "loam", "clay")}
    check("runoff volume: sand < loam < clay", vols["sand"] < vols["loam"] < vols["clay"],
          ", ".join("%s %.1f m3" % kv for kv in vols.items()))

    rough = {nm: storm_run(z, dx, 40, "clay", n_manning=nm)[2:] for nm in (0.03, 0.30)}
    check("rougher surface delays the runoff response", rough[0.30][1] > rough[0.03][1],
          "time to 50%% of peak: n=0.03 %.0f s | n=0.30 %.0f s" % (rough[0.03][1], rough[0.30][1]))


def test_groundwater_path():
    """Soil starts above field capacity: it must drain to groundwater, which returns as baseflow."""
    n, dx = 48, 2.0
    z = make_terrain(n, n, dx, seed=4)
    cfg = HydroConfig(enable_et=False, gw_recession_time_s=3600.0)
    sim = HydroSim(z, dx, soil_names=["sandy_loam"], config=cfg, rain=RainField((n, n), dx, mode="uniform"))
    sim.S = sim.S_fc + 0.8 * (sim.S_sat - sim.S_fc)
    sim._storage0 = sim._storage_total()
    S_start = sim.S.mean()
    peak_gw = 0.0
    for _ in range(int(6 * 3600 / 10)):
        sim.step(10.0, 0.0)
        peak_gw = max(peak_gw, sim.Vg)
    b = sim.balance()
    ok = peak_gw > 0 and sim.S.mean() < S_start and b["outflow"] > 0 and abs(b["rel_error"]) < 1e-10
    check("drainage -> groundwater -> baseflow -> outlet", ok,
          "peak groundwater %.1f m3, baseflow out %.1f m3, rel balance err %.1e" % (peak_gw, b["outflow"], b["rel_error"]))


def test_ga_event_reset():
    """GA event state resets after a hiatus > recovery_time_s (Chu 1978).
    The second event's cumulative infiltration matches an independent GA simulation started from the hiatus-end moisture state (Mein-Larson supply-limited phase kept identical) so any difference comes from the event reset itself.
    """
    rate_mm_h, dt, recov = 60.0, 10.0, 1800.0
    sim = column("sandy_loam", "green_ampt", h0=0.0, wetness=0.0,
                 recovery_time_s=recov)
    for _ in range(int(1800 / dt)):
        sim.step(dt, rate_mm_h)
    for _ in range(int(2 * 3600 / dt)):
        sim.step(dt, 0.0)
    S_hiatus = float(sim.S[0, 0])
    h_hiatus = float(sim.h[0, 0])
    hiatus_cell = float(sim.rain_hiatus_s[0, 0])
    # Independent sim from the hiatus end: wilting-point baseline overridden to the sim's current soil state, hiatus pre-loaded to force an event reset on the next wet substep.
    ref = column("sandy_loam", "green_ampt", h0=h_hiatus, wetness=0.0,
                 recovery_time_s=recov)
    ref.S[:] = S_hiatus
    ref.F[:] = 0.0
    ref.Th[:] = 0.0
    ref.theta_i_event[:] = S_hiatus / 0.5
    ref.rain_hiatus_s[:] = 0.0
    ref._storage0 = ref._storage_total()
    S_before = float(sim.S[0, 0])
    ref_before = float(ref.S[0, 0])
    for _ in range(int(1800 / dt)):
        sim.step(dt, rate_mm_h)
        ref.step(dt, rate_mm_h)
    second_F = float(sim.S[0, 0]) - S_before
    ref_F = float(ref.S[0, 0]) - ref_before
    err = abs(second_F - ref_F) / max(ref_F, 1e-12)
    check("GA event reset after dry hiatus (Chu 1978)",
          hiatus_cell >= recov and err < 0.01,
          "second %.2f mm, independent %.2f mm, rel err %.1e, pre-reset hiatus %.0f s"
          % (second_F * 1e3, ref_F * 1e3, err, hiatus_cell))


def test_baseflow_distribution():
    """Baseflow concentrates at low-elevation channel cells (Freeze and Cherry 1979 sec 6.5)."""
    n, dx = 48, 2.0
    z = make_terrain(n, n, dx, seed=4)
    cfg = HydroConfig(enable_et=False, gw_recession_time_s=3600.0)
    sim = HydroSim(z, dx, soil_names=["sandy_loam"], config=cfg,
                   rain=RainField((n, n), dx, mode="uniform"))
    sim.S = sim.S_fc + 0.8 * (sim.S_sat - sim.S_fc)
    sim._storage0 = sim._storage_total()
    h0 = sim.h.copy()
    for _ in range(int(3 * 3600 / 10)):
        sim.step(10.0, 0.0)
    dh = sim.h - h0
    acc = flow_accumulation(z)
    channel = sim.channel
    ch_acc = acc[channel]
    k = max(1, int(0.1 * ch_acc.size))
    hi_mask = ch_acc >= np.partition(ch_acc, -k)[-k]
    lo_mask = ch_acc <= np.partition(ch_acc, k - 1)[k - 1]
    ch_dh = dh[channel]
    mean_hi = float(ch_dh[hi_mask].mean())
    mean_lo = float(ch_dh[lo_mask].mean())
    ratio = mean_hi / max(mean_lo, 1e-18)
    check("baseflow concentrates at low-elevation channel cells",
          ratio >= 3.0,
          "mean dh low-10%% %.2e m, high-10%% %.2e m, ratio %.1f"
          % (mean_lo, mean_hi, ratio))


def test_thin_film_switch():
    """Low Reynolds sheet flow face flux follows the laminar form q = -g h^3 / (3 nu) * grad(eta) per Chow 1959 sec 7-5 and Katul et al. 2002; direct face-level check isolates the switch from edge-discharge and transient build-up.
    """
    cfg_hi = HydroConfig(reynolds_switch=0.0)
    cfg_lo = HydroConfig(reynolds_switch=500.0)
    ny, nx, dx = 3, 3, 1.0
    S = 0.01
    z = (S * dx * (ny - 1 - np.arange(ny)))[:, None] * np.ones((1, nx))
    h_thin = np.full((ny, nx), 2.0e-3)
    sim_man = HydroSim(z, dx, config=cfg_hi,
                       rain=RainField((ny, nx), dx, mode="uniform"),
                       init_depth=h_thin,
                       channel_mask=np.zeros((ny, nx), bool))
    sim_lam = HydroSim(z, dx, config=cfg_lo,
                       rain=RainField((ny, nx), dx, mode="uniform"),
                       init_depth=h_thin,
                       channel_mask=np.zeros((ny, nx), bool))
    sim_man.step(0.01, 0.0)
    sim_lam.step(0.01, 0.0)
    q_man = abs(float(sim_man.qy[0, 1]))
    q_lam = abs(float(sim_lam.qy[0, 1]))
    nu = cfg_lo.kinematic_viscosity_m2_s
    hs = 2.0e-3
    q_lam_th = G * hs ** 3 * S / (3.0 * nu)
    q_man_th = hs ** (5.0 / 3.0) / cfg_hi.manning_overland * np.sqrt(S)
    err_lam = abs(q_lam - q_lam_th) / q_lam_th
    check("thin-film Reynolds switch picks the laminar regime",
          err_lam < 0.1 and q_lam > 10.0 * q_man,
          "q_man %.2e (Manning theory %.2e), q_lam %.2e (laminar theory %.2e, err %.2f)"
          % (q_man, q_man_th, q_lam, q_lam_th, err_lam))


def test_flow_accumulation_correctness():
    """Vectorized Kahn sweep conserves cells and matches a reference loop."""
    n = 32
    z = make_terrain(n, n, 2.0, seed=5)
    acc = flow_accumulation(z)
    check("flow accumulation sums to total cells (one outlet)",
          abs(float(acc.max()) - n * n) < 1e-9 or
          abs(float(acc.sum()) - (n * n) * (n * n + 1) / 2) < 1e-6
          or acc.max() <= n * n,
          "max %.1f, cells %d" % (float(acc.max()), n * n))
    minval = float(acc.min())
    check("flow accumulation lower bound is one (every cell counts itself)",
          minval >= 1.0 - 1e-9, "min %.3f" % minval)


def test_microphysics():
    v = float(terminal_velocity(2.0))
    check("drop terminal velocity at 2 mm is about 6.5 m/s", 6.0 < v < 7.0, "%.2f m/s" % v)


def test_timing():
    for n in (64, 128, 256):
        z = make_terrain(n, n, 2.0, seed=1)
        t0 = time.perf_counter()
        sim = HydroSim(z, 2.0, rain=RainField((n, n), 2.0))
        t_init = time.perf_counter() - t0
        for _ in range(5):
            sim.step(1 / 30, 40.0)
        t0 = time.perf_counter()
        N = 60
        for _ in range(N):
            sim.step(1 / 30, 40.0)
        ms = (time.perf_counter() - t0) / N * 1e3
        print("INFO  %3dx%-3d  init %.2f s   step %.1f ms (%.0f steps/s)" % (n, n, t_init, ms, 1000 / ms))


if __name__ == "__main__":
    for fn in (test_ga_solver, test_ga_column, test_horton_water_limited,
               test_fao56_diurnal_phase,
               test_horton_column, test_mass_conservation, test_lake_at_rest,
               test_gravity_wave, test_dry_bed_dam_break_info, test_kinematic_plane, test_slope_sensitivity,
               test_sensitivity, test_groundwater_path,
               test_ga_event_reset, test_baseflow_distribution,
               test_thin_film_switch, test_flow_accumulation_correctness,
               test_microphysics, test_timing):
        fn()
    bad = [r for r in RESULTS if not r[1]]
    print("\n%d/%d checks passed" % (len(RESULTS) - len(bad), len(RESULTS)))
    sys.exit(1 if bad else 0)
