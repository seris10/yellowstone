from pathlib import Path
import hashlib,json,subprocess
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter,map_coordinates
root=Path.cwd();directory=root/'evidence/terrace-contrast'
report=json.loads((directory/'report.json').read_text())
world=json.loads((root/'yellowstone_midway/data/world.json').read_text())
pool=next(p for p in world['pools'] if p['id']=='pool_1034_0')
linear=lambda x:np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
a=linear(np.asarray(Image.open(directory/'overhead-before.png'),float)/255)
b=linear(np.asarray(Image.open(directory/'overhead-after.png'),float)/255)
luma=np.array([.2126,.7152,.0722]);a=a@luma;b=b@luma
view=next(v for v in report['captures'] if v['id']=='overhead-after')
width,height=view['image_size'];pixel_m=view['orthogonal_size']/height
x,z=np.meshgrid(pool['center'][0]+(np.arange(width)+.5-width/2)*pixel_m,pool['center'][2]+(np.arange(height)+.5-height/2)*pixel_m)
packed=np.asarray(Image.open(root/'yellowstone_midway/assets/textures/prismatic_terrace_detail.png'),float)/255
sample=np.array([(z+640)/.625-.5,(x+640)/.625-.5])
edge=map_coordinates(packed[...,2],sample,order=1,mode='nearest');support=map_coordinates(packed[...,3],sample,order=1,mode='nearest')
radius=np.hypot(x-pool['center'][0],z-pool['center'][2]);mask=(radius>75)&(radius<150)&(support>.99)
sigma=8/pixel_m
feature=edge-gaussian_filter(edge,sigma)
records={}
for label,pixels in [('before',a),('after',b)]:
    ratio=pixels/np.maximum(gaussian_filter(pixels,sigma),.02)-1
    center_feature=feature[mask]-feature[mask].mean();center_ratio=ratio[mask]-ratio[mask].mean()
    records[label]={'mapped_edge_correlation':float(np.corrcoef(center_feature,center_ratio)[0,1]),'linear_luminance_contrast_regression':float(np.dot(center_feature,center_ratio)/np.dot(center_feature,center_feature)), 'contrast_std':float(ratio[mask].std())}
source_paths=['yellowstone_midway/assets/textures/prismatic_apron_display.png','yellowstone_midway/assets/textures/prismatic_terrace_detail.png','yellowstone_midway/assets/textures/prismatic_water_display.png','yellowstone_midway/assets/textures/mapped_surface_detail.png','yellowstone_midway/data/display/prismatic.json','yellowstone_midway/data/world.json','yellowstone_midway/references/midway_orthophoto_detail.jpg']
preserved={}
for rel in source_paths:
    actual=(root/rel).read_bytes();original=subprocess.check_output(['git','show','18f456de029bb528f23bd38a9f90125bcbb48bea:'+rel])
    preserved[rel]={'sha256':hashlib.sha256(actual).hexdigest(),'matches_source_commit':actual==original}
assert all(r['matches_source_commit'] for r in preserved.values())
old=(root/'work/thermal_apron_before.gdshader').read_text();new=(root/'yellowstone_midway/shaders/thermal_apron.gdshader').read_text()
normal_line='detail_xy += (terrace.rg * 2.0 - 1.0) * terrace.a * spring_support;'
assert normal_line in old and normal_line in new
assert old.count('texture(')==new.count('texture(')
source_only_change=new.replace(''' float mapped_contrast = abs(dot(surface.spatial_detail, vec3(0.2126, 0.7152, 0.0722)) - 1.0);
 float terrace_structure = max(smoothstep(0.06, 0.24, mapped_contrast), flow);
 float terrace_edge = terrace.b * terrace.a * spring_support * terrace_structure;
 base *= 1.0 - terrace_edge * 0.075;''',' base *= 1.0 - terrace.b * terrace.a * spring_support * 0.42;')==old
assert source_only_change
comparison=[]
for name in ('wide','overlook40','apron','overhead'):
    before=next(v for v in report['captures'] if v['id']==name+'-before');after=next(v for v in report['captures'] if v['id']==name+'-after')
    assert before['primitives']==after['primitives']
    assert before['draw_calls']==after['draw_calls']
    comparison.append({'view':name,'primitives_unchanged':before['primitives'],'draw_calls_unchanged':before['draw_calls']})
receipt={'scope':'Native raster comparison and independent source-preservation review; authored display correction, uncalibrated morphology. No frame-time or field-validation claim.','source_commit':'18f456de029bb528f23bd38a9f90125bcbb48bea','cause':'A periodic radial terrace edge mask multiplied albedo by up to0.42 across the apron, producing dark continuous rings independent of illumination or mapped flow structure.','correction':'Retain complete terrace normal contribution. Weight albedo edge by the larger of a mapped linear-light color-ratio contrast gate or current flow fraction; bound edge darkening at0.075. No additional texture fetches.','authored_parameters':{'mapped_contrast_smoothstep':[.06,.24],'maximum_albedo_darkening':.075,'previous_maximum_albedo_darkening':.42},'normal_term_unchanged':True,'texture_call_count_unchanged':True,'only_source_change_is_edge_contrast':source_only_change,'preserved_inputs':preserved,'views':comparison,'overhead_alignment_diagnostic':{'scope':'Association with the existing authored edge field; this is not a photographic-quality or scientific-accuracy score.','annulus_m':[75,150],'pixel_m':pixel_m,'eligible_pixels':int(mask.sum()),'local_luminance_mean_sigma_m':8,'records':records},'capture_report_sha256':hashlib.sha256((directory/'report.json').read_bytes()).hexdigest(),'shader_sha256':hashlib.sha256(new.encode()).hexdigest(),'source_limits':['The terrace generator still carries an unmeasured radial display field; this correction changes its albedo presentation only.','Mapped contrast describes aerial image structure, not surveyed terrace geometry.','Full camera/light/weather and human visual acceptance remain separate from these captures.'],'ok':True}
(directory/'review.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'shader_sha256':receipt['shader_sha256'],'overhead':records,'views':comparison,'preserved_inputs':len(preserved)},indent=2))
