from yellowstone_python.insects_birds import (DEFAULT_DIETS, bird_timing,
                                                   daily_trace, foraging_state,
                                                   holling_type_ii,
                                                   insect_activity,
                                                   step_compartments,
                                                   step_resource,
                                                   update_wildlife,
                                                   update_wildlife_from_intake)


def test_activity_gates():
    sunny = insect_activity(sun=1.0, air_c=22.0, cloud=0.1, moisture=0.8,
                            resource=0.8, wind_mps=0.5, flowering=0.7)
    assert foraging_state(sunny) == "hover"
    storm = insect_activity(sun=0.1, air_c=9.0, cloud=0.9, moisture=0.8,
                            resource=0.8, wind_mps=9.0, flowering=0.2)
    assert foraging_state(storm) == "inactive"
    assert 0.0 <= storm < sunny <= 1.0


def test_bird_timing_follows_activity():
    perch_hi, forage_hi = bird_timing(0.9, 10.0, 17.0)
    perch_lo, forage_lo = bird_timing(0.05, 10.0, 17.0)
    assert perch_hi < perch_lo and forage_hi > forage_lo


def test_resource_recovers():
    r = step_resource(0.5, 0.06, sun=1.0, moisture=0.8, consumed=0.0,
                      dt_s=3600.0)
    assert r > 0.5 and r <= 1.0


def test_dipper_raven_retuned_not_replaced():
    wl = [{"id": "dipper_01", "patch_id": "bridge_riparian",
           "perch_seconds": 10.0, "forage_seconds": 17.0},
          {"id": "bison_01", "patch_id": "north_meadow",
           "graze_seconds": 24}]
    out = update_wildlife(wl, {"bridge_riparian": 0.8})
    dip = next(r for r in out if r["id"] == "dipper_01")
    assert dip["perch_seconds"] < 10.0 and dip["forage_seconds"] > 17.0
    assert next(r for r in out if r["id"] == "bison_01")["graze_seconds"] == 24


def test_daily_trace_proves_gating():
    tr = daily_trace({"moisture": 0.85, "insect_resource": 0.8},
                     {"cloud": 0.9}, wind_mps=9.0, flowering=0.2)
    assert all(s["state"] == "inactive" for s in tr)
    tr2 = daily_trace({"moisture": 0.85, "insect_resource": 0.8},
                      {"cloud": 0.05}, wind_mps=0.3, flowering=0.8)
    assert any(s["state"] == "hover" for s in tr2)


def test_holling_saturates():
    assert holling_type_ii(0.0, 1.2, 0.4) == 0.0
    assert holling_type_ii(100.0, 1.2, 0.4) <= 1 / 0.4 + 1e-9
    assert holling_type_ii(2.0, 1.2, 0.4) > holling_type_ii(0.5, 1.2, 0.4)


def test_warmer_water_emerges_more():
    kw = dict(dt_s=86400.0, consumers=None)
    f0 = dict(sun=1.0, air_c=20.0, cloud=0.1, moisture=0.7, flowering=0.6,
              wind_mps=0.5)
    _, warm = step_compartments({"Nt": 0.5, "Nb": 0.5, "Ne": 0.1},
                                {**f0, "water_c": 18.0}, **kw)
    _, cool = step_compartments({"Nt": 0.5, "Nb": 0.5, "Ne": 0.1},
                                {**f0, "water_c": 8.0}, **kw)
    assert warm["emergence"] > cool["emergence"]


def test_wind_suppresses_air_not_water():
    f = dict(sun=1.0, air_c=20.0, cloud=0.1, moisture=0.7, flowering=0.6,
             water_c=15.0)
    calm, _ = step_compartments({"Nt": 0.5, "Nb": 0.5, "Ne": 0.4},
                                {**f, "wind_mps": 0.2}, dt_s=3600.0,
                                consumers=None)
    windy, _ = step_compartments({"Nt": 0.5, "Nb": 0.5, "Ne": 0.4},
                                 {**f, "wind_mps": 12.0}, dt_s=3600.0,
                                 consumers=None)
    assert windy["Ne"] < calm["Ne"] and windy["Nb"] == calm["Nb"]


def test_consumption_depletes_shared_pools():
    f = dict(sun=1.0, air_c=20.0, cloud=0.1, moisture=0.7, flowering=0.6,
             water_c=15.0, wind_mps=0.5)
    s0 = {"Nt": 0.8, "Nb": 0.8, "Ne": 0.8}
    eaten, led = step_compartments(s0, f, dt_s=3600.0,
                                   consumers=DEFAULT_DIETS)
    assert sum(led["consumed_by"].values()) > 0
    assert eaten["Nb"] < s0["Nb"]  # dipper+trout benthic take is real
    wl = update_wildlife_from_intake(
        [{"id": "dipper_01", "perch_seconds": 10.0, "forage_seconds": 17.0},
         {"id": "raven_01", "perch_seconds": 18.0, "forage_seconds": 22.0}],
        {k: v for k, v in led["consumed_by"].items()})
    assert wl[0].get("intake_basis_prey_per_h") is not None
    assert wl[1]["forage_seconds"] >= 2.0  # generalist floor holds
