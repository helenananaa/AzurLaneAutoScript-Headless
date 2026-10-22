"""Known post-start rejection is task-local; it never grants a food purchase."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.observer_fixtures import make_button, make_text
from tests.test_commission_start_pending import SIGNATURE, accepted_start, pending


TIP_PATH = 'OverlayCamera/Overlay/UIOverlay/TipPanel(Clone)/Grid/toolTip(Clone)/Text'
OIL_TIP = '<color=white>石油已经达到上限无法接受委托</color>'


def add_tip(backend, text=OIL_TIP):
    # Controlled composition: retained r206 pending owner plus the exact tip
    # read after r210's input. This is not a raw r210 observer fixture.
    tip = make_text(text, TIP_PATH)
    backend.ui['texts'].append(tip)
    backend.ui['text_count'] += 1
    return tip


@pytest.mark.parametrize('drift', [False, True])
def test_known_tip_requires_exact_pending_owner_and_post_input_generation(drift):
    b, o, _ = pending(drift)
    add_tip(b)
    generation = b.snapshot['generation']
    assert o.commission_start_oil_rejection_generation(SIGNATURE, 0, generation - 1) == generation
    assert o.commission_start_oil_rejection_generation(SIGNATURE, 0, generation) is None
    assert not b.taps


def test_known_rejection_defers_without_waiting_or_repeating_accepted_start(monkeypatch):
    b, _, a, receipt = accepted_start(monkeypatch)
    add_tip(b)
    clicked_at = a._commission_context.start_clicked_at
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.monotonic',
                        lambda: clicked_at + .5)
    session = SimpleNamespace(discard_task_state=a.reset_task_state, trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'commission'):
            a.commission_start_confirmed()
    assert caught.value.cause.rejection == 'client oil capacity'
    assert caught.value.cause.receipt == receipt
    assert a._action_ledger.remaining('commission.start') == 0
    assert len(b.taps) == 1
    with semantic_task_scope(session, 'research'):
        a.begin_research()
    assert len(b.taps) == 1


@pytest.mark.parametrize('message', ['其他通知', '石油已经达到上限无法领取委托奖励'])
def test_unrelated_tip_keeps_original_unknown_result_wait(monkeypatch, message):
    b, _, a, _ = accepted_start(monkeypatch)
    add_tip(b, message)
    clicked_at = a._commission_context.start_clicked_at
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.monotonic',
                        lambda: clicked_at + .5)
    assert a.commission_start_confirmed() is False
    assert len(b.taps) == 1


@pytest.mark.parametrize('case', ['duplicate', 'truncated', 'wrong-owner', 'blocked',
                                 'incoherent', 'foreign-package', 'stale'])
def test_unproven_rejection_does_not_become_a_local_oil_result(monkeypatch, case):
    b, _, a, _ = accepted_start(monkeypatch)
    tip = add_tip(b)
    if case == 'duplicate':
        b.ui['texts'].append(deepcopy(tip)); b.ui['text_count'] += 1
    elif case == 'truncated': tip['flags'] |= 0x10
    elif case == 'wrong-owner':
        next(t for t in b.ui['texts'] if t['path'].endswith('/scrollItem/labelName$'))['text'] = 'different commission'
    elif case == 'blocked':
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    elif case == 'incoherent': b.ui['generation'] += 5
    elif case == 'foreign-package': b.snapshot['package'] = 'unrelated.package'
    else: b.snapshot['age_ms'] = 10001
    session = SimpleNamespace(discard_task_state=a.reset_task_state, trace=None)
    with pytest.raises(SemanticGateClosed):
        with semantic_task_scope(session, 'commission'):
            a.commission_start_confirmed()
    assert session.last_task_outcome['outcome'] == 'raised'
    assert len(b.taps) == 1
