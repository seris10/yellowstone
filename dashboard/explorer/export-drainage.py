"""Derive potential surface drainage from the pinned, unmodified 4 m DEM."""
import argparse
import hashlib
import heapq
import json
from pathlib import Path

import numpy as np

SOURCE = 'yellowstone_midway/references/terrain_source.f32'
SOURCE_HASH = 'ecd0ba29c110eaadbea4732b93af474fb0227e8b5bae1aa7f70ff1497756ccba'
OFFSETS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def priority_flood(source):
    raw = np.asarray(source, dtype=np.float64)
    if raw.ndim != 2 or min(raw.shape) < 3 or not np.isfinite(raw).all():
        raise ValueError('A finite rectangular DEM of at least 3 by 3 samples is required')
    h, w = raw.shape
    filled = raw.copy().ravel()
    seen = np.zeros(h * w, dtype=bool)
    parent = np.full(h * w, -1, dtype=np.int32)
    order = np.empty(h * w, dtype=np.int32)
    heap = []
    boundary = np.unique(np.concatenate((np.arange(w), np.arange((h - 1) * w, h * w), np.arange(0, h * w, w), np.arange(w - 1, h * w, w))))
    for i in boundary:
        seen[i] = True
        heapq.heappush(heap, (float(filled[i]), int(i)))
    k = 0
    while heap:
        level, i = heapq.heappop(heap)
        order[k] = i
        k += 1
        r, c = divmod(i, w)
        for dr, dc in OFFSETS:
            rr, cc = r + dr, c + dc
            if not (0 <= rr < h and 0 <= cc < w):
                continue
            j = rr * w + cc
            if seen[j]:
                continue
            seen[j] = True
            parent[j] = i
            filled[j] = max(float(filled[j]), level)
            heapq.heappush(heap, (float(filled[j]), j))
    rank = np.empty(h * w, dtype=np.int32)
    rank[order] = np.arange(h * w)
    return filled.reshape(raw.shape), parent, order, rank


def route(source, spacing=4.0):
    raw = np.asarray(source, dtype=np.float64)
    filled, parent, order, rank = priority_flood(raw)
    h, w = raw.shape
    receiver = parent.copy().reshape(raw.shape)
    steepest = np.zeros(raw.shape)
    ids = np.arange(raw.size).reshape(raw.shape)
    for dr, dc in OFFSETS:
        r0, r1, c0, c1 = max(0, -dr), min(h, h - dr), max(0, -dc), min(w, w - dc)
        src = (slice(r0, r1), slice(c0, c1))
        dst = (slice(r0 + dr, r1 + dr), slice(c0 + dc, c1 + dc))
        slope = (filled[src] - filled[dst]) / (spacing * np.hypot(dr, dc))
        better = slope > steepest[src]
        receiver[src][better] = ids[dst][better]
        steepest[src][better] = slope[better]
    receiver[[0, -1], :] = -1
    receiver[:, [0, -1]] = -1
    receiver = receiver.ravel()
    valid = receiver >= 0
    if not np.all(rank[receiver[valid]] < rank[valid]):
        raise AssertionError('Routing is not topologically ordered')
    # Node-centered grid: edge support is half a cell, corners a quarter.
    support = np.ones(raw.shape, dtype=np.float64) * spacing ** 2
    support[[0, -1], :] *= 0.5
    support[:, [0, -1]] *= 0.5
    area = support.ravel().copy()
    for i in order[::-1]:
        j = receiver[i]
        if j >= 0:
            area[j] += area[i]
    if area[receiver < 0].sum() != support.sum():
        raise AssertionError('Contributing-area conservation failed')
    return {'filled': filled, 'receiver': receiver, 'order': order, 'rank': rank, 'area': area, 'support': support}


def channel_order(receiver, flood_order, active):
    result = np.zeros(receiver.size, dtype=np.uint8)
    maximum = np.zeros_like(result)
    count = np.zeros_like(result)
    for i in flood_order[::-1]:
        if not active[i]:
            continue
        result[i] = max(1, int(maximum[i]) + (int(count[i]) >= 2))
        j = receiver[i]
        if j >= 0 and active[j]:
            if result[i] > maximum[j]:
                maximum[j], count[j] = result[i], 1
            elif result[i] == maximum[j]:
                count[j] += 1
    return result


def visible_links(raw, routed, spacing=4, min_slope=0.002):
    receiver = routed['receiver']
    ids = np.arange(raw.size)
    valid = receiver >= 0
    j = np.maximum(receiver, 0)
    w = raw.shape[1]
    distances = spacing * np.hypot(ids // w - j // w, ids % w - j % w)
    drop = raw.ravel() - raw.ravel()[j]
    depth = routed['filled'].ravel() - raw.ravel()
    return valid & (depth <= 1e-6) & (depth[j] <= 1e-6) & (drop >= min_slope * distances)


def branches(raw, routed, threshold_ha, spacing=4, start=(-2048, -2048)):
    receiver, area = routed['receiver'], routed['area']
    active = area >= threshold_ha * 10000
    orders = channel_order(receiver, routed['order'], active)
    edge = visible_links(raw, routed, spacing) & active
    incoming = np.bincount(receiver[edge], minlength=raw.size)
    starts = np.flatnonzero(edge & (incoming != 1))
    w = raw.shape[1]
    output = []
    edge_count = 0
    for seed in starts:
        points = []
        i = int(seed)
        branch_order = int(orders[i])
        while True:
            r, c = divmod(i, w)
            points.append([start[0] + c * spacing, start[1] + r * spacing, float(raw.ravel()[i]), float(area[i])])
            if not edge[i]:
                break
            j = int(receiver[i])
            edge_count += 1
            if incoming[j] != 1:
                r, c = divmod(j, w)
                points.append([start[0] + c * spacing, start[1] + r * spacing, float(raw.ravel()[j]), float(area[j])])
                break
            i = j
        output.append({'id': len(output), 'order': branch_order, 'area_start_m2': points[0][3], 'area_end_m2': points[-1][3], 'points': points})
    if edge_count != int(edge.sum()):
        raise AssertionError('Export must cover each visible drainage link exactly once')
    return {'threshold_ha': threshold_ha, 'branch_count': len(output), 'edge_count': edge_count, 'maximum_order': int(orders.max()), 'branches': output}


def export(root, out):
    manifest_path = out / 'data/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    source = root / SOURCE
    source_hash = digest(source)
    if manifest['sources'][SOURCE] != SOURCE_HASH or source_hash != SOURCE_HASH:
        raise ValueError('Pinned DEM source hash mismatch')
    raw = np.fromfile(source, dtype='<f4').reshape(1025, 1025).astype(np.float64)
    routed = route(raw)
    depths = routed['filled'] - raw
    levels = [branches(raw, routed, threshold) for threshold in (0.5, 2, 8)]
    metadata = {
        'schema': 'yellowstone.dem-drainage.v1',
        'label': 'Terrain drainage',
        'description': 'Possible surface drainage paths calculated from ground elevations. These lines are not surveyed streams and do not show whether water is present.',
        'source': SOURCE, 'source_sha256': source_hash, 'n': 1025, 'spacing_m': 4,
        'start': [-2048, -2048], 'point_fields': ['x_m', 'z_m', 'elevation_navd88_m', 'contributing_area_m2'],
        'method': {
            'depressions': 'D8 Priority-Flood, all outer-edge samples open; depression elevations raised to their lowest spill level in a separate routing array.',
            'routing': 'Steepest downhill D8 on filled elevations; equal-height ties follow the earlier flood predecessor. Strictly decreasing flood rank prevents cycles.',
            'accumulation': 'Local DEM contributing area; 16 m² interior support, 8 m² edges, 4 m² corners. External catchments are absent.',
            'order': 'Strahler order on thresholded channels before clipping. Two or more equal highest-order tributaries increase order by one.',
            'display_filter': 'Links touching raised DEM samples, and links with original ground slope below 0.2%, are omitted. Paths end at these gaps; no connecting lines cross the gaps.',
            'min_display_slope': 0.002,
            'reference': 'https://doi.org/10.1016/j.cageo.2013.04.024',
        },
        'limits': 'The 4.096 km square cuts across catchments, so upstream area outside the map is missing. D8 paths and branch order depend on DEM resolution, depression handling and the selected area threshold. Flat water surfaces and filled depressions are omitted; groundwater, culverts and seasonal flow are not represented.',
        'statistics': {
            'source_samples': int(raw.size), 'domain_area_m2': float(routed['support'].sum()),
            'outlet_area_sum_m2': float(routed['area'][routed['receiver'] < 0].sum()),
            'filled_samples': int((depths > 0).sum()), 'max_fill_depth_m': float(depths.max()),
            'mean_fill_depth_m': float(depths.mean()), 'p99_fill_depth_m': float(np.percentile(depths, 99)),
            'visible_downhill_links': int(visible_links(raw, routed).sum()),
            'outlets': int((routed['receiver'] < 0).sum()),
        },
        'levels': levels,
    }
    target = out / 'data/drainage.json'
    target.write_text(json.dumps(metadata, separators=(',', ':'), allow_nan=False))
    # Preserve concurrently updated terrain and other asset metadata.
    latest = json.loads(manifest_path.read_text())
    latest['assets']['drainage.json'] = {'sha256': digest(target), 'bytes': target.stat().st_size}
    latest['drainage'] = {k: metadata[k] for k in ('schema', 'label', 'description', 'source', 'source_sha256', 'method', 'limits', 'statistics')}
    latest['drainage'].update({'file': target.name, 'thresholds_ha': [level['threshold_ha'] for level in levels], 'default_threshold_ha': 0.5})
    manifest_path.write_text(json.dumps(latest, separators=(',', ':'), allow_nan=False))
    return metadata


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path(__file__).parent)
    args = parser.parse_args()
    result = export(args.root, args.out)
    print(json.dumps({'statistics': result['statistics'], 'levels': [{k: v for k, v in row.items() if k != 'branches'} for row in result['levels']]}, indent=2))
