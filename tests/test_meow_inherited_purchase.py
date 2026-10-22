from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed, AlasSemanticUnmapped
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


def test_original_additional_buy_back_edge_recovers_retained_purchase():
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values['meowfficer/buy/max']=True
    oracle.meowfficer_purchase_state=Mock(return_value=object())
    assert adapter.appear(NamedButton('MEOWFFICER_BUY'))
    assert not adapter.appear(NamedButton('WITHDRAW'))
    assert not adapter.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))
    for name in ('FLEET_CHECK','MEOWFFICER_CHECK','GOTO_MAIN_WHITE','MEOWFFICER_INFO',
                 'GET_ITEMS_1','GET_ITEMS_2','GET_ITEMS_3','GET_SHIP','GET_MISSION',
                 'DORM_INFO','DORM_FEED_CANCEL','DORM_TROPHY_CONFIRM'):
        assert not adapter.appear(NamedButton(name))
    adapter.click(NamedButton('BACK_ARROW'))
    assert oracle.click_calls==['meowfficer/buy/close']


def test_covered_purchase_does_not_supply_native_additional_close():
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values['meowfficer/buy/max']=True
    oracle.meowfficer_purchase_state=Mock(side_effect=SemanticGateClosed('covered'))
    from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
    for name in ('WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM', 'GET_ITEMS_1', 'GET_MISSION',
                 'DORM_FEED_CANCEL'):
        assert adapter._appear_priority(name) is UNHANDLED
    with pytest.raises(AlasSemanticUnmapped):adapter.click(NamedButton('BACK_ARROW'))
    assert oracle.click_calls==[]
