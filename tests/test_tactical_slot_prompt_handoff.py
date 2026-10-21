"""A covered slot yields to ALAS' existing reviewed learning prompt handler."""
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.oracle.errors import SemanticInputBlocked
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


def prompt(drift=False):
    backend, oracle, _ = host(drift, 'tactical-slot-covered-continue-r328.json')
    # Static replay only: normalize in-memory clocks after a later UI endpoint
    # was retained. The source fixture preserves the actual adjacent clocks.
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for p in (backend.snapshot, backend.buttons, backend.ui):
        p['generation'] = generation
    oracle._sleep = lambda _: None
    adapter = AlasSemanticAdapter(oracle, lambda: None, tactical_assign_budget=1)
    adapter.begin_tactical()
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_newly_covered_slot_sends_no_input_then_native_cancel_owns_prompt(drift):
    backend, oracle, adapter = prompt(drift)
    assert oracle.tactical_continue_prompt_text() is not None
    before = oracle.input_dispatch_count
    assert adapter._click_tactical('ADD_NEW_STUDENT') is None
    assert oracle.input_dispatch_count == before
    assert not backend.taps
    assert adapter._action_ledger.remaining('tactical.assign') == 1
    assert adapter._commission_context.tactical_empty_slot_receipt is None
    cancel = oracle._unique(oracle.read_state(), 'tactical/continue/cancel')
    def dismissed():
        for part, family in ((backend.buttons, 'buttons'), (backend.ui, 'texts'), (backend.ui, 'images')):
            part[family] = [x for x in part[family] if '/Msgbox(Clone)/' not in x['path']]
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
        backend.ui['text_count'] = len(backend.ui['texts'])
        backend.ui['image_count'] = len(backend.ui['images'])
        for p in (backend.snapshot, backend.buttons, backend.ui):
            p['generation'] += 1
    backend.on_tap = dismissed
    assert adapter.cancel_tactical_continue_if_present()
    assert backend.taps == [(round(cancel.point.x), round(cancel.point.y))]
    assert adapter._action_ledger.remaining('tactical.assign') == 1


@pytest.mark.parametrize('damage', ['foreign-text', 'duplicate', 'loading', 'foreign-package', 'truncated'])
def test_unreviewed_or_additionally_blocked_prompt_cannot_yield_slot_input(damage):
    backend, oracle, adapter = prompt()
    if damage == 'foreign-text':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/msg_panel/content'))['text'] = '是否购买资源？'
    elif damage == 'duplicate':
        backend.buttons['buttons'].append(dict(next(b for b in backend.buttons['buttons']
            if b['path'].endswith('/custom_button_2(Clone)'))))
        backend.buttons['button_count'] += 1
    elif damage == 'loading':
        backend.buttons['buttons'].append(make_button('Loading(Clone)', 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'))
        backend.buttons['button_count'] += 1
    elif damage == 'foreign-package':
        backend.foreground = 'other.package/.Activity'
    else:
        backend.ui['text_truncated'] = True
    with pytest.raises(SemanticGateClosed) as caught:
        adapter._click_tactical('ADD_NEW_STUDENT')
    if damage in ('foreign-text', 'duplicate', 'truncated'):
        assert isinstance(caught.value, SemanticInputBlocked)
    assert not backend.taps
    assert adapter._action_ledger.remaining('tactical.assign') == 1


@pytest.mark.parametrize('target,blockers', [('other/target', ('tactical-continue',)),
    ('tactical/slot/first-empty', ('loading',))])
def test_unrelated_input_refusal_is_not_reclassified(target, blockers):
    _, oracle, adapter = prompt()
    error = SemanticInputBlocked(target, 10, blockers)
    oracle.click_tactical_first_empty_slot = Mock(side_effect=error)
    with pytest.raises(SemanticInputBlocked) as caught:
        adapter._click_tactical('ADD_NEW_STUDENT')
    assert caught.value is error
