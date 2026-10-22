"""Original UI recovery can safely cancel an earlier task's learning prompt."""
import pytest
from unittest.mock import Mock
from alas_headless import SemanticGateClosed
from tests.test_game_tips_loading_presence import host


def prompt_host(flow=None):
    backend, oracle, adapter = host(fixture='inherited-tactical-continue-r292.json')
    # Coherent static replay only; the retained fixture keeps its raw clocks.
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for p in (backend.snapshot, backend.buttons, backend.ui):
        p['generation'] = generation
    if flow:
        getattr(adapter, 'begin_'+flow)()
    return backend, oracle, adapter


@pytest.mark.parametrize('flow', [None, 'commission', 'research'])
def test_orphan_prompt_precedes_unrelated_page_probes_and_cancels_through_native_alias(flow):
    backend, oracle, adapter = prompt_host(flow)
    assert oracle.tactical_continue_prompt_text() is not None
    cancel = oracle._unique(oracle.read_state(), 'tactical/continue/cancel')
    for name in ('GOTO_MAIN_WHITE', 'GUILD_CHECK', 'EXERCISE_CHECK'):
        assert adapter.appear(name) is False
    assert adapter.appear('POPUP_CANCEL') is True
    assert adapter.appear('POPUP_CONFIRM') is True
    def dismissed():
        for key, records in [('buttons', 'buttons'), ('ui', 'texts'), ('ui', 'images')]:
            part = getattr(backend, key)
            part[records] = [x for x in part[records] if '/Msgbox(Clone)/' not in x['path']]
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
        backend.ui['text_count'] = len(backend.ui['texts'])
        backend.ui['image_count'] = len(backend.ui['images'])
        for p in (backend.snapshot, backend.buttons, backend.ui):
            p['generation'] += 1
    backend.on_tap = dismissed
    receipt = adapter.click('POPUP_CONFIRM_UI_ADDITIONAL')
    assert receipt.semantic_id == 'tactical/continue/cancel'
    assert backend.taps == [(round(cancel.point.x), round(cancel.point.y))]
    assert oracle.tactical_continue_prompt_text() is None


@pytest.mark.parametrize('case', ['foreign', 'stale', 'duplicate_cancel', 'other_text'])
def test_unknown_or_unsafe_prompt_cannot_gain_cancel_input(case):
    backend, oracle, adapter = prompt_host()
    if case == 'foreign': backend.foreground = 'unrelated/.Activity'
    elif case == 'stale': backend.snapshot['age_ms'] = 10001
    elif case == 'duplicate_cancel':
        backend.buttons['buttons'].append(dict(next(b for b in backend.buttons['buttons']
            if b['path'].endswith('/custom_button_2(Clone)'))))
        backend.buttons['button_count'] += 1
    else:
        next(t for t in backend.ui['texts'] if t['path'].endswith('/window/msg_panel/content'))['text'] = 'Unknown resource purchase'
    with pytest.raises(SemanticGateClosed):
        adapter.click('POPUP_CONFIRM_UI_ADDITIONAL')
    assert not backend.taps


def test_original_meta_session_keeps_inherited_prompt_recovery_before_other_probes(monkeypatch):
    from tests import test_frame_post_input_foreground as support
    original = support.host
    def coherent(*args, **kwargs):
        backend, oracle, adapter = original(*args, **kwargs)
        generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
        for p in (backend.snapshot, backend.buttons, backend.ui):
            p['generation'] = generation
        return backend, oracle, adapter
    monkeypatch.setattr(support, 'host', coherent)
    backend, session, _ = support.session_for_meta('inherited-tactical-continue-r292.json')
    session.begin_meta_beacon()
    assert session.appear('POPUP_CANCEL') is True
    assert session.appear('POPUP_CONFIRM') is True
    assert session.appear('GOTO_MAIN_WHITE') is False
    receipt = session.click('POPUP_CONFIRM_UI_ADDITIONAL')
    assert receipt.semantic_id == 'tactical/continue/cancel'
    assert len(backend.taps) == 1
    assert session.open().oracle.input_dispatch_count == 1


def test_queued_prompt_mount_yields_one_old_probe_then_requires_new_identity():
    backend, oracle, adapter = prompt_host('commission')
    assert adapter.appear('POPUP_CANCEL') is True
    assert adapter.appear('POPUP_CONFIRM') is True
    content = next(t for t in backend.ui['texts'] if t['path'].endswith('/window/msg_panel/content'))
    known_text = content['text']
    content['text'] = ''
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] += 1
    assert adapter.click('POPUP_CONFIRM_UI_ADDITIONAL') is None
    assert not backend.taps
    # The zero-input yield consumes its source correlation; an unknown second
    # click cannot borrow it indefinitely or confirm another kind of dialog.
    with pytest.raises(SemanticGateClosed):
        adapter.click('POPUP_CONFIRM_UI_ADDITIONAL')
    assert not backend.taps
    content['text'] = known_text
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] += 1
    assert adapter.appear('POPUP_CONFIRM') is True
    assert adapter.click('POPUP_CONFIRM_UI_ADDITIONAL').semantic_id == 'tactical/continue/cancel'
    assert len(backend.taps) == 1


def test_prompt_replaced_during_fresh_input_acquisition_never_dispatches():
    backend, oracle, adapter = prompt_host('commission')
    assert adapter.appear('POPUP_CONFIRM') is True
    fresh = Mock()
    fresh.tactical_continue_prompt_text.return_value = None
    adapter._fresh_input_oracle = Mock(return_value=fresh)
    assert adapter.click('POPUP_CONFIRM_UI_ADDITIONAL') is None
    fresh.click.assert_not_called()
    assert not backend.taps
