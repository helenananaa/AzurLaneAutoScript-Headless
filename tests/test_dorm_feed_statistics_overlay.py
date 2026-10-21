"""Feed availability yields to the native dorm statistics handler."""
from unittest.mock import Mock

import pytest

from alas_headless.semantic_oracle import SemanticGateClosed
from alas_headless.adapter.semantic.contracts import _CampaignFlowContext
from alas_headless.oracle.errors import SemanticTargetNotActionable
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle

FEED = "UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/bottomPanel/bottomleft/feed_btn"
CONFIRM = "OverlayCamera/Overlay/UIMain/BackYardStatisticsUI(Clone)/painting/confirm_btn"


@pytest.mark.parametrize('foreign_blocker', [False, True])
def test_guild_with_retained_campaign_context_owns_only_unobscured_confirm_absence(foreign_blocker):
    from types import SimpleNamespace
    from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._campaign_context = object()
    oracle.exists_values['guild/page/back'] = True
    oracle.guild_page_visible = Mock(return_value=True)
    blockers = [SimpleNamespace(blocker_id='guild-page')]
    if foreign_blocker:
        blockers.append(SimpleNamespace(blocker_id='unknown'))
    oracle._blocking_rules = Mock(return_value=tuple(blockers))
    if foreign_blocker:
        assert adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM') is UNHANDLED
    else:
        assert not adapter.appear(NamedButton('CAMPAIGN_WITHDRAW_CONFIRM'))
    assert oracle.click_calls == []


def test_statistics_overlay_yields_feed_to_original_info_handler():
    backend = FakeBackend([
        make_button("feed_btn", FEED, raycast_top=False),
        make_button("confirm_btn", CONFIRM),
    ])
    oracle = make_oracle(backend)
    oracle._tap = Mock()
    assert not oracle.enabled("dorm/feed")
    assert oracle.enabled("dorm/statistics/confirm")
    with pytest.raises(SemanticTargetNotActionable, match="not actionable") as refused:
        oracle.click("dorm/feed")
    assert refused.value.semantic_id == 'dorm/feed'
    assert refused.value.generation >= 10
    oracle._tap.assert_not_called()


def test_uncovered_feed_remains_available():
    buttons = [make_button("feed_btn", FEED)]
    oracle = make_oracle(FakeBackend(buttons))
    assert oracle.enabled("dorm/feed")


def test_unknown_overlay_does_not_become_a_statistics_mapping():
    oracle = make_oracle(FakeBackend([
        make_button("feed_btn", FEED, raycast_top=False),
        make_button("confirm_btn", CONFIRM.replace("BackYardStatisticsUI", "OtherUI")),
    ]))
    oracle._tap = Mock()
    with pytest.raises(SemanticGateClosed, match="not actionable"):
        oracle.click("dorm/feed")
    oracle._tap.assert_not_called()


@pytest.mark.parametrize("feed_ready", [False, True])
def test_native_dorm_marker_waits_for_feed_readiness(feed_ready):
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_dorm()
    oracle.exists_values["dorm/page/manage"] = True
    oracle.exists_values["dorm/statistics/confirm"] = False
    oracle.enabled_values["dorm/feed/close"] = False
    oracle.enabled_values["dorm/feed"] = feed_ready
    oracle.click = Mock()
    assert adapter.appear(NamedButton("DORM_CHECK")) is feed_ready
    oracle.click.assert_not_called()


def test_retained_feed_yields_home_probes_to_original_feed_cancel():
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_dorm()
    oracle.exists_values["dorm/feed/close"] = True
    oracle.enabled_values["dorm/feed/close"] = True
    oracle.enabled_values["dorm/empty-food/cancel"] = False
    oracle.click = Mock()
    for name in ("GOTO_MAIN", "GOTO_MAIN_WHITE", "RPG_HOME"):
        assert not adapter.appear(NamedButton(name))
    assert adapter.appear(NamedButton("DORM_FEED_CANCEL"))
    oracle.click.assert_not_called()


def test_reviewed_dorm_back_yields_campaign_probe_during_main_mount():
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.click(NamedButton("DORM_GOTO_MAIN"))
    assert not adapter.appear(NamedButton("CAMPAIGN_WITHDRAW_CONFIRM"))
    assert oracle.click_calls == ["dorm/page/back"]


@pytest.mark.parametrize("foreign_blocker", [False, True])
def test_dorm_back_wait_does_not_classify_unknown_or_foreign_surface(foreign_blocker):
    import time
    from types import SimpleNamespace
    from alas_headless import AlasSemanticUnmapped
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    if foreign_blocker:
        adapter._dorm_return_transition_until = time.monotonic() + 8
        oracle._blocking_rules = Mock(return_value=(SimpleNamespace(blocker_id="unknown"),))
    with pytest.raises(AlasSemanticUnmapped):
        adapter.appear(NamedButton("CAMPAIGN_WITHDRAW_CONFIRM"))


def test_mounting_meow_page_excludes_unrelated_page_probes():
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values["meowfficer/page/back"] = True
    oracle.enabled_values["meowfficer/page/back"] = False
    assert not adapter.appear(NamedButton("FLEET_CHECK"))
    assert not adapter.appear(NamedButton("MEOWFFICER_CHECK"))
    oracle.enabled_values["meowfficer/page/back"] = True
    assert adapter.appear(NamedButton("MEOWFFICER_CHECK"))


def test_meow_page_has_no_campaign_confirm_and_main_has_no_dock():
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values["meowfficer/page/back"] = True
    assert not adapter.appear(NamedButton("CAMPAIGN_WITHDRAW_CONFIRM"))
    oracle.main_page_visible_value = True
    assert not adapter.appear(NamedButton("DOCK_CHECK"))


def test_meow_loading_underlay_has_no_campaign_confirm():
    from types import SimpleNamespace
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values["meowfficer/page/back"] = True
    oracle._blocking_rules = Mock(return_value=(SimpleNamespace(blocker_id="meowfficer-dock"),
                                              SimpleNamespace(blocker_id="loading")))
    oracle.click = Mock()
    assert not adapter.appear(NamedButton("CAMPAIGN_WITHDRAW_CONFIRM"))
    oracle.click.assert_not_called()


def test_loading_hides_reward_and_page_probes_even_with_business_underlay():
    from types import SimpleNamespace
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle._blocking_rules = Mock(return_value=(SimpleNamespace(blocker_id="commission-page"),
                                              SimpleNamespace(blocker_id="loading")))
    oracle.click = Mock()
    for name in ("GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3", "FLEET_CHECK"):
        assert not adapter.appear(NamedButton(name))
    oracle.click.assert_not_called()


@pytest.mark.parametrize('notice_present', [False, True])
def test_meow_page_urgent_notice_probe_keeps_actual_notice_guard(notice_present):
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values['meowfficer/page/back'] = True
    oracle._campaign_urgent_notice_matches = Mock(return_value=notice_present)
    oracle.click = Mock()
    if notice_present:
        with pytest.raises(SemanticGateClosed, match='urgent commission notice'):
            adapter.appear(NamedButton('GET_MISSION'))
    else:
        assert not adapter.appear(NamedButton('GET_MISSION'))
    oracle.click.assert_not_called()


@pytest.mark.parametrize('name',['WITHDRAW','CAMPAIGN_WITHDRAW_CONFIRM','DOCK_CHECK'])
def test_unobscured_main_owns_withdraw_absence_with_retained_campaign_context(name):
    from tests.semantic_support.adapter_fixtures import NamedButton
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._campaign_context=_CampaignFlowContext(stage_code='7-2')
    oracle.main_page_visible_value=True
    assert not adapter.appear(NamedButton(name))
    assert oracle.click_calls==[]


def test_obscured_main_does_not_override_withdraw_probe_owner():
    from types import SimpleNamespace
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._campaign_context=_CampaignFlowContext(stage_code='7-2')
    oracle.main_page_visible_value=True
    oracle.read_ui_state=Mock(return_value=SimpleNamespace(texts=()))
    oracle._blocking_rules=Mock(return_value=(SimpleNamespace(blocker_id="unknown"),))
    assert adapter._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM') is UNHANDLED


def test_unknown_surface_does_not_prove_dock_absence_with_retained_context():
    from types import SimpleNamespace
    from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
    from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
    adapter,oracle,_=AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._campaign_context=_CampaignFlowContext(stage_code='7-2')
    oracle.read_ui_state=Mock(return_value=SimpleNamespace(texts=()))
    oracle._blocking_rules=Mock(return_value=(SimpleNamespace(blocker_id="unknown"),))
    assert adapter._appear_priority('DOCK_CHECK') is UNHANDLED
    assert oracle.click_calls==[]
