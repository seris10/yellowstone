import numpy as np
import pytest
from scipy.spatial.transform import Rotation
from yellowstone_python.wildlife_motion.core import *
from yellowstone_python.wildlife_motion.mammals import foot_cycle,stride_speed

@pytest.mark.parametrize('a,b',[([1,0,0],[0,1,0]),([1,0,0],[-1,0,0]),([0,0,1],[0,0,1])])
def test_align(a,b):
 r=align_vectors(a,b);np.testing.assert_allclose(r@unit(a),unit(b),atol=1e-12);assert np.linalg.det(r)==pytest.approx(1)

@pytest.mark.parametrize('target',[[.3,-.8,0],[0,-3,0],[0,-.01,0]])
def test_ik_fixed_lengths(target):
 a=np.zeros(3);m,e,err=two_bone_ik(a,np.array(target),.7,.5,np.array([0,0,1.]))
 assert np.linalg.norm(m)==pytest.approx(.7,abs=1e-8);assert np.linalg.norm(e-m)==pytest.approx(.5,abs=1e-8)
 assert err>=0

def test_fk_and_local():
 s=Skeleton(['root','child'],np.array([-1,0]),np.array([[1,2,3],[1,3,3]]))
 r=np.array([axis_rotation('z',.3),axis_rotation('x',.2)]);po=fk(s,r);t,q=po.local(s)
 np.testing.assert_allclose(t,s.offsets,atol=1e-12);np.testing.assert_allclose(Rotation.from_quat(q).as_matrix(),r,atol=1e-12)

@pytest.mark.parametrize('parents',[[-1,-1],[-1,1],[-1,3]])
def test_invalid_skeleton(parents):
 with pytest.raises(ValueError):Skeleton(['a','b'],parents,[[0,0,0],[0,1,0]])

@pytest.mark.parametrize('duty',[.4,.6,.8])
def test_foot_contact(duty):
 f=1.2;S=.4
 for p in np.linspace(.01,duty-.01,5):
  z,y,contact=foot_cycle(p,duty,S,.1);dz=(foot_cycle(p+1e-7,duty,S,.1)[0]-z)/1e-7*f
  assert contact and y==0;assert dz+stride_speed(f,S,duty)==pytest.approx(0,abs=1e-8)
 for boundary in [0,duty]:
  a=np.array(foot_cycle(boundary-1e-7,duty,S,.1)[:2]);b=np.array(foot_cycle(boundary+1e-7,duty,S,.1)[:2])
  assert np.linalg.norm(a-b)<1e-5

def test_zero_weights_rejected_by_export():
 from yellowstone_python.wildlife_motion.synthetic import bird_proxy
 from yellowstone_python.wildlife_motion.gltf import export_asset
 a,s,j,w=bird_proxy();w[:]=0
 with pytest.raises(ValueError):export_asset(a,'unused.glb',s,j,w)
