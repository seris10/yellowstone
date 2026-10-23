"""Named dashboard scope, historical receipts, and strict stale behavior."""
import importlib.util
import json
from pathlib import Path
import sys
import pytest
from yellowstone_python.common.io import sha256_file

spec=importlib.util.spec_from_file_location('scoped_receipts',Path(__file__).parents[1]/'tools/run_evidence.py')
E=importlib.util.module_from_spec(spec);spec.loader.exec_module(E)


def receipt(root):
    inventory=E.inventory_for('dashboard')
    return {'status':'executed_passed','scope':'dashboard','complete_source_inventory':True,'source_inventory':inventory,'source_hashes':E.source_hashes(root,inventory)}


@pytest.mark.parametrize('mutation',['edit','add','remove','output'])
def test_dashboard_and_log_mutations(tmp_path,mutation):
    folder=tmp_path/'dashboard/src';folder.mkdir(parents=True)
    src=folder/'app.js';src.write_text('let n=1;')
    build=tmp_path/'dashboard/build_public.py';build.write_text('print(1)')
    r=receipt(tmp_path);assert 'dashboard/build_public.py' in r['source_hashes']
    log=tmp_path/'command.log';log.write_text('pass');r.update(output='command.log',output_sha256=sha256_file(log))
    assert E.evidence_status(r,tmp_path)=='executed_passed'
    if mutation=='edit':src.write_text('let n=2;')
    elif mutation=='add':(folder/'new.css').write_text('body{}')
    elif mutation=='remove':src.unlink()
    else:log.write_text('altered')
    assert E.evidence_status(r,tmp_path)=='stale'


def test_historical_inventory_not_relabelled(tmp_path):
    folder=tmp_path/'yellowstone_python/yellowstone_python';folder.mkdir(parents=True);(folder/'model.py').write_text('x=1')
    r={'status':'executed_passed','source_hashes':E.source_hashes(tmp_path),'complete_source_inventory':True}
    dash=tmp_path/'dashboard';dash.mkdir();(dash/'test.mjs').write_text('x=2')
    assert E.evidence_status(r,tmp_path)=='executed_passed'


@pytest.mark.parametrize('strict,expected',[(False,0),(True,2)])
def test_strict_stale_exit(tmp_path,monkeypatch,strict,expected):
    tool=tmp_path/'yellowstone_python/tools/run_evidence.py';tool.parent.mkdir(parents=True);tool.write_text('')
    folder=tmp_path/'dashboard';folder.mkdir();source=folder/'app.js';source.write_text('before')
    monkeypatch.setattr(E,'__file__',str(tool));monkeypatch.chdir(tmp_path)
    argv=['run_evidence','--name','synthetic','--scope','dashboard']+(['--strict'] if strict else [])+['--',sys.executable,'-c',"from pathlib import Path;Path('dashboard/app.js').write_text('after')"]
    monkeypatch.setattr(sys,'argv',argv)
    assert E.main()==expected
    r=json.loads(next((tmp_path/'evidence/receipts').glob('*.json')).read_text())
    assert r['status']=='stale' and r['scope']=='dashboard'


def test_scoped_source_symlink_refused(tmp_path):
    folder=tmp_path/'dashboard';folder.mkdir();other=tmp_path/'source.js';other.write_text('1');(folder/'link.js').symlink_to(other)
    with pytest.raises(ValueError):E.source_hashes(tmp_path,E.inventory_for('dashboard'))
