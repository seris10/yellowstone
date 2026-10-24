"""Runnable illustrative service. No Yellowstone predictions are implied."""
import argparse
import signal
from .reference_network import Reservoir, ReservoirNetwork
from .runtime import ParkRuntime
from .service import RuntimeService, make_server
from .state_store import StateStore

def _interrupt(signum, frame):
    """Route the termination signal to the KeyboardInterrupt shutdown path."""
    raise KeyboardInterrupt

def serve_firehole(port: int) -> None:
    """Serve the published Firehole replay with segment residency; segment state is not saved."""
    from yellowstone_python.common.io import load_json
    from yellowstone_python.common.provenance import default_world_root
    from .residency import firehole_residency
    residency, chainage = firehole_residency(load_json(default_world_root() / "data" / "river_replay.json"))
    try:
        service = RuntimeService(residency.runtime, horizon_s=residency.quantum_s, residency=residency,
                                 chainage=chainage)
        server = make_server(service, port=port)
        service.start()
        signal.signal(signal.SIGTERM, _interrupt)
        print(f"Illustrative Firehole residency at http://127.0.0.1:{port}; Ctrl+C or SIGTERM stops it", flush=True)
        try:
            server.serve_forever(poll_interval=.2)
        except KeyboardInterrupt:
            pass
        finally:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
            server.server_close()
            service.close()
    finally:
        residency.close()
    print("Stopped; segment checkpoints are not persistable, so no state was saved")

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--state", default="park_demo.sqlite3")
    p.add_argument("--firehole", action="store_true",
                   help="serve the published Firehole replay with focus-driven segment residency; no state file")
    args = p.parse_args()
    if args.firehole:
        serve_firehole(args.port)
        return
    domain = ReservoirNetwork("demo.catchment", [
        Reservoir.at_temperature("upstream", 1000., 12., .002),
        Reservoir.at_temperature("branch_a", 500., 10., .001),
        Reservoir.at_temperature("branch_b", 500., 15., .001),
        Reservoir.at_temperature("confluence", 1500., 11., .001)],
        [("upstream", "branch_a", .6), ("upstream", "branch_b", .4),
         ("branch_a", "confluence", 1.), ("branch_b", "confluence", 1.)],
        {"upstream": {"flow_m3s": 2., "temperature_c": 13.}})
    runtime = ParkRuntime([domain])
    store = StateStore(args.state)
    runtime.load_committed(store, "demo-world")
    service = RuntimeService(runtime)
    server = make_server(service, port=args.port)
    service.start()
    signal.signal(signal.SIGTERM, _interrupt)
    print(f"Illustrative park runtime at http://127.0.0.1:{args.port}; Ctrl+C or SIGTERM saves committed state", flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        server.server_close()
        service.close()
        saved = runtime.save_committed(store, "demo-world", service.presentation_s)
        store.close()
        print(f"Saved committed checkpoint at {saved:.3f} physical seconds")

if __name__ == "__main__":
    main()
