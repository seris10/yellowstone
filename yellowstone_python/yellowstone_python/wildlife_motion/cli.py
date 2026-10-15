"""Wildlife motion commands."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import numpy as np
from .core import AssetError
from .gltf import load_asset,export_asset,read_glb,accessor
from .species import get_profile,all_profiles
from .rigging import prepare,make_weights
from .mammals import MammalEngine,register_sole_offsets
from .birds import BirdEngine


def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,allow_nan=False))


def read_json(path):return json.loads(Path(path).read_text()) if path else None


def fit(args,expected=None):
    profile=get_profile(args.species)
    if expected and profile['engine']!=expected:raise AssetError(f'Use the {profile["engine"]} application for this species')
    asset=load_asset(args.input)
    asset,sk=prepare(asset,profile,read_json(args.rig),forward=args.forward,up=args.up,
        align_heading=not args.no_align_heading,length_m=args.length_m,wing_state=args.wing_state)
    return asset,sk,profile


def add_asset_args(parser):
    parser.add_argument('input',type=Path,help='Original, unskinned GLB; never overwritten')
    parser.add_argument('--species',required=True)
    parser.add_argument('--rig',type=Path,help='Reviewed rig JSON bound to this source SHA256')
    parser.add_argument('--forward',default='+z',choices=['+x','-x','+y','-y','+z','-z'])
    parser.add_argument('--up',default='+y',choices=['+x','-x','+y','-y','+z','-z'])
    parser.add_argument('--no-align-heading',action='store_true')
    parser.add_argument('--length-m',type=float,help='Independently known canonical bbox length; NOT an automatic animal size estimate')
    parser.add_argument('--wing-state',choices=['unknown','folded','spread'],default='unknown')


def parser():
    p=argparse.ArgumentParser(description='CPU-first, inspectable wildlife animation and measured-data interfaces')
    p.add_argument('--version',action='version',version='0.1.0')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('profiles',help='List species, supported actions and evidence status')
    a=sub.add_parser('inspect',help='Prepare editable landmarks and an offline review page');add_asset_args(a)
    a.add_argument('--outdir',type=Path,required=True)
    a=sub.add_parser('animate',help='Rig and bake species-specific motion clips into a GLB');add_asset_args(a)
    a.add_argument('--output','-o',type=Path,required=True)
    a.add_argument('--modes',help='Comma-separated case-sensitive actions, e.g. Idle,Walk,Trot')
    a.add_argument('--fps',type=int,default=30);a.add_argument('--cycles',type=int,default=2)
    a.add_argument('--controls',type=Path,help='JSON of engine controls or gait-fit overrides')
    a.add_argument('--root-motion',action='store_true',help='Translate walking root; exported clip will not loop')
    a.add_argument('--texture-max',type=int,help='Optional texture downsampling; omit to preserve source texture bytes')
    a.add_argument('--preview',type=Path,help='Optional MP4, requires [preview] dependencies')
    a.add_argument('--validate-motion',action='store_true',help='Write numerical skin/IK report, not a biological score')
    a=sub.add_parser('diversify',help='Produce within-asset variants, with rig regenerated for each');add_asset_args(a)
    a.add_argument('--outdir',type=Path,required=True);a.add_argument('--count',type=int,default=3)
    a.add_argument('--seed',type=int,default=0);a.add_argument('--strength',type=float,default=.5)
    group=a.add_mutually_exclusive_group(required=True)
    group.add_argument('--artistic',action='store_true',help='Explicitly authorize non-empirical randomized variation')
    group.add_argument('--population-model',type=Path,help='Fit to a documented same-reference factor dataset')
    group.add_argument('--config',type=Path,help='Explicit Variant JSON controls')
    a.add_argument('--texture-max',type=int,default=2048);a.add_argument('--modes',default='Idle,Walk')
    a=sub.add_parser('population-fit',help='Fit correlated relative factors, grouped by individual')
    a.add_argument('input',type=Path);a.add_argument('--output',type=Path,required=True)
    a.add_argument('--qualifiers',type=Path,help='JSON exact-match filters, e.g. sex/life_stage/population')
    a.add_argument('--base-reference',type=Path,help='Species and exact source asset SHA256; required before population-based export')
    a=sub.add_parser('calibrate',help='Fit gait frequency, duty and phase from annotated contact events')
    a.add_argument('input',type=Path);a.add_argument('--output',type=Path,required=True)
    a.add_argument('--bootstrap',type=int,default=1000);a.add_argument('--seed',type=int,default=0)
    a=sub.add_parser('water',help='Run SI-unit buoyancy/drag/paddle surface-swimming prototype')
    a.add_argument('--config',type=Path);a.add_argument('--output',type=Path,required=True)
    a.add_argument('--duration',type=float,default=8.);a.add_argument('--fps',type=int,default=60)
    a=sub.add_parser('fixtures',help='Write original synthetic bird sources and animated test assets')
    a.add_argument('--outdir',type=Path,required=True)
    a=sub.add_parser('validate',help='Independently sample serialized skinning channels in an exported GLB')
    a.add_argument('input',type=Path);a.add_argument('--output',type=Path)
    return p


def main(argv=None,expected_engine=None):
    p=parser();args=p.parse_args(argv)
    try:
        if args.command=='profiles':
            for key,profile in all_profiles().items():
                if expected_engine and profile['engine']!=expected_engine:continue
                print(f'{key:20} {profile["taxon"]:30} {", ".join(profile["gaits"])}')
            print('\nNumeric defaults are authored controls. They are not measured species distributions.')
        elif args.command=='inspect':
            from .review import write_review
            asset,sk,profile=fit(args,expected_engine);args.outdir.mkdir(parents=True,exist_ok=True)
            name=profile['id'];dump(args.outdir/(name+'.rig.json'),sk.to_dict())
            write_review(asset,sk,args.outdir/(name+'_landmarks.html'))
            dump(args.outdir/(name+'_inspection.json'),{'source_sha256':asset.source_sha256,'vertices':len(asset.vertices),
                 'triangles':len(asset.faces),'bbox':np.array([asset.vertices.min(0),asset.vertices.max(0)]).tolist(),
                 'review_status':sk.metadata['review_status'],'scale_status':sk.metadata['scale_status']})
            print(f'Prepared {name}. Open {args.outdir/(name+"_landmarks.html")} locally and inspect the joints.')
        elif args.command=='animate':
            from .validation import validate_motion
            if args.input.resolve()==args.output.resolve():raise AssetError('Output must differ from the original source file')
            asset,sk,profile=fit(args,expected_engine);j,w,wr=make_weights(asset.vertices,asset.faces,sk)
            register_sole_offsets(asset.vertices,j,w,sk)
            engine=(MammalEngine if profile['engine']=='mammal' else BirdEngine)(sk,profile)
            controls=read_json(args.controls)
            control_source=None
            if args.controls:
                import hashlib
                control_source={'filename':args.controls.name,'sha256':hashlib.sha256(args.controls.read_bytes()).hexdigest(),
                                'evidence_status':'user_supplied_controls_not_independently_validated',
                                'schema':controls.get('schema','unversioned_controls')}
            if controls and 'overrides' in controls:controls=controls['overrides']
            modes=args.modes.split(',') if args.modes else None
            clips=engine.clips(modes,args.fps,args.cycles,controls,args.root_motion)
            if control_source:
                for clip in clips:clip.metadata['control_source']=control_source
            args.output.parent.mkdir(parents=True,exist_ok=True)
            meta=export_asset(asset,args.output,sk,j,w,clips,args.texture_max)
            dump(args.output.with_suffix('.weights.json'),wr)
            if args.validate_motion:
                # Pass the exact controls used for export into numerical checks.
                import copy
                checked=copy.deepcopy(profile)
                if controls:
                    for mode in modes or [c.name for c in clips]:checked['gaits'][mode].update(controls)
                checker=type(engine)(sk,checked)
                dump(args.output.with_suffix('.validation.json'),validate_motion(asset,sk,j,w,checker,modes or [c.name for c in clips]))
            if args.preview:
                from .preview import render_video
                mode=next((c.name for c in clips if c.name not in ('Idle','Float')),clips[0].name)
                render_video(asset,sk,j,w,lambda t:engine.pose(t,mode,controls,args.root_motion),args.preview,
                    title=profile['common_name']+' / '+mode,follow_root=args.root_motion,
                    ground=mode not in ('Flight','Glide'))
            print(f'Wrote {args.output}: {len(sk.names)} joints; clips {", ".join(c.name for c in clips)}')
            print(f'Landmarks: {sk.metadata["review_status"]}. Scale: {sk.metadata["scale_status"]}. Inspect shoulder/hip skinning.')
        elif args.command=='diversify':
            from .asset_audit import audit_asset
            from .validation import validate_motion
            from .variation import sample_artistic,sample_population,diversify,Variant
            if not 1<=args.count<=100:raise ValueError('Variant count must be in [1,100]')
            asset,sk,profile=fit(args,expected_engine);args.outdir.mkdir(parents=True,exist_ok=True)
            population=read_json(args.population_model);config=read_json(args.config)
            for i in range(args.count):
                seed=args.seed+i
                cfg=Variant(**config) if config else sample_population(population,seed) if population else sample_artistic(seed,args.strength)
                va,vs=diversify(asset,sk,cfg);j,w,_=make_weights(va.vertices,va.faces,vs);register_sole_offsets(va.vertices,j,w,vs)
                engine=(MammalEngine if profile['engine']=='mammal' else BirdEngine)(vs,profile)
                out=args.outdir/f'{profile["id"]}_variant_{i:02}.glb'
                export_asset(va,out,vs,j,w,engine.clips(args.modes.split(',')),args.texture_max)
                validation=validate_motion(va,vs,j,w,engine,args.modes.split(','))
                audit=audit_asset(out)
                dump(out.with_suffix('.validation.json'),{'asset_sha256':audit['sha256'],
                    'population_lineage':cfg.population_lineage,'deformation':validation,'serialized':audit,
                    'visual_acceptance':'unassessed','biological_acceptance':'not_yet_accepted'})
                print(out)
        elif args.command=='population-fit':
            from .variation import fit_population
            dump(args.output,fit_population(args.input,read_json(args.qualifiers),base_reference=read_json(args.base_reference)))
            print(args.output)
        elif args.command=='calibrate':
            from .calibration import fit_gait_events
            dump(args.output,fit_gait_events(args.input,args.bootstrap,args.seed));print(args.output)
        elif args.command=='water':
            from .water import WaterConfig,simulate,save_simulation
            c=WaterConfig(**(read_json(args.config) or {}));result=simulate(c,args.duration,args.fps)
            save_simulation(result,args.output);print(f'Wrote {args.output}. Surface surrogate, not species-calibrated CFD.')
        elif args.command=='fixtures':
            from .synthetic import bird_proxy
            args.outdir.mkdir(parents=True,exist_ok=True)
            for spread in (False,True):
                asset,sk,j,w=bird_proxy(spread);tag='spread' if spread else 'folded'
                src=args.outdir/f'synthetic_bird_{tag}_source.glb';export_asset(asset,src)
                # Bind exported source hash for subsequent user CLI runs.
                imported=load_asset(src);sk.metadata['source_sha256']=imported.source_sha256
                imported.metadata['scale_status']='synthetic_fixture_meters'
                dump(args.outdir/f'synthetic_bird_{tag}.rig.json',sk.to_dict())
                register_sole_offsets(imported.vertices,j,w,sk)
                e=BirdEngine(sk,get_profile('mallard'))
                modes=['Flight','Glide'] if spread else ['Idle','Walk','Float','Paddle']
                export_asset(imported,args.outdir/f'synthetic_bird_{tag}_animated.glb',sk,j,w,e.clips(modes))
            print(f'Wrote original synthetic engineering proxies to {args.outdir}; these are not biological reference models.')
        elif args.command=='validate':
            from .asset_audit import audit_asset
            report={'schema':'wildlife-motion.serialized-check/1','animations':[],
                    'passed':False,'required_checks':{'geometry_skin_and_clips':'unavailable'}}
            try:
                audit=audit_asset(args.input)
                if not audit['skins'] or not audit['clips'] or not audit['triangles']:
                    raise AssetError('Expected nonempty animated, skinned geometry')
                report['animations']=[{'name':clip['name'],'sampled_finite':clip['sampled_finite']} for clip in audit['clips']]
                report['audit']=audit
                report['passed']=all(clip['sampled_finite'] for clip in audit['clips'])
                report['required_checks']['geometry_skin_and_clips']='passed' if report['passed'] else 'failed'
            except (AssetError,ValueError,KeyError,OSError,RuntimeError,IndexError,TypeError) as error:
                report['error']=str(error)
                report['required_checks']['geometry_skin_and_clips']='failed'
            report['status']='numerically_checked' if report['passed'] else 'failed'
            report['note']='Use the official Khronos glTF Validator for complete format conformance checks.'
            if args.output:dump(args.output,report)
            print(json.dumps(report,indent=2))
            return 0 if report['passed'] else 2
    except (AssetError,ValueError,KeyError,OSError,RuntimeError) as e:
        p.exit(2,f'Error: {e}\n')
    return 0


def mammals_main():return main(expected_engine='mammal')
def birds_main():return main(expected_engine='bird')
