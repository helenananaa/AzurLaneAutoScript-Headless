import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_buttons, make_oracle, make_snapshot,
)


def commission_award(root='AwardInfoUI(Clone)'):
    path = 'root/OverlayCamera/Overlay/UIMain/' + root + '/items/close'
    backend = FakeBackend([make_button('close', path, 640, 507)])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_commission()
    return backend, oracle, adapter


@pytest.mark.parametrize('root', ['AwardInfoUI(Clone)', 'AwardInfoUI1(Clone)'])
@pytest.mark.parametrize('resource', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3'])
def test_delayed_close_returns_after_fresh_exit_with_one_input(root, resource, monkeypatch):
    backend, oracle, adapter = commission_award(root)
    original = oracle.read_state
    reads = []
    def read():
        if backend.taps:
            reads.append(True)
            if len(reads) == 3:
                # The next native commission may already show its EXP popup.
                path = 'root/OverlayCamera/Overlay/UIMain/ShipExpUI(Clone)/skipLayer'
                backend.snapshot = make_snapshot(generation=11)
                backend.buttons = make_buttons([make_button('skipLayer', path, 640, 360)], generation=11)
        return original()
    oracle.read_state = read
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.sleep', lambda _: None)
    receipt = adapter.click(resource)
    assert receipt.semantic_id in ('reward/award-info/close', 'reward/award-info1/close')
    assert len(reads) == 3
    assert backend.taps == [(640, 507)]


@pytest.mark.parametrize('change', ['still_mounted', 'stale_absence'])
def test_unconfirmed_exit_rejects_without_repeating_input(change, monkeypatch):
    backend, oracle, adapter = commission_award()
    def after_input():
        if change == 'stale_absence':
            backend.buttons = make_buttons([])
        else:
            backend.snapshot = make_snapshot(generation=11)
            backend.buttons['generation'] = 11
    backend.on_tap = after_input
    monkeypatch.setattr('alas_headless.adapter.semantic.commission.time.sleep', lambda _: None)
    with pytest.raises(SemanticGateClosed, match='did not close after one input'):
        adapter.click('GET_ITEMS_1')
    assert backend.taps == [(640, 507)]


def test_missing_award_without_recorded_close_remains_an_input_error():
    backend, oracle, adapter = commission_award()
    backend.buttons = make_buttons([])
    with pytest.raises(SemanticGateClosed, match='popup is absent'):
        adapter.click('GET_ITEMS_2')
    assert backend.taps == []
