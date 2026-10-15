"""Adversarial integrity checks for benchmark records; this does not run the game."""
from pathlib import Path
import copy
import hashlib
import json
import tempfile
from forest_benchmark_evidence import digest, validate_benchmark, same_redundant_json_payload


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + '\n')


def expected_failure(fn):
    try:
        fn()
    except (AssertionError, KeyError):
        return
    raise AssertionError('Corrupt evidence unexpectedly accepted')


with tempfile.TemporaryDirectory(prefix='forest-benchmark-integrity-') as directory:
    root = Path(directory).resolve()
    (root / 'work').mkdir()
    harness = root / 'work/harness.gd'
    harness.write_text('Synthetic integrity fixture, not executable game code.\n')
    fixture = root / 'work/forcing.json'
    payload = {'fixture': 'synthetic integrity test only'}
    write_json(fixture, payload)
    canonical = fixture.read_text().strip()
    fixtures = {str(p.relative_to(root)): digest(p) for p in (fixture, harness)}
    world = root / 'world'
    world.mkdir()
    (world / 'project.godot').write_text('synthetic fixture\n')
    release = world / 'data/releases/synthetic/RELEASE.json'
    write_json(release, {'release_id': 'synthetic', 'artifacts': {}})
    write_json(world / 'data/release.json', {'manifest': 'data/releases/synthetic/RELEASE.json', 'sha256': digest(release)})
    state_keys = ('simulation_epoch_unix world_epoch_unix ecosystem_epoch_unix elapsed_s '
        'source_solar_degrees sun_rotation_radians sun_direction cloud_sun_direction cloud_offset '
        'ecosystem_wind_xz_mps resolution msaa_3d shadow_enabled shadow_mode shadow_splits '
        'shadow_blend_splits shadow_fade_start shadow_atlas_size shadow_filter_quality shadow_range_m '
        'shadow_bias shadow_normal_bias').split()
    state = {key: 0 for key in state_keys}
    pairs = {'runs': [], 'harness_fixture_hashes': fixtures}
    receipts = {}
    for label in ('a1', 'b1', 'b2', 'a2'):
        dest = root / 'captures' / label
        dest.mkdir(parents=True)
        captures = []
        for i in range(9):
            path = dest / (str(i) + '.png')
            path.write_bytes(b'synthetic image hash fixture')
            captures.append({'file': path.name, 'sha256': digest(path)})
        lock = {'schema': 'yellowstone.forest_benchmark_lock.v1', 'requested_forcing_validated': True,
            'forcing_unchanged': True, 'first_state': state, 'last_state': state,
            'forcing_checks': 191, 'external_readers_disabled': True, 'input_nodes_disabled': 1,
            'input_probe': 'synthetic probe', 'canonical_payload_json': canonical,
            'canonical_payload_sha256': hashlib.sha256(canonical.encode()).hexdigest(),
            'canonical_payload': payload, 'fixture_path': str(fixture), 'fixture_file_sha256': digest(fixture),
            'harness_path': str(harness), 'harness_sha256': digest(harness),
            'source_hashes': {'res://project.godot': digest(world / 'project.godot')},
            'normalization': 'synthetic fixture'}
        report = {'ok': True, 'failures': [], 'release_id': 'synthetic', 'captures': captures,
            'benchmark_fixture': lock, 'moving_camera': {'sample_frames': 120, 'drawn_frame_steps': [1] * 120}}
        write_json(dest / 'report.json', report)
        pairs['runs'].append({'run': label, 'world': 'world', 'capture_directory': str(dest.relative_to(root)),
            'report': copy.deepcopy(report), 'report_sha256': digest(dest / 'report.json')})
        receipts[label] = {'fixture_hashes': copy.deepcopy(fixtures)}
    assert validate_benchmark(pairs, receipts, root)['ok']
    assert same_redundant_json_payload({'sun': [21.26584774441318]}, {'sun': [21.2658477444132]})
    assert not same_redundant_json_payload({'sun': [21.26584774441318]}, {'sun': [21.26584774442]})
    assert not same_redundant_json_payload({'sun': True}, {'sun': 1})
    assert not same_redundant_json_payload({'sun': 1}, {'extra': 1})
    checked = 5
    for label, corrupt in [
        ('ignored fixture', lambda r: r['benchmark_fixture'].update(requested_forcing_validated=False)),
        ('too few samples', lambda r: r['moving_camera'].update(sample_frames=119)),
        ('cross-run lighting', lambda r: (r['benchmark_fixture']['first_state'].update(sun_direction=2), r['benchmark_fixture']['last_state'].update(sun_direction=2))),
        ('wrong source hash', lambda r: r['benchmark_fixture']['source_hashes'].update({'res://project.godot': '0' * 64}))]:
        bad = copy.deepcopy(pairs)
        run = bad['runs'][1]
        corrupt(run['report'])
        path = root / run['capture_directory'] / 'report.json'
        write_json(path, run['report'])
        run['report_sha256'] = digest(path)
        expected_failure(lambda: validate_benchmark(bad, receipts, root))
        write_json(path, pairs['runs'][1]['report'])
        checked += 1
    wrong_receipts = copy.deepcopy(receipts)
    wrong_receipts['b1']['fixture_hashes']['work/harness.gd'] = '0' * 64
    expected_failure(lambda: validate_benchmark(pairs, wrong_receipts, root))
    checked += 1
    (root / 'captures/b1/0.png').write_bytes(b'mutated capture')
    expected_failure(lambda: validate_benchmark(pairs, receipts, root))
    checked += 1
    print(f'{checked} integrity checks passed; synthetic evidence only, no renderer/performance claim.')
