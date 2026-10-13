"""Round-trip and CF-conformance tests for replay NetCDF export."""
import importlib.util
import unittest

HAS_NC = (importlib.util.find_spec("xarray") is not None
          and importlib.util.find_spec("netCDF4") is not None)


def _build_river_frames():
    from yellowstone_python.replay.river_transport import Cell, River
    cells = [Cell(f"c_{i:02d}", 20.0, 10.0, 220.0, 15.0,
                  dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
             for i in range(4)]
    river = River(cells, boundary_m3_s=8.0, boundary_c=17.5,
                  air_c=9.0)
    frames = river.run(600.0, dt_s=10.0, sample_s=120.0)
    ids = [c.id for c in cells]
    return frames, ids


@unittest.skipUnless(HAS_NC, "xarray/netCDF4 not installed")
class NcExportTests(unittest.TestCase):
    def test_frames_round_trip_bit_identical(self):
        import tempfile
        from pathlib import Path
        from yellowstone_python.replay.nc_export import (
            read_replay_netcdf,
            write_replay_netcdf,
        )
        frames, ids = _build_river_frames()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.nc"
            write_replay_netcdf(frames, ids, path)
            back = read_replay_netcdf(path)
        self.assertEqual(back["cell_ids"], ids)
        self.assertEqual([f["t_s"] for f in frames], back["times_s"])
        for frame, row in zip(frames, back["temperature_c"]):
            self.assertEqual(list(frame["temperature_c"]), row)


@unittest.skipUnless(HAS_NC, "xarray/netCDF4 not installed")
class CfComplianceTests(unittest.TestCase):
    def test_time_units_have_reference_epoch(self):
        import tempfile
        from pathlib import Path
        import xarray as xr
        from yellowstone_python.replay.nc_export import write_replay_netcdf
        frames, ids = _build_river_frames()
        frames[0]["wall_time"] = "2024-07-01T12:00:00Z"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.nc"
            write_replay_netcdf(frames, ids, path)
            with xr.open_dataset(path, decode_times=False) as data:
                units = data["time"].attrs["units"]
                calendar = data["time"].attrs["calendar"]
        self.assertTrue(units.startswith("seconds since "), units)
        self.assertIn("2024-07-01T12:00:00Z", units)
        self.assertEqual(calendar, "standard")

    def test_standard_name_is_water_temperature(self):
        import tempfile
        from pathlib import Path
        import xarray as xr
        from yellowstone_python.replay.nc_export import write_replay_netcdf
        frames, ids = _build_river_frames()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.nc"
            write_replay_netcdf(frames, ids, path)
            with xr.open_dataset(path, decode_times=False) as data:
                attrs = data["water_temperature"].attrs
        self.assertEqual(attrs["standard_name"], "water_temperature")
        self.assertNotEqual(attrs["standard_name"], "sea_water_temperature")

    def test_shape_mismatch_names_frame_index(self):
        import tempfile
        from pathlib import Path
        from yellowstone_python.replay.nc_export import write_replay_netcdf
        frames, ids = _build_river_frames()
        # Trim one cell from the second frame's temperature row.
        frames[1]["temperature_c"] = list(frames[1]["temperature_c"])[:-1]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.nc"
            with self.assertRaises(ValueError) as ctx:
                write_replay_netcdf(frames, ids, path)
        self.assertIn("frame 1", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
