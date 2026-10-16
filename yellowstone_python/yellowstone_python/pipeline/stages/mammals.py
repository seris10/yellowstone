"""Mammal ecology initialization from published patch and actor inputs."""
from __future__ import annotations

import copy

from yellowstone_python.common.mammal_forcing import environmental_forcing

READS = ("patches2", "wildlife3", "weather_frag", "replay_doc", "world", "world_root", "tfns", "shells")
WRITES = ("mammal_doc", "wildlife_mammals", "mammal_settings", "mammal_encounters", "mammal_catalogue", "wildlife3")


def run(state, cfg):
    """Initialize the authored mammal model without modifying source inputs."""
    settings = dict(cfg.get("mammals", {}) or {})
    settings.setdefault("enabled", True)
    settings.setdefault("seed", 54173)
    actors = copy.deepcopy(state["wildlife3"])
    if not settings["enabled"]:
        state.update(mammal_doc={"enabled": False}, wildlife_mammals=actors,
                     mammal_settings=settings, mammal_encounters={"actors": []},
                     mammal_catalogue={"enabled": False})
        return state
    from yellowstone_python.land.mammals import MammalEcology, author_midway_encounters, load_catalogue
    from yellowstone_python.authoring.mammal_encounters import habitat_mask_blocker
    catalogue = load_catalogue()
    encounters = author_midway_encounters(
        state["world"], state["tfns"], state["shells"], patches=state["patches2"],
        existing_actors=actors, seed=settings["seed"], catalogue=catalogue,
        blocked=habitat_mask_blocker(state["world_root"]))
    by_id = {row["id"]: row for row in actors}
    for actor in encounters["actors"]:
        by_id[actor["id"]] = actor
    actors = list(by_id.values())
    from yellowstone_python.land.grazers import update_grazers
    actors = update_grazers(actors, state["patches2"],
        snow_depth_by_patch={row["id"]: row.get("snow_depth_m", 0.0) for row in state["patches2"]})
    state["wildlife3"] = actors
    model = MammalEcology(state["patches2"], actors=actors, seed=settings["seed"])
    epoch = state["replay_doc"]["simulation_time"]["start_epoch_unix"]
    model.step(0.0, environmental_forcing(state["patches2"], state["weather_frag"], epoch))
    state.update(mammal_doc=model.snapshot(), wildlife_mammals=actors,
                 mammal_settings=settings, mammal_encounters=encounters,
                 mammal_catalogue=catalogue)
    return state
