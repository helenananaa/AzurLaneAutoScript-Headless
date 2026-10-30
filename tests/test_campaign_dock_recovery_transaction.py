"""ALAS dock return preserves its accepted sortie rather than starting a run."""
from unittest.mock import Mock
from contextlib import nullcontext
from types import SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from tests.test_campaign_reentry_recovery import completed_menu
from tests.semantic_support.adapter_fixtures import NamedButton


def pending_continue():
    adapter, oracle = completed_menu()
    adapter.authorize_campaign_auto_search_continue(
        use_2x_book=False, fleet1=1, fleet2=2,
        fleet_order='fleet1_mob_fleet2_boss')
    adapter.continue_campaign_normal_auto_search()
    return adapter, oracle


@pytest.mark.parametrize('choice', ['organize', 'enhance'])
def test_dock_return_keeps_accepted_continue_and_never_replays_it(choice):
    adapter, oracle = pending_continue()
    context = adapter._campaign_context
    before = dict(adapter._action_ledger._remaining)
    receipt = oracle.click_receipt('campaign/dock-full/' + choice,
                                   generation=context.sortie_receipt.generation + 1)
    oracle.click_campaign_dock_full_choice = Mock(return_value=receipt)
    adapter.click_campaign_dock_full_choice(choice)
    oracle.campaign_page_is_normal = Mock(side_effect=AssertionError('return frame can still be dock'))
    for _ in range(2):
        adapter.prepare_campaign_run()
    assert adapter._campaign_context is context
    assert context.auto_search_completion is None
    assert context.sortie_proof is None
    assert not context.manual_completion_proven
    assert dict(adapter._action_ledger._remaining) == before
    with pytest.raises(SemanticGateClosed, match='fresh authorization'):
        adapter.continue_campaign_normal_auto_search()
    oracle.click_campaign_auto_search_reentry.assert_called_once()


@pytest.mark.parametrize('generation_delta', [None, -1, 0])
def test_unknown_or_previous_sortie_recovery_cannot_start_an_incomplete_run(generation_delta):
    adapter, oracle = pending_continue()
    context = adapter._campaign_context
    if generation_delta is not None:
        context.dock_full_recovery_receipt = oracle.click_receipt(
            'campaign/dock-full/organize',
            generation=context.sortie_receipt.generation + generation_delta)
    with pytest.raises(SemanticGateClosed, match='proven completion'):
        adapter.prepare_campaign_run()
    assert adapter._campaign_context is context
    assert adapter._action_ledger.remaining('campaign.sortie') == 0


def test_new_continue_invalidates_previous_dock_recovery_receipt():
    adapter, oracle = completed_menu()
    context = adapter._campaign_context
    context.dock_full_recovery_receipt = oracle.click_receipt(
        'campaign/dock-full/organize', generation=999)
    adapter.authorize_campaign_auto_search_continue(
        use_2x_book=False, fleet1=1, fleet2=2,
        fleet_order='fleet1_mob_fleet2_boss')
    adapter.continue_campaign_normal_auto_search()
    assert context.dock_full_recovery_receipt is None


def test_unknown_dock_input_does_not_record_recovery_authority():
    adapter, oracle = pending_continue()
    oracle.click_campaign_dock_full_choice = Mock(side_effect=SemanticGateClosed('unknown input outcome'))
    with pytest.raises(SemanticGateClosed, match='unknown input'):
        adapter.click_campaign_dock_full_choice('organize')
    assert adapter._campaign_context.dock_full_recovery_receipt is None
    with pytest.raises(SemanticGateClosed, match='proven completion'):
        adapter.prepare_campaign_run()


def test_original_entry_loop_observes_map_after_returning_dock_frame():
    from tests.test_alas_config_branch_compatibility import method
    adapter, oracle = pending_continue()
    context = adapter._campaign_context
    recovery=oracle.click_receipt('campaign/dock-full/organize',
                                  generation=context.sortie_receipt.generation + 1)
    oracle.click_campaign_dock_full_choice=Mock(return_value=recovery)
    oracle.campaign_page_is_normal=Mock(side_effect=AssertionError('returning dock frame'))
    boundary=SimpleNamespace(
        campaign_pre_sortie_active=lambda:True,
        campaign_dock_full_visible=Mock(side_effect=[True,False]),
        campaign_retirement_visible=lambda:False,
        prepare_campaign_run=Mock(side_effect=adapter.prepare_campaign_run),
        campaign_sortie_committed=adapter.campaign_sortie_committed,
        confirm_war_archives_entry_if_present=lambda:None,
        campaign_auto_search_running=lambda:True,
        confirm_campaign_auto_search_started=Mock(return_value=SimpleNamespace(
            stage_code='12-4',prepared_fleets=(1,2,0),sortie_generation=10,
            map_generation=20,map_root_path='LevelGrid')))
    def retire():
        adapter.click_campaign_dock_full_choice('organize')
        return True
    host=SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=boundary,screenshot=Mock()),
        config=SimpleNamespace(campaign_name='12-4',DropRecord_CombatRecord='do_not'),
        stat=SimpleNamespace(new=lambda **kwargs:nullcontext()),
        map_clear_percentage_timer=Mock(),is_in_map=lambda:False,
        handle_popup_confirm=lambda *args:False,handle_retirement=retire,
        handle_2x_book_popup=lambda:False,is_in_auto_search_menu=lambda:False,
        map_is_auto_search=True)
    enter=method('module/map/map_operation.py','MapOperation','enter_map',Timer=Mock())
    enter(host,NamedButton('12-4'))
    boundary.prepare_campaign_run.assert_called_once_with()
    boundary.confirm_campaign_auto_search_started.assert_called_once_with()
    assert adapter._campaign_context is context
    assert context.auto_search_completion is None
    assert adapter._action_ledger.remaining('campaign.sortie')==0
    oracle.click_campaign_auto_search_reentry.assert_called_once()
