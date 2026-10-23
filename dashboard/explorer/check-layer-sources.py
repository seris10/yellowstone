"""Compare exported analysis arrays with the immutable source build."""
import argparse,hashlib,json
from pathlib import Path
import numpy as np

def main(root,out):
 data=out/'data';m=json.loads((data/'layers.json').read_text());b=root/'yellowstone_python/derived'/m['build_id'];checks=[]
 def check(name,condition):
  if not condition:raise AssertionError(name)
  checks.append(name)
 for file,sha in m['sources'].items():check('source hash: '+file,hashlib.sha256((root/file).read_bytes()).hexdigest()==sha)
 for source,target,dtype in [('mat_community.i16','mats.f32','<i2'),('outflow_temperature.f32','outflow.f32','<f4'),('lidar_canopy/cover_fraction.f32','coverage.f32','<f4'),('lidar_canopy/valid_fraction.f32','coverage-support.f32','<f4')]:
  a=np.fromfile(b/source,dtype=dtype).astype('<f4');c=np.fromfile(data/target,dtype='<f4');check('exact array: '+target,np.array_equal(a,c,equal_nan=True))
 source=json.loads((b/'river_replay.json').read_text())['replay'];feeding=np.array([[f['feeding_by_species'][s] for f in source['frames']] for s in m['habitat']['species']],dtype='<f4');check('all saved feeding factors',np.array_equal(feeding.ravel(),np.fromfile(data/'habitat.f32',dtype='<f4')));check('exact weather rows',source['weather_trace']==m['weather']['rows']);check('weather time support',m['weather']['rows'][0]['t_s']==0 and m['weather']['rows'][-1]['t_s']==source['frames'][-1]['t_s']);pools={p['id']:p for p in json.loads((b/'pools_state.json').read_text())['pools']};check('all steam anchors',all(p['position_xz']==pools[p['id']]['center_xz'] for p in m['steam_sources']));print(json.dumps({'checks':checks,'passed':len(checks),'failed':0},indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,default=Path(__file__).parent);a=p.parse_args();main(a.root,a.out)
