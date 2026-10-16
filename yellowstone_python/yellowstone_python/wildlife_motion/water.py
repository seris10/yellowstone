"""Surface swimming with buoyancy and drag."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import csv,json
from pathlib import Path
import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq
from .birds import paddle_cycle
from .core import axis_rotation


def submerged_fraction(q: float | np.ndarray):
    q=np.clip(q,-1.,1.)
    return .5+.75*q-.25*q**3


@dataclass
class WaterConfig:
    mass_kg: float=1.0
    radii_m: tuple[float,float,float]=(.095,.085,.19)
    density_kg_m3: float=1000.
    gravity_m_s2: float=9.80665
    body_drag_coefficient: float=.8
    foot_drag_coefficient: float=1.1
    foot_area_m2: float=.0022
    foot_separation_m: float=.09
    frequency_hz: float=1.6
    power_fraction: float=.60
    stance_sweep_m: float=.085
    recovery_lift_m: float=.018
    phase_offset: float=.5
    heave_damping_n_s_m: float=9.
    yaw_damping_n_m_s: float=.025
    steering_bias: float=0.
    current_m_s: tuple[float,float,float]=(0.,0.,0.)
    wave_amplitude_m: float=.008
    wave_length_m: float=1.4
    wave_period_s: float=1.5
    parameter_status: str='authored_surrogate_inputs_not_species_measurements'

    def __post_init__(self):
        if (len(self.radii_m)!=3 or len(self.current_m_s)!=3
                or not np.isfinite(self.radii_m).all()
                or not np.isfinite(self.current_m_s).all()):
            raise ValueError('Radii and current require three finite components')
        scalars=[v for v in asdict(self).values() if isinstance(v,(int,float))]
        if not np.isfinite(scalars).all():raise ValueError('Water inputs must be finite')
        if min(self.mass_kg,self.density_kg_m3,self.gravity_m_s2,*self.radii_m,
               self.frequency_hz,self.wave_length_m,self.wave_period_s)<=0:
            raise ValueError('Mass, dimensions, frequency and wave scales must be positive')
        if min(self.body_drag_coefficient,self.foot_drag_coefficient,self.foot_area_m2,
               self.heave_damping_n_s_m,self.yaw_damping_n_m_s,self.stance_sweep_m,
               self.recovery_lift_m,self.wave_amplitude_m,self.foot_separation_m)<0:
            raise ValueError('Areas, coefficients, amplitudes and damping cannot be negative')
        if not 0<self.power_fraction<1 or abs(self.steering_bias)>.8:
            raise ValueError('Invalid power fraction or steering bias')
        if len(self.radii_m)!=3 or len(self.current_m_s)!=3 or not np.isfinite(self.current_m_s).all():
            raise ValueError('Radii and current require three finite components')

    @property
    def volume_m3(self):return 4*np.pi*np.prod(self.radii_m)/3


def surface(x: float,z: float,t: float,c: WaterConfig):
    k=2*np.pi/c.wave_length_m;phase=k*z-2*np.pi*t/c.wave_period_s
    return c.wave_amplitude_m*np.sin(phase),c.wave_amplitude_m*k*np.cos(phase)


def equilibrium_center_height(c: WaterConfig):
    fraction=c.mass_kg/(c.density_kg_m3*c.volume_m3)
    if fraction>=1:raise ValueError('Configured mass cannot float in the ellipsoid volume')
    q=brentq(lambda q:submerged_fraction(q)-fraction,-1,1)
    return -q*c.radii_m[1]


def water_forces(t: float,state: np.ndarray,c: WaterConfig):
    """State [x,y,z,vx,vy,vz,yaw,yaw_rate]. Force is N, moment N m."""
    pos=state[:3];vel=state[3:6];yaw=state[6];rate=state[7]
    rot=axis_rotation('y',yaw);height,slope=surface(pos[0],pos[2],t,c)
    q=(height-pos[1])/c.radii_m[1];fraction=float(submerged_fraction(q))
    buoyancy=c.density_kg_m3*c.gravity_m_s2*c.volume_m3*fraction
    force=np.array([0.,buoyancy-c.mass_kg*c.gravity_m_s2-fraction*c.heave_damping_n_s_m*vel[1],0.])
    relative=vel-np.asarray(c.current_m_s);horizontal=relative.copy();horizontal[1]=0
    area=np.pi*c.radii_m[0]*c.radii_m[1]*fraction
    force-=.5*c.density_kg_m3*c.body_drag_coefficient*area*np.linalg.norm(horizontal)*horizontal
    moment=-fraction*c.yaw_damping_n_m_s*rate;foot_forces=[];foot_immersion=[]
    for sign,phase in [(1,0.),(-1,c.phase_offset)]:
        displacement,foot_velocity,effective_area=paddle_cycle(t,c.frequency_hz,c.power_fraction,
                                      c.stance_sweep_m,c.recovery_lift_m,phase)
        lever=rot@np.array([sign*c.foot_separation_m/2,-.09+displacement[1],displacement[2]])
        foot_position=pos+lever
        foot_surface,_=surface(foot_position[0],foot_position[2],t,c)
        depth=foot_surface-foot_position[1]
        wet=float(np.clip(depth/max(np.sqrt(c.foot_area_m2),1e-6),0.,1.))
        world_velocity=vel+rot@foot_velocity+np.cross([0,rate,0],lever)
        rel=world_velocity-np.asarray(c.current_m_s)
        # Reduce projected foot area during wetted recovery.
        multiplier=1+sign*c.steering_bias
        fd=-.5*c.density_kg_m3*c.foot_drag_coefficient*c.foot_area_m2*wet*effective_area*multiplier*np.linalg.norm(rel)*rel
        force+=fd;moment+=np.cross(lever,fd)[1];foot_forces.append(fd.tolist())
        foot_immersion.append(wet)
    return force,moment,{'submerged_fraction':fraction,'buoyancy_n':buoyancy,
                        'surface_height_m':height,'surface_slope':slope,'foot_forces_n':foot_forces,
                        'foot_wetted_fraction':foot_immersion,'body_wetted_area_m2':area,
                        'wetted_area_policy':'authored submerged-volume fraction and bounded foot-depth transition'}


def simulate(c: WaterConfig,duration: float=8.,fps: int=60,initial_state=None):
    if not 0<duration<=600 or not 1<=fps<=240:raise ValueError('Duration in (0,600], fps in [1,240] required')
    y0=np.zeros(8) if initial_state is None else np.asarray(initial_state,float).copy()
    if initial_state is None:y0[1]=equilibrium_center_height(c)
    if y0.shape!=(8,) or not np.isfinite(y0).all():raise ValueError('Initial state requires eight finite SI values')
    inertia=c.mass_kg*(c.radii_m[0]**2+c.radii_m[2]**2)/5
    def rhs(t,y):
        force,torque,_=water_forces(t,y,c)
        return np.r_[y[3:6],force/c.mass_kg,y[7],torque/inertia]
    times=np.linspace(0,duration,max(2,round(duration*fps)+1))
    result=solve_ivp(rhs,(0,duration),y0,t_eval=times,rtol=2e-7,atol=1e-9,
                     max_step=min(1/120,1/(100*c.frequency_hz)))
    if not result.success or not np.isfinite(result.y).all():raise RuntimeError('Water integration failed: '+result.message)
    states=result.y.T
    values=[water_forces(t,y,c)[2] for t,y in zip(times,states)]
    return {'times':times,'states':states,'surface_height_m':np.array([d['surface_height_m'] for d in values]),
            'submerged_fraction':np.array([d['submerged_fraction'] for d in values]),
            'config':asdict(c),'integration':{'method':'RK45','nfev':result.nfev,'rtol':2e-7,'atol':1e-9},
            'schema':'wildlife-motion.water/1'}


def save_simulation(result,path: str | Path):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['time_s','x_m','y_m','z_m','vx_m_s','vy_m_s','vz_m_s','yaw_rad','yaw_rate_rad_s','surface_height_m','submerged_fraction'])
        for t,y,h,v in zip(result['times'],result['states'],result['surface_height_m'],result['submerged_fraction']):w.writerow([t,*y,h,v])
    meta={k:v for k,v in result.items() if not isinstance(v,np.ndarray)}
    meta['limitations']=['Drag-based surface prototype; not calibrated for a biological specimen.',
      'No free-surface wave resistance, underwater lift model, or energy/metabolic model.',
      'Ellipsoid is a hydrostatic proxy, not the visible mesh displacement volume.']
    path.with_suffix('.json').write_text(json.dumps(meta,indent=2))


def bird_pose_from_water(engine,result: dict,time: float,meters_per_asset_unit: float):
    """Apply surface displacement and yaw to bird kinematics."""
    if not np.isfinite(meters_per_asset_unit) or meters_per_asset_unit<=0:
        raise ValueError('Supply a positive physical scale for the visible mesh')
    from .core import Pose
    times=result['times'];t=float(np.clip(time,times[0],times[-1]))
    state=np.array([np.interp(t,times,result['states'][:,i]) for i in range(8)])
    c=WaterConfig(**result['config']);h=engine.skeleton.metadata['height'];scale=meters_per_asset_unit
    controls={'frequency_hz':c.frequency_hz,'power_fraction':c.power_fraction,
              'sweep_height':c.stance_sweep_m/(scale*h),
              'recovery_lift_height':c.recovery_lift_m/(scale*h),'left_right_phase':c.phase_offset}
    pose=engine.pose(t,'Paddle',controls)
    _,slope=surface(state[0],state[2],t,c)
    rot=axis_rotation('y',state[6])@axis_rotation('x',-np.arctan(slope))
    anchor=pose.positions[engine.skeleton.index('pelvis')].copy()
    p=(pose.positions-anchor)@rot.T+state[:3]/scale
    r=np.einsum('ij,njk->nik',rot,pose.rotations)
    return Pose(p,r,{**pose.diagnostics,'water_parameter_status':c.parameter_status,
         'root_motion':'integrated_SI_surface_surrogate','meters_per_asset_unit':scale})
