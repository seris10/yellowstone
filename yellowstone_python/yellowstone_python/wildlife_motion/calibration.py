"""Observation fitting for motion controls."""
from __future__ import annotations
import csv,hashlib
from pathlib import Path
import numpy as np


def resolve_touchdown_phases(phases: dict, engine: str) -> dict:
    """Normalize complete contact maps to the selected engine's limb IDs."""
    if engine not in ('bird', 'mammal'):
        raise ValueError('Unknown contact engine: ' + str(engine))
    limbs = ('L', 'R') if engine == 'bird' else ('FL', 'FR', 'HL', 'HR')
    aliases = {'left': 'L', 'right': 'R', 'left_foot': 'L', 'right_foot': 'R',
               'front_left': 'FL', 'front_right': 'FR', 'hind_left': 'HL', 'hind_right': 'HR'}
    if not isinstance(phases, dict):
        raise ValueError('Touchdown phases require a complete limb map')
    resolved = {}
    for key, value in phases.items():
        name = str(key).strip().lower().replace(' ', '_').replace('-', '_')
        limb = aliases.get(name, name.upper())
        if limb not in limbs or limb in resolved:
            raise ValueError('Unknown, incompatible or duplicate touchdown limb: ' + str(key))
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not 0 <= value < 1:
            raise ValueError('Touchdown phases must be finite cycle fractions in [0,1)')
        resolved[limb] = float(value)
    if set(resolved) != set(limbs):
        raise ValueError('Touchdown phases require all limbs: ' + ', '.join(limbs))
    return resolved


def circular_mean(phases):
    z=np.mean(np.exp(2j*np.pi*np.asarray(phases)))
    if abs(z)<1e-6:raise ValueError('Phase observations are too dispersed for a meaningful circular mean')
    return float((np.angle(z)/(2*np.pi))%1)


def fit_gait_events(path: str | Path,bootstrap: int=1000,seed: int=0):
    """Fit contact frequencies and phases by specimen."""
    path=Path(path);rows=list(csv.DictReader(path.open(newline='')))
    if not rows:raise ValueError('Empty events table')
    if bootstrap<10:raise ValueError('At least ten bootstrap replicates required')
    grouped={};seen=set()
    for r in rows:
        sid=r['specimen_id'].strip();limb=r['limb'].strip();key=(sid,r['cycle_id'],limb)
        if not sid or not r['cycle_id']:raise ValueError('Known specimen and cycle identifiers required')
        if key in seen:raise ValueError('Duplicate specimen/cycle/limb; reconcile repeated annotations first')
        seen.add(key)
        t,l,n,o=[float(r[k]) for k in ['touchdown_s','liftoff_s','next_touchdown_s','cycle_origin_s']]
        if not np.isfinite([t,l,n,o]).all() or not t<l<n:raise ValueError('Require touchdown < liftoff < next touchdown')
        period=n-t;val=[1/period,(l-t)/period,((t-o)/period)%1]
        grouped.setdefault(limb,{}).setdefault(sid,[]).append(val)
    rng=np.random.default_rng(seed);out={}
    for limb,individuals in grouped.items():
        means=[]
        for vals in individuals.values():
            x=np.asarray(vals);means.append([x[:,0].mean(),x[:,1].mean(),circular_mean(x[:,2])])
        x=np.asarray(means);phase=circular_mean(x[:,2]);mean=x[:,:2].mean(0)
        intervals=None
        if len(x)>1:
            samples=x[rng.integers(0,len(x),size=(bootstrap,len(x))),:2].mean(1)
            intervals=np.quantile(samples,[.025,.975],axis=0).T.tolist()
        phase_disp=float(np.abs(np.exp(2j*np.pi*x[:,2]).mean()))
        out[limb]={'frequency_hz':float(mean[0]),'duty_factor':float(mean[1]),'touchdown_phase':phase,
                  'n_specimens':len(x),'n_cycles':sum(map(len,individuals.values())),
                  'frequency_duty_ci95':intervals,'phase_resultant_length':phase_disp}
    overrides={'frequency_hz':float(np.mean([v['frequency_hz'] for v in out.values()])),
               'duty_factor':float(np.mean([v['duty_factor'] for v in out.values()])),
               'touchdown_phases':{k:v['touchdown_phase'] for k,v in out.items()}}
    return {'schema':'wildlife-motion.gait-fit/1','limbs':out,'overrides':overrides,
            'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bootstrap_by':'specimen',
            'bootstrap_replicates':bootstrap,'seed':seed,
            'limitations':['User annotations are not automatically verified.','Shared duty/frequency overrides average limb estimates; inspect asymmetry before applying.',
                           'A single specimen cannot establish population uncertainty.']}


def fourier_design(times,frequency,harmonics):
    phase=2*np.pi*frequency*np.asarray(times)
    return np.column_stack([np.ones(len(phase))]+[fun(k*phase) for k in range(1,harmonics+1) for fun in (np.sin,np.cos)])


def fit_periodic_track(times,values,frequency_hz,confidence=None,harmonics=3):
    """Fit periodic coordinates or unwrapped joint angles."""
    t=np.asarray(times,float);v=np.asarray(values,float)
    if (not np.isfinite(frequency_hz) or frequency_hz<=0
            or not isinstance(harmonics,int) or harmonics<1 or harmonics>12):
        raise ValueError('Positive finite frequency and 1..12 integer harmonics required')
    if v.ndim==1:v=v[:,None]
    c=np.ones(len(t)) if confidence is None else np.asarray(confidence,float)
    if len(t)!=len(v) or len(c)!=len(t):raise ValueError('Mismatched track lengths')
    valid=np.isfinite(t)&np.isfinite(v).all(1)&np.isfinite(c)&(c>0)
    t,v,c=t[valid],v[valid],c[valid]
    if len(t)<2*harmonics+3:raise ValueError('Too few reliable observations for requested harmonics')
    X=fourier_design(t,frequency_hz,harmonics);w=np.sqrt(c)
    coeff,residual,rank,s=np.linalg.lstsq(X*w[:,None],v*w[:,None],rcond=None)
    if rank<X.shape[1]:raise ValueError('Motion samples do not constrain the requested periodic basis')
    error=X@coeff-v
    return {'schema':'wildlife-motion.periodic-track/1','frequency_hz':frequency_hz,'harmonics':harmonics,
            'coefficients':coeff.tolist(),'n_valid':len(t),'rmse':np.sqrt(np.mean(error**2,axis=0)).tolist(),
            'fit_status':'least_squares_user_observations_not_cross_validated'}


def evaluate_track(model,times):
    return fourier_design(np.atleast_1d(times),model['frequency_hz'],model['harmonics'])@np.asarray(model['coefficients'])
