from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import MissionDisposition, SemanticGateClosed, SemanticTargetMissing
from alas_headless.semantic_oracle import SemanticOracle
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


def returning(receipt_id='reward/award-info/close'):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_mission_reward(daily=True, weekly=True)
    receipt = oracle.click_receipt(receipt_id)
    adapter._mission_context.award_close_receipt = receipt
    oracle.read_state = Mock(return_value=SimpleNamespace(buttons=()))
    oracle._sleep = Mock()
    oracle._retry_transition_read = lambda reader, **kw: SemanticOracle._retry_transition_read(oracle,reader,**kw)
    oracle.mission_page_state = Mock(return_value=SimpleNamespace(
        generation=receipt.generation+2, disposition=MissionDisposition.UNFINISHED))
    return adapter, oracle, receipt


@pytest.mark.parametrize('receipt_id,resource', [('reward/award-info/close','GET_ITEMS_1'),
                                               ('reward/new-ship/continue','GET_SHIP')])
def test_own_close_waits_for_reviewed_destination_and_does_not_click_again(receipt_id,resource):
    adapter,oracle,receipt=returning(receipt_id)
    destination=oracle.mission_page_state.return_value
    oracle.mission_page_state.side_effect=[SemanticGateClosed('transition'),destination]
    with pytest.raises(SemanticTargetMissing,match='already closed'):
        adapter.click(NamedButton(resource))
    assert oracle.mission_page_state.call_count==2
    assert adapter._mission_context.award_close_receipt is None
    assert oracle.click_calls==[]


@pytest.mark.parametrize('bad',['unknown','old_generation','other_popup','no_receipt'])
def test_unproven_destination_cannot_consume_a_close_receipt(bad):
    adapter,oracle,receipt=returning()
    if bad=='unknown': oracle.mission_page_state.return_value.disposition=MissionDisposition.UNKNOWN
    elif bad=='old_generation': oracle.mission_page_state.return_value.generation=receipt.generation
    elif bad=='other_popup':
        oracle.read_state.return_value.buttons=(SimpleNamespace(active_in_hierarchy=True,path='root/AwardInfoUI(Clone)/items/close'),)
    else: adapter._mission_context.award_close_receipt=None
    with pytest.raises(SemanticGateClosed): adapter.click(NamedButton('GET_ITEMS_1'))
    assert oracle.click_calls==[]
    assert adapter._mission_context.award_close_receipt is (None if bad=='no_receipt' else receipt)


def test_award_receipt_cannot_consume_a_ship_confirmation():
    adapter,oracle,receipt=returning()
    with pytest.raises(SemanticGateClosed): adapter.click(NamedButton('GET_SHIP'))
    oracle.read_state.assert_not_called()
    assert adapter._mission_context.award_close_receipt is receipt
    assert oracle.click_calls==[]


@pytest.mark.parametrize('proven',[True,False])
def test_completed_award_close_hands_proven_ship_to_original_loop_without_input(proven):
    adapter,oracle,receipt=returning()
    oracle.read_state.return_value=SimpleNamespace(generation=receipt.generation+2,
        buttons=(SimpleNamespace(active_in_hierarchy=True,path='root/NewShipUI(Clone)/shake_panel/click'),))
    oracle.new_ship_reward_visible=Mock(return_value=proven)
    with pytest.raises(SemanticTargetMissing if proven else SemanticGateClosed):
        adapter.click(NamedButton('GET_ITEMS_1'))
    assert oracle.click_calls==[]
    assert adapter._mission_context.award_close_receipt is (None if proven else receipt)
