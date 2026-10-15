"""Provider statuses, validation, cache keys, and a live hydrosim run."""
import pytest

from yellowstone_python.land.hydrology_provider import HydrologyProvider



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
            from yellowstone_python.land.hydrology_provider import HydrologySnapshot
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
            from yellowstone_python.land.hydrology_provider import HydrologySnapshot
            return HydrologySnapshot(kwargs["rain_mm_h"], None, {}, "ok")

    p = Probe(terrain=np.zeros((8, 8)))
    weather = {"air_c": 7.0, "precipitation_mm_h_hourly": [1.0, 2.0, 3.0]}
    assert p.snapshot(weather=weather, hour=1.0).precipitation_rate_mm_h == 2.0
    assert p.snapshot(weather=weather, hour=4.0).precipitation_rate_mm_h == 2.0


@pytest.mark.needs_science
def test_live_hydrosim_run():
    from yellowstone_python.land.hydrology_provider import import_hydrosim
    module, provenance = import_hydrosim()
    if module is None:
        pytest.skip("hydrosim not importable")
    from yellowstone_python.land.vegetation import load_terrain
    terrain = load_terrain(TERRAIN)
    p = HydrologyProvider(terrain=terrain, grid=16, sim_s=30.0)
    snap = p.snapshot(weather=_weather(2.0), hour=16.0)
    assert snap.status == "ok", snap.error
    assert 0.0 <= snap.ground_wetness_fraction <= 1.0
    assert snap.state["sim_grid"] == 16
    assert snap.state["soil"] == "sandy_loam"


def test_refuse_on_cfl_overflow(monkeypatch):
    """CFL overflow is carried in state and refused when the provider asks."""
    import sys
    import types
    import numpy as np

    fake = types.ModuleType("fake_hydrosim_cfl")
    fake.SOILS = {"sandy_loam": {}}

    class _Sim:
        def __init__(self, *args, **kwargs):
            pass

        def step(self, dt, rain):
            return {"cfl_exceeded_count": 3, "boundary_condition": "closed"}

        def soil_saturation(self):
            return np.full((4, 4), 0.5)

        def balance(self):
            return {"rel_error": 0.0}

    fake.HydroSim = _Sim
    fake.Climate = lambda **kwargs: None
    fake.RainField = lambda *args, **kwargs: None
    fake.HydroConfig = lambda **kwargs: None
    monkeypatch.setitem(sys.modules, "fake_hydrosim_cfl", fake)
    terrain = np.zeros((8, 8))

    flagged = HydrologyProvider(terrain=terrain, grid=4, sim_s=30.0,
                                module_name="fake_hydrosim_cfl")
    snap = flagged.snapshot(weather=_weather(), hour=16.0)
    assert snap.status == "ok", snap.error
    assert snap.state["cfl_exceeded_count"] == 3
    assert snap.state["boundary_condition"] == "closed"

    refusing = HydrologyProvider(terrain=terrain, grid=4, sim_s=30.0,
                                 module_name="fake_hydrosim_cfl",
                                 refuse_on_cfl_overflow=True)
    snap = refusing.snapshot(weather=_weather(), hour=16.0)
    assert snap.status == "refused_cfl_exceeded"
    assert snap.ground_wetness_fraction is None
    assert snap.state["cfl_exceeded_count"] == 3


def test_bundle_to_provider_to_weather(tmp_path):
    """Meteorological bundle precipitation reaches the provider and weather response."""
    import json
    from yellowstone_python.service.llm_backend import Backend

    bundle_origin_epoch = 1_791_072_000.0
    rows = []
    precipitation = []
    for i in range(24):
        epoch = bundle_origin_epoch + i * 3600.0
        rows.append([epoch, 7.0, 0.5, 2.0, 150.0, 0.3])
        precipitation.append(2.0 if i == 16 else 0.0)
    bundle = {
        "schema": "yellowstone.met_forcing.v1",
        "status": "measured_remote_not_calibrated",
        "fetched_at_utc": "2026-10-11T00:00:00+00:00",
        "elevation_m": 2245.0,
        "hourly": rows,
        "precipitation_mm_h": precipitation,
    }
    world = tmp_path / "world"
    derived = tmp_path / "derived"
    data = world / "data"
    data.mkdir(parents=True)
    derived.mkdir()
    (derived / "met.json").write_text(json.dumps(bundle))
    (data / "ecosystem.json").write_text(json.dumps(
        {"clock_hour": 16.0, "simulation_epoch_unix": bundle_origin_epoch,
         "weather": {"utc_offset_hours": 0.0}, "river_reaches": [],
         "patches": [], "wildlife": []}))
    (data / "placements.json").write_text(json.dumps({"trees": []}))
    (data / "placement_overrides.json").write_text(json.dumps(
        {"add": [], "remove": [], "replace": {}}))
    (data / "world.json").write_text(json.dumps({"pools": []}))
    (derived / "census.json").write_text(json.dumps(
        {"n": 0, "status": "stub", "trees": []}))

    class FakeProvider:
        """Stand-in provider that mirrors HydrologyProvider's contract."""

        def __init__(self):
            self.calls = []

        def snapshot(self, *, weather, hour):
            self.calls.append({"weather": dict(weather), "hour": hour})
            rain = weather.get("precipitation_rate_mm_h")
            if rain is None:
                return type("S", (), {
                    "status": "no_precipitation_input",
                    "ground_wetness_fraction": None,
                    "state": {"status": "no_precipitation_input"},
                })
            return type("S", (), {
                "status": "ok",
                "ground_wetness_fraction": 0.5,
                "state": {"status": "ok", "sim_grid": 8},
            })

    provider = FakeProvider()
    backend = Backend(world=world, derived=derived, hydrology=provider)
    response = backend.weather(epoch_unix=bundle_origin_epoch + 16 * 3600.0)

    assert response["schema_version"] == 2
    assert isinstance(response["generated_at_unix"], int)
    assert "solar" in response
    assert response["source"]["endpoint"] == "open-meteo_hourly_bundle"
    assert response["precipitation_status"] == "meteorological_model_forcing"
    assert response["precipitation_rate_mm_h"] == 2.0
    assert response["ground_wetness_fraction"] == 0.5
    assert response["source"]["hydrology_status"] == "ok"
    assert provider.calls, "hydrology provider must be called from weather"
    forwarded = provider.calls[-1]["weather"]
    assert forwarded["precipitation_rate_mm_h"] == 2.0

    dry_response = backend.weather(epoch_unix=bundle_origin_epoch)
    assert dry_response["precipitation_status"] == "meteorological_model_forcing"
    assert dry_response["precipitation_rate_mm_h"] == 0.0
    assert dry_response["source"]["hydrology_status"] == "ok"

pytestmark = pytest.mark.needs_world


@pytest.fixture(autouse=True)
def resolved_module_paths(monkeypatch, request, resolved_paths):
    """Provide path aliases from shared fixtures and restore them after each test."""
    import sys
    module = sys.modules[__name__]
    monkeypatch.setattr(module, 'TERRAIN', resolved_paths['TERRAIN_F32'], raising=False)
