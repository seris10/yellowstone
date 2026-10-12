"""Contract-level tests of new validator only; no recovered code or engine runs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import validate_manifest as vm
from jsonschema import Draft202012Validator


def example(name='representative_disconnected'):
    return vm.load_json(ROOT/'examples'/f'{name}.json')

def ref(document, ident, namespace='tests'):
    return {'world_id':document['world']['id'],'namespace':namespace,'id':ident}

def put_artifact(document, folder, name, role, payload=b'synthetic bytes only\n', authority='derived'):
    path=folder/name
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(payload)
    record={'ref':ref(document,name,'artifacts'),'role':role,'authority':authority,'availability':'verified_bytes',
            'uri':name,'uri_kind':'package_relative','sha256':hashlib.sha256(payload).hexdigest(),'byte_length':len(payload)}
    document['artifacts'].append(record)
    return record

def add_override(candidate, baseline, changes, status='accepted', operation='update'):
    target=baseline['interfaces']['placements'][0]
    record={'ref':ref(candidate,'override-one','overrides'),'target_ref':target['ref'],'status':status,'operation':operation,
            'base_world_revision':baseline['world']['revision'],'expected_target_hash':vm.record_hash(target),
            'hash_domain':'shared_record_v1','changes':changes,'reason':'Synthetic explicit reviewed change.'}
    candidate['interfaces'].setdefault('overrides',[]).append(record)
    return record

def make_streamable(folder):
    document=example()
    document['profile']='streamable'
    document['native_bindings']=[]
    document['artifacts']=[]
    for frame in document['coordinate_frames']:
        frame.pop('native_binding_ref',None)
    for placement in document['interfaces']['placements']:
        placement.pop('native_binding_ref',None)
    source=put_artifact(document,folder,'source.json','native_world',b'{"synthetic":true}\n','source_of_truth')
    payload=put_artifact(document,folder,'chunk.json','chunk_payload')
    collision=put_artifact(document,folder,'collision.json','collision_mesh')
    validation=put_artifact(document,folder,'validation.json','validation_report',b'{"scope":"synthetic test fixture, no engine execution"}\n')
    for chunk in document['interfaces']['chunks']:
        chunk.update(source_artifact_refs=[source['ref']],payload_artifact_ref=payload['ref'],
            collision_artifact_ref=collision['ref'],validation_artifact_ref=validation['ref'],readiness='validated')
    document['runtime'].update(status='ready',engine_target='synthetic packaging target; not an engine result',
        streaming={'chunk_size_m':64,'load_radius_chunks':1,'unload_radius_chunks':2,'minimum_collision_ahead_m':10,
          'commit_budget_ms':2,'maximum_background_jobs':2,'commit_policy':'cpu_workers_main_thread_commit',
          'stale_work_policy':'generation_token_discard','collision_activation_gate':True})
    return document

def externalize_placements(document, folder, name='placements.json'):
    placements=document['interfaces'].pop('placements')
    payload=json.dumps({'records':placements},allow_nan=False).encode()
    artifact=put_artifact(document,folder,name,'placement_catalog',payload)
    document['interfaces']['bindings']=[{'ref':ref(document,'external-placements','bindings'),'interface':'placements',
      'artifact_ref':artifact['ref'],'encoding':'json_array','records_json_pointer':'/records','record_definition':'placement','mode':'normalized_sidecar'}]
    return placements,artifact


class ManifestValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema=vm.load_json(ROOT/'world_manifest.schema.json')

    def result(self, document, **kwargs):
        return vm.validate_manifest(document,schema=self.schema,**kwargs)

    def assertValid(self, document, **kwargs):
        result=self.result(document,**kwargs)
        self.assertTrue(result['valid'],json.dumps(result['errors'],indent=2))
        return result

    def assertCode(self, code, document, **kwargs):
        result=self.result(document,**kwargs)
        self.assertFalse(result['valid'])
        self.assertIn(code,{error['code'] for error in result['errors']},result['errors'])
        return result

    def test_schema_is_draft202012_valid(self):
        Draft202012Validator.check_schema(self.schema)

    def test_all_shipped_examples(self):
        for path in (ROOT/'examples').glob('*.json'):
            with self.subTest(example=path.name): self.assertValid(vm.load_json(path))

    def test_duplicate_json_key_rejected(self):
        with self.assertRaises(vm.StrictJSONError): vm.strict_loads('{"world":1,"world":2}')

    def test_nonfinite_and_overflow_numbers_rejected(self):
        for text in ('NaN','Infinity','-Infinity','1e999','-1e999','{"x":1e999}'):
            with self.subTest(text=text),self.assertRaises(vm.StrictJSONError): vm.strict_loads(text)

    def test_programmatic_nonfinite_rejected(self):
        document=example(); document['world']['revision']=float('inf')
        self.assertCode('NONFINITE_NUMBER',document)

    def test_contract_version_drift_rejected(self):
        document=example(); document['contract_version']='0.2.0'
        self.assertCode('SCHEMA_VIOLATION',document)

    def test_unknown_core_fields_and_unscoped_extensions_rejected(self):
        document=example(); document['unsupported']=True
        self.assertCode('SCHEMA_VIOLATION',document)
        document=example(); document['extensions']={'unsupported':True}
        self.assertCode('SCHEMA_VIOLATION',document)

    def test_optional_schema_instance_hint(self):
        document=example(); document.pop('$schema')
        self.assertValid(document)

    def test_unknown_native_version_explicit(self):
        document=example('inventory_unknown'); self.assertValid(document)
        document['native_bindings'][0].pop('format_version_status')
        self.assertCode('SCHEMA_VIOLATION',document)

    def test_native_version_types_preserved(self):
        document=example(); document['native_bindings'][0]['format_version']='0.3.0'
        self.assertCode('NATIVE_VERSION',document)
        document=example(); binding=document['native_bindings'][0]
        binding.update(format='groundwork_material',format_version=1,position_space='material_local',scale_application='none')
        self.assertValid(document)
        binding['format_version']='1'
        self.assertCode('NATIVE_VERSION',document)

    def test_composite_duplicate_rejected_but_region_repeats_valid(self):
        document=example()
        self.assertEqual(document['interfaces']['placements'][0]['ref']['id'],document['interfaces']['placements'][1]['ref']['id'])
        self.assertValid(document)
        document['interfaces']['placements'][1]['ref']=deepcopy(document['interfaces']['placements'][0]['ref'])
        self.assertCode('DUPLICATE_ID',document)

    def test_dangling_reference_has_precise_path(self):
        document=example(); document['interfaces']['placements'][0]['frame_ref']['id']='missing'
        result=self.assertCode('DANGLING_REFERENCE',document)
        self.assertIn('/interfaces/placements/0/frame_ref',{e['path'] for e in result['errors']})

    def test_wrong_reference_interface_rejected(self):
        document=example(); document['interfaces']['placements'][0]['frame_ref']=document['artifacts'][0]['ref']
        self.assertCode('REFERENCE_TYPE',document)

    def test_grid_needs_n_plus_one_vertices(self):
        document=example('georeferenced'); document['interfaces']['terrain'][0]['grid']['sample_count']=[2,2]
        self.assertCode('GRID_SAMPLE_COUNT',document)

    def test_grid_bounds_and_spacing_agree(self):
        document=example('georeferenced'); document['interfaces']['terrain'][0]['grid']['bounds_xz']=[0,0,21,20]
        self.assertCode('GRID_BOUNDS_SPACING',document)
        document['interfaces']['terrain'][0]['grid']['bounds_xz']=[20,0,0,20]
        self.assertCode('INVALID_BOUNDS',document)

    def test_grid_raster_registration_separate(self):
        document=example('georeferenced')
        self.assertEqual(document['interfaces']['terrain'][0]['source_raster']['registration'],'pixel_areas')
        self.assertValid(document)
        document['interfaces']['terrain'][0]['grid']['registration']='pixel_areas'
        self.assertCode('SCHEMA_VIOLATION',document)

    def test_singular_source_affine_rejected(self):
        document=example('georeferenced'); document['interfaces']['terrain'][0]['source_raster']['affine_gdal']=[0,1,1,0,1,1]
        self.assertCode('SINGULAR_AFFINE',document)

    def test_finite_inputs_cannot_overflow_grid_witness(self):
        document=example('georeferenced'); document['interfaces']['terrain'][0]['grid']['spacing_m']=[1e308,1e308]
        document['interfaces']['terrain'][0]['source_raster']['affine_gdal']=[0,1e308,0,0,0,1e308]
        result=self.assertCode('GRID_NUMERIC_RANGE',document)
        self.assertIn('AFFINE_NUMERIC_RANGE',{e['code'] for e in result['errors']})
        json.dumps(result,allow_nan=False)

    def test_nodata_mask_required(self):
        document=example('georeferenced'); document['interfaces']['terrain'][0]['validity_mask_artifact_ref']=None
        self.assertCode('NODATA_MASK_REQUIRED',document)

    def test_material_microrelief_is_not_terrain_elevation(self):
        document=example('georeferenced'); terrain=document['interfaces']['terrain'][0]
        terrain['elevation_artifact_ref']=document['interfaces']['materials'][0]['height_master_artifact_ref']
        self.assertCode('MATERIAL_HEIGHT_IS_NOT_TERRAIN',document)

    def test_ir_transform_double_compression_guards(self):
        document=example(); document['native_bindings'][0]['scale_application']='apply_on_view'
        self.assertCode('IR_DOUBLE_COMPRESSION',document)
        document=example(); document['interfaces']['placements'][0]['scale_application']='source_to_view_pending'
        self.assertCode('DOUBLE_COMPRESSION',document)

    def test_fictional_authored_frame_needs_no_compression_ratio(self):
        document=example(); self.assertNotIn('scale_mappings',document['coordinate_frames'][2]['representation'])
        self.assertValid(document)

    def test_unlocated_habitat_null_is_not_zero(self):
        document=example(); habitat=document['interfaces']['habitats'][0]
        self.assertIsNone(habitat['center']); self.assertValid(document)
        habitat['center']=[0,0,0]
        self.assertCode('SCHEMA_VIOLATION',document)

    def test_georeferencing_is_no_accuracy_claim(self):
        document=example('georeferenced')
        self.assertIsNone(document['coordinate_frames'][0]['georeference']['operation']['accuracy_m'])
        self.assertValid(document)
        document['coordinate_frames'][0]['georeference']['operation']['method']='affine_approximation'
        self.assertCode('GEOGRAPHIC_MODE_OVERCLAIM',document)

    def test_physical_model_rejects_compressed_distance(self):
        document=example(); document['models'][0]['space']='physical'
        self.assertCode('MODEL_SPACE_MISMATCH',document)

    def test_observed_species_needs_evidence(self):
        document=example('georeferenced'); document['interfaces']['species'][0]['occurrence_evidence']='observed'
        self.assertCode('OBSERVATION_WITHOUT_EVIDENCE',document)

    def test_chunk_dependency_cycle_reports_witness(self):
        document=example(); a,b=document['interfaces']['chunks']; a['dependencies']=[b['ref']]; b['dependencies']=[a['ref']]
        result=self.assertCode('CHUNK_CYCLE',document)
        error=next(e for e in result['errors'] if e['code']=='CHUNK_CYCLE')
        self.assertEqual(error['witness']['cycle'][0],error['witness']['cycle'][-1])

    def test_frame_parent_cycle_rejected(self):
        document=example(); a,b=document['coordinate_frames'][:2]; a['parent_frame_ref']=b['ref']; b['parent_frame_ref']=a['ref']
        self.assertCode('FRAME_CYCLE',document)

    def test_water_reversible_cycle_allowed(self):
        document=example('georeferenced'); a=document['interfaces']['water'][0]; b=deepcopy(a); b['ref']=ref(document,'tide-channel','water'); b['state_ref']=None
        a['connections']=[{'water_ref':b['ref'],'flow':'reversible'}]; b['connections']=[{'water_ref':a['ref'],'flow':'reversible'}]
        document['interfaces']['water'].append(b)
        self.assertValid(document)

    def test_road_width_is_positive_full_width(self):
        document=example('georeferenced'); document['interfaces']['roads'][0]['full_width_m']=0
        self.assertCode('SCHEMA_VIOLATION',document)

    def test_stale_proposed_override_hash_and_revision(self):
        document=example(); override=add_override(document,document,{'position':[2,3,4]},status='proposed')
        self.assertValid(document)
        override['expected_target_hash']='0'*64
        self.assertCode('STALE_OVERRIDE_HASH',document)
        override['base_world_revision']=999
        self.assertCode('STALE_OVERRIDE_REVISION',document)

    def test_locked_proposed_override_rejected(self):
        document=example(); document['interfaces']['placements'][0]['locked']=True
        add_override(document,document,{'position':[2,3,4]},status='proposed')
        self.assertCode('LOCKED_OVERRIDE',document)

    def test_native_hash_never_recalculated_as_shared_hash(self):
        document=example(); override=add_override(document,document,{'position':[2,3,4]},status='proposed')
        override.update(hash_domain='native_opaque',expected_target_hash='0'*64)
        result=self.assertValid(document)
        self.assertIn('NATIVE_HASH_NOT_RECOMPUTED',{e['code'] for e in result['warnings']})

    def test_baseline_coordinate_mode_change_rejected(self):
        baseline=example(); candidate=deepcopy(baseline); frame=candidate['coordinate_frames'][0]
        frame['geography_mode']='unknown'; frame.pop('representation')
        self.assertCode('FRAME_DRIFT',candidate,baseline=baseline)

    def test_baseline_accepted_id_removal_rejected(self):
        baseline=example(); candidate=deepcopy(baseline); candidate['interfaces']['placements'].pop(0)
        candidate['interfaces']['chunks'][0]['placement_refs']=[]
        self.assertCode('ACCEPTED_ID_REMOVED',candidate,baseline=baseline)

    def test_baseline_locked_edit_rejected(self):
        baseline=example(); baseline['interfaces']['placements'][0]['locked']=True
        candidate=deepcopy(baseline); candidate['world']['revision']+=1; candidate['interfaces']['placements'][0]['position']=[1,2,3]
        add_override(candidate,baseline,{'position':[1,2,3]})
        self.assertCode('LOCKED_PLACEMENT_CHANGED',candidate,baseline=baseline)

    def test_baseline_unlocked_change_needs_exact_override(self):
        baseline=example(); candidate=deepcopy(baseline); candidate['world']['revision']+=1
        candidate['interfaces']['placements'][0]['position']=[1,2,3]
        self.assertCode('ACCEPTED_CHANGE_WITHOUT_OVERRIDE',candidate,baseline=baseline)
        override=add_override(candidate,baseline,{'position':[1,2,3]})
        self.assertValid(candidate,baseline=baseline)
        override['changes']['position']=[3,2,1]
        self.assertCode('OVERRIDE_DIFF_MISMATCH',candidate,baseline=baseline)

    def test_baseline_accepted_change_requires_new_revision(self):
        baseline=example(); candidate=deepcopy(baseline); candidate['interfaces']['placements'][0]['position']=[1,2,3]
        add_override(candidate,baseline,{'position':[1,2,3]})
        self.assertCode('REVISION_NOT_ADVANCED',candidate,baseline=baseline)

    def test_baseline_override_hash_must_match_baseline(self):
        baseline=example(); candidate=deepcopy(baseline); candidate['world']['revision']+=1
        candidate['interfaces']['placements'][0]['position']=[1,2,3]
        override=add_override(candidate,baseline,{'position':[1,2,3]}); override['expected_target_hash']='f'*64
        self.assertCode('STALE_OVERRIDE_HASH',candidate,baseline=baseline)

    def test_baseline_ambiguous_override_rejected(self):
        baseline=example(); candidate=deepcopy(baseline); candidate['world']['revision']+=1; candidate['interfaces']['placements'][0]['position']=[1,2,3]
        override=add_override(candidate,baseline,{'position':[1,2,3]}); other=deepcopy(override); other['ref']=ref(candidate,'override-two','overrides')
        candidate['interfaces']['overrides'].append(other)
        self.assertCode('AMBIGUOUS_OVERRIDE',candidate,baseline=baseline)

    def test_suppression_retains_accepted_id(self):
        baseline=example(); candidate=deepcopy(baseline); candidate['world']['revision']+=1; candidate['interfaces']['placements'][0]['suppressed']=True
        add_override(candidate,baseline,{'suppressed':True},operation='suppress')
        self.assertValid(candidate,baseline=baseline)
        self.assertEqual(baseline['interfaces']['placements'][0]['ref'],candidate['interfaces']['placements'][0]['ref'])

    def test_baseline_source_hash_and_native_locator_retained(self):
        baseline=example(); baseline['artifacts'][0].update(sha256='a'*64,byte_length=1)
        candidate=deepcopy(baseline); candidate['artifacts'][0]['sha256']='b'*64
        self.assertCode('SOURCE_ARTIFACT_DRIFT',candidate,baseline=baseline)
        candidate=deepcopy(baseline); candidate['interfaces']['placements'][0].pop('native_binding_ref')
        self.assertCode('PLACEMENT_PROVENANCE_DRIFT',candidate,baseline=baseline)

    def test_native_binding_cannot_be_retargeted_under_same_identity(self):
        baseline=example(); candidate=deepcopy(baseline)
        other=deepcopy(candidate['artifacts'][0]); other['ref']=ref(candidate,'other-native','artifacts'); candidate['artifacts'].append(other)
        candidate['native_bindings'][0]['artifact_ref']=other['ref']
        self.assertCode('NATIVE_BINDING_DRIFT',candidate,baseline=baseline)

    def test_provenance_content_cannot_change_under_same_identity(self):
        baseline=example('georeferenced'); candidate=deepcopy(baseline)
        candidate['provenance']['sources'][0]['title']='Rewritten historical evidence'
        self.assertCode('PROVENANCE_RECORD_DRIFT',candidate,baseline=baseline)
        candidate=deepcopy(baseline); candidate['provenance']['licenses'][0]['identifier']='A different license claim'
        self.assertCode('PROVENANCE_RECORD_DRIFT',candidate,baseline=baseline)

    def test_frozen_incumbent_is_preserved_without_inventing_acceptance(self):
        baseline=example(); baseline['interfaces']['placements'][0]['status']='frozen_incumbent'
        self.assertValid(baseline)
        candidate=deepcopy(baseline); candidate['world']['revision']+=1; candidate['interfaces']['placements'][0]['position']=[1,2,3]
        self.assertCode('ACCEPTED_CHANGE_WITHOUT_OVERRIDE',candidate,baseline=baseline)

    def test_placement_fidelity_and_unknown_metadata_preserved(self):
        baseline=example(); baseline['interfaces']['placements'][0]['extensions']={'native:unknown-field':{'a':1}}
        for field,value in (('fidelity','survey_control'),('extensions',{})):
            with self.subTest(field=field):
                candidate=deepcopy(baseline); candidate['interfaces']['placements'][0][field]=value
                self.assertCode('ACCEPTED_CHANGE_WITHOUT_OVERRIDE',candidate,baseline=baseline)

    def test_lock_protects_candidate_and_rejected_placements(self):
        for status in ('candidate','rejected'):
            with self.subTest(status=status):
                baseline=example(); placement=baseline['interfaces']['placements'][0]; placement.update(status=status,locked=True)
                candidate=deepcopy(baseline); candidate['world']['revision']+=1; candidate['interfaces']['placements'][0]['position']=[1,2,3]
                self.assertCode('LOCKED_PLACEMENT_CHANGED',candidate,baseline=baseline)

    def test_json_pointer_does_not_alias_array_indices_or_escapes(self):
        value={'items':['a','b'],'slash/key':{'tilde~key':7},'01':'literal object key'}
        self.assertEqual(vm.json_at_pointer(value,'/items/1'),'b')
        self.assertEqual(vm.json_at_pointer(value,'/slash~1key/tilde~0key'),7)
        self.assertEqual(vm.json_at_pointer(value,'/01'),'literal object key')
        for path in ('/items/-1','/items/+1','/items/01','/items/-','/slash~2key','/trailing~','items/1'):
            with self.subTest(path=path),self.assertRaises(ValueError): vm.json_at_pointer(value,path)

    def test_file_hash_and_size_rechecked(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); document=example('inventory_unknown'); a=put_artifact(document,folder,'fixture.bin','other')
            result=self.assertValid(document,artifact_root=folder,check_files=True)
            self.assertEqual(result['summary']['artifacts_rechecked'],1)
            (folder/'fixture.bin').write_bytes(b'changed')
            self.assertCode('ARTIFACT_INTEGRITY',document,artifact_root=folder,check_files=True)

    def test_recorded_hash_claim_not_asserted_reread(self):
        document=example('inventory_unknown'); document['artifacts'][0].update(availability='verified_bytes',uri='absent.zip',uri_kind='package_relative',sha256='a'*64,byte_length=1)
        result=self.assertValid(document)
        self.assertEqual(result['summary']['artifacts_rechecked'],0)
        self.assertIn('ARTIFACT_BYTES_NOT_RECHECKED',{w['code'] for w in result['warnings']})

    def test_package_path_and_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            outer=Path(tmp); folder=outer/'package'; folder.mkdir(); (outer/'outside.bin').write_bytes(b'outside')
            document=example('inventory_unknown'); a=put_artifact(document,folder,'inside.bin','other',b'outside')
            a['uri']='../outside.bin'; self.assertCode('ARTIFACT_UNAVAILABLE',document,artifact_root=folder,check_files=True)
            (folder/'escape.bin').symlink_to(outer/'outside.bin'); a['uri']='escape.bin'
            self.assertCode('ARTIFACT_UNAVAILABLE',document,artifact_root=folder,check_files=True)

    def test_remote_uri_not_fetched(self):
        document=example('inventory_unknown'); document['artifacts'][0].update(availability='verified_bytes',uri='https://example.invalid/data.zip',uri_kind='remote_url',sha256='a'*64,byte_length=1)
        self.assertCode('ARTIFACT_UNAVAILABLE',document,check_files=True)

    def test_sidecar_records_structured_resolved_and_counted(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); document=example(); externalize_placements(document,folder)
            result=self.assertValid(document,artifact_root=folder,check_files=True)
            self.assertEqual(result['summary']['sidecar_records_checked'],2)
            self.assertEqual(result['summary']['sidecar_bindings_unopened'],0)

    def test_sidecar_not_opened_cannot_resolve_feature_refs(self):
        with tempfile.TemporaryDirectory() as tmp:
            document=example(); externalize_placements(document,Path(tmp))
            result=self.assertCode('DANGLING_REFERENCE',document)
            self.assertIn('SIDECAR_NOT_OPENED',{w['code'] for w in result['warnings']})

    def test_sidecar_bad_record_cannot_claim_verified_interface(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); document=example(); placements,artifact=externalize_placements(document,folder)
            placements[0]['position']='bad'; payload=json.dumps({'records':placements}).encode(); (folder/artifact['uri']).write_bytes(payload)
            artifact.update(sha256=hashlib.sha256(payload).hexdigest(),byte_length=len(payload))
            self.assertCode('SCHEMA_VIOLATION',document,artifact_root=folder,check_files=True)

    def test_duplicate_sidecar_and_inline_id_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); document=example(); placements,_=externalize_placements(document,folder)
            document['interfaces']['placements']=[placements[0]]
            self.assertCode('DUPLICATE_ID',document,artifact_root=folder,check_files=True)

    def test_baseline_sidecar_changes_actually_compared(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); original=example(); baseline=deepcopy(original); externalize_placements(baseline,folder,'base.json')
            candidate=deepcopy(original); candidate['world']['revision']+=1; candidate['interfaces']['placements'][0]['position']=[1,2,3]
            add_override(candidate,original,{'position':[1,2,3]}); externalize_placements(candidate,folder,'candidate.json')
            result=self.assertValid(candidate,baseline=baseline,check_files=True,artifact_root=folder)
            self.assertTrue(result['summary']['baseline_checked']); self.assertEqual(result['summary']['baseline_sidecar_records_checked'],2)
            candidate['interfaces']['overrides'][0]['changes']['position']=[9,9,9]
            self.assertCode('OVERRIDE_DIFF_MISMATCH',candidate,baseline=baseline,check_files=True,artifact_root=folder)

    def test_opaque_baseline_refuses_preservation_claim(self):
        baseline=example(); baseline['interfaces']['bindings']=[{'ref':ref(baseline,'opaque','bindings'),'interface':'placements',
          'artifact_ref':baseline['artifacts'][0]['ref'],'encoding':'native_unparsed','records_json_pointer':'','record_definition':'placement','mode':'read_only_native'}]
        self.assertCode('BASELINE_RECORDS_UNINSPECTED',deepcopy(baseline),baseline=baseline)

    def test_synthetic_streamable_fixture_requires_actual_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); document=make_streamable(folder)
            self.assertCode('STREAMABLE_FILES_REQUIRED',document)
            result=self.assertValid(document,artifact_root=folder,check_files=True)
            self.assertEqual(result['summary']['artifacts_rechecked'],4)
            self.assertFalse(result['summary']['runtime_executed'])
            self.assertFalse(result['summary']['scientific_models_executed'])

    def test_streamable_needs_readiness_sources_and_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); document=make_streamable(folder); chunk=document['interfaces']['chunks'][0]
            chunk.update(readiness='planned',source_artifact_refs=[],payload_artifact_ref=None)
            result=self.assertCode('CHUNK_NOT_READY',document,artifact_root=folder,check_files=True)
            self.assertTrue({'CHUNK_SOURCE_REQUIRED','CHUNK_ARTIFACT_NOT_VERIFIED'}.issubset({e['code'] for e in result['errors']}))

    def test_streamable_hysteresis_and_feature_frame(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); document=make_streamable(folder); document['runtime']['streaming']['unload_radius_chunks']=1
            self.assertCode('STREAM_HYSTERESIS',document,artifact_root=folder,check_files=True)
            document['runtime']['streaming']['unload_radius_chunks']=2
            document['interfaces']['chunks'][0]['placement_refs']=[document['interfaces']['placements'][1]['ref']]
            self.assertCode('CHUNK_FEATURE_FRAME',document,artifact_root=folder,check_files=True)

    def test_streamable_opaque_or_unverified_sidecar_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp); document=make_streamable(folder); _,artifact=externalize_placements(document,folder)
            self.assertValid(document,artifact_root=folder,check_files=True)
            artifact['availability']='metadata_only'
            self.assertCode('STREAMABLE_BINDING_UNVERIFIED',document,artifact_root=folder,check_files=True)
            document['interfaces']['bindings'][0]['encoding']='native_unparsed'
            self.assertCode('STREAMABLE_OPAQUE_BINDING',document,artifact_root=folder,check_files=True)

    def test_cli_emits_structured_parse_error_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'bad.json'; path.write_text('{"x":1,"x":2}')
            process=subprocess.run([sys.executable,str(ROOT/'tools/validate_manifest.py'),str(path)],capture_output=True,text=True)
            result=json.loads(process.stdout)
            self.assertEqual(process.returncode,1); self.assertFalse(result['valid'])
            self.assertEqual(result['errors'][0]['code'],'INPUT_OR_DEPENDENCY_ERROR')


if __name__=='__main__': unittest.main()
