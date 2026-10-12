"""Round-trip tests for replay NetCDF export."""
import importlib.util
import unittest

HAS_NC = (importlib.util.find_spec("xarray") is not None
          and importlib.util.find_spec("netCDF4") is not None)


@unittest.skipUnless(HAS_NC, "xarray/netCDF4 not installed")
class NcExportTests(unittest.TestCase):
    def test_frames_round_trip_bit_identical(self):
        import tempfile
        from pathlib import Path
        from yellowstone_python.replay.nc_export import (
            read_replay_netcdf,
            write_replay_netcdf,
        )
        from yellowstone_python.replay.river_transport import (
            Cell,
            River,
        )
        cells = [Cell(f"c_{i:02d}", 20.0, 10.0, 220.0, 15.0,
                      dispersion_m2_s=1.0, exchange_w_m2_k=12.0)
                 for i in range(4)]
        river = River(cells, boundary_m3_s=8.0, boundary_c=17.5,
                      air_c=9.0)
        frames = river.run(600.0, dt_s=10.0, sample_s=120.0)
        ids = [c.id for c in cells]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.nc"
            write_replay_netcdf(frames, ids, path)
            back = read_replay_netcdf(path)
        self.assertEqual(back["cell_ids"], ids)
        self.assertEqual([f["t_s"] for f in frames], back["times_s"])
        for frame, row in zip(frames, back["temperature_c"]):
            self.assertEqual(list(frame["temperature_c"]), row)


if __name__ == "__main__":
    unittest.main()
