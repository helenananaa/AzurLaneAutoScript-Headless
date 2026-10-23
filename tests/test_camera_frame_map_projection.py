"""Real frozen endpoint parsing needs no impossible second generation."""
from unittest.mock import Mock

import pytest

from alas_headless.adapter import SemanticFrameReader
from alas_headless import SemanticGateClosed
from tests.test_adapter_frame import REVISION, make_clock
from tests.semantic_support.campaign_fixtures import make_campaign_map_backend


PARAMETERS = dict(columns=3, rows=2, land_cells=((1, 0),), expected_fleet_count=2)


def frozen_map(*, moving=False, missing_geometry=None):
    backend = make_campaign_map_backend(generations=(10,))
    handle, _, clock = make_clock()
    handle.snapshot = backend.snapshot
    handle.buttons = backend.buttons
    handle.ui = backend.ui
    if missing_geometry:
        cell = next(button for button in handle.buttons['buttons'] if '/quads/' in button['path'])
        cell.pop('adb_' + missing_geometry)
    if moving:
        anchor = next(image for image in handle.ui['images']
            if image['path'].endswith('cell_fleet_one/ammo/bg'))
        anchor['anchor_world_position']['x'] += 0.5
    for payload in (handle.snapshot, handle.buttons, handle.ui):
        payload['driver_revision'] = REVISION
        payload['pid'] = handle.pid
    clock.acquire(include_ui=True)
    return handle, clock, SemanticFrameReader(clock, clock._oracle).oracle()


def test_camera_map_parses_one_real_frame_and_reuses_it_without_transport_or_sleep():
    handle, _, oracle = frozen_map()
    requests = list(handle.requests)
    oracle._sleep = Mock(side_effect=AssertionError('cannot wait for another immutable frame'))
    state = oracle.campaign_map_observation('12-4', **PARAMETERS)
    assert state.generation == 10
    assert len(state.cells) == 5
    assert oracle.campaign_map_observation('12-4', **PARAMETERS).signature == state.signature
    assert handle.requests == requests
    assert handle.taps == []


def test_moving_fleet_has_no_invented_grid_and_remains_refused_for_input():
    handle, _, oracle = frozen_map(moving=True)
    with pytest.raises(SemanticGateClosed, match='anchor is unmatched'):
        oracle.campaign_map_observation('12-4', **PARAMETERS)
    with pytest.raises(SemanticGateClosed):
        oracle.campaign_map_state('12-4', **PARAMETERS)
    assert handle.taps == []


@pytest.mark.parametrize('missing', ['point', 'bounds'])
def test_missing_cell_geometry_never_produces_a_partial_view_or_input_state(missing):
    handle, _, oracle = frozen_map(missing_geometry=missing)
    with pytest.raises(SemanticGateClosed):
        oracle.campaign_map_observation('12-4', **PARAMETERS)
    with pytest.raises(SemanticGateClosed):
        oracle.campaign_map_state('12-4', **PARAMETERS)
    assert not handle.taps


def test_input_map_stability_still_rejects_a_single_unchanging_generation():
    handle, _, oracle = frozen_map()
    with pytest.raises(SemanticGateClosed, match='did not stabilize'):
        oracle.campaign_map_state('12-4', **PARAMETERS)
    assert handle.taps == []


@pytest.mark.parametrize('change', ['land', 'fleet_count'])
def test_frozen_map_observation_keeps_topology_and_typed_identity_checks(change):
    handle, _, oracle = frozen_map()
    params = dict(PARAMETERS)
    if change == 'land':
        params['land_cells'] = ((1, 0), (1, 0))
    else:
        params['expected_fleet_count'] = 1
    with pytest.raises(SemanticGateClosed):
        oracle.campaign_map_observation('12-4', **params)
    assert handle.taps == []
