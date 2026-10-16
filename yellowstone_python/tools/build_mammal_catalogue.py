"""Primary mammal catalogue and reproducible local encounter authoring."""
from __future__ import annotations

import argparse
from pathlib import Path

from yellowstone_python.common.io import load_json, sha256_file, write_json_atomic
from yellowstone_python.common.provenance import default_world_root
from yellowstone_python.land.mammal_catalogue import CATALOGUE_PATH, build_catalogue, load_catalogue
from yellowstone_python.land.mammals import MammalEcology, author_midway_encounters


def main(argv=None):
    """Compile cached primary records and generate independent authored encounter sidecars."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--npspecies-records", type=Path)
    parser.add_argument("--catalogue-out", type=Path, default=CATALOGUE_PATH)
    parser.add_argument("--world", type=Path, default=default_world_root())
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=54173)
    args = parser.parse_args(argv)
    paths = {"world": args.world / "data/world.json", "baseline_ecosystem": args.world / "data/ecosystem.json.pre-python",
             "terrain": args.world / "data/terrain.f32", "habitat_mask": args.world / "assets/textures/habitat_mask.png"}
    if args.out.resolve() in {p.resolve() for p in paths.values()} or args.catalogue_out.resolve() in {p.resolve() for p in paths.values()}:
        raise ValueError("mammal output cannot replace a protected world input")
    if args.npspecies_records:
        write_json_atomic(args.catalogue_out, build_catalogue(load_json(args.npspecies_records)), indent=1)
    catalogue = load_catalogue(args.catalogue_out)
    from yellowstone_python.authoring.mammal_encounters import habitat_mask_blocker
    from yellowstone_python.common.mammal_forcing import environmental_forcing
    from yellowstone_python.land.vegetation import load_terrain, terrain_fns
    from yellowstone_python.thermal_features.pool_crust import build_all
    before = {key: sha256_file(path) for key, path in paths.items()}
    world, baseline = load_json(paths["world"]), load_json(paths["baseline_ecosystem"])
    encounters = author_midway_encounters(world, terrain_fns(load_terrain(str(paths["terrain"]))), build_all(world["pools"]),
        patches=baseline["patches"], existing_actors=baseline["wildlife"], seed=args.seed, catalogue=catalogue,
        blocked=habitat_mask_blocker(args.world))
    model = MammalEcology(baseline["patches"], encounters["actors"], seed=args.seed, catalogue=catalogue)
    model.step(0., environmental_forcing(baseline["patches"], baseline.get("weather", {}), world["simulation_epoch_unix"]))
    document = {"schema": "yellowstone.mammals.v1", "status": "authored", "scientific_acceptance": "not_yet_accepted",
                "quantitative_uncertainty": "unknown", "mammals": model.snapshot(), "encounters": encounters,
                "sources": [{"id": key, "file": f"yellowstone_midway/{path.relative_to(args.world)}", "sha256": before[key]} for key, path in paths.items()],
                "catalogue_sha256": sha256_file(args.catalogue_out), "producer_sha256": sha256_file(Path(__file__))}
    if any(sha256_file(path) != before[key] for key, path in paths.items()):
        raise ValueError("mammal source input changed during authoring")
    write_json_atomic(args.out, document, indent=1)
    print(f"mammals: {catalogue['source_counts']}; {len(encounters['actors'])} authored display representatives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
