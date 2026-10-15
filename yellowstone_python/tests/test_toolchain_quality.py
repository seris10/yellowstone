"""Toolchain controls cross calibration, serialization and physical domains."""
import copy
import json
import struct
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest

from yellowstone_python.wildlife_motion.birds import BirdEngine
from yellowstone_python.wildlife_motion.cli import main
from yellowstone_python.wildlife_motion.gltf import accessor, export_asset, read_glb, write_glb
from yellowstone_python.wildlife_motion.species import get_profile
from yellowstone_python.wildlife_motion.synthetic import bird_proxy
from yellowstone_python.wildlife_motion.validation import imported_skin
from yellowstone_python.wildlife_motion.water import WaterConfig, equilibrium_center_height, water_forces
from yellowstone_python.river.uncertainty import ridge_members, member_trajectories


def animated_bird(path, controls=None):
    """Export a small synthetic contact fixture."""
    asset, skeleton, joints, weights = bird_proxy(False)
    engine = BirdEngine(skeleton, get_profile('mallard'))
    export_asset(asset, path, skeleton, joints, weights,
                 engine.clips(['Walk'], fps=8, cycles=1, overrides=controls))
    return engine


def test_fitted_bird_phases_reach_analytic_and_serialized_feet(tmp_path):
    first, second = tmp_path/'first.glb', tmp_path/'second.glb'
    engine = animated_bird(first)
    controls = {'touchdown_phases': {'left': .25, 'right': .75}}
    animated_bird(second, controls)
    assert engine.pose(0, 'Walk').diagnostics['contacts'] != engine.pose(0, 'Walk', controls).diagnostics['contacts']
    assert not np.allclose(imported_skin(first, 'Walk', 0), imported_skin(second, 'Walk', 0))
    doc, _ = read_glb(second)
    assert doc['animations'][0]['extras']['wildlife_motion']['controls']['touchdown_phases'] == {'L': .25, 'R': .75}


@pytest.mark.parametrize('changes', [
    {'touchdown_phases': {'L': .2}}, {'touchdown_phases': {'FL': 0, 'FR': .5}},
    {'touchdown_phases': {'L': float('nan'), 'R': .5}}, {'unimplemented_knob': 2}])
def test_incomplete_or_inactive_bird_controls_refuse(changes):
    with pytest.raises(ValueError):
        BirdEngine(None, get_profile('mallard')).parameters('Walk', changes)


@pytest.mark.parametrize('defect', ['nonfinite', 'indices', 'weights', 'animations', 'loop'])
def test_validation_cli_required_failure_is_structured_and_nonzero(tmp_path, defect):
    path, report = tmp_path/'bad.glb', tmp_path/'report.json'
    animated_bird(path)
    doc, raw = read_glb(path)
    blob = bytearray(raw)
    primitive = doc['meshes'][0]['primitives'][0]
    if defect == 'animations':
        doc.pop('animations')
    else:
        attribute = ('indices' if defect == 'indices' else
                     primitive['attributes']['WEIGHTS_0'] if defect == 'weights' else
                     primitive['attributes']['POSITION'])
        index = primitive['indices'] if attribute == 'indices' else attribute
        record = doc['accessors'][index]
        offset = doc['bufferViews'][record['bufferView']].get('byteOffset', 0) + record.get('byteOffset', 0)
        if defect == 'indices':
            code = {5123: 'H', 5125: 'I'}[record['componentType']]
            struct.pack_into('<'+code, blob, offset, 65535)
        elif defect == 'weights':
            struct.pack_into('<f', blob, offset, -1.)
        elif defect == 'nonfinite':
            struct.pack_into('<f', blob, offset, float('nan'))
        else:
            sampler = doc['animations'][0]['samplers'][0]
            record = doc['accessors'][sampler['output']]
            view = doc['bufferViews'][record['bufferView']]
            offset = view.get('byteOffset', 0) + record.get('byteOffset', 0)
            width = {'VEC3': 3, 'VEC4': 4}[record['type']]
            struct.pack_into('<f', blob, offset+(record['count']-1)*width*4, 50.)
    write_glb(path, doc, blob)
    assert main(['validate', str(path), '--output', str(report)]) != 0
    result = json.loads(report.read_text())
    assert result['passed'] is False and result['status'] == 'failed'


def test_validation_cli_valid_serialized_positive_control(tmp_path):
    path = tmp_path/'valid.glb'
    animated_bird(path)
    assert main(['validate', str(path)]) == 0


def test_dry_body_and_feet_have_no_hydrodynamic_force():
    config = WaterConfig(wave_amplitude_m=0)
    state = np.array([0., 10., 0., 1., 2., 0., 0., 1.])
    force, moment, report = water_forces(.17, state, config)
    np.testing.assert_allclose(force, [0, -config.mass_kg*config.gravity_m_s2, 0])
    assert moment == 0 and report['submerged_fraction'] == 0
    np.testing.assert_allclose(report['foot_forces_n'], 0)


def test_immersed_current_relative_drag_and_bounded_surface_transition():
    config = WaterConfig(wave_amplitude_m=0, foot_area_m2=0, current_m_s=(.2, 0., 0.))
    state = np.zeros(8)
    state[1] = equilibrium_center_height(config)
    state[3] = 1.
    force, _, _ = water_forces(0, state, config)
    assert force[0] < 0
    state[3] = -.5
    assert water_forces(0, state, config)[0][0] > 0
    values = [water_forces(0, np.array([0., height, 0., 1., 0., 0., 0., 0.]), config)[0]
              for height in np.linspace(-.5, .5, 101)]
    assert np.isfinite(values).all()


def test_rejected_low_error_candidate_cannot_reenter_ensemble(monkeypatch):
    rows = [{'q_lat': q, 't_lat': 25., 'c_mult': 1., 'train_rmse': error, 'budget_ok': valid}
            for q, error, valid in [(1., 0., False), (2., 1., True), (3., 1.05, True)]]
    members = ridge_members(rows, 1., min_members=5)
    assert {member['q_lat'] for member in members} == {2., 3.}
    assert all(member['minimum_unavailable'] for member in members)
    from yellowstone_python.river import calibrate
    monkeypatch.setattr(calibrate, 'run_fit_forward', lambda *args: {'grid': [0, 1], 'modeled_c': [1, 2], 'budget_ok': False})
    checked = member_trajectories({}, 1., 1., members)
    assert checked['trajectories'] == [] and len(checked['rejected_members']) == 2


def test_stage_c_serialized_low_flow_model_reproduces_metrics():
    from dataclasses import asdict
    from tests.test_calibrate_river_transport import _synthetic_bundle
    from tools.calibrate_river_transport import stage_a_hydraulics, stage_c_sources
    from yellowstone_python.river.calibrate import interp_series, run_fit_forward
    from yellowstone_python.river.hydraulics import score_paired_series
    from yellowstone_python.river.uncertainty import fit_masks
    bundle = _synthetic_bundle(truth=(.2, 25., 1.3), days=.25, dt_s=900.)
    stage_a = stage_a_hydraulics(bundle, 20000., 40000.)
    result = stage_c_sources(bundle, stage_a, [.1, .2, .4], [20., 25., 30.], dt_s=900., spinup_s=0.,
                             skip_de=True, n_bootstrap=100, min_members=2)
    restored = json.loads(json.dumps(asdict(result)))
    model = restored['evaluated_model']
    assert restored['c_mult'] == model['parameters']['c_mult'] == 1.
    assert .1 <= restored['q_lat'] <= .4
    parameters = model['parameters']
    forward = run_fit_forward(model['forcing_bundle'], parameters['volume_m3'], parameters['area_m2'],
                              restored['q_lat'], restored['t_lat'], restored['c_mult'], 900.)
    target = interp_series(bundle['sites']['06036905']['series']['temperature_c'], forward['grid'])
    training, holdout = fit_masks(forward['grid'], 0., .7)
    for label, window in [('train_rmse', training), ('holdout_rmse', holdout)]:
        assert restored[label] == pytest.approx(score_paired_series(forward['modeled_c'][window], target[window])['rmse'], abs=1e-12)


def test_exhausted_optimizer_is_not_reported_as_converged():
    from tests.test_calibrate_river_transport import _synthetic_bundle
    from yellowstone_python.river.calibrate import least_squares_fit
    bundle = _synthetic_bundle(days=.25, dt_s=900.)
    result = least_squares_fit(bundle, 20000., 40000., (1., 20., 1.), spinup_s=0., dt_s=900., max_nfev=1)
    assert result['success'] is False and result['optimizer']['converged'] is False
    assert result['optimizer']['termination_reason'] and result['optimizer']['termination_code'] == 0


def test_surface_identifiability_uses_the_actual_confounded_objective(monkeypatch):
    import tools.calibrate_river_transport as staged
    from tests.test_calibrate_river_transport import _synthetic_bundle
    bundle = _synthetic_bundle(days=.25, dt_s=900.)
    report = staged.observation_hierarchy_report(bundle)
    assert report['identifiability']['status'] == 'unassessed'
    def confounded(arrays, volume, area, q, t, c, params, dt, *, with_checks=False):
        values = [c+params.longwave_multiplier+params.longwave_bias_w_m2 for _ in arrays['grid']]
        return {'modeled_c': values, 'budget_ok': True} if with_checks else values
    monkeypatch.setattr(staged, '_stage_d_forward', confounded)
    a = staged.stage_a_hydraulics(bundle, 20000., 40000.)
    c = staged.StageCResult(.2, 25., 0., 0., 'fixture', 'synthetic', {})
    result = staged.stage_d_surface(bundle, a, c, identifiable=['longwave_multiplier', 'longwave_bias_w_m2'],
        skip_polish=True, spinup_s=0., dt_s=900., lhs_samples=4, min_members=2, n_bootstrap=100)
    assert result.identifiability['status'] == 'locally_confounded'
    assert result.identifiability['rank'] < len(result.estimated_parameters)
    assert result.identified_fields == []
    assert result.objective['residual_channels'] == ['downstream_temperature_c']


def test_weather_queries_preserve_scenario_day_and_absolute_instant(tmp_path):
    from yellowstone_python.atmosphere.time_utils import epoch_unix_for_local
    from yellowstone_python.service.llm_backend import Backend
    world, derived = tmp_path/'world', tmp_path/'derived'
    (world/'data').mkdir(parents=True)
    derived.mkdir()
    origin = epoch_unix_for_local('2026-06-21', 12., -6.)
    expected = epoch_unix_for_local('2026-06-21', 16., -6.)
    (world/'data/ecosystem.json').write_text(json.dumps({'simulation_epoch_unix': origin,
        'weather': {'utc_offset_hours': -6., 'use_met_bundle': True}}))
    start = epoch_unix_for_local('2026-06-20', 0., -6.)
    rows = [[start+i*3600., float(i), .5, 2., 100., .2] for i in range(72)]
    (derived/'met.json').write_text(json.dumps({'schema': 'yellowstone.met_forcing.v1', 'hourly': rows}))
    backend = Backend(world=world, derived=derived)
    for query in ({'hour':16.}, {'epoch_unix':expected}, {'elapsed_hours':4.}):
        snapshot = backend.weather(**query)
        assert snapshot['simulation_time_unix'] == expected and snapshot['air_c'] == 40.
    unavailable = backend.weather(elapsed_hours=100.)
    assert unavailable['source']['weather_bundle_window']['status'] == 'unavailable_out_of_window'
    assert unavailable['simulation_time_unix'] == origin + 360000.
    with pytest.raises(ValueError, match='Choose one'):
        backend.weather(hour=16., elapsed_hours=4.)


def test_actual_fish_actor_uses_signed_displacement_and_freezes_on_pause():
    godot = shutil.which('godot')
    if not godot:
        pytest.skip('Godot executable unavailable')
    world = Path(__file__).resolve().parents[2]/'yellowstone_midway'
    result = subprocess.run([godot, '--headless', '--path', str(world), '--script',
        'tools/validate_toolchain.gd'], text=True, capture_output=True, timeout=30)
    assert result.returncode == 0 and 'TOOLCHAIN_FISH PASS' in result.stdout, result.stdout+result.stderr


def test_population_variant_carries_exact_lineage_and_refuses_mismatched_base(tmp_path):
    from tests.wildlife_motion.test_data_water import write_population
    from yellowstone_python.wildlife_motion.variation import fit_population, sample_population, diversify
    source = tmp_path/'population.csv'
    write_population(source)
    asset, skeleton, _, _ = bird_proxy()
    reference = {'species': skeleton.metadata['species'], 'asset_sha256': asset.source_sha256}
    model = fit_population(source, base_reference=reference)
    variant = sample_population(model, 17)
    derived, rig = diversify(asset, skeleton, variant)
    lineage = derived.metadata['variant']['population_lineage']
    assert lineage['dataset_sha256'] == model['source_sha256']
    assert lineage['model_sha256'] == model['model_sha256']
    assert lineage['source_model'] == model and lineage['seed'] == 17
    assert rig.metadata['variant']['population_lineage'] == lineage
    wrong = copy.deepcopy(asset)
    wrong.source_sha256 = '0'*64
    with pytest.raises(ValueError, match='same source mesh'):
        diversify(wrong, skeleton, variant)
