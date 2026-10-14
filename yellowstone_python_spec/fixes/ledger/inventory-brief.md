# Inventory brief: what exists, what is wired, what is rendered

Purpose: produce structured data for a project dashboard that shows each simulated component and each coupling, with status. You change no code and write only your assigned output file.

Project root: `../../roots-of-reason/5-original-games/yellowstone`. Python: `yellowstone_python/` (package `yellowstone_python/yellowstone_python/`, tools, configs, derived outputs). Godot world: `yellowstone_midway/` (scripts, scenes, data, shaders, tools). Atmosphere add-on: `yellowstone_atmosphere/`. Hydrology prototype: `hydrology/`. Spec and plans: `yellowstone_python_spec/` (00 to 03, improvements.md, addons.md, additional-research.md), `research/` (domain research incl. yellowstone-todo.md), `yellowstone_species_gen/00_RESEARCH_SPEC.md`.

Status vocabulary (closed), applied per component:
- `rendered`: implemented in Python (or Godot-native) AND visibly represented in the Godot world (mesh, material, shader, particles, actor, overlay) from that data.
- `python_only`: implemented and wired in the Python build, output published or written, but nothing in Godot draws it.
- `partial_unwired`: code exists but is not called by the build/runner, or its output is not consumed, or it is stubbed/illustrative-only in a way the code itself admits.
- `not_started`: called for by the spec/research/plans as part of the current project, no implementation.
- `next_phase`: plausible extension named in plans/research or clearly implied (including educational interactivity hooks), not required for the current project.

Domains (closed): `atmosphere`, `hydrology` (river, overland, groundwater), `hydrothermal` (pools, geochemistry, sinter, plumes, heat), `cryosphere` (snow, soil water), `aquatic_ecology` (fish, insects, foodweb), `terrestrial_ecology` (vegetation, flora, grazers, birds, census), `observation` (fetchers, obs bundles, calibration, uncertainty), `infrastructure` (build, publish, claims, provenance, store, backend), `rendering` (Godot-only systems).

Evidence is mandatory: every status and every coupling carries `file:line`. Never infer from names, comments, or trackers alone. Mark `NOT VERIFIED` where you could not confirm.

Output: one JSON file at the path in your assignment:

```json
{
  "generated_from": "<what you read, sha256 first 12 of key files>",
  "components": [{
    "id": "river_heat", "label": "River heat transport", "domain": "hydrology",
    "python": ["yellowstone_python/yellowstone_python/replay/river_transport.py"],
    "godot": ["yellowstone_midway/scripts/python_river_replay.gd"],
    "status": "rendered", "evidence": ["file:line ..."],
    "method": "one line: governing equation or method",
    "validation": "illustrative | fitted_not_validated | validated | none",
    "notes": "one line"
  }],
  "couplings": [{
    "from": "air_temperature", "to": "river_heat", "quantity": "air temperature forcing",
    "status": "wired | partial | missing | proposed", "evidence": ["file:line"], "notes": "one line"
  }]
}
```

Final message: ONLY `{"file":"<path>","components":<n>,"couplings":<n>,"by_status":{...}}`.
