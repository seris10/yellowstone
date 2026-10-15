"""Authenticate the shared forcing benchmark and its explicitly selected receipts."""
from pathlib import Path
import hashlib
import json
import math


def same_redundant_json_payload(expected, observed):
    """Compare duplicate parsed JSON with bounded decimal serialization loss."""
    if isinstance(expected, bool) or isinstance(observed, bool):
        return type(expected) is type(observed) and expected == observed
    if isinstance(expected, (int, float)) and isinstance(observed, (int, float)):
        return math.isfinite(expected) and math.isfinite(observed) and math.isclose(
            expected, observed, rel_tol=0.0, abs_tol=1e-12)
    if type(expected) is not type(observed):
        return False
    if isinstance(expected, dict):
        return expected.keys() == observed.keys() and all(
            same_redundant_json_payload(value, observed[key]) for key, value in expected.items())
    if isinstance(expected, list):
        return len(expected) == len(observed) and all(
            same_redundant_json_payload(a, b) for a, b in zip(expected, observed))
    return expected == observed


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def local(root, path):
    value = (root / path).resolve()
    assert value.is_relative_to(root), path
    return value


def validate_benchmark(pairs, receipts, root):
    assert [run['run'] for run in pairs['runs']] == ['a1', 'b1', 'b2', 'a2']
    fixture_hashes = pairs['harness_fixture_hashes']
    assert len(fixture_hashes) == 2
    for path, expected in fixture_hashes.items():
        assert digest(local(root, path)) == expected, path
    common_keys = ('simulation_epoch_unix', 'world_epoch_unix', 'ecosystem_epoch_unix',
        'elapsed_s', 'source_solar_degrees', 'sun_rotation_radians', 'sun_direction',
        'cloud_sun_direction', 'cloud_offset', 'ecosystem_wind_xz_mps', 'resolution',
        'msaa_3d', 'shadow_enabled', 'shadow_mode', 'shadow_splits', 'shadow_blend_splits',
        'shadow_fade_start', 'shadow_atlas_size', 'shadow_filter_quality', 'shadow_range_m',
        'shadow_bias', 'shadow_normal_bias')
    first = None
    common_fixture = None
    controls = {}
    for run in pairs['runs']:
        label = run['run']
        receipt = receipts[label]
        for path, expected in fixture_hashes.items():
            assert receipt['fixture_hashes'][path] == expected, (label, path)
        report_path = local(root, run['capture_directory']) / 'report.json'
        assert digest(report_path) == run['report_sha256'], (label, 'raw report hash')
        assert json.loads(report_path.read_text()) == run['report']
        report = run['report']
        assert report['ok'] and not report['failures']
        assert report['moving_camera']['sample_frames'] == 120
        assert len(report['moving_camera']['drawn_frame_steps']) == 120
        assert all(step == 1 for step in report['moving_camera']['drawn_frame_steps'])
        lock = report['benchmark_fixture']
        assert lock['schema'] == 'yellowstone.forest_benchmark_lock.v1'
        assert lock['requested_forcing_validated'] is True
        assert lock['forcing_unchanged'] is True and lock['first_state'] == lock['last_state']
        assert lock['forcing_checks'] >= 191
        assert lock['external_readers_disabled'] is True and lock['input_nodes_disabled'] > 0
        assert lock['input_probe']
        canonical = lock['canonical_payload_json']
        assert hashlib.sha256(canonical.encode()).hexdigest() == lock['canonical_payload_sha256']
        assert same_redundant_json_payload(json.loads(canonical), lock['canonical_payload'])
        fixture = local(root, lock['fixture_path'])
        world = local(root, run['world'])
        harness_path = lock['harness_path']
        harness = local(root, world / harness_path.removeprefix('res://') if harness_path.startswith('res://') else harness_path)
        assert fixture.read_text().strip() == canonical
        assert digest(fixture) == lock['fixture_file_sha256'] == fixture_hashes[str(fixture.relative_to(root))]
        assert digest(harness) == lock['harness_sha256'] == fixture_hashes[str(harness.relative_to(root))]
        assert len(report['captures']) == 9
        for capture in report['captures']:
            assert digest(report_path.parent / capture['file']) == capture['sha256']
        pointer = json.loads((world / 'data/release.json').read_text())
        release_path = world / pointer['manifest']
        assert digest(release_path) == pointer['sha256']
        release = json.loads(release_path.read_text())
        assert release['release_id'] == report['release_id']
        for path, expected in lock['source_hashes'].items():
            active = path.startswith('active:')
            relative = path.removeprefix('active:').removeprefix('res://')
            artifact = release['artifacts'].get(relative) if active else None
            source = release_path.parent / artifact['path'] if artifact else world / relative
            assert digest(source) == expected, (label, path)
        state = lock['first_state']
        if first is None:
            first = state
            common_fixture = lock['canonical_payload_sha256']
        else:
            assert lock['canonical_payload_sha256'] == common_fixture
            assert state == first, (label, 'full shared forcing/render state')
            for key in common_keys:
                assert state[key] == first[key], (label, key)
        controls[label] = {'forcing_checks': lock['forcing_checks'],
            'requested_forcing_validated': True, 'stable_first_last': True,
            'report_sha256': run['report_sha256'], 'harness_sha256': lock['harness_sha256'],
            'canonical_payload_sha256': common_fixture}
    return {'ok': True, 'runs': controls, 'shared_physical_state_fields': list(common_keys),
        'harness_fixture_hashes': fixture_hashes, 'full_first_state_equal_across_runs': True,
        'redundant_payload_comparison': 'Only the duplicate parsed payload permits absolute numeric difference <= 1e-12 for Godot JSON decimal serialization. Original fixture text, fixture hash and canonical JSON hash remain exact authorities. Image and first/last/cross-run state checks remain exact.',
        'normalization': pairs['runs'][0]['report']['benchmark_fixture']['normalization'],
        'scope': 'Common authored weather, epoch and physical sunlight; baseline sun convention normalized in memory. This is a controlled comparison, not an unchanged as-shipped-default lighting comparison. Wall intervals include common forcing-verification overhead. Shader TIME and particles remain animated; desktop load is uncontrolled and GPU execution time is unavailable.'}


def validate_saved_world_capture(report, receipt, root, benchmark_state, publication_images):
    """Authenticate the saved-world images against current sources and shared forcing."""
    assert report['ok'] is True and not report['failures']
    raw_path = local(root, report['raw_report_path'])
    assert digest(raw_path) == report['raw_report_sha256']
    raw = json.loads(raw_path.read_text())
    assert raw == {key: value for key, value in report.items()
        if key not in ('raw_report_path', 'raw_report_sha256', 'receipt_file')}
    world = local(root, 'yellowstone_midway')
    assert digest(world / 'scenes/authored_world.tscn') == report['authored_world_sha256']
    lock = report['benchmark_fixture']
    assert lock['schema'] == 'yellowstone.forest_benchmark_lock.v1'
    assert lock['requested_forcing_validated'] is True and lock['forcing_unchanged'] is True
    assert lock['first_state'] == lock['last_state'] == benchmark_state
    assert lock['forcing_checks'] >= 9
    assert lock['external_readers_disabled'] is True and lock['input_nodes_disabled'] > 0
    canonical = lock['canonical_payload_json']
    assert hashlib.sha256(canonical.encode()).hexdigest() == lock['canonical_payload_sha256']
    assert same_redundant_json_payload(json.loads(canonical), lock['canonical_payload'])
    fixture = local(root, lock['fixture_path'])
    wrapper = local(root, world / lock['harness_path'].removeprefix('res://'))
    shared = local(root, lock['shared_lock_harness_path'])
    assert fixture.read_text().strip() == canonical
    expected_files = {
        fixture: lock['fixture_file_sha256'], wrapper: lock['harness_sha256'],
        shared: lock['shared_lock_harness_sha256'],
        world / 'scenes/authored_world.tscn': report['authored_world_sha256'],
        world / 'data/release.json': report['inputs']['res://data/release.json']}
    for path, expected in expected_files.items():
        assert digest(path) == expected == receipt['fixture_hashes'][str(path.relative_to(root))]
    special_inputs = {'forcing_fixture': fixture, 'capture_wrapper': wrapper,
        'shared_forcing_lock_harness': shared}
    for name, expected in report['inputs'].items():
        path = local(root, world / name.removeprefix('res://')) if name.startswith('res://') else special_inputs[name]
        assert digest(path) == expected, name
    pointer = json.loads((world / 'data/release.json').read_text())
    release_path = local(root, world / pointer['manifest'])
    assert digest(release_path) == pointer['sha256']
    release = json.loads(release_path.read_text())
    for name, expected in lock['source_hashes'].items():
        relative = name.removeprefix('active:').removeprefix('res://')
        artifact = release['artifacts'].get(relative) if name.startswith('active:') else None
        path = local(root, release_path.parent / artifact['path'] if artifact else world / relative)
        assert digest(path) == expected, name
    assert len(report['captures']) == 8
    image_hashes = {}
    for capture in report['captures']:
        path = local(root, capture['file'])
        assert capture['error'] == 0 and digest(path) == capture['sha256']
        image_hashes[str(path.relative_to(root))] = capture['sha256']
    assert len(image_hashes) == 8
    for role in ('overlook', 'floor', 'fov72', 'fov40', 'fov30'):
        assert str(local(root, publication_images[role]).relative_to(root)) in image_hashes, role
    return {'ok': True, 'image_hashes': image_hashes,
        'raw_report': {'path': str(raw_path.relative_to(root)), 'sha256': report['raw_report_sha256']},
        'fixture_hashes': {str(path.relative_to(root)): value for path, value in expected_files.items()},
        'forcing_checks': lock['forcing_checks'], 'exact_state_matches_benchmark': True,
        'scope': 'Eight final-runtime native images authenticated against raw report, execution fixtures, current source bytes and the exact ABBA forcing state. The separately captioned historical rainbow image is outside this final-graphics set. This does not establish visual acceptance or field calibration.'}
