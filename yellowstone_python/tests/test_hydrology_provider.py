"""Provider statuses, validation, cache keys, and a live hydrosim run."""
import pytest

from yellowstone_python.hydrology_provider import HydrologyProvider

from paths import TERRAIN_F32 as TERRAIN


def _weather(rain=2.0):
    return {"air_c": 7.0, "humidity": 0.45, "wind_speed_m_s": 2.0,
            "precipitation_rate_mm_h": rain}


def test_disabled_returns_status_without_sim():
    p = HydrologyProvider(terrain=None, enabled=False)
    snap = p.snapshot(weather=_weather(), hour=16.0)
    assert snap.status == "disabled"
    assert snap.ground_wetness_fraction is None


def test_missing_precipitation_named():
    p = HydrologyProvider(terrain=None)
    snap = p.snapshot(weather={"air_c": 7.0}, hour=16.0)
    assert snap.status == "no_precipitation_input"


def test_missing_terrain_named():
    p = HydrologyProvider(terrain=None)
    snap = p.snapshot(weather=_weather(), hour=16.0)
    assert snap.status == "no_terrain_input"


def test_missing_module_named_unavailable():
    p = HydrologyProvider(terrain=None, module_name="nonexistent_xyz")
    snap = p.snapshot(weather=_weather(), hour=16.0)
    assert snap.status == "no_terrain_input"


def test_bad_module_reports_unavailable():
    import numpy as np
    p = HydrologyProvider(terrain=np.zeros((8, 8)), module_name="nonexistent_xyz")
    snap = p.snapshot(weather=_weather(), hour=16.0)
    assert snap.status == "unavailable"
    assert snap.error is not None


def test_constructor_validation():
    import numpy as np
    terrain = np.zeros((8, 8))
    for kwargs in ({"ttl_s": 0.0}, {"ttl_s": -1.0}, {"sim_s": 0.0},
                   {"soil": ""}, {"grid": 0}, {"grid": True},
                   {"terrain_dx_m": 0.0}):
        with pytest.raises(ValueError):
            HydrologyProvider(terrain=terrain, **kwargs)
    with pytest.raises(ValueError):
        HydrologyProvider(terrain=terrain).snapshot(
            weather=[1.0], hour=16.0)


def test_cache_key_tracks_inputs():
    import numpy as np
    calls = []

    class Probe(HydrologyProvider):
        def _compute(self, **kwargs):
            calls.append(kwargs["rain_mm_h"])
            from yellowstone_python.hydrology_provider import HydrologySnapshot
            return HydrologySnapshot(kwargs["rain_mm_h"], None, {}, "ok")

    p = Probe(terrain=np.zeros((8, 8)))
    p.snapshot(weather=_weather(2.0), hour=16.0)
    p.snapshot(weather=_weather(2.0), hour=16.0)
    assert calls == [2.0]
    p.snapshot(weather=_weather(5.0), hour=16.0)
    assert calls == [2.0, 5.0]
    p.snapshot(weather=_weather(2.0), hour=17.0)
    assert calls == [2.0, 5.0, 2.0]


def test_hour_selects_hourly_rain():
    import numpy as np

    class Probe(HydrologyProvider):
        def _compute(self, **kwargs):
            from yellowstone_python.hydrology_provider import HydrologySnapshot
            return HydrologySnapshot(kwargs["rain_mm_h"], None, {}, "ok")

    p = Probe(terrain=np.zeros((8, 8)))
    weather = {"air_c": 7.0, "precipitation_mm_h_hourly": [1.0, 2.0, 3.0]}
    assert p.snapshot(weather=weather, hour=1.0).precipitation_rate_mm_h == 2.0
    assert p.snapshot(weather=weather, hour=4.0).precipitation_rate_mm_h == 2.0


def test_live_hydrosim_run():
    from yellowstone_python.hydrology_provider import import_hydrosim
    module, provenance = import_hydrosim()
    if module is None:
        pytest.skip("hydrosim not importable")
    from yellowstone_python.vegetation import load_terrain
    terrain = load_terrain(TERRAIN)
    p = HydrologyProvider(terrain=terrain, grid=16, sim_s=30.0)
    snap = p.snapshot(weather=_weather(2.0), hour=16.0)
    assert snap.status == "ok", snap.error
    assert 0.0 <= snap.ground_wetness_fraction <= 1.0
    assert snap.state["sim_grid"] == 16
    assert snap.state["soil"] == "sandy_loam"
