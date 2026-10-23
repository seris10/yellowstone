"""Isolated source, fixture, and log mutation demonstrations."""
import argparse
import importlib.util
import json
from pathlib import Path
from yellowstone_python.common.io import sha256_file


def main():
    """Record freshness changes without touching the actual project artifacts."""
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):parser.error('output directory must be empty')
    spec=importlib.util.spec_from_file_location('scoped_receipts',Path(__file__).parents[2]/'tools/run_evidence.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    root=args.out/'synthetic';folder=root/'dashboard/src';folder.mkdir(parents=True)
    source=folder/'app.js';source.write_text('export const temperatureC = 15;\n')
    forcing=root/'forcing.json';forcing.write_text('{"class":"synthetic","temperature_c":15}\n')
    log=root/'command.log';log.write_text('Synthetic fixture execution complete.\n')
    inventory=module.inventory_for('dashboard')
    receipt={'schema':'yellowstone.command_receipt.v2','scope':'dashboard','status':'executed_passed','complete_source_inventory':True,'source_inventory':inventory,'source_hashes':module.source_hashes(root,inventory),'fixture_hashes':{'forcing.json':sha256_file(forcing)},'output':'command.log','output_sha256':sha256_file(log),'command':['synthetic fixture construction; no subprocess claim']}
    states={'original':module.evidence_status(receipt,root)}
    for name,path in [('source_changed',source),('fixture_changed',forcing),('output_changed',log)]:
        original=path.read_bytes();path.write_bytes(original+b'changed');states[name]=module.evidence_status(receipt,root);path.write_bytes(original)
    added=folder/'added.css';added.write_text('body{}');states['source_added']=module.evidence_status(receipt,root);added.unlink()
    original=source.read_bytes();source.unlink();states['source_removed']=module.evidence_status(receipt,root);source.write_bytes(original)
    states['restored']=module.evidence_status(receipt,root)
    expected={k:('executed_passed' if k in ('original','restored') else 'stale') for k in states}
    result={'fixture_class':'synthetic','scope':'dashboard','states':states,'passed':states==expected,'limitations':['Hash matching demonstrates freshness for the named inventory, not correctness or trusted authorship.','No historical receipt has been relabeled.']}
    (args.out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n');(args.out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
