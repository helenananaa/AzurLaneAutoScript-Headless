"""Fault containment at shared ALAS observation and confirmation boundaries."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from alas_headless.oracle.surfaces import ObservationSurface
from alas_headless.adapter.semantic.resources import UI_PAGE_CHECK_RESOURCES
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import (
    DRIVER_REVISION, FakeBackend, make_button, make_oracle, make_text, make_ui,
)


def real_adapter(backend):
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(
        oracle, lambda: None,
        frame_observation_oracle=lambda: oracle,
        frame_identity_provider=AlasSemanticAdapterTestsSupport.frame_identity,
    )
    return adapter, oracle


def main_buttons():
    return [
        make_button("battle", "UICamera/Canvas/UIMain/MainUI/frame/right/1/battle"),
        make_button("formation", "UICamera/Canvas/UIMain/MainUI/frame/right/1/formation"),
    ]


def poison_unrelated_readers(monkeypatch, oracle):
    readers = []
    for method in (
        "operation_siren_reset_shop_visible",
        "operation_siren_reset_fleet_visible",
        "raid_page_visible",
        "event_story_dialogue_visible",
        "event_story_skip_prompt_visible",
        "daily_combat_visible",
    ):
        reader = Mock(side_effect=SemanticGateClosed("injected optional parser failure: " + method))
        monkeypatch.setattr(oracle, method, reader)
        readers.append(reader)
    return readers


def test_main_page_sweep_and_session_survive_unrelated_parser_failures(monkeypatch):
    backend = FakeBackend(main_buttons())
    adapter, oracle = real_adapter(backend)
    readers = poison_unrelated_readers(monkeypatch, oracle)
    session = AlasSemanticSession(serial="offline-test", driver_revision=DRIVER_REVISION)
    session.adapter = adapter

    for resource in sorted(UI_PAGE_CHECK_RESOURCES):
        assert session.appear(NamedButton(resource)) is (
            resource in ("MAIN_GOTO_FLEET", "MAIN_GOTO_CAMPAIGN_WHITE")
        )
    for reader in readers:
        reader.assert_not_called()
    assert backend.taps == []


@pytest.mark.parametrize("page", ["research", "mission"])
def test_other_task_pages_skip_failed_optional_readers(monkeypatch, page):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    if page == "research":
        adapter.begin_research()
        oracle.exists_values["research/page/back"] = True
        oracle.research_project_values = [SimpleNamespace(slot=i) for i in range(5)]
        expected = "RESEARCH_CHECK"
    else:
        oracle.exists_values["task/page/back"] = True
        expected = "MISSION_CHECK"
    # The generic fixture's optional monthstart methods are deliberately absent.
    for name in ("operation_siren_reset_shop_visible", "operation_siren_reset_fleet_visible"):
        monkeypatch.setattr(oracle, name, Mock(), raising=False)
    readers = poison_unrelated_readers(monkeypatch, oracle)
    assert adapter.appear(NamedButton(expected))
    assert adapter.appear(NamedButton("FLEET_CHECK")) is False
    for reader in readers:
        reader.assert_not_called()


def test_broken_reset_fleet_hides_underlay_without_breaking_page_scan():
    backend = FakeBackend(main_buttons() + [
        make_button("bg", "UICamera/Canvas/UIMain/WorldFleetSelect(Clone)/bg"),
    ])
    adapter, oracle = real_adapter(backend)
    # The owner is mounted but its detached start control is missing.
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")) is False
    assert adapter.appear(NamedButton("RESEARCH_CHECK")) is False
    with pytest.raises(SemanticGateClosed, match="start is missing"):
        adapter.appear(NamedButton("RESET_FLEET_PREPARATION"))
    with pytest.raises(SemanticGateClosed, match="start is missing"):
        adapter.click(NamedButton("RESET_FLEET_PREPARATION"))
    assert backend.taps == []

    # Recovery is a new observed surface on the same adapter, without a sticky
    # global capability-denied flag or a new session.
    backend.buttons["buttons"] = main_buttons()
    backend.buttons["button_count"] = 2
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))


def shop_prompt_backend(label="确 定", message="大型作战已经重置，是否打开特别兑换商店？"):
    root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
    path = root + "button_container/custom_button_1(Clone)"
    backend = FakeBackend(main_buttons() + [make_button("custom_button_1(Clone)", path, raycast_top=None)])
    backend.ui = make_ui([
        make_text(message, root + "msg_panel/content"),
        make_text(label, path + "/pic"),
    ])
    return backend


def test_reset_shop_keeps_valid_navigation_and_rejects_changed_action_label():
    backend = shop_prompt_backend()
    adapter, _ = real_adapter(backend)
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")) is False
    assert adapter.appear(NamedButton("POPUP_CONFIRM"))
    assert adapter.click(NamedButton("POPUP_CONFIRM")).semantic_id == "os/reset/shop"
    assert len(backend.taps) == 1

    backend = shop_prompt_backend(label="购买")
    adapter, _ = real_adapter(backend)
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")) is False
    with pytest.raises(SemanticGateClosed, match="confirmation label changed"):
        adapter.appear(NamedButton("POPUP_CONFIRM"))
    with pytest.raises(SemanticGateClosed, match="confirmation label changed"):
        adapter.click(NamedButton("POPUP_CONFIRM"))
    assert backend.taps == []


def test_other_confirmation_does_not_enter_reset_parser(monkeypatch):
    backend = shop_prompt_backend(message="是否购买物品？")
    adapter, oracle = real_adapter(backend)
    reader = Mock(side_effect=RuntimeError("optional reset implementation is broken"))
    monkeypatch.setattr(oracle, "operation_siren_reset_shop_visible", reader)
    monkeypatch.setattr(oracle, "click_operation_siren_reset_shop", reader)
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")) is False
    # Unknown confirmation cannot borrow either main-page or reset authority.
    with pytest.raises(SemanticGateClosed):
        adapter.click(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
    with pytest.raises(SemanticGateClosed):
        adapter.click(NamedButton("POPUP_CONFIRM"))
    reader.assert_not_called()
    assert backend.taps == []


def test_confirmation_routing_uses_complete_text_without_requiring_images():
    backend = shop_prompt_backend(message="是否购买物品？")
    backend.ui["image_truncated"] = True
    _, oracle = real_adapter(backend)
    assert not oracle.observation_surface_present(ObservationSurface.RESET_SHOP)
    backend.ui["text_truncated"] = True
    with pytest.raises(SemanticGateClosed, match="text snapshot is truncated"):
        oracle.observation_surface_present(ObservationSurface.RESET_SHOP)
    assert backend.taps == []


def test_malformed_story_still_hides_page_without_parsing_choices(monkeypatch):
    root = "OverlayCamera/Overlay/UIOverlay/NewStoryUI(Clone)"
    backend = FakeBackend(main_buttons() + [
        make_button("NewStoryUI(Clone)", root),
        make_button("NewStoryUI(Clone)", root),
    ])
    adapter, oracle = real_adapter(backend)
    reader = Mock(side_effect=SemanticGateClosed("story parser failed"))
    monkeypatch.setattr(oracle, "event_story_dialogue_visible", reader)
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")) is False
    assert adapter.appear(NamedButton("RAID_CHECK")) is False
    reader.assert_not_called()
    with pytest.raises(SemanticGateClosed):
        adapter.click(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
    assert backend.taps == []


def test_surface_routing_tolerates_reparenting_and_inactive_retained_objects():
    backend = FakeBackend(main_buttons() + [
        make_button("bg", "NewParent/WorldFleetSelect(Clone)/bg"),
    ])
    adapter, oracle = real_adapter(backend)
    assert oracle.observation_surface_present(ObservationSurface.RESET_FLEET)
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE")) is False
    backend.buttons["buttons"][-1]["active_in_hierarchy"] = False
    backend.buttons["buttons"].reverse()
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))


@pytest.mark.parametrize("inactive", [False, True])
def test_root_blocker_does_not_match_similar_name_or_inactive_owner(inactive):
    owner = "NewStoryUI(Clone)" if inactive else "NewStoryUI(Clone)Preview"
    button = make_button(owner, "OverlayCamera/Overlay/UIOverlay/" + owner)
    button["active_in_hierarchy"] = not inactive
    backend = FakeBackend(main_buttons() + [button])
    adapter, _ = real_adapter(backend)
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
    adapter.click(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
    assert len(backend.taps) == 1


def test_runtime_identity_failure_is_not_hidden_by_task_isolation():
    backend = FakeBackend(main_buttons())
    backend.snapshot["package"] = "other.package"
    adapter, _ = real_adapter(backend)
    with pytest.raises(SemanticGateClosed):
        adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
    assert backend.taps == []


def test_guild_notification_hides_main_before_its_fast_page_route():
    root = "OverlayCamera/Overlay/UIMain/GuildMsgBoxUI(Clone)"
    backend = FakeBackend(main_buttons() + [make_button("close", root + "/frame/close")])
    adapter, _ = real_adapter(backend)
    adapter.begin_mission_reward(daily=False, weekly=False)
    assert not adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
    assert adapter.appear(NamedButton("GUILD_POPUP_CANCEL"))
    with pytest.raises(SemanticGateClosed):
        adapter.click(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
    receipt = adapter.click(NamedButton("GUILD_POPUP_CANCEL"))
    assert receipt.semantic_id == "overlay/guild-message/close"
    assert len(backend.taps) == 1
    backend.buttons["buttons"] = main_buttons()
    backend.buttons["button_count"] = 2
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))


def test_reward_sidebar_wins_over_retained_main_page_and_closes_normally():
    path = "OverlayCamera/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)"
    backend = FakeBackend(main_buttons() + [make_button("CommissionInfoUI4Mellow(Clone)", path)])
    adapter, _ = real_adapter(backend)
    assert adapter.appear(NamedButton("REWARD_CHECK"))
    assert not adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))
    assert adapter.click(NamedButton("REWARD_GOTO_MAIN")).semantic_id == "reward/page/back"
    assert len(backend.taps) == 1
    backend.buttons["buttons"][-1]["active_in_hierarchy"] = False
    assert not adapter.appear(NamedButton("REWARD_CHECK"))
    assert adapter.appear(NamedButton("MAIN_GOTO_CAMPAIGN_WHITE"))


def test_repeated_reward_close_accepts_only_its_proven_destination():
    backend = FakeBackend(main_buttons())
    adapter, _ = real_adapter(backend)
    assert adapter.click(NamedButton("REWARD_GOTO_MAIN")).semantic_id == "main/already"
    assert backend.taps == []
    backend.buttons["buttons"] = []
    backend.buttons["button_count"] = 0
    with pytest.raises(SemanticGateClosed):
        adapter.click(NamedButton("REWARD_GOTO_MAIN"))
    backend.buttons["buttons"] = main_buttons() + [make_button(
        "close", "OverlayCamera/Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/close")]
    backend.buttons["button_count"] = 3
    with pytest.raises(SemanticGateClosed):
        adapter.click(NamedButton("REWARD_GOTO_MAIN"))
    assert backend.taps == []


def test_mission_home_navigation_skips_absent_business_parsers(monkeypatch):
    backend = FakeBackend([make_button("back", "root/TaskScene(Clone)/blur_panel/adapt/top/back")])
    adapter, oracle = real_adapter(backend)
    # Use the repository's reviewed mapping, independent of parent hierarchy.
    target = oracle._targets["task/page/back"]
    backend.buttons["buttons"] = [make_button(target.name, "root/" + target.path_suffix)]
    readers = []
    for name in ("recommendation_shop_visible", "guild_page_visible", "raid_page_visible",
                 "operation_siren_page_visible", "meta_page_visible", "game_room_page_visible",
                 "battle_pass_page_visible"):
        reader = Mock(side_effect=SemanticGateClosed("unrelated parser failure"))
        monkeypatch.setattr(oracle, name, reader)
        readers.append(reader)
    assert adapter._goto_main_target() == "task/page/back"
    assert adapter.click(NamedButton("GOTO_MAIN")).semantic_id == "task/page/back"
    assert len(backend.taps) == 1
    for reader in readers:
        reader.assert_not_called()


def test_home_navigation_keeps_ambiguity_rejection():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    oracle.exists_values.update({"task/page/back": True, "research/page/back": True})
    with pytest.raises(SemanticGateClosed, match="ambiguous"):
        adapter.click(NamedButton("GOTO_MAIN"))
    assert oracle.click_calls == []


def test_absent_shop_pages_skip_their_detailed_parsers(monkeypatch):
    adapter, oracle = real_adapter(FakeBackend(main_buttons()))
    for resource, method in (("SHOP_CHECK", "recommendation_shop_visible"),
                             ("BATTLE_PASS_CHECK", "battle_pass_page_visible"),
                             ("WAR_ARCHIVES_CHECK", "war_archives_page_visible")):
        reader = Mock(side_effect=RuntimeError("unrelated parser failure"))
        monkeypatch.setattr(oracle, method, reader)
        assert adapter.appear(NamedButton(resource)) is False
        reader.assert_not_called()


@pytest.mark.parametrize("message,kind", [
    ("需要暂时离开大型作战么？", "opsi-exit"),
    ("深渊海域作战难度较高且不可重复进入，\n请确认舰队战备后前往作战", "opsi-abyssal-entry"),
    ("保存当前编队并出击？", "meta-sortie"),
    ("是否进入当前信标META的模拟战斗？\n战斗强度：Lv15\n", "meta-simulation"),
])
def test_popup_routes_only_to_its_owner(monkeypatch, message, kind):
    backend = shop_prompt_backend(message=message)
    adapter, oracle = real_adapter(backend)
    methods = {"opsi-exit": "operation_siren_exit_prompt_visible",
               "opsi-abyssal-entry": "operation_siren_abyssal_entry_prompt_visible",
               "meta-sortie": "meta_assist_sortie_prompt_visible",
               "meta-simulation": "meta_simulation_prompt_visible"}
    for other, method in methods.items():
        if other != kind:
            monkeypatch.setattr(oracle, method, Mock(side_effect=RuntimeError("wrong owner")))
    assert oracle.observation_prompt_kind() == kind
    # Ownership only selects the parser; it is not a substitute for its contract.
    reader = Mock(side_effect=SemanticGateClosed("owned structure is malformed"))
    monkeypatch.setattr(oracle, methods[kind], reader)
    with pytest.raises(SemanticGateClosed, match="owned structure"):
        adapter.appear(NamedButton("POPUP_CONFIRM"))
    with pytest.raises(SemanticGateClosed, match="owned structure"):
        adapter.click(NamedButton("POPUP_CONFIRM"))
    assert backend.taps == []


def test_unmapped_fallback_does_not_replace_error_with_absent_combat_failure(monkeypatch):
    from alas_headless import AlasSemanticUnmapped
    adapter, oracle = real_adapter(FakeBackend(main_buttons()))
    session = AlasSemanticSession(serial="offline-test", driver_revision=DRIVER_REVISION)
    session.adapter = adapter
    session.refresh_frame = lambda: None
    monkeypatch.setattr(adapter, "appear", Mock(side_effect=AlasSemanticUnmapped("optional")))
    for method in ("daily_combat_visible", "daily_battle_result_visible", "raid_page_visible"):
        monkeypatch.setattr(oracle, method, Mock(side_effect=RuntimeError("absent combat parser")))
    with pytest.raises(AlasSemanticUnmapped):
        session.appear(NamedButton("UNREVIEWED_OPTIONAL_FEATURE"))
