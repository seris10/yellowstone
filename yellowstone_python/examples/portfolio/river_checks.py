"""Synthetic river verification and measured refinement errors."""
import argparse
import hashlib
import json
from pathlib import Path
from yellowstone_python.river.benchmarks import run_all_benchmarks


def main():
    """Run existing numerical checks and plot their actual refinement errors."""
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    if args.out.exists() and any(args.out.iterdir()):parser.error('output directory must be empty')
    report=run_all_benchmarks()
    second=run_all_benchmarks()
    report['repeatability_equal']=report==second
    report['fixture_class']='synthetic'
    report['forcing_scope']='Prescribed discharge, upstream temperature, geometry, and heat-exchange parameters in existing benchmark functions.'
    args.out.mkdir(parents=True,exist_ok=True)
    (args.out/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    row=next(x for x in report['results'] if x['name']=='mms_traveling_wave')
    fig,axs=plt.subplots(1,2,figsize=(10,4),layout='constrained')
    axs[0].loglog(row['n_cells'],row['spatial_errors_c'],'o-');axs[0].set(xlabel='Number of cells',ylabel='Temperature error (C)',title='Synthetic manufactured wave: spatial refinement')
    axs[1].loglog(row['dt_s'],row['temporal_errors_c'],'o-');axs[1].set(xlabel='Timestep (s)',ylabel='Temperature error (C)',title='Temporal refinement')
    fig.suptitle('Synthetic benchmark fixture | benchmark source SHA256 '+report['code_sha256'][:12], fontsize=10)
    fig.savefig(args.out/'refinement.png',dpi=160);plt.close(fig)
    print(json.dumps({'passed':report['passed'],'executed_checks':len(report['results']),'not_applicable':report['not_applicable'],'repeatability_equal':report['repeatability_equal']},indent=2))
    return 0 if report['passed'] and report['repeatability_equal'] else 1


if __name__=='__main__':raise SystemExit(main())
