"""META card entry and its accepted destination share one fresh input frame."""
from unittest.mock import Mock, patch
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt
from alas_headless.adapter import StaleFrameError
from tests.test_frame_post_input_foreground import session_for_meta
from tests.test_game_tips_loading_presence import host


def dossier_session():
    backend, oracle, adapter = host(fixture='meta-dossier-entry-return-r381.json')
    # A static replay cannot advance its adjacent endpoint clocks. Normalize
    # only this in-memory replay; retained raw evidence remains unchanged.
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] = generation
    with patch('tests.test_frame_post_input_foreground.host', return_value=(backend, oracle, adapter)):
        return session_for_meta()


@pytest.mark.parametrize('drift', [False, True])
def test_actual_empty_dossier_reuses_entry_without_split_live_destination_reads(drift):
    backend, session, _ = dossier_session()
    adapter = session.open()
    previous = ActionReceipt('meta/dossier/open', backend.snapshot['generation']-1,
                             None, None, 'accepted/card')
    adapter._meta_dossier_entry_receipt = previous
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['texts'].reverse()
        backend.ui['optional_upstream_field'] = 1
    live = adapter.oracle
    live.meta_dossier_empty_points = Mock(side_effect=AssertionError('split live destination'))
    live.observation_target_present = Mock(side_effect=AssertionError('split live card'))
    live.click_meta_card = Mock(side_effect=AssertionError('repeated card input'))
    ordinal = session._frame_clock._ordinal
    assert session.click('META_MAIN_DOSSIER_ENTRANCE') is previous
    assert session._frame_clock._ordinal == ordinal+1
    assert not backend.taps
    live.meta_dossier_empty_points.assert_not_called()
    live.observation_target_present.assert_not_called()
    live.click_meta_card.assert_not_called()


@pytest.mark.parametrize('damage', ['missing-list', 'counter', 'duplicate', 'foreign'])
def test_unknown_dossier_destination_never_acknowledges_entry(damage):
    backend, session, _ = dossier_session()
    session.open()._meta_dossier_entry_receipt = ActionReceipt(
        'meta/dossier/open', backend.snapshot['generation']-1, None, None, 'accepted/card')
    if damage == 'missing-list':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons']
                                     if not b['path'].endswith('/list_btn')]
    elif damage == 'counter':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/progress/value'))['text'] = 'unknown'
    elif damage == 'duplicate':
        backend.buttons['buttons'].append(dict(next(b for b in backend.buttons['buttons']
                                                    if b['path'].endswith('/list_btn'))))
    else:
        backend.foreground = 'unrelated.package/.Activity'
        session._INITIAL_GAME_STARTUP_RETRY_ATTEMPTS = 0
    backend.buttons['button_count'] = len(backend.buttons['buttons'])
    with pytest.raises(SemanticGateClosed):
        session.click('META_MAIN_DOSSIER_ENTRANCE')
    assert not backend.taps


def test_card_entry_does_not_fallback_when_new_frame_acquisition_fails():
    backend, session, _ = dossier_session()
    session.refresh_frame = Mock(side_effect=StaleFrameError())
    with pytest.raises(StaleFrameError):
        session.click('META_MAIN_DOSSIER_ENTRANCE')
    assert not backend.taps
