"""Export optional explorer layers from one checked Yellowstone build."""
import argparse, copy, hashlib, json, sys
from pathlib import Path
import numpy as np

def export(root,out):
 m=json.loads((out/'data/manifest.json').read_text()); b=root/'yellowstone_python/derived'/m['build_id']; bm=json.loads((b/'BUILD.json').read_text()); sources={}
 def read(name):
  p=b/name; raw=p.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
  assert sha==bm['output_artifact_hashes'][name],name
  sources[str(p.relative_to(root))]=sha
  return raw
 def doc(name):return json.loads(read(name))
 def write(name,data):
  raw=json.dumps(data,separators=(',',':'),allow_nan=False).encode() if isinstance(data,(dict,list)) else data
  (out/'data'/name).write_bytes(raw);m['assets'][name]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 mats=doc('mat_state.json'); cooling=doc('outflow_temperature.json'); canopy=doc('lidar_canopy/unresolved_render_canopy.json'); replay=doc('river_replay.json')['replay']
 mat=np.frombuffer(read('mat_community.i16'),dtype='<i2').astype('<f4');write('mats.f32',mat.tobytes())
 write('outflow.f32',read('outflow_temperature.f32'))
 for key,name in [('cover_fraction','coverage'),('valid_fraction','coverage-support')]:write(name+'.f32',read('lidar_canopy/'+key+'.f32'))
 species=list(replay['frames'][0]['feeding_by_species']); feeding=np.array([[f['feeding_by_species'][s] for f in replay['frames']] for s in species],dtype='<f4');write('habitat.f32',feeding.tobytes())
 metadata={'build_id':m['build_id'],'sources':sources,'mats':{'grid':mats['grid'],'legend':mats['legend'],'area_m2_by_class':{str(c['class_id']):int((mat==c['class_id']).sum()) for c in mats['legend']},'source':'mat_state.json / mat_community.i16','description':'Temperature-based community classes with chosen pH and class boundaries. Colors follow an authored palette; these are not mapped field observations.'},'outflow':{'grid':cooling['grid'],'range_c':[float(np.nanmin(np.frombuffer(read('outflow_temperature.f32'),dtype='<f4'))),float(np.nanmax(np.frombuffer(read('outflow_temperature.f32'),dtype='<f4')))],'source':'outflow_temperature.json / outflow_temperature.f32','description':'Saved cooling calculation on a 1 m grid. Spring flows and heat-exchange assumptions have not been calibrated to this site.'},'coverage':{'grid':{'nx':canopy['width'],'nz':canopy['height'],'cell_size_m':canopy['cell_size_m'],'origin_xz_m':[-640,-640]},'source':'lidar_canopy/cover_fraction.f32','description':'Fraction of each 2 m cell covered by LiDAR canopy outside detected crown cores. Gaps in source coverage remain empty. This is surface cover, not a tree count.'},'habitat':{'species':species,'frames':len(replay['frames']),'cells':len(replay['cells']),'source':'river_replay.json / feeding_by_species','description':'Temperature feeding factor from the model’s species curves, from 0 to 1. It omits food, oxygen, cover and population abundance.'},'weather':{'rows':replay['weather_trace'],'cloud':replay['cloud'],'humidity':replay['humidity'],'source':'river_replay.json / weather_trace','description':'Saved scenario weather at one-minute intervals. These conditions were authored for the simulation, not observed at the site.'},'steam_sources':[]}
 pools=doc('pools_state.json')['pools']
 for p in pools:
  if p['id'] in cooling['spring_temps_c']:metadata['steam_sources'].append({'id':p['id'],'name':p['name'],'position_xz':p['center_xz'],'temperature_c':cooling['spring_temps_c'][p['id']]})
 # Re-run the published solver configuration, then change only the thermal-source temperature.
 sys.path.insert(0,str(root/'yellowstone_python'))
 from yellowstone_python.river.river_transport import river_from_config
 write('scenario-input.json',{'source_build':m['build_id'],'solver_config':replay['solver_config'],'solver_sha256':hashlib.sha256((root/'yellowstone_python/yellowstone_python/river/river_transport.py').read_bytes()).hexdigest(),'source_replay_sha256':sources[str((b/'river_replay.json').relative_to(root))],'source_file':'yellowstone_python/river/river_transport.py','duration_s':7200,'dt_s':1,'sample_s':10,'inflow_change_c':-5})
 config=copy.deepcopy(replay['solver_config']); reference=river_from_config(config); frames=reference.run(7200,1,10)
 error=max(abs(x-y) for f,g in zip(frames,replay['frames']) for x,y in zip(f['temperature_c'],g['temperature_c']))
 if error>1e-8:raise ValueError(f'Baseline does not reproduce: {error}')
 scenario=copy.deepcopy(config)
 for source in scenario['sources']:
  values=source['temperature_c'];source['temperature_c']={'times_s':values['times_s'],'values':[x-5 for x in values['values']]}
 # Both cases begin with the same stored water and hyporheic temperatures.
 scenario['initialize_steady']=False
 for cell,initial in zip(scenario['cells'],replay['frames'][0]['temperature_c']):cell['initial_c']=initial
 river=river_from_config(scenario); comparison=river.run(7200,1,10)
 write('scenario.json',{'id':'cooler-inflow','label':'Thermal inflow −5°C','changed_parameter':'Thermal-source entry temperatures reduced by 5°C; flow, weather, geometry and initial state unchanged. Ground overlays keep the original snapshot.','frames':[{'t':f['t_s'],'values':f['temperature_c']} for f in comparison],'baseline_max_error_c':error,'budget':comparison[-1]['budget'],'solver_sha256':hashlib.sha256((root/'yellowstone_python/yellowstone_python/river/river_transport.py').read_bytes()).hexdigest()})
 metadata['scenario']={'baseline_max_error_c':error,'initial_max_error_c':max(abs(x-y) for x,y in zip(comparison[0]['temperature_c'],replay['frames'][0]['temperature_c']))}
 write('layers.json',metadata);m['optional_layers']={'metadata':'layers.json','source_build':m['build_id']};(out/'data/manifest.json').write_text(json.dumps(m,separators=(',',':')))
 print(json.dumps({'source_files':len(sources),'scenario':metadata['scenario'],'species':species,'weather_samples':len(replay['weather_trace'])}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--out',type=Path,default=Path(__file__).parent);a=p.parse_args();export(a.root,a.out)
