"""Real-time defaults and selectable live clock rates."""
import datetime as dt
import json
import sys
import time
from types import SimpleNamespace

import pytest

from yellowstone_python.river.obs_model import DOWNSTREAM_GAUGE, UPSTREAM_GAUGE
from yellowstone_python.river.river_transport import Cell, River
from yellowstone_python.service.live.engine import LiveEngine


def make_engine(**kwargs):
    river = River([Cell('a', 20., 10., 200., 15.)], 5., 15.)
    config = {'patches': [{'id': 'p', 'center_xz': [0., 0.], 'soil_mm': 60., 'snow_mm': 0.,
                          'biomass': .5, 'capacity': 1., 'moisture': .5}]}
    return LiveEngine(river, config, horizon_s=20., frame_interval_s=10., **kwargs)


def test_constructor_and_published_clock_default_to_real_time():
    model = make_engine()
    assert model.time_scale == 1.
    assert model.schema()['header']['time_scale'] == 1.
    assert model.frames()['header']['time_scale'] == 1.
    assert model.schema()['time_scales'] == [1, 60, 600, 3600]


def test_default_worker_advances_one_simulated_second_per_wall_second():
    model = make_engine(start_worker=True)
    try:
        deadline = time.monotonic() + 10.
        while not model._clock_started and time.monotonic() < deadline:
            time.sleep(.01)
        assert model._clock_started
        assert model.worker_error is None
        start_wall = time.monotonic()
        start_player = model.frames()['player_t_s']
        time.sleep(.25)
        elapsed = time.monotonic() - start_wall
        result = model.frames()
        assert result['player_t_s'] - start_player == pytest.approx(elapsed, abs=.05)
        assert result['header']['time_scale'] == 1.
        assert result['buffer_headroom_s'] > 0.
    finally:
        model.close()


@pytest.mark.parametrize('requested', [None, 1., 60., 600., 3600.])
def test_cli_defaults_to_real_time_and_keeps_explicit_rates(monkeypatch, tmp_path, requested):
    from yellowstone_python.service.live import __main__ as command
    captured = {}
    closed = []
    def from_build(path, **kwargs):
        captured.update({'path': path, **kwargs})
        return SimpleNamespace(close=lambda: closed.append('engine'))
    def serve():
        raise KeyboardInterrupt
    server = SimpleNamespace(serve_forever=serve, server_close=lambda: closed.append('server'))
    monkeypatch.setattr(command.LiveEngine, 'from_build', from_build)
    monkeypatch.setattr(command, 'live_server', lambda engine, port, token=None: server)
    arguments = ['live', '--build', str(tmp_path)]
    if requested is not None:
        arguments += ['--time-scale', str(requested)]
    monkeypatch.setattr(sys, 'argv', arguments)
    assert command.main() == 0
    assert captured['time_scale'] == (1. if requested is None else requested)
    assert captured['start_worker']
    assert closed == ['server', 'engine']


@pytest.mark.parametrize('rate', [1., 60., 600., 3600.])
def test_controls_dates_and_checkpoint_restore_preserve_selected_rate(rate):
    model = make_engine()
    checkpoint = model._checkpoint()
    model._record_max_dt_capacity(600., .01)
    assert model.command('clock', {'time_scale': rate})['time_scale'] == rate
    model.command('control', {'at_s': 0., 'changes': {'weather.cloud': .5}})
    model.command('control', {'at_s': 0., 'changes': {'clock_hour': 12.}})
    model.command('control', {'at_s': 0., 'changes': {'snow.as_of_date': '2026-10-03'}})
    model._restore(checkpoint)
    model.command('clock', {'paused': True})
    model.command('clock', {'paused': False})
    assert model.time_scale == rate


@pytest.mark.parametrize('rate', [1., 600.])
def test_measured_day_selection_preserves_default_or_selected_rate(rate):
    midnight = dt.datetime(2026, 10, 3, tzinfo=dt.timezone(dt.timedelta(hours=-6))).timestamp()
    times = [midnight + i * 900. for i in range(193)]
    series = {'temperature_c': [[t, 15.] for t in times],
              'discharge_m3_s': [[t, 5.] for t in times]}
    bundle = {'sites': {UPSTREAM_GAUGE: {'series': series}, DOWNSTREAM_GAUGE: {'series': series}},
              'met': {'hourly': [[midnight + i * 3600., 10., .5, 2., 0., .5] for i in range(49)]}}
    model = make_engine(observation_bundle=bundle)
    if rate != 1.:
        model._record_max_dt_capacity(600., .01)
        model.command('clock', {'time_scale': rate})
    for date in model.measured_dates():
        result = model.command('measured', {'date': date})
        assert result['run_mode'] == 'observed_replay'
        assert model.time_scale == rate


def test_session_export_without_clock_event_uses_real_time_step(tmp_path):
    import yaml
    from yellowstone_python.service.live.__main__ import export_session
    model = make_engine()
    model.compute_until(10.)
    model.close()
    log = tmp_path / 'session.jsonl'
    log.write_text(''.join(json.dumps(event) + '\n' for event in model.session_events))
    output = export_session(log, tmp_path / 'scenario.yaml')
    assert yaml.safe_load(output.read_text())['live']['dt_s'] == .1
