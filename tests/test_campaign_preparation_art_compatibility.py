import copy
import pytest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.campaign_fixtures import make_live_eventsp_map_preparation_backend
from tests.semantic_support.observer_fixtures import make_button, make_oracle


def compatible_panel(profile):
    backend = make_live_eventsp_map_preparation_backend(profile=profile)
    root = 'OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/'
    backend.buttons['buttons'].append(make_button('auto_button', root+'panel/auto_button', raycast_top=None))
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    auto_image = copy.deepcopy(next(v for v in backend.ui['images'] if v['path'] == root+'panel/start_button'))
    auto_image.update(path=root+'panel/auto_button', name='auto_button', sprite='btn_auto')
    backend.ui['images'].append(auto_image)
    backend.ui['image_count'] = len(backend.ui['images'])
    for image in backend.ui['images']:
        if image['path'] == root+'panel/start_button':
            image['sprite'] = 'btn_start'
        if image['path'] == root+'panel/head/Image' or image['path'].startswith(root+'panel/drops/'):
            image['sprite'] = 'new_event_art'
    return backend


def current_sp_panel():
    backend = make_live_eventsp_map_preparation_backend(profile='sp')
    root = 'OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/'
    for records in (backend.buttons['buttons'], backend.ui['images']):
        button = next(v for v in records if v['path'] == root+'panel/start_button')
        button.update(path=root+'panel/start_button_l', name='start_button_l')
    drop = 'panel/drops/frame/list/item(Clone)'
    for records, key, suffixes in (
        (backend.buttons['buttons'], 'button_count', ['']),
        (backend.ui['texts'], 'text_count', ['/icon_bg/count']),
        (backend.ui['images'], 'image_count', ['/icon_bg', '/icon_bg/frame', '/icon_bg/icon']),
    ):
        for suffix in suffixes:
            records.append(copy.deepcopy(next(v for v in records if v['path'] == root+drop+suffix)))
        (backend.buttons if key == 'button_count' else backend.ui)[key] = len(records)
    counts = [v for v in backend.ui['texts'] if v['path'] == root+drop+'/icon_bg/count']
    counts[-1]['text'] = '800'
    next(v for v in backend.ui['texts'] if v['path'] == root+'panel/drops/frame/list/item/icon_bg/count')['text'] = '5'
    return backend


def test_current_sp_alternate_start_and_additional_reward_row():
    backend = current_sp_panel()
    state = make_oracle(backend).campaign_preparation_state('sp')
    assert state.proceed_button.name == 'start_button_l'
    assert state.remaining_attempts == 1
    assert not backend.taps


@pytest.mark.parametrize('damage', ['duplicate_start', 'missing_row_image', 'reward_text'])
def test_current_sp_still_rejects_ambiguous_action_or_partial_reward_slice(damage):
    backend = current_sp_panel()
    if damage == 'duplicate_start':
        value = copy.deepcopy(next(v for v in backend.buttons['buttons'] if v['name'] == 'start_button_l'))
        value.update(path=value['path'].replace('start_button_l', 'start_button'), name='start_button')
        backend.buttons['buttons'].append(value)
        backend.buttons['button_count'] += 1
    elif damage == 'missing_row_image':
        backend.ui['images'].pop()
        backend.ui['image_count'] -= 1
    else:
        next(v for v in backend.ui['texts'] if v['path'].endswith('item(Clone)/icon_bg/count'))['text'] = '购买'
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).campaign_preparation_state('sp')
    assert not backend.taps


@pytest.mark.parametrize('profile', ['sp', 'b3', 'd3'])
def test_additive_auto_control_and_new_art_preserve_stage_and_dispatch_no_input(profile):
    backend = compatible_panel(profile)
    state = make_oracle(backend).campaign_preparation_state(profile)
    assert state.stage_code == profile and state.oil_cost == 10
    assert not backend.taps


def test_new_event_numeric_node_id_keeps_exact_stage_text_binding():
    backend = compatible_panel('b3')
    old = next(v['path'] for v in backend.buttons['buttons'] if '/Battle/Nodes/Chapter_' in v['path'] and v['name'] == 'main')
    import re
    old_node = re.search(r'Chapter_[0-9]+', old).group()
    for group in (backend.buttons['buttons'], backend.ui['images'], backend.ui['texts'], backend.ui['toggles']):
        for value in group:
            value['path'] = value['path'].replace(old_node, 'Chapter_2060006')
    assert make_oracle(backend).campaign_preparation_state('b3').stage_code == 'b3'
    assert not backend.taps


@pytest.mark.parametrize('hit', [True, False])
def test_native_top_hit_is_valid_and_obscured_control_still_rejected(hit):
    backend = compatible_panel('b3')
    control = next(v for v in backend.buttons['buttons'] if v['path'].endswith('/Loop/Toggle'))
    control['raycast_top'] = hit
    if hit:
        assert make_oracle(backend).campaign_preparation_state('b3').stage_code == 'b3'
    else:
        with pytest.raises(SemanticGateClosed):
            make_oracle(backend).campaign_preparation_state('b3')
    assert not backend.taps


@pytest.mark.parametrize('damage', ['duplicate_auto', 'missing_auto_image', 'unknown_start', 'wrong_stage'])
def test_compatible_art_does_not_admit_ambiguous_control_or_changed_stage(damage):
    backend = compatible_panel('d3')
    root = 'OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/'
    if damage == 'duplicate_auto':
        backend.buttons['buttons'].append(copy.deepcopy(backend.buttons['buttons'][-1]))
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    if damage == 'missing_auto_image':
        backend.ui['images'] = [v for v in backend.ui['images'] if v['path'] != root+'panel/auto_button']
        backend.ui['image_count'] = len(backend.ui['images'])
    if damage == 'unknown_start':
        next(v for v in backend.ui['images'] if v['path'] == root+'panel/start_button')['sprite'] = 'unreviewed'
    if damage == 'wrong_stage':
        next(v for v in backend.ui['texts'] if v['path'] == root+'panel/title_form/title_index')['text'] = 'D2'
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).campaign_preparation_state('d3')
    assert not backend.taps
