"""Serve the real Python engine with a small deterministic river fixture."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "yellowstone_python"))
from yellowstone_python.service.live import LiveEngine
from yellowstone_python.river.river_transport import Cell, River
from yellowstone_python.service.server import live_server


def main() -> None:
    cells = [Cell("cell_" + str(i), 20., 10., 200., 15.) for i in range(3)]
    rows = [{"id": cell.id, "river_id": "test", "start_s_m": i * 20., "end_s_m": (i + 1) * 20., "center_s_m": (i + .5) * 20., "position_xyz": [0., 1., (i + .5) * 20.]} for i, cell in enumerate(cells)]
    geometry = {"river_features": {"test": {"points_xyz": [[0., 1., 0.], [0., 1., 60.]], "point_s_m": [0., 60.], "width_m": 10.}}}
    config = {"live": {"foodweb_interval_s": 10.}, "wildlife": [
        {"id": "brown_fixture", "species_id": "brown_trout"},
        {"id": "rainbow_fixture", "species_id": "rainbow_trout"}]}
    engine = LiveEngine(River(cells, 5., 15.), config, cells=rows, geometry=geometry, horizon_s=180., frame_interval_s=10., time_scale=1., start_worker=True)
    server = live_server(engine, port=18878)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        engine.close()


if __name__ == "__main__":
    main()
