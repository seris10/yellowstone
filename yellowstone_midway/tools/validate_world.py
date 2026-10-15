#!/usr/bin/env python3
"""Checks invariants for a real-scale connected landscape."""
from pathlib import Path
import json
import numpy as np
from scipy.spatial import cKDTree

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    world = json.loads((ROOT / 'data/world.json').read_text())
    h = np.fromfile(ROOT / 'data/terrain.f32', dtype='<f4').reshape(1025, 1025)
    errors: list = []
    metrics: dict = {}

    def check(condition, message):
        if not condition:
            errors.append(message)

    check(np.isfinite(h).all(), 'Elevation grid has missing/nonfinite values')
    check(world['georeference']['unit'] == 'metre', 'World units changed')  # spelling-ok
    check(world['georeference']['extent'] == 4096, 'Unapproved geographic rescaling')
    check(len({p['id'] for p in world['routes']}) == len(world['routes']), 'Duplicate route identifiers')
    check(len({p['id'] for p in world['pools']}) == len(world['pools']), 'Duplicate water identifiers')
    # Baked tile edges checked by validate_baked.gd; endpoint pairs within 0.2 m horizontally.
    for group, key, tolerance in [('routes', 'route_join_error_m', .04), ('rivers', 'river_join_error_m', .04)]:
        endpoints = []
        names = []
        for item in world[group]:
            pts = np.asarray(item['points'])
            check(np.isfinite(pts).all(), f'{item["id"]}: nonfinite vertex')
            check(np.max(np.abs(pts[:, [0, 2]])) <= 2048.1, f'{item["id"]}: outside bounds')
            for p in [pts[0], pts[-1]]:
                endpoints.append(p)
                names.append(item['id'])
        pts = np.array(endpoints)
        tree = cKDTree(pts[:, [0, 2]])
        worst = 0.
        for i, j in tree.query_pairs(.2):
            if names[i] == names[j]:
                continue
            error = float(abs(pts[i, 1] - pts[j, 1]))
            worst = max(worst, error)
            check(error <= tolerance, f'{group} join {names[i]} / {names[j]}: {error:.4f}m')
        metrics[key] = worst
    for river in world['rivers']:
        if river['name'] == 'FIREHOLE RIVER':
            p = np.array(river['points'])
            check(p[0, 2] >= p[-1, 2], f'{river["id"]}: Firehole must be ordered downstream northward')
            check(np.max(np.diff(p[:, 1])) < .005, f'{river["id"]}: water climbs downstream')
    for pool in world['pools']:
        if not pool['thermal']:
            check(pool['temperature_c'] < 35, 'Ordinary lake assigned hot-spring temperature')
    # Placement snapshots are data.
    placements = json.loads((ROOT / 'data/placements.json').read_text())
    ids = []
    for group in ['trees', 'grass', 'rocks', 'logs']:
        for p in placements[group]:
            ids.append(p['id'])
            check(len(p['position']) == 3 and p['scale'] > 0, f'Invalid placement: {p["id"]}')
    check(len(ids) == len(set(ids)), 'Duplicate stable placement ids')
    metrics['fixed_placements'] = len(ids)
    # Photos are references/CC0 scans.
    check((ROOT / 'references/dem.tif').exists(), 'Lost original terrain source')
    check((ROOT / 'data/placement_overrides.json').exists(), 'Missing manual override layer')
    report = {'ok': not errors, 'metrics': metrics, 'errors': errors}
    (ROOT / 'tests/data_validation.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
