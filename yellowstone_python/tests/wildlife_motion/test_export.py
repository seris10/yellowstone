import numpy as np
import pytest
from yellowstone_python.wildlife_motion.synthetic import bird_proxy
from yellowstone_python.wildlife_motion.gltf import *
from yellowstone_python.wildlife_motion.birds import BirdEngine
from yellowstone_python.wildlife_motion.species import get_profile
from yellowstone_python.wildlife_motion.core import skin,AssetError
from yellowstone_python.wildlife_motion.validation import imported_skin
from yellowstone_python.wildlife_motion.cli import main


def test_roundtrip_serialized_skin(tmp_path):
 a,s,j,w=bird_proxy(True);e=BirdEngine(s,get_profile('mallard'));clips=e.clips(['Flight'],fps=40,cycles=1)
 file=tmp_path/'bird.glb';export_asset(a,file,s,j,w,clips)
 # Exact key time: independent GLB matrices must match the generating engine.
 for time in clips[0].times[::2]:
  imported=imported_skin(file,'Flight',float(time));expected=skin(a.vertices,s,j,w,e.pose(float(time),'Flight'))
  np.testing.assert_allclose(imported,expected,atol=5e-7)
 doc,blob=read_glb(file);assert len(doc['skins'][0]['joints'])==len(s.names)
 with pytest.raises(AssetError):load_asset(file)


def test_unskinned_geometry_roundtrip(tmp_path):
 a,s,j,w=bird_proxy();file=tmp_path/'bird.glb';export_asset(a,file);b=load_asset(file)
 np.testing.assert_allclose(a.vertices,b.vertices,atol=1e-7);np.testing.assert_array_equal(a.faces,b.faces)
 np.testing.assert_allclose(a.colors,b.colors,atol=1e-7)


def test_bad_glb(tmp_path):
 p=tmp_path/'bad.glb';p.write_bytes(b'not a glb at all')
 with pytest.raises(AssetError):read_glb(p)


def test_cli_fixture_workflow(tmp_path):
 assert main(['fixtures','--outdir',str(tmp_path)])==0
 src=tmp_path/'synthetic_bird_folded_source.glb';out=tmp_path/'new.glb';rig=tmp_path/'synthetic_bird_folded.rig.json'
 assert main(['animate',str(src),'--species','mallard','--rig',str(rig),'--output',str(out),'--modes','Paddle','--cycles','1'])==0
 assert out.exists();assert main(['validate',str(out)])==0


def test_cli_never_overwrites_input(tmp_path):
 a,s,j,w=bird_proxy();file=tmp_path/'bird.glb';export_asset(a,file)
 with pytest.raises(SystemExit) as exc:main(['animate',str(file),'--species','mallard','-o',str(file)])
 assert exc.value.code==2
