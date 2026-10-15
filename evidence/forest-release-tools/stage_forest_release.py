from pathlib import Path
import json
import subprocess

root=Path(__file__).resolve().parents[1]
assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=root).strip()
paths=set()
for name in ['floor','spring','atmosphere','submission']:
 d=json.loads((root/f'work/forest-stage-{name}.json').read_text())
 paths.update(d.get('files',[]));paths.update(d.get('paths',[]))
paths.update(['README.md','docs/PERFORMANCE.md','yellowstone_midway/data/release.json','yellowstone_midway/data/asset_manifest.json','yellowstone_python_spec/fixes/ledger/fixes-57.md'])
paths.update(['yellowstone_midway/scripts/tree_submission.gd',
              'yellowstone_midway/scripts/tree_submission.gd.uid',
              'yellowstone_midway/scripts/world.gd',
              'yellowstone_midway/tools/validate_tree_submission.gd',
              'yellowstone_midway/tools/validate_tree_submission.gd.uid',
              'evidence/atmosphere-world-rain-comparison.json',
              'evidence/tree-instance-lod.json'])
extra = root / 'work/forest-release-stage-extra.json'
if extra.is_file():
 d=json.loads(extra.read_text())
 assert isinstance(d,list) and all(isinstance(p,str) for p in d)
 paths.update(d)
for pattern in ['evidence/forest-*.json','evidence/color-mip-release-inventory.json']:
 paths.update(str(p.relative_to(root)) for p in root.glob(pattern))
for directory in ['evidence/forest-render','evidence/forest-render-pairs','evidence/forest-render-pairs-uncompacted']:
 paths.update(str(p.relative_to(root)) for p in (root/directory).rglob('*') if p.is_file())
for p in (root/'evidence/receipts').glob('*.json'):
 d=json.loads(p.read_text())
 if d.get('name','').startswith('forest-'):
  paths.add(str(p.relative_to(root)));paths.add(str(p.with_suffix('.log').relative_to(root)))
pointer=json.loads((root/'yellowstone_midway/data/release.json').read_text())
generation=root/'yellowstone_midway'/Path(pointer['manifest']).parent
paths.update(str(p.relative_to(root)) for p in generation.rglob('*') if p.is_file())
assert not any(p.startswith('dashboard/') or p=='yellowstone_python_spec/04_PARK_STREAMING_SPEC.md' for p in paths)
assert all(not Path(p).is_absolute() and '..' not in Path(p).parts for p in paths)
paths=sorted(p for p in paths if (root/p).is_file())
for p in paths:
 assert (root/p).stat().st_size < 100_000_000,p
subprocess.run(['git','add','--',*paths],cwd=root,check=True)
staged=subprocess.check_output(['git','diff','--cached','--name-only'],cwd=root,text=True).splitlines()
assert not any(p.startswith('dashboard/') for p in staged)
(root/'work/forest-release-staged.json').write_text(json.dumps(staged,indent=2)+'\n')
print('Staged',len(staged),'task-owned files')
