"""The input port returns its receipt while native ui_goto owns Main proof."""
import json
from pathlib import Path

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.midmap_replay import ReplayRuntime, REVISION
from tests.semantic_support.observer_fixtures import make_button
from tests.test_game_tips_loading_presence import host
from alas_headless import AlasSemanticUnmapped


@pytest.mark.parametrize('drift', [False, True])
def test_reviewed_back_does_not_wait_for_or_manufacture_main(drift):
    data = json.loads((Path(__file__).parent / 'fixtures/exercise-inherited-home-r157.json').read_text(encoding='utf8'))
    if drift:
        data['buttons']['buttons'].reverse()
        data['ui']['optional_metadata'] = {'new': True}
    runtime = ReplayRuntime({'state': {'protocol_schema': data['snapshot']['protocol_schema'],
        'status': 'ok', 'snapshot': data['snapshot'], 'buttons': data['buttons']}, 'ui': data['ui']})
    runtime.on_input = lambda x, y: None  # Delayed destination: still Exercise.
    session = AlasSemanticSession(runtime_handle=runtime, driver_revision=REVISION)
    try:
        session.refresh_frame()
        assert session.open()._frame_or_live_observation_oracle().exercise_page_visible()
        receipt = session.click('GOTO_MAIN')
        assert receipt.semantic_id == 'exercise/page/back'
        assert receipt.path.endswith('/MilitaryExerciseUI(Clone)/blur_panel/adapt/top/backBtn')
        assert len(runtime.actions) == 1
        for name in ('GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3', 'GET_SHIP'):
            assert session.appear(name) is False
        session.refresh_frame()
        assert not session.open()._frame_or_live_observation_oracle().main_page_visible()
        assert session.open()._frame_or_live_observation_oracle().exercise_page_visible()
    finally:
        session.close()


@pytest.mark.parametrize('case', ['foreign', 'stale', 'truncated', 'ambiguous-back', 'missing-count'])
def test_inherited_exercise_popup_absence_requires_complete_unobscured_page(case):
    backend, _, adapter = host(fixture='exercise-inherited-home-r157.json')
    if case == 'foreign':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'stale':
        backend.snapshot['age_ms'] = 10001
    elif case == 'truncated':
        backend.buttons['truncated'] = True
    elif case == 'ambiguous-back':
        back = next(b for b in backend.buttons['buttons'] if b['name'] == 'backBtn')
        backend.buttons['buttons'].append(dict(back))
        backend.buttons['button_count'] += 1
    else:
        backend.ui['texts'] = [t for t in backend.ui['texts'] if not t['path'].endswith('/season_info/count')]
        backend.ui['text_count'] = len(backend.ui['texts'])
    with pytest.raises((SemanticGateClosed, AlasSemanticUnmapped)):
        adapter._appear_once('GET_ITEMS_1')
    assert not backend.taps
