"""Portable tests for new sidecar tools; never import or execute recovered games.

Quantitative fixtures are taken from recovered native conventions, including
Mono_Basin/tools/build_world.py:23-25; Osa ENGINEERING_AND_AUTHORING.md:71,99;
original Sierra tools/bake_world.gd:127; Atlas tools/bake_atlas.gd:491; and IR
ir/scale_frame.gd:23-28. Tests write only inside TemporaryDirectory instances.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[1]


def load_module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


coordinates = load_module('shared_coordinate_views', 'adapters/coordinate_views.py')
identities = load_module('shared_placement_ids', 'tools/enroll_placement_ids.py')


def fingerprint_without_ledger(document):
    payload = {key: value for key, value in document.items() if key != 'ledger_sha256'}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False,
                         separators=(',', ':'), allow_nan=False).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


class CoordinateViews(unittest.TestCase):
    def assert_xyz_close(self, actual, expected):
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=8)

    def test_native_angle_units_are_explicit(self):
        # Sierra prop rotation and Osa object yaw are degrees. Mojave rotation,
        # Atlas placement yaw, and Osa spawn_yaw are already radians.
        self.assertAlmostEqual(coordinates.yaw_radians(180, native_unit='degree'), math.pi)
        self.assertEqual(coordinates.yaw_radians(math.pi, native_unit='radian'), math.pi)
        self.assertAlmostEqual(coordinates.yaw_radians(18, native_unit='degree'), math.pi / 10)
        self.assertEqual(coordinates.yaw_radians(0.05, native_unit='radian'), 0.05)
        with self.assertRaises(ValueError):
            coordinates.yaw_radians(180, native_unit='guess')

    def test_osa_half_channel_width_and_full_trail_width(self):
        self.assertEqual(coordinates.full_width_metres(2.05, native_semantics='half_width'), 4.1)
        self.assertEqual(coordinates.full_width_metres(1.25, native_semantics='full_width'), 1.25)
        self.assertEqual(coordinates.full_width_metres(0, native_semantics='half_width'), 0)
        with self.assertRaises(ValueError):
            coordinates.full_width_metres(-1, native_semantics='half_width')
        with self.assertRaises(ValueError):
            coordinates.full_width_metres(1, native_semantics='width')

    def test_coast_affine_preserves_navd88_and_axis_sign(self):
        result = coordinates.projected_to_authored(
            source_enh=(588600, 4091100, 0.905),
            source_origin_enh=(588544, 4091136, 0),
            source_to_authored_basis=((1, 0, 0), (0, 0, 1), (0, -1, 0)),
            authored_origin_xyz=(0, 0, 0), frame_id='coast-utm10')
        self.assertEqual(result.xyz, (56, 0.905, 36))
        self.assertEqual(result.frame_id, 'coast-utm10')

    def test_affine_reflected_north_positive_frame_is_not_normalized(self):
        result = coordinates.projected_to_authored(
            source_enh=(510100, 4250200, 1703),
            source_origin_enh=(510000, 4250000, 1700),
            source_to_authored_basis=((1, 0, 0), (0, 0, 1), (0, 1, 0)),
            authored_origin_xyz=(10, 20, 30), frame_id='north-positive')
        self.assertEqual(result.xyz, (110, 23, 230))

    def test_mono_preserves_actual_native_linear_coefficients(self):
        zero = coordinates.mono_legacy_to_authored(-119.09, 37.90, 1900)
        self.assertEqual(zero.xyz, (0, 0, 0))
        point = coordinates.mono_legacy_to_authored(-119.08, 37.91, 2165.1)
        self.assert_xyz_close(point.xyz, (879.51596, 265.1, -1109.94595))
        # A UTM transform or common 111320*cos(latitude) approximation would
        # move this point and cannot replace the recovered conversion silently.
        self.assertEqual(point.frame_id, 'mono-basin-legacy')

    def test_ir_source_scale_and_native_entity_passthrough(self):
        result = coordinates.ir_source_to_authored(
            source_xyz=(610, 50, -590), source_origin_xyz=(10, 10, 10),
            game_origin_xyz=(100, 200, 300), horizontal_compression=60,
            vertical_compression=2, frame_id='ir-region')
        self.assertEqual(result.xyz, (110, 220, 290))
        native = coordinates.ir_entity_to_authored(game_xyz=result.xyz, frame_id='ir-region')
        self.assertEqual(native, result)
        with self.assertRaises(ValueError):
            coordinates.ir_source_to_authored(
                source_xyz=result, source_origin_xyz=(0, 0, 0),
                game_origin_xyz=(0, 0, 0), horizontal_compression=60,
                vertical_compression=2, frame_id='ir-region')

    def test_ir_legacy_floor_and_invalid_ratios(self):
        result = coordinates.ir_source_to_authored(
            source_xyz=(1, 1, 1), source_origin_xyz=(0, 0, 0),
            game_origin_xyz=(0, 0, 0), horizontal_compression=0.00001,
            vertical_compression=0.000001, frame_id='legacy-floor')
        self.assertEqual(result.xyz, (10000, 10000, 10000))
        for invalid in (0, -1, True, float('nan'), float('inf')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                coordinates.ir_source_to_authored(
                    source_xyz=(1, 1, 1), source_origin_xyz=(0, 0, 0),
                    game_origin_xyz=(0, 0, 0), horizontal_compression=invalid,
                    vertical_compression=1, frame_id='invalid')

    def test_rebase_subtracts_before_lossy_vector_conversion(self):
        point = coordinates.AuthoredPosition('large-frame', (1_000_000_000.125, 12, -999_999_999.5))
        origin = coordinates.AuthoredPosition('large-frame', (1_000_000_000, 0, -1_000_000_000))
        before = point.xyz
        self.assertEqual(coordinates.to_runtime(point, origin), (0.125, 12, 0.5))
        self.assertEqual(point.xyz, before)
        other = coordinates.AuthoredPosition('another-region', origin.xyz)
        with self.assertRaises(ValueError):
            coordinates.to_runtime(point, other)

    def test_groundwork_physical_range_decode(self):
        self.assertEqual(coordinates.groundwork_height_metres(0, height_offset_m=-0.01, height_range_m=0.03), -0.01)
        self.assertAlmostEqual(coordinates.groundwork_height_metres(65535, height_offset_m=-0.01, height_range_m=0.03), 0.02)
        for sample in (-1, 65536, True, 1.5, '1'):
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                coordinates.groundwork_height_metres(sample, height_offset_m=0, height_range_m=1)
        with self.assertRaises(ValueError):
            coordinates.groundwork_height_metres(10, height_offset_m=0, height_range_m=-1)

    def test_numeric_strings_booleans_and_nonfinite_components_rejected(self):
        for value in (True, '1.5', float('nan'), float('inf'), -float('inf'), 10 ** 400):
            with self.subTest(value=repr(value)[:30]), self.assertRaises(ValueError):
                coordinates.AuthoredPosition('frame', (value, 0, 0))
        for frame in ('', None, True, 12):
            with self.subTest(frame=frame), self.assertRaises(ValueError):
                coordinates.AuthoredPosition(frame, (0, 0, 0))

    def test_finite_inputs_cannot_emit_overflow_results(self):
        with self.assertRaises(ValueError):
            coordinates.full_width_metres(1e308, native_semantics='half_width')
        with self.assertRaises(ValueError):
            coordinates.groundwork_height_metres(65535, height_offset_m=1e308, height_range_m=1e308)
        with self.assertRaises(ValueError):
            coordinates.to_runtime(coordinates.AuthoredPosition('f', (1e308, 0, 0)),
                                   coordinates.AuthoredPosition('f', (-1e308, 0, 0)))
        with self.assertRaises(ValueError):
            coordinates.projected_to_authored(
                source_enh=(1e308, 0, 0), source_origin_enh=(-1e308, 0, 0),
                source_to_authored_basis=((1, 0, 0), (0, 1, 0), (0, 0, 1)),
                authored_origin_xyz=(0, 0, 0), frame_id='overflow')


class IdentityEnrollment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.source = self.directory / 'source.json'
        self.output = self.directory / 'identity.json'
        self.write_source({'instances': [{'id': 'pine_01', 'position': [1, 2, 3]}]})

    def write_source(self, document):
        self.source.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')

    def enroll(self, **kwargs):
        options = dict(pointer='/instances', world_id='world', namespace='region:plants', id_field='id')
        options.update(kwargs)
        return identities.enroll(self.source, self.output, **options)

    def write_sidecar(self, document, *, rehash=False):
        if rehash:
            document['ledger_sha256'] = fingerprint_without_ledger(document)
        self.output.write_text(json.dumps(document, ensure_ascii=False), encoding='utf-8')

    def test_native_identity_reuse_preserves_both_files_and_typed_id(self):
        self.write_source({'instances': [{'id': '001', 'p': [1, 2, 3]}, {'id': 7, 'p': [4, 5, 6]}]})
        source_before = self.source.read_bytes()
        first, created = self.enroll()
        self.assertTrue(created)
        output_before = self.output.read_bytes()
        second, created = self.enroll()
        self.assertFalse(created)
        self.assertEqual(first, second)
        self.assertEqual(self.source.read_bytes(), source_before)
        self.assertEqual(self.output.read_bytes(), output_before)
        self.assertEqual(first['entries'][0]['entity_ref']['id'], '001')
        self.assertEqual(first['entries'][1]['native_id'], 7)
        self.assertIs(type(first['entries'][1]['native_id']), int)

    def test_idless_identical_records_get_distinct_stable_identities(self):
        # Identical positions must not deduplicate authored individuals.
        self.write_source({'instances': [{'p': [1, 2, 3]}, {'p': [1, 2, 3]}]})
        first, created = self.enroll(id_field=None)
        self.assertTrue(created)
        assigned = [entry['entity_ref']['id'] for entry in first['entries']]
        self.assertEqual(len(set(assigned)), 2)
        self.assertTrue(all(uuid.UUID(value).version == 4 for value in assigned))
        second, created = self.enroll(id_field=None)
        self.assertFalse(created)
        self.assertEqual(first, second)

    def test_changed_source_bytes_require_reviewed_rebind(self):
        self.enroll()
        existing = self.output.read_bytes()
        self.source.write_bytes(self.source.read_bytes() + b'\n')
        with self.assertRaisesRegex(ValueError, 'different source revision'):
            self.enroll()
        self.assertEqual(self.output.read_bytes(), existing)

    def test_reordering_records_cannot_rebind_array_positions(self):
        self.write_source({'instances': [{'p': [1, 2, 3]}, {'p': [7, 8, 9]}]})
        self.enroll(id_field=None)
        existing = self.output.read_bytes()
        self.write_source({'instances': [{'p': [7, 8, 9]}, {'p': [1, 2, 3]}]})
        with self.assertRaises(ValueError):
            self.enroll(id_field=None)
        self.assertEqual(self.output.read_bytes(), existing)

    def test_duplicate_native_id_rejected_within_namespace_only(self):
        first, _ = self.enroll(namespace='tahoe:plants')
        second_output = self.directory / 'identity-other-region.json'
        second, _ = identities.enroll(self.source, second_output, pointer='/instances', world_id='world',
                                     namespace='feather:plants', id_field='id')
        self.assertEqual(first['entries'][0]['entity_ref']['id'], second['entries'][0]['entity_ref']['id'])
        self.assertNotEqual(first['entries'][0]['entity_ref'], second['entries'][0]['entity_ref'])
        self.output = self.directory / 'duplicate-identity.json'
        for values in (['pine', 'pine'], [1, '1']):
            with self.subTest(values=values):
                self.write_source({'instances': [{'id': value} for value in values]})
                with self.assertRaisesRegex(ValueError, 'Duplicate native ID'):
                    self.enroll()
                self.assertFalse(self.output.exists())

    def test_changed_namespace_or_world_cannot_reuse_sidecar(self):
        self.enroll()
        before = self.output.read_bytes()
        for arguments in ({'namespace': 'new-region'}, {'world_id': 'other-world'}, {'id_field': None}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                self.enroll(**arguments)
        self.assertEqual(self.output.read_bytes(), before)

    def test_source_output_alias_refused_without_mutation(self):
        before = self.source.read_bytes()
        with self.assertRaises(ValueError):
            identities.enroll(self.source, self.source, pointer='/instances', world_id='w', namespace='n', id_field='id')
        self.assertEqual(self.source.read_bytes(), before)

    def test_source_json_duplicate_keys_and_all_nonfinite_spellings_rejected(self):
        invalid = [b'{"instances":[],"instances":[]}', b'{"instances":[{"id":"a","id":"b"}]}']
        invalid += [b'{"instances":[],"unused_metadata":' + number + b'}'
                    for number in (b'NaN', b'Infinity', b'-Infinity', b'1e999', b'-1e999')]
        for data in invalid:
            with self.subTest(data=data):
                self.source.write_bytes(data)
                with self.assertRaises(ValueError):
                    self.enroll()
                self.assertEqual(self.source.read_bytes(), data)
                self.assertFalse(self.output.exists())

    def test_reused_sidecar_json_duplicate_keys_and_overflow_rejected(self):
        self.enroll()
        valid = self.output.read_bytes()
        for number in ('NaN', 'Infinity', '-Infinity', '1e999', '-1e999'):
            data = valid.decode('utf-8').replace('"notice":', '"unused":' + number + ',"notice":', 1)
            with self.subTest(number=number):
                self.output.write_text(data, encoding='utf-8')
                with self.assertRaises(ValueError):
                    self.enroll()
                self.assertEqual(self.output.read_text(encoding='utf-8'), data)
        self.output.write_bytes(valid.replace(b'"sidecar_version":', b'"sidecar_version":"0.1.0","sidecar_version":', 1))
        with self.assertRaises(ValueError):
            self.enroll()

    def test_bad_source_id_types_and_nonobject_records_rejected(self):
        for record in ({'id': True}, {'id': None}, {'id': 1.5}, {'id': ''}, {}, [], 'plant'):
            with self.subTest(record=record):
                self.write_source({'instances': [record]})
                with self.assertRaises(ValueError):
                    self.enroll()
                self.assertFalse(self.output.exists())

    def test_json_pointer_escaping_and_root_array(self):
        self.write_source({'a/b~c': [{'id': 'a'}]})
        result, _ = self.enroll(pointer='/a~1b~0c')
        self.assertEqual(result['entries'][0]['initial_json_pointer'], '/a~1b~0c/0')
        self.source = self.directory / 'array.json'
        self.output = self.directory / 'array-identity.json'
        self.write_source([{'id': 'root'}])
        result, _ = self.enroll(pointer='')
        self.assertEqual(result['entries'][0]['initial_json_pointer'], '/0')

    def test_invalid_pointer_cannot_alias_different_array_member(self):
        self.write_source({'groups': [{'rows': [{'id': 'first'}]}, {'rows': [{'id': 'last'}]}]})
        for pointer in ('/groups/-1/rows', '/groups/01/rows', '/groups/+1/rows', '/groups/2/rows',
                        '/groups/-/rows', '/groups/\u0661/rows', '/bad~2key', '/bad~', 'groups/0/rows'):
            with self.subTest(pointer=pointer), self.assertRaises(ValueError):
                self.enroll(pointer=pointer)
        self.assertFalse(self.output.exists())

    def test_edited_idless_identity_fingerprint_is_rejected(self):
        self.write_source({'instances': [{'p': [1, 2, 3]}]})
        result, _ = self.enroll(id_field=None)
        result['entries'][0]['entity_ref']['id'] = str(uuid.uuid4())
        self.write_sidecar(result)
        with self.assertRaisesRegex(ValueError, 'fingerprint'):
            self.enroll(id_field=None)

    def test_sidecar_semantics_are_validated_beyond_fingerprint(self):
        original, _ = self.enroll()
        mutations = [
            lambda d: d['entries'][0].update(record_sha256='0' * 64),
            lambda d: d['entries'][0].update(native_id='other'),
            lambda d: d['entries'][0].update(baseline_status='proposal'),
            lambda d: d['entries'][0].update(initial_json_pointer='/instances/-1'),
            lambda d: d['entries'][0]['entity_ref'].update(namespace='other'),
            lambda d: d['entries'][0]['entity_ref'].update(id='another'),
            lambda d: d.update(entries={}),
            lambda d: d.update(entries=[None]),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                value = deepcopy(original)
                mutate(value)
                self.write_sidecar(value, rehash=True)
                with self.assertRaises(ValueError):
                    self.enroll()

    def test_typed_native_id_bool_cannot_equal_integer_on_reuse(self):
        self.write_source({'instances': [{'id': 1}]})
        result, _ = self.enroll()
        result['entries'][0]['native_id'] = True
        self.write_sidecar(result, rehash=True)
        with self.assertRaisesRegex(ValueError, 'typed native ID'):
            self.enroll()

    def test_invalid_idless_uuid_rejected_even_with_recomputed_fingerprint(self):
        self.write_source({'instances': [{'p': [1, 2, 3]}]})
        original, _ = self.enroll(id_field=None)
        for value in ('legacy-index-0', str(uuid.uuid1()), original['entries'][0]['entity_ref']['id'].upper()):
            with self.subTest(value=value):
                modified = deepcopy(original)
                modified['entries'][0]['entity_ref']['id'] = value
                self.write_sidecar(modified, rehash=True)
                with self.assertRaises(ValueError):
                    self.enroll(id_field=None)

    def test_existing_document_shape_errors_fail_closed(self):
        for value in ([], None, 3, {'sidecar_version': '0.1.0'}):
            with self.subTest(value=value):
                self.write_sidecar(value)
                with self.assertRaises(ValueError):
                    self.enroll()

    def test_exclusive_publication_preserves_racing_output(self):
        source_before = self.source.read_bytes()
        def raced_publication(source_path, target_path):
            Path(target_path).write_bytes(b'created by another writer')
            raise FileExistsError('another sidecar appeared before commit')
        with patch.object(identities.os, 'link', side_effect=raced_publication):
            with self.assertRaises(FileExistsError):
                self.enroll()
        self.assertEqual(self.output.read_bytes(), b'created by another writer')
        self.assertEqual(self.source.read_bytes(), source_before)
        self.assertFalse(list(self.directory.glob('.identity.json.*')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
