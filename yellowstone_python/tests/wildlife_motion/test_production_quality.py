"""Source-bound rig and final-surface gates preserve accepted output bytes."""
import copy
import json

import pytest

from tools.build_wildlife_motion_assets import _animate, build
from yellowstone_python.wildlife_motion.gltf import read_glb
from yellowstone_python.wildlife_motion.quality import serialized_surface_report, evaluate_surface_budget
from yellowstone_python.wildlife_motion.rigging import prepare
from yellowstone_python.wildlife_motion.species import get_profile
from yellowstone_python.wildlife_motion.synthetic import mammal_proxy


def test_production_requires_review_before_mutating_the_output(tmp_path):
    target = tmp_path/'accepted.glb'
    target.write_bytes(b'previous accepted derivative')
    with pytest.raises(ValueError, match='source-bound reviewed rig'):
        _animate(mammal_proxy(), 'gray_wolf', target)
    assert target.read_bytes() == b'previous accepted derivative'
    with pytest.raises(ValueError, match='review-manifest'):
        build(tmp_path/'sources', tmp_path/'badger.glb', tmp_path/'world')
    assert not (tmp_path/'world').exists()


def test_wrong_source_reviewed_rig_is_refused(tmp_path):
    asset = mammal_proxy()
    _, skeleton = prepare(asset, get_profile('gray_wolf'))
    rig = skeleton.to_dict()
    rig['metadata'].update(review_status='reviewed', source_sha256='0'*64)
    with pytest.raises(ValueError, match='different source mesh'):
        _animate(asset, 'gray_wolf', tmp_path/'wrong.glb', review_assets={asset.source_sha256:{'rig':rig}})
    assert not (tmp_path/'wrong.glb').exists()


def test_development_export_keeps_resolved_rig_controls_and_exact_surface_hash(tmp_path):
    asset = mammal_proxy()
    _, skeleton = prepare(asset, get_profile('gray_wolf'))
    rig = skeleton.to_dict()
    rig['metadata']['review_status'] = 'reviewed'
    phases = {'FL':.1, 'FR':.6, 'HL':.3, 'HR':.8}
    path = tmp_path/'development.glb'
    manifest, _ = _animate(asset, 'gray_wolf', path, allow_unreviewed_development=True,
        review_assets={asset.source_sha256:{'rig':rig,'controls':{'Walk':{'touchdown_phases':phases}}}})
    document, _ = read_glb(path)
    walk = next(clip for clip in document['animations'] if clip['name']=='Walk')
    assert walk['extras']['wildlife_motion']['controls']['touchdown_phases'] == phases
    assert document['extras']['wildlife_motion']['rig']['rest'] == rig['rest']
    report = serialized_surface_report(path, samples=5)
    quality = json.loads(path.with_suffix('.quality.json').read_text())
    assert quality['surface']['asset_sha256'] == report['asset_sha256']
    assert manifest['production_quality']['status'] == 'unaccepted_development'
    budget = {'maximum_edge_stretch_p99':0., 'maximum_stance_surface_slip_height_per_s':0.,
        'maximum_stance_surface_distance_height':0., 'maximum_loop_error_height':0.}
    assert evaluate_surface_budget(report, budget)['passed'] is False
    unavailable = copy.deepcopy(report)
    unavailable['modes']['Walk']['stance_surface_slip_height_per_s'] = None
    assert evaluate_surface_budget(unavailable, budget)['passed'] is False


def test_preanimated_import_requires_selected_controls_and_landmarks(tmp_path):
    from tools.build_wildlife_motion_assets import check_preanimated_review
    asset = mammal_proxy()
    _, skeleton = prepare(asset, get_profile('gray_wolf'))
    rig = skeleton.to_dict()
    rig['metadata']['review_status'] = 'reviewed'
    review = {'rig':rig, 'controls':{'Walk':{'frequency_hz':1.4}}}
    path = tmp_path/'selected.glb'
    _animate(asset, 'gray_wolf', path, allow_unreviewed_development=True,
             review_assets={asset.source_sha256:review})
    document, _ = read_glb(path)
    check_preanimated_review(document, review)
    wrong = copy.deepcopy(review)
    wrong['controls']['Walk']['frequency_hz'] = 1.6
    with pytest.raises(ValueError, match='clip controls differ'):
        check_preanimated_review(document, wrong)
    wrong = copy.deepcopy(review)
    wrong['rig']['rest'][0][0] += .1
    with pytest.raises(ValueError, match='selected reviewed rig'):
        check_preanimated_review(document, wrong)
