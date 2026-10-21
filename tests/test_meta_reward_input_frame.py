"""Completed beacon proof and input use one prepared fresh frame."""
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from tests.test_frame_post_input_foreground import session_for_meta
from tests.semantic_support.observer_fixtures import make_button, make_ui


@pytest.mark.parametrize('drift', [False, True])
def test_actual_completed_beacon_claim_reuses_prepared_frame_and_native_award_observation(drift):
    backend, session, _ = session_for_meta('meta-completed-reward-r351.json')
    session.begin_meta_beacon()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.buttons['optional_upstream_metadata'] = 'additive'
    live = session.open().oracle
    live.click_meta_current_reward = Mock(side_effect=AssertionError('split live reward proof'))
    live.meta_current_detail_state = Mock(side_effect=AssertionError('split live detail'))
    ordinal = session._frame_clock._ordinal
    def rewarded():
        assert session._frame_clock.current_frame_id is None
        generation = backend.snapshot['generation']+1
        backend.buttons['buttons'] = [make_button('close',
            'OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close')]
        backend.buttons['button_count'] = 1
        backend.ui = make_ui([])
        for p in (backend.snapshot, backend.buttons, backend.ui):
            p['generation'] = generation
            p['pid'] = live.fingerprint.expected_pid
            p['driver_revision'] = live.fingerprint.driver_revision
    backend.on_tap = rewarded
    receipt = session.click('BEACON_REWARD')
    assert receipt.semantic_id == 'meta/current/reward'
    assert live.input_dispatch_count == len(backend.taps) == 1
    assert session._frame_clock._ordinal == ordinal+1
    live.click_meta_current_reward.assert_not_called()
    live.meta_current_detail_state.assert_not_called()
    assert session.appear('GET_ITEMS_1')


@pytest.mark.parametrize('damage', ['hp', 'sprite', 'duplicate', 'blocker', 'foreign'])
def test_reward_input_frame_keeps_complete_beacon_and_identity_guards(damage):
    backend, session, _ = session_for_meta('meta-completed-reward-r351.json')
    session.begin_meta_beacon()
    if damage == 'hp':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/hp/Text'))['text'] = '1/<color=#E31D15>1820000</color>'
    elif damage == 'sprite':
        next(i for i in backend.ui['images'] if i['path'].endswith('/btns/award_btn'))['sprite'] = 'unknown'
    elif damage == 'duplicate':
        backend.buttons['buttons'].append(dict(next(b for b in backend.buttons['buttons']
            if b['path'].endswith('/btns/award_btn'))))
        backend.buttons['button_count'] += 1
    elif damage == 'blocker':
        backend.buttons['buttons'].append(make_button('Loading(Clone)',
            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count'] += 1
    else:
        backend.foreground = 'other.package/.Activity'
        session._INITIAL_GAME_STARTUP_RETRY_ATTEMPTS = 0
    with pytest.raises(SemanticGateClosed):
        session.click('BEACON_REWARD')
    assert not backend.taps


def test_failed_acquisition_never_falls_back_to_old_completed_beacon():
    backend, session, _ = session_for_meta('meta-completed-reward-r351.json')
    adapter = session.open()
    adapter.begin_meta_beacon()
    adapter._input_frame_refresher = Mock(side_effect=StaleFrameError())
    with pytest.raises(StaleFrameError):
        adapter.click('BEACON_REWARD')
    assert not backend.taps
