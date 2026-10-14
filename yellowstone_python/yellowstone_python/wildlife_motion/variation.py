"""Seeded morphology controls and population fitting."""
from __future__ import annotations
import copy,csv,hashlib
from dataclasses import dataclass,asdict
from pathlib import Path
import numpy as np
from .core import Skeleton,vertex_normals,smoothstep
from .gltf import MeshAsset

FEATURES=['size','body_width','body_depth','head_size','leg_length','tail_length']


@dataclass
class Variant:
    size: float=1.
    body_width: float=1.
    body_depth: float=1.
    head_size: float=1.
    leg_length: float=1.
    tail_length: float=1.
    coat_tint: tuple[float,float,float]=(1.,1.,1.)
    seed: int=0
    status: str='explicit_authored_controls'
    demographic_metadata: dict | None=None

    def __post_init__(self):
        for f in FEATURES:
            v=getattr(self,f)
            if not np.isfinite(v) or not .75<=v<=1.25:
                raise ValueError(f'{f} must be in [.75,1.25]; larger changes require a different deformation model')
        if len(self.coat_tint)!=3 or not np.isfinite(self.coat_tint).all() or min(self.coat_tint)<.2 or max(self.coat_tint)>1:
            raise ValueError('Coat tint must be three linear multipliers in [.2,1]')


def sample_artistic(seed: int=0,strength: float=.5):
    if not 0<=strength<=1:raise ValueError('Artistic strength must be in [0,1]')
    rng=np.random.default_rng(seed)
    sd=np.array([.035,.07,.045,.025,.025,.035])*strength
    vals=np.exp(rng.normal(size=6)*sd)
    tint=np.clip(1-rng.uniform(0,.15,3)*strength,.75,1.)
    return Variant(**dict(zip(FEATURES,vals)),coat_tint=tuple(tint),seed=seed,
                   status='artistic_randomization_not_biological_population_sampling')


def warp(points: np.ndarray,sk: Skeleton,c: Variant):
    """Continuous deformation field applied identically to mesh and rig points."""
    p=np.asarray(points,float).copy();q=p.copy();h=sk.metadata['height'];L=sk.metadata['length']
    hip=sk.rest[sk.index('pelvis')];thorax=sk.rest[sk.index('thorax')];head=sk.rest[sk.index('head')]
    # Preserve the ground while changing limb reach, lifting the torso smoothly.
    q[:,1]+=(c.leg_length-1)*.48*h*smoothstep(p[:,1]/(.5*h))
    trunk=smoothstep((p[:,2]-(hip[2]-.18*L))/(.18*L))*(1-smoothstep((p[:,2]-thorax[2])/(.18*L)))
    trunk*=smoothstep((p[:,1]-.28*h)/(.25*h))
    q[:,0]*=1+(c.body_width-1)*trunk
    q[:,1]+=(c.body_depth-1)*trunk*(p[:,1]-.60*h)
    radius=max(np.linalg.norm(head-sk.rest[sk.index('neck' if sk.metadata['engine']=='mammal' else 'neck_1')])*1.8,.16*h)
    headfield=np.exp(-np.sum(((p-head)/radius)**2,axis=1)**2)
    q+=(c.head_size-1)*headfield[:,None]*(p-head)
    if 'tail' in sk.groups:
        base=sk.rest[sk.groups['tail'][0]]
        direction=sk.rest[sk.groups['tail'][-1]]-base
        norm=np.linalg.norm(direction)
        if norm>1e-9:
            direction/=norm;d=(p-base)@direction
            lateral=np.linalg.norm(p-base-d[:,None]*direction,axis=1)
            field=smoothstep(d/max(.1*L,1e-9))*np.exp(-(lateral/(.10*h))**4)
            q+=(c.tail_length-1)*field[:,None]*d[:,None]*direction
    return q*c.size


def diversify(asset: MeshAsset,sk: Skeleton,config: Variant):
    new=copy.copy(asset);new.vertices=warp(asset.vertices,sk,config);new.normals=vertex_normals(new.vertices,new.faces)
    new.tangents=None
    new.metadata=copy.deepcopy(asset.metadata);new.metadata['variant']=asdict(config)
    skeleton=Skeleton.from_dict(sk.to_dict());skeleton.rest=warp(sk.rest,sk,config)
    skeleton.metadata['variant']=asdict(config);skeleton.metadata['height']=float(np.ptp(new.vertices[:,1]));skeleton.metadata['length']=float(np.ptp(new.vertices[:,2]))
    skeleton.metadata.pop('sole_offsets',None)
    # Apply cosmetic color multipliers above paws and facial features.
    h=sk.metadata['height'];head=sk.rest[sk.index('head')]
    regional=smoothstep((asset.vertices[:,1]-.17*h)/(.22*h))
    regional*=1-np.exp(-np.sum((asset.vertices-head)**2,axis=1)/(.17*h)**2)
    factors=1+regional[:,None]*(np.asarray(config.coat_tint)-1)
    colors=np.ones((len(asset.vertices),4)) if asset.colors is None else asset.colors.copy()
    colors[:,:3]*=factors;new.colors=colors.astype(np.float32)
    return new,skeleton


def fit_population(csv_path: str | Path,qualifiers: dict | None=None):
    """Fit relative morphology factors by specimen."""
    path=Path(csv_path);rows=list(csv.DictReader(path.open(newline='')));filters=qualifiers or {}
    data={}
    for row in rows:
        if any(row.get(k)!=v for k,v in filters.items()):continue
        sid=row.get('specimen_id','').strip()
        if not sid:raise ValueError('Each observation needs a known specimen_id; unknown identity cannot be pooled as independent')
        v=np.array([float(row[f]) for f in FEATURES])
        if not np.isfinite(v).all() or np.any(v<=0):raise ValueError('Population factors must be positive and finite')
        data.setdefault(sid,[]).append(np.log(v))
    if len(data)<5:raise ValueError('At least five independently identified specimens are required; even five is exploratory')
    x=np.array([np.mean(v,axis=0) for v in data.values()]);cov=np.cov(x,rowvar=False)
    alpha=.4 # Authored covariance shrinkage strength.
    cov=(1-alpha)*cov+alpha*np.diag(np.diag(cov))
    return {'schema':'wildlife-motion.population/1','features':FEATURES,'log_mean':x.mean(0).tolist(),
            'log_covariance':cov.tolist(),'n_specimens':len(x),'n_observations':sum(map(len,data.values())),
            'specimen_ids':sorted(data),'qualifiers':filters,'covariance_diagonal_shrinkage':alpha,
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'status':'empirical_fit_to_user_supplied_relative_factors; not independently biologically validated'}


def sample_population(model: dict,seed: int=0):
    if model.get('schema')!='wildlife-motion.population/1' or model['features']!=FEATURES:
        raise ValueError('Unsupported population model')
    rng=np.random.default_rng(seed);mu=np.asarray(model['log_mean']);cov=np.asarray(model['log_covariance'])
    if mu.shape!=(6,) or cov.shape!=(6,6) or not np.isfinite(mu).all() or not np.isfinite(cov).all():raise ValueError('Invalid population model arrays')
    # Reject samples outside the deformation domain.
    for _ in range(100):
        values=np.exp(rng.multivariate_normal(mu,cov,check_valid='raise'))
        if np.all((values>=.75)&(values<=1.25)):
            return Variant(**dict(zip(FEATURES,values)),seed=seed,status='sampled_user_population_with_domain_rejection',demographic_metadata=model.get('qualifiers'))
    raise ValueError('Population lies outside the deformation domain; use a different base mesh or deformation model')
