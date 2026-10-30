"""Hidden render nodes don't erase a proved native selected-fleet model."""
import copy
import json
from pathlib import Path

import pytest

from alas_headless import SemanticGateClosed
from tests.test_opsi_question_fleet_relative import scene, PLANE
from tests.test_opsi_daemon_resource_radar import image


def model_scene():
    backend, oracle = scene()
    shadow = backend.ui['images'][-2]
    shadow.update(active_in_hierarchy=False, active_and_enabled=False)
    # This diagnostic projection is intentionally wrong and must be ignored.
    shadow['adb_point'] = dict(x=0, y=0)
    backend.ui['operation_siren_map_state'] = dict(
        schema_version=1, status=1, stage=5, truncated=False, stack_balanced=True,
        map_id=1022, active=True, valid=True, fleet_index=1, fleet_id=1,
        row=8, column=6, damage_known=True, damage_level=0,
        moving_known=False, moving=False, future_metadata='compatible')
    return backend, oracle


def test_hidden_fleet_model_selects_native_cell_and_retains_original_daemon_target():
    backend, oracle = model_scene()
    backend.ui['images'].reverse()
    backend.ui['images'].append(image('resource', 'exp', (0, -2)))
    # Radar direct event names are numeric, as in the actual game.
    backend.ui['images'][-1]['name'] = '10220151'
    backend.ui['images'][-1]['path'] = backend.ui['images'][-1]['path'].replace('resource', '10220151')
    backend.ui['image_count'] = len(backend.ui['images'])
    assert oracle.operation_siren_current_fleet_defeated() is False
    target = oracle.operation_siren_nearest_daemon_target()
    receipt = oracle.click_operation_siren_daemon_target(target)
    assert receipt.path == PLANE + 'quads/world_quad_6_6/walk_quad'
    assert backend.taps == [(640, 430)]


@pytest.mark.parametrize('key,value', [
    ('schema_version', True), ('status', 2), ('stack_balanced', False),
    ('truncated', True), ('active', False), ('valid', False),
    ('map_id', 0), ('fleet_id', 0), ('fleet_index', 2),
    ('row', True), ('row', -1), ('row', 8.0), ('column', None),
])
def test_inconsistent_model_cannot_authorize_hidden_fleet_input(key, value):
    backend, oracle = model_scene()
    backend.ui['operation_siren_map_state'][key] = value
    with pytest.raises(SemanticGateClosed, match='fleet model'):
        oracle.click_operation_siren_relative_grid((0, -2), fleet_relative=True)
    assert not backend.taps


@pytest.mark.parametrize('fault', ['missing_cell', 'duplicate_cell', 'moving'])
def test_model_still_requires_one_current_native_origin(fault):
    backend, oracle = model_scene()
    if fault == 'missing_cell':
        del backend.ui['images'][3]
    elif fault == 'duplicate_cell':
        backend.ui['images'].append(copy.deepcopy(backend.ui['images'][3]))
    else:
        backend.ui['operation_siren_map_state'].update(moving_known=True, moving=True)
    backend.ui['image_count'] = len(backend.ui['images'])
    with pytest.raises(SemanticGateClosed):
        oracle.click_operation_siren_relative_grid((0, -2), fleet_relative=True)
    assert not backend.taps


@pytest.mark.parametrize('change', [dict(damage_known=False), dict(damage_level=1), dict(damage_level=False)])
def test_hidden_fleet_without_zero_damage_proof_does_not_report_healthy(change):
    backend, oracle = model_scene()
    backend.ui['operation_siren_map_state'].update(change)
    with pytest.raises(SemanticGateClosed, match='map anchor is absent'):
        oracle.operation_siren_current_fleet_defeated()
    assert not backend.taps


def test_optional_model_failure_does_not_break_positive_legacy_shadow():
    backend, oracle = scene()
    backend.ui['operation_siren_map_state'] = dict(status=2)
    assert not oracle.operation_siren_current_fleet_defeated()
    assert oracle.click_operation_siren_relative_grid((0, -2), fleet_relative=True).path.endswith('world_quad_6_6/walk_quad')


def test_actual_observed_model_joins_a_native_grid_with_no_input():
    from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_ui
    path = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261025/world-map-model-observation-r1.json'
    if not path.exists():
        pytest.skip('private live model evidence unavailable')
    data = json.loads(path.read_text(encoding='utf-8'))
    raw = data['observed_immutable_frame']['frame']['projections']
    ui = raw['ui']
    backend = FakeBackend(raw['buttons']['buttons'])
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    backend.ui['operation_siren_map_state'] = ui['operation_siren_map_state']
    oracle = make_oracle(backend)
    model = oracle._operation_siren_selected_fleet_model(oracle.read_ui_state())
    assert model['row'] == 7 and model['column'] == 2 and model['damage_level'] == 0
    assert len([i for i in backend.ui['images'] if i['path'] == PLANE+'quads/world_quad_7_2/walk_quad'
                and i['active_in_hierarchy'] and i['active_and_enabled']]) == 1
    assert not oracle.operation_siren_current_fleet_defeated()
    assert not backend.taps
