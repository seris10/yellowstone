"""Surface landmarks and skeletal weights."""
from __future__ import annotations
import copy
import numpy as np
from scipy.cluster.vq import kmeans2
from scipy.spatial.transform import Rotation
from scipy.sparse import coo_matrix,diags
from .core import Skeleton,AssetError,smoothstep,unit
from .gltf import MeshAsset


def axis_basis(forward: str='+z',up: str='+y') -> np.ndarray:
    def vec(name):
        if name not in ['+x','-x','+y','-y','+z','-z']:
            raise ValueError('Axes must be signed strings such as +z or -x')
        v=np.zeros(3);v['xyz'.index(name[1])]=1 if name[0]=='+' else -1
        return v
    f,u=vec(forward),vec(up)
    if abs(f@u)>.1:raise ValueError('Up and forward axes must be perpendicular')
    return np.stack([np.cross(u,f),u,f])


def foot_clusters(v: np.ndarray,count: int) -> np.ndarray:
    lo,hi=v.min(0),v.max(0);h=hi[1]-lo[1]
    low=v[v[:,1]<lo[1]+.09*h]
    if len(low)<count*8:raise AssetError('Too few ground-level vertices to estimate feet; supply reviewed landmarks')
    candidates=low[:,[0,2]]
    best=None
    for seed in (2,7,19):
        centers,labels=kmeans2(candidates,count,minit='++',seed=seed,iter=60)
        score=np.sum((candidates-centers[labels])**2)
        if best is None or score<best[0]:best=(score,centers,labels)
    _,centers,labels=best
    if len(set(labels))!=count:raise AssetError('Could not distinguish feet; use manual landmarks')
    out=[]
    for i,c in enumerate(centers):
        q=low[labels==i]
        out.append([c[0],float(np.quantile(q[:,1],.02)+.035*h),c[1]])
    return np.asarray(out)


def canonicalize(asset: MeshAsset,profile: dict,forward: str='+z',up: str='+y',
                 align_heading: bool=True,length_m: float | None=None) -> tuple[MeshAsset,np.ndarray]:
    m=np.eye(4);m[:3,:3]=axis_basis(forward,up)
    oriented=asset.transformed(m)
    feet=foot_clusters(oriented.vertices,4 if profile['engine']=='mammal' else 2)
    h=oriented.vertices[:,1].ptp() if hasattr(oriented.vertices[:,1],'ptp') else np.ptp(oriented.vertices[:,1])
    if profile['engine']=='mammal' and align_heading:
        order=np.argsort(feet[:,2]);rear=feet[order[:2]].mean(0);front=feet[order[2:]].mean(0)
        d=front-rear
        yaw=np.arctan2(d[0],d[2])
        if abs(yaw)>np.deg2rad(65):raise AssetError('Ambiguous heading; set the correct --forward axis or disable heading alignment')
        r=np.eye(4);r[:3,:3]=Rotation.from_euler('y',-yaw).as_matrix();m=r@m
    tmp=asset.transformed(m)
    feet=foot_clusters(tmp.vertices,4 if profile['engine']=='mammal' else 2)
    origin=np.array([feet[:,0].mean(),tmp.vertices[:,1].min(),feet[:,2].mean()])
    m[:3,3]=-origin
    scale=1.
    if length_m is not None:
        if not np.isfinite(length_m) or length_m<=0:raise ValueError('Documented physical length must be positive')
        scale=length_m/np.ptp(tmp.vertices[:,2]);m[:3,:]*=scale
    final=asset.transformed(m)
    final.metadata.update({'canonical_transform':m.tolist(),'forward_input':forward,'up_input':up,
       'heading_estimation':'paw-cluster midpoint' if align_heading and profile['engine']=='mammal' else 'explicit input axes',
       'scale_status':'user_supplied_bbox_length_m' if length_m else 'unverified_asset_units',
       'supplied_bbox_length_m':length_m,'canonical_scale_factor':scale})
    return final,foot_clusters(final.vertices,4 if profile['engine']=='mammal' else 2)


def _build(names,positions,parents,groups,metadata) -> Skeleton:
    return Skeleton(names,np.array(parents),np.array(positions),groups,metadata)


def estimate_mammal(asset: MeshAsset,feet: np.ndarray,profile: dict) -> Skeleton:
    v=asset.vertices;h=float(np.ptp(v[:,1]));length=float(np.ptp(v[:,2]));ground=float(v[:,1].min())
    order=np.argsort(feet[:,2]);rear=feet[order[:2]];front=feet[order[2:]]
    # L is +X in the canonical frame; staggered rest feet are not forced symmetric.
    front=front[np.argsort(-front[:,0])];rear=rear[np.argsort(-rear[:,0])]
    fz=float(front[:,2].mean());hz=float(rear[:,2].mean())
    chestz=fz-.075*length;hipz=hz+.07*length
    pelvis=np.array([0.,.64*h,hipz]);thorax=np.array([0.,.65*h,chestz])
    lumbar=.58*pelvis+.42*thorax
    neck=np.array([0.,.73*h,chestz+.10*length])
    headpts=v[(v[:,2]>chestz+.10*length)&(v[:,1]>.64*h)]
    head=np.median(headpts,axis=0) if len(headpts) else neck+np.array([0,.07*h,.10*length])
    names=['root','pelvis','lumbar','thorax','neck','head']
    pos=[np.zeros(3),pelvis,lumbar,thorax,neck,head];parents=[-1,0,1,2,3,4]
    groups={'body':[1,2,3,4,5]}
    plant=profile['foot_posture']=='plantigrade'
    width=.20*h if profile['family'] in ('ursid','mustelid') else .16*h
    for key,foot,is_front,sign in [('FL',front[0],True,1),('FR',front[1],True,-1),
                                    ('HL',rear[0],False,1),('HR',rear[1],False,-1)]:
        upper=np.array([sign*width,(.56 if is_front else .61)*h,chestz if is_front else hipz])
        if is_front:
            middle=np.array([.5*(upper[0]+foot[0]),.31*h,upper[2]-.055*length])
            ankle=np.array([foot[0],(.13 if plant else .12)*h,foot[2]-.040*length])
        else:
            middle=np.array([.55*upper[0]+.45*foot[0],.39*h,.60*upper[2]+.40*foot[2]+.07*length])
            ankle=np.array([foot[0],(.15 if plant else .25)*h,foot[2]-.055*length])
        idx=[];last=3 if is_front else 1
        for part,point in zip(['upper','middle','ankle','foot'],[upper,middle,ankle,foot]):
            idx.append(len(names));names.append(key+'_'+part);pos.append(point);parents.append(last);last=len(names)-1
        groups[key]=idx
    if profile['family'] in ('felid','canid','mustelid'):
        tailbase=np.array([0.,.72*h,hipz-.09*length])
        tailpts=v[(v[:,2]<hipz-.11*length)&(v[:,1]>.53*h)]
        if len(tailpts)>10:
            tip=tailpts[np.argmin(tailpts[:,2])]
            if np.linalg.norm(tip-tailbase)>.03*length:
                ids=[];last=1
                for k,point in enumerate([tailbase,.5*(tailbase+tip),tip]):
                    ids.append(len(names));names.append('tail_'+str(k));pos.append(point);parents.append(last);last=len(names)-1
                groups['tail']=ids
    metadata={'species':profile['id'],'engine':'mammal','review_status':'estimated_unreviewed',
       'source_sha256':asset.source_sha256,'canonical_transform':asset.metadata['canonical_transform'],
       'scale_status':asset.metadata['scale_status'],'parameter_status':profile['parameter_status'],
       'height':h,'length':length,'foot_posture':profile['foot_posture'],
       'warnings':['Joint centers inferred from surface geometry, not measured skeletons.',
                   'Posed AI meshes may require joint and weight correction, particularly shoulders, hips, and feet.']}
    return _build(names,pos,parents,groups,metadata)


def estimate_bird(asset: MeshAsset,feet: np.ndarray,profile: dict,wing_state: str='unknown') -> Skeleton:
    v=asset.vertices;h=float(np.ptp(v[:,1]));length=float(np.ptp(v[:,2]));width=float(np.ptp(v[:,0]))
    feet=feet[np.argsort(-feet[:,0])]
    longneck=profile['family'] in ('wader','longneck_waterfowl')
    bodyheight=(.48 if longneck else .62)*h
    names=['root','pelvis','thorax','neck_0','neck_1','head']
    pos=[np.zeros(3),np.array([0,bodyheight,-.10*length]),np.array([0,bodyheight,.08*length]),
         np.array([0,bodyheight+.06*h,.19*length]),np.array([0,.81*h,.28*length]),
         np.array([0,.91*h,.33*length])]
    parents=[-1,0,1,2,3,4];groups={'body':[1,2,3,4,5],'neck':[3,4,5]}
    for side,sign,foot in [('L',1,feet[0]),('R',-1,feet[1])]:
        points=[np.array([sign*.09*width,bodyheight,-.04*length]),
                np.array([sign*.12*width,.42*h,.07*length]),
                np.array([foot[0],.20*h,foot[2]-.09*length]),foot]
        ids=[];last=1
        for part,point in zip(['upper','middle','ankle','foot'],points):
            ids.append(len(names));names.append(side+'_'+part);pos.append(point);parents.append(last);last=len(names)-1
        groups[side]=ids
    for side,sign in [('L',1),('R',-1)]:
        if wing_state=='spread':
            points=[np.array([sign*.10*width,bodyheight+.07*h,.07*length]),
                    np.array([sign*.23*width,bodyheight+.05*h,.03*length]),
                    np.array([sign*.35*width,bodyheight+.05*h,-.05*length]),
                    np.array([sign*.49*width,bodyheight+.04*h,-.16*length])]
        else:
            points=[np.array([sign*.24*width,bodyheight+.10*h,.07*length]),
                    np.array([sign*.34*width,bodyheight+.08*h,-.04*length]),
                    np.array([sign*.37*width,bodyheight+.04*h,-.17*length]),
                    np.array([sign*.32*width,bodyheight,-.29*length])]
        ids=[];last=2
        for part,point in zip(['shoulder','elbow','wrist','tip'],points):
            ids.append(len(names));names.append('wing_'+side+'_'+part);pos.append(point);parents.append(last);last=len(names)-1
        groups['wing_'+side]=ids
    ids=[];last=1
    for k,p in enumerate([[0,bodyheight,-.30*length],[0,bodyheight+.02*h,-.44*length]]):
        ids.append(len(names));names.append('tail_'+str(k));pos.append(np.array(p));parents.append(last);last=len(names)-1
    groups['tail']=ids
    return _build(names,pos,parents,groups,{'species':profile['id'],'engine':'bird','review_status':'estimated_unreviewed',
      'wing_state':wing_state,'source_sha256':asset.source_sha256,'canonical_transform':asset.metadata['canonical_transform'],
      'scale_status':asset.metadata['scale_status'],'height':h,'length':length,'float_waterline':.43*h,
      'parameter_status':profile['parameter_status'],
      'warnings':['Bird templates require landmark review. Hidden wings cannot be unfolded from absent geometry.',
                  'Knee is proximal; visible backward-bending joint is the intertarsal/hock region.']})


def prepare(asset: MeshAsset,profile: dict,rig_document: dict | None=None,**kwargs) -> tuple[MeshAsset,Skeleton]:
    if rig_document is not None:
        skel=Skeleton.from_dict(rig_document)
        if skel.metadata.get('source_sha256')!=asset.source_sha256:
            raise AssetError('Rig was prepared for a different source mesh (SHA256 mismatch)')
        if skel.metadata.get('species')!=profile['id']:
            raise AssetError('Rig species differs from requested species; no cross-species conversion is performed')
        matrix=np.asarray(skel.metadata.get('canonical_transform'),float)
        if matrix.shape!=(4,4):raise AssetError('Rig is missing its canonical coordinate transform')
        final=asset.transformed(matrix)
        final.metadata.update({'canonical_transform':matrix.tolist(),'scale_status':skel.metadata.get('scale_status','unverified_asset_units')})
        return final,skel
    wing_state=kwargs.pop('wing_state','unknown')
    final,feet=canonicalize(asset,profile,**kwargs)
    skel=estimate_mammal(final,feet,profile) if profile['engine']=='mammal' else estimate_bird(final,feet,profile,wing_state)
    return final,skel


def _segment_distances(v: np.ndarray,points: np.ndarray):
    a,b=points[:-1],points[1:];ab=b-a
    t=np.clip(np.einsum('nsi,si->ns',v[:,None,:]-a,ab)/np.maximum(np.sum(ab*ab,axis=1),1e-12),0,1)
    delta=v[:,None,:]-(a[None,:,:]+t[:,:,None]*ab)
    d=np.linalg.norm(delta,axis=2)
    which=np.argmin(d,axis=1);row=np.arange(len(v))
    return d[row,which],which,t[row,which]


def make_weights(vertices: np.ndarray,faces: np.ndarray,skel: Skeleton,
                 smooth_iterations: int=10) -> tuple[np.ndarray,np.ndarray,dict]:
    """Compute capsule weights with spatial seam welding."""
    v=np.asarray(vertices);n=len(v);nj=len(skel.names);h=skel.metadata['height']
    if (v.ndim!=2 or v.shape[1]!=3 or n<3 or not np.isfinite(v).all()
            or not np.isfinite(h) or h<=0 or np.max(np.ptp(v,axis=0))<=0
            or not isinstance(smooth_iterations,int) or smooth_iterations<0):
        raise ValueError('Weight inputs require finite surface geometry and positive height')
    names=['body']+[k for k in skel.groups if k not in ('body','neck')]
    distances=[];data=[]
    for name in names:
        chain=skel.groups[name]
        d,seg,t=_segment_distances(v,skel.rest[chain]);distances.append(d);data.append((chain,seg,t))
    ds=np.column_stack(distances)
    legkeys=['FL','FR','HL','HR'] if skel.metadata['engine']=='mammal' else ['L','R']
    for col,name in enumerate(names):
        if name in legkeys:
            root=skel.rest[skel.groups[name][0]]
            ds[:,col]+=np.maximum(v[:,1]-root[1],0.)*4
        elif name.startswith('wing'):
            if skel.metadata.get('wing_state')=='spread':
                root=skel.rest[skel.groups[name][0]]
                ds[:,col]+=np.maximum(abs(root[0])*.8-abs(v[:,0]),0)*5
            else:
                ds[:,col]+=.10*h  # No loose wing flapping from a fused folded-wing shell.
    low=v[:,1]<.24*h
    for col,name in enumerate(names):
        if name not in legkeys:ds[low,col]+=5*h
    winner=ds.argmin(axis=1)
    # Smooth competing capsule memberships across the surface.
    relative=ds-ds.min(axis=1,keepdims=True)
    membership=np.exp(-np.square(relative/(.105*h)))
    membership/=membership.sum(axis=1,keepdims=True)
    dense=np.zeros((n,nj),float)
    rows=np.arange(n)
    for col,(chain,seg,t) in enumerate(data):
        blend=smoothstep((t-.60)/.40)
        if names[col]=='body':blend=smoothstep(t)
        j0=np.asarray(chain)[seg];j1=np.asarray(chain)[seg+1]
        amount=membership[:,col]
        if names[col] in legkeys:
            # Share proximal soft tissue between trunk and limb.
            root=skel.rest[chain[0]]
            trunk_fraction=smoothstep((v[:,1]-(root[1]-.20*h))/(.24*h))
            par=skel.parents[chain[0]]
            dense[:,par]+=amount*trunk_fraction
            amount=amount*(1-trunk_fraction)
        dense[rows,j0]+=amount*(1-blend)
        dense[rows,j1]+=amount*blend
    # UV seam vertices must have identical weights to avoid animated cracks.
    tol=max(np.ptp(v,axis=0))*1e-7
    _,first,inverse=np.unique(np.round(v/tol).astype(np.int64),axis=0,return_index=True,return_inverse=True)
    unique=v[first];nu=len(unique)
    wd=np.zeros((nu,nj));counts=np.bincount(inverse,minlength=nu)
    np.add.at(wd,inverse,dense);wd/=counts[:,None]
    f=inverse[faces];edges=np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]])
    edges=np.sort(edges,axis=1);edges=np.unique(edges[edges[:,0]!=edges[:,1]],axis=0)
    dist=np.linalg.norm(unique[edges[:,0]]-unique[edges[:,1]],axis=1)
    ew=1/np.maximum(dist,.004*h)
    a=coo_matrix((np.r_[ew,ew],(np.r_[edges[:,0],edges[:,1]],np.r_[edges[:,1],edges[:,0]])),shape=(nu,nu)).tocsr()
    sums=np.asarray(a.sum(axis=1)).ravel();a=diags(1/np.maximum(sums,1e-12))@a
    # Pin the soles; smoothing must not let a neighbor pull a planted paw upward.
    pinned=unique[:,1]<.065*h
    for key in legkeys:
        foot=skel.groups[key][-1];pos=skel.rest[foot]
        mask=pinned & (np.linalg.norm(unique[:,[0,2]]-pos[[0,2]],axis=1)<.16*h)
        wd[mask]=0;wd[mask,foot]=1
    base=wd.copy()
    for _ in range(smooth_iterations):
        smoothed=a@wd
        wd=.35*base+.65*smoothed
        wd[pinned]=base[pinned]
    wd=np.maximum(wd,0)
    idx=np.argsort(wd,axis=1)[:,-4:][:,::-1]
    vals=np.take_along_axis(wd,idx,axis=1)
    vals/=np.maximum(vals.sum(axis=1,keepdims=True),1e-15)
    idx[vals<1e-10]=0;vals[vals<1e-10]=0;vals/=vals.sum(axis=1,keepdims=True)
    joints=idx[inverse].astype(np.uint16);weights=vals[inverse].astype(np.float32)
    report={'method':'region-gated capsule priors + UV-welded graph smoothing',
      'anatomical_validation':'not established','unique_spatial_vertices':nu,'original_vertices':n,
      'chain_vertex_counts':{name:int(np.sum(winner==i)) for i,name in enumerate(names)},
      'max_weight_sum_error':float(abs(weights.sum(axis=1)-1).max()),
      'smoothed_iterations':smooth_iterations,'seam_weld_tolerance':tol}
    return joints,weights,report
