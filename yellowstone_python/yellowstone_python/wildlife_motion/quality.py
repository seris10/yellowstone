"""Exact serialized surface diagnostics and explicit production quality budgets."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path

import numpy as np

from .asset_audit import audit_asset
from .birds import BirdEngine
from .core import Skeleton
from .gltf import accessor, read_glb
from .mammals import MammalEngine
from .species import get_profile
from .validation import imported_skin

REQUIRED_BUDGETS = ('maximum_edge_stretch_p99', 'maximum_stance_surface_slip_height_per_s',
                    'maximum_stance_surface_distance_height', 'maximum_loop_error_height')


def serialized_surface_report(path: Path, samples: int = 9) -> dict:
    """Measure deformation and planted contact surfaces on the exported GLB."""
    if samples < 3:
        raise ValueError('At least three surface samples required')
    audit = audit_asset(path, samples=samples)
    document, blob = read_glb(path)
    manifest = document.get('extras', {}).get('wildlife_motion', {})
    if len(document.get('skins', [])) != 1:
        return {'status': 'unavailable', 'reason': 'single_source_bound_skin_required', 'asset_sha256': audit['sha256']}
    if not manifest.get('rig'):
        return {'status': 'unavailable', 'reason': 'source_bound_rig_metadata_missing', 'asset_sha256': audit['sha256']}
    skeleton = Skeleton.from_dict(manifest['rig'])
    profile = get_profile(skeleton.metadata['species'])
    primitives = [primitive for node in document['nodes'] if 'skin' in node
                  for primitive in document['meshes'][node['mesh']]['primitives']]
    vertices, joints, weights, faces, offset = [], [], [], [], 0
    for primitive in primitives:
        attributes = primitive['attributes']
        points = accessor(document, blob, attributes['POSITION'])
        vertices.append(points)
        joints.append(accessor(document, blob, attributes['JOINTS_0'], False))
        weights.append(accessor(document, blob, attributes['WEIGHTS_0']))
        indices = accessor(document, blob, primitive['indices'], False).reshape(-1, 3)
        faces.append(indices+offset)
        offset += len(points)
    vertices, joints, weights, faces = map(np.vstack, (vertices, joints, weights, faces))
    edges = np.unique(np.sort(np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1), axis=0)
    rest_edges = np.linalg.norm(vertices[edges[:, 0]]-vertices[edges[:, 1]], axis=1)
    usable = rest_edges > 1e-8
    edges, rest_edges = edges[usable], rest_edges[usable]
    height = float(np.ptp(vertices[:, 1]))
    if height <= 0 or not len(edges):
        raise ValueError('Nondegenerate skinned surface required')
    regions = {}
    for limb in ('FL', 'FR', 'HL', 'HR') if profile['engine'] == 'mammal' else ('L', 'R'):
        joint = skeleton.groups[limb][-1]
        candidates = np.flatnonzero(np.sum(weights*(joints == joint), axis=1) > .5)
        if len(candidates):
            low = vertices[candidates, 1].min()
            regions[limb] = candidates[vertices[candidates, 1] <= low+.02*height]
    reports = {}
    for animation in document.get('animations', []):
        mode = animation['name']
        if mode not in ('Idle', 'Walk'):
            continue
        metadata = animation.get('extras', {}).get('wildlife_motion', {})
        controls = metadata.get('controls')
        if not isinstance(controls, dict):
            return {'status': 'unavailable', 'reason': 'resolved_clip_controls_missing', 'asset_sha256': audit['sha256']}
        resolved_profile = copy.deepcopy(profile)
        resolved_profile['gaits'][mode] = controls
        engine = (MammalEngine if profile['engine'] == 'mammal' else BirdEngine)(skeleton, resolved_profile)
        duration = float(max(accessor(document, blob, sampler['input'])[-1, 0] for sampler in animation['samplers']))
        speed = float(metadata.get('speed_asset_units_s', 0.))
        stretch, slip, distance = [], [], []
        observed = set()
        for time in np.linspace(0, duration, samples, endpoint=False):
            surface = imported_skin(path, mode, float(time))
            if not np.isfinite(surface).all():
                raise ValueError('Nonfinite final animated surface')
            ratio = np.linalg.norm(surface[edges[:, 0]]-surface[edges[:, 1]], axis=1)/rest_edges
            stretch.append(float(np.quantile(abs(ratio-1), .99)))
            delta = min(1e-4, duration*1e-4)
            pose = engine.pose(float(time), mode)
            next_pose = engine.pose(float(time+delta), mode)
            active = [limb for limb, contact in pose.diagnostics.get('contacts', {}).items()
                      if contact and next_pose.diagnostics.get('contacts', {}).get(limb) and limb in regions]
            if active:
                later = imported_skin(path, mode, float(time+delta))
                for limb in active:
                    indices = regions[limb]
                    velocity = (later[indices]-surface[indices])/delta
                    if not metadata.get('root_motion', False):
                        velocity[:, 2] += speed
                    slip.append(float(np.linalg.norm(velocity, axis=1).mean()/height))
                    distance.append(float(np.max(abs(surface[indices, 1]))/height))
                    observed.add(limb)
        first, last = imported_skin(path, mode, 0.), imported_skin(path, mode, duration)
        reports[mode] = {'edge_stretch_p99': max(stretch), 'stance_surface_slip_height_per_s': max(slip) if slip else None,
            'stance_surface_distance_height': max(distance) if distance else None,
            'loop_error_height': float(abs(first-last).max()/height), 'observed_contact_regions': sorted(observed)}
    return {'schema': 'yellowstone.serialized_surface_quality.v1', 'status': 'numerically_measured',
        'asset_sha256': audit['sha256'], 'modes': reports, 'samples_per_clip': samples,
        'height_asset_units': height, 'contact_region_vertices': {key: len(value) for key, value in regions.items()},
        'required_contact_regions': ['FL', 'FR', 'HL', 'HR'] if profile['engine'] == 'mammal' else ['L', 'R'],
        'ground_policy': 'flat canonical ground at y=0; turns and actual terrain require target-engine review',
        'biological_acceptance': 'not_yet_accepted', 'visual_acceptance': 'unassessed'}


def evaluate_surface_budget(report: dict, budget: dict) -> dict:
    """Apply predeclared geometric limits without implying biological acceptance."""
    if not isinstance(budget, dict) or any(key not in budget for key in REQUIRED_BUDGETS):
        raise ValueError('A complete predeclared deformation budget is required')
    if any(isinstance(budget[key], bool) or not np.isfinite(budget[key]) or budget[key] < 0 for key in REQUIRED_BUDGETS):
        raise ValueError('Deformation limits must be finite nonnegative numbers')
    failures = []
    if report.get('status') != 'numerically_measured' or not {'Idle', 'Walk'} <= set(report.get('modes', {})):
        failures.append('required_idle_walk_surface_evidence_unavailable')
    for name, mode in report.get('modes', {}).items():
        for metric in ('edge_stretch_p99', 'stance_surface_slip_height_per_s', 'stance_surface_distance_height', 'loop_error_height'):
            value = mode.get(metric)
            if value is None or not np.isfinite(value) or value > budget['maximum_'+metric]:
                failures.append(name+'.'+metric)
        if not set(report.get('required_contact_regions', [])) <= set(mode.get('observed_contact_regions', [])):
            failures.append(name+'.contact_surface_unavailable')
    return {'passed': not failures, 'failures': failures, 'budget': dict(budget),
            'budget_class': 'authored_geometric_acceptance_limits; not biological distributions'}
