import pytest
from datetime import datetime, timezone

from yellowstone_python.river.river_transport import Series
from yellowstone_python.river.river_world import Channel, _weather_times, add_temperature_pulse, build_mapped_replay, cell_faces, energy_met_series, firehole_chain, parse_cross_sections, parse_simulation_start, physical_weather, timestamp_metadata, validate_source_record, validate_weather_configuration
from yellowstone_python.atmosphere.time_utils import epoch_unix_for_local

# Fixed replay epoch so the clock is deterministic across runs.
REPLAY_START = {"simulation_start_epoch_unix": 1784000000.0}

def feature(identifier, upstream, downstream, points):
    return {
        "id": identifier,
        "name": "FIREHOLE RIVER",
        "width": 22.0,
        "endpoint_node_ids": [upstream, downstream],
        "points": points,
    }

def test_river_world_chain_uses_nodes_not_input_order():
    upstream = feature(
        "upstream", "a", "b",
        [[0, 2, 100], [0, 1, 50]],
    )
    downstream = feature(
        "downstream", "b", "c",
        [[0, 1, 50], [0, 0, 0]],
    )
    chain = firehole_chain({
        "rivers": [downstream, upstream]
    })
    assert [row['id'] for row in chain] == ['upstream', 'downstream']


def test_river_world_original_vertex_chainage_survives_join():
    channel = Channel([
        feature("a", "n0", "n1", [[0, 2, 100], [0, 1, 50]]),
        feature("b", "n1", "n2", [[0, 1, 50], [0, 0, 0]]),
    ])
    assert channel.features['b']['point_s_m'] == [50, 100]
    assert channel.position_at(75) == [0, 0.5, 25]
    assert channel.chainage_at_z(25) == 75


def test_river_world_declared_junction_with_bad_coordinates_fails():
    with pytest.raises(ValueError):
        Channel([
            feature("a", "n0", "n1", [[0, 2, 100], [0, 1, 50]]),
            feature("b", "n1", "n2", [[1, 1, 50], [0, 0, 0]]),
        ])


def test_river_world_branch_is_rejected():
    with pytest.raises(ValueError):
        firehole_chain({
            "rivers": [
                feature("a", "n0", "n1", [[0, 0, 2], [0, 0, 1]]),
                feature("b", "n1", "n2", [[0, 0, 1], [0, 0, 0]]),
                feature("c", "n1", "n3", [[0, 0, 1], [1, 0, 0]]),
            ]
        })


def test_river_world_ambiguous_legacy_z_is_rejected():
    channel = Channel([
        feature(
            "curve", "n0", "n1",
            [[0, 2, 100], [10, 1, 0], [20, 0, 100]],
        )
    ])
    with pytest.raises(ValueError):
        channel.chainage_at_z(50)


def test_river_world_source_is_exact_face_and_cells_are_bounded():
    faces = cell_faces(101.0, [37.0], 20.0)
    assert 37.0 in faces
    assert faces[0] == 0.0
    assert faces[-1] == 101.0
    assert (all((0 < b - a <= 20.0 for a, b in zip(faces, faces[1:]))))



def tiny_world_ecosystem():
    world = {
        "georeference": {"note": "test"},
        "rivers": [
            {
                "id": "seg_a",
                "name": "FIREHOLE RIVER",
                "width": 10.0,
                "endpoint_node_ids": ["n0", "n1"],
                "points": [[0, 0, 100], [0, 0, 0]],
            },
            {
                "id": "seg_b",
                "name": "FIREHOLE RIVER",
                "width": 20.0,
                "endpoint_node_ids": ["n1", "n2"],
                "points": [[0, 0, 0], [0, 0, -50]],
            },
        ],
    }
    ecosystem = {
        "boundary_m3s": 5.0,
        "boundary_c": 15.0,
        "clock_hour": 12.0,
        "weather": {},
        "river_reaches": [],
    }
    return world, ecosystem


def test_cross_section_default_path_uses_assumed_depth_everywhere():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=120.0,
                              maximum_cell_m=25.0)
    for record in doc["cells"]:
        assert record['geometry_status'] == 'mapped_centerline_authored_width_assumed_rectangular_depth'
        assert record['volume_m3'] == pytest.approx(record['length_m'] * record['width_m'] * 1.1, abs=0.5 * 10 ** -(7), rel=0)
        assert record['depth_m'] == 1.1
        assert record['depth_status'] == 'assumed_rectangular_depth_no_bathymetry'
    assert (doc['numerical_checks']['passed'])


def test_cross_section_profiles_override_per_feature_volume_and_status():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(
        world, ecosystem, **REPLAY_START, duration_s=120.0, maximum_cell_m=25.0,
        cross_sections={
            "seg_b": {"depth_m": 2.0,
                      "status": "authored_estimate",
                      "source": "hand profile"},
        })
    by_river = {}
    for record in doc["cells"]:
        by_river.setdefault(record["river_id"], []).append(record)
    for record in by_river["seg_a"]:
        assert record['depth_m'] == 1.1
        assert 'assumed' in record['geometry_status']
    for record in by_river["seg_b"]:
        assert record['depth_m'] == 2.0
        assert record['geometry_status'] == 'mapped_centerline_authored_width_profile_depth'
        assert record['depth_status'] == 'authored_estimate'
        assert record['depth_source'] == 'hand profile'
        assert record['volume_m3'] == pytest.approx(record['length_m'] * 20.0 * 2.0, abs=0.5 * 10 ** -(7), rel=0)
    # Velocity varies with the profiled area.
    vel = {rid: rows[0]["representative_velocity_m_s"]
           for rid, rows in by_river.items()}
    assert vel['seg_a'] != pytest.approx(vel['seg_b'], abs=0.5 * 10 ** -(7), rel=0)
    assert (doc['numerical_checks']['passed'])
    assert doc['parameter_notes']['cross_sections'] == {'seg_b': {'depth_m': 2.0, 'status': 'authored_estimate', 'source': 'hand profile'}}


def test_cross_section_unknown_feature_rejected():
    world, ecosystem = tiny_world_ecosystem()
    with pytest.raises(ValueError):
        build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                            cross_sections={"nope": {"depth_m": 1.0,
                                                     "status": "x"}})


def test_cross_section_real_measurement_site_accepts_gauge_id_string():
    parsed = parse_cross_sections({
        "seg_a": {"depth_m": 1.0, "status": "ok",
                  "real_measurement_site": "06036805"},
    })
    assert parsed['seg_a']['real_measurement_site'] == '06036805'


def test_cross_section_real_measurement_site_rejects_bool_and_bad_strings():
    for bad in (True, False, "abc", "123", "12345678901234567",
                "0603680a", 6036805):
        with pytest.raises(ValueError):
            parse_cross_sections({
                "seg_a": {"depth_m": 1.0, "status": "ok",
                          "real_measurement_site": bad},
            })


def test_cross_section_bad_profiles_rejected():
    for bad in ({"seg_a": {"depth_m": 0.0, "status": "x"}},
                {"seg_a": {"depth_m": -2.0, "status": "x"}},
                {"seg_a": {"depth_m": "deep", "status": "x"}},
                {"seg_a": {"depth_m": 1.0}},
                {"seg_a": {"depth_m": 1.0, "status": ''}},
                {"seg_a": {"depth_m": 1.0, "status": "x",
                           "wobble": 1}}):
        with pytest.raises(ValueError):
            parse_cross_sections(bad)
    with pytest.raises(ValueError):
        parse_cross_sections([])



def test_provider_input_extra_sources_land_in_cells_and_budget():
    from yellowstone_python.land.groundwater_provider import riv_reaches_to_sources, with_chainage
    world, ecosystem = tiny_world_ecosystem()
    laterals = riv_reaches_to_sources([{
        "source_id": "gw_riv_0", "cell_id": "any",
        "gw_cell": [0, 0, 1], "flow_m3_s": 0.5,
        "temperature_c": 30.0}])
    extra = with_chainage(laterals, {"gw_riv_0": 60.0})
    doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=120.0,
                              maximum_cell_m=25.0,
                              extra_sources=extra)
    ids = [s["id"] for s in doc["forcing"]["sources"]]
    assert 'gw_riv_0' in ids
    inventory = doc["hydraulics_summary"]["thermal_inventory"]
    assert inventory['n_sources'] == 1
    assert (doc['numerical_checks']['passed'])


def test_provider_input_extra_sources_rejected():
    world, ecosystem = tiny_world_ecosystem()
    good = {"id": "gw", "s_m": 10.0, "flow_m3_s": 0.5,
            "temperature_c": 30.0, "status": "s"}
    for bad in ({**good, "s_m": 500.0},
                {**good, "flow_m3_s": -1.0},
                {**good, "temperature_c": {"times_s": [1.0],
                                           "values": [1.0]}},
                {**good, "status": ''},
                {**good, "id": ""}):
        with pytest.raises(ValueError):
            build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                extra_sources=[bad])


def test_provider_input_upstream_discharge_schedule_drives_boundary():
    import yellowstone_python.land.overland_provider as op
    world, ecosystem = tiny_world_ecosystem()
    result = op.predict_discharge([10.0, 20.0], area_m2=360000.0,
                                  runoff_coefficient=0.5, dt_s=60.0,
                                  t0_epoch_s=REPLAY_START["simulation_start_epoch_unix"])
    doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                              maximum_cell_m=25.0,
                              upstream_discharge=result)
    assert doc['forcing']['boundary_m3_s']['values'] == pytest.approx([0.5, 1.0])
    note = doc["parameter_notes"]["upstream_discharge"]
    assert note['method'] == 'area_runoff_coefficient'
    assert note['n_steps'] == 2
    assert (doc['numerical_checks']['passed'])


def test_provider_input_upstream_discharge_rejected():
    import yellowstone_python.land.overland_provider as op
    world, ecosystem = tiny_world_ecosystem()
    result = op.predict_discharge([10.0], area_m2=100.0)
    del result["method"]
    with pytest.raises(ValueError):
        build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                            upstream_discharge=result)
    with pytest.raises(ValueError):
        build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                            upstream_discharge={"method": "x"})



def test_silica_diagnostic_absent_by_default():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0)
    assert 'silica_diagnostic' not in doc


def test_silica_diagnostic_feature_obs_diagnose_final_temps():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                              silica_obs={"seg_a": 40.0})
    diag = doc["silica_diagnostic"]
    assert diag['n_cells'] == len(doc['cells'])
    pairs = list(zip(doc["cells"], diag["rows"]))
    seg_a = [r for c, r in pairs if c["river_id"] == "seg_a"]
    seg_b = [r for c, r in pairs if c["river_id"] == "seg_b"]
    assert (seg_a and seg_b)
    assert (all((r['flag'] != 'no_observation' for r in seg_a)))
    assert (all((r['flag'] == 'no_observation' for r in seg_b)))
    assert diag['n_observed'] == len(seg_a)


def test_silica_diagnostic_bad_obs_rejected():
    world, ecosystem = tiny_world_ecosystem()
    for bad in ({"seg_a": -1.0}, {"seg_a": 0.0},
                {"nope": 10.0}, {"seg_a": "x"}, ["seg_a"]):
        with pytest.raises(ValueError):
            build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0,
                                silica_obs=bad)



def test_landscape_pocket_pockets_do_not_enter_solver_cells():
    world, ecosystem = tiny_world_ecosystem()
    pockets = [{
        "id": "pocket_a", "river_id": "seg_a",
        "chainage_m": 50.0, "flow_m3_s": 0.1,
        "temperature_c": 11.5,
        "status": "measured_pocket_illustrative",
    }]
    doc = build_mapped_replay(
        world, ecosystem, **REPLAY_START, duration_s=60.0,
        maximum_cell_m=25.0, landscape_pockets=pockets,
    )
    cell_ids = [cell["id"] for cell in doc["cells"]]
    assert 'pocket_a' not in cell_ids
    assert doc['landscape_pockets']['n'] == 1
    record = doc["landscape_pockets"]["records"][0]
    assert record['kind'] == 'pocket'
    assert record['conservation'] == 'non_conservative'
    assert len(record['position_xyz']) == 3
    assert (doc['numerical_checks']['passed'])


def test_landscape_pocket_pocket_scheduled_flow_rejected():
    world, ecosystem = tiny_world_ecosystem()
    with pytest.raises(ValueError):
        build_mapped_replay(
            world, ecosystem, **REPLAY_START, duration_s=60.0,
            landscape_pockets=[{
                "id": "pocket_a", "river_id": "seg_a",
                "chainage_m": 10.0,
                "flow_m3_s": {"times_s": [0.0], "values": [0.1]},
                "temperature_c": 11.5, "status": "x",
            }],
        )


def test_landscape_pocket_pocket_conservative_claim_rejected():
    world, ecosystem = tiny_world_ecosystem()
    with pytest.raises(ValueError):
        build_mapped_replay(
            world, ecosystem, **REPLAY_START, duration_s=60.0,
            landscape_pockets=[{
                "id": "pocket_a", "river_id": "seg_a",
                "chainage_m": 10.0, "flow_m3_s": 0.1,
                "temperature_c": 11.5, "status": "x",
                "conservation": "conservative",
            }],
        )



def test_replay_frame_flow_frames_carry_per_cell_discharge():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(
        world, ecosystem, **REPLAY_START,
        duration_s=60.0, maximum_cell_m=25.0)
    n_cells = len(doc["cells"])
    for frame in doc["frames"]:
        assert 'q_cells_m3s' in frame
        assert len(frame['q_cells_m3s']) == n_cells
    # Downstream face flows define each cell's discharge.
    assert doc['frames'][0]['q_cells_m3s'] == doc['face_flow_m3_s'][1:]


def test_replay_frame_flow_frames_carry_per_cell_depth():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(
        world, ecosystem, **REPLAY_START,
        duration_s=60.0, maximum_cell_m=25.0)
    depths = [record["depth_m"] for record in doc["cells"]]
    for frame in doc["frames"]:
        assert 'depth_m_cells' in frame
        assert frame['depth_m_cells'] == depths


def test_replay_frame_flow_frames_depth_tracks_profile_overrides():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(
        world, ecosystem, **REPLAY_START,
        duration_s=60.0, maximum_cell_m=25.0,
        cross_sections={
            "seg_b": {"depth_m": 2.0,
                      "status": "authored_estimate",
                      "source": "hand profile"},
        })
    for frame in doc["frames"]:
        for depth, record in zip(frame["depth_m_cells"], doc["cells"]):
            assert depth == pytest.approx(record['depth_m'], abs=0.5 * 10 ** -(7), rel=0)



def test_cell_bed_elevation_bed_elevation_is_surface_minus_depth():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(
        world, ecosystem, **REPLAY_START,
        duration_s=60.0, maximum_cell_m=25.0)
    for record in doc["cells"]:
        assert 'bed_elevation_m' in record
        assert record['bed_elevation_m'] == pytest.approx(record['position_xyz'][1] - record['depth_m'], abs=0.5 * 10 ** -(7), rel=0)


def test_cell_bed_elevation_bed_elevation_reflects_profile_depth():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(
        world, ecosystem, **REPLAY_START,
        duration_s=60.0, maximum_cell_m=25.0,
        cross_sections={
            "seg_b": {"depth_m": 2.0,
                      "status": "authored_estimate",
                      "source": "hand profile"},
        })
    for record in doc["cells"]:
        expected = record["position_xyz"][1] - record["depth_m"]
        assert record['bed_elevation_m'] == pytest.approx(expected, abs=0.5 * 10 ** -(7), rel=0)
        if record["river_id"] == "seg_b":
            assert record['depth_m'] == pytest.approx(2.0, abs=0.5 * 10 ** -(7), rel=0)

def test_simulation_clock_start_requires_timezone():
    with pytest.raises(ValueError):
        parse_simulation_start(simulation_start_utc="2026-07-15T22:20:00")


def test_simulation_clock_start_normalizes_to_utc():
    result = parse_simulation_start(
        simulation_start_utc="2026-07-15T16:20:00-06:00")
    assert result.isoformat() == '2026-07-15T22:20:00+00:00'


def test_simulation_clock_start_accepts_z_suffix():
    result = parse_simulation_start(
        simulation_start_utc="2026-07-15T22:20:00Z")
    assert result.isoformat() == '2026-07-15T22:20:00+00:00'


def test_simulation_clock_start_rejects_two_representations():
    with pytest.raises(ValueError):
        parse_simulation_start(
            simulation_start_utc="2026-07-15T22:20:00Z",
            simulation_start_epoch_unix=1784000000.0,
        )


def test_simulation_clock_start_required_by_replay():
    world, ecosystem = tiny_world_ecosystem()
    with pytest.raises(ValueError):
        build_mapped_replay(world, ecosystem, duration_s=60.0)


def test_simulation_clock_epoch_and_utc_agree():
    by_text = parse_simulation_start(
        simulation_start_utc="2026-07-15T22:20:00Z")
    by_epoch = parse_simulation_start(
        simulation_start_epoch_unix=by_text.timestamp())
    assert by_epoch == by_text


def test_simulation_clock_metadata_covers_the_run():
    meta = timestamp_metadata(
        parse_simulation_start(simulation_start_utc="2026-07-15T22:20:00Z"),
        7200.0,
    )
    assert meta['start_utc'] == '2026-07-15T22:20:00Z'
    assert meta['duration_s'] == 7200.0
    assert meta['end_epoch_unix'] - meta['start_epoch_unix'] == pytest.approx(7200.0, abs=0.5 * 10 ** -(7), rel=0)


def test_simulation_clock_local_epoch_round_trip():
    epoch = epoch_unix_for_local("2026-07-15", 16.5, -6.0)
    start = datetime.fromtimestamp(epoch, tz=timezone.utc)
    assert (start.day, start.hour, start.minute) == (15, 22, 30)


def test_simulation_clock_local_epoch_rejects_bad_hour():
    with pytest.raises(ValueError):
        epoch_unix_for_local("2026-07-15", 24.0, -6.0)


def test_simulation_clock_replay_document_carries_the_clock():
    world, ecosystem = tiny_world_ecosystem()
    doc = build_mapped_replay(
        world, ecosystem, simulation_start_utc="2026-07-15T22:20:00Z",
        duration_s=120.0, maximum_cell_m=25.0)
    assert doc['simulation_time']['start_utc'] == '2026-07-15T22:20:00Z'
    assert doc['forcing_time_reference']['start_epoch_unix'] == pytest.approx(doc['simulation_time']['start_epoch_unix'], abs=0.5 * 10 ** -(7), rel=0)
    assert 'air_temperature' in doc['weather_forcing']
    assert doc['parameter_notes']['simulation_time']['authority'] == 'UTC epoch timestamp'


def test_simulation_clock_sample_interval_below_time_step_rejected():
    world, ecosystem = tiny_world_ecosystem()
    with pytest.raises(ValueError):
        build_mapped_replay(
            world, ecosystem, **REPLAY_START,
            duration_s=60.0, dt_s=5.0, sample_s=2.0)



def test_weather_schedule_weather_times_include_exact_final_time():
    assert _weather_times(125.0, 60.0) == [0.0, 60.0, 120.0, 125.0]


def test_weather_schedule_weather_times_land_on_final_time():
    assert _weather_times(120.0, 60.0) == [0.0, 60.0, 120.0]


def test_weather_schedule_scheduled_air_temperature_is_used():
    ecosystem = {
        "clock_hour": 12.0,
        "weather": {
            "air_temperature_c": {
                "times_s": [0.0, 60.0],
                "values": [2.0, 12.0],
            }
        },
    }
    series, records = physical_weather(
        ecosystem, duration_s=120.0, interval_s=60.0)
    assert series.at(0.0) == pytest.approx(2.0, abs=0.5 * 10 ** -(7), rel=0)
    assert series.at(60.0) == pytest.approx(12.0, abs=0.5 * 10 ** -(7), rel=0)
    assert records[-1]['t_s'] == pytest.approx(120.0, abs=0.5 * 10 ** -(7), rel=0)
    assert records[0]['air_source'] == 'scheduled_weather.air_temperature_c'


def test_weather_schedule_authored_curve_still_used_without_schedule():
    _, records = physical_weather(
        {"clock_hour": 12.0, "weather": {}}, duration_s=60.0)
    assert records[0]['air_source'] == 'authored_diurnal_approximation'


def test_weather_schedule_budget_honors_scheduled_met():
    ecosystem = {
        "clock_hour": 12.0,
        "weather": {
            "relative_humidity": {"times_s": [0.0, 60.0],
                                  "values": [0.2, 0.9]},
            "wind_speed_mps": {"times_s": [0.0, 60.0],
                               "values": [1.0, 9.0]},
            "cloud_fraction": {"times_s": [0.0, 60.0],
                               "values": [0.0, 1.0]},
            "shortwave_w_m2": {"times_s": [0.0, 60.0],
                               "values": [100.0, 800.0]},
        },
    }
    spec = energy_met_series(ecosystem, duration_s=60.0,
                             interval_s=60.0)
    assert spec['rh']['values'][0] == pytest.approx(0.2, abs=0.5 * 10 ** -(7), rel=0)
    assert spec['rh']['values'][-1] == pytest.approx(0.9, abs=0.5 * 10 ** -(7), rel=0)
    assert spec['wind_mps']['values'][-1] == pytest.approx(9.0, abs=0.5 * 10 ** -(7), rel=0)
    assert spec['shortwave_w_m2']['values'][-1] == pytest.approx(800.0, abs=0.5 * 10 ** -(7), rel=0)
    assert spec['cloud']['values'][-1] == pytest.approx(1.0, abs=0.5 * 10 ** -(7), rel=0)


def test_weather_schedule_weather_configuration_rejects_out_of_range():
    ecosystem = {"weather": {"humidity": 1.4}}
    with pytest.raises(ValueError):
        validate_weather_configuration(ecosystem)


def test_weather_schedule_weather_configuration_rejects_bad_wind():
    with pytest.raises(ValueError):
        validate_weather_configuration({"weather": {"wind_xz_mps": [1.0]}})



def test_source_forcing_temperature_pulse_preserves_schedule():
    source = Series((0.0, 100.0), (60.0, 70.0))
    result = add_temperature_pulse(
        source, start_s=30.0, end_s=80.0, delta_c=10.0)
    assert result.times_s == (0.0, 30.0, 80.0, 100.0)
    assert result.at(0.0) == pytest.approx(60.0, abs=0.5 * 10 ** -(7), rel=0)
    assert result.at(30.0) == pytest.approx(70.0, abs=0.5 * 10 ** -(7), rel=0)
    assert result.at(50.0) == pytest.approx(70.0, abs=0.5 * 10 ** -(7), rel=0)
    assert result.at(80.0) == pytest.approx(60.0, abs=0.5 * 10 ** -(7), rel=0)


def test_source_forcing_temperature_pulse_follows_a_step_change():
    source = Series((0.0, 100.0), (62.0, 70.0))
    result = add_temperature_pulse(
        source, start_s=30.0, end_s=80.0, delta_c=10.0)
    assert result.at(10.0) == pytest.approx(62.0, abs=0.5 * 10 ** -(7), rel=0)
    assert result.at(60.0) == pytest.approx(72.0, abs=0.5 * 10 ** -(7), rel=0)
    assert result.at(120.0) == pytest.approx(70.0, abs=0.5 * 10 ** -(7), rel=0)


def test_source_forcing_temperature_pulse_requires_ordered_window():
    source = Series((0.0, 10.0), (60.0, 10.0))
    with pytest.raises(ValueError):
        add_temperature_pulse(source, start_s=80.0, end_s=30.0, delta_c=5.0)


def test_source_forcing_temperature_pulse_rejects_above_upper_guard():
    source = Series((0.0, 100.0), (60.0, 70.0))
    with pytest.raises(ValueError, match='upper guard'):
        add_temperature_pulse(
            source, start_s=30.0, end_s=80.0, delta_c=120.0)


def test_source_forcing_scheduled_source_flow_is_accepted():
    source = {
        "id": "source_a",
        "flow_m3s": {"times_s": [0.0, 60.0], "values": [1.0, 2.0]},
        "temperature_c": 20.0,
    }
    validate_source_record(source, "test source")
    from yellowstone_python.river.river_transport import Cell, River, Source
    river = River([Cell("c", 20.0, 2.0, 40.0, 20.0)], boundary_m3_s=1.0,
                  boundary_c=20.0, air_c=20.0,
                  sources=[Source("source_a", "c", Series.parse(source["flow_m3s"]), 20.0)])
    river.run(60.0, dt_s=1.0, sample_s=60.0)
    assert river.budget()["water_relative_residual"] < 1e-10
    assert river.budget()["heat_relative_residual"] < 1e-10


def test_source_forcing_scheduled_source_temperature_is_accepted():
    source = {
        "id": "source_a",
        "flow_m3s": 0.25,
        "temperature_c": {"times_s": [0.0, 900.0],
                          "values": [62.0, 80.0]},
    }
    validate_source_record(source, "test source")


def test_source_forcing_duplicate_reach_ids_rejected():
    world, ecosystem = tiny_world_ecosystem()
    ecosystem["river_reaches"] = [{"id": "a"}, {"id": "a"}]
    with pytest.raises(ValueError):
        build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0)


def test_source_forcing_mapped_replay_rejects_scheduled_source_flow():
    world, ecosystem = tiny_world_ecosystem()
    ecosystem["river_reaches"] = [{
        "id": "r1",
        "lateral_sources": [{
            "id": "src",
            "flow_m3s": {"times_s": [0.0], "values": [1.0]},
            "temperature_c": 20.0,
        }],
    }]
    with pytest.raises(ValueError):
        build_mapped_replay(world, ecosystem, **REPLAY_START, duration_s=60.0)


def test_source_forcing_feature_at_rejects_chainage_past_the_channel():
    world, _ = tiny_world_ecosystem()
    channel = Channel(firehole_chain(world))
    with pytest.raises(ValueError):
        channel.feature_at(channel.length_m + 1.0)


def test_source_forcing_feature_records_are_ordered_downstream():
    world, _ = tiny_world_ecosystem()
    channel = Channel(firehole_chain(world))
    starts = [record["start_s_m"] for record in channel._feature_records]
    assert starts == sorted(starts)



