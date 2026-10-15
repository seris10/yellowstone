"""Run the shared locked-forcing forest benchmark in ABBA order."""
from pathlib import Path
import hashlib
import json
import re
import subprocess

root = Path(__file__).resolve().parents[1]
python = root / 'yellowstone_python/.venv/bin/python'
project = root / 'yellowstone_midway'
baseline = root / 'work/Yellowstone-Surface-Update'
harness = root / 'work/validate_forest_benchmark.gd'
fixture = root / 'work/forest-benchmark-forcing.json'
hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in (harness, fixture)}
runs = []
receipts = {}
for label, world in [('a1', baseline), ('b1', project), ('b2', project), ('a2', baseline)]:
    destination = 'work/forest-paired-' + label + '-attachment'
    assert not (world / destination).exists(), ('Preserve existing measurement', destination)
    title = 'Previous release benchmark' if label.startswith('a') else 'Updated release benchmark'
    name = 'forest-render-pair-' + label + '-attachment'
    command = [str(python), '-m', 'tools.run_evidence', '--name', name]
    source_fixtures = [world / 'project.godot', world / 'scenes/authored_world.tscn',
                       world / 'data/release.json', world / 'scripts/canopy_surface.gd',
                       world / 'shaders/canopy_surface.gdshader', harness, fixture]
    if world == project:
        source_fixtures.append(world / 'scripts/tree_submission.gd')
    for path in source_fixtures:
        command.extend(['--fixture', str(path)])
    command.extend(['--', '/usr/bin/time', '-lp', '/opt/homebrew/bin/godot', '--path',
                    str(world), '--rendering-method', 'mobile', '--rendering-driver', 'metal',
                    '--disable-vsync', '--script', str(harness), '--', '--out=res://' + destination,
                    '--fixture=' + str(fixture), '--benchmark-label=' + title])
    print('Starting', label, title, flush=True)
    log_path = root / 'work' / ('forest-paired-' + label + '-attachment.log')
    with log_path.open('w') as log:
        result = subprocess.run(command, cwd=root / 'yellowstone_python', stdout=log,
                                stderr=subprocess.STDOUT)
    assert result.returncode == 0, (label, log_path)
    log = log_path.read_text()
    assert 'SCRIPT ERROR:' not in log and 'ERROR:' not in log, label
    matches = re.findall(r'receipt: (evidence/receipts/[0-9a-f]+\.json)', log)
    assert len(matches) == 1, (label, matches)
    receipts[label] = {'path': matches[0], 'name': name}
    report_path = world / destination / 'report.json'
    report = json.loads(report_path.read_text())
    assert report['ok'] and all(step == 1 for step in report['moving_camera']['drawn_frame_steps'])
    locked = report['benchmark_fixture']
    assert locked['forcing_unchanged'] and locked['first_state'] == locked['last_state']
    assert locked['requested_forcing_validated'] and locked['forcing_checks'] >= 191
    assert locked['harness_sha256'] == hashes[str(harness.relative_to(root))]
    assert locked['fixture_file_sha256'] == hashes[str(fixture.relative_to(root))]
    if runs:
        assert locked['canonical_payload_sha256'] == runs[0]['report']['benchmark_fixture']['canonical_payload_sha256']
        assert locked['first_state'] == runs[0]['report']['benchmark_fixture']['first_state'], (label, 'full forcing/render state')
        for key in ('simulation_epoch_unix', 'elapsed_s', 'sun_rotation_radians', 'sun_direction',
                    'cloud_sun_direction', 'cloud_offset', 'resolution', 'msaa_3d', 'shadow_range_m'):
            assert locked['first_state'][key] == runs[0]['report']['benchmark_fixture']['first_state'][key], (label, key)
    runs.append({'run': label, 'world': str(world.relative_to(root)),
                 'capture_directory': str((world / destination).relative_to(root)),
                 'report_sha256': hashlib.sha256(report_path.read_bytes()).hexdigest(),
                 'receipt': receipts[label], 'report': report})
    aggregate = {'order': 'ABBA', 'vsync_requested': False, 'harness_fixture_hashes': hashes,
                 'runs': runs}
    (root / 'work/forest-attachment-pairs.json').write_text(json.dumps(aggregate, indent=2) + '\n')
    (root / 'work/forest-attachment-pair-receipts.json').write_text(json.dumps(receipts, indent=2) + '\n')
    print(label, {key: report['moving_camera'][key] for key in
                 ('median_wall_frame_ms', 'p95_wall_frame_ms', 'draw_calls_mean')}, flush=True)
