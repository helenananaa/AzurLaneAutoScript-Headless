"""Reuse an accepted navigation receipt only after its real destination arrives."""
from unittest.mock import Mock, patch
import pytest
from alas_headless import SemanticGateClosed
from tests.test_build_missing_entry_reentry import fixture
from tests.semantic_support.adapter_fixtures import NamedButton


def test_partial_main_counter_after_accepted_entry_waits_for_destination_without_tap():
    adapter, oracle, receipt = fixture()
    oracle.main_gold = Mock(side_effect=SemanticGateClosed('main coin counter is absent or malformed'))
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.sleep'):
        assert adapter.click(NamedButton('MAIN_GOTO_BUILD')) is receipt
    assert oracle.click_calls == ['main/build']


@pytest.mark.parametrize('case', ['no-receipt', 'expired', 'no-destination', 'old-destination'])
def test_missing_counter_never_authorizes_unproven_destination_or_new_input(case):
    adapter, oracle, receipt = fixture()
    if case == 'no-receipt': adapter._build_context.entry_receipt = None
    elif case == 'expired': adapter._build_context.passive_transition_until = 0
    else:
        adapter._build_context.passive_transition_until = 20
        oracle.exists = Mock(return_value=case == 'old-destination')
        oracle.read_state.return_value.generation = receipt.generation
    oracle.main_gold = Mock(side_effect=SemanticGateClosed('main coin counter is absent or malformed'))
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.monotonic', side_effect=[0, 0, 0, 6]):
        with pytest.raises(SemanticGateClosed): adapter.click(NamedButton('MAIN_GOTO_BUILD'))
    assert oracle.click_calls == ['main/build']
