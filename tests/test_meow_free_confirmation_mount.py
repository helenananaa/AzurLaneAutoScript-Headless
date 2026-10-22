"""A typed free-box confirmation may mount before the underlying panel leaves."""
from unittest.mock import Mock
from types import SimpleNamespace
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticInputBlocked
from tests.test_game_tips_loading_presence import host
from tests.test_meowfficer_purchase_grants import transaction


def test_retained_free_prompt_is_confirmable_but_never_authorizes_panel_close():
    backend, oracle, _ = host(fixture='meow-free-confirm-r696.json')
    # The retained live diagnostic has adjacent state/UI publications. Freeze
    # their clocks together in this static replay, leaving the raw fixture intact.
    generation = max(p['generation'] for p in (backend.snapshot, backend.buttons, backend.ui))
    for part in (backend.snapshot, backend.buttons, backend.ui):
        part['generation'] = generation
    assert oracle.enabled('meowfficer/buy/confirm')
    # Reproduce the two-read race: the ready underlay quote was already
    # returned, then close's fresh state sees this retained prompt publication.
    # This later diagnostic is not claimed to be the failed internal frame.
    oracle.meowfficer_purchase_state = Mock(return_value=SimpleNamespace(
        generation=generation - 1, count=1, total_price=0))
    with pytest.raises(SemanticInputBlocked) as caught:
        oracle.click('meowfficer/buy/close')
    assert caught.value.semantic_id == 'meowfficer/buy/close'
    assert caught.value.blockers == ('meowfficer-queue-prompt',)
    assert not backend.taps and oracle.input_dispatch_count == 0


def test_accepted_free_submit_waits_for_mount_without_second_submit(monkeypatch):
    adapter, oracle, count, after = transaction(free=True)
    before = oracle.meowfficer_dock_state.side_effect
    # Rebuild the iterator while retaining the helper's exact zero-cost quotes.
    first = next(before)
    oracle.meowfficer_dock_state = Mock(side_effect=[first,
        SemanticGateClosed('prompt mounting'), SemanticGateClosed('prompt ready'), after])
    quote = next(oracle.meowfficer_purchase_state.side_effect)
    oracle.meowfficer_purchase_state = Mock(return_value=quote)
    closed = []
    oracle.enabled = lambda target: bool(closed) and target == 'meowfficer/buy/confirm'
    original = oracle.click
    def click(target):
        if target == 'meowfficer/buy/close':
            closed.append(True)
            raise SemanticInputBlocked(target, 11, ['meowfficer-queue-prompt'])
        return original(target)
    oracle.click = click
    monkeypatch.setattr('alas_headless.adapter.semantic.meowfficer.time.sleep', lambda _: None)
    assert adapter.buy_meowfficer_boxes(count) is after
    assert closed == [True]
    assert oracle.click_calls == ['meowfficer/buy/enter', 'meowfficer/buy/submit', 'meowfficer/buy/confirm']
    assert adapter._action_ledger.remaining('shop.purchase') == 0


@pytest.mark.parametrize('error', [
    SemanticInputBlocked('meowfficer/buy/close', 11, ['unknown-popup']),
    SemanticInputBlocked('different/target', 11, ['loading']),
    SemanticGateClosed('foreground changed'),
])
def test_unrelated_or_invalid_close_refusal_is_not_swallowed(error, monkeypatch):
    adapter, oracle, count, _ = transaction(free=True)
    first = next(oracle.meowfficer_dock_state.side_effect)
    quote = next(oracle.meowfficer_purchase_state.side_effect)
    oracle.meowfficer_dock_state = Mock(side_effect=[first, SemanticGateClosed('pending')])
    oracle.meowfficer_purchase_state = Mock(return_value=quote)
    oracle.enabled = lambda _: False
    original = oracle.click
    oracle.click = lambda target: (_ for _ in ()).throw(error) if target == 'meowfficer/buy/close' else original(target)
    monkeypatch.setattr('alas_headless.adapter.semantic.meowfficer.time.sleep', lambda _: None)
    with pytest.raises(type(error)):
        adapter.buy_meowfficer_boxes(count)
    assert oracle.click_calls == ['meowfficer/buy/enter', 'meowfficer/buy/submit']
