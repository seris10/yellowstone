"""Process views must remain tied to their actual checked outputs."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def load(name):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder, domains, processes = load("build_public"), load("domain_data"), load("process_data")


@pytest.fixture(scope="module")
def selected():
    try:
        path = builder.selected_build(builder.ROOT)
    except (FileNotFoundError, ValueError):
        pytest.skip("Checked model artifacts are local; bundled dataset tests run in public clones")
    checked = domains.CheckedBuild(path)
    systems = domains.export_systems(path)
    return checked, systems, processes.process_views(checked, systems)


def test_every_implemented_process_has_direct_data_or_existing_river_view(selected):
    checked, systems, catalog = selected
    snapshot = builder.public_snapshot(checked.path)
    implemented = {row["id"] for row in snapshot["nodes"] if row["implementation"] != "research"}
    assert set(catalog) | {"transport", "shading"} == implemented
    for views in catalog.values():
        assert views and len({view["id"] for view in views}) == len(views)
        for view in views:
            if view["kind"] == "native":
                dataset = systems[view["system"]]
                assert any(row["id"] == view["quantity"] for group in ["variables", "grids", "profiles", "tables"] for row in dataset[group])
            else:
                assert view["sources"]
                assert all(source["sha256"] in checked.manifest["output_artifact_hashes"].values() for source in view["sources"])
    public = json.dumps(catalog)
    assert "/Users/" not in public and "execution_evidence" not in public


def test_weather_uses_every_saved_physical_time_and_steam_uses_its_own_report(selected):
    checked, systems, catalog = selected
    frames = checked.document("ecosystem.godot.json")["python_series"]
    weather = next(row for row in systems["atmosphere"]["series"] if row["variable_id"] == "air_temperature")
    assert weather["times"] == [frame["t_s"] for frame in frames]
    assert weather["values"] == [frame["weather"]["air_temperature_c"] for frame in frames]
    assert weather["times"][-1] > 60
    assert weather["values"][0] != weather["values"][-1]
    report = checked.document("steam_microclimate.json")["report"]
    temperature, humidity = catalog["steam"][:2]
    assert [row["y"] for row in temperature["points"]] == [report["upwind_air_c"], report["downwind_air_c"]]
    assert [row["y"] for row in humidity["points"]] == [report["upwind_rh"] * 100, report["downwind_rh"] * 100]
    assert all("times" not in view for view in catalog["steam"])
    assert not any(view.get("quantity") in {"air_temperature", "wind_speed"} for view in catalog["steam"])


def test_heat_budgets_boundary_and_outlet_retain_exact_samples_and_units(selected):
    checked, _, catalog = selected
    replay = checked.document("river_replay.json")["replay"]
    surface = catalog["surface"][0]
    assert surface["unit"] == "MJ"
    assert surface["values"] == [frame["budget"]["surface_exchange_j"] * 1e-6 for frame in replay["frames"]]
    outlet = catalog["outlet"][0]
    assert outlet["values"] == [frame["temperature_c"][-1] for frame in replay["frames"]]
    upstream = {view["id"]: view for view in catalog["boundary"]}
    assert upstream["boundary_c"]["points"][0]["y"] == replay["forcing"]["boundary_c"]["values"][0]
    assert upstream["boundary_m3_s"]["points"][0]["y"] == replay["forcing"]["boundary_m3_s"]
    assert catalog["et"][0]["quantity"] == "reference_et"
    assert catalog["outflow_cooling"][0]["quantity"] == "outflow_temperature"
    assert catalog["fish"][0]["quantity"] == "feeding_brown_trout"


def test_mat_area_is_native_classified_cell_area_and_routes_have_no_fake_clock(selected):
    checked, _, catalog = selected
    import struct
    mat = checked.document("mat_state.json")
    expected = sum(value != mat["rasters"]["community"]["nodata"] for value, in struct.iter_unpack("<h", checked.binary("mat_community.i16")))
    assert sum(row["y"] for row in catalog["mat"][0]["points"]) == expected * mat["grid"]["cell_size_m"] ** 2
    assert catalog["grazers"][0]["routes"]
    assert "times" not in catalog["grazers"][0]


def test_corrupt_steam_artifact_blocks_export(tmp_path):
    documents = {"CHECKS.json": {"passed": True}, "steam_microclimate.json": {"report": {"upwind_air_c": 20, "downwind_air_c": 21, "upwind_rh": .4, "downwind_rh": .5}}}
    hashes = {}
    for name, value in documents.items():
        payload = json.dumps(value).encode()
        (tmp_path / name).write_bytes(payload)
        hashes[name] = hashlib.sha256(payload).hexdigest()
    (tmp_path / "BUILD.json").write_text(json.dumps({"checks_passed": True, "output_artifact_hashes": hashes}))
    (tmp_path / "steam_microclimate.json").write_text("{}")
    with pytest.raises(ValueError, match="Artifact hash mismatch"):
        processes.process_views(domains.CheckedBuild(tmp_path), {})
