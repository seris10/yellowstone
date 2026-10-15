"""Original engineering bird proxy. Explicitly NOT an anatomical reference asset."""
from __future__ import annotations
import hashlib
import numpy as np
from .core import Skeleton,vertex_normals
from .gltf import MeshAsset,Appender


def ellipsoid(center,radii,segments=20,rings=12):
    # Pole duplication is avoided: all triangles have positive area.
    c=np.asarray(center);r=np.asarray(radii);v=[c+np.array([0,r[1],0])]
    for j in range(1,rings):
        ph=np.pi*j/rings
        for i in range(segments):
            th=2*np.pi*i/segments
            v.append(c+r*np.array([np.sin(ph)*np.cos(th),np.cos(ph),np.sin(ph)*np.sin(th)]))
    v.append(c-np.array([0,r[1],0]));bottom=len(v)-1;f=[]
    for i in range(segments):f.append([0,1+(i+1)%segments,1+i])
    for j in range(rings-2):
        for i in range(segments):
            a=1+j*segments+i;b=1+j*segments+(i+1)%segments;d=a+segments;e=b+segments
            f.extend([[a,b,d],[b,e,d]])
    last=1+(rings-2)*segments
    for i in range(segments):f.append([last+i,last+(i+1)%segments,bottom])
    return np.array(v),np.array(f)


def bird_proxy(spread: bool=False):
    names=['root','pelvis','thorax','neck_0','neck_1','head']
    pos=[[0,0,0],[0,.40,-.08],[0,.43,.12],[0,.48,.25],[0,.61,.29],[0,.70,.34]]
    par=[-1,0,1,2,3,4];groups={'body':[1,2,3,4,5],'neck':[3,4,5]}
    for side,sign in [('L',1),('R',-1)]:
        points=[[sign*.10,.39,-.04],[sign*.11,.28,.04],[sign*.12,.15,-.07],[sign*.12,.045,.02]]
        ids=[];last=1
        for label,p in zip(['upper','middle','ankle','foot'],points):
            ids.append(len(names));names.append(side+'_'+label);pos.append(p);par.append(last);last=len(names)-1
        groups[side]=ids
    for side,sign in [('L',1),('R',-1)]:
        points=([[sign*.12,.46,.10],[sign*.34,.47,.07],[sign*.56,.46,-.04],[sign*.83,.43,-.20]] if spread else
                [[sign*.13,.46,.10],[sign*.19,.45,-.03],[sign*.19,.43,-.17],[sign*.15,.41,-.30]])
        ids=[];last=2
        for label,p in zip(['shoulder','elbow','wrist','tip'],points):
            ids.append(len(names));names.append('wing_'+side+'_'+label);pos.append(p);par.append(last);last=len(names)-1
        groups['wing_'+side]=ids
    ids=[];last=1
    for i,p in enumerate([[0,.40,-.29],[0,.43,-.44]]):
        ids.append(len(names));names.append('tail_'+str(i));pos.append(p);par.append(last);last=len(names)-1
    groups['tail']=ids
    sk=Skeleton(names,np.array(par),np.array(pos),groups,{'engine':'bird','species':'mallard','review_status':'synthetic_fixture',
        'wing_state':'spread' if spread else 'folded','height':.82,'length':1.,'scale_status':'synthetic_fixture_meters',
        'float_waterline':.30,'canonical_transform':np.eye(4).tolist(),'parameter_status':'authored_engineering_fixture'})
    vertices=[];faces=[];colors=[];joints=[];weights=[];N=0
    def add(center,radii,joint,color):
        nonlocal N
        v,f=ellipsoid(center,radii);vertices.append(v);faces.append(f+N);colors.append(np.tile([*color,1.],(len(v),1)))
        joints.append(np.tile([joint,0,0,0],(len(v),1)));weights.append(np.tile([1.,0,0,0],(len(v),1)));N+=len(v)
    add([0,.415,-.01],[.18,.17,.32],1,[.63,.66,.65])
    add([0,.48,.20],[.13,.13,.17],2,[.27,.20,.15])
    add([0,.585,.28],[.075,.13,.07],4,[.10,.33,.26])
    add([0,.705,.345],[.105,.105,.12],5,[.11,.38,.27])
    add([0,.685,.47],[.087,.032,.12],5,[.87,.62,.13])
    for sign in [1,-1]:add([sign*.094,.738,.392],[.017,.017,.017],5,[.018,.022,.02])
    for side,sign in [('L',1),('R',-1)]:
        a,b,c,d=groups[side]
        add((sk.rest[b]+sk.rest[c])*.5,[.027,.087,.030],b,[.74,.35,.09])
        add(sk.rest[d]+[0,0,.035],[.073,.021,.093],d,[.9,.43,.07])
        if spread:
            for k,j in enumerate(groups['wing_'+side][:-1]):
                p=sk.rest[j];q=sk.rest[groups['wing_'+side][k+1]]
                center=(p+q)*.5
                add(center,[abs(q[0]-p[0])*.65,.027,.14 if k<2 else .20],j,[.35-.05*k,.42-.04*k,.40-.03*k])
            # Arrange terminal feathers as an authored geometry fixture.
            for k in range(7):
                add([sign*(.58+.035*k),.443,-.17-.018*k],[.042,.014,.20],groups['wing_'+side][2],[.27,.31,.32])
        else:add([sign*.151,.47,-.055],[.058,.099,.25],groups['wing_'+side][0],[.32,.39,.40])
    add([0,.425,-.36],[.105,.033,.13],groups['tail'][0],[.28,.33,.32])
    v=np.vstack(vertices);f=np.vstack(faces);c=np.vstack(colors);n=vertex_normals(v,f)
    doc={'asset':{'version':'2.0','generator':'Wildlife Motion original synthetic engineering fixture'},
         'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0,'materials':[{'name':'ProxySurface','doubleSided':True,
         'pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':.85}}]}
    app=Appender(doc);attr={'POSITION':app.add(v,bounds=True,target=34962),'NORMAL':app.add(n,target=34962),'COLOR_0':app.add(c,'VEC4',target=34962)}
    ind=app.add(f,'SCALAR',5125,target=34963)
    doc['meshes']=[{'primitives':[{'attributes':attr,'indices':ind,'material':0}]}]
    doc['buffers']=[{'byteLength':len(app.blob)}]
    sha=hashlib.sha256(v.tobytes()+f.tobytes()).hexdigest();sk.metadata['source_sha256']=sha
    asset=MeshAsset(doc,bytes(app.blob),v,n,f,[(0,len(v))],[(0,len(f))],None,sha,
                   {'mesh_index':0,'source':'original_synthetic_bird_proxy','scale_status':'synthetic_fixture_meters','canonical_transform':np.eye(4).tolist()},c)
    return asset,sk,np.vstack(joints).astype(np.uint16),np.vstack(weights).astype(np.float32)


def mammal_proxy():
    """Simple four-legged test solid; no biological specimen measurements."""
    vertices=[];faces=[];count=0
    parts=[([0,.8,0],[.26,.32,.62]),([0,.94,.62],[.22,.22,.26]),
           ([0,.92,-.70],[.06,.06,.15])]
    for sign in [-1,1]:
        for z in [-.43,.43]:
            parts.extend([([sign*.20,.37,z],[.075,.30,.085]),([sign*.20,.055,z+.04],[.095,.055,.12])])
    for center,radii in parts:
        v,f=ellipsoid(center,radii,16,10);vertices.append(v);faces.append(f+count);count+=len(v)
    v=np.vstack(vertices);f=np.vstack(faces);n=vertex_normals(v,f)
    doc={'asset':{'version':'2.0'},'nodes':[{'mesh':0}],'scenes':[{'nodes':[0]}],'scene':0}
    app=Appender(doc);attr={'POSITION':app.add(v,bounds=True),'NORMAL':app.add(n)};ind=app.add(f,'SCALAR',5125)
    doc['meshes']=[{'primitives':[{'attributes':attr,'indices':ind}]}];doc['buffers']=[{'byteLength':len(app.blob)}]
    sha=hashlib.sha256(v.tobytes()).hexdigest()
    return MeshAsset(doc,bytes(app.blob),v,n,f,[(0,len(v))],[(0,len(f))],None,sha,
                     {'mesh_index':0,'source':'original_synthetic_quadruped','canonical_transform':np.eye(4).tolist()})
