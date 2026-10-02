from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED


def started():
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values['research/progress/confirm']=True
    receipt=adapter.click(NamedButton('POPUP_CONFIRM'))
    oracle.exists_values['research/progress/confirm']=False
    oracle.main_page_visible_value=True
    oracle.read_state=Mock(return_value=SimpleNamespace(generation=receipt.generation+1))
    return adapter,oracle,receipt


def test_disappeared_research_popup_completes_actual_receipt_without_second_input():
    adapter,oracle,receipt=started()
    assert adapter.click(NamedButton('POPUP_CONFIRM')) is receipt
    assert oracle.click_calls==['research/progress/confirm']


@pytest.mark.parametrize('unsafe',['not_main','blocker','old_generation','expired'])
def test_previous_popup_receipt_does_not_complete_unknown_or_obscured_surface(unsafe):
    adapter,oracle,receipt=started()
    if unsafe=='not_main':oracle.main_page_visible_value=False
    elif unsafe=='blocker':oracle._blocking_rules=Mock(return_value=(object(),))
    elif unsafe=='old_generation':oracle.read_state=Mock(return_value=SimpleNamespace(generation=receipt.generation))
    else:adapter._research_progress_close_until=0
    assert adapter._click_priority('POPUP_CONFIRM') is UNHANDLED
    assert oracle.click_calls==['research/progress/confirm']
