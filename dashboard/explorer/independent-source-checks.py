"""Independent retained-source comparison without importing the exporter."""
from pathlib import Path
import argparse
import hashlib,json,math,platform
import numpy as np
from PIL import Image
parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);parser.add_argument('--out',type=Path,default=Path(__file__).parent);args=parser.parse_args()
root=args.root
out=args.out;data=out/'data';m=json.loads((data/'manifest.json').read_text());build=root/'yellowstone_python/derived'/m['build_id'];b=json.loads((build/'BUILD.json').read_text());checks=[]
def check(name,passed,**details):
 checks.append({'name':name,'passed':bool(passed),**details})
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
check('source_build_identity',m['build_id']==b['build_id']=='cca3820afdd4' and m['source_commit']==b['code_commit'],build_id=m['build_id'],source_commit=m['source_commit'])
for name,expected in m['sources'].items():check('source_sha256:'+name,digest(root/name)==expected)
for name,info in m['assets'].items():check('export_sha256:'+name,digest(data/name)==info['sha256'] and (data/name).stat().st_size==info['bytes'])
source=json.loads((build/'river_replay.json').read_text())['replay'];target=json.loads((data/'replay.json').read_text())
check('river_manifest_source_binding',digest(build/'river_replay.json')==b['output_artifact_hashes']['river_replay.json'])
check('river_cell_count',len(source['cells'])==len(target['cells'])==m['cell_count'],count=len(target['cells']))
fields=['id','position_xyz','river_id','start_s_m','end_s_m','center_s_m','width_m','depth_m']
check('every_exported_river_cell_field',all(all(src[field]==dst[field] for field in fields) for src,dst in zip(source['cells'],target['cells'])),fields=fields)
check('all_temperature_values_and_frame_times',len(source['frames'])==len(target['frames'])==m['frame_count'] and all(s['temperature_c']==t['values'] and s['t_s']==t['t'] for s,t in zip(source['frames'],target['frames'])),frame_count=len(target['frames']),value_count=sum(len(f['values']) for f in target['frames']))
check('connection_identity',source.get('source_connections',[])==target['source_connections'])
values=np.array([f['values'] for f in target['frames']]);check('temperature_range',m['temperature_range_c']==[float(values.min()),float(values.max())] and np.isfinite(values).all(),minimum_c=float(values.min()),maximum_c=float(values.max()))
world=json.loads((build/'world.runtime.json').read_text());geo=world['georeference'];check('coordinate_origin_contract',geo==source['georeference']==m['georeference'] and geo['crs']=='EPSG:32612' and geo['origin'][2]==2200 and geo['vertical_datum']=='NAVD88',origin_utm_height=geo['origin'],formula='x=E-E0; z=N0-N; y=H-H0')
refs=root/'yellowstone_midway/references';broad_meta=json.loads((refs/'terrain_source.json').read_text());broad=np.fromfile(refs/'terrain_source.f32',dtype='<f4').reshape(broad_meta['height'],broad_meta['width']);exported=np.fromfile(data/'terrain-full.f32',dtype='<f4').reshape(m['terrain']['full']['n'],m['terrain']['full']['n'])
check('every_broad_terrain_sample',np.array_equal(broad,exported),sample_count=int(exported.size),maximum_abs_error_m=float(np.max(np.abs(broad-exported))))
check('broad_coordinates',broad_meta['row_order']=='north_to_south' and broad_meta['origin_utm_m']==geo['origin'][:2] and m['terrain']['full']['start']==broad_meta['sample_bounds_local_xz_m'][:2] and m['terrain']['full']['spacing_m']==broad_meta['spacing_m'],edge_coordinates_m=[-2048,2048])
img=Image.open(refs/'dem_1m_core.tif');core=np.asarray(img);exported=np.fromfile(data/'terrain-core.f32',dtype='<f4').reshape(m['terrain']['core']['n'],m['terrain']['core']['n'])
check('every_core_terrain_sample',np.array_equal(core[::2,::2],exported),sample_count=int(exported.size),maximum_abs_error_m=float(np.max(np.abs(core[::2,::2]-exported))))
scale=img.tag_v2.get(33550);tie=img.tag_v2.get(33922)
first=[tie[3]+scale[0]/2-geo['origin'][0],geo['origin'][1]-(tie[4]-scale[1]/2)]
last=[first[0]+scale[0]*(exported.shape[1]-1)*2,first[1]+scale[1]*(exported.shape[0]-1)*2]
check('core_pixel_center_coordinates_from_geotiff',np.allclose(first,m['terrain']['core']['start'],rtol=0,atol=1e-8) and m['terrain']['core']['spacing_m']==2*scale[0] and scale[0]==scale[1],first_retained_center_xz_m=first,last_retained_center_xz_m=last,pixel_scale_m=list(scale))
src=json.loads((build/'census.json').read_text())['payload'];dst=json.loads((data/'crowns.json').read_text());fields=dst['fields'];check('canopy_source_binding',digest(build/'census.json')==b['output_artifact_hashes']['census.json']);check('every_canopy_field',dst['rows']==[[tree[k] for k in fields] for tree in src['trees']],count=len(dst['rows']),field_count=len(fields),fields=fields);check('canopy_provenance_and_status',dst['source']==src['source'] and dst['status']==src['status'] and len(dst['rows'])==m['crown_count'])
features=json.loads((data/'features.json').read_text());pools=json.loads((build/'pools_state.json').read_text())
check('all_mapped_river_polylines',len(features['rivers'])==len(world['rivers']) and all(s['id']==t['id'] and s['points']==t['points'] for s,t in zip(world['rivers'],features['rivers'])))
check('all_route_polylines',len(features['routes'])==len(world['routes']) and all(s['id']==t['id'] and s['kind']==t['kind'] and s['points']==t['points'] for s,t in zip(world['routes'],features['routes'])))
check('all_selected_pool_fields',len(features['pools'])==len(pools['pools']) and all(all(s[k]==v for k,v in t.items()) for s,t in zip(pools['pools'],features['pools'])))
check('anchors_retained',features['anchors']==world['anchors'])
# Change one byte in memory to confirm the checksum comparison can reject it.
blob=(data/'replay.json').read_bytes();altered=bytes([blob[0]^1])+blob[1:];check('negative_control_changed_asset_rejected',hashlib.sha256(altered).hexdigest()!=m['assets']['replay.json']['sha256'])
report={'schema':'yellowstone.independent_export_checks.v1','method':'Separate comparison script; exporter not imported; every retained value compared with its declared source','environment':{'python':platform.python_version(),'platform':platform.platform()},'build_id':m['build_id'],'exporter_sha256':digest(out/'export.py'),'manifest_sha256':digest(data/'manifest.json'),'checker_sha256':digest(Path(__file__)),'checks':checks,'passed':sum(c['passed'] for c in checks),'failed':sum(not c['passed'] for c in checks),'limitations':['Data/export checks do not establish browser interaction, visual quality, gameplay, or scientific field validity.','Terrain reference rasters are independently source-hashed references, separate from the immutable model build.']}
(out/'independent-source-checks.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'passed':report['passed'],'failed':report['failed']},indent=2));assert not report['failed']
