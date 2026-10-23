"""Reproduce the saved comparison with an installed Yellowstone solver."""
import argparse,copy,hashlib,inspect,json
from pathlib import Path
from yellowstone_python.river.river_transport import river_from_config

def main(out):
 data=out/'data';inputs=json.loads((data/'scenario-input.json').read_text());baseline=json.loads((data/'replay.json').read_text());saved=json.loads((data/'scenario.json').read_text())
 path=Path(inspect.getfile(river_from_config));actual=hashlib.sha256(path.read_bytes()).hexdigest()
 if actual!=inputs['solver_sha256']:raise ValueError('Installed solver differs from the recorded source hash')
 config=copy.deepcopy(inputs['solver_config']);river=river_from_config(config);frames=river.run(inputs['duration_s'],inputs['dt_s'],inputs['sample_s'])
 baseline_error=max(abs(a-b) for f,g in zip(frames,baseline['frames']) for a,b in zip(f['temperature_c'],g['values']))
 if baseline_error>1e-8:raise ValueError(f'Baseline reproduction error: {baseline_error}')
 for source in config['sources']:source['temperature_c']['values']=[v+inputs['inflow_change_c'] for v in source['temperature_c']['values']]
 config['initialize_steady']=False
 for cell,initial in zip(config['cells'],baseline['frames'][0]['values']):cell['initial_c']=initial
 river=river_from_config(config);frames=river.run(inputs['duration_s'],inputs['dt_s'],inputs['sample_s'])
 error=max(abs(a-b) for f,g in zip(frames,saved['frames']) for a,b in zip(f['temperature_c'],g['values']))
 if error>1e-8:raise ValueError(f'Comparison reproduction error: {error}')
 print(json.dumps({'baseline_max_error_c':baseline_error,'comparison_max_error_c':error,'frames':len(frames),'solver_sha256':actual}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path(__file__).parent);a=p.parse_args();main(a.out)
