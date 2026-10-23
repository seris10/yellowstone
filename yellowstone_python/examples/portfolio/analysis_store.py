"""Synthetic source-to-SQL demonstration with independent JSON reference checks."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
from yellowstone_python.service import analysis_store as store


def fixture():
    """Return small authored inputs with boundary points and missing observations."""
    trees=[dict(stable_id=name,x=x,z=z,crown_r_m=1.,confidence='high',peak_exg=.2,evidence_class='synthetic') for name,x,z in [('edge',0.,0.),('corner',10.,10.),('middle',5.,5.),('outside',10.01,5.)]]
    cells=[dict(id='cell_A',river_id='synthetic',center_s_m=5.,start_s_m=0.,end_s_m=10.,length_m=10.,width_m=2.,depth_m=1.,volume_m3=20.,hydraulics={'velocity_continuity_m_s':.5})]
    return dict(census={'schema':'yellowstone.canopy_census.v1','trees':trees},replay={'cells':cells,'frames':[{'t_s':t,'temperature_c':[15+t/10]} for t in (0.,10.,20.)]},firehole={'schema':'yellowstone.firehole_obs.v1','sites':{'synthetic':{'series':{'discharge_m3_s':[[1000.,1.5]],'temperature_c':[[1000.,None]]}}}},snotel={'schema':'yellowstone.snotel_obs.v1','sites':{'synthetic':{'days':{'2026-01-01':{'WTEQ':1.,'PRCP':.5,'SNWD':2.,'TAVG':32.,'TMAX':50.,'TMIN':14.},'2026-01-02':{'WTEQ':None,'PRCP':None,'SNWD':None,'TAVG':None,'TMAX':None,'TMIN':None}}}}})


def main():
    """Build a new SQLite store and compare four queries with raw JSON."""
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):parser.error('output directory must be empty')
    data=fixture();raw=(json.dumps(data,indent=2)+'\n').encode();identity=hashlib.sha256(raw).hexdigest()
    con=store.build_con(build_id='synthetic-portfolio',**data,source_shas={'fixture.json':identity},notes='All inputs synthetic; no measured park observations')
    bbox=store.query(con,'census_trees',columns=['stable_id'],x0=0,x1=10,z0=0,z1=10)
    expected_bbox=sorted(t['stable_id'] for t in data['census']['trees'] if 0<=t['x']<=10 and 0<=t['z']<=10)
    interval=store.query(con,'replay_frames',columns=['t_s','cell_id','temperature_c'],cell_id='cell_A',t0=10,t1=20)
    expected_interval=[[f['t_s'],'cell_A',f['temperature_c'][0]] for f in data['replay']['frames'] if 10<=f['t_s']<=20]
    missing=con.execute('SELECT COUNT(*) FROM obs_snotel WHERE wteq_mm IS NULL').fetchone()[0]
    expected_missing=sum(d['WTEQ'] is None for d in data['snotel']['sites']['synthetic']['days'].values())
    converted=con.execute("SELECT wteq_mm,tavg_c FROM obs_snotel WHERE day='2026-01-01'").fetchone()
    raw_day=data['snotel']['sites']['synthetic']['days']['2026-01-01'];expected_converted=[raw_day['WTEQ']*25.4,(raw_day['TAVG']-32)*5/9]
    checks={'inclusive_bbox':sorted(r[0] for r in bbox['rows'])==expected_bbox,'time_cell_grain':sorted(map(list,interval['rows']))==expected_interval,'null_retention':missing==expected_missing,'inch_fahrenheit_conversion':list(converted)==expected_converted}
    result=dict(fixture_class='synthetic',fixture_sha256=identity,grain='one row per (time_s, cell_id)',queries={'inclusive_bbox':bbox,'cell_time_interval':interval,'missing_snow_observation_count':missing,'converted_snow_and_temperature':dict(wteq_mm=converted[0],tavg_c=converted[1])},reference_checks=checks,passed=all(checks.values()))
    args.out.mkdir(parents=True,exist_ok=True);(args.out/'fixture.json').write_bytes(raw)
    disk=sqlite3.connect(args.out/'analysis.sqlite');con.backup(disk);disk.close();con.close()
    (args.out/'results.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps(result,indent=2));return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
