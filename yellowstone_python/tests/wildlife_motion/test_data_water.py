import csv
import numpy as np
import pytest
from yellowstone_python.wildlife_motion.water import *
from yellowstone_python.wildlife_motion.variation import *
from yellowstone_python.wildlife_motion.calibration import *
from yellowstone_python.wildlife_motion.synthetic import bird_proxy


def test_submerged_volume():
 np.testing.assert_allclose(submerged_fraction(np.array([-2,-1,0,1,2])),[0,0,.5,1,1])
 q=np.linspace(-1,1,100);assert np.all(np.diff(submerged_fraction(q))>=0)

def test_float_equilibrium():
 c=WaterConfig(wave_amplitude_m=0,foot_area_m2=0);y=equilibrium_center_height(c)
 state=np.zeros(8);state[1]=y;force,torque,_=water_forces(0,state,c)
 np.testing.assert_allclose(force,np.zeros(3),atol=1e-9)
 r=simulate(c,.2,10);np.testing.assert_allclose(r['states'][:,1],y,atol=1e-9)

def test_sink_rejected():
 with pytest.raises(ValueError):equilibrium_center_height(WaterConfig(mass_kg=100))

@pytest.mark.parametrize('change',[{'mass_kg':-1},{'power_fraction':1},{'wave_length_m':0},{'steering_bias':1}])
def test_invalid_water(change):
 with pytest.raises(ValueError):WaterConfig(**change)

def test_water_finite_forward():
 r=simulate(WaterConfig(wave_amplitude_m=0),.4,15)
 assert np.isfinite(r['states']).all();assert r['states'][-1,2]>0

def test_identity_warp_and_rig():
 a,s,j,w=bird_proxy();v,rs=diversify(a,s,Variant())
 np.testing.assert_allclose(v.vertices,a.vertices,atol=1e-12);np.testing.assert_allclose(rs.rest,s.rest,atol=1e-12)

def test_repeatable_artistic_variant():
 assert asdict(sample_artistic(7))==asdict(sample_artistic(7))
 assert asdict(sample_artistic(7))!=asdict(sample_artistic(8))
 with pytest.raises(ValueError):Variant(head_size=5)


def write_population(path,repeats=1):
 with path.open('w',newline='') as f:
  writer=csv.writer(f);writer.writerow(['specimen_id',*FEATURES,'sex'])
  for i in range(6):
   for _ in range(repeats):writer.writerow([f's{i}',*[1+.004*i]*6,'unknown'])

def test_population_individual_not_image(tmp_path):
 p=tmp_path/'a.csv';q=tmp_path/'b.csv';write_population(p,1);write_population(q,7)
 a=fit_population(p);b=fit_population(q)
 assert a['n_specimens']==b['n_specimens']==6;assert b['n_observations']==42
 np.testing.assert_allclose(a['log_mean'],b['log_mean'],atol=1e-12)
 assert asdict(sample_population(a,17))==asdict(sample_population(a,17))

def test_population_small_sample(tmp_path):
 p=tmp_path/'a.csv';write_population(p)
 with pytest.raises(ValueError):fit_population(p,{'sex':'female'})

def test_periodic_fit_exact():
 t=np.linspace(0,2,101);x=1+.2*np.sin(2*np.pi*1.5*t)-.5*np.cos(4*np.pi*1.5*t)
 m=fit_periodic_track(t,x,1.5,harmonics=2)
 np.testing.assert_allclose(evaluate_track(m,t).ravel(),x,atol=1e-12)

def test_gait_event_fit(tmp_path):
 p=tmp_path/'e.csv'
 with p.open('w',newline='') as f:
  w=csv.writer(f);w.writerow(['specimen_id','cycle_id','limb','touchdown_s','liftoff_s','next_touchdown_s','cycle_origin_s'])
  for i in range(3):
   for cycle in range(2):
    for limb,phase in [('HL',0),('FL',.25),('HR',.5),('FR',.75)]:
     t=cycle+phase;w.writerow([f's{i}',cycle,limb,t,t+.65,t+1,cycle])
 m=fit_gait_events(p,100,5);assert m['overrides']['frequency_hz']==pytest.approx(1)
 assert m['overrides']['duty_factor']==pytest.approx(.65)
 assert m['limbs']['FL']['n_specimens']==3
 assert m['overrides']['touchdown_phases']['FR']==pytest.approx(.75)


def test_surface_motion_to_bird_pose_requires_scale():
 from yellowstone_python.wildlife_motion.birds import BirdEngine
 from yellowstone_python.wildlife_motion.species import get_profile
 a,s,j,w=bird_proxy(False)
 engine=BirdEngine(s,get_profile('mallard'))
 result=simulate(WaterConfig(wave_amplitude_m=0),.2,15)
 with pytest.raises(ValueError):bird_pose_from_water(engine,result,.1,0)
 pose=bird_pose_from_water(engine,result,.1,.5)
 assert np.isfinite(pose.positions).all()
 expected=np.array([np.interp(.1,result['times'],result['states'][:,i]) for i in range(3)])/.5
 np.testing.assert_allclose(pose.positions[s.index('pelvis')],expected,atol=1e-10)
 assert pose.diagnostics['meters_per_asset_unit']==.5
