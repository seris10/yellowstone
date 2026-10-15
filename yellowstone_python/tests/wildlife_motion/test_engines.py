import numpy as np
import pytest
from yellowstone_python.wildlife_motion.synthetic import bird_proxy,mammal_proxy
from yellowstone_python.wildlife_motion.rigging import prepare,make_weights,axis_basis
from yellowstone_python.wildlife_motion.species import get_profile
from yellowstone_python.wildlife_motion.mammals import MammalEngine,register_sole_offsets
from yellowstone_python.wildlife_motion.birds import BirdEngine,paddle_cycle
from yellowstone_python.wildlife_motion.core import fk,skin,AssetError

@pytest.mark.parametrize('species',['grizzly','black_bear','bobcat','canada_lynx','american_badger','american_bison','gray_wolf'])
def test_all_mammal_profiles_execute(species):
 p=get_profile(species);a,s=prepare(mammal_proxy(),p);j,w,r=make_weights(a.vertices,a.faces,s)
 register_sole_offsets(a.vertices,j,w,s);e=MammalEngine(s,p)
 np.testing.assert_allclose(skin(a.vertices,s,j,w,fk(s)),a.vertices,atol=3e-7)
 for mode in p['gaits']:
  period=1/e.parameters(mode)['frequency_hz'];first=e.pose(0,mode);last=e.pose(period,mode)
  np.testing.assert_allclose(first.positions,last.positions,atol=1e-8)
  assert np.isfinite(e.pose(period*.23,mode).positions).all()

def test_seam_weights_identical():
 a,s,j,w=bird_proxy();p=get_profile('mallard')
 # Make repeated vertices on a synthetic surface, matching the seam scenario.
 v=np.vstack([a.vertices,a.vertices[:15]]);j,w,r=make_weights(v,a.faces,s)
 np.testing.assert_allclose(w[-15:],w[:15]);np.testing.assert_array_equal(j[-15:],j[:15])

@pytest.mark.parametrize('species',['mallard','trumpeter_swan','sandhill_crane','common_raven','bald_eagle','american_dipper'])
def test_all_bird_profiles_execute(species):
 a,s,j,w=bird_proxy(True);e=BirdEngine(s,get_profile(species))
 for mode in e.available_modes():
  period=1/e.parameters(mode)['frequency_hz'];first=e.pose(0,mode);last=e.pose(period,mode)
  np.testing.assert_allclose(first.positions,last.positions,atol=1e-8)
  assert np.isfinite(e.pose(.213,mode).positions).all()

def test_folded_wings_cannot_fly():
 a,s,j,w=bird_proxy(False);e=BirdEngine(s,get_profile('mallard'))
 assert 'Flight' not in e.available_modes()
 with pytest.raises(AssetError):e.pose(0,'Flight')

def test_unreviewed_wings_cannot_fly():
 a,s,j,w=bird_proxy(True);s.metadata['review_status']='estimated_unreviewed'
 with pytest.raises(AssetError):BirdEngine(s,get_profile('mallard')).pose(0,'Flight')

def test_paddle_analytic_velocity():
 for t in [.11,.39,.47]:
  pos,vel,area=paddle_cycle(t,1.6,.6,.09,.02)
  eps=1e-7;numerical=(paddle_cycle(t+eps,1.6,.6,.09,.02)[0]-paddle_cycle(t-eps,1.6,.6,.09,.02)[0])/(2*eps)
  np.testing.assert_allclose(vel,numerical,atol=1e-7);assert .13-1e-10<=area<=1

def test_axis_mapping():
 m=axis_basis('-x','+z');np.testing.assert_allclose(m@[-1,0,0],[0,0,1]);assert np.linalg.det(m)==pytest.approx(1)
 with pytest.raises(ValueError):axis_basis('+z','-z')

def test_rig_wrong_source():
 a,s=prepare(mammal_proxy(),get_profile('grizzly'));d=s.to_dict();d['metadata']['source_sha256']='not-the-source'
 with pytest.raises(AssetError):prepare(mammal_proxy(),get_profile('grizzly'),d)


def test_mammal_rejects_incomplete_measured_phases():
 from yellowstone_python.wildlife_motion.mammals import MammalEngine
 from yellowstone_python.wildlife_motion.species import get_profile
 # Parameter validation does not depend on a fitted skeleton.
 engine=MammalEngine(None,get_profile('bobcat'))
 with pytest.raises(ValueError):engine.parameters('Walk',{'touchdown_phases':{'FL':.2}})
 with pytest.raises(ValueError):engine.parameters('Walk',{'frequency_hz':float('nan')})
 with pytest.raises(ValueError):engine.parameters('Walk',{'clearance_height':-1})
