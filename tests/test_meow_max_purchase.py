from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


@pytest.mark.parametrize('price', [21000, 17220, 1230, 21001, 22500, 0, -1])
def test_original_full_daily_count_uses_exact_max_and_checks_price(price):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    before = SimpleNamespace(purchased=0, purchase_total=15, coins=65000, box_counts=(10, 20, 30))
    after = SimpleNamespace(purchased=15, coins=65000-price, box_counts=(15, 25, 35))
    oracle.meowfficer_dock_state = Mock(side_effect=[before, after])
    oracle.meowfficer_purchase_state = Mock(side_effect=[
        SimpleNamespace(count=1, total_price=1230),
        SimpleNamespace(count=15, total_price=price),
    ])
    if 0 < price <= 21000:
        assert adapter.buy_meowfficer_boxes(15) is after
        assert oracle.click_calls == ['meowfficer/buy/enter', 'meowfficer/buy/max', 'meowfficer/buy/submit']
    else:
        with pytest.raises(SemanticGateClosed, match='price'):
            adapter.buy_meowfficer_boxes(15)
        assert oracle.click_calls == ['meowfficer/buy/enter', 'meowfficer/buy/max']


def test_discounted_purchase_still_requires_exact_quoted_coin_postcondition():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.meowfficer_dock_state = Mock(side_effect=[
        SimpleNamespace(purchased=0, purchase_total=15, coins=20000, box_counts=(10,20,30)),
        SimpleNamespace(purchased=15, coins=2779, box_counts=(15,25,35)),
    ])
    oracle.meowfficer_purchase_state = Mock(return_value=SimpleNamespace(count=15, total_price=17220))
    with pytest.raises(SemanticGateClosed, match='coin postcondition'):
        adapter.buy_meowfficer_boxes(15)
