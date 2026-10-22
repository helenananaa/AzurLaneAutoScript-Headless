"""Stale action results must not become no-input scheduler deferrals."""

from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from alas_headless.oracle.errors import SemanticSnapshotStale
from tests.semantic_support.observer_fixtures import DRIVER_REVISION, make_button, make_oracle
from tests.test_shipyard_purchase import PANEL, add_prompt, purchase_backend
from tests.test_shipyard_blueprint_use import finish, use_backend


def session_for(backend, **budgets):
    oracle = make_oracle(backend)
    oracle._sleep = lambda _: None
    session = AlasSemanticSession('offline-test', DRIVER_REVISION)
    session.adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None, **budgets)
    return session


@pytest.mark.parametrize('action', ['quantity', 'fate'])
@pytest.mark.parametrize('stale_after_input', [False, True])
def test_shipyard_navigation_distinguishes_stale_admission_from_pending_result(action, stale_after_input):
    b = purchase_backend(owned=1)
    b.buttons['buttons'].append(make_button('fitting_btn', PANEL.replace('/calc_panel', '/fitting_btn')))
    b.buttons['button_count'] += 1
    session = session_for(b)
    def stale():
        for snapshot in (b.snapshot, b.buttons, b.ui):
            snapshot['age_ms'] = 12000
    if stale_after_input:
        b.on_tap = stale
    else:
        stale()
    expected = SemanticSnapshotStale if stale_after_input else TaskCapabilityUnavailable
    with pytest.raises(expected):
        with semantic_task_scope(session, 'shipyard'):
            if action == 'quantity':
                session.adapter.shipyard_change_quantity(3, 1)
            else:
                session.adapter.shipyard_enter_fate(3)
    assert len(b.taps) == int(stale_after_input)
    assert session.last_task_error['input_outcome_uncertain'] is stale_after_input
    assert session.last_task_outcome['outcome'] == ('raised' if stale_after_input else 'observation-not-ready')


@pytest.mark.parametrize('operation', ['purchase_prompt', 'purchase_result', 'blueprint_result'])
def test_split_shipyard_result_preserves_accepted_input_uncertainty(operation):
    b = use_backend() if operation == 'blueprint_result' else purchase_backend()
    session = session_for(b, shop_purchase_budget=1)
    a = session.adapter
    if operation == 'blueprint_result':
        a.begin_shipyard_blueprint_use(3, 1)
        a.shipyard_blueprint_use_submit()
        observe = a.shipyard_blueprint_use_completed
    else:
        a.begin_shipyard_purchase(3, 'PR', 2, 150)
        a.shipyard_purchase_submit()
        if operation == 'purchase_result':
            add_prompt(b)
            a.shipyard_purchase_confirm('BP_BUY')
            observe = a.shipyard_purchase_completed
        else:
            observe = lambda: a.shipyard_purchase_confirm('BP_BUY')
    b.snapshot['age_ms'] = 12000
    with pytest.raises(SemanticSnapshotStale):
        with semantic_task_scope(session, 'shipyard'):
            observe()
    assert session.last_task_outcome['outcome'] == 'raised'
    assert session.last_task_error['input_outcome_uncertain'] is True
    assert len(b.taps) == (2 if operation == 'purchase_result' else 1)
    assert a._action_ledger.remaining('shop.purchase') == (0 if operation == 'purchase_result' else 1)


@pytest.mark.parametrize('operation', ['purchase', 'blueprint'])
def test_verified_split_result_does_not_leave_pending_uncertainty(operation):
    b = use_backend() if operation == 'blueprint' else purchase_backend()
    session = session_for(b, shop_purchase_budget=1)
    a = session.adapter
    if operation == 'blueprint':
        a.begin_shipyard_blueprint_use(3, 1)
        a.shipyard_blueprint_use_submit()
        finish(b)
        observe = a.shipyard_blueprint_use_completed
    else:
        a.begin_shipyard_purchase(3, 'PR', 2, 150)
        a.shipyard_purchase_submit()
        add_prompt(b)
        a.shipyard_purchase_confirm('BP_BUY')
        b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
        b.ui['shipyard_strengthen'].update(purchased=4, coins=1850, exp=12)
        observe = a.shipyard_purchase_completed
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session, 'shipyard'):
            assert observe()
            for snapshot in (b.snapshot, b.buttons, b.ui):
                snapshot['age_ms'] = 12000
            observe()
    assert session.last_task_error['input_outcome_uncertain'] is False


def test_completed_quantity_action_does_not_poison_a_later_independent_stale_read():
    b = purchase_backend()
    session = session_for(b)
    def advance():
        b.snapshot['generation'] = b.buttons['generation'] = b.ui['generation'] = 11
        next(t for t in b.ui['texts'] if t['path'].endswith('/calc/base/count/Text'))['text'] = '3'
    b.on_tap = advance
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session, 'shipyard'):
            assert session.adapter.shipyard_change_quantity(3, 1)
            b.snapshot['age_ms'] = 12000
            session.adapter.oracle.read_state()
    assert len(b.taps) == 1
    assert session.last_task_error['input_outcome_uncertain'] is False


@pytest.mark.parametrize('action', ['claim', 'close'])
def test_guild_postcondition_outside_ledger_dispatch_retains_uncertainty(action, monkeypatch):
    # Use the real adapter boundary and stale observer, with a controlled
    # reviewed navigation target to isolate the post-dispatch read.
    b = purchase_backend()
    session = session_for(b)
    a = session.adapter
    o = a.oracle
    def click(*args):
        o._tap(640, 360)
        return SimpleNamespace(generation=10)
    b.on_tap = lambda: b.snapshot.__setitem__('age_ms', 12000)
    monkeypatch.setattr(o, 'click', click)
    if action == 'claim':
        monkeypatch.setattr(o, 'enabled', lambda _: True)
        monkeypatch.setattr(a, '_dispatch_mutation', lambda _, operation: operation())
        operation = a.claim_all_guild_reports
    else:
        monkeypatch.setattr(a, '_fresh_input_oracle', lambda: o)
        operation = a.close_guild_dispatch_page
    with pytest.raises(SemanticSnapshotStale):
        with semantic_task_scope(session, 'guild'):
            operation()
    assert b.taps == [(640, 360)]
    assert session.last_task_error['input_outcome_uncertain'] is True
