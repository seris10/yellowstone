"""Quadruped kinematics with foot contacts."""
from __future__ import annotations
from dataclasses import dataclass
import copy
import numpy as np
from .core import (Skeleton,Pose,Clip,fk,axis_rotation,smootherstep,
                   pose_limb,sample_clip,AssetError)

FOOTFALLS={
    'walk': {'HL':0.,'FL':.25,'HR':.5,'FR':.75},
    'running_walk': {'HL':0.,'FL':.25,'HR':.5,'FR':.75},
    'trot': {'FL':0.,'HR':0.,'FR':.5,'HL':.5},
    'pace': {'FL':0.,'HL':0.,'FR':.5,'HR':.5},
    'canter': {'HL':0.,'HR':.18,'FL':.18,'FR':.45},
    'transverse_gallop': {'HL':0.,'HR':.12,'FL':.48,'FR':.60},
    'rotary_gallop': {'HL':0.,'HR':.12,'FR':.48,'FL':.60},
}


def foot_cycle(phase: float,duty: float,stance_length: float,clearance: float) -> tuple[float,float,bool]:
    """Return fore-aft displacement, lift, and contact state."""
    if (not np.isfinite([phase,duty,stance_length,clearance]).all()
            or not 0<duty<1 or stance_length<0 or clearance<0):
        raise ValueError('Duty must be in (0,1); distances must be nonnegative')
    p=float(phase%1.)
    if p<duty:
        return stance_length*(.5-p/duty),0.,True
    q=(p-duty)/(1-duty);r=(1-duty)/duty
    z=stance_length*(-.5+(1+r)*float(smootherstep(q))-r*q)
    y=clearance*64*q**3*(1-q)**3
    return z,y,False


def stride_speed(frequency: float,stance_length: float,duty: float) -> float:
    if (not np.isfinite([frequency,stance_length,duty]).all()
            or frequency<=0 or stance_length<0 or not 0<duty<1):
        raise ValueError('Positive frequency, nonnegative sweep and valid duty required')
    return frequency*stance_length/duty


def register_sole_offsets(vertices,joints,weights,skeleton):
    offsets={}
    legs=['FL','FR','HL','HR'] if skeleton.metadata['engine']=='mammal' else ['L','R']
    for name in legs:
        fi=skeleton.groups[name][-1]
        influence=np.sum(weights*(joints==fi),axis=1)
        mask=influence>.80
        if np.any(mask):
            minimum=float(vertices[mask,1].min())
            offsets[name]=float(skeleton.rest[fi,1]-minimum)
        else:offsets[name]=float(skeleton.rest[fi,1])
    skeleton.metadata['sole_offsets']=offsets


@dataclass
class MammalEngine:
    skeleton: Skeleton
    profile: dict

    def parameters(self,mode: str,overrides: dict | None=None) -> dict:
        if mode not in self.profile['gaits']:
            raise AssetError(f'{mode} is not enabled for {self.profile["common_name"]}')
        from .calibration import resolve_touchdown_phases
        p=copy.deepcopy(self.profile['gaits'][mode])
        supported=set(p) | {'touchdown_phases'}
        if set(overrides or {})-supported:
            raise ValueError('Unsupported mammal controls: '+', '.join(sorted(set(overrides)-supported)))
        p.update(overrides or {})
        numeric=[value for value in p.values() if isinstance(value,(int,float))]
        if not np.isfinite(numeric).all() or p['frequency_hz']<=0 or not 0<p['duty_factor']<1:
            raise ValueError('Gait controls must be finite, with positive frequency and duty in (0,1)')
        if 'touchdown_phases' in p:
            p['touchdown_phases']=resolve_touchdown_phases(p['touchdown_phases'],'mammal')
        for name in ('stance_length_height','clearance_height','body_bob_height','body_lowering_height'):
            if p.get(name,0)<0:raise ValueError(f'{name} cannot be negative')
        return p

    def pose(self,time: float,mode: str='Walk',overrides: dict | None=None,
             root_motion: bool=False,ground=None) -> Pose:
        if not np.isfinite(time):raise ValueError('Motion time must be finite')
        sk=self.skeleton;p=self.parameters(mode,overrides)
        h=sk.metadata['height'];length=sk.metadata['length'];f=p['frequency_hz'];phase=(f*time)%1
        pattern=p['pattern'];idle=pattern=='idle';dig=pattern=='dig'
        n=len(sk.names);lr=np.tile(np.eye(3),(n,1,1))
        body_roll=np.deg2rad(p['body_roll_deg'])*np.sin(2*np.pi*phase)
        lr[sk.index('pelvis')]=axis_rotation('z',body_roll)
        lr[sk.index('lumbar')]=axis_rotation('y',np.deg2rad(.6)*np.sin(2*np.pi*phase+.3))
        lr[sk.index('neck')]=axis_rotation('x',np.deg2rad(1.5 if idle else .7)*np.sin(2*np.pi*phase))
        lr[sk.index('head')]=axis_rotation('y',np.deg2rad(9 if idle else p['head_yaw_deg'])*np.sin(2*np.pi*phase)) @ axis_rotation('z',-.5*body_roll)
        for j in sk.groups.get('tail',[]):
            lr[j]=axis_rotation('y',np.deg2rad(3)*np.sin(2*np.pi*phase))
        bob=p['body_bob_height']*h*(np.cos(4*np.pi*phase)-1)*.5
        body_shift=np.array([0.,bob-p.get('body_lowering_height',0.)*h,0.])
        pose=fk(sk,lr,body_shift)
        S=p['stance_length_height']*h
        speed=0. if idle or dig else stride_speed(f,S,p['duty_factor'])
        contacts={};errors={};targets={}
        sole=sk.metadata.get('sole_offsets',{})
        for leg in ['FL','FR','HL','HR']:
            chain=sk.groups[leg];upper=sk.rest[chain[0]];restfoot=sk.rest[chain[-1]]
            target=restfoot.copy()
            target[1]=sole.get(leg,restfoot[1])
            if idle:
                contact=True;lift=0.;pitch=0.
            elif dig:
                if leg.startswith('F'):
                    local=(phase+(0 if leg=='FL' else .5))%1
                    dz,lift,contact=foot_cycle(local,p['duty_factor'],S,p['clearance_height']*h)
                    target[2]=upper[2]+.14*length+dz
                    target[1]+=lift
                    pitch=-.20*np.sin(2*np.pi*local)
                else:
                    contact=True;lift=0.;pitch=0.
            else:
                schedule=p['touchdown_phases'] if 'touchdown_phases' in p else FOOTFALLS[pattern]
                local=(phase-schedule[leg])%1
                dz,lift,contact=foot_cycle(local,p['duty_factor'],S,p['clearance_height']*h)
                # Move a posed mesh toward a neutral stance, without changing bind geometry.
                neutral_z=.80*restfoot[2]+.20*(upper[2]+(.03 if leg.startswith('F') else -.035)*length)
                target[2]=neutral_z+dz;target[1]+=lift
                pitch=0. if contact else .10*np.sin(np.pi*(local-p['duty_factor'])/(1-p['duty_factor']))
            if ground is not None:
                y,normal=ground(float(target[0]),float(target[2]+speed*time),time)
                target[1]+=y
                from .core import align_vectors
                rf=align_vectors(np.array([0.,1.,0.]),normal)@axis_rotation('x',pitch)
            else:rf=axis_rotation('x',pitch)
            err=pose_limb(sk,pose,chain,target,rf)
            contacts[leg]=contact;errors[leg]=float(err);targets[leg]=target.tolist()
        if root_motion:pose.positions[:,2]+=speed*time
        pose.diagnostics={'contacts':contacts,'targets':targets,'reach_errors':errors,
                          'max_reach_error':max(errors.values()),'speed_asset_units_s':speed}
        return pose

    def clips(self,modes: list[str] | None=None,fps: int=30,cycles: int=2,
              overrides: dict | None=None,root_motion: bool=False) -> list[Clip]:
        if not isinstance(cycles,int) or cycles<1:raise ValueError('At least one integer cycle required')
        result=[]
        for mode in modes or list(self.profile['gaits']):
            p=self.parameters(mode,overrides);duration=cycles/p['frequency_hz']
            speed=0. if p['pattern'] in ('idle','dig') else stride_speed(p['frequency_hz'],p['stance_length_height']*self.skeleton.metadata['height'],p['duty_factor'])
            meta={'engine':'mammal','species':self.profile['id'],'parameter_status':self.profile['parameter_status'],
                  'controls':p,'speed_asset_units_s':speed,'root_motion':root_motion,
                  'scale_status':self.skeleton.metadata.get('scale_status'),'gait_pattern':p['pattern']}
            clip=sample_clip(self.skeleton,lambda t:self.pose(t,mode,overrides,root_motion),
                             duration,fps,mode,loop=not root_motion,metadata=meta)
            result.append(clip)
        return result
