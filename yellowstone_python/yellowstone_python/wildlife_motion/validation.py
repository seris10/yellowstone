"""Numerical motion and serialized skin checks."""
from __future__ import annotations
import numpy as np
from scipy.spatial.transform import Rotation,Slerp
from .core import fk,skin,Pose
from .gltf import read_glb,accessor,node_matrix


def validate_motion(asset,skeleton,joints,weights,engine,modes=None,samples=25):
    if samples<3:raise ValueError('At least three motion samples required')
    rest=skin(asset.vertices,skeleton,joints,weights,fk(skeleton))
    report={'schema':'wildlife-motion.validation/1','source_sha256':asset.source_sha256,
            'rest_skin_max_error':float(abs(rest-asset.vertices).max()),
            'weight_sum_max_error':float(abs(weights.sum(1)-1).max()),
            'joint_count':len(skeleton.names),'modes':{},
            'not_validated':['Species-specific biological motion','Force balance and energetics',
              'Self-collision and fur/feather contact','Playback inside a target game engine']}
    n=len(skeleton.names);rest_lengths=np.linalg.norm(skeleton.offsets[1:],axis=1)
    edges=np.vstack([asset.faces[:,[0,1]],asset.faces[:,[1,2]],asset.faces[:,[2,0]]])
    edges=np.unique(np.sort(edges,axis=1),axis=0)
    original_edges=np.linalg.norm(asset.vertices[edges[:,0]]-asset.vertices[edges[:,1]],axis=1)
    valid=original_edges>1e-8
    modes=modes or (engine.available_modes() if hasattr(engine,'available_modes') else list(engine.profile['gaits']))
    for mode in modes:
        p=engine.parameters(mode);period=1/p['frequency_hz']
        start=engine.pose(0,mode);end=engine.pose(period,mode)
        reach=[];lengtherr=[];skinmins=[];stretch=[];slip=[]
        for t in np.linspace(0,period,samples,endpoint=False):
            pose=engine.pose(t,mode)
            reach.append(pose.diagnostics.get('max_reach_error',0))
            lengths=np.linalg.norm(pose.positions[1:]-pose.positions[skeleton.parents[1:]],axis=1)
            lengtherr.append(float(abs(lengths-rest_lengths).max()))
            v=skin(asset.vertices,skeleton,joints,weights,pose);skinmins.append(float(v[:,1].min()))
            ratios=np.linalg.norm(v[edges[valid,0]]-v[edges[valid,1]],axis=1)/original_edges[valid]
            stretch.append(float(np.quantile(abs(ratios-1),.99)))
            if skeleton.metadata['engine']=='mammal' or mode=='Walk':
                dt=period*1e-5
                a=engine.pose(t,mode,root_motion=True);b=engine.pose(t+dt,mode,root_motion=True)
                for name,in_contact in a.diagnostics.get('contacts',{}).items():
                    if in_contact and b.diagnostics['contacts'].get(name):
                        j=skeleton.groups[name][-1]
                        slip.append(float(np.linalg.norm(b.positions[j]-a.positions[j])/dt))
        report['modes'][mode]={'max_ik_reach_error':float(max(reach)),
            'max_link_length_error':float(max(lengtherr)),
            'loop_position_error':float(abs(start.positions-end.positions).max()),
            'loop_rotation_matrix_error':float(abs(start.rotations-end.rotations).max()),
            'minimum_mesh_y':float(min(skinmins)),
            'worst_frame_p99_abs_edge_stretch':float(max(stretch)),
            'max_stance_joint_world_slip_per_s':float(max(slip)) if slip else None,
            'note':'Edge distortion is a skinning diagnostic, not a measured biomechanical strain.'}
    return report


def imported_skin(path,animation_name: str,time: float):
    """Evaluate serialized joint transforms and skin matrices."""
    doc,blob=read_glb(path);nodes=doc['nodes'];local=[node_matrix(n) for n in nodes]
    anim=next((a for a in doc.get('animations',[]) if a['name']==animation_name),None)
    if anim is None:raise ValueError('Animation not found')
    for channel in anim['channels']:
        sampler=anim['samplers'][channel['sampler']]
        if sampler.get('interpolation','LINEAR')!='LINEAR':raise ValueError('Round-trip checker supports LINEAR interpolation')
        ts=accessor(doc,blob,sampler['input']).ravel();values=accessor(doc,blob,sampler['output'])
        t=float(np.clip(time,ts[0],ts[-1]));i=int(np.clip(np.searchsorted(ts,t,side='right')-1,0,len(ts)-2))
        f=(t-ts[i])/(ts[i+1]-ts[i]);ni=channel['target']['node'];key=channel['target']['path']
        if key=='translation':local[ni][:3,3]=(1-f)*values[i]+f*values[i+1]
        elif key=='rotation':local[ni][:3,:3]=Slerp([0,1],Rotation.from_quat(values[i:i+2]))([f]).as_matrix()[0]
        else:raise ValueError('Unexpected exported animation path')
    parents={child:i for i,n in enumerate(nodes) for child in n.get('children',[])}
    world={}
    def transform(i):
        if i not in world:world[i]=transform(parents[i])@local[i] if i in parents else local[i]
        return world[i]
    mi=next(i for i,n in enumerate(nodes) if 'skin' in n);sk=doc['skins'][nodes[mi]['skin']]
    inv=accessor(doc,blob,sk['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
    matrices=np.array([transform(i)@ib for i,ib in zip(sk['joints'],inv)])
    result=[]
    for p in doc['meshes'][nodes[mi]['mesh']]['primitives']:
        a=p['attributes'];v=accessor(doc,blob,a['POSITION']);j=accessor(doc,blob,a['JOINTS_0'],False).astype(int);w=accessor(doc,blob,a['WEIGHTS_0'])
        vh=np.c_[v,np.ones(len(v))];out=np.zeros((len(v),4))
        for k in range(4):out+=w[:,k,None]*np.einsum('nij,nj->ni',matrices[j[:,k]],vh)
        result.append(out[:,:3])
    return np.vstack(result)
