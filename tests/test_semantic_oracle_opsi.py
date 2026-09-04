"""Opsi regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import SemanticGateClosed, SemanticTargetMissing
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_text,
    make_toggle,
    make_ui,
)
from tests.semantic_support.oracle_cases import (
    OperationSirenSemanticOracleTestsSupport,
    SemanticOracleTestsSupport,
)
from unittest import mock


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_operation_siren_event_trigger_result_click_is_exact(self):
        root = "OverlayCamera/Overlay/UIMain/NewBattleResultEmptyUI(Clone)"
        continue_path = (
            root
            + "/NewBattleResultGradePage(Clone)/bg/ResultEffect/Tips/"
            "dianjijixu/bg20"
        )
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "点击继续",
                    continue_path,
                    {"left": 160.0, "top": 617.0, "right": 264.0, "bottom": 643.0},
                ),
                make_text("VICTORY", root + "/Effect/bg03/Text"),
            ],
            images=[
                make_image(root, "bg_mask"),
                make_image(root + "/Effect", "jiesuan_bg02"),
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.daily_battle_result_visible())
        receipt = oracle.click_daily_battle_result()

        self.assertEqual(receipt.semantic_id, "operation-siren/battle/result")
        self.assertEqual(receipt.path, continue_path)
        self.assertEqual(backend.taps, [(212, 630)])
        self.assertEqual(oracle.operation_siren_battle_result_grade(), "VICTORY")

        backend.taps.clear()
        backend.ui["texts"][1]["text"] = "DEFEAT"
        self.assertTrue(oracle.operation_siren_battle_result_visible())
        self.assertEqual(oracle.operation_siren_battle_result_grade(), "DEFEAT")
        receipt = oracle.click_daily_battle_result()
        self.assertEqual(receipt.semantic_id, "operation-siren/battle/result")
        self.assertEqual(backend.taps, [(212, 630)])

        backend.taps.clear()
        backend.ui["texts"][1]["text"] = "UNKNOWN"
        self.assertFalse(oracle.daily_battle_result_visible())
        with self.assertRaisesRegex(SemanticGateClosed, "absent"):
            oracle.click_daily_battle_result()
        self.assertEqual(backend.taps, [])


class OperationSirenSemanticOracleTests(OperationSirenSemanticOracleTestsSupport, unittest.TestCase):
    def test_meta_assist_state_binds_selected_candidate_and_next_input(self):
        backend = self._meta_assist_backend(selected_index=2)
        oracle = make_oracle(backend)

        state = oracle.meta_assist_state()
        self.assertEqual(state.remaining_attempts, 3)
        self.assertEqual(state.selected_level, 15)
        self.assertEqual(state.candidate_count, 3)
        self.assertEqual(state.selected_candidate_index, 2)

        receipt = oracle.click_meta_assist_next_candidate(
            expected_index=2,
            expected_level=15,
        )
        self.assertEqual(receipt.semantic_id, "meta/assist/candidate/3")
        self.assertEqual(backend.taps, [(260, 400)])

    def test_meta_assist_next_candidate_rejects_stale_selection(self):
        backend = self._meta_assist_backend(selected_index=2)
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "changed before selection"):
            oracle.click_meta_assist_next_candidate(
                expected_index=1,
                expected_level=15,
            )
        self.assertEqual(backend.taps, [])

    def test_meta_assist_state_rejects_missing_selected_identity(self):
        backend = self._meta_assist_backend(selected_index=2)
        backend.ui["texts"].pop()
        backend.ui["text_count"] -= 1
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "selected.*ambiguous"):
            oracle.meta_assist_state()
        self.assertEqual(backend.taps, [])

    def test_operation_siren_header_allows_ap_above_regeneration_capacity(self):
        state = make_oracle(
            self._operation_siren_header_backend(340)
        ).operation_siren_state()

        self.assertEqual(state.action_points, 340)
        self.assertEqual(state.action_point_capacity, 200)

    def test_operation_siren_header_rejects_ap_above_legacy_safety_bound(self):
        with self.assertRaisesRegex(SemanticGateClosed, "summary is inconsistent"):
            make_oracle(
                self._operation_siren_header_backend(601)
            ).operation_siren_state()

    def test_map_exit_owner_unmounted_is_an_idempotent_missing_target(self):
        oracle = make_oracle(FakeBackend([]))

        with self.assertRaisesRegex(
            SemanticTargetMissing, "local-map identity is absent"
        ):
            oracle.click_operation_siren_map_exit()

    def test_auto_search_distinguishes_normal_off_from_on(self):
        root = "WorldMapUI(Clone)/top/adapt/right_stage/btn_list/auto_fight/"
        self.assertEqual(self._state(make_button("off", root + "off")), "off")
        self.assertEqual(self._state(make_button("on", root + "on")), "on")

    def test_auto_search_rejects_absent_or_ambiguous_state(self):
        root = "WorldMapUI(Clone)/top/adapt/right_stage/btn_list/auto_fight/"
        with self.assertRaisesRegex(SemanticGateClosed, "absent or inconsistent"):
            self._state()
        with self.assertRaisesRegex(SemanticGateClosed, "absent or inconsistent"):
            self._state(
                make_button("off", root + "off"),
                make_button("on", root + "on"),
            )

    def test_strategic_search_distinguishes_off_popup_and_on(self):
        switch = "WorldMapUI(Clone)/top/adapt/right_stage/btn_list/auto_switch/"
        oracle = make_oracle(FakeBackend([make_button("off", switch + "off")]))
        with mock.patch.object(oracle, "operation_siren_state"):
            self.assertEqual(oracle.operation_siren_strategic_search_state(), "off")

        oracle = make_oracle(FakeBackend([make_button("on", switch + "on")]))
        with mock.patch.object(oracle, "operation_siren_state"):
            self.assertEqual(oracle.operation_siren_strategic_search_state(), "on")

        root = (
            "root/OverlayCamera/Overlay/UIMain/WorldSwitchPlanningUI(Clone)/"
            "window/button_container/"
        )
        oracle = make_oracle(
            FakeBackend(
                [
                    make_button("custom_button_1", root + "custom_button_1"),
                    make_button("custom_button_2", root + "custom_button_2"),
                ]
            )
        )
        self.assertEqual(
            oracle.operation_siren_strategic_search_state(), "configuring"
        )

    def test_strategic_search_toggle_accepts_exact_delegated_popup(self):
        root = "root/OverlayCamera/Overlay/UIMain/WorldSwitchPlanningUI(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1",
                    root + "window/button_container/custom_button_1",
                    raycast_top=None,
                ),
                make_button(
                    "custom_button_2",
                    root + "window/button_container/custom_button_2",
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    root + "window/content/toggles/toggle_safe",
                    raycast_top=None,
                    x=640,
                    y=243,
                )
            ],
        )

        receipt = make_oracle(backend).click_toggle(
            "os/strategic-search/tab/secured"
        )

        self.assertEqual(receipt.semantic_id, "os/strategic-search/tab/secured")
        self.assertEqual(backend.taps, [(640, 243)])

    def test_strategic_search_entry_and_confirm_accept_exact_delegated_buttons(self):
        switch = (
            "root/OverlayCamera/Overlay/UIMain/top/adapt/right_stage/"
            "btn_list/auto_switch/off"
        )
        backend = FakeBackend(
            [make_button("off", switch, x=1225, y=598, raycast_top=None)]
        )
        oracle = make_oracle(backend)
        with mock.patch.object(oracle, "operation_siren_state"):
            receipt = oracle.click("os/map/strategic-search/off")
        self.assertEqual(receipt.semantic_id, "os/map/strategic-search/off")
        self.assertEqual(backend.taps, [(1225, 598)])

        root = (
            "root/OverlayCamera/Overlay/UIMain/WorldSwitchPlanningUI(Clone)/"
            "window/button_container/"
        )
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1",
                    root + "custom_button_1",
                    x=783,
                    y=528,
                    raycast_top=None,
                ),
                make_button(
                    "custom_button_2",
                    root + "custom_button_2",
                    x=497,
                    y=528,
                    raycast_top=None,
                ),
            ]
        )
        receipt = make_oracle(backend).click("os/strategic-search/confirm")
        self.assertEqual(receipt.semantic_id, "os/strategic-search/confirm")
        self.assertEqual(backend.taps, [(783, 528)])

    def test_strategic_search_scroll_proves_auto_submit_visible(self):
        root = "root/OverlayCamera/Overlay/UIMain/WorldSwitchPlanningUI(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1",
                    root + "window/button_container/custom_button_1",
                    raycast_top=None,
                ),
                make_button(
                    "custom_button_2",
                    root + "window/button_container/custom_button_2",
                    raycast_top=None,
                ),
            ]
        )
        handle = make_image(
            root + "window/content/scrollbar/Sliding Area/Handle",
            "scroll_bar",
            {"left": 901, "top": 273, "right": 913, "bottom": 350},
        )
        handle["raycast_target"] = True
        target_path = root + "window/content/view/content/consume/toggles/yes"
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    target_path,
                    raycast_top=None,
                    x=510,
                    y=774,
                    bounds={"left": 480, "top": 756, "right": 540, "bottom": 792},
                )
            ],
            images=[handle],
        )

        def reveal():
            backend.ui = make_ui(
                [],
                toggles=[
                    make_toggle(
                        target_path,
                        raycast_top=None,
                        x=510,
                        y=558,
                        bounds={
                            "left": 480,
                            "top": 540,
                            "right": 540,
                            "bottom": 576,
                        },
                    )
                ],
                images=[handle],
                generation=11,
            )

        backend.on_swipe = reveal
        receipt = make_oracle(
            backend
        ).operation_siren_strategic_search_scroll_to_bottom()

        self.assertEqual(receipt.semantic_id, "os/strategic-search/scroll/bottom")
        self.assertEqual(backend.swipes, [(907, 312, 907, 430, 450)])

    def test_local_map_shell_is_blocked_by_order_overlay(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "LevelCamera/Canvas/LevelOrigin/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "LevelCamera/Canvas/LevelOrigin/top/adapt/left_stage/other/fleet_bar",
                ),
                make_button(
                    "back",
                    "OverlayCamera/Overlay/UIMain/SVOrderPanel(Clone)/adapt/back",
                ),
            ]
        )

        self.assertFalse(
            make_oracle(backend).operation_siren_local_map_visible()
        )

    def test_low_resolve_prompt_requires_exact_message_and_cancel(self):
        path = (
            "root/UICamera/Canvas/UIMain/Msgbox(Clone)/window/"
            "button_container/custom_button_2(Clone)"
        )
        backend = FakeBackend(
            [make_button("custom_button_2(Clone)", path, x=640, y=526)]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "当前舰队士气过低，无法与强敌战斗！\n"
                    "提示：取得任意战斗胜利均可恢复舰队的士气。",
                    "root/UICamera/Canvas/UIMain/Msgbox(Clone)/window/"
                    "msg_panel/content",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.operation_siren_low_resolve_prompt_visible())
        receipt = oracle.click_operation_siren_low_resolve_cancel()

        self.assertEqual(receipt.semantic_id, "os/combat/low-resolve/cancel")
        self.assertEqual(backend.taps, [(640, 526)])
        backend.ui = make_ui(
            [
                make_text(
                    "当前舰队状态异常。",
                    "root/UICamera/Canvas/UIMain/Msgbox(Clone)/window/"
                    "msg_panel/content",
                )
            ]
        )
        self.assertFalse(oracle.operation_siren_low_resolve_prompt_visible())

    def test_operation_siren_submarine_return_exit_prompt_is_exact(self):
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    "root/Msgbox(Clone)/window/button_container/"
                    "custom_button_1(Clone)",
                ),
                make_button(
                    "custom_button_2(Clone)",
                    "root/Msgbox(Clone)/window/button_container/"
                    "custom_button_2(Clone)",
                ),
            ]
        )
        prompt_path = "root/Msgbox(Clone)/window/msg_panel/content"
        backend.ui = make_ui(
            [
                make_text(
                    "离开当前海域后，潜艇舰队会自动返回我方港口待命，是否离开？",
                    prompt_path,
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.operation_siren_exit_prompt_visible())

        backend.ui = make_ui([make_text("是否离开？", prompt_path)])
        self.assertFalse(oracle.operation_siren_exit_prompt_visible())

        backend.ui = make_ui(
            [
                make_text(
                    "是否确定从深渊海域离开？\n"
                    "（警告：离开后将无法再次返回挑战强敌！）",
                    prompt_path,
                )
            ]
        )
        self.assertTrue(oracle.operation_siren_exit_prompt_visible())

        backend.ui = make_ui(
            [
                make_text(
                    "是否确定从该处隐秘海域离开？\n"
                    "（离开后将无法再次返回）",
                    prompt_path,
                )
            ]
        )
        self.assertTrue(oracle.operation_siren_exit_prompt_visible())

        backend.ui = make_ui(
            [
                make_text(
                    "困难难度：仲裁者·司特莲库斯·VIII",
                    "root/top/adapt/top_stage/title/name",
                ),
                make_text(
                    "是否确定从困难难度：仲裁者·司特莲库斯·VIII中离开？\n"
                    "（离开后当前作战进度将会重置，已获得的奖励无法重复领取）",
                    prompt_path,
                ),
            ]
        )
        self.assertTrue(oracle.operation_siren_exit_prompt_visible())

    def test_operation_siren_abyssal_entry_prompt_is_exact_and_clickable(self):
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    "root/Msgbox(Clone)/window/button_container/"
                    "custom_button_1(Clone)",
                ),
                make_button(
                    "custom_button_2(Clone)",
                    "root/Msgbox(Clone)/window/button_container/"
                    "custom_button_2(Clone)",
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "深渊海域作战难度较高且不可重复进入，\n"
                    "请确认舰队战备后前往作战",
                    "root/Msgbox(Clone)/window/msg_panel/content",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.operation_siren_abyssal_entry_prompt_visible())
        receipt = oracle.click_operation_siren_abyssal_entry(True)
        self.assertEqual(receipt.semantic_id, "os/abyssal/entry/confirm")

        backend.ui = make_ui(
            [
                make_text(
                    "深渊海域作战难度较高且不可重复进入",
                    "root/Msgbox(Clone)/window/msg_panel/content",
                )
            ]
        )
        self.assertFalse(oracle.operation_siren_abyssal_entry_prompt_visible())

    def test_operation_siren_abyssal_exit_uses_nearest_exact_floor_model(self):
        backend = FakeBackend([])
        title = make_text(
            "加勒比海A-深渊海域",
            "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/title/name",
        )
        locked = make_image(
            "root/LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "cell_6_6/attachments/event_4100212/icon/model/"
            "taban_jinzhi(Clone)/taban",
            "taban01",
            {"left": 560, "top": 700, "right": 720, "bottom": 850},
        )
        distant_unlocked = make_image(
            "root/LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "cell_13_6/attachments/event_4100203/icon/model/"
            "taban(Clone)/taban",
            "taban01",
            {"left": 530, "top": 1750, "right": 750, "bottom": 1950},
        )
        backend.ui = make_ui([title], images=[locked, distant_unlocked])
        oracle = make_oracle(backend)

        self.assertFalse(oracle.operation_siren_abyssal_exit_available())

        unlocked = make_image(
            "root/LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            "cell_6_6/attachments/event_4100212/icon/model/"
            "taban(Clone)/taban",
            "taban01",
            {"left": 572, "top": 445, "right": 708, "bottom": 565},
        )
        backend.ui = make_ui([title], images=[unlocked, distant_unlocked])
        self.assertTrue(oracle.operation_siren_abyssal_exit_available())
        receipt = oracle.click_operation_siren_abyssal_exit()
        self.assertEqual(receipt.semantic_id, "os/abyssal/exit")
        self.assertEqual(backend.taps, [(640, 505)])

        backend.ui = make_ui(
            [
                make_text(
                    "加勒比海A-隐匿海域",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/"
                    "top_stage/title/name",
                )
            ],
            images=[unlocked],
        )
        self.assertFalse(oracle.operation_siren_abyssal_exit_available())

    def test_operation_siren_world_overview_is_exact_and_clickable(self):
        path = "root/OverlayCamera/Overlay/UIMain/WorldOverviewUI(Clone)/bg"
        backend = FakeBackend(
            [make_button("bg", path, x=640, y=360, raycast_top=None)]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "点击任意位置返回",
                    "root/OverlayCamera/Overlay/UIMain/"
                    "WorldOverviewUI(Clone)/tip/Text",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.operation_siren_world_overview_visible())
        receipt = oracle.click_operation_siren_world_overview()
        self.assertEqual(receipt.semantic_id, "os/world-overview/close")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui = make_ui(
            [make_text("点击返回", "root/WorldOverviewUI(Clone)/tip/Text")]
        )
        self.assertFalse(oracle.operation_siren_world_overview_visible())

    def test_month_boss_room_difficulty_uses_exact_retained_title(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        title_path = (
            "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/title/name"
        )
        backend.ui = make_ui(
            [make_text("普通难度：仲裁者·司特劳斯·VIII", title_path)]
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.operation_siren_month_boss_room_difficulty(),
            "normal",
        )
        backend.ui = make_ui(
            [make_text("困难难度：仲裁者·司特劳斯·VIII", title_path)]
        )
        self.assertEqual(
            oracle.operation_siren_month_boss_room_difficulty(),
            "hard",
        )
        backend.ui = make_ui([make_text("NA海域西南B-安全海域", title_path)])
        with self.assertRaisesRegex(SemanticGateClosed, "title"):
            oracle.operation_siren_month_boss_room_difficulty()

    def test_auto_search_info_count_accepts_only_reviewed_os_messages(self):
        backend = FakeBackend([])
        path = (
            "OverlayCamera/Overlay/UIOverlay/TipPanel(Clone)/Grid/"
            "toolTip(Clone)/Text"
        )
        backend.ui = make_ui(
            [
                make_text(
                    "<color=white>当前所选舰队开始自律寻敌</color>",
                    path,
                ),
                make_text(
                    "<color=white>当前所选舰队视野内无可自律事件，无法继续自律寻敌</color>",
                    path,
                ),
                make_text("其他提示", path),
            ]
        )

        self.assertEqual(
            make_oracle(backend).operation_siren_auto_search_info_count(),
            2,
        )

    def test_auto_search_reward_close_is_exact_and_actionable(self):
        path = (
            "root/OverlayCamera/Overlay/UIMain/WorldAutoFightRewardUI(Clone)/"
            "Window/Fixed/ButtonExit"
        )
        backend = FakeBackend(
            [make_button("ButtonExit", path, x=640, y=600, raycast_top=True)]
        )
        oracle = make_oracle(backend)
        self.assertTrue(oracle.enabled("os/auto-search/reward/close"))
        receipt = oracle.click("os/auto-search/reward/close")
        self.assertEqual(receipt.semantic_id, "os/auto-search/reward/close")
        self.assertEqual(backend.taps, [(640, 600)])

    def test_operation_siren_order_confirmation_uses_exact_cost_prompt(self):
        root = "root/OverlayCamera/Overlay/UIMain/"
        panel = root + "SVOrderPanel(Clone)/adapt/"
        fov = panel + "order_list/fov/type_enable"
        backend = FakeBackend(
            [
                make_button("back", panel + "back", x=60, y=60),
                make_button("type_enable", fov, x=1070, y=423),
                make_button(
                    "btn_confirm",
                    root + "Msgbox/window/button_container/btn_confirm",
                    x=790,
                    y=542,
                ),
                make_button(
                    "btn_cancel",
                    root + "Msgbox/window/button_container/btn_cancel",
                    x=490,
                    y=542,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0", fov + "/cost/Text"),
                make_text(
                    "是否消耗<color=#92FC63FF>0</color>行动力，\n"
                    "侦查当前海域的全部区域？",
                    root + "Msgbox/window/msg_panel/base/content",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(
            oracle.operation_siren_order_confirmation_visible("scan")
        )
        receipt = oracle.click_operation_siren_order_confirmation(
            "scan", confirm=True
        )
        self.assertEqual(receipt.semantic_id, "os/order/confirm")
        self.assertEqual(backend.taps, [(790, 542)])

        # The modal overlay legitimately disables the order panel behind it.
        # Its exact back/order identities still bind the prompt to the pending
        # typed order, while only confirm/cancel must remain actionable.
        backend.buttons["buttons"][0]["active_and_enabled"] = False
        backend.buttons["buttons"][0]["interactable"] = False
        backend.buttons["buttons"][0].pop("adb_point")
        backend.buttons["buttons"][1]["active_and_enabled"] = False
        backend.buttons["buttons"][1]["interactable"] = False
        backend.buttons["buttons"][1].pop("adb_point")
        self.assertTrue(
            oracle.operation_siren_order_confirmation_visible("scan")
        )

        backend.ui["texts"][1]["text"] = (
            "是否消耗<color=#92FC63FF>10</color>行动力，\n"
            "侦查当前海域的全部区域？"
        )
        with self.assertRaisesRegex(SemanticGateClosed, "cost changed"):
            oracle.operation_siren_order_confirmation_visible("scan")

        backend.ui["texts"][0]["text"] = "5"
        backend.ui["texts"][1]["text"] = (
            "是否消耗<color=#92FC63FF>4</color>行动力，\n"
            "侦查当前海域的全部区域？"
        )
        self.assertTrue(
            oracle.operation_siren_order_confirmation_visible("scan")
        )

    def test_battle_pass_reward_uses_exact_notice_and_delegated_entrance(self):
        reward_root = "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)"
        entrance = reward_root + "/frame/link_btns/btns/crusing"
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)", reward_root,
                    raycast_top=True,
                ),
                make_button("crusing", entrance, x=617, y=130, raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [], images=[make_image(entrance + "/tip", "exclamation_mark")]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.battle_pass_reward_available())
        receipt = oracle.click_battle_pass_entrance()
        self.assertEqual(receipt.semantic_id, "reward/battle-pass/enter")
        self.assertEqual(backend.taps, [(617, 130)])

        backend.ui["images"][0]["sprite"] = "unrelated"
        self.assertFalse(oracle.battle_pass_reward_available())

    def test_battle_pass_claim_all_excludes_paid_button(self):
        root = "root/UICamera/Canvas/UIMain/WorldCruiseUI(Clone)"
        claim = (
            root
            + "/frame/award_container/WorldCruiseAwardPage(Clone)/frame/btns/btn_all"
        )
        backend = FakeBackend(
            [
                make_button("award", root + "/frame/toggles/award", raycast_top=None),
                make_button("btn_all", claim, x=1160, y=615, raycast_top=None),
                make_button(
                    "btn_pay",
                    root
                    + "/frame/award_container/WorldCruiseAwardPage(Clone)/frame/btns/btn_pay",
                    x=900,
                    y=615,
                    raycast_top=None,
                ),
                make_button("home", root + "/top/home", x=1223, y=38, raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [make_text("W O R L D  C R U I S E", root + "/top/title/Text/en")],
            images=[
                make_image(root, "mask"),
                make_image(root + "/frame/toggles/award/selected", "toggle_bg"),
                make_image(claim + "/Image", "tip"),
                make_image(
                    root
                    + "/frame/award_container/WorldCruiseAwardPage(Clone)/frame/btns/btn_pay/Image",
                    "lock",
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.battle_pass_page_visible())
        self.assertTrue(oracle.battle_pass_claim_all_available())
        receipt = oracle.click_battle_pass_claim_all()
        self.assertEqual(receipt.semantic_id, "battle-pass/claim-all")
        self.assertEqual(backend.taps, [(1160, 615)])
        self.assertNotIn((900, 615), backend.taps)

        backend.ui["images"][2]["sprite"] = "lock"
        self.assertFalse(oracle.battle_pass_claim_all_available())

    def test_battle_pass_probe_skips_ui_coherence_off_page(self):
        backend = FakeBackend([])
        backend.ui = make_ui([], generation=30)
        oracle = make_oracle(backend)

        self.assertFalse(oracle.battle_pass_page_visible())
        self.assertNotIn("GET /v1/ui\n", backend.requests)

        root = "root/UICamera/Canvas/UIMain/WorldCruiseUI(Clone)"
        backend.buttons = make_buttons(
            [make_button("award", root + "/frame/toggles/award", raycast_top=None)],
            generation=10,
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not coherent"):
            make_oracle(backend).battle_pass_page_visible()

    def test_data_key_limit_prompt_cancel_preserves_full_counter(self):
        archive = "root/UICamera/Canvas/UIOrigin/LevelRemasterView(Clone)"
        popup = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window"
        backend = FakeBackend(
            [
                make_button("bg", archive + "/bg", raycast_top=None),
                make_button(
                    "custom_button_1(Clone)",
                    popup + "/button_container/custom_button_1(Clone)",
                    x=790,
                    y=515,
                ),
                make_button(
                    "custom_button_2(Clone)",
                    popup + "/button_container/custom_button_2(Clone)",
                    x=490,
                    y=515,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("300/300", archive + "/nums/text"),
                make_text(
                    "确 定",
                    popup + "/button_container/custom_button_1(Clone)/pic",
                ),
                make_text(
                    "取 消",
                    popup + "/button_container/custom_button_2(Clone)/pic",
                ),
                make_text(
                    "所持<color=#ffde38>档案密钥</color>数量达到上限，"
                    "完成任务后只能获得<color=#ff5c5c>0</color>份"
                    "<color=#ffde38>档案密钥</color>，是否确认领取？",
                    popup + "/msg_panel/content",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.data_key_limit_prompt_visible())
        receipt = oracle.click_data_key_limit_choice(confirm=False)

        self.assertEqual(receipt.semantic_id, "archive/key-limit/cancel")
        self.assertEqual(backend.taps, [(490, 515)])
