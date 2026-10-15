"""Authenticate the shared forcing benchmark and its explicitly selected receipts."""
from pathlib import Path
import hashlib
import json


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
        assert json.loads(canonical) == lock['canonical_payload']
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
            for key in common_keys:
                assert state[key] == first[key], (label, key)
        controls[label] = {'forcing_checks': lock['forcing_checks'],
            'requested_forcing_validated': True, 'stable_first_last': True,
            'report_sha256': run['report_sha256'], 'harness_sha256': lock['harness_sha256'],
            'canonical_payload_sha256': common_fixture}
    return {'ok': True, 'runs': controls, 'shared_physical_state_fields': list(common_keys),
        'harness_fixture_hashes': fixture_hashes,
        'normalization': pairs['runs'][0]['report']['benchmark_fixture']['normalization'],
        'scope': 'Common authored weather, epoch and physical sunlight; baseline sun convention normalized in memory. This is a controlled comparison, not an unchanged as-shipped-default lighting comparison. Wall intervals include common forcing-verification overhead. Shader TIME and particles remain animated; desktop load is uncontrolled and GPU execution time is unavailable.'}
