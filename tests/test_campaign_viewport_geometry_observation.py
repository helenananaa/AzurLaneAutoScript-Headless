"""Read-only viewport geometry rebinds; input retains its independent proof."""
import copy

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.campaign_fixtures import make_campaign_map_backend
from tests.semantic_support.observer_fixtures import make_oracle


def moving_camera():
    backend = make_campaign_map_backend()
    oracle = make_oracle(backend)
    state = oracle.campaign_map_state('12-4', columns=3, rows=2,
        land_cells=((1, 0),), expected_fleet_count=2)
    target = next(b for b in backend.buttons['buttons']
        if b['path'].endswith('chapter_cell_quad_1_1'))
    backend.snapshot['generation'] = backend.buttons['generation'] = 12
    target['raycast_top'] = True
    target['adb_point']['x'] += 20
    target['adb_bounds']['left'] += 20
    target['adb_bounds']['right'] += 20
    return backend, oracle, state, target


def test_viewport_lookup_returns_exact_current_geometry_after_game_recenter():
    backend, oracle, state, raw = moving_camera()
    target = oracle.campaign_map_cell_viewport_target(state, 'A1')
    assert target.point.x == raw['adb_point']['x']
    assert target.bounds.left == raw['adb_bounds']['left']
    assert target.path == raw['path']
    assert not backend.taps


@pytest.mark.parametrize('enemy_coverage', [False, True])
def test_same_geometry_change_does_not_authorize_any_grid_tap(enemy_coverage):
    backend, oracle, state, _ = moving_camera()
    with pytest.raises(SemanticGateClosed):
        oracle.click_campaign_map_cell(state, 'A1', allow_expected_enemy_coverage=enemy_coverage)
    assert not backend.taps


@pytest.mark.parametrize('bad', ['duplicate', 'foreign', 'stale', 'missing_geometry'])
def test_viewport_observation_still_rejects_invalid_current_target(bad):
    backend, oracle, state, target = moving_camera()
    if bad == 'duplicate':
        backend.buttons['buttons'].append(copy.deepcopy(target))
        backend.buttons['button_count'] += 1
    elif bad == 'foreign':
        backend.snapshot['package'] = 'other.package'
    elif bad == 'stale':
        backend.snapshot['age_ms'] = 100000
    else:
        target.pop('adb_bounds')
    with pytest.raises(SemanticGateClosed):
        oracle.campaign_map_cell_viewport_target(state, 'A1')
    assert not backend.taps
