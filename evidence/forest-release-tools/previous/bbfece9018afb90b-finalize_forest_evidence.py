from pathlib import Path
import argparse
import hashlib
import json
import shutil
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'yellowstone_python'))
from tools.run_evidence import evidence_status
from forest_runtime_scope import scoped_receipt_status
from forest_benchmark_evidence import validate_benchmark
parser = argparse.ArgumentParser()
parser.add_argument('--submission-report', default='evidence/forest-tree-submission.json')
parser.add_argument('--receipt-manifest', required=True)
parser.add_argument('--pairs', required=True, help='Exact final ABBA aggregate JSON path')
parser.add_argument('--canopy-report', default='evidence/canopy-visible-attachments.json')
args = parser.parse_args()
equivalence = json.loads((root/'evidence/forest-runtime-equivalence.json').read_text())
assert equivalence['ok']
submission = json.loads((root/args.submission_report).read_text())
assert submission['ok'] and len(submission['native']) >= 3
for key, relative in [('source_sha256', 'yellowstone_midway/scripts/tree_submission.gd'),
                      ('world_sha256', 'yellowstone_midway/scripts/world.gd'),
                      ('scene_sha256', 'yellowstone_midway/scenes/authored_world.tscn')]:
    assert submission[key] == hashlib.sha256((root/relative).read_bytes()).hexdigest(), relative
pairs = json.loads((root/args.pairs).read_text())
pairs['aggregate_input'] = {'path':args.pairs,'sha256':hashlib.sha256((root/args.pairs).read_bytes()).hexdigest()}
assert [run['run'] for run in pairs['runs']] == ['a1','b1','b2','a2']
pairs['schema'] = 'yellowstone.forest_render_pairs.v1'
pairs['baseline_release'] = 'b2b3d24fd7a0b08bdd63c34576aefd01412875728a5233935c6bd6ae992900ee'
pairs['updated_release'] = equivalence['release_id']
pairs['model_source_commit'] = equivalence['model_source_commit']
pairs['runtime_source_commit'] = equivalence['runtime_source_commit']
pairs['runtime_source_identity'] = equivalence['runtime_source_identity']
pairs['scoped_runtime_identity'] = equivalence['scoped_runtime_identity']
pairs['receipt_scope_status'] = {}
specifications = json.loads((root/args.receipt_manifest).read_text())
assert set(specifications) == {'a1','b1','b2','a2'}
pairs['measurement_receipts'] = {key:value['path'] for key,value in specifications.items()}
pairs['measurement_receipt_names'] = {key:value['name'] for key,value in specifications.items()}
receipt_objects = {}
for label in ['a1','b1','b2','a2']:
    receipt = json.loads((root/pairs['measurement_receipts'][label]).read_text())
    assert receipt['name'] == specifications[label]['name']
    status = scoped_receipt_status(receipt, root)
    assert status['scoped_runtime_identity'] == equivalence['scoped_runtime_identity']
    assert status['status'] == 'executed_passed', ('Fresh source-bound ABBA receipt required',label)
    pairs['receipt_scope_status'][label] = status
    receipt_objects[label] = receipt
pairs['benchmark_verification'] = validate_benchmark(pairs, receipt_objects, root)
pairs['scope'] = pairs['benchmark_verification']['scope']
pairs['acceptance_target'] = {'median_wall_frame_ms_max': 33.4, 'p95_wall_frame_ms_max': 50.0}
pairs['harness_sha256'] = pairs['runs'][0]['report']['benchmark_fixture']['harness_sha256']
rows = []
for run in pairs['runs']:
    m = run['report']['moving_camera']
    assert run['report']['ok'] and all(step == 1 for step in m['drawn_frame_steps'])
    assert run['report']['release_id'] == (pairs['baseline_release'] if run['run'].startswith('a') else pairs['updated_release'])
    run['passes_target'] = m['median_wall_frame_ms'] <= 33.4 and m['p95_wall_frame_ms'] <= 50.0
    version = 'Published surface package' if run['run'].startswith('a') else 'Forest and spring update'
    rows.append(f"| {run['run'].upper()} | {version} | {m['median_wall_frame_ms']:.3f} | {m['p95_wall_frame_ms']:.3f} | {m['draw_calls_mean']:.3f} |")
    source = root / run.get('capture_directory',str(Path(run['world']) / ('work/forest-paired-' + run['run'])))
    assert json.loads((source/'report.json').read_text()) == run['report'], ('Aggregate/raw mismatch',run['run'])
    run['raw_report_sha256'] = hashlib.sha256((source/'report.json').read_bytes()).hexdigest()
    destination = root / 'evidence/forest-render-pairs' / run['run']
    destination.mkdir(parents=True, exist_ok=True)
    for path in source.glob('*'):
        if path.is_file(): shutil.copy2(path, destination/path.name)
    run['capture_directory'] = str(destination.relative_to(root))
(root/'evidence/forest-render-pairs.json').write_text(json.dumps(pairs,indent=2)+'\n')
old = [r['report']['moving_camera'] for r in pairs['runs'] if r['run'].startswith('a')]
new = [r['report']['moving_camera'] for r in pairs['runs'] if r['run'].startswith('b')]
draw_delta = (sum(x['draw_calls_mean'] for x in new)/sum(x['draw_calls_mean'] for x in old)-1)*100
median_delta = (sum(x['median_wall_frame_ms'] for x in new)/sum(x['median_wall_frame_ms'] for x in old)-1)*100
summary = f'The mean of the two run medians changes by {median_delta:+.1f} percent; mean draw calls change by {draw_delta:+.1f} percent. These four short wall-time runs do not isolate GPU cost or establish performance on other hardware.'
submission_rows = []
control_noise = []
for record in submission['native']:
    assert record['compaction_difference']['changed_channels'] == 0
    for control in ('repeat_difference','restoration_difference','recompaction_difference'):
        difference = record.get(control,{})
        if int(difference.get('changed_channels',0)):
            control_noise.append(f"{record['id']} {control}: {difference['changed_channels']} changed channels, maximum {difference['maximum_byte_difference']}/255")
    before = float(record['uncompacted_primitives'])
    after = float(record['compacted_primitives'])
    assert after < before
    submission_rows.append(f"| {record['id']} | {before:,.0f} | {after:,.0f} | {(after/before-1)*100:+.1f}% | 0 |")
source_instances = int(submission['native'][0]['submission']['source_instances'])
assert all(int(record['submission']['source_instances']) == source_instances for record in submission['native'])
cpu_bytes = source_instances * (20 * 4 + 3 * 4)
gpu_bytes = source_instances * 20 * 4
selection_bytes_max = source_instances * 4
control_scope = ('Independent repeated/rebound controls show ' + '; '.join(control_noise) + '. '
                 'The original-to-compacted gate retains exact equality; no image tolerance was widened. '
                 'The control variability limits a general claim of perfectly deterministic raster output.'
                 if control_noise else 'All recorded repeat, restored-original and recompaction controls also have zero changed channels in this run. This does not establish deterministic output in other scenes or driver states.')
control_scope += ' ' + ' '.join(item for item in submission.get('limitations',[]) if 'Earlier whole-scene controls' in item)
submission_text = '''The runtime retains immutable source Multimeshes and fills a separate visible prefix for near/middle LOD submission. It selects the same per-tree center-distance interval as the shader, expanded by a 2 m guard, and refreshes after more than 1 m of camera movement or a camera change. Far impostors and all source instances remain available. No view-frustum filter removes off-screen shadow casters. The existing shader still controls the final LOD selection and complementary transition.

The isolated native comparison uses the same frozen saved world with compaction disabled and enabled. The original-to-compacted images, including visible shadows, match exactly in the tested views. Submitted primitive changes are separate from frame-time changes:

| View | Uncompacted primitives | Compacted primitives | Change | Changed image channels |
|---|---:|---:|---:|---:|
''' + '\n'.join(submission_rows) + '\n\n' + control_scope + f'''

The source arrays contain {source_instances:,} near/middle instance records. Retaining 20-float records plus three-float centers accounts for {cpu_bytes:,} bytes of CPU data payload; cloned 20-float GPU instance buffers account for {gpu_bytes:,} bytes of additional GPU payload. Retained selection indices add up to {selection_bytes_max:,} bytes. These are format-based payload estimates, excluding allocator, resource, temporary-array and driver overhead; they are not measured total resident memory. Compaction trades those allocations and intermittent CPU selection/upload work for fewer submitted instances. The validator records update time and changed slots per tested position; these observations are not a whole-session CPU bound.

The uncompacted regression remains in `evidence/forest-render-pairs-uncompacted.json` and its raw capture directory. The intermediate pre-attachment run also remains historical; its B1/B2 initial-sun discrepancy prevents a causal performance interpretation. The final ABBA table above measures the adopted runtime. These are different experiments and are retained separately.
'''
text = '''# Render measurement

The reference is Apple M4, macOS arm64, Godot 4.5.1, Metal Forward Mobile, 1440 by 900, 4x MSAA, walking shadows at 140 m and a 4096 atlas.
''' + f"\nThe numerical generation is `{equivalence['release_id']}`, from build `{equivalence['build_id']}` at model source commit `{equivalence['model_source_commit']}`. The runtime source commit is `{equivalence['runtime_source_commit']}`. `evidence/forest-runtime-equivalence.json` authenticates unchanged model sources, physical inputs and checked artifacts, while separately identifying the display submission revision and asset metadata correction. The baseline is the previously published surface package `b2b3d24fd7a0`.\n" + '''

The identical work-only native harness runs in ABBA order after model builds, tests and editor imports finish. Each run captures nine fixed views, then 60 warmup and 120 moving-camera samples. Every measured sample advances exactly one drawn frame. A common authored fixture locks weather, epoch and the physical sun vector; it normalizes the old sun convention in memory without changing either package. This compares the releases under shared forcing, not unchanged as-shipped default lighting. Requested values are independently checked, then checked for drift over all captures and moving frames; input callbacks and external readers are disabled. Tree wind is disabled, while shader TIME and particles remain animated. Vsync is disabled by request; wall time includes presentation and the common forcing-verification overhead. The GPU monitor is unavailable. Desktop applications remain uncontrolled; these are not isolated GPU measurements. Original receipts retain their full inventories and global status. Runtime comparisons exclude exactly `dashboard/build_data.py`, an unbundled dashboard generator outside the numerical source-hash roots; its observed hash and any global staleness remain explicit. All included source, fixture and output hashes remain strict.

| Run | Version | Median wall frame, ms | p95 wall frame, ms | Mean draw calls |
|---|---|---:|---:|---:|
''' + '\n'.join(rows) + '\n\n' + summary + '\n\n' + submission_text + '''

The retained acceptance target is median <= 33.4 ms and p95 <= 50 ms. Each run's explicit target result is in `evidence/forest-render-pairs.json`; no 60 fps claim is made. Earlier surface measurements remain in `evidence/surface-render-pairs.json`. An initial baseline attempt lacked its Godot class cache and timed out without samples; its failed receipt is retained and excluded from this table.

All 63,565 trees, 159,157 residual-canopy cells, existing render distances, shadows and antialiasing remain enabled. Crown architecture, per-instance complementary LOD selection, boundary-specific batch padding and reduced canopy geometry accompany 24,000 litter beds, 18,000 plant patches, 1,600 logs and 24 snags. Display counts are authored. At the original model/source snapshot, saved tree bindings passed 2,758,746 native checks over 22,254 batches and a capacity of 635,650 LOD instances. The equivalence proof preserves those baked inputs; this historical run is distinct from the final runtime compaction and canopy checks. That capacity describes the immutable baked records; it is not the number submitted after runtime compaction. Selection and source-retention checks do not establish endpoint image fidelity.

Final raw tree endpoint budgets pass 34 of 96 comparisons: 8/32 at 18 m, 8/32 at 65 m and 18/32 at 180 m. The remaining 62 failures and all raw captures remain public. Far billboard brightness differs from dynamically lit meshes. Dithering does not turn mismatched endpoints into a visual pass. Thin residual-canopy supports and simplified straight logs remain visible close up.

Color mipmaps are filtered offline in linear light, with original level-zero pixels and the same per-texture RGBA8 mip layout. Eight buffers add 111,848,096 distribution bytes. The added forest material layers increase texture storage; unchanged sampler count does not imply unchanged total GPU memory. Mixed forest pixels add up to four texture reads, and the spring apron adds two detail reads. Four cloud density samples bound atmospheric work. These costs and structural savings are distinct from measured frame time.

Scientific claims remain unaccepted. Ground-cover abundance, crown envelopes, ring widths, terrace relief and rainbow occurrence frequency are authored or uncalibrated. Previous deer/badger deformation and textured mesh-reduction acceptance gaps remain open. Other platforms, native executable exports and whole-world live-service timing are untested.

Evidence: `evidence/forest-render-pairs.json`, `evidence/forest-render-pairs-uncompacted.json`, `evidence/forest-runtime-equivalence.json`, `evidence/forest-tree-submission.json`, `evidence/forest-baseline-bytes.json`, `evidence/forest-verification.json`, `evidence/forest-render/report.json`, `evidence/tree-lod-quality.json`, `evidence/tree-lod-appearance.json`, `evidence/atmosphere-color-mips.json` and `evidence/forest-package.json`.
'''
canopy_path = root / args.canopy_report
if canopy_path.is_file():
    canopy_report = json.loads(canopy_path.read_text())
    assert canopy_report['ok'] and not canopy_report['failures'] and canopy_report['checks'] > 0
    assert canopy_report['source_hashes'] and canopy_report['native_views']
    for path, expected in canopy_report['source_hashes'].items():
        assert hashlib.sha256((root/path).read_bytes()).hexdigest() == expected, path
    for view in canopy_report['native_views']:
        assert hashlib.sha256((root/view['path']).read_bytes()).hexdigest() == view['sha256'], view['path']
    text = text.replace('Thin residual-canopy supports and simplified straight logs remain visible close up.',
        ' '.join(canopy_report['limitations']) + ' Final canopy attachment checks are recorded in `' + args.canopy_report + '`.')
(root/'docs/PERFORMANCE.md').write_text(text)
(root/'work/forest-performance-summary.json').write_text(json.dumps({'summary':summary,'median_percent_change':median_delta,'draw_percent_change':draw_delta,'all_targets_pass':all(r['passes_target'] for r in pairs['runs']),'rows':[[r['run'].upper(),'Previous release' if r['run'].startswith('a') else 'Update',round(r['report']['moving_camera']['median_wall_frame_ms'],3),round(r['report']['moving_camera']['p95_wall_frame_ms'],3)] for r in pairs['runs']]},indent=2)+'\n')
print(summary)
