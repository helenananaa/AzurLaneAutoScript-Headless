import copy

import pytest

from alas_headless.semantic_oracle import SemanticGateClosed
from tests.test_campaign_preparation_art_compatibility import compatible_panel
from tests.semantic_support.observer_fixtures import make_oracle


ROOT = 'OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/'


def linear_panel(stage='t6'):
    """Current linear event structure, independent of account or captured data."""
    backend = compatible_panel('b3')
    for owner, key, count in (
        (backend.buttons, 'buttons', 'button_count'),
        (backend.ui, 'images', 'image_count'),
        (backend.ui, 'texts', 'text_count'),
    ):
        owner[key] = [v for v in owner[key] if not v['path'].startswith(ROOT+'panel/Difficulty/')]
        rows = [copy.deepcopy(v) for v in owner[key]
                if v['path'].startswith(ROOT+'panel/drops/frame/list/item(Clone)')]
        # One more complete reward row. Repeated fields remain count-bound.
        seen = set()
        for value in rows:
            if value['path'] not in seen:
                owner[key].append(value)
                seen.add(value['path'])
        owner[count] = len(owner[key])
    for value in backend.ui['texts']:
        if value['path'].endswith('/title_form/title_index'):
            value['text'] = stage.upper()
        if value['path'] == ROOT+'panel/Level/Text':
            value['text'] = 'LV 100'
        if value['path'] == ROOT+'panel/drops/frame/list/item/icon_bg/count':
            value['text'] = '180'
    return backend


@pytest.mark.parametrize('stage', ['t1', 't6', 't12'])
def test_linear_event_binds_stage_without_historical_level_or_reward_allowlist(stage):
    backend = linear_panel(stage)
    state = make_oracle(backend).campaign_preparation_state(stage)
    assert state.stage_code == stage
    assert state.oil_cost == 10 and state.remaining_attempts is None
    assert not backend.taps


@pytest.mark.parametrize('damage', [
    'different_underlay', 'duplicate_start', 'blocked_start', 'missing_reward_slice',
    'malformed_cost', 'malformed_progress', 'truncated_title', 'unexpected_mode_control',
])
def test_linear_compatibility_preserves_identity_action_and_complete_frame_boundaries(damage):
    backend = linear_panel()
    if damage == 'different_underlay':
        next(v for v in backend.ui['texts'] if '/Chapter_' in v['path']
             and v['path'].endswith('/title_index'))['text'] = 'T5'
    elif damage == 'duplicate_start':
        backend.buttons['buttons'].append(copy.deepcopy(next(v for v in backend.buttons['buttons'] if v['name'] == 'start_button')))
        backend.buttons['button_count'] += 1
    elif damage == 'blocked_start':
        next(v for v in backend.buttons['buttons'] if v['name'] == 'start_button')['raycast_top'] = False
    elif damage == 'missing_reward_slice':
        backend.ui['images'].pop()
        backend.ui['image_count'] -= 1
    elif damage in ('malformed_cost', 'malformed_progress'):
        suffix = 'panel/cost/text' if damage == 'malformed_cost' else 'panel/progress/Text/value'
        next(v for v in backend.ui['texts'] if v['path'] == ROOT+suffix)['text'] = 'unknown'
    elif damage == 'truncated_title':
        next(v for v in backend.ui['texts'] if v['path'] == ROOT+'panel/title_form/title_index')['flags'] |= 0x10
    else:
        control = copy.deepcopy(next(v for v in backend.buttons['buttons'] if v['name'] == 'start_button'))
        control.update(path=ROOT+'panel/Difficulty/Normal/Switch', name='Switch')
        backend.buttons['buttons'].append(control)
        backend.buttons['button_count'] += 1
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).campaign_preparation_state('t6')
    assert not backend.taps
