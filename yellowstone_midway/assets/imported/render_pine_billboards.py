#!/usr/bin/env python3
"""Render CC0 source-derived distant tree impostors. Run offline.
Requires trimesh, pyrender, Pillow, numpy; EGL.
"""
import os
os.environ.setdefault('PYOPENGL_PLATFORM', 'egl')
from pathlib import Path
import json
import numpy as np
from PIL import Image
import trimesh
import pyrender
BASE = Path(__file__).resolve().parent / 'pine_tree_01'

def camera_pose(eye, target):
    back = np.asarray(eye,dtype=float) - target
    back /= np.linalg.norm(back)
    right = np.cross([0,1,0], back); right /= np.linalg.norm(right)
    up = np.cross(back, right)
    out = np.eye(4); out[:3,:3] = np.column_stack([right,up,back]); out[:3,3] = eye
    return out

src=trimesh.load(BASE/'pine_b_compact.gltf',force='scene')
scene=pyrender.Scene.from_trimesh_scene(src,bg_color=[0,0,0,0],ambient_light=[0.62,0.62,0.62])
camera=pyrender.OrthographicCamera(xmag=16/3,ymag=8,znear=0.1,zfar=60)
pose=camera_pose([0,7.7,25],[0,7.7,0])
cam=scene.add(camera,pose=pose)
# Moderate broad front illumination preserves readable bark.
light=pyrender.DirectionalLight(color=np.ones(3),intensity=1.1)
ln=scene.add(light,pose=camera_pose([8,16,14],[0,7,0]))
r=pyrender.OffscreenRenderer(512,768)
files=[]
for i in range(4):
    angle=i*np.pi/2
    eye=np.array([np.sin(angle)*25,7.7,np.cos(angle)*25])
    scene.set_pose(cam,camera_pose(eye,[0,7.7,0]))
    scene.set_pose(ln,camera_pose(eye+[6,8,0],[0,7,0]))
    color,_=r.render(scene,flags=pyrender.RenderFlags.RGBA)
    p=BASE/('pine_billboard_%d.png'%i)
    Image.fromarray(color).save(p)
    files.append(p.name)
r.delete()
metadata={'source':'https://polyhaven.com/a/pine_tree_01','source_authors':['Rico Cilliers','Rob Tuytel'],
 'license':'CC0-1.0','source_mesh':'pine_b_compact.gltf','files':files,
 'pixel_width':512,'pixel_height':768,'world_width_m':32/3,'world_height_m':16,
 'world_bottom_y_m':-0.3,'camera_target_y_m':7.7,
 'azimuth_degrees':[0,90,180,270],
 'notes':['Offline technical renders of a source-derived mesh; original source species unspecified.',
          'Baked diffuse lighting; reserve for distant foliage. Cutout alpha, no collision.',
          'Rendered with pyrender, which may not implement every glTF texture-transform extension.']}
(BASE/'billboard_metadata.json').write_text(json.dumps(metadata,indent=2))
print(json.dumps(metadata,indent=2))
