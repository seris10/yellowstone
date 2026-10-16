from pathlib import Path
import hashlib
import json
import struct
import numpy as np
import pytest
from yellowstone_python.park_runtime.terrain_pack import build_pack, geometric_error, triangle_sample
from yellowstone_python.park_runtime.field_codec import encode, decode


def test_field_roundtrip_and_rejection():
    values=np.arange(24,dtype=np.float32).reshape(2,3,4)
    packet=encode(values,session_id="s",revision=2,t0_s=1,t1_s=2,
                  entity_ids=["a","b","c"],fields=["t","q","d","o"],units=["C","m3/s","m","mg/L"])
    header,restored=decode(packet)
    assert header["revision"]==2
    assert np.array_equal(values,restored)
    for broken in [b"",b"BAD!"+packet[4:],packet[:-1],b"YSP1"+struct.pack("<I",100000)+b"{}"]:
        with pytest.raises((ValueError,KeyError)): decode(broken)

@pytest.mark.parametrize("bad",[float("nan"),float("inf")])
def test_field_invalid_numbers(bad):
    with pytest.raises(ValueError):
        encode(np.full((2,1,1),bad),session_id="s",revision=0,t0_s=0,t1_s=1,
               entity_ids=["a"],fields=["x"],units=["m"])

def test_planar_error_zero():
    x,z=np.meshgrid(np.arange(65),np.arange(65))
    heights=x*2+z*3+9
    assert geometric_error(heights,heights[::4,::4])==0.

def test_triangle_sampler_matches_corners():
    grid=np.array([[0.,2.],[3.,8.]])
    assert triangle_sample(grid,np.array([0,1,0,1]),np.array([0,0,1,1])).tolist()==[0,2,3,8]

def test_paged_pack_shares_edges_and_validates_errors(tmp_path):
    x,z=np.meshgrid(np.arange(65),np.arange(65))
    heights=(np.sin(x/5)*8+np.cos(z/7)*4).astype("<f4")
    catalog=build_pack(heights,tmp_path,mesh_cells=16,root_cells=64,origin_x_m=0,origin_z_m=0)
    root=catalog["roots"][0]
    page=json.loads((tmp_path/root["page"]).read_text())
    assert len(page["children"])==4
    samples=[]
    for d in page["children"][:2]:
        child=json.loads((tmp_path/d["page"]).read_text())
        raw=(tmp_path/child["heights"]["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==child["heights"]["sha256"]
        samples.append(np.frombuffer(raw,dtype="<f4").reshape(17,17))
    assert np.array_equal(samples[0][:,-1],samples[1][:,0])
    coarse=heights[::4,::4]
    assert root["error_m"]==pytest.approx(geometric_error(heights,coarse))
    assert len(list(tmp_path.rglob("*.f32")))==21

def test_pack_nodata_not_silently_filled(tmp_path):
    heights=np.ones((17,17),dtype="<f4"); heights[8,8]=np.nan
    with pytest.raises(ValueError): build_pack(heights,tmp_path,mesh_cells=4,root_cells=16)
    assert not (tmp_path/"catalog.json").exists()

def test_append_disjoint_pack(tmp_path):
    values=np.zeros((17,17),dtype="<f4")
    build_pack(values,tmp_path,pack_id="first",mesh_cells=4,root_cells=16,origin_x_m=0,origin_z_m=0)
    catalog=build_pack(values,tmp_path,pack_id="next",mesh_cells=4,root_cells=16,origin_x_m=64,origin_z_m=0,append=True)
    assert len(catalog["roots"])==2
    with pytest.raises(ValueError):
        build_pack(values,tmp_path,pack_id="overlap",mesh_cells=4,root_cells=16,origin_x_m=32,origin_z_m=0,append=True)


def test_overlay_preloads_exist():
    import re
    root=Path(__file__).resolve().parents[1]/"overlay"/"yellowstone_midway"
    for path in (root/"scripts"/"park_runtime").glob("*.gd"):
        for reference in re.findall(r'(?:preload|load)\("res://([^"\n]+)"\)',path.read_text()):
            assert (root/reference).exists(),(path,reference)
