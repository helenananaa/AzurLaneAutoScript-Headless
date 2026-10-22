"""Original unknown-page recovery uses this list's typed Home control."""
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import make_button
from tests.test_game_tips_loading_presence import host


def frozen_host(drift=False):
    backend, live, _ = host(drift, 'activity-archives-home-r158.json')
    oracle = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        backend.tap, live.fingerprint, frame_guard=lambda: None)
    adapter = AlasSemanticAdapter(live, lambda: None, frame_observation_oracle=lambda: oracle,
                                  input_frame_refresher=lambda: None)
    return backend, live, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_retained_activity_list_home_restores_main_without_archive_task_context(drift):
    backend, oracle, adapter = frozen_host(drift)
    assert adapter._goto_main_target() == 'archive/activity-list/home'
    assert adapter.appear('GOTO_MAIN') is True
    generation = backend.snapshot['generation']
    def arrive_main():
        backend.snapshot['generation'] = generation + 1
        backend.buttons['generation'] = generation + 1
        backend.buttons['buttons'] = [
            make_button('battle', 'UICamera/Canvas/UIOrigin/NewMainMellowTheme(Clone)/frame/right/1/battle'),
            make_button('formation', 'UICamera/Canvas/UIOrigin/NewMainMellowTheme(Clone)/frame/right/1/formation'),
        ]
        backend.buttons['button_count'] = 2
    backend.on_tap = arrive_main
    receipt = adapter.click('GOTO_MAIN')
    assert receipt.semantic_id == 'archive/activity-list/home'
    assert len(backend.taps) == 1
    assert oracle.main_page_visible()


@pytest.mark.parametrize('failure', ['duplicate', 'obscured', 'foreign', 'truncated',
                                    'wrong_sprite', 'image_obscured', 'wrong_bounds',
                                    'incoherent_ui', 'blocked'])
def test_invalid_activity_home_never_dispatches(failure):
    backend, oracle, adapter = frozen_host()
    home = next(b for b in backend.buttons['buttons'] if b['name'] == 'homeBtn')
    if failure == 'duplicate':
        backend.buttons['buttons'].append(dict(home))
        backend.buttons['button_count'] += 1
    elif failure == 'obscured':
        home['raycast_top'] = False
    elif failure == 'foreign':
        backend.snapshot['package'] = 'unrelated.package'
    elif failure == 'truncated':
        backend.buttons['truncated'] = True
    elif failure == 'blocked':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif failure == 'incoherent_ui':
        backend.ui['generation'] += 5
    else:
        image = next(i for i in backend.ui['images'] if i['path'] == home['path'])
        if failure == 'wrong_sprite':
            image['sprite'] = 'purchase_button'
        elif failure == 'image_obscured':
            image['raycast_top'] = False
        else:
            image['adb_bounds'] = dict(image['adb_bounds'], right=image['adb_bounds']['right'] + 1)
    with pytest.raises(SemanticGateClosed):
        adapter.click('GOTO_MAIN')
    assert not backend.taps


def test_home_return_does_not_require_unrelated_main_battle_actionability():
    backend, oracle, adapter = frozen_host()
    oracle.wait_for = Mock(side_effect=AssertionError('ALAS owns navigation completion'))
    def arrive():
        backend.snapshot['generation'] += 1
        backend.buttons['generation'] += 1
        backend.buttons['buttons'] = [
            make_button('battle', 'root/frame/right/1/battle', raycast_top=False),
            make_button('formation', 'root/frame/right/1/formation', raycast_top=False),
        ]
        backend.buttons['button_count'] = 2
    backend.on_tap = arrive
    assert adapter.click('GOTO_MAIN').semantic_id == 'archive/activity-list/home'
    assert oracle.main_page_visible()
    assert oracle.enabled('main/battle') is False
    assert len(backend.taps) == 1
