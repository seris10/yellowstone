"""Live lookahead, clock, control, branching and HTTP integration tests."""
import copy
import json
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from yellowstone_python.service.live import LiveEngine
from yellowstone_python.service.live.engine import DEPENDENCIES
from yellowstone_python.river.river_transport import Cell, River, river_from_config
from yellowstone_python.service.server import live_server
from yellowstone_python.study_mode import SCHEMA


def engine(**kwargs):
    river = River([Cell('a', 20., 10., 200., 15.), Cell('b', 20., 10., 200., 15.)], 5., 15.)
    return LiveEngine(river, {'live': {'foodweb_interval_s': 10.}}, horizon_s=60., frame_interval_s=10., **kwargs)


def test_control_truncates_only_future_frames_and_advects_boundary_first():
    model = engine()
    model.compute_until(60.)
    before = model.frames()['frames']
    result = model.command('control', {'at_s': 20., 'changes': {'hydro.boundary_c': 25.}})
    assert result['truncate_after_t_s'] == 20.
    assert model.frames()['frames'][:2] == before[:2]
    assert model.frames()['frames'][2]['temperature_c'] == before[2]['temperature_c']
    model.compute_until(60.)
    first = model.frames(20.)['frames'][0]
    assert first['temperature_c'][0] > first['temperature_c'][1]
    assert model.frames()['frames'][:2] == before[:2]
    assert result['dirty_stages'] == ['river', 'oxygen', 'periphyton', 'foodweb']


def test_checkpoint_recompute_matches_fresh_physical_run():
    model = engine()
    model.compute_until(20.)
    model.command('control', {'at_s': 20., 'key': 'hydro.boundary_c', 'value': 23.})
    model.compute_until(60.)
    fresh = river_from_config(model.solver_config())
    fresh.run(60., dt_s=.1, sample_s=10.)
    assert fresh.temperature_c == pytest.approx(model.river.temperature_c, abs=1e-12)


def test_identical_marked_branches_have_equal_scientific_state():
    model = engine()
    model.compute_until(20.)
    model.command('mark', {'at_s': 20.})
    model.compute_until(60.)
    comparison = model.compare()
    assert comparison['A']['temperature_c'] == comparison['B']['temperature_c']
    assert comparison['metrics'] == {'refuge_shift_m': 0., 'emergence_change': 0., 'dipper_intake_change': 0.}


def test_schema_has_bounds_provenance_geometry_and_measured_dates():
    schema = engine().schema()
    assert schema['cells'][0]['id'] == 'a'
    assert schema['measured_dates'] == []
    rows = {row['key']: row for row in schema['controls']}
    assert rows['hydro.boundary_c']['min'] == 0.
    assert rows['hydro.boundary_m3s']['min'] == 2.5
    assert all(row['bound_source'] and row['provenance'] for row in rows.values())


@pytest.mark.parametrize('key', list(DEPENDENCIES))
def test_dependency_table_is_defined_for_schema_controls(key):
    assert key in SCHEMA
    assert DEPENDENCIES[key]
    if key == 'hydro.boundary_c':
        assert 'snow' not in DEPENDENCIES[key]


def test_worker_clock_pause_and_step():
    model = engine(start_worker=True)
    try:
        deadline = time.monotonic() + 10.
        while model.river.time_s < 60. and time.monotonic() < deadline:
            time.sleep(.02)
        model.command('clock', {'paused': True})
        at = model.player_t_s
        time.sleep(.05)
        assert model.player_t_s == at
        result = model.command('clock', {'step': True})
        assert result['player_t_s'] == at + 10.
        assert model.worker_error is None
    finally:
        model.close()


def test_http_control_and_invalid_input():
    model = engine(start_worker=True)
    server = live_server(model, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f'http://127.0.0.1:{server.server_port}'
    def post(path, payload):
        request = Request(base + path, json.dumps(payload).encode(), {'Content-Type': 'application/json'})
        return json.loads(urlopen(request, timeout=20.).read())
    try:
        schema = json.loads(urlopen(base + '/api/live/schema').read())
        result = post('/api/live/control', {'at_s': 20., 'key': 'hydro.boundary_c', 'value': 25.})
        assert result['ok']
        with pytest.raises(HTTPError) as error:
            post('/api/live/control', {'key': 'hydro.boundary_c', 'value': -1.})
        assert error.value.code == 400
        assert b'outside' in error.value.read()
        deadline = time.monotonic() + 10.
        frames = []
        while not frames and time.monotonic() < deadline:
            frames = json.loads(urlopen(base + '/api/live/frames?after_t_s=20').read())['frames']
            time.sleep(.02)
        assert frames and frames[0]['temperature_c'][0] > frames[0]['temperature_c'][1]
        assert schema['session_id'] == model.session_id
    finally:
        server.shutdown()
        server.server_close()
        model.close()


def test_export_preserves_control_times_variable_steps_and_shading(tmp_path):
    import yaml
    from yellowstone_python.service.live.engine import run_exported_scenario
    model = engine()
    model.compute_until(20.)
    model.command('control', {'at_s': 20., 'changes': {
        'hydro.boundary_c': 23., 'river.shade': {'cell_ids': ['a'], 'multiplier': .4}}})
    model.command('clock', {'time_scale': 600.})
    model.compute_until(60.)
    target = tmp_path / 'scenario.yaml'
    model.export_scenario(target)
    config = yaml.safe_load(target.read_text())
    replay = run_exported_scenario(config['live'])
    assert replay['frames'][-1]['temperature_c'] == pytest.approx(model.river.temperature_c, abs=1e-12)
    assert replay['final_budget'] == model.river.budget()


@pytest.mark.parametrize('direction,expected', [(0., [0., 2.]), (90., [-2., 0.]),
                                               (180., [0., -2.]), (270., [2., 0.])])
def test_wind_controls_use_meteorological_from_direction(direction, expected):
    model = engine()
    model.command('control', {'at_s': 0., 'changes': {
        'weather.wind_speed_mps': 2., 'weather.wind_direction_deg': direction}})
    assert model.config['weather']['wind_xz_mps'] == pytest.approx(expected, abs=1e-12)


def test_startup_wind_direction_round_trip_preserves_vector():
    model = engine()
    vector = model.config['weather']['wind_xz_mps'][:]
    direction = model.config['weather']['wind_direction_deg']
    model.command('control', {'at_s': 0., 'key': 'weather.wind_direction_deg', 'value': direction})
    assert model.config['weather']['wind_xz_mps'] == pytest.approx(vector, abs=1e-12)


def test_dry_air_is_valid_and_has_no_finite_dewpoint():
    model = engine()
    model.command('control', {'at_s': 0., 'key': 'weather.humidity', 'value': 0.})
    model.compute_until(10.)
    assert model.frames()['frames'][-1]['weather']['dewpoint_c'] is None


def test_late_renderer_acknowledgment_does_not_pause_worker():
    model = engine(start_worker=True)
    try:
        time.sleep(.2)
        model.frames(-1., player_t_s=0.)
        time.sleep(.1)
        assert model.worker_error is None
    finally:
        model.close()


def test_schema_endpoint_responds_during_model_lock():
    model = engine()
    server = live_server(model, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with model._lock:
            response = urlopen(f'http://127.0.0.1:{server.server_port}/api/live/schema', timeout=1.)
            schema = json.loads(response.read())
        assert schema['session_id'] == model.session_id
    finally:
        server.shutdown()
        server.server_close()


def test_mark_and_compare_at_non_frame_time():
    model = engine()
    model.compute_until(60.)
    model.command('mark', {'at_s': 21.375})
    comparison = model.compare(21.375)
    assert comparison['compare_t_s'] == 21.375
    assert comparison['A']['temperature_c'] == comparison['B']['temperature_c']
    assert comparison['metrics']['refuge_shift_m'] == 0.


def test_actor_profiles_use_species_ids_and_current_water_temperature():
    from yellowstone_python.aquatic.fish import thermal_performance
    model = engine()
    model.config['wildlife'] = [{'id': 'brown_actor', 'species_id': 'brown_trout'},
                                {'id': 'rainbow_actor', 'species_id': 'rainbow_trout'}]
    model.river._temperature_c = [25., 16.]
    frame = model._frame()
    assert {row['id'] for row in frame['trout']} == {'brown_actor', 'rainbow_actor'}
    for species in ('brown_trout', 'rainbow_trout'):
        assert frame['feeding_by_species'][species] == [thermal_performance(t, species)['feeding'] for t in [25., 16.]]
    assert frame['cells'][0]['feeding'] == 0.
    assert frame['cells'][0]['exposure_temperature_c'] == 15.


def test_frames_endpoint_responds_during_model_lock():
    model = engine()
    server = live_server(model, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with model._lock:
            response = urlopen(f'http://127.0.0.1:{server.server_port}/api/live/frames', timeout=1.)
            result = json.loads(response.read())
        assert result['frames'][0]['t_s'] == 0.
    finally:
        server.shutdown()
        server.server_close()


def test_live_domains_resolve_to_real_build_stage_contracts():
    from yellowstone_python.service.live.engine import live_stage_contracts
    from yellowstone_python.pipeline import stage_contracts
    resolved = live_stage_contracts()
    assert resolved['stages'] == stage_contracts()
    assert resolved['domains']['oxygen'] == resolved['domains']['river']
    assert resolved['domains']['snow'] != resolved['domains']['river']


def test_model_component_ids_and_source_files_exist(repo_root):
    from yellowstone_python.registry.equations import COMPONENTS
    names = {row['component'] for row in COMPONENTS}
    for row in engine().schema()['header']['model_components'].values():
        assert row['component_id'] in names
        assert (repo_root / row['source_file']).is_file()


@pytest.mark.parametrize('temperature', [0., 6., 10., 13., 16., 18., 20., 22., 25., 28.])
def test_live_species_feeding_matches_thermal_functions(temperature):
    from yellowstone_python.aquatic.fish import thermal_performance
    model = engine()
    model.river._temperature_c = [temperature, temperature]
    frame = model._frame()
    for species in ('brown_trout', 'rainbow_trout'):
        expected = thermal_performance(temperature, species)['feeding']
        assert frame['feeding_by_species'][species] == [expected, expected]


def test_live_land_uses_canonical_conductive_profile_and_soil_bucket():
    import yellowstone_python.land.snow_season as snow
    import yellowstone_python.thermal_features.ground_heat as ground
    from yellowstone_python.common.site import SITE_ELEVATION_M
    river = River([Cell('a', 20., 10., 200., 15.)], 5., 15.)
    config = {'weather': {'night_air_c': 10., 'day_warming_c': 0., 'gust_mps': 0.,
        'wind_xz_mps': [0., 2.], 'precip_mm_h': 2.},
        'patches': [{'id': 'p', 'center_xz': [0., 0.], 'soil_mm': 60., 'snow_mm': 0.,
                    'biomass': .5, 'capacity': 1., 'moisture': .5}]}
    model = LiveEngine(river, config, time_scale=600., frame_interval_s=60.)
    model.compute_until(3600.)
    patch = model.frames()['frames'][-1]['ecology']['patches'][0]
    rain = 2.
    expected = snow.step_soil_bucket(60., rain, 10., 2., elapsed_days=1. / 24.)
    assert patch['soil_mm'] == pytest.approx(expected['soil_mm'], abs=1e-12)
    assert patch['soil_temperature_c'] == ground.soil_temperature_c(10., ground.GHF_BACKGROUND_W_M2,
                                                                   site_elevation_m=SITE_ELEVATION_M)
    assert model.ecology['land_ledger']['water_residual_mm'] == pytest.approx(0., abs=1e-12)


def test_refining_aquatic_interval_has_small_oxygen_and_biomass_error():
    models = []
    for interval in (60., 10.):
        river = River([Cell('a', 20., 10., 200., 15.), Cell('b', 20., 10., 200., 15.)], 5., 15.)
        model = LiveEngine(river, {'live': {'aquatic_interval_s': interval}},
                           time_scale=600., frame_interval_s=10.)
        model.compute_until(1800.)
        models.append(model)
    coarse, fine = models
    assert coarse.ecology['oxygen_mg_l'] == pytest.approx(fine.ecology['oxygen_mg_l'], abs=.02)
    assert coarse.ecology['periphyton'] == pytest.approx(fine.ecology['periphyton'], rel=.001)
    assert coarse.river.temperature_c == fine.river.temperature_c


@pytest.mark.parametrize('changes,expected', [
    ({'weather.night_air_c': 9.}, ['weather', 'river', 'insects', 'snow', 'soil', 'oxygen', 'periphyton', 'foodweb']),
    ({'weather.cloud': .7}, ['weather', 'river', 'insects', 'snow']),
    ({'weather.precip_mm_h': 2.}, ['weather', 'snow', 'soil', 'runoff', 'river']),
    ({'clock_hour': 13.}, ['display']),
    ({'hydro.boundary_m3s': 4.}, ['river', 'hydraulics', 'oxygen', 'foodweb']),
    ({'hydro.boundary_c': 20.}, ['river', 'oxygen', 'periphyton', 'foodweb']),
    ({'thermal.excelsior_enabled': False}, ['river', 'solutes', 'foodweb']),
    ({'aquatic.tributary_pockets': True}, ['foodweb']),
])
def test_control_rows_mark_exact_model_dependencies(changes, expected):
    from yellowstone_python.river.river_transport import Source
    river = River([Cell('a', 20., 10., 200., 15.)], 5., 15.,
                  sources=[Source('excelsior_aggregate_outflow', 'a', .2, 62.)])
    config = {'patches': [{'id': 'p', 'center_xz': [0., 0.], 'biomass': .5,
                           'capacity': 1., 'moisture': .5}]}
    model = LiveEngine(river, config)
    result = model.command('control', {'at_s': 0., 'changes': changes})
    assert result['dirty_stages'] == expected
    assert model.frames()['header']['dirty_stages'] == expected


def test_surface_iteration_failure_is_visible_in_service_health():
    from yellowstone_python.river.river_transport import SurfaceBudget
    river = River([Cell('a', 20., 10., 200., 15.)], 5., 15.,
        surface_budget=SurfaceBudget.parse({'rh': .5, 'wind_mps': 2.,
            'shortwave_w_m2': 900., 'cloud': .2}), max_surface_iterations=1,
        surface_tolerance_c=1e-16)
    model = LiveEngine(river, start_worker=True, horizon_s=10., frame_interval_s=10.)
    try:
        deadline = time.monotonic() + 10.
        while not model.frames()['header']['health']['worker_error'] and time.monotonic() < deadline:
            time.sleep(.02)
        health = model.frames()['header']['health']
        assert health['surface_iteration_failures'] > 0
        assert health['worker_error']
        assert model.paused
    finally:
        model.close()


def test_identical_branches_keep_equal_steps_after_clock_scale_change():
    model = engine()
    model.compute_until(20.)
    model.command('mark', {'at_s': 20.})
    model._compute_rate_sps = 10000.
    model.command('clock', {'time_scale': 600.})
    model.compute_until(80.)
    assert model._baseline.time_scale == model.time_scale
    comparison = model.compare(80.)
    assert comparison['A']['temperature_c'] == comparison['B']['temperature_c']
    assert comparison['metrics']['refuge_shift_m'] == 0.


def test_static_baked_series_are_excluded_from_checkpoint_config():
    class StaticSeries:
        def __deepcopy__(self, memo):
            raise AssertionError('static baked series must not be copied into live state')
    river = River([Cell('a', 20., 10., 200., 15.)], 5., 15.)
    model = LiveEngine(river, {'python_series': StaticSeries()})
    assert 'python_series' not in model.config
    assert 'python_series' not in model._checkpoint()['config']


def test_published_player_and_buffer_are_one_atomic_snapshot():
    model = engine()
    published = model.frames()
    model.player_t_s = 17.
    result = model.frames()
    assert result['player_t_s'] == published['player_t_s']
    assert result['buffer_headroom_s'] == published['buffer_headroom_s']
    model._publish_snapshot()
    assert model.frames()['player_t_s'] == 17.


def test_default_chainage_accumulates_unequal_cell_lengths():
    river = River([Cell('a', 20., 10., 200., 15.), Cell('b', 40., 10., 400., 15.),
                   Cell('c', 50., 10., 500., 15.)], 5., 15.)
    model = LiveEngine(river)
    assert [row['center_s_m'] for row in model.cells] == [10., 40., 85.]
    assert [row['position_xyz'][2] for row in model.cells] == [10., 40., 85.]


def test_default_scale_can_upgrade_using_measured_maximum_step_capacity():
    model = engine()
    assert model.time_scale == 1.
    model._compute_rate_sps = 160.
    model._record_max_dt_capacity(600., .5)
    result = model.command('clock', {'time_scale': 600.})
    assert result['time_scale'] == 600.
    assert result['max_supported_time_scale'] == 600.
    assert model._header()['dt_s'] == .1


def test_geometry_excludes_baked_frames_before_copying():
    class StaticFrames:
        def __deepcopy__(self, memo):
            raise AssertionError('baked frames must not be copied into live geometry')
    river = River([Cell('a', 20., 10., 200., 15.)], 5., 15.)
    model = LiveEngine(river, geometry={'frames': StaticFrames(), 'river_features': {'river': {}}})
    assert 'frames' not in model.geometry
    assert model.schema()['river_features'] == {'river': {}}
