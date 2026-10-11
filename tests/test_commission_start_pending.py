"""An accepted start with a proven pending owner defers only Commission."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticCommissionStartUnproven
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from alas_headless.oracle.errors import SemanticSnapshotStale
from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button


SIGNATURE = (4, '日常资源开发IV', 15, 7200, 'pending', 'faxiankuangmai')


def pending(drift=False):
    b, o, a = host(drift, 'commission-start-pending-r206.json')
    # Retain the original independently captured STATE/UI pair in the fixture.
    # A frozen replay must share a generation across repeated reads; live state
    # advances between requests instead of returning the earlier STATE forever.
    generation = max(f['generation'] for f in (b.snapshot, b.buttons, b.ui))
    for frame in (b.snapshot, b.buttons, b.ui): frame['generation'] = generation
    return b, o, a


def accepted_start(monkeypatch):
    b, o, a = pending()
    a = AlasSemanticAdapter(o, lambda: None, commission_start_budget=1)
    a.begin_commission()
    a._commission_context.selected_signature = SIGNATURE
    def advance():
        for frame in (b.snapshot, b.buttons, b.ui):
            frame['generation'] += 3
    b.on_tap = advance
    receipt = a.click('COMMISSION_START')
    clicked_at = a._commission_context.start_clicked_at
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.monotonic',
                        lambda: clicked_at + 16)
    return b, o, a, receipt


@pytest.mark.parametrize('drift', [False, True])
def test_actual_pending_detail_is_proven_without_success_or_input(drift):
    b, o, _ = pending(drift)
    assert o.commission_start_pending_generation(SIGNATURE, 0) == b.snapshot['generation']
    with pytest.raises(SemanticGateClosed):
        o.commission_start_transition(SIGNATURE)
    assert not b.taps


def test_pending_start_is_task_local_and_consumed_input_is_never_repeated(monkeypatch):
    b, o, a, receipt = accepted_start(monkeypatch)
    session = SimpleNamespace(discard_task_state=a.reset_task_state, trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'commission'):
            a.commission_start_confirmed()
    cause = caught.value.cause
    assert isinstance(cause, AlasSemanticCommissionStartUnproven)
    assert cause.receipt == receipt and cause.generation > receipt.generation
    assert cause.signature == SIGNATURE
    assert session.last_task_outcome['outcome'] == 'result-unproven'
    assert a._action_ledger.remaining('commission.start') == 0
    assert len(b.taps) == 1
    with semantic_task_scope(session, 'research'):
        a.begin_research()
        assert o.read_state().generation > receipt.generation
    assert len(b.taps) == 1


@pytest.mark.parametrize('case', ['duplicate-text', 'wrong-name', 'wrong-cost',
                                 'image-method', 'incoherent', 'truncated',
                                 'blocked', 'no-new-generation', 'wrong-task', 'stale'])
def test_unproven_or_unrelated_result_remains_fatal(monkeypatch, case):
    b, _, a, receipt = accepted_start(monkeypatch)
    name = next(t for t in b.ui['texts'] if t['path'].endswith('/scrollItem/labelName$'))
    if case == 'duplicate-text':
        b.ui['texts'].append(deepcopy(name)); b.ui['text_count'] += 1
    elif case == 'wrong-name': name['text'] = 'another commission'
    elif case == 'wrong-cost':
        next(t for t in b.ui['texts'] if t['path'].endswith('/consume/Text'))['text'] = '100'
    elif case == 'image-method': b.ui['method_mask'] &= ~0x8
    elif case == 'incoherent': b.ui['generation'] += 5
    elif case == 'truncated':
        next(i for i in b.ui['images']
             if i['path'].endswith('/scrollItem/iconState$/0'))['flags'] |= 0x10
    elif case == 'blocked':
        b.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        b.buttons['button_count'] += 1
    elif case == 'no-new-generation':
        for frame in (b.snapshot, b.buttons, b.ui): frame['generation'] = receipt.generation
    elif case == 'stale': b.snapshot['age_ms'] = 10001
    session = SimpleNamespace(discard_task_state=a.reset_task_state, trace=None)
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session, 'research' if case == 'wrong-task' else 'commission'):
            a.commission_start_confirmed()
    if case == 'stale':
        assert isinstance(caught.value, SemanticSnapshotStale)
        assert caught.value.input_outcome_uncertain
    assert session.last_task_outcome['outcome'] == 'raised'
    assert len(b.taps) == 1
