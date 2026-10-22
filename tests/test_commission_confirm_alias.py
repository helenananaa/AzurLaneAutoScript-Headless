from types import SimpleNamespace

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


@pytest.mark.parametrize('actual_cost', [15, 16])
def test_original_commission_confirm_suffix_keeps_selected_oil_cost_guard(actual_cost):
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_commission()
    adapter._commission_context.start_receipt = SimpleNamespace(generation=10)
    adapter._commission_context.selected_oil_cost = 15
    oracle.commission_start_prompt_cost = lambda: actual_cost
    if actual_cost == 15:
        receipt = adapter.click(NamedButton('POPUP_CONFIRM_COMMISSION_START'))
        assert receipt.semantic_id == 'commission/start/confirm'
        assert oracle.click_calls == ['commission/start/confirm']
    else:
        with pytest.raises(SemanticGateClosed, match='prompt changed'):
            adapter.click(NamedButton('POPUP_CONFIRM_COMMISSION_START'))
        assert oracle.click_calls == []
    assert adapter._button_name('POPUP_CONFIRM_UNREVIEWED_START') == 'POPUP_CONFIRM_UNREVIEWED_START'
