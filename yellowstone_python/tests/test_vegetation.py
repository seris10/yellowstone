from yellowstone_python.land.vegetation import guild_suitability, patch_step, propose_plantings, propose_plantings_reviewed


def test_thermal_excluded_for_lodgepole():
    assert guild_suitability("lodgepole_pine", "thermal_core", 5, 0.6) == 0.0
    assert guild_suitability("lodgepole_pine", "thermal_core", 5, 0.6,
                             in_exclusion=True) == 0.0
    assert guild_suitability("lodgepole_pine", "forest_lodgepole", 5, 0.6) > 0.3


def test_biomass_bounded_and_grazed():
    patches = [{"id": "m", "biomass": 0.8, "capacity": 1.0, "moisture": 0.6,
                "growth_per_hour": 0.012}]
    out, _ = patch_step(patches, hour=12.0, dt_s=3600.0)
    assert 0.0 <= out[0]["biomass"] <= 1.0
    grazers = {"g1": {"patch_id": "m", "active": True,
                      "rate_per_second": 1.5e-06}}
    out2, led = patch_step(patches, hour=12.0, dt_s=3600.0, grazers=grazers)
    assert out2[0]["biomass"] < out[0]["biomass"]  # grazing debits growth


def test_proposals_deterministic_and_stable():
    kw = dict(guild="lodgepole_pine", center_xz=(-360, 260), radius_m=30,
              count=10, seed=7, habitat_id="forest_edge")
    a = propose_plantings(**kw)
    b = propose_plantings(**kw)
    assert [r["stable_id"] for r in a] == [r["stable_id"] for r in b]
    assert len(a) == 10 and len({r["stable_id"] for r in a}) == 10


def _flat_terrain():
    return (lambda x, z: 12.0), (lambda x, z: 5.0)


def test_reviewed_enforces_separation_and_suitability():
    kw = dict(guild="lodgepole_pine", center_xz=(0, 0), radius_m=30,
              count=20, seed=7, habitat_id="forest_edge",
              terrain_fn=_flat_terrain(),
              patches=[{"id": "p", "center_xz": [0, 0], "radius_m": 200,
                        "moisture": 0.6}],
              suitability_threshold=0.12)
    a, log = propose_plantings_reviewed(**kw)
    b, _ = propose_plantings_reviewed(**kw)
    assert [r["stable_id"] for r in a] == [r["stable_id"] for r in b]
    for i, r1 in enumerate(a):
        for r2 in a[i + 1:]:
            import math
            assert math.hypot(r1["x"] - r2["x"], r1["z"] - r2["z"]) >= 6.0 - 1e-6
        assert r1["suitability"] >= 0.12
        assert "y" in r1  # terrain-grounded elevation
    assert any(r["decision"] == "reject" for r in log)  # ledger records skips


def test_reviewed_ids_derive_from_cells():
    a, _ = propose_plantings_reviewed(
        "lodgepole_pine", (0, 0), 30, 5, 7, terrain_fn=_flat_terrain(),
        patches=[{"id": "p", "center_xz": [0, 0], "radius_m": 200,
                   "moisture": 0.6}])
    assert all(r["stable_id"].startswith("prop_lodgepole_pine_7_") for r in a)


def test_review_honors_suitability_threshold():
    # Suitability here is about 0.095 for each candidate: below the default 0.12 floor and above an explicit 0.0 gate.
    from yellowstone_python.authoring.review_proposals import review
    kw = dict(guild="meadow_grass", center_xz=(0, 0), radius_m=30,
              count=10, seed=11, habitat_id="dry_meadow",
              terrain_fn=_flat_terrain(),
              patches=[{"id": "p", "center_xz": [0, 0], "radius_m": 200,
                        "moisture": 0.1}],
              canopy=0.9, suitability_threshold=0.0)
    proposals, _ = propose_plantings_reviewed(**kw)
    assert len(proposals) == 10
    assert all(r["suitability"] < 0.12 for r in proposals)
    sample, slope = _flat_terrain()
    default_ok, _ = review(proposals, [], sample, slope, [],
                           lambda x, z: 0.1, canopy=0.9)
    assert default_ok == []
    custom_ok, _ = review(proposals, [], sample, slope, [],
                          lambda x, z: 0.1, canopy=0.9,
                          suitability_threshold=0.0)
    assert len(custom_ok) == 10


def test_patch_step_refuses_invalid_parameters():
    import pytest
    ok = [{"id": "m", "biomass": 0.5, "capacity": 1.0, "moisture": 0.5}]
    with pytest.raises(ValueError, match="dt_s"):
        patch_step(ok, hour=12.0, dt_s=-1.0)
    with pytest.raises(ValueError, match="dt_s"):
        patch_step(ok, hour=12.0, dt_s=float("nan"))
    with pytest.raises(ValueError, match="biomass"):
        patch_step([{"id": "m", "biomass": -0.1}], hour=12.0, dt_s=60.0)
    with pytest.raises(ValueError, match="growth_per_hour"):
        patch_step([{"id": "m", "biomass": 0.5, "growth_per_hour": -1.0}],
                   hour=12.0, dt_s=60.0)
    with pytest.raises(ValueError, match="duplicate patch id"):
        patch_step([{"id": "m", "biomass": 0.5}, {"id": "m", "biomass": 0.5}],
                   hour=12.0, dt_s=60.0)
    with pytest.raises(ValueError, match="rate_per_second"):
        patch_step(ok, hour=12.0, dt_s=60.0,
                   grazers={"g": {"patch_id": "m", "active": True,
                                  "rate_per_second": -0.5}})


def test_habitat_moisture_at_is_order_independent():
    from yellowstone_python.land.vegetation import habitat_moisture_at, moisture_at
    patches = [{"id": "far", "center_xz": [50, 0], "radius_m": 200,
                "moisture": 0.9, "habitat": "wet_meadow"},
               {"id": "near", "center_xz": [5, 0], "radius_m": 50,
                "moisture": 0.2, "habitat": "dry_meadow"}]
    a = habitat_moisture_at(0, 0, patches)
    b = habitat_moisture_at(0, 0, list(reversed(patches)))
    assert a == b == ("dry_meadow", 0.2)
    assert moisture_at(0, 0, patches) == 0.2
    # Outside every patch: the default habitat and moisture.
    assert habitat_moisture_at(5000, 5000, patches) == ("unsuitable_matrix",
                                                        0.2)


def test_terrain_fns_refuse_bad_shape_and_nonfinite():
    import numpy as np
    import pytest
    from yellowstone_python.land.vegetation import GRID, terrain_fns
    with pytest.raises(ValueError, match="shape"):
        terrain_fns(np.zeros((8, 8)))
    bad = np.zeros((GRID, GRID), dtype=np.float64)
    bad[10, 10] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        terrain_fns(bad)


def test_load_terrain_refuses_nonfinite(tmp_path):
    import numpy as np
    import pytest
    from yellowstone_python.land.vegetation import GRID, load_terrain
    h = np.zeros(GRID * GRID, dtype="<f4")
    h[5] = np.inf
    path = tmp_path / "terrain.f32"
    path.write_bytes(h.tobytes())
    with pytest.raises(ValueError, match="NaN or infinite"):
        load_terrain(str(path))


def test_propose_plantings_reviewed_applies_constraints():
    class _Pc:
        def excluded(self, x, z):
            return x > 0.0

    kw = dict(guild="lodgepole_pine", center_xz=(0, 0), radius_m=30,
              count=50, seed=7, habitat_id="forest_edge",
              terrain_fn=_flat_terrain(),
              patches=[{"id": "p", "center_xz": [0, 0], "radius_m": 200,
                        "moisture": 0.6}],
              suitability_threshold=0.12,
              constraints=_Pc())
    accepted, log = propose_plantings_reviewed(**kw)
    for r in accepted:
        assert r["x"] <= 0.0
    assert any(row.get("reason") == "placement_constraints_exclusion"
               for row in log)


def test_propose_plantings_reviewed_rejects_bad_constraints():
    import pytest
    with pytest.raises(TypeError):
        propose_plantings_reviewed(
            "lodgepole_pine", (0, 0), 30, 5, 7,
            terrain_fn=_flat_terrain(),
            patches=[{"id": "p", "center_xz": [0, 0], "radius_m": 200,
                      "moisture": 0.6}],
            constraints=object())


def test_render_suitability_validates_inputs_and_creates_dirs(tmp_path):
    import pytest
    from yellowstone_python.land.vegetation import habitat_moisture_at, render_suitability_png
    terrain_fn = (lambda x, z: 0.0, lambda x, z: 5.0)
    patches = [{"id": "p", "center_xz": [0, 0], "radius_m": 100,
                "moisture": 0.5, "habitat": "forest_edge"}]
    for kwargs in ({"guild": "bogus"}, {"size": 1},
                   {"bbox": (0, 0, 0, 10)}, {"bbox": (0, 0, -10, 10)},
                   {"canopy": 1.5}, {"bbox": (0, 0, float("nan"), 10)},
                   {"bbox": (0, 0, 10)}):
        call = dict(guild="lodgepole_pine", size=4, path=str(tmp_path / "s.png"),
                    bbox=(-10, -10, 10, 10), terrain_fn=terrain_fn,
                    patches=patches, shells=[])
        call.update(kwargs)
        with pytest.raises(ValueError):
            render_suitability_png(**call)
    out = tmp_path / "nested" / "deeper" / "s.png"
    assert render_suitability_png(
        "lodgepole_pine", 4, str(out), bbox=(-10, -10, 10, 10),
        terrain_fn=terrain_fn, patches=patches, shells=[]) == str(out)
    assert out.exists()
