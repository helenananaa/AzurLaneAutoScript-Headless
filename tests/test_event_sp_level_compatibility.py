"""SP enemy level is observed data, while stage and input identity remain bound."""
import copy

import pytest

from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.campaign_fixtures import make_live_eventsp_map_preparation_backend
from tests.semantic_support.observer_fixtures import make_oracle


ROOT = 'OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/'


def sp_panel(level):
    backend = make_live_eventsp_map_preparation_backend()
    next(value for value in backend.ui['texts']
         if value['path'] == ROOT+'panel/Level/Text')['text'] = level
    return backend


@pytest.mark.parametrize('level', ['LV 110', 'LV 105', 'LV 125'])
def test_sp_level_drift_preserves_exact_stage_and_observed_cost(level):
    backend = sp_panel(level)
    state = make_oracle(backend).campaign_preparation_state('sp')
    assert state.stage_code == 'sp' and state.kind == 'map'
    assert state.oil_cost == 10 and state.remaining_attempts == 1
    assert not backend.taps


@pytest.mark.parametrize('level', ['', 'unknown', 'LV 0', 'LV -1', 'LV 10x', 'LV 1.5'])
def test_sp_malformed_level_cannot_reach_input(level):
    backend = sp_panel(level)
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).click_campaign_map_preparation('sp')
    assert not backend.taps


@pytest.mark.parametrize('damage', [
    'detail_stage', 'underlay_stage', 'duplicate_level', 'truncated_level', 'blocked_proceed',
])
def test_sp_level_drift_does_not_relax_identity_or_complete_actionable_surface(damage):
    backend = sp_panel('LV 105')
    level = next(value for value in backend.ui['texts']
                 if value['path'] == ROOT+'panel/Level/Text')
    if damage == 'detail_stage':
        next(value for value in backend.ui['texts']
             if value['path'] == ROOT+'panel/title_form/title_index')['text'] = 'T6'
    elif damage == 'underlay_stage':
        next(value for value in backend.ui['texts']
             if '/Chapter_' in value['path'] and value['path'].endswith('/title_index'))['text'] = 'T6'
    elif damage == 'duplicate_level':
        backend.ui['texts'].append(copy.deepcopy(level))
        backend.ui['text_count'] += 1
    elif damage == 'truncated_level':
        level['flags'] |= 0x10
    else:
        next(value for value in backend.buttons['buttons']
             if value['path'] == ROOT+'panel/start_button')['raycast_top'] = False
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).click_campaign_map_preparation('sp')
    assert not backend.taps
