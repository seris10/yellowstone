"""Bird kinematics and wing articulation."""
from __future__ import annotations
from dataclasses import dataclass
import copy
import numpy as np
from .core import Skeleton,Pose,AssetError,fk,pose_limb,axis_rotation,sample_clip
from .mammals import foot_cycle,stride_speed
from .calibration import resolve_touchdown_phases


def paddle_cycle(time: float,frequency_hz: float,power_fraction: float,
                 sweep: float,recovery_lift: float,phase_offset: float=0.) -> tuple[np.ndarray,np.ndarray,float]:
    """Return foot displacement, velocity, and projected web area."""
    if (not np.isfinite([time,frequency_hz,power_fraction,sweep,recovery_lift,phase_offset]).all()
            or frequency_hz<=0 or not 0<power_fraction<1 or min(sweep,recovery_lift)<0):
        raise ValueError('Invalid paddling controls')
    phase=(frequency_hz*time-phase_offset)%1.;b=power_fraction
    z,y,power=foot_cycle(phase,b,sweep,recovery_lift)
    if power:
        vz=-sweep*frequency_hz/b;vy=0.;area=1.
    else:
        q=(phase-b)/(1-b);r=(1-b)/b
        hprime=30*q*q*(1-q)**2
        vz=sweep*((1+r)*hprime-r)*frequency_hz/(1-b)
        vy=recovery_lift*192*q*q*(1-q)**2*(1-2*q)*frequency_hz/(1-b)
        # Continuous feathering: area decreases during recovery and reopens before power.
        area=1.-.87*np.sin(np.pi*q)**2
    return np.array([0.,y,z]),np.array([0.,vy,vz]),float(area)


@dataclass
class BirdEngine:
    skeleton: Skeleton
    profile: dict

    def available_modes(self) -> list[str]:
        modes=list(self.profile['gaits'])
        if self.skeleton.metadata.get('wing_state')!='spread' or self.skeleton.metadata.get('review_status') not in ('reviewed','synthetic_fixture'):
            modes=[m for m in modes if m not in ('Flight','Glide')]
        return modes

    def parameters(self,mode: str,overrides: dict | None=None) -> dict:
        if mode not in self.profile['gaits']:raise AssetError(f'{mode} is not enabled for this bird')
        if mode in ('Flight','Glide') and mode not in self.available_modes():
            raise AssetError('Flight requires wing_state=spread and reviewed landmarks. Folded/fused wings cannot be made flight-ready by this program')
        p=copy.deepcopy(self.profile['gaits'][mode])
        supported=set(p) | ({'touchdown_phases'} if mode=='Walk' else set())
        if set(overrides or {})-supported:
            raise ValueError('Unsupported bird controls: '+', '.join(sorted(set(overrides)-supported)))
        p.update(overrides or {})
        if mode=='Walk':
            p['touchdown_phases']=resolve_touchdown_phases(p.get('touchdown_phases',
                {'L':0.,'R':p.get('left_right_phase',.5)}),'bird')
        numeric=[v for v in p.values() if isinstance(v,(int,float))]
        if not np.isfinite(numeric).all() or p['frequency_hz']<=0:
            raise ValueError('Bird controls must be finite with positive frequency')
        if mode=='Walk' and (not 0<p['duty_factor']<1
                or min(p['stance_length_height'],p['clearance_height'])<0):
            raise ValueError('Bird walking controls are outside their domain')
        if mode=='Paddle' and (not 0<p['power_fraction']<1
                or min(p['sweep_height'],p['recovery_lift_height'])<0):
            raise ValueError('Bird paddling controls are outside their domain')
        return p

    def pose(self,time: float,mode: str='Idle',overrides: dict | None=None,
             root_motion: bool=False) -> Pose:
        if not np.isfinite(time):raise ValueError('Motion time must be finite')
        p=self.parameters(mode,overrides);sk=self.skeleton
        h=sk.metadata['height'];f=p['frequency_hz'];phase=(time*f)%1.;wave=2*np.pi*phase
        lr=np.tile(np.eye(3),(len(sk.names),1,1));shift=np.zeros(3)
        water=mode in ('Float','Paddle');flying=mode in ('Flight','Glide')
        if water:
            shift[1]=-sk.metadata.get('float_waterline',.43*h)+.006*h*np.sin(wave)
            lr[1]=axis_rotation('z',np.deg2rad(1.0)*np.sin(wave))@axis_rotation('x',np.deg2rad(.7)*np.cos(wave))
        elif mode=='Walk':
            shift[1]=.008*h*(np.cos(2*wave)-1)
            lr[1]=axis_rotation('z',np.deg2rad(2.0)*np.sin(wave))
        if flying:
            for side,sgn in [('L',1),('R',-1)]:
                sh,el,wr,tip=sk.groups['wing_'+side]
                flap=np.deg2rad(p['flap_deg'])*np.sin(wave)
                sweep=np.deg2rad(p['sweep_deg'])*np.cos(wave)
                fold=np.deg2rad(p['fold_deg'])*(.5+.5*np.cos(wave))
                lr[sh]=axis_rotation('z',sgn*flap)@axis_rotation('y',sgn*sweep)
                lr[el]=axis_rotation('y',sgn*fold)
                lr[wr]=axis_rotation('y',-sgn*.55*fold)
            shift[1]=.02*h*np.cos(wave)
        if not flying:
            lr[sk.index('head')]=axis_rotation('y',np.deg2rad(5 if mode=='Idle' else 1.5)*np.sin(wave))
        # Stabilize head roll with an authored angle.
        lr[sk.index('neck_1')]=axis_rotation('z',-np.deg2rad(.7)*np.sin(wave)) if water else np.eye(3)
        pose=fk(sk,lr,shift);sole=sk.metadata.get('sole_offsets',{})
        contacts={};errors={};speed=0.;areas={}
        phases=p['touchdown_phases'] if mode=='Walk' else {'L':0.,'R':p.get('left_right_phase',.5)}
        for side,phaseoffset in phases.items():
            chain=sk.groups[side];foot=sk.rest[chain[-1]];target=foot.copy();rf=np.eye(3)
            if mode=='Walk':
                S=p['stance_length_height']*h
                dz,lift,contact=foot_cycle(phase-phaseoffset,p['duty_factor'],S,p['clearance_height']*h)
                target[2]+=dz;target[1]=sole.get(side,foot[1])+lift
                speed=stride_speed(f,S,p['duty_factor'])
            elif mode=='Paddle':
                disp,velocity,area=paddle_cycle(time,f,p['power_fraction'],p['sweep_height']*h,
                                               p['recovery_lift_height']*h,phaseoffset)
                target+=shift+disp
                feather=(1-area)/.87
                rf=axis_rotation('y',(1 if side=='L' else -1)*np.pi*.38*feather)
                areas[side]=area;contact=False
            elif mode=='Float':
                target+=shift;contact=False
            elif flying:
                upper=pose.positions[chain[0]]
                target=np.array([foot[0],upper[1]-.25*h,upper[2]-.10*h])
                rf=axis_rotation('x',-.45);contact=False
            else:
                target[1]=sole.get(side,foot[1]);contact=True
            errors[side]=pose_limb(sk,pose,chain,target,rf);contacts[side]=contact
        if root_motion and mode=='Walk':pose.positions[:,2]+=speed*time
        pose.diagnostics={'max_reach_error':max(errors.values()),'reach_errors':errors,
            'contacts':contacts,'effective_web_area_fraction':areas,'speed_asset_units_s':speed,
            'water_model':'visual surface stroke; use water.py for SI dynamics' if water else None}
        return pose

    def clips(self,modes=None,fps=30,cycles=2,overrides=None,root_motion=False):
        if not isinstance(cycles,int) or cycles<1:
            raise ValueError('At least one integer cycle required')
        clips=[]
        for mode in modes or self.available_modes():
            p=self.parameters(mode,overrides);duration=cycles/p['frequency_hz']
            meta={'engine':'bird','species':self.profile['id'],'controls':p,
                  'parameter_status':self.profile['parameter_status'],'root_motion':root_motion,
                  'wing_state':self.skeleton.metadata.get('wing_state')}
            clips.append(sample_clip(self.skeleton,lambda t:self.pose(t,mode,overrides,root_motion),
               duration,fps,mode,loop=not (root_motion and mode=='Walk'),metadata=meta))
        return clips
