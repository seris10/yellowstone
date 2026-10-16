"""Round-trip and CF-conformance tests for replay NetCDF export."""
import importlib.util
import pytest

HAS_NC = (importlib.util.find_spec("xarray") is not None
          and importlib.util.find_spec("netCDF4") is not None)


def _build_river_frames():
    from yellowstone_python.river.river_transport import Cell, River
    cells = [Cell(f"c_{i:02d}", 20.0, 10.0, 220.0, 15.0,
                  dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
             for i in range(4)]
    river = River(cells, boundary_m3_s=8.0, boundary_c=17.5,
                  air_c=9.0)
    frames = river.run(600.0, dt_s=10.0, sample_s=120.0)
    ids = [c.id for c in cells]
    return frames, ids


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_NC, reason='xarray/netCDF4 not installed')
def test_nc_export_frames_round_trip_bit_identical():
    import tempfile
    from pathlib import Path
    from yellowstone_python.river.nc_export import read_replay_netcdf, write_replay_netcdf
    frames, ids = _build_river_frames()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "replay.nc"
        write_replay_netcdf(frames, ids, path)
        back = read_replay_netcdf(path)
    assert back['cell_ids'] == ids
    assert [f['t_s'] for f in frames] == back['times_s']
    for frame, row in zip(frames, back["temperature_c"]):
        assert list(frame['temperature_c']) == row



@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_NC, reason='xarray/netCDF4 not installed')
def test_cf_compliance_time_units_have_reference_epoch():
    import tempfile
    from pathlib import Path
    import xarray as xr
    from yellowstone_python.river.nc_export import write_replay_netcdf
    frames, ids = _build_river_frames()
    frames[0]["wall_time"] = "2024-07-01T12:00:00Z"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "replay.nc"
        write_replay_netcdf(frames, ids, path)
        with xr.open_dataset(path, decode_times=False) as data:
            units = data["time"].attrs["units"]
            calendar = data["time"].attrs["calendar"]
    assert (units.startswith('seconds since ')), units
    assert '2024-07-01T12:00:00Z' in units
    assert calendar == 'standard'


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_NC, reason='xarray/netCDF4 not installed')
def test_cf_compliance_standard_name_is_water_temperature():
    import tempfile
    from pathlib import Path
    import xarray as xr
    from yellowstone_python.river.nc_export import write_replay_netcdf
    frames, ids = _build_river_frames()
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "replay.nc"
        write_replay_netcdf(frames, ids, path)
        with xr.open_dataset(path, decode_times=False) as data:
            attrs = data["water_temperature"].attrs
    assert attrs['standard_name'] == 'water_temperature'
    assert attrs['standard_name'] != 'sea_water_temperature'


@pytest.mark.needs_science
@pytest.mark.skipif(not HAS_NC, reason='xarray/netCDF4 not installed')
def test_cf_compliance_shape_mismatch_names_frame_index():
    import tempfile
    from pathlib import Path
    from yellowstone_python.river.nc_export import write_replay_netcdf
    frames, ids = _build_river_frames()
    # Trim one cell from the second frame's temperature row.
    frames[1]["temperature_c"] = list(frames[1]["temperature_c"])[:-1]
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "replay.nc"
        with pytest.raises(ValueError) as ctx:
            write_replay_netcdf(frames, ids, path)
    assert 'frame 1' in str(ctx.value)



