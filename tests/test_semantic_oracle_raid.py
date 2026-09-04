"""Raid regression cases for the oracle."""

import copy
import unittest
from alas_headless.semantic_oracle import (
    Point,
    RaidMultipleSortieState,
    SemanticGateClosed,
)
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_current_raid_backend,
    make_image,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_raid_remain_reads_all_pinned_modes_from_typed_nodes(self):
        root = "UICamera/Canvas/UIMain/BossRushVerSardiniaSPUI(Clone)"
        buttons = [
            make_button(str(node), f"{root}/Battle/Nodes/{node}")
            for node in range(5001, 5006)
        ]
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [
                make_text("12/15", f"{root}/Battle/Nodes/5001/remain/Text"),
                make_text("7 / 15", f"{root}/Battle/Nodes/5002/remain/Text"),
                make_text("0/15", f"{root}/Battle/Nodes/5003/remain/Text"),
                make_text("3", f"{root}/Battle/Nodes/5004/times/Text"),
            ]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.raid_remain("raid_20260212", "easy"), 12)
        self.assertEqual(oracle.raid_remain("raid_20260212", "normal"), 7)
        self.assertEqual(oracle.raid_remain("raid_20260212", "hard"), 0)
        state = oracle.raid_remain_state("raid_20260212", "ex")
        self.assertEqual((state.remaining, state.capacity, state.node_id), (3, None, 5004))

    def test_raid_remain_rejects_unsafe_and_harmless_drift_separately(self):
        root = "UICamera/Canvas/UIMain/BossRushVerSardiniaSPUI(Clone)"
        buttons = [
            make_button(str(node), f"{root}/Battle/Nodes/{node}")
            for node in range(5001, 5006)
        ]
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [
                make_text("9/15", f"{root}/Battle/Nodes/5001/new_layout/value"),
                make_text("metadata", f"{root}/Battle/Nodes/5001/new_layout/label"),
            ]
        )
        oracle = make_oracle(backend)
        self.assertEqual(oracle.raid_remain("raid_20260212", "easy"), 9)

        backend.ui = make_ui(
            [
                make_text("9/15", f"{root}/Battle/Nodes/5001/remain/Text"),
                make_text("8/15", f"{root}/Battle/Nodes/5001/duplicate/Text"),
            ]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            make_oracle(backend).raid_remain("raid_20260212", "easy")

        with self.assertRaisesRegex(SemanticGateClosed, "event is unsupported"):
            make_oracle(backend).raid_remain("raid_future", "easy")

    def test_current_raid_reads_typed_counters_and_keeps_advanced_distinct(self):
        backend = make_current_raid_backend()
        root = "UICamera/Canvas/UIMain/ActivityBossAmatsukazeUI(Clone)"
        # Additive metadata and a future unrelated control do not alter any
        # reviewed stage identity.
        backend.buttons["buttons"].append(
            make_button("metadata", root + "/adapt/left/metadata")
        )
        backend.buttons["button_count"] += 1
        backend.ui["texts"].append(make_text("metadata", root + "/adapt/left/value"))
        backend.ui["text_count"] += 1
        oracle = make_oracle(backend)

        self.assertEqual(oracle.raid_remain("raid_20260827", "easy"), 15)
        self.assertEqual(oracle.raid_remain("raid_20260827", "normal"), 8)
        self.assertEqual(oracle.raid_remain("raid_20260827", "hard"), 0)
        self.assertEqual(oracle.event_points(), 1234)
        state = oracle.raid_remain_state("raid_20260827", "ex")
        self.assertEqual((state.remaining, state.capacity, state.node_id), (2, None, 4))

        ticket_image = next(
            image
            for image in backend.ui["images"]
            if image["path"] == root + "/adapt/top/ticket"
        )
        for sprite in ("star", "title", "future_ticket"):
            ticket_image["sprite"] = sprite
            self.assertEqual(oracle.raid_remain("raid_20260827", "ex"), 2)

        ticket_label = next(
            text
            for text in backend.ui["texts"]
            if text["path"] == root + "/adapt/top/ticket/Desc"
        )
        ticket_label["text"] = "未来挑战券"
        with self.assertRaisesRegex(SemanticGateClosed, "counter is absent"):
            oracle.raid_remain("raid_20260827", "ex")

        with self.assertRaisesRegex(SemanticGateClosed, "mode is unsupported"):
            oracle.click_raid_stage("raid_20260827", "advanced")
        self.assertEqual(backend.taps, [])

    def test_current_raid_stage_click_uses_exact_typed_slot(self):
        backend = make_current_raid_backend()
        receipt = make_oracle(backend).click_raid_stage("raid_20260827", "hard")

        self.assertEqual(receipt.semantic_id, "raid/stage/hard")
        self.assertTrue(receipt.path.endswith("/adapt/right/3"))
        self.assertEqual(backend.taps, [(1112, 411)])

    def test_current_raid_counter_waits_for_complete_typed_page(self):
        backend = make_current_raid_backend()
        transient = copy.deepcopy(backend.ui)
        ticket_path = (
            "UICamera/Canvas/UIMain/ActivityBossAmatsukazeUI(Clone)"
            "/adapt/top/ticket"
        )
        transient["images"] = [
            image for image in transient["images"] if image["path"] != ticket_path
        ]
        transient["image_count"] = len(transient["images"])
        backend.ui_sequence = [transient, copy.deepcopy(backend.ui)]

        state = make_oracle(backend).raid_remain_state("raid_20260827", "ex")

        self.assertEqual(state.remaining, 2)
        self.assertEqual(backend.taps, [])

    def test_current_raid_hidden_zero_requires_stable_healthy_page(self):
        backend = make_current_raid_backend()
        root = "UICamera/Canvas/UIMain/ActivityBossAmatsukazeUI(Clone)"
        zero_path = root + "/adapt/right/3/Text"
        backend.ui["texts"] = [
            item for item in backend.ui["texts"] if item["path"] != zero_path
        ]
        backend.ui["text_count"] = len(backend.ui["texts"])
        stable_first = dict(copy.deepcopy(backend.ui), generation=10)
        stable_second = dict(copy.deepcopy(backend.ui), generation=11)
        backend.ui_sequence = [stable_first, stable_second]

        state = make_oracle(backend).raid_remain_state("raid_20260827", "hard")

        self.assertEqual((state.remaining, state.capacity, state.node_id), (0, 15, 3))
        self.assertEqual(backend.taps, [])

        unstable = make_current_raid_backend()
        unstable.ui["texts"] = [
            item for item in unstable.ui["texts"] if item["path"] != zero_path
        ]
        unstable.ui["text_count"] = len(unstable.ui["texts"])
        with self.assertRaisesRegex(SemanticGateClosed, "not stable"):
            make_oracle(unstable).raid_remain_state("raid_20260827", "hard")

        malformed = make_current_raid_backend()
        malformed_text = next(
            item for item in malformed.ui["texts"] if item["path"] == zero_path
        )
        malformed_text["text"] = "CLEARED"
        with self.assertRaisesRegex(SemanticGateClosed, "malformed"):
            make_oracle(malformed).raid_remain_state("raid_20260827", "hard")

    def test_current_raid_home_uses_proven_bounds_center(self):
        backend = make_current_raid_backend()
        receipt = make_oracle(backend).click_raid_home("raid_20260827")

        self.assertEqual(receipt.semantic_id, "raid/page/home")
        self.assertEqual(receipt.point, Point(1241, 39.5))
        self.assertEqual(backend.taps, [(1241, 40)])

    def test_current_raid_does_not_click_through_fleet_overlay(self):
        backend = make_current_raid_backend()
        fleet_root = (
            "OverlayCamera/Overlay/UIMain/ActivityBossFleetSelectView(Clone)/panel"
        )
        backend.buttons["buttons"].append(
            make_button("start_button", fleet_root + "/start_button", raycast_top=None)
        )
        backend.buttons["button_count"] += 1

        oracle = make_oracle(backend)
        self.assertFalse(oracle.raid_page_visible("raid_20260827"))
        with self.assertRaisesRegex(SemanticGateClosed, "obscured"):
            oracle.click_raid_stage("raid_20260827", "normal")
        self.assertEqual(backend.taps, [])

    def test_current_raid_yields_exact_story_overlay_to_original_alas_handler(self):
        backend = make_current_raid_backend()
        story_root = "root/Overlay/UIOverlay/NewStoryUI(Clone)"
        backend.buttons["buttons"].extend(
            (
                make_button("NewStoryUI(Clone)", story_root),
                make_button(
                    "skip_button",
                    story_root + "/front/btns/btns/skip_button",
                    raycast_top=None,
                ),
            )
        )
        backend.buttons["button_count"] += 2

        oracle = make_oracle(backend)
        self.assertFalse(oracle.raid_page_visible("raid_20260827"))
        with self.assertRaisesRegex(SemanticGateClosed, "obscured by event story"):
            oracle.click_raid_home("raid_20260827")
        self.assertEqual(backend.taps, [])

    def test_current_raid_rejects_malformed_story_overlay_locally(self):
        backend = make_current_raid_backend()
        backend.buttons["buttons"].append(
            make_button(
                "NewStoryUI(Clone)",
                "root/Overlay/UIOverlay/NewStoryUI(Clone)",
            )
        )
        backend.buttons["button_count"] += 1

        with self.assertRaisesRegex(SemanticGateClosed, "story overlay is malformed"):
            make_oracle(backend).raid_page_visible("raid_20260827")
        self.assertEqual(backend.taps, [])

    def test_current_raid_fleet_back_uses_proven_bounds_center(self):
        root = "OverlayCamera/Overlay/UIMain/ActivityBossFleetSelectView(Clone)/panel"
        back_bounds = {"left": 1125, "top": 66, "right": 1197, "bottom": 118}
        start_bounds = {"left": 966, "top": 567, "right": 1198, "bottom": 660}
        recommend_bounds = {
            "left": 1019,
            "top": 165,
            "right": 1094,
            "bottom": 235,
        }
        backend = FakeBackend(
            [
                make_button(
                    "btnBack",
                    root + "/btnBack",
                    1197,
                    66,
                    back_bounds,
                    raycast_top=None,
                ),
                make_button(
                    "start_button",
                    root + "/start_button",
                    966,
                    660,
                    start_bounds,
                    raycast_top=None,
                ),
                make_button(
                    "btn_recom",
                    root + "/fleet/1/btn_recom",
                    1057,
                    200,
                    recommend_bounds,
                    raycast_top=None,
                ),
                *[
                    make_button(
                        "shiptpl(Clone)",
                        root + "/fleet/1/" + group + "/shiptpl(Clone)",
                        400 + index * 80,
                        200 if group == "main" else 300,
                        raycast_top=None,
                    )
                    for group in ("main", "vanguard")
                    for index in range(3)
                ],
            ]
        )
        backend.ui = make_ui(
            [make_text("FLEET SELECT", root + "/title/Image/text/text (1)")],
            images=[
                make_image(root + "/btnBack", "x_butten", back_bounds),
                make_image(root + "/start_button", "qianwang_button", start_bounds),
                make_image(
                    root + "/fleet/1/btn_recom",
                    "tuijian_butten",
                    recommend_bounds,
                ),
            ],
        )

        receipt = make_oracle(backend).click_raid_fleet_back("raid_20260827")

        self.assertEqual(receipt.point, Point(1161, 92))
        self.assertEqual(backend.taps, [(1161, 92)])
        backend.taps.clear()
        receipt = make_oracle(backend).click_raid_fleet_start("raid_20260827")
        self.assertEqual(receipt.point, Point(1082, 613.5))
        self.assertEqual(backend.taps, [(1082, 614)])
        backend.taps.clear()
        receipt = make_oracle(backend).click_raid_fleet_recommend("raid_20260827")
        self.assertEqual(receipt.point, Point(1056.5, 200))
        self.assertEqual(backend.taps, [(1056, 200)])
        self.assertTrue(make_oracle(backend).raid_fleet_ready("raid_20260827"))

        for button in backend.buttons["buttons"]:
            if button["name"] == "shiptpl(Clone)" and "/main/" in button["path"]:
                button["name"] = "emptytpl(Clone)"
                button["path"] = button["path"].replace(
                    "/shiptpl(Clone)", "/emptytpl(Clone)"
                )
        self.assertFalse(make_oracle(backend).raid_fleet_ready("raid_20260827"))

    def test_current_raid_rejects_swapped_ex_and_advanced_sprites(self):
        backend = make_current_raid_backend()
        root = "UICamera/Canvas/UIMain/ActivityBossAmatsukazeUI(Clone)"
        for image in backend.ui["images"]:
            if image["path"] == root + "/adapt/right/4":
                image["sprite"] = "btn_lv_sp"
            elif image["path"] == root + "/adapt/right/5":
                image["sprite"] = "btn_lv_ex"

        with self.assertRaisesRegex(SemanticGateClosed, "stage sprites"):
            make_oracle(backend).raid_remain("raid_20260827", "ex")
        self.assertEqual(backend.taps, [])

    def test_current_raid_advanced_entry_stays_distinct_from_ex(self):
        backend = make_current_raid_backend()
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "mode is unsupported"):
            oracle.click_raid_stage("raid_20260827", "advanced")
        self.assertEqual(backend.taps, [])

        receipt = oracle.click_raid_advanced_challenge("raid_20260827")
        self.assertEqual(receipt.semantic_id, "raid/advanced/entry")
        self.assertEqual(
            receipt.path,
            "UICamera/Canvas/UIMain/ActivityBossAmatsukazeUI(Clone)/adapt/right/5",
        )
        self.assertEqual(backend.taps, [(1146, 196)])

        backend.taps.clear()
        advanced_image = next(
            image
            for image in backend.ui["images"]
            if image["path"].endswith("/adapt/right/5")
        )
        advanced_image["sprite"] = "btn_lv_ex"
        with self.assertRaisesRegex(SemanticGateClosed, "stage sprites"):
            oracle.click_raid_advanced_challenge("raid_20260827")
        self.assertEqual(backend.taps, [])

    def test_current_raid_precombat_probe_skips_ui_coherence_off_page(self):
        backend = make_current_raid_backend()
        backend.ui["generation"] = 30
        oracle = make_oracle(backend)

        self.assertFalse(oracle.raid_precombat_visible("raid_20260827"))
        self.assertNotIn("GET /v1/ui\n", backend.requests)

        root = "OverlayCamera/Overlay/UIMain/ActivityBossPrecombatUI(Clone)"
        backend.buttons = make_buttons(
            [make_button("start", root + "/adapt/right/start", raycast_top=None)],
            generation=10,
        )
        with self.assertRaisesRegex(SemanticGateClosed, "snapshots are incoherent"):
            make_oracle(backend).raid_precombat_visible("raid_20260827")

    def test_current_raid_precombat_notice_and_sortie_are_distinct_inputs(self):
        root = "UICamera/Canvas/UIOrigin/ActivityBossPrecombatUI(Clone)"
        start = root + "/adapt/right/start"
        multiple = root + "/adapt/right/multiple"
        notice_root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window"
        notice = notice_root + "/button_container/custom_button_1(Clone)"
        start_bounds = {"left": 1051, "top": 596, "right": 1282, "bottom": 686}
        multiple_bounds = {
            "left": 1051,
            "top": 520,
            "right": 1282,
            "bottom": 580,
        }
        notice_bounds = {"left": 549, "top": 515, "right": 731, "bottom": 582}
        back = root + "/blur_panel/top/back_btn"
        back_bounds = {"left": 1, "top": -3, "right": 115, "bottom": 111}
        backend = FakeBackend(
            [
                make_button(
                    "start", start, 1167, 641, start_bounds, raycast_top=None
                ),
                make_button(
                    "multiple",
                    multiple,
                    1167,
                    550,
                    multiple_bounds,
                    raycast_top=None,
                ),
                *[
                    make_button(
                        "mouseChild",
                        root
                        + "/adapt/middle/HeroContainer/info/ship{0}_root/mouseChild".format(
                            index
                        ),
                        200 + index * 80,
                        300,
                        raycast_top=None,
                    )
                    for index in range(6)
                ],
                make_button(
                    "custom_button_1(Clone)",
                    notice,
                    640,
                    548,
                    notice_bounds,
                    raycast_top=True,
                ),
                make_button(
                    "back_btn", back, 58, 54, back_bounds, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("WEIGH ANCHOR", start + "/text_en"),
                make_text("MULTIPLE SORTIES", multiple + "/text_en"),
                make_text("出击", start + "/text"),
                make_text("消耗：", start + "/cost_container/title"),
                make_text("87", start + "/cost_container/popup/Text"),
                make_text("额外收益次数：", start + "/bonus/title"),
                make_text("15", start + "/bonus/Text"),
                make_text(
                    "MAIN",
                    root + "/adapt/middle/gear_score/main/line/Image/Text2",
                ),
                make_text(
                    "VANGUARD",
                    root + "/adapt/middle/gear_score/vanguard/line/Image/Text2",
                ),
                make_text("19476", root + "/adapt/middle/gear_score/main/Text"),
                make_text(
                    "16655", root + "/adapt/middle/gear_score/vanguard/Text"
                ),
                make_text("知道了", notice + "/pic"),
                make_text("信息", notice_root + "/top/bg/infomation/title"),
                make_text(
                    "INFORMATION", notice_root + "/top/bg/infomation/title_en"
                ),
                make_text(
                    "注意，自律战斗时可能出现以下情况",
                    notice_root + "/help_panel/list/help_tpl",
                ),
            ],
            images=[
                make_image(start, "btn_formation_sel", start_bounds),
                make_image(multiple, "btn_blue", multiple_bounds),
                make_image(
                    start + "/cost_container/popup/icon", "res_oil"
                ),
                make_image(notice, "btn_big_blue", notice_bounds),
                make_image(back, "icon_bg_front_1920", back_bounds),
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.raid_precombat_visible("raid_20260827"))
        self.assertTrue(
            oracle.raid_precombat_multiple_visible("raid_20260827")
        )
        self.assertTrue(oracle.raid_precombat_notice_visible("raid_20260827"))
        with self.assertRaisesRegex(SemanticGateClosed, "obscured by notice"):
            oracle.click_raid_precombat_start("raid_20260827")
        with self.assertRaisesRegex(SemanticGateClosed, "obscured by notice"):
            oracle.click_raid_precombat_multiple("raid_20260827")
        notice_receipt = oracle.click_raid_precombat_notice("raid_20260827")
        self.assertEqual(
            notice_receipt.semantic_id, "raid/precombat/notice/acknowledge"
        )
        self.assertEqual(backend.taps, [(640, 548)])

        backend.buttons["buttons"] = [
            button for button in backend.buttons["buttons"] if button["path"] != notice
        ]
        backend.buttons["button_count"] -= 1
        backend.ui["texts"] = [
            text
            for text in backend.ui["texts"]
            if not text["path"].startswith(notice_root)
        ]
        backend.ui["text_count"] = len(backend.ui["texts"])
        backend.ui["images"] = [
            image for image in backend.ui["images"] if image["path"] != notice
        ]
        backend.ui["image_count"] -= 1
        backend.taps.clear()

        self.assertFalse(oracle.raid_precombat_notice_visible("raid_20260827"))

        multiple_receipt = oracle.click_raid_precombat_multiple(
            "raid_20260827"
        )
        self.assertEqual(
            multiple_receipt.semantic_id, "raid/precombat/multiple"
        )
        self.assertEqual(backend.taps, [(1167, 550)])
        backend.taps.clear()

        loading_path = "root/UIOverlay/Loading(Clone)/panel"
        backend.buttons["buttons"].append(
            make_button("panel", loading_path, raycast_top=True)
        )
        backend.buttons["button_count"] += 1
        self.assertFalse(oracle.raid_precombat_visible("raid_20260827"))
        with self.assertRaisesRegex(SemanticGateClosed, "input is blocked"):
            oracle.click_raid_precombat_start("raid_20260827")
        self.assertEqual(backend.taps, [])
        backend.buttons["buttons"] = [
            button
            for button in backend.buttons["buttons"]
            if button["path"] != loading_path
        ]
        backend.buttons["button_count"] -= 1

        start_image = next(
            image for image in backend.ui["images"] if image["path"] == start
        )
        start_image["adb_bounds"] = {
            "left": 1080,
            "top": 596,
            "right": 1282,
            "bottom": 686,
        }
        self.assertFalse(oracle.raid_precombat_visible("raid_20260827"))
        with self.assertRaisesRegex(SemanticGateClosed, "does not cover start"):
            oracle.click_raid_precombat_start("raid_20260827")
        self.assertEqual(backend.taps, [])
        start_image["adb_bounds"] = start_bounds

        numeric_text = next(
            text
            for text in backend.ui["texts"]
            if text["path"] == start + "/cost_container/popup/Text"
        )
        backend.ui["texts"].remove(numeric_text)
        backend.ui["text_count"] -= 1
        self.assertFalse(oracle.raid_precombat_visible("raid_20260827"))
        with self.assertRaisesRegex(SemanticGateClosed, "identity is incomplete"):
            oracle.click_raid_precombat_start("raid_20260827")
        self.assertEqual(backend.taps, [])
        backend.ui["texts"].append(numeric_text)
        backend.ui["text_count"] += 1

        multiple_image = next(
            image for image in backend.ui["images"] if image["path"] == multiple
        )
        multiple_image["sprite"] = "btn_red"
        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            oracle.raid_precombat_multiple_visible("raid_20260827")
        with self.assertRaisesRegex(SemanticGateClosed, "absent or ambiguous"):
            oracle.click_raid_precombat_multiple("raid_20260827")
        self.assertEqual(backend.taps, [])
        multiple_image["sprite"] = "btn_blue"

        start_receipt = oracle.click_raid_precombat_start("raid_20260827")
        self.assertEqual(start_receipt.semantic_id, "raid/precombat/start")
        self.assertEqual(backend.taps, [(1167, 641)])
        backend.taps.clear()
        back_receipt = oracle.click_raid_precombat_back("raid_20260827")
        self.assertEqual(back_receipt.semantic_id, "raid/precombat/back")
        self.assertEqual(backend.taps, [(58, 54)])

        backend.taps.clear()
        backend.ui["texts"] = [
            text
            for text in backend.ui["texts"]
            if text["path"] not in {start + "/bonus/title", start + "/bonus/Text"}
        ]
        backend.ui["texts"].extend(
            (
                make_text("使用", start + "/ticket/title"),
                make_text("1/1", start + "/ticket/Text"),
            )
        )
        backend.ui["text_count"] = len(backend.ui["texts"])
        backend.ui["images"].extend(
            (
                make_image(start + "/ticket/icon", "nvpu_ticket"),
                make_image(start + "/ticket/checkbox", "check_frame_bg"),
                make_image(start + "/ticket/bg", "frame_bg"),
            )
        )
        backend.ui["image_count"] = len(backend.ui["images"])

        self.assertTrue(oracle.raid_precombat_visible("raid_20260827"))
        ex_receipt = oracle.click_raid_precombat_start("raid_20260827")
        self.assertEqual(ex_receipt.semantic_id, "raid/precombat/start")
        self.assertEqual(backend.taps, [(1167, 641)])

        backend.taps.clear()
        backend.ui["images"] = [
            image
            for image in backend.ui["images"]
            if image["path"] != start + "/ticket/icon"
        ]
        backend.ui["image_count"] = len(backend.ui["images"])
        self.assertFalse(oracle.raid_precombat_visible("raid_20260827"))
        with self.assertRaisesRegex(SemanticGateClosed, "identity is incomplete"):
            oracle.click_raid_precombat_start("raid_20260827")
        self.assertEqual(backend.taps, [])

    def test_current_raid_rejects_duplicate_counter(self):
        backend = make_current_raid_backend()
        root = "UICamera/Canvas/UIMain/ActivityBossAmatsukazeUI(Clone)"
        backend.ui["texts"].append(
            make_text("7/15", root + "/adapt/right/2/Text")
        )
        backend.ui["text_count"] += 1

        with self.assertRaisesRegex(SemanticGateClosed, "counter is absent or ambiguous"):
            make_oracle(backend).raid_remain("raid_20260827", "normal")

    def test_current_raid_multiple_sortie_close_is_exact_and_resource_free(self):
        root = "OverlayCamera/Overlay/UIMain/ContinuousOperationWindowUI(Clone)"
        back = root + "/window/top/btnBack"
        back_bounds = {"left": 891, "top": 149, "right": 963, "bottom": 201}
        backend = FakeBackend(
            [make_button("btnBack", back, 927, 175, back_bounds, raycast_top=None)]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "MULTIPLE SORTIES",
                    root + "/window/top/bg/title/title/title_en",
                ),
                make_text("1", root + "/window/panel/content/value_bg/value"),
                make_text("0/0", root + "/window/panel/ticket/Number"),
                make_text("14", root + "/window/panel/bonus/Number"),
            ],
            images=[
                make_image(back, "close_btn", back_bounds),
                make_image(
                    root + "/window/panel/ticket/checkbox/checkmark",
                    "checkmark_ban",
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.raid_multiple_sortie_visible("raid_20260827"))
        state = oracle.raid_multiple_sortie_state("raid_20260827")
        self.assertEqual(
            state,
            RaidMultipleSortieState(
                generation=10,
                event="raid_20260827",
                sortie_count=1,
                ticket_selected=0,
                ticket_owned=0,
                bonus_count=14,
                zero_ticket_disabled=True,
                root=root,
            ),
        )
        receipt = oracle.click_raid_multiple_sortie_back("raid_20260827")
        self.assertEqual(receipt.semantic_id, "raid/multiple-sortie/back")
        self.assertEqual(backend.taps, [(927, 175)])

        ticket_text = next(
            item
            for item in backend.ui["texts"]
            if item["path"] == root + "/window/panel/ticket/Number"
        )
        checkmark = next(
            item
            for item in backend.ui["images"]
            if item["sprite"] == "checkmark_ban"
        )
        backend.ui["images"].remove(checkmark)
        backend.ui["image_count"] -= 1
        ticket_text["text"] = "1/2"
        positive = oracle.raid_multiple_sortie_state("raid_20260827")
        self.assertEqual(
            (positive.ticket_selected, positive.ticket_owned), (1, 2)
        )
        self.assertFalse(positive.zero_ticket_disabled)

        backend.ui["images"].append(checkmark)
        backend.ui["image_count"] += 1
        with self.assertRaisesRegex(SemanticGateClosed, "positive ticket state is disabled"):
            oracle.raid_multiple_sortie_state("raid_20260827")
        ticket_text["text"] = "0/0"
        backend.ui["images"].remove(checkmark)
        backend.ui["image_count"] -= 1
        with self.assertRaisesRegex(SemanticGateClosed, "zero-ticket state is inconsistent"):
            oracle.raid_multiple_sortie_state("raid_20260827")
        backend.ui["images"].append(checkmark)
        backend.ui["image_count"] += 1

        backend.taps.clear()
        backend.ui["images"][0]["sprite"] = "close_btn_disabled"
        with self.assertRaisesRegex(SemanticGateClosed, "identity is incomplete"):
            oracle.raid_multiple_sortie_visible("raid_20260827")
        with self.assertRaisesRegex(SemanticGateClosed, "identity is incomplete"):
            oracle.click_raid_multiple_sortie_back("raid_20260827")
        self.assertEqual(backend.taps, [])

    def test_main_raid_entry_uses_current_typed_activity_button(self):
        path = (
            "OverlayCamera/Overlay/UIMain/NewMainMellowTheme(Clone)/frame/right/"
            "activity/MainActBossBtn"
        )
        bounds = {
            "left": 945.061,
            "top": 65.64,
            "right": 1058.394,
            "bottom": 179.01,
        }
        backend = FakeBackend(
            [
                make_button(
                    "MainActBossBtn",
                    path,
                    1001.727,
                    122.325,
                    bounds,
                    raycast_top=None,
                ),
                make_button("battle", "root/frame/right/1/battle"),
                make_button("formation", "root/frame/right/1/formation"),
            ]
        )
        icon = make_image(path + "/Image", "event_boss", bounds)
        icon["raycast_target"] = True
        backend.ui = make_ui([], images=[icon])
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("main/raid"))
        receipt = oracle.click("main/raid")

        self.assertEqual(receipt.path, path)
        self.assertEqual(backend.taps, [(1002, 122)])

    def test_main_raid_entry_rejects_a_mismatched_typed_icon(self):
        path = "root/frame/right/activity/MainActBossBtn"
        bounds = {"left": 945, "top": 66, "right": 1058, "bottom": 179}
        backend = FakeBackend(
            [
                make_button(
                    "MainActBossBtn",
                    path,
                    1002,
                    122,
                    bounds,
                    raycast_top=None,
                ),
                make_button("battle", "root/frame/right/1/battle"),
                make_button("formation", "root/frame/right/1/formation"),
            ]
        )
        icon = make_image(path + "/Image", "event_summary", bounds)
        icon["raycast_target"] = True
        backend.ui = make_ui([], images=[icon])
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/raid"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/raid")
        self.assertEqual(backend.taps, [])

    def test_main_raid_entry_rejects_an_unrelated_activity_button(self):
        backend = FakeBackend(
            [
                make_button(
                    "MainCoreActivityBtn",
                    "root/frame/right/activity/MainCoreActivityBtn",
                    1111,
                    122,
                )
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/raid"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/raid")
        self.assertEqual(backend.taps, [])
