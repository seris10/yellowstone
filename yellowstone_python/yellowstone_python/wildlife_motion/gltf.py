"""Embedded glTF geometry and animation serialization."""
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from io import BytesIO
import copy
import hashlib
import json
import struct
import numpy as np
from PIL import Image
from scipy.spatial.transform import Rotation
from .core import AssetError, Skeleton, Clip, vertex_normals

DTYPES = {5120:'i1',5121:'u1',5122:'<i2',5123:'<u2',5125:'<u4',5126:'<f4'}
SIZES = {'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}


def read_glb(path: str | Path) -> tuple[dict, bytes]:
    data = Path(path).read_bytes()
    if len(data)<20:
        raise AssetError('Truncated GLB')
    magic,version,length = struct.unpack_from('<III',data)
    if magic!=0x46546C67 or version!=2 or length!=len(data):
        raise AssetError('Expected a valid GLB 2.0 file')
    offset,doc,blob = 12,None,None
    while offset<len(data):
        if offset+8>len(data): raise AssetError('Truncated chunk header')
        size,kind=struct.unpack_from('<II',data,offset);offset+=8
        if size%4 or offset+size>len(data): raise AssetError('Invalid GLB chunk length')
        chunk=data[offset:offset+size];offset+=size
        if kind==0x4E4F534A:
            if doc is not None: raise AssetError('Duplicate JSON chunk')
            doc=json.loads(chunk.decode('utf8').rstrip(' \0'))
        elif kind==0x004E4942:
            if blob is not None: raise AssetError('Duplicate BIN chunk')
            blob=chunk
    if doc is None or blob is None: raise AssetError('A JSON and embedded BIN chunk are required')
    if doc.get('asset',{}).get('version')!='2.0': raise AssetError('Unsupported glTF version')
    buffers=doc.get('buffers',[])
    if len(buffers)!=1 or 'uri' in buffers[0]:
        raise AssetError('Only one embedded GLB buffer is supported; pack external resources first')
    if buffers[0]['byteLength']>len(blob): raise AssetError('Buffer exceeds BIN chunk')
    return doc,blob


def write_glb(path: str | Path, doc: dict, blob: bytes | bytearray) -> None:
    doc=copy.deepcopy(doc)
    doc['buffers']=[{'byteLength':len(blob)}]
    j=json.dumps(doc,separators=(',',':'),allow_nan=False).encode('utf8')
    j+=b' '*((-len(j))%4)
    b=bytes(blob)+b'\0'*((-len(blob))%4)
    total=12+8+len(j)+8+len(b)
    if total>=2**32: raise AssetError('GLB exceeds 4 GiB container limit')
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('wb') as f:
        f.write(struct.pack('<III',0x46546C67,2,total))
        f.write(struct.pack('<II',len(j),0x4E4F534A));f.write(j)
        f.write(struct.pack('<II',len(b),0x004E4942));f.write(b)


def accessor(doc: dict, blob: bytes, index: int, normalize: bool = True) -> np.ndarray:
    if not isinstance(index,int) or not 0<=index<len(doc.get('accessors',[])):
        raise AssetError('Accessor index out of range')
    a=doc['accessors'][index]
    if 'sparse' in a or 'bufferView' not in a:
        raise AssetError('Sparse or implicit accessors need an external decompression/conversion step')
    if a['type'] not in SIZES or a['componentType'] not in DTYPES:
        raise AssetError('Unsupported accessor component/type')
    if not isinstance(a['bufferView'],int) or not 0<=a['bufferView']<len(doc.get('bufferViews',[])):
        raise AssetError('Buffer view index out of range')
    v=doc['bufferViews'][a['bufferView']]
    if v.get('buffer',0)!=0: raise AssetError('External buffers are unsupported')
    dtype=np.dtype(DTYPES[a['componentType']]);cols=SIZES[a['type']]
    count=int(a['count']);step=int(v.get('byteStride',cols*dtype.itemsize))
    view_start=int(v.get('byteOffset',0));local_start=int(a.get('byteOffset',0))
    start=view_start+local_start
    end=start+max(0,count-1)*step+cols*dtype.itemsize
    if (count<=0 or view_start<0 or local_start<0 or v['byteLength']<=0
            or step<cols*dtype.itemsize or step % dtype.itemsize
            or start % dtype.itemsize or end>len(blob)
            or end>view_start+v['byteLength']):
        raise AssetError('Accessor exceeds its buffer view')
    out=np.ndarray((count,cols),dtype=dtype,buffer=blob,offset=start,
                   strides=(step,dtype.itemsize)).copy()
    if normalize and a.get('normalized'):
        if dtype.kind not in ('i','u'):
            raise AssetError('Normalized accessors require integer components')
        info=np.iinfo(dtype);out=out.astype(float)/info.max
        if info.min<0: out=np.maximum(out,-1.)
    return out


class Appender:
    def __init__(self,doc: dict,blob: bytes=b''):
        self.doc=doc;self.blob=bytearray(blob)
        doc.setdefault('accessors',[]);doc.setdefault('bufferViews',[])

    def add(self,array: np.ndarray,kind: str='VEC3',ctype: int=5126,
            target: int | None=None, bounds: bool=False) -> int:
        array=np.asarray(array,dtype=np.dtype(DTYPES[ctype])).reshape(-1,SIZES[kind])
        if not len(array): raise ValueError('Cannot write an empty accessor')
        while len(self.blob)%4:self.blob.append(0)
        view={'buffer':0,'byteOffset':len(self.blob),'byteLength':array.nbytes}
        if target is not None:view['target']=target
        self.blob.extend(np.ascontiguousarray(array).tobytes())
        vi=len(self.doc['bufferViews']);self.doc['bufferViews'].append(view)
        ac={'bufferView':vi,'componentType':ctype,'count':len(array),'type':kind}
        if bounds:
            ac['min']=array.min(0).tolist();ac['max']=array.max(0).tolist()
        ai=len(self.doc['accessors']);self.doc['accessors'].append(ac)
        return ai


def node_matrix(node: dict) -> np.ndarray:
    if 'matrix' in node:return np.asarray(node['matrix'],float).reshape(4,4).T
    m=np.eye(4)
    m[:3,:3]=Rotation.from_quat(node.get('rotation',[0,0,0,1])).as_matrix() @ np.diag(node.get('scale',[1,1,1]))
    m[:3,3]=node.get('translation',[0,0,0])
    return m


@dataclass
class MeshAsset:
    doc: dict
    blob: bytes
    vertices: np.ndarray
    normals: np.ndarray
    faces: np.ndarray
    primitive_slices: list[tuple[int,int]]
    primitive_face_slices: list[tuple[int,int]]
    uvs: np.ndarray | None
    source_sha256: str
    metadata: dict = field(default_factory=dict)
    colors: np.ndarray | None = None
    tangents: np.ndarray | None = None

    def transformed(self, matrix: np.ndarray) -> 'MeshAsset':
        out=copy.copy(self)
        tangent_repairs=0
        out.vertices=self.vertices@matrix[:3,:3].T+matrix[:3,3]
        out.normals=self.normals@np.linalg.inv(matrix[:3,:3])
        out.normals/=np.maximum(np.linalg.norm(out.normals,axis=1,keepdims=True),1e-12)
        if self.tangents is not None:
            out.tangents=self.tangents.copy()
            direction=self.tangents[:,:3]@matrix[:3,:3].T
            direction-=out.normals*np.sum(direction*out.normals,axis=1,keepdims=True)
            lengths=np.linalg.norm(direction,axis=1)
            invalid=lengths<1e-10
            tangent_repairs=int(np.count_nonzero(invalid))
            if tangent_repairs:
                axes=np.eye(3)[np.argmin(np.abs(out.normals[invalid]),axis=1)]
                direction[invalid]=np.cross(out.normals[invalid],axes)
            direction/=np.maximum(np.linalg.norm(direction,axis=1,keepdims=True),1e-12)
            out.tangents[:,:3]=direction
            if np.linalg.det(matrix[:3,:3])<0:out.tangents[:,3]*=-1
        if np.linalg.det(matrix[:3,:3])<0:out.faces=self.faces[:,[0,2,1]].copy()
        out.metadata=copy.deepcopy(self.metadata)
        if tangent_repairs:
            previous=out.metadata.get('tangent_frame_repair',{}).get('count',0)
            out.metadata['tangent_frame_repair']={'count':previous+tangent_repairs,
                'method':'orthogonal_frame_for_degenerate_UV_tangent','evidence_class':'derived'}
        return out

    def texture(self,primitive: int=0,limit: int=2048) -> Image.Image | None:
        p=self.doc['meshes'][self.metadata['mesh_index']]['primitives'][primitive]
        mat=self.doc.get('materials',[])[p['material']] if 'material' in p else {}
        tex=mat.get('pbrMetallicRoughness',{}).get('baseColorTexture')
        if not tex:return None
        im=self.doc['images'][self.doc['textures'][tex['index']]['source']]
        if 'bufferView' not in im:raise AssetError('External texture URI unsupported')
        v=self.doc['bufferViews'][im['bufferView']];start=v.get('byteOffset',0)
        image=Image.open(BytesIO(self.blob[start:start+v['byteLength']]))
        image.thumbnail((limit,limit),Image.Resampling.LANCZOS)
        return image.convert('RGBA')


def load_asset(path: str | Path, allow_skinned: bool=False) -> MeshAsset:
    doc,blob=read_glb(path)
    if doc.get('extensionsRequired'):
        raise AssetError('Decode required extensions first: '+', '.join(doc['extensionsRequired']))
    if (doc.get('skins') or doc.get('animations')) and not allow_skinned:
        raise AssetError('Input is already rigged/animated. Use the original unskinned mesh; rigs are never overwritten silently')
    mesh_nodes=[i for i,n in enumerate(doc.get('nodes',[])) if 'mesh' in n]
    if len(mesh_nodes)!=1:
        raise AssetError('This release requires one mesh node (multiple material primitives are supported). Join objects in Blender first')
    ni=mesh_nodes[0];mi=doc['nodes'][ni]['mesh']
    parent={}
    for i,n in enumerate(doc['nodes']):
        for c in n.get('children',[]):
            if c in parent:raise AssetError('Node has multiple parents')
            parent[c]=i
    chain=[];cur=ni
    while True:
        if cur in chain:raise AssetError('Cyclic node hierarchy')
        chain.append(cur)
        if cur not in parent:break
        cur=parent[cur]
    transform=np.eye(4)
    for i in reversed(chain):transform=transform@node_matrix(doc['nodes'][i])
    if abs(np.linalg.det(transform[:3,:3]))<1e-12:raise AssetError('Singular node transform')
    vs,ns,fs,uvs,ps,pfs=[],[],[],[],[],[];nv=nf=0
    colors=[];have_colors=False;tangents=[];have_tangents=True
    for p in doc['meshes'][mi]['primitives']:
        if p.get('mode',4)!=4 or p.get('targets'):
            raise AssetError('Triangle primitives without pre-existing morph targets are required')
        attr=p['attributes'];v=accessor(doc,blob,attr['POSITION']).astype(float)
        if not np.isfinite(v).all():raise AssetError('Nonfinite mesh positions')
        ind=accessor(doc,blob,p['indices'],False).ravel().astype(int) if 'indices' in p else np.arange(len(v))
        if len(ind)%3 or ind.min()<0 or ind.max()>=len(v):raise AssetError('Invalid triangle indices')
        f=ind.reshape(-1,3)
        n=accessor(doc,blob,attr['NORMAL']) if 'NORMAL' in attr else vertex_normals(v,f)
        uv=accessor(doc,blob,attr['TEXCOORD_0']) if 'TEXCOORD_0' in attr else np.zeros((len(v),2))
        if 'COLOR_0' in attr:
            c=accessor(doc,blob,attr['COLOR_0']);have_colors=True
            if c.shape[1]==3:c=np.c_[c,np.ones(len(c))]
        else:c=np.ones((len(v),4))
        if 'TANGENT' in attr:
            tangents.append(accessor(doc,blob,attr['TANGENT']))
        else:
            have_tangents=False
        vs.append(v);ns.append(n);fs.append(f+nv);uvs.append(uv);colors.append(c)
        ps.append((nv,nv+len(v)));pfs.append((nf,nf+len(f)));nv+=len(v);nf+=len(f)
    asset=MeshAsset(doc,blob,np.vstack(vs),np.vstack(ns),np.vstack(fs),ps,pfs,np.vstack(uvs),
                    hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                    {'source':Path(path).name,'mesh_index':mi,'node_index':ni,
                     'scale_status':'unverified_asset_units', 'source_transform':transform.tolist()},
                    np.vstack(colors) if have_colors else None,
                    np.vstack(tangents) if have_tangents else None)
    return asset.transformed(transform)


def resize_textures(doc: dict,blob: bytes,limit: int | None) -> tuple[dict,bytes,list[dict]]:
    """Repack image views at the requested resolution."""
    d=copy.deepcopy(doc)
    if limit is None:return d,blob,[]
    if limit<64:raise ValueError('Texture limit must be at least 64 pixels')
    overrides={};changes=[]
    for im in d.get('images',[]):
        if 'bufferView' not in im:raise AssetError('Cannot resize external images')
        vi=im['bufferView'];view=d['bufferViews'][vi];start=view.get('byteOffset',0)
        image=Image.open(BytesIO(blob[start:start+view['byteLength']]))
        before=image.size
        if max(before)<=limit:continue
        image.thumbnail((limit,limit),Image.Resampling.LANCZOS)
        b=BytesIO();image.save(b,format='PNG');overrides[vi]=b.getvalue();im['mimeType']='image/png'
        changes.append({'image':im.get('name',str(vi)),'before':list(before),'after':list(image.size)})
    out=bytearray()
    for vi,view in enumerate(d.get('bufferViews',[])):
        while len(out)%4:out.append(0)
        start=view.get('byteOffset',0)
        chunk=overrides.get(vi,blob[start:start+view['byteLength']])
        view['byteOffset']=len(out);view['byteLength']=len(chunk);out.extend(chunk)
    return d,bytes(out),changes


def export_asset(asset: MeshAsset,path: str | Path,skeleton: Skeleton | None=None,
                 joints: np.ndarray | None=None,weights: np.ndarray | None=None,
                 clips: list[Clip] | None=None,texture_limit: int | None=None) -> dict:
    doc,blob,changes=resize_textures(asset.doc,asset.blob,texture_limit)
    app=Appender(doc,blob)
    mesh=copy.deepcopy(doc['meshes'][asset.metadata['mesh_index']]);mesh['name']='WildlifeSurface'
    for i,p in enumerate(mesh['primitives']):
        a,b=asset.primitive_slices[i];fa,fb=asset.primitive_face_slices[i]
        p['attributes']['POSITION']=app.add(asset.vertices[a:b],bounds=True,target=34962)
        p['attributes']['NORMAL']=app.add(asset.normals[a:b],target=34962)
        if asset.tangents is not None:
            p['attributes']['TANGENT']=app.add(asset.tangents[a:b],'VEC4',target=34962)
        else:
            p['attributes'].pop('TANGENT',None)
        p['indices']=app.add(asset.faces[fa:fb]-a,'SCALAR',5125,target=34963)
        if asset.colors is not None:p['attributes']['COLOR_0']=app.add(asset.colors[a:b],'VEC4',target=34962)
        if skeleton is not None:
            p['attributes']['JOINTS_0']=app.add(joints[a:b],'VEC4',5123,target=34962)
            p['attributes']['WEIGHTS_0']=app.add(weights[a:b],'VEC4',5126,target=34962)
    doc['meshes']=[mesh]
    doc['nodes']=[{'name':'WildlifeModel','children':[1]}, {'name':'Surface','mesh':0}]
    doc['scenes']=[{'name':'WildlifeScene','nodes':[0]}];doc['scene']=0
    doc.pop('skins',None);doc.pop('animations',None);doc.pop('cameras',None)
    manifest={'schema':'wildlife-motion.asset/1','source_sha256':asset.source_sha256,
              'vertices':len(asset.vertices),'triangles':len(asset.faces),
              'coordinate_system':'+Y up, +Z forward, +X anatomical left',
              'metadata':asset.metadata,'texture_resizing':changes,'clips':[]}
    if skeleton is not None:
        if joints is None or weights is None:raise ValueError('Skin weights required')
        if joints.shape!=(len(asset.vertices),4) or weights.shape!=joints.shape:
            raise ValueError('Exactly four skin influences per vertex required')
        if (not np.isfinite(weights).all() or np.min(weights)<0
                or not np.allclose(weights.sum(1),1,atol=3e-7)):
            raise ValueError('Invalid skin weights')
        if np.min(joints)<0 or np.max(joints)>=len(skeleton.names):raise ValueError('Joint index out of range')
        doc['nodes'][0]['children']=[2];doc['nodes'][1]['skin']=0
        doc['scenes'][0]['nodes']=[0,1]
        offsets=skeleton.offsets
        for j,name in enumerate(skeleton.names):
            node={'name':name,'translation':offsets[j].tolist()}
            children=(np.flatnonzero(skeleton.parents==j)+2).tolist()
            if children:node['children']=children
            doc['nodes'].append(node)
        ibm=np.tile(np.eye(4),(len(skeleton.names),1,1));ibm[:,:3,3]=-skeleton.rest
        ib=app.add(ibm.transpose(0,2,1).reshape(-1,16),'MAT4')
        doc['skins']=[{'name':'WildlifeRig','joints':list(range(2,len(skeleton.names)+2)),
                       'skeleton':2,'inverseBindMatrices':ib}]
        doc['animations']=[]
        for clip in clips or []:
            tm=app.add(clip.times,'SCALAR',bounds=True)
            animation={'name':clip.name,'samplers':[],'channels':[],
                       'extras':{'loop':clip.loop,'wildlife_motion':clip.metadata}}
            for j in range(len(skeleton.names)):
                for track,array,kind in [('translation',clip.translations[:,j],'VEC3'),
                                         ('rotation',clip.rotations[:,j],'VEC4')]:
                    output=app.add(array,kind)
                    si=len(animation['samplers'])
                    animation['samplers'].append({'input':tm,'output':output,'interpolation':'LINEAR'})
                    animation['channels'].append({'sampler':si,'target':{'node':j+2,'path':track}})
            doc['animations'].append(animation)
            manifest['clips'].append({'name':clip.name,'duration_s':float(clip.times[-1]),
                                      'frames':len(clip.times),'loop':clip.loop,**clip.metadata})
        manifest['joint_count']=len(skeleton.names)
        manifest['rig']=skeleton.to_dict()
    doc.setdefault('asset',{})['generator']='yellowstone-wildlife-motion 0.1.0'
    doc['extras']={'wildlife_motion':manifest}
    write_glb(path,doc,app.blob)
    Path(path).with_suffix('.manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False))
    return manifest
