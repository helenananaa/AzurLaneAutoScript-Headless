"""Retained result ownership and original-retirement dispatch seams."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


def completed_menu(recovery=None):
    o = FakeOracle()
    o.campaign_fleets['submarine'] = 0
    a = AlasSemanticAdapter(o, lambda: None, campaign_stage_entry_budget=1,
        campaign_fleet_mutation_budget=6, campaign_sortie_budget=2)
    a.begin_campaign_pre_sortie('12-4')
    button = NamedButton('12-4'); button.semantic_campaign_stage_code = '12-4'
    a.click(button); a.click(NamedButton('MAP_PREPARATION'))
    a.authorize_campaign_fleet_preparation(1, 2, 0)
    a.confirm_campaign_fleet_selection()
    a.ensure_campaign_auto_search_roles('fleet1_mob_fleet2_boss')
    a.authorize_campaign_sortie(use_auto_search=True, use_2x_book=False,
        submarine_mode='do_not_use', fleet_order='fleet1_mob_fleet2_boss')
    a.click(NamedButton('FLEET_PREPARATION')); a.confirm_campaign_auto_search_started()
    o.enabled_values['reward/campaign-total/exit'] = True
    o.campaign_official_combat_auto_state = Mock(return_value=(81, True))
    o.read_state = Mock(return_value=SimpleNamespace(generation=90, buttons=(SimpleNamespace(
        name='ButtonExit', path='OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit', actionable=True),)))
    o.campaign_auto_search_reentry_available = Mock(return_value=True)
    o._campaign_2x_book_control = Mock(return_value=(None, None, False, 100))
    o.click_campaign_auto_search_reentry = Mock(return_value=o.click_receipt('reward/campaign-total/go'))
    if recovery:
        o.campaign_dock_full_visible = Mock(side_effect=[True, False])
    proof = a.wait_campaign_auto_search_completion('12-4', timeout_seconds=60,
        keep_result=True, recovery_handler=recovery)
    assert proof.result_exit_receipt is None
    return a, o


def test_retained_menu_reuses_preparation_but_consumes_a_new_sortie():
    a, o = completed_menu()
    previous = a._campaign_context
    a.prepare_campaign_run()
    assert a._campaign_context is previous
    assert a._action_ledger.remaining('campaign.sortie') == 1
    assert a._action_ledger.remaining('campaign.stage_entry') == 0
    assert a.campaign_stage_entry_allowed()
    assert a.appear(NamedButton('AUTO_SEARCH_MENU_CONTINUE'))
    values = dict(use_2x_book=False, fleet1=1, fleet2=2, fleet_order='fleet1_mob_fleet2_boss')
    with pytest.raises(SemanticGateClosed):
        a.continue_campaign_normal_auto_search()
    with pytest.raises(SemanticGateClosed):
        a.authorize_campaign_auto_search_continue(**dict(values, fleet1=2))
    assert o.click_campaign_auto_search_reentry.call_count == 0
    assert a.authorize_campaign_auto_search_continue(**values)
    a.click(NamedButton('AUTO_SEARCH_MENU_CONTINUE'))
    assert a._action_ledger.remaining('campaign.sortie') == 0
    assert previous.sortie_proof is None
    assert previous.auto_search_completion is None
    assert not a.appear(NamedButton('AUTO_SEARCH_MENU_CONTINUE'))
    with pytest.raises(SemanticGateClosed):
        a.continue_campaign_normal_auto_search()
    assert o.click_campaign_auto_search_reentry.call_count == 1


def test_changed_book_blocks_go_without_spending_grant():
    a, o = completed_menu()
    a.authorize_campaign_auto_search_continue(use_2x_book=False, fleet1=1, fleet2=2,
        fleet_order='fleet1_mob_fleet2_boss')
    o.campaign_2x_book_value = True
    with pytest.raises(SemanticGateClosed, match='book changed'):
        a.continue_campaign_normal_auto_search()
    assert a._action_ledger.remaining('campaign.sortie') == 1
    o.click_campaign_auto_search_reentry.assert_not_called()


def test_retained_result_hides_optional_chapter_probes():
    a, o = completed_menu()
    o.observation_target_present = Mock(side_effect=lambda target: target == 'reward/campaign-total/exit')
    o.campaign_page_is_normal = Mock(side_effect=AssertionError('underlay parser must not run'))
    assert not a.appear(NamedButton('CAMPAIGN_CHECK'))
    o.campaign_page_is_normal.assert_not_called()


def test_wait_delegates_actual_dock_interruption_to_alas_handler():
    recover = Mock()
    a, o = completed_menu(recover)
    recover.assert_called_once_with()
    assert a._action_ledger.remaining('campaign.sortie') == 1


def test_retirement_session_ports_precede_generic_combat_probes():
    oracle = Mock()
    oracle.retirement_selection_visible.return_value = True
    adapter = SimpleNamespace(oracle=oracle, _frame_or_live_observation_oracle=lambda: oracle)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    session.refresh_frame = Mock()
    assert session.appear(NamedButton('IN_RETIREMENT_CHECK'))
    assert session.appear(NamedButton('DOCK_CHECK'))
    assert session.appear(NamedButton('BACK_ARROW'))
    oracle.retirement_page_back_available.assert_called_once()
    session.click(NamedButton('BACK_ARROW'))
    session.refresh_frame.assert_called_once()
    oracle.click_retirement_page_back.assert_called_once()
    session._retirement_return_receipt = SimpleNamespace(generation=40)
    oracle.read_state.return_value = SimpleNamespace(generation=41, buttons=(
        SimpleNamespace(path='root/DockyardUI(Clone)/main/ship', active_in_hierarchy=True),))
    assert session.appear(NamedButton('IN_RETIREMENT_CHECK'))
    oracle.read_state.return_value = SimpleNamespace(generation=42, buttons=())
    assert not session.appear(NamedButton('IN_RETIREMENT_CHECK'))
    assert not session.appear(NamedButton('DOCK_CHECK'))
    assert session._retirement_return_receipt is None
