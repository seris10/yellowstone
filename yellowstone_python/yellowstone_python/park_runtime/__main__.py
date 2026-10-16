"""Runnable illustrative service. No Yellowstone predictions are implied."""
import argparse
from .reference_network import Reservoir, ReservoirNetwork
from .runtime import ParkRuntime
from .service import RuntimeService, make_server
from .state_store import StateStore

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8766)
    p.add_argument("--state", default="park_demo.sqlite3")
    args = p.parse_args()
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
    print(f"Illustrative park runtime at http://127.0.0.1:{args.port}; Ctrl+C saves committed state", flush=True)
    try:
        server.serve_forever(poll_interval=.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()
        saved = runtime.save_committed(store, "demo-world", service.presentation_s)
        store.close()
        print(f"Saved committed checkpoint at {saved:.3f} physical seconds")

if __name__ == "__main__":
    main()
