"""Canonical interchange crosses both maintained tree writers and final meshes."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.tree_architecture import main
from yellowstone_python.authoring.tree_library import SCHEMA, canonical_library, read_library


def authoring_module():
    """Load the production mesh author outside its command-line entry point."""
    path = Path(__file__).resolve().parents[2]/'yellowstone_midway/tools/author_lodgepole.py'
    spec = importlib.util.spec_from_file_location('tree_mesh_author', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_both_writers_cross_the_same_reader_and_unknown_versions_refuse(tmp_path):
    out = tmp_path/'standalone.json'
    main(['--height-m','5','--dbh-m','.1','--crown-radius-m','1','--crown-ratio','.7','--out',str(out)])
    standalone = read_library(out)
    current = Path(__file__).resolve().parents[2]/'yellowstone_midway/assets/imported/lodgepole/architecture_library.json'
    mesh_library = read_library(current)
    assert standalone['schema'] == mesh_library['schema'] == SCHEMA
    assert set(standalone['variants'][0]) == set(mesh_library['variants'][0])
    assert standalone['variants'][0]['representation']['units'] == 'm'
    bad = copy.deepcopy(standalone)
    bad['schema'] = 'yellowstone.tree_architecture_library.v999'
    with pytest.raises(ValueError, match='Unsupported'):
        canonical_library(bad)


def test_selected_parameter_library_changes_final_geometry_and_retains_identity(tmp_path):
    author = authoring_module()
    results = []
    for spacing in (.5, 1.4):
        parameters = tmp_path/('parameters_'+str(spacing)+'.json')
        parameters.write_text(json.dumps({'whorl_spacing_m':spacing}))
        library = tmp_path/('architecture_'+str(spacing)+'.json')
        main(['--height-m','5','--dbh-m','.1','--crown-radius-m','1','--crown-ratio','.7',
              '--identity','fixed_tree','--variants','1','--parameters',str(parameters),'--out',str(library)])
        original = library.read_bytes()
        result = author.export_selected_architecture(library, 'fixed_tree:0', tmp_path/('mesh_'+str(spacing)))
        assert library.read_bytes() == original
        assert result['variant_id'] == 'fixed_tree:0' and result['render_transform'] == 'identity'
        assert all(row['final_attachment_checks']['maximum_gap_m'] == 0 for row in result['representations'])
        results.append(result)
    assert results[0]['representations'][0]['geometry_sha256'] != results[1]['representations'][0]['geometry_sha256']
    assert results[0]['source_graph']['parameters']['whorl_spacing_m'] == .5


def test_installed_commands_offer_help_from_outside_the_checkout(tmp_path):
    for module in ['tools.gen_flora','yellowstone_python.authoring.gen_flora','tools.tree_architecture',
                   'tools.blender_wildlife_decimate','yellowstone_python.wildlife_motion']:
        result = subprocess.run([sys.executable,'-m',module,'--help'],cwd=tmp_path,text=True,capture_output=True,timeout=30)
        assert result.returncode == 0 and 'usage:' in result.stdout, result.stdout+result.stderr


def test_middle_lods_share_source_graph_and_report_missing_source_traits():
    import numpy as np
    from tools.tree_architecture import display_distribution_report
    author = authoring_module()
    levels = [author.build_tree(author.ARCHETYPES['dense'], level, 4381) for level in range(3)]
    assert len({level[1]['source_graph_sha256'] for level in levels}) == 1
    assert len({level[1]['architecture_shoots'] for level in levels}) == 1
    assert levels[0][1]['needle_cards'] > levels[1][1]['needle_cards'] > levels[2][1]['needle_cards']
    axes = []
    for surfaces, _ in levels:
        branches = surfaces[1]
        centers = {}
        for tube in branches.tubes:
            if tube['parent'] != 'stem':
                continue
            start = tube['offset']
            count = tube['rings'] * (tube['sides'] + 1)
            rings = np.asarray(branches.positions[start:start + count]).reshape(tube['rings'], tube['sides'] + 1, 3)
            centers[tube['identity']] = rings[:, :-1].mean(axis=1)
        axes.append(centers)
    assert axes[0].keys() == axes[1].keys() == axes[2].keys()
    for identity in axes[0]:
        np.testing.assert_allclose(axes[0][identity], axes[1][identity], atol=1e-12)
        np.testing.assert_allclose(axes[0][identity], axes[2][identity], atol=1e-12)
    assert levels[0][1]['triangles'] > levels[1][1]['triangles'] > levels[2][1]['triangles']
    report = display_distribution_report([{'id':'small','height_m':5.,'crown_ratio':.3},
                                          {'id':'tall','height_m':18.,'variant':0}], 'runtime')
    assert report['archetype_counts'] == {'sapling':1, 'edge':1}
    assert report['source']['dbh_m']['status'] == 'unavailable'
    assert report['display']['crown_ratio']['p05'] < .4
