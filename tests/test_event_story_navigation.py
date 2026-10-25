"""A complete story selector remains an original ALAS navigation page."""
import copy
import json
from pathlib import Path

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui

PAGE = 'UICamera/Canvas/UIMain/LevelMainScene(Clone)'
ROOT = PAGE + '/LevelSelectSPFullUI(Clone)'


def story_backend(total=2):
    backend = FakeBackend([
        make_button('back_button', PAGE + '/top/top_chapter/back_button', 58, 54),
        make_button('Switch', ROOT + '/Story/Battle/Switch', raycast_top=None),
        *[make_button(str(i), ROOT + '/Story/Nodes/Viewport/Content/' + str(i),
                      raycast_top=None) for i in range(1, total + 1)],
    ])
    backend.ui = make_ui([make_text(f'{total}/{total}', ROOT + '/Story/Desc/Digit')])
    return backend


@pytest.mark.parametrize('marker', ['EVENT_CHECK', 'SP_CHECK'])
@pytest.mark.parametrize('total', [2, 3])
def test_story_selector_is_a_page_without_becoming_a_battle_selector(marker, total):
    backend = story_backend(total)
    backend.ui['texts'].append(make_text('unrelated additive metadata', 'Other/label'))
    backend.ui['text_count'] += 1
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert adapter.appear(marker)
    assert not oracle.campaign_page_is_normal()
    assert not oracle.event_campaign_stage_selector_visible()
    with pytest.raises(SemanticGateClosed):
        oracle.event_campaign_page_state()
    assert not adapter.appear('CAMPAIGN_CHECK')
    assert not backend.taps


@pytest.mark.parametrize('damage', [
    'missing-switch', 'duplicate-switch', 'missing-progress', 'duplicate-progress',
    'count-mismatch', 'duplicate-node', 'covered-back', 'foreign-back', 'duplicate-back',
    'modal', 'preparation', 'mixed-battle', 'other-root', 'stale', 'foreground', 'incoherent',
])
def test_unproven_story_selector_remains_closed(damage):
    backend = story_backend()
    buttons = backend.buttons['buttons']
    if damage == 'missing-switch':
        buttons[:] = [b for b in buttons if b['name'] != 'Switch']
    elif damage == 'duplicate-switch':
        buttons.append(copy.deepcopy(buttons[1]))
    elif damage == 'missing-progress':
        backend.ui['texts'] = []
    elif damage == 'duplicate-progress':
        backend.ui['texts'].append(copy.deepcopy(backend.ui['texts'][0]))
    elif damage == 'count-mismatch':
        backend.ui['texts'][0]['text'] = '3/3'
    elif damage == 'duplicate-node':
        buttons[-1] = copy.deepcopy(buttons[-2])
    elif damage == 'covered-back':
        buttons[0]['raycast_top'] = False
    elif damage == 'foreign-back':
        buttons[0]['path'] = 'Other/' + buttons[0]['path']
    elif damage == 'duplicate-back':
        buttons.append(copy.deepcopy(buttons[0]))
    elif damage == 'modal':
        buttons.append(make_button('popup', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/popup'))
    elif damage == 'preparation':
        buttons.append(make_button('go', 'UICamera/Canvas/UIMain/LevelInfoSPUI(Clone)/panel/go'))
    elif damage == 'mixed-battle':
        buttons.append(make_button('Switch', ROOT + '/Battle/Mask/Story/Switch'))
    elif damage == 'other-root':
        buttons.append(make_button('Switch', 'Other/' + ROOT + '/Story/Battle/Switch'))
    elif damage == 'stale':
        backend.snapshot['age_ms'] = 1000000
    elif damage == 'foreground':
        backend.foreground = 'other.package/.OtherActivity'
    else:
        backend.ui['generation'] += 20
    backend.buttons['button_count'] = len(buttons)
    backend.ui['text_count'] = len(backend.ui['texts'])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    try:
        assert not adapter.appear('EVENT_CHECK')
    except SemanticGateClosed:
        pass
    assert not backend.taps


def test_retained_story_return_failure_is_a_complete_story_selector():
    path = Path(__file__).resolve().parents[1] / 'artifacts/full-feature-live-20261025/event-story-r1.json'
    if not path.exists():
        pytest.skip('private current story failure unavailable')
    retained = json.loads(path.read_text(encoding='utf-8'))['retained_immutable_frame']['frame']['projections']
    backend = FakeBackend(retained['buttons']['buttons'])
    ui = retained['ui']
    backend.ui = make_ui(ui['texts'], images=ui['images'], toggles=ui['toggles'])
    oracle = make_oracle(backend)
    assert oracle.event_story_page_state()[:2] == (26, 26)
    assert AlasSemanticAdapter(oracle, lambda: None).appear('EVENT_CHECK')
    assert not backend.taps
