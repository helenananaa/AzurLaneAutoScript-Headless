from unittest.mock import Mock
import pytest
from alas_headless.oracle.campaign_map import CampaignMapOracle
from alas_headless.semantic_oracle import SemanticGateClosed
from alas_headless import AlasSemanticAdapter
from tests.semantic_support.adapter_fixtures import FakeOracle
from types import SimpleNamespace
import time


def test_ready_opsi_globe_returns_non_campaign_without_input():
    oracle = Mock()
    oracle.campaign_map_entry_state.side_effect = SemanticGateClosed('map entry absent')
    oracle.daily_battle_result_visible.return_value = False
    oracle.operation_siren_globe_visible.return_value = True
    assert CampaignMapOracle.campaign_is_in_map(oracle) is False
    oracle.read_state.assert_not_called()
    oracle._tap.assert_not_called()


def test_unknown_surface_still_fails_closed():
    oracle = Mock()
    oracle.campaign_map_entry_state.side_effect = SemanticGateClosed('map entry absent')
    oracle.daily_battle_result_visible.return_value = False
    oracle.operation_siren_globe_visible.return_value = False
    oracle._matches.return_value = ()
    with pytest.raises(SemanticGateClosed, match='startup surface is not reviewed'):
        CampaignMapOracle.campaign_is_in_map(oracle)
    oracle._tap.assert_not_called()


def test_inherited_shop_requires_both_atomic_anchor_and_existing_shell_reader():
    oracle = Mock()
    oracle.campaign_map_entry_state.side_effect = SemanticGateClosed('map entry absent')
    oracle.daily_battle_result_visible.return_value = False
    oracle.operation_siren_globe_visible.return_value = False
    oracle._matches.side_effect = lambda state, target: (object(),) if target == 'shop/home' else ()
    oracle.recommendation_shop_visible.return_value = True
    assert CampaignMapOracle.campaign_is_in_map(oracle) is False
    oracle.recommendation_shop_visible.return_value = False
    with pytest.raises(SemanticGateClosed, match='startup surface is not reviewed'):
        CampaignMapOracle.campaign_is_in_map(oracle)
    oracle._tap.assert_not_called()


def test_native_home_recovery_uses_one_exact_globe_return_edge():
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._goto_main_target = Mock(return_value='os/globe/map')
    receipt = SimpleNamespace(semantic_id='os/globe/map', generation=10)
    oracle.click_operation_siren_globe_map = Mock(return_value=receipt)
    assert host._click_main('GOTO_MAIN', None) is receipt
    oracle.click_operation_siren_globe_map.assert_called_once_with()
    assert host._operation_siren_page_remount_until > time.monotonic()


@pytest.mark.parametrize('sortie', [None, object()])
def test_inherited_opsi_is_not_resumed_as_campaign_sortie(sortie):
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._campaign_context = SimpleNamespace(sortie_receipt=sortie)
    host._operation_siren_allows_passive_probe = Mock(return_value=True)
    if sortie is None:
        assert host._appear_passive_surface('IN_MAP', None) is False
    else:
        from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
        assert host._appear_passive_surface('IN_MAP', None) is UNHANDLED
