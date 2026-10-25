"""Boundary regression cases for the oracle."""

import copy
import unittest
from alas_headless.semantic_oracle import (
    AdbObserverBridge,
    Bounds,
    ObserverTransportError,
    OracleFingerprint,
    SemanticGateClosed,
    SemanticOracle,
    SemanticTextTarget,
    SemanticToggleTarget,
    request_observer_state,
)
from tests.semantic_support.observer_fixtures import (
    COMPONENT,
    DRIVER_REVISION,
    FakeBackend,
    PACKAGE,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_snapshot,
    make_text,
    make_toggle,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport
from unittest import mock


class ObserverProtocolTests(unittest.TestCase):
    def test_exact_unavailable_status_is_not_reported_as_malformed(self):
        with self.assertRaisesRegex(
            ObserverTransportError, "observer is unavailable"
        ):
            request_observer_state(
                lambda _request: {
                    "protocol_schema": "alas-headless.observer/v1",
                    "status": "unavailable",
                }
            )


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_truncated_button_identity_fails_closed_before_matching(self):
        raw = make_button("battle", "root/frame/right/1/battle")
        raw["flags"] = 0x200
        backend = FakeBackend([raw])

        with self.assertRaisesRegex(SemanticGateClosed, "identity is truncated"):
            make_oracle(backend).read_state()

        self.assertEqual(backend.taps, [])

    def test_event_list_back_delegation_does_not_bypass_raycast_blocker(self):
        root = (
            "root/UICamera/Canvas/UIMain/ActivityMainUI(Clone)/"
            "adapt/blur_panel/adapt/top/back_btn"
        )
        backend = FakeBackend(
            [make_button("back_btn", root, raycast_top=False)]
        )

        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            make_oracle(backend).click("event-list/page/back")

        self.assertEqual(backend.taps, [])

    def test_war_archives_page_counter_and_uncollected_state_are_exact(self):
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
        backend = FakeBackend(
            [
                make_button(
                    "state_before", root + "/getBtn/state_before", raycast_top=None
                )
            ]
        )
        backend.ui = make_ui(
            [make_text("300/300", root + "/nums/text")],
            toggles=[
                make_toggle(root + "/toggles/EX", checked=True, raycast_top=None),
                make_toggle(root + "/toggles/SP", checked=False, raycast_top=None),
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.war_archives_page_visible())
        self.assertEqual(oracle.war_archives_data_key_text(), "300/300")
        self.assertFalse(oracle.war_archives_data_key_collected())

        receipt = oracle.click_war_archives_data_key_collect()
        self.assertEqual(receipt.semantic_id, "archive/key/collect")
        self.assertEqual(receipt.path, root + "/getBtn/state_before")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.taps.clear()
        backend.buttons = make_buttons(
            [make_button("state_after", root + "/getBtn/state_after", raycast_top=None)]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "already collected"):
            oracle.click_war_archives_data_key_collect()
        self.assertEqual(backend.taps, [])

        backend.buttons = make_buttons([])
        backend.ui = make_ui(
            [make_text("300/300", root + "/nums/text")],
            toggles=[
                make_toggle(root + "/toggles/EX", checked=True, raycast_top=None),
                make_toggle(root + "/toggles/SP", checked=False, raycast_top=None),
            ],
            images=[
                make_image(
                    root + "/getBtn/state_after", sprite="remaster_key_got"
                )
            ],
        )
        self.assertTrue(oracle.war_archives_data_key_collected())
        with self.assertRaisesRegex(SemanticGateClosed, "already collected"):
            oracle.click_war_archives_data_key_collect()

    def test_war_archives_page_rejects_inconsistent_toggle_selection(self):
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
        backend = FakeBackend([])
        backend.ui = make_ui(
            [make_text("300/300", root + "/nums/text")],
            toggles=[
                make_toggle(root + "/toggles/EX", checked=True, raycast_top=None),
                make_toggle(root + "/toggles/SP", checked=True, raycast_top=None),
            ],
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).war_archives_page_visible()

    def test_war_archives_offscreen_card_swipe_is_exact_and_bounded(self):
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
        card = root + "/list/content/item(Clone)/bg/icon"
        card_bounds = {
            "left": 729.0,
            "top": 900.0,
            "right": 1184.0,
            "bottom": 1070.0,
        }
        backend = FakeBackend(
            [
                make_button(
                    "icon",
                    card,
                    x=956.0,
                    y=985.0,
                    bounds=card_bounds,
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [make_text("300/300", root + "/nums/text")],
            toggles=[
                make_toggle(root + "/toggles/EX", checked=True, raycast_top=None),
                make_toggle(root + "/toggles/SP", checked=False, raycast_top=None),
            ],
            images=[
                make_image(card, "temp_zhuiluo", card_bounds),
                dict(make_image(root + "/list/scroll_bar", "white_dot",
                               {"left": 1255, "top": 126, "right": 1258, "bottom": 693}),
                     raycast_target=True),
                make_image(
                    root + "/list/scroll_bar/Handle/Image",
                    "scroll_bar",
                    {"left": 1248, "top": 126, "right": 1264, "bottom": 215},
                ),
            ],
        )
        oracle = make_oracle(backend)

        receipt = oracle.swipe_war_archives_campaign_toward(
            "war_archives_20181026_en"
        )
        self.assertEqual(
            receipt.semantic_id,
            "archive/campaign/search/war_archives_20181026_en",
        )
        self.assertEqual(backend.swipes, [(1256, 170, 1256, 214, 350)])
        self.assertEqual(backend.taps, [])

    def test_war_archives_category_click_requires_exact_unselected_toggle(self):
        root = "OverlayCamera/Overlay/UIMain/LevelRemasterView(Clone)"
        backend = FakeBackend([])
        backend.ui = make_ui(
            [make_text("300/300", root + "/nums/text")],
            toggles=[
                make_toggle(
                    root + "/toggles/EX",
                    checked=True,
                    raycast_top=None,
                    x=949,
                    y=56,
                    bounds={"left": 897, "top": 36, "right": 1001, "bottom": 76},
                ),
                make_toggle(
                    root + "/toggles/SP",
                    checked=False,
                    raycast_top=None,
                    x=1053,
                    y=56,
                    bounds={"left": 1001, "top": 36, "right": 1105, "bottom": 76},
                ),
            ],
        )
        oracle = make_oracle(backend)

        receipt = oracle.click_war_archives_category("sp")
        self.assertEqual(receipt.semantic_id, "archive/category/sp")
        self.assertEqual(backend.taps, [(1053, 56)])

    def test_war_archives_entry_prompt_requires_exact_cost_and_key_balance(self):
        msgbox = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window"
        campaign = "UICamera/Canvas/UIMain/LevelMainScene(Clone)"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_2(Clone)",
                    msgbox + "/button_container/custom_button_2(Clone)",
                    x=480,
                    y=520,
                ),
                make_button(
                    "custom_button_1(Clone)",
                    msgbox + "/button_container/custom_button_1(Clone)",
                    x=800,
                    y=520,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "进入所选关卡需要消耗档案秘钥x5，是否进入？",
                    msgbox + "/msg_panel/content",
                ),
                make_text(
                    "取消",
                    msgbox + "/button_container/custom_button_2(Clone)/pic",
                ),
                make_text(
                    "确定",
                    msgbox + "/button_container/custom_button_1(Clone)/pic",
                ),
                make_text(
                    "295 / 300",
                    campaign + "/main/right_chapter/event_btns/tickets/Text",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.war_archives_entry_confirmation_cost(), 5)
        receipt = oracle.confirm_war_archives_entry()
        self.assertEqual(receipt.semantic_id, "archive/entry/confirm")
        self.assertEqual(backend.taps, [(800, 520)])

        backend.ui["texts"][0]["text"] = (
            "进入所选关卡需要消耗档案秘钥x6，是否进入？"
        )
        with self.assertRaisesRegex(
            SemanticGateClosed, "entry cost changed"
        ):
            oracle.war_archives_entry_confirmation_cost()
        self.assertEqual(backend.taps, [(800, 520)])
        backend.ui["texts"] = []
        backend.ui["text_count"] = 0
        self.assertIsNone(oracle.war_archives_entry_confirmation_cost())
        with self.assertRaises(SemanticGateClosed):
            oracle.confirm_war_archives_entry()
        self.assertEqual(backend.taps, [(800, 520)])

    def test_foreground_parser_accepts_resumed_markers_only(self):
        for output in (
            "topResumedActivity=ActivityRecord{abc u0 " + COMPONENT + " t42}",
            "mResumedActivity: ActivityRecord{abc u0 " + COMPONENT + " t42}",
        ):
            with self.subTest(output=output):
                match = AdbObserverBridge._FOREGROUND_PATTERN.search(output)
                self.assertIsNotNone(match)
                self.assertEqual(match.group(1), COMPONENT)
        self.assertIsNone(
            AdbObserverBridge._FOREGROUND_PATTERN.search(
                "mFocusedActivity=ActivityRecord{abc u0 " + COMPONENT + " t42}"
            )
        )

    def test_foreground_query_has_a_dedicated_busy_emulator_timeout(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge._run = mock.Mock(
            return_value=(
                "topResumedActivity=ActivityRecord{abc u0 "
                + COMPONENT
                + " t42}"
            )
        )

        self.assertEqual(bridge.foreground_component(), COMPONENT)
        bridge._run.assert_called_once_with(
            ("shell", "dumpsys", "activity", "activities"),
            timeout_seconds=30.0,
        )

    def test_cold_restart_requires_a_new_numeric_game_pid(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge.pid = 1234
        calls = []
        replies = iter(("", "Status: ok", "5678"))

        def run(arguments, timeout_seconds=None):
            calls.append((tuple(arguments), timeout_seconds))
            return next(replies)

        bridge._run = run
        bridge.restart_game(COMPONENT)

        self.assertEqual(bridge.pid, 5678)
        self.assertEqual(
            calls,
            [
                (("shell", "am", "force-stop", PACKAGE), 30.0),
                (
                    (
                        "shell",
                        "am",
                        "start",
                        "-W",
                        "--es",
                        "unity",
                        "\\-force-gfx-st",
                        "-n",
                        COMPONENT,
                    ),
                    60.0,
                ),
                (("shell", "pidof", PACKAGE), 30.0),
            ],
        )

    def test_cold_restart_rejects_an_unchanged_pid(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge.pid = 1234
        replies = iter(("", "Status: ok", "1234"))
        bridge._run = lambda arguments, timeout_seconds=None: next(replies)

        with self.assertRaisesRegex(
            ObserverTransportError, "PID did not change"
        ):
            bridge.restart_game(COMPONENT)

    def test_cold_restart_accepts_force_stop_timeout_only_when_pid_is_absent(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge.pid = 1234
        calls = []

        def run(arguments, timeout_seconds=None):
            calls.append((tuple(arguments), timeout_seconds))
            if len(calls) == 1:
                raise ObserverTransportError("scripted host timeout")
            if len(calls) == 2:
                return ""
            if len(calls) == 3:
                return "Status: ok"
            return "5678"

        bridge._run = run
        bridge.restart_game(COMPONENT)

        self.assertEqual(bridge.pid, 5678)
        self.assertEqual(
            calls[1],
            (("shell", "pidof", PACKAGE), 30.0),
        )

    def test_cold_restart_waits_for_timed_out_force_stop_pid_to_disappear(self):
        bridge = AdbObserverBridge("device-1", PACKAGE)
        bridge.pid = 1234
        replies = iter(("1234", "1234", "", "Status: ok", "5678"))

        def run(arguments, timeout_seconds=None):
            if tuple(arguments) == ("shell", "am", "force-stop", PACKAGE):
                raise ObserverTransportError("scripted host timeout")
            return next(replies)

        bridge._run = run
        with mock.patch("alas_headless.semantic_oracle.time.sleep") as sleep:
            bridge.restart_game(COMPONENT)

        self.assertEqual(bridge.pid, 5678)
        self.assertEqual(sleep.call_count, 2)

    def test_atomic_state_rejects_different_generations(self):
        backend = FakeBackend([])

        def mismatched_state(request_line):
            self.assertEqual(request_line, "GET /v1/state\n")
            return {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": make_snapshot(generation=10),
                "buttons": make_buttons([], generation=11),
            }

        oracle = SemanticOracle(
            mismatched_state,
            backend.foreground_component,
            backend.tap,
            OracleFingerprint(
                package=PACKAGE,
                component=COMPONENT,
                driver_revision=DRIVER_REVISION,
                expected_pid=1234,
            ),
        )
        with self.assertRaisesRegex(SemanticGateClosed, "generation-atomic"):
            oracle.read_state()

    def test_exact_text_marker_and_indexed_list_groups(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "空空如也",
                    "root/page/empty",
                    {"left": 10, "top": 10, "right": 90, "bottom": 30},
                ),
                make_text(
                    "委托甲",
                    "root/list/1/name",
                    {"left": 20, "top": 120, "right": 100, "bottom": 140},
                ),
                make_text(
                    "01:30:00",
                    "root/list/1/time",
                    {"left": 120, "top": 120, "right": 200, "bottom": 140},
                ),
                make_text(
                    "委托零",
                    "root/list/0/name",
                    {"left": 20, "top": 60, "right": 100, "bottom": 80},
                ),
            ]
        )
        oracle = SemanticOracle(
            backend.request,
            backend.foreground_component,
            backend.tap,
            OracleFingerprint(
                package=PACKAGE,
                component=COMPONENT,
                driver_revision=DRIVER_REVISION,
                expected_pid=1234,
            ),
            text_targets=(
                SemanticTextTarget("page/empty", "root/page/empty", ("空空如也",)),
            ),
            sleep=lambda _: None,
        )

        self.assertEqual(oracle.text_state("page/empty").text, "空空如也")
        groups = oracle.indexed_text_groups("root/list")
        self.assertEqual([group.index for group in groups], [0, 1])
        self.assertEqual(
            [item.text for item in groups[1].texts], ["委托甲", "01:30:00"]
        )

    def test_typed_countdown_parser_is_strict(self):
        self.assertEqual(SemanticOracle.parse_countdown_seconds("09:42"), 582)
        self.assertEqual(SemanticOracle.parse_countdown_seconds("12:34:56"), 45296)
        for value in ("9:42", "01:60", "完成", "1d 02:03:04"):
            with self.subTest(value=value):
                with self.assertRaises(SemanticGateClosed):
                    SemanticOracle.parse_countdown_seconds(value)

    def test_typed_toggle_state_and_click_require_top_raycast(self):
        path = "root/options/merit"
        backend = FakeBackend([])
        backend.ui = make_ui([], toggles=[make_toggle(path, checked=True)])
        oracle = SemanticOracle(
            backend.request,
            backend.foreground_component,
            backend.tap,
            OracleFingerprint(
                package=PACKAGE,
                component=COMPONENT,
                driver_revision=DRIVER_REVISION,
                expected_pid=1234,
            ),
            toggle_targets=(SemanticToggleTarget("mail/filter/merit", "merit", path),),
            sleep=lambda _: None,
        )

        self.assertTrue(oracle.toggle_selected("mail/filter/merit"))
        receipt = oracle.click_toggle("mail/filter/merit")
        self.assertEqual(receipt.path, path)
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui = make_ui(
            [], toggles=[make_toggle(path, checked=True, raycast_top=False)]
        )
        with self.assertRaises(SemanticGateClosed):
            oracle.click_toggle("mail/filter/merit")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_main_badges_use_exact_typed_markers(self):
        backend = FakeBackend(
            [
                make_button(
                    "mail", "root/NewMainMellowTheme(Clone)/frame/top/btns/mail"
                ),
                make_button(
                    "task", "root/NewMainMellowTheme(Clone)/frame/bottom/frame/task"
                ),
                make_button(
                    "live", "root/NewMainMellowTheme(Clone)/frame/bottom/frame/live"
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "3",
                    "root/NewMainMellowTheme(Clone)/frame/top/btns/mail/Text",
                )
            ]
        )
        backend.ui["images"].append(
            make_image(
                "root/NewMainMellowTheme(Clone)/frame/bottom/frame/live/tip",
                "reddot",
            )
        )
        backend.ui["image_count"] += 1
        oracle = make_oracle(backend)

        self.assertEqual(oracle.main_mail_unread_count(), 3)
        self.assertFalse(oracle.main_red_dot("main/task"))
        self.assertTrue(oracle.main_red_dot("main/live"))

    def test_new_ship_page_visible_is_non_actionable_page_ownership_only(self):
        root = "root/UICamera/Canvas/UIOrigin/NewShipUI(Clone)/shake_panel/"
        backend = FakeBackend(
            [make_button("property_btn", root + "property_btn", x=1096, y=620)]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.new_ship_reward_page_visible())
        self.assertFalse(oracle.new_ship_reward_visible())
        self.assertFalse(oracle.enabled("reward/new-ship/continue"))

        backend.buttons = make_buttons([])
        self.assertFalse(oracle.new_ship_reward_page_visible())

    def test_network_reconnect_confirm_requires_exact_reviewed_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_2(Clone)",
                    popup + "button_container/custom_button_2(Clone)",
                ),
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                ),
                make_button(
                    "back_btn",
                    "root/UICamera/Canvas/UIMain/EventUI(Clone)/blur_panel/"
                    "adapt/top/back_btn",
                    raycast_top=False,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "服务器连接失败，是否重新连接？\n[NetworkDown]",
                    popup + "msg_panel/content",
                ),
                make_text(
                    "取 消",
                    popup + "button_container/custom_button_2(Clone)/pic",
                ),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("overlay/network-reconnect/cancel"))
        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))
        receipt = oracle.click("overlay/network-reconnect/confirm")
        self.assertEqual(receipt.semantic_id, "overlay/network-reconnect/confirm")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["texts"][0]["text"] = (
            "服务器连接失败，是否重新连接？\n[HostNotFound]"
        )
        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))

        backend.ui["texts"][0]["text"] = (
            "服务器连接失败，是否重新连接？\n[ConnectionReset]"
        )
        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))

        backend.ui["texts"][0]["text"] = (
            "服务器连接失败，是否重新连接？\n[UnknownNetworkError]"
        )
        self.assertFalse(oracle.enabled("overlay/network-reconnect/confirm"))

        backend.ui["texts"][0]["text"] = "是否购买资源？"
        self.assertFalse(oracle.enabled("overlay/network-reconnect/confirm"))

    def test_msgbox_identity_uses_stable_button_sandwich_not_fixed_delta(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        buttons = [
            make_button(
                "custom_button_2(Clone)",
                popup + "button_container/custom_button_2(Clone)",
            ),
            make_button(
                "custom_button_1(Clone)",
                popup + "button_container/custom_button_1(Clone)",
            ),
        ]
        backend = FakeBackend(buttons)
        backend.snapshot_sequence = [
            make_snapshot(generation=generation) for generation in (10, 31, 33)
        ]
        backend.buttons_sequence = [
            make_buttons(buttons, generation=generation) for generation in (10, 31, 33)
        ]
        texts = [
            make_text(
                "服务器连接失败，是否重新连接？\n[NetworkDown]",
                popup + "msg_panel/content",
            ),
            make_text("取 消", popup + "button_container/custom_button_2(Clone)/pic"),
            make_text("确 定", popup + "button_container/custom_button_1(Clone)/pic"),
        ]
        backend.ui_sequence = [
            make_ui(texts, generation=generation) for generation in (30, 32)
        ]
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("overlay/network-reconnect/confirm"))

    def test_msgbox_identity_retries_one_reversed_opening_snapshot(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        buttons = [
            make_button(
                "custom_button_2(Clone)",
                popup + "button_container/custom_button_2(Clone)",
            ),
            make_button(
                "custom_button_1(Clone)",
                popup + "button_container/custom_button_1(Clone)",
            ),
        ]
        texts = [
            make_text(
                "服务器连接失败，是否重新连接？\n[NetworkDown]",
                popup + "msg_panel/content",
            ),
            make_text("取 消", popup + "button_container/custom_button_2(Clone)/pic"),
            make_text("确 定", popup + "button_container/custom_button_1(Clone)/pic"),
        ]
        backend = FakeBackend(buttons)
        backend.snapshot_sequence = [
            make_snapshot(generation=generation) for generation in (10, 31, 33)
        ]
        backend.buttons_sequence = [
            make_buttons(buttons, generation=generation) for generation in (10, 31, 33)
        ]
        backend.ui_sequence = [
            make_ui(texts, generation=generation) for generation in (32, 32)
        ]

        oracle = make_oracle(backend)
        before = oracle.read_state()

        self.assertTrue(oracle._network_reconnect_prompt_matches(before))

    def test_repair_completion_requests_cold_restart_without_button_tap(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "修复完毕，即将重启游戏",
                    "root/Overlay/UIMain/UpdatePanel/progressInfo",
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_restart_required())
        self.assertFalse(oracle.login_update_restart_required())
        self.assertEqual(backend.taps, [])

    def test_outdated_client_msgbox_is_an_exact_restart_prompt(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend(
            [
                make_button(
                    "custom_button_1(Clone)",
                    popup + "button_container/custom_button_1(Clone)",
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "指挥官，当前客户端的游戏版本不是最新的，"
                    "推荐您重新打开游戏进行更新",
                    popup + "msg_panel/content",
                ),
                make_text(
                    "确 定",
                    popup + "button_container/custom_button_1(Clone)/pic",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.login_update_restart_prompt_available())
        receipt = oracle.click_login_update_restart_prompt()
        self.assertEqual(receipt.semantic_id, "login/update/restart-msgbox")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_shared_combat_pause_requires_one_exact_actionable_control(self):
        backend = FakeBackend([
            make_button(
                "PauseBtn",
                "UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn",
                raycast_top=None,
            )
        ])
        oracle = make_oracle(backend)

        self.assertTrue(oracle.combat_pause_visible())
        receipt = oracle.click_combat_pause()

        self.assertEqual(receipt.semantic_id, "combat/pause")
        self.assertEqual(len(backend.taps), 1)

    def test_dock_full_prompt_cannot_alias_network_reconnect_input(self):
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        button_path = popup + "button_container/custom_button_1(Clone)"
        backend = FakeBackend(
            [
                make_button("custom_button_1(Clone)", button_path, x, 515)
                for x in (440, 640, 840)
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "船坞已满，请前往整理或扩展",
                    popup + "msg_panel/content",
                ),
                *[
                    make_text(label, button_path + "/pic")
                    for label in ("整 理", "拓 展", "强 化")
                ],
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.dock_full_prompt_active())
        self.assertFalse(oracle.enabled("overlay/network-reconnect/confirm"))
        with self.assertRaisesRegex(SemanticGateClosed, "dock-full prompt"):
            oracle.click("overlay/network-reconnect/confirm")
        self.assertEqual(backend.taps, [])

    def test_absent_network_reconnect_does_not_require_unrelated_toggle_snapshot(self):
        backend = FakeBackend([])
        backend.ui["toggle_truncated"] = True
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("overlay/network-reconnect/cancel"))
        self.assertFalse(oracle.enabled("overlay/network-reconnect/confirm"))

    def test_happy_path_exposes_bounds_and_clicks_center(self):
        backend = FakeBackend(
            [
                make_button(
                    "settings",
                    "UICamera/Canvas/UIOrigin/Main/frame/top/btns/settings",
                    1221.0,
                    36.0,
                    {"left": 1202.0, "top": 17.0, "right": 1240.0, "bottom": 55.0},
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.exists("main/settings"))
        self.assertTrue(oracle.enabled("main/settings"))
        self.assertEqual(oracle.bounds("main/settings").left, 1202.0)
        receipt = oracle.click("main/settings")

        self.assertEqual(receipt.path.split("/")[-1], "settings")
        self.assertEqual(backend.taps, [(1221, 36)])

    def test_enabled_retries_a_truncated_button_transition_frame(self):
        button = make_button(
            "settings",
            "UICamera/Canvas/UIOrigin/Main/frame/top/btns/settings",
            1221,
            36,
        )
        backend = FakeBackend([button])
        incomplete = make_buttons([button], generation=10)
        incomplete["truncated"] = True
        backend.buttons_sequence = [
            incomplete,
            make_buttons([button], generation=11),
        ]

        self.assertTrue(make_oracle(backend).enabled("main/settings"))

    def test_unknown_mapping_fails_closed_without_input(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/not-mapped")
        self.assertEqual(backend.taps, [])

    def test_wrong_foreground_fails_closed_without_input(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )
        backend.foreground = "com.android.launcher3/.QuickstepLauncher"
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_stale_snapshot_fails_closed(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )
        backend.buttons["age_ms"] = 3000
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.enabled("main/settings")

    def test_duplicate_target_is_ambiguous(self):
        button = make_button("settings", "root/frame/top/btns/settings", 1221, 36)
        backend = FakeBackend([button, copy.deepcopy(button)])
        oracle = make_oracle(backend)

        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_missing_bounds_fails_closed(self):
        button = make_button("settings", "root/frame/top/btns/settings", 1221, 36)
        button["adb_bounds"] = None
        backend = FakeBackend([button])
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_non_top_raycast_target_fails_closed(self):
        backend = FakeBackend(
            [
                make_button(
                    "settings",
                    "root/frame/top/btns/settings",
                    1221,
                    36,
                    raycast_top=False,
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        self.assertEqual(backend.taps, [])

    def test_unrelated_zero_area_button_does_not_poison_valid_target(self):
        zero_area = make_button("layout", "root/layout")
        zero_area["adb_bounds"] = {
            "left": 100,
            "top": 100,
            "right": 100,
            "bottom": 100,
        }
        backend = FakeBackend(
            [
                zero_area,
                make_button("settings", "root/frame/top/btns/settings", 1221, 36),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("main/settings"))
        self.assertEqual(backend.taps, [])

    def test_bulletin_blocks_main_but_allows_mapped_close(self):
        backend = FakeBackend(
            [
                make_button("settings", "root/frame/top/btns/settings", 1221, 36),
                make_button(
                    "close_btn",
                    "Overlay/UIMain/NewBulletinBoardUI(Clone)/bg/close_btn",
                    1204,
                    83,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/settings"))
        self.assertTrue(oracle.enabled("overlay/bulletin/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/settings")
        receipt = oracle.click("overlay/bulletin/close")

        self.assertEqual(receipt.semantic_id, "overlay/bulletin/close")
        self.assertEqual(backend.taps, [(1204, 83)])

    def test_task_page_blocks_main_but_allows_exact_back(self):
        backend = FakeBackend(
            [
                make_button("task", "root/frame/bottom/frame/task", 875, 684),
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/task"))
        self.assertTrue(oracle.enabled("task/page/back"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/task")
        receipt = oracle.click("task/page/back")

        self.assertEqual(receipt.semantic_id, "task/page/back")
        self.assertEqual(backend.taps, [(58, 53)])

    def test_award_info_blocks_task_page_but_allows_exact_close(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    "root/TaskScene(Clone)/blur_panel/adapt/top/back_btn",
                    58,
                    53,
                ),
                make_button(
                    "close",
                    "root/AwardInfoUI(Clone)/items/close",
                    640,
                    650,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("task/page/back"))
        self.assertTrue(oracle.enabled("reward/award-info/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("task/page/back")
        receipt = oracle.click("reward/award-info/close")

        self.assertEqual(receipt.semantic_id, "reward/award-info/close")
        self.assertEqual(backend.taps, [(640, 650)])

    def test_generation_rollback_fails_closed(self):
        backend = FakeBackend([])
        oracle = make_oracle(backend)
        oracle.read_state()
        backend.snapshot["generation"] = 9
        backend.buttons["generation"] = 9

        with self.assertRaises(SemanticGateClosed):
            oracle.read_state()

    def test_click_and_wait_requires_a_new_generation(self):
        backend = FakeBackend(
            [make_button("settings", "root/frame/top/btns/settings", 1221, 36)]
        )

        def transition():
            backend.snapshot["generation"] = 11
            backend.buttons = make_buttons(
                [
                    make_button(
                        "back_btn",
                        "root/NewSettingsUI(Clone)/blur_panel/adapt/top/back_btn",
                        73,
                        42,
                    )
                ],
                generation=11,
            )

        backend.on_tap = transition
        oracle = make_oracle(backend)

        target = oracle.click_and_wait("main/settings", "settings/back", 1.0)

        self.assertEqual(target.name, "back_btn")
        self.assertEqual(backend.taps, [(1221, 36)])

    def test_typed_text_is_selected_by_ocr_bounds(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text("01:23:45", "root/timer"),
                make_text(
                    "outside",
                    "root/outside",
                    {"left": 500.0, "top": 500.0, "right": 600.0, "bottom": 540.0},
                    kind="tmp-text",
                ),
            ]
        )
        oracle = make_oracle(backend)

        matches = oracle.texts_in_bounds(Bounds(90, 90, 200, 150))

        self.assertEqual([item.text for item in matches], ["01:23:45"])
        self.assertEqual(matches[0].kind, "ugui-text")

    def test_typed_text_snapshot_truncation_fails_closed(self):
        backend = FakeBackend([])
        backend.ui = make_ui([make_text("12")])
        backend.ui["text_truncated"] = True

        with self.assertRaises(SemanticGateClosed):
            _ = make_oracle(backend).read_ui_state().texts

    def test_typed_image_exposes_sprite_color_and_bounds(self):
        backend = FakeBackend([])
        backend.ui = make_ui([], images=[make_image("root/red_dot", "red_dot")])

        state = make_oracle(backend).read_ui_state()

        self.assertEqual(state.images[0].sprite, "red_dot")
        self.assertEqual(state.images[0].color, (1.0, 0.5, 0.25, 1.0))
        self.assertEqual(state.images[0].bounds, Bounds(200, 100, 240, 140))

    def test_absent_sprite_ignores_legacy_residue_without_closing_images(self):
        backend = FakeBackend([])
        valid = make_image("root/valid", "current")
        absent = make_image("root/absent", "")
        absent["flags"] &= ~0x8
        stale = make_image("root/stale", "legacy-residue")
        stale["flags"] &= ~0x8
        backend.ui = make_ui([], images=[valid, absent, stale])

        images = make_oracle(backend).read_ui_state().images

        self.assertEqual([image.sprite for image in images], ["current", "", ""])
        self.assertTrue(all(not image.truncated for image in images))

    def test_legacy_sprite_residue_cannot_select_an_image_target(self):
        backend = FakeBackend([])
        root = (
            "root/EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
            "tagRoot"
        )
        stale = make_image(root + "/daily_btn/selected/Image", "toggle_meiri_sel 1")
        stale["flags"] &= ~0x8
        valid = make_image(root + "/urgency_btn/selected/Image", "toggle_jinji_sel 1")
        backend.ui = make_ui([], images=[stale, valid])
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            oracle.image_selected("commission/nav/daily")
        self.assertTrue(oracle.image_selected("commission/nav/urgent"))

    def test_image_state_retries_a_truncated_transition_frame(self):
        backend = FakeBackend([])
        image = make_image(
            "root/EventUI(Clone)/blur_panel/adapt/left_length/frame/scroll_rect/"
            "tagRoot/daily_btn/selected/Image",
            "toggle_meiri_sel 1",
        )
        incomplete = make_ui([], images=[image], generation=10)
        incomplete["image_truncated"] = True
        backend.ui_sequence = [
            incomplete,
            make_ui([], images=[image], generation=11),
        ]

        self.assertTrue(make_oracle(backend).image_selected("commission/nav/daily"))

    def test_typed_text_record_truncation_is_scoped_to_the_record(self):
        backend = FakeBackend([])
        text = make_text("12")
        text["flags"] |= 0x10
        backend.ui = make_ui([text])

        state = make_oracle(backend).read_ui_state()

        self.assertTrue(state.texts[0].truncated)
