"""An accepted entry can outlive its source during the existing Build wait."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.semantic_oracle import SemanticTargetMissing
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


def fixture():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_build()
    receipt = adapter.click(NamedButton('MAIN_GOTO_BUILD'))
    oracle.exists = Mock(side_effect=[False, False, True])
    oracle.enabled = Mock(return_value=True)
    oracle.read_state = Mock(return_value=SimpleNamespace(generation=receipt.generation + 1))
    return adapter, oracle, receipt


def test_missing_old_entry_waits_for_fresh_destination_without_another_tap():
    adapter, oracle, receipt = fixture()
    oracle.main_gold = Mock(side_effect=SemanticTargetMissing('semantic target is absent: main/build'))
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.sleep'):
        assert adapter.click(NamedButton('MAIN_GOTO_BUILD')) is receipt
    assert oracle.click_calls == ['main/build']


@pytest.mark.parametrize('case', ['no-receipt', 'expired', 'coin-malformed', 'other-missing', 'no-destination'])
def test_missing_entry_does_not_soften_unrelated_or_unproven_reads(case):
    adapter, oracle, _ = fixture()
    error = SemanticTargetMissing('semantic target is absent: main/build')
    if case == 'no-receipt': adapter._build_context.entry_receipt = None
    elif case == 'expired': adapter._build_context.passive_transition_until = 0
    elif case == 'coin-malformed':
        error = SemanticGateClosed('main coin counter is absent or malformed')
        # Malformed source data alone is insufficient. No real destination
        # arrives, so the accepted-entry transition still must fail closed.
        oracle.exists = Mock(return_value=False)
        adapter._build_context.passive_transition_until = 20
    elif case == 'other-missing': error = SemanticTargetMissing('semantic target is absent: unrelated')
    else:
        oracle.exists = Mock(return_value=False)
        adapter._build_context.passive_transition_until = 20
    oracle.main_gold = Mock(side_effect=error)
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.monotonic', side_effect=[0, 0, 0, 6]):
        with pytest.raises(SemanticGateClosed): adapter.click(NamedButton('MAIN_GOTO_BUILD'))
    assert oracle.click_calls == ['main/build']
