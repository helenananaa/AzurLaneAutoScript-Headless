"""Campaign preparation regression cases for the oracle."""

import copy
import unittest
from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.semantic_oracle import SemanticGateClosed, SemanticTargetMissing
from tests.semantic_support.campaign_fixtures import (
    make_event_preparation_backend,
    make_live_eventsp_fleet_preparation_backend,
    make_live_eventsp_map_preparation_backend,
    make_normal_fleet_preparation_backend,
)
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_image,
    make_oracle,
    make_text,
    make_toggle,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport
from types import SimpleNamespace


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_hard_recommend_confirmation_requires_exact_prompt(self):
        root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        fleet = (
            "UICamera/Canvas/UIOrigin/LevelFleetSelectView(Clone)/"
            "panel/Fixed/start_button"
        )

        def prompt_backend(content="是否采用推荐配置补齐空余位置?"):
            backend = FakeBackend([
                make_button("start_button", fleet, raycast_top=False),
                make_button("custom_button_1(Clone)",
                            root + "button_container/custom_button_1(Clone)"),
                make_button("custom_button_2(Clone)",
                            root + "button_container/custom_button_2(Clone)"),
            ])
            backend.ui = make_ui([
                make_text(content, root + "msg_panel/content"),
                make_text("确 定", root + "button_container/custom_button_1(Clone)/pic"),
                make_text("取 消", root + "button_container/custom_button_2(Clone)/pic"),
            ], images=[
                make_image(root + "button_container/custom_button_1(Clone)",
                           "btn_big_blue"),
                make_image(root + "button_container/custom_button_2(Clone)",
                           "btn_big_grey"),
            ])
            return backend

        backend = prompt_backend()
        self.assertTrue(make_oracle(backend).campaign_hard_recommend_prompt_present())
        receipt = make_oracle(backend).confirm_campaign_hard_recommend_prompt()
        self.assertEqual(receipt.semantic_id, "campaign/hard/recommend/confirm")
        self.assertEqual(len(backend.taps), 1)

        backend = prompt_backend()
        cancel_receipt = make_oracle(backend).cancel_campaign_hard_recommend_prompt()
        self.assertEqual(cancel_receipt.semantic_id, "campaign/hard/recommend/cancel")
        self.assertEqual(cancel_receipt.path,
                         root + "button_container/custom_button_2(Clone)")

        backend = prompt_backend("购买道具?")
        self.assertTrue(make_oracle(backend).campaign_hard_recommend_prompt_present())
        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).confirm_campaign_hard_recommend_prompt()
        self.assertEqual(backend.taps, [])

        backend = FakeBackend([make_button("start_button", fleet)])
        self.assertFalse(make_oracle(backend).campaign_hard_recommend_prompt_present())

        backend = prompt_backend()
        backend.buttons["buttons"][1]["raycast_top"] = False
        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).confirm_campaign_hard_recommend_prompt()
        self.assertEqual(backend.taps, [])

    def test_auto_reentry_requires_exact_label_hit_and_unblocked_surface(self):
        root = "OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/"
        for top, label, allowed in ((True, "再次前往", True), (None, "再次前往", False), (True, "购买", False)):
            backend = FakeBackend([
                make_button("ButtonGO", root + "ButtonGO", raycast_top=top),
                make_button("enter_main", "UICamera/Canvas/UIMain/LevelMainScene(Clone)/entrance/enters/enter_main", raycast_top=False),
            ])
            backend.ui = make_ui([make_text(label, root + "ButtonGO/pic")])
            oracle = make_oracle(backend)
            self.assertIs(oracle.campaign_auto_search_reentry_available(), allowed)
            if allowed:
                self.assertEqual(oracle.click_campaign_auto_search_reentry().semantic_id, "reward/campaign-total/go")
            else:
                with self.assertRaises(SemanticGateClosed):
                    oracle.click_campaign_auto_search_reentry()
                self.assertEqual(backend.taps, [])

    def test_auto_book_uses_the_observed_result_widget_not_prep_coordinates(self):
        root = "OverlayCamera/Overlay/UIMain/LevelStageTotalRewardPanel(Clone)/Window/Fixed/SpList/Item"
        item = root + "/Active/Item/IconTpl/icon_bg"
        checkbox = root + "/Active/Checkbox"
        for selected in (False, True):
            backend = FakeBackend([
                make_button("Item", root),
                make_button("enter_main", "UICamera/Canvas/UIMain/LevelMainScene(Clone)/entrance/enters/enter_main", raycast_top=False),
            ])
            images = [make_image(item + "/icon", "tebiezuozhan"), make_image(checkbox, "bg_rect")]
            if selected:
                images.append(make_image(checkbox + "/Mark", "gou"))
            backend.ui = make_ui([make_text("568", item + "/count")], images=images)
            oracle = make_oracle(backend)
            self.assertIsNone(oracle.campaign_2x_book_selected(mode="prep"))
            self.assertIs(oracle.campaign_2x_book_selected(mode="auto"), selected)
            self.assertEqual(oracle.click_campaign_2x_book(selected, mode="auto").semantic_id, "campaign/2x-book-auto")
            self.assertEqual(len(backend.taps), 1)
        backend = FakeBackend([make_button("Item", root, raycast_top=None)])
        backend.ui = make_ui([make_text("568", item + "/count")], images=images)
        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).click_campaign_2x_book(True, mode="auto")
        self.assertEqual(backend.taps, [])

    def test_book_confirmation_is_not_a_dock_full_popup_and_proves_quantity(self):
        root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        backend = FakeBackend([
            make_button("custom_button_1(Clone)", root + "button_container/custom_button_1(Clone)"),
            make_button("custom_button_2(Clone)", root + "button_container/custom_button_2(Clone)"),
        ])
        pairs = {
            "single_item_panel/display_panel/name_container/name/Text": "高效作战指令书",
            "single_item_panel/display_panel/desc/Text": "是否使用高效作战指令书？战斗石油消耗增加100%",
            "single_item_panel/left/own/Text": "569",
            "single_item_panel/left/IconTpl/icon_bg/count": "1",
            "button_container/custom_button_1(Clone)/pic": "确 定",
            "button_container/custom_button_2(Clone)/pic": "取 消",
        }
        backend.ui = make_ui([make_text(v, root+k) for k,v in pairs.items()])
        oracle = make_oracle(backend)
        self.assertFalse(oracle.campaign_dock_full_visible("12-4"))
        self.assertTrue(oracle.campaign_2x_book_prompt_visible())
        self.assertEqual(oracle.click_campaign_2x_book_prompt(False).semantic_id, "campaign/2x-book/cancel")
        pairs["single_item_panel/left/IconTpl/icon_bg/count"] = "2"
        backend.ui = make_ui([make_text(v, root+k) for k,v in pairs.items()])
        with self.assertRaisesRegex(SemanticGateClosed, "terms"):
            oracle.click_campaign_2x_book_prompt(True)
        self.assertEqual(len(backend.taps), 1)

    def test_normal_stage_mode_uses_chapter_destination_not_event_switch(self):
        oracle = make_oracle(FakeBackend([]))
        oracle.campaign_map_preparation_state = lambda stage: SimpleNamespace(
            proceed_button=SimpleNamespace(path="OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/start_button"))
        for destination, current in (("hard", "normal"), ("normal", "hard")):
            oracle.campaign_mode_switch_state = lambda: destination
            self.assertEqual(oracle.campaign_map_preparation_mode_state("12-4"), current)
        # Native detail identity owns this interpretation; an event-like name
        # does not invalidate an otherwise exact chapter detail.
        self.assertEqual(oracle.campaign_map_preparation_mode_state("A1"), "hard")
        oracle.campaign_map_preparation_state = lambda stage: SimpleNamespace(
            proceed_button=SimpleNamespace(path="UnknownUI/panel/start_button"))
        with self.assertRaisesRegex(SemanticGateClosed, "not on an event stage"):
            oracle.campaign_map_preparation_mode_state("A1")

    def test_2x_book_toggle_proves_inventory_identity_and_both_states(self):
        root = "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/Fixed/sp"
        for selected in (False, True):
            backend = FakeBackend([make_button("sp", root)])
            images = [make_image(root + "/item/icon", "tebiezuozhan"),
                      make_image(root + "/checkbox", "bg_rect")]
            if selected:
                images.append(make_image(root + "/checkbox/mark", "gou"))
            backend.ui = make_ui([make_text("569", root + "/item/count")], images=images)
            oracle = make_oracle(backend)
            self.assertIs(oracle.campaign_2x_book_selected(), selected)
            oracle.click_campaign_2x_book(selected)
            self.assertEqual(len(backend.taps), 1)

    def test_2x_book_rejects_empty_inventory_unknown_marker_and_obscured_button(self):
        root = "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/Fixed/sp"
        for count, marker, top in (("0", None, True), ("2", "unknown", True), ("2", None, False)):
            backend = FakeBackend([make_button("sp", root, raycast_top=top)])
            images = [make_image(root + "/item/icon", "tebiezuozhan"),
                      make_image(root + "/checkbox", "bg_rect")]
            if marker:
                images.append(make_image(root + "/checkbox/mark", marker))
            backend.ui = make_ui([make_text(count, root + "/item/count")], images=images)
            with self.assertRaises(SemanticGateClosed):
                make_oracle(backend).click_campaign_2x_book(False)
            self.assertEqual(backend.taps, [])

    def test_clear_mode_reads_both_states_and_rejects_unknown_hit_target(self):
        path = "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle"
        for enabled in (True, False):
            backend = FakeBackend([make_button("Toggle", path)])
            backend.ui = make_ui([], images=[make_image(path + ("/on" if enabled else "/off"), "live2d_on" if enabled else "live2d_off")])
            oracle = make_oracle(backend)
            self.assertIs(oracle.campaign_clear_mode_selected(), enabled)
            oracle.click_campaign_clear_mode(enabled)
            self.assertEqual(len(backend.taps), 1)
        backend = FakeBackend([make_button("Toggle", path, raycast_top=None)])
        backend.ui = make_ui([], images=[make_image(path + "/on", "live2d_on")])
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            make_oracle(backend).click_campaign_clear_mode(True)
        self.assertEqual(backend.taps, [])

    def test_clear_mode_rejects_conflicting_markers_and_changed_state(self):
        path = "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle"
        backend = FakeBackend([make_button("Toggle", path)])
        backend.ui = make_ui([], images=[make_image(path + "/on", "live2d_on"), make_image(path + "/off", "live2d_off")])
        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            make_oracle(backend).campaign_clear_mode_selected()
        backend.ui = make_ui([], images=[make_image(path + "/on", "live2d_on")])
        with self.assertRaisesRegex(SemanticGateClosed, "changed"):
            make_oracle(backend).click_campaign_clear_mode(False)
        self.assertEqual(backend.taps, [])

    def test_campaign_auto_search_roles_use_exact_duty_controls(self):
        prefix = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/"
            "panel/"
        )
        buttons = []
        for fleet in (1, 2):
            for item in range(1, 5):
                buttons.append(
                    make_button(
                        "Item{0}".format(item),
                        prefix
                        + "ShipList/fleet/{0}/DutySelect/Item{1}".format(
                            fleet, item
                        ),
                    )
                )
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    prefix + "Fixed/RightTabs/duty_btn", checked=True
                )
            ],
            images=[
                make_image(
                    prefix
                    + "ShipList/fleet/1/DutySelect/Item1/Checkmark",
                    "gou",
                ),
                make_image(
                    prefix
                    + "ShipList/fleet/2/DutySelect/Item2/Checkmark",
                    "gou",
                ),
            ],
        )

        state = make_oracle(backend).campaign_auto_search_role_state()

        self.assertEqual((state.fleet1_role, state.fleet2_role), ("mob", "boss"))

    def test_campaign_auto_search_roles_reject_multiple_checkmarks(self):
        prefix = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/"
            "panel/"
        )
        buttons = [
            make_button(
                "Item{0}".format(item),
                prefix
                + "ShipList/fleet/{0}/DutySelect/Item{1}".format(fleet, item),
            )
            for fleet in (1, 2)
            for item in range(1, 5)
        ]
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    prefix + "Fixed/RightTabs/duty_btn", checked=True
                )
            ],
            images=[
                make_image(
                    prefix
                    + "ShipList/fleet/1/DutySelect/Item1/Checkmark",
                    "gou",
                ),
                make_image(
                    prefix
                    + "ShipList/fleet/1/DutySelect/Item3/Checkmark",
                    "gou",
                ),
                make_image(
                    prefix
                    + "ShipList/fleet/2/DutySelect/Item2/Checkmark",
                    "gou",
                ),
            ],
        )

        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            make_oracle(backend).campaign_auto_search_role_state()

    def test_campaign_hard_auto_search_proves_game_managed_9710_surface(self):
        prefix = (
            "root/OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/"
            "panel/"
        )
        backend = FakeBackend([])
        backend.ui = make_ui(
            [
                make_text(
                    "机动总值大于1250（1458）",
                    prefix
                    + "Fixed/limit_list/limit_elite/limit_list/condition/Text",
                ),
                make_text("编队", prefix + "Fixed/RightTabs/formation_btn/text"),
                make_text("指挥喵", prefix + "Fixed/RightTabs/commander_btn/text"),
                make_text(
                    "编队调整", prefix + "Fixed/RightTabs/adjustment_btn/text"
                ),
            ],
            toggles=[
                make_toggle(
                    prefix + "Fixed/RightTabs/formation_btn", checked=True
                ),
                make_toggle(
                    prefix + "Fixed/RightTabs/commander_btn", checked=False
                ),
                make_toggle(
                    prefix + "Fixed/RightTabs/adjustment_btn", checked=False
                ),
            ],
        )

        state = make_oracle(backend).campaign_auto_search_role_state()

        self.assertEqual(
            (state.fleet1_role, state.fleet2_role),
            ("game-managed", "game-managed"),
        )

    def test_campaign_auto_search_toggle_uses_exact_stage_info_identity(self):
        path = (
            "root/OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"
            "BottomExtra/LoopGroup/view/container/AutoFight"
        )
        backend = FakeBackend(
            [
                make_button(
                    "main",
                    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                    "float/levels/items/Chapter_1204/main",
                ),
                make_button(
                    "start",
                    "root/OverlayCamera/Overlay/UIMain/"
                    "LevelStageInfoView(Clone)/panel/start",
                ),
            ]
        )
        backend.ui = make_ui(
            [], toggles=[make_toggle(path, checked=True, x=838, y=596)]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.toggle_selected("campaign/map-preparation/auto-search"))
        receipt = oracle.click_toggle("campaign/map-preparation/auto-search")

        self.assertEqual(receipt.path, path)
        self.assertEqual(backend.taps, [(838, 596)])

        backend.ui = make_ui(
            [],
            toggles=[make_toggle(path, checked=True, raycast_top=None, x=838, y=596)],
        )
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click_toggle("campaign/map-preparation/auto-search")
        self.assertEqual(backend.taps, [(838, 596)])

    def test_campaign_auto_search_effectively_off_when_sp_loop_mode_is_off(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
        toggle_path = root + "BottomExtra/LoopGroup/view/container/AutoFight"
        control_path = root + "BottomExtra/LoopGroup/Loop/Toggle"
        backend = FakeBackend(
            [
                make_button(
                    "Toggle",
                    control_path,
                    x=1022,
                    y=595,
                    bounds={"left": 979, "top": 583, "right": 1065, "bottom": 607},
                    raycast_top=None,
                )
            ]
        )
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    toggle_path,
                    checked=True,
                    raycast_top=None,
                    x=949,
                    y=595,
                    bounds={"left": 895, "top": 582, "right": 1002, "bottom": 608},
                )
            ],
            images=[
                make_image(
                    root + "BottomExtra/LoopGroup/Loop/Toggle/off",
                    "live2d_off",
                    {"left": 1033, "top": 589, "right": 1052, "bottom": 601},
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.campaign_auto_search_selected())
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click_toggle("campaign/map-preparation/auto-search")
        self.assertEqual(backend.taps, [])

    def test_campaign_auto_search_effectively_off_when_standard_loop_is_off(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"
        toggle_path = root + "BottomExtra/LoopGroup/view/container/AutoFight"
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    toggle_path,
                    checked=True,
                    raycast_top=False,
                    x=950,
                    y=596,
                )
            ],
            images=[
                make_image(
                    root + "BottomExtra/LoopGroup/Loop/Toggle/off",
                    "live2d_off",
                    {"left": 1034, "top": 590, "right": 1053, "bottom": 603},
                )
            ],
        )

        self.assertFalse(make_oracle(backend).campaign_auto_search_selected())

    def test_campaign_auto_search_clicks_exact_sp_delegated_image_when_loop_on(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
        toggle_path = root + "BottomExtra/LoopGroup/view/container/AutoFight"
        control_path = root + "BottomExtra/LoopGroup/Loop/Toggle"
        toggle_bounds = {
            "left": 783,
            "top": 582,
            "right": 890,
            "bottom": 608,
        }
        delegated_image = make_image(toggle_path, "white_dot", toggle_bounds)
        delegated_image["raycast_target"] = True
        backend = FakeBackend(
            [
                make_button(
                    "start_button",
                    root + "start_button",
                    raycast_top=True,
                ),
                make_button(
                    "Toggle",
                    control_path,
                    x=1065,
                    y=595,
                    bounds={
                        "left": 979,
                        "top": 583,
                        "right": 1065,
                        "bottom": 607,
                    },
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            toggles=[
                make_toggle(
                    toggle_path,
                    checked=True,
                    raycast_top=None,
                    x=837,
                    y=595,
                    bounds=toggle_bounds,
                )
            ],
            images=[
                make_image(
                    control_path + "/on",
                    "live2d_on",
                    {"left": 995, "top": 589, "right": 1010, "bottom": 601},
                ),
                delegated_image,
            ],
        )
        oracle = make_oracle(backend)

        receipt = oracle.click_toggle("campaign/map-preparation/auto-search")

        self.assertEqual(receipt.path, toggle_path)
        self.assertEqual(backend.taps, [(837, 595)])

    def test_campaign_map_preparation_is_stage_bound_and_cancel_only(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                    "top/top_chapter/back_button",
                    raycast_top=False,
                ),
                make_button("start_button", root + "start_button", 951, 523),
                make_button("btnBack", root + "btnBack", 1066, 149),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("12–4  ", root + "title_form/title_index"),
                make_text("TF58，翱翔于天际", root + "title_form/title"),
            ]
        )
        oracle = make_oracle(backend)

        state = oracle.campaign_map_preparation_state("12-4")
        self.assertEqual(state.kind, "map")
        self.assertEqual(state.stage_code, "12-4")
        self.assertEqual(state.title, "TF58，翱翔于天际")
        proceed = oracle.click_campaign_map_preparation("12-4")
        cancel = oracle.cancel_campaign_map_preparation("12-4")
        self.assertEqual(proceed.semantic_id, "campaign/map-preparation/proceed")
        self.assertEqual(cancel.semantic_id, "campaign/map-preparation/cancel")
        self.assertEqual(backend.taps, [(951, 523), (1066, 149)])

        backend.ui["texts"][0]["text"] = "12–3"
        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            make_oracle(backend).campaign_map_preparation_state("12-4")

    def test_campaign_map_preparation_accepts_reviewed_rootless_live_path_only(self):
        root = "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"

        def live_backend():
            backend = FakeBackend(
                [
                    make_button(
                        "bg",
                        "OverlayCamera/Overlay/UIMain/"
                        "LevelStageInfoView(Clone)/bg",
                        raycast_top=False,
                    ),
                    make_button("start_button", root + "start_button", 951, 523),
                    make_button("btnBack", root + "btnBack", 1066, 149),
                ]
            )
            backend.ui = make_ui(
                [
                    make_text("12–4  ", root + "title_form/title_index"),
                    make_text("TF58，翱翔于天际", root + "title_form/title"),
                ]
            )
            return backend

        backend = live_backend()
        state = make_oracle(backend).campaign_map_preparation_state("12-4")
        self.assertEqual((state.kind, state.stage_code), ("map", "12-4"))

        backend = live_backend()
        for button in backend.buttons["buttons"]:
            button["path"] = "Mirror/" + button["path"]
        for text in backend.ui["texts"]:
            text["path"] = "Mirror/" + text["path"]
        with self.assertRaisesRegex(SemanticGateClosed, "not reviewed"):
            make_oracle(backend).campaign_map_preparation_state("12-4")

    def test_hard_114_clear_panel_alternate_proceed_is_narrowly_reviewed(self):
        root = "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/"

        def backend_for_hard():
            backend = FakeBackend([
                make_button(
                    "btn_normal",
                    "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
                    "main/left_chapter/buttons/btn_normal",
                    raycast_top=None,
                ),
                make_button("start_button_l", root + "start_button_l", 1007, 523,
                            raycast_top=None),
                make_button("btnBack", root + "btnBack", 1069, 191),
            ])
            backend.ui = make_ui([
                make_text("11–4", root + "title_form/title_index"),
                make_text("撕裂的夜幕", root + "title_form/title"),
                make_text("100%", root + "progress/Text/value"),
            ], images=[make_image(root + "start_button_l", "qianwang_butten")])
            return backend

        backend = backend_for_hard()
        oracle = make_oracle(backend)
        state = oracle.campaign_map_preparation_state("11-4")
        self.assertEqual(state.proceed_button.path, root + "start_button_l")
        self.assertEqual(
            oracle.click_campaign_map_preparation("11-4").semantic_id,
            "campaign/map-preparation/proceed",
        )
        self.assertEqual(len(backend.taps), 1)

        for missing in ("hard_underlay", "progress", "sprite"):
            backend = backend_for_hard()
            if missing == "hard_underlay":
                backend.buttons["buttons"].pop(0)
            elif missing == "progress":
                backend.ui["texts"].pop()
            else:
                backend.ui["images"].clear()
            with self.subTest(missing=missing), self.assertRaises(SemanticGateClosed):
                make_oracle(backend).campaign_map_preparation_state("11-4")
            self.assertEqual(backend.taps, [])

        backend = backend_for_hard()
        backend.buttons["buttons"][1]["raycast_top"] = False
        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).campaign_map_preparation_state("11-4")
        self.assertEqual(backend.taps, [])

    def test_current_event_map_preparation_uses_sp_detail_surface(self):
        root = "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
        backend = FakeBackend(
            [
                make_button("start_button", root + "start_button", 949, 521),
                make_button("btnBack", root + "btnBack", 1065, 148),
                make_button(
                    "Switch",
                    root + "Difficulty/Normal/Switch",
                    392,
                    598,
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("A1  ", root + "title_form/title_index"),
                make_text("新的活动关卡", root + "title_form/title"),
                make_text("10", root + "cost/text"),
            ]
        )
        oracle = make_oracle(backend)

        state = oracle.campaign_map_preparation_state("a1")
        self.assertEqual(state.stage_code, "a1")
        self.assertEqual(state.oil_cost, 10)
        self.assertEqual(oracle.campaign_map_preparation_mode_state("a1"), "normal")
        mode_receipt = oracle.click_campaign_map_preparation_mode("a1", "hard")
        self.assertEqual(
            mode_receipt.semantic_id,
            "campaign/map-preparation/mode/hard",
        )
        receipt = oracle.cancel_campaign_map_preparation("a1")
        self.assertEqual(receipt.semantic_id, "campaign/map-preparation/cancel")
        self.assertEqual(backend.taps, [(392, 598), (1065, 148)])

    def test_campaign_preparation_state_requires_one_complete_reviewed_root(self):
        for kind in ("map", "fleet"):
            with self.subTest(case="canonical", kind=kind):
                backend = make_event_preparation_backend("sp", kind=kind)
                state = make_oracle(backend).campaign_preparation_state("sp")
                self.assertEqual((state.kind, state.stage_code), (kind, "sp"))

        backend = FakeBackend([])
        self.assertIsNone(make_oracle(backend).campaign_preparation_state("sp"))

        map_root = (
            "root/OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/"
        )
        backend = FakeBackend([])
        backend.ui = make_ui([make_text("SP", map_root + "title_form/title_index")])
        with self.assertRaisesRegex(SemanticGateClosed, "controls"):
            make_oracle(backend).campaign_preparation_state("sp")
        self.assertEqual(backend.taps, [])

        fleet_root = (
            "root/OverlayCamera/Overlay/UIMain/"
            "LevelFleetSelectView(Clone)/panel/"
        )
        backend = FakeBackend([])
        backend.ui = make_ui(
            [make_text("舰队选择", fleet_root + "Fixed/title/Image/text")]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "cancel"):
            make_oracle(backend).campaign_preparation_state("sp")
        self.assertEqual(backend.taps, [])

        for kind in ("map", "fleet"):
            with self.subTest(case="cross-root", kind=kind):
                backend = make_event_preparation_backend("sp", kind=kind)
                for text in backend.ui["texts"]:
                    text["path"] = text["path"].replace("root/", "other/", 1)
                with self.assertRaisesRegex(
                    SemanticGateClosed, "root is not reviewed"
                ):
                    make_oracle(backend).campaign_preparation_state("sp")
                self.assertEqual(backend.taps, [])

        for kind in ("map", "fleet"):
            with self.subTest(case="remounted", kind=kind):
                backend = make_event_preparation_backend(
                    "sp", kind=kind, prefix="root/Remounted/"
                )
                with self.assertRaisesRegex(
                    SemanticGateClosed, "root is not reviewed"
                ):
                    make_oracle(backend).campaign_preparation_state("sp")
                self.assertEqual(backend.taps, [])

            with self.subTest(case="renamed-remount", kind=kind):
                backend = make_event_preparation_backend("sp", kind=kind)
                for button in backend.buttons["buttons"]:
                    button["path"] = button["path"].replace(
                        "View(Clone)", "View(Remounted)"
                    ).replace("SPUI(Clone)", "SPUI(Remounted)")
                for text in backend.ui["texts"]:
                    text["path"] = text["path"].replace(
                        "View(Clone)", "View(Remounted)"
                    ).replace("SPUI(Clone)", "SPUI(Remounted)")
                with self.assertRaisesRegex(
                    SemanticGateClosed, "root is not reviewed"
                ):
                    make_oracle(backend).campaign_preparation_state("sp")
                self.assertEqual(backend.taps, [])

        for kind in ("map", "fleet"):
            with self.subTest(case="duplicate-root", kind=kind):
                backend = make_event_preparation_backend("sp", kind=kind)
                duplicate = make_event_preparation_backend(
                    "sp", kind=kind, prefix="other/"
                )
                backend.buttons["buttons"].extend(duplicate.buttons["buttons"])
                backend.buttons["button_count"] = len(backend.buttons["buttons"])
                backend.ui["texts"].extend(duplicate.ui["texts"])
                backend.ui["text_count"] = len(backend.ui["texts"])
                with self.assertRaisesRegex(
                    SemanticGateClosed, "root is not reviewed|ambiguous"
                ):
                    make_oracle(backend).campaign_preparation_state("sp")

        backend = make_event_preparation_backend("sp", kind="fleet")
        for button in backend.buttons["buttons"]:
            if "LevelSelectSPFullUI" in button["path"]:
                button["path"] = button["path"].replace(
                    "root/", "root/Remounted/", 1
                )
        for text in backend.ui["texts"]:
            if "LevelSelectSPFullUI" in text["path"]:
                text["path"] = text["path"].replace(
                    "root/", "root/Remounted/", 1
                )
        with self.assertRaisesRegex(SemanticGateClosed, "underlay is not reviewed"):
            make_oracle(backend).campaign_preparation_state("sp")
        self.assertEqual(backend.taps, [])

        for kind in ("map", "fleet"):
            for generation in (7, 13):
                with self.subTest(
                    case="incoherent", kind=kind, generation=generation
                ):
                    backend = make_event_preparation_backend("sp", kind=kind)
                    backend.ui["generation"] = generation
                    with self.assertRaisesRegex(
                        SemanticGateClosed, "not coherent|moved backwards"
                    ):
                        make_oracle(backend).campaign_preparation_state("sp")

        backend = make_event_preparation_backend("sp", kind="map")
        backend.ui["text_truncated"] = True
        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).campaign_preparation_state("sp")

        backend = make_event_preparation_backend("sp", kind="fleet")
        backend.ui["texts"][1]["flags"] |= 0x10
        with self.assertRaisesRegex(SemanticGateClosed, "underlay"):
            make_oracle(backend).campaign_preparation_state("sp")

        for kind in ("map", "fleet"):
            with self.subTest(case="wrong-stage", kind=kind):
                backend = make_event_preparation_backend("sp", kind=kind)
                with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
                    make_oracle(backend).campaign_preparation_state("ex")

    def test_campaign_preparation_absolute_root_allowlist_rejects_aliases(self):
        def rewrite(backend, old_root, new_root):
            for button in backend.buttons["buttons"]:
                if button["path"].startswith(old_root):
                    button["path"] = new_root + button["path"][len(old_root) :]
            for group in ("texts", "toggles", "images"):
                for item in backend.ui[group]:
                    if item["path"].startswith(old_root):
                        item["path"] = new_root + item["path"][len(old_root) :]

        event_map = make_event_preparation_backend("sp", kind="map")
        event_fleet = make_event_preparation_backend("sp", kind="fleet")
        normal_fleet = make_normal_fleet_preparation_backend("12-4")
        self.assertEqual(
            make_oracle(event_map).campaign_preparation_state("sp").kind, "map"
        )
        self.assertEqual(
            make_oracle(event_fleet).campaign_preparation_state("sp").kind,
            "fleet",
        )
        self.assertEqual(
            make_oracle(normal_fleet).campaign_preparation_state("12-4").kind,
            "fleet",
        )

        canonical_prep_roots = {
            "map": (
                "root/OverlayCamera/Overlay/UIMain/"
                "LevelInfoSPUI(Clone)/panel/"
            ),
            "fleet": (
                "root/OverlayCamera/Overlay/UIMain/"
                "LevelFleetSelectView(Clone)/panel/"
            ),
        }
        for kind, canonical in canonical_prep_roots.items():
            variants = (
                "root/Mirror/" + canonical[len("root/") :],
                "root/550e8400-e29b-41d4-a716-446655440000/"
                + canonical[len("root/") :],
                canonical.lower(),
                "extra/" + canonical,
                canonical.replace("UIMain/Level", "UIMain/Nested/Level"),
                canonical.replace("(Clone)", "(UnknownClone)"),
                canonical.replace("UIMain/Level", "UIMain/../Level"),
                canonical
                + "Mirror/"
                + (
                    "LevelInfoSPUI(Clone)/panel/"
                    if kind == "map"
                    else "LevelFleetSelectView(Clone)/panel/"
                ),
            )
            for index, variant in enumerate(variants):
                with self.subTest(kind=kind, variant=index):
                    backend = make_event_preparation_backend("sp", kind=kind)
                    rewrite(backend, canonical, variant)
                    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
                    adapter.begin_campaign_pre_sortie("SP")
                    context = adapter._campaign_context
                    context_before = dict(vars(context))
                    ledger_before = dict(adapter._action_ledger._remaining)

                    with self.assertRaises(SemanticGateClosed):
                        adapter.appear(SimpleNamespace(name="EVENT_CHECK"))

                    self.assertEqual(backend.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(adapter._action_ledger._remaining, ledger_before)
                    adapter.end_campaign_pre_sortie()

        underlays = (
            (
                "event",
                "sp",
                make_event_preparation_backend,
                "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/",
            ),
            (
                "normal",
                "12-4",
                lambda stage, **_kwargs: make_normal_fleet_preparation_backend(
                    stage
                ),
                "root/UICamera/Canvas/UIMain/LevelMainScene(Clone)/",
            ),
        )
        for surface, stage_code, factory, canonical in underlays:
            variants = (
                "root/Mirror/" + canonical[len("root/") :],
                "root/550e8400-e29b-41d4-a716-446655440000/"
                + canonical[len("root/") :],
                canonical.upper(),
                "extra/" + canonical,
                canonical.replace("UIMain/Level", "UIMain/Nested/Level"),
                canonical.replace("(Clone)", "(UnknownClone)"),
                canonical.replace("UIMain/Level", "UIMain/../Level"),
                canonical
                + "Mirror/"
                + (
                    "LevelSelectSPFullUI(Clone)/"
                    if surface == "event"
                    else "LevelMainScene(Clone)/"
                ),
            )
            for index, variant in enumerate(variants):
                with self.subTest(surface=surface, variant=index):
                    backend = factory(stage_code, kind="fleet")
                    rewrite(backend, canonical, variant)
                    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
                    adapter.begin_campaign_pre_sortie(stage_code)
                    context = adapter._campaign_context
                    context_before = dict(vars(context))
                    ledger_before = dict(adapter._action_ledger._remaining)

                    with self.assertRaises(SemanticGateClosed):
                        adapter.appear(SimpleNamespace(name="EVENT_CHECK"))

                    self.assertEqual(backend.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(adapter._action_ledger._remaining, ledger_before)
                    adapter.end_campaign_pre_sortie()

    def test_live_eventd_d1_map_preparation_accepts_only_reviewed_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="d1")
        pooled_paths = {
            "panel/Difficulty/Hard/Mask_Difficulty_Loop",
            "panel/Difficulty/Mask_Difficlty",
            "panel/Difficulty/Mask_Difficlty/Image",
            "panel/Difficulty/Mask_Difficlty/Image_1",
            "panel/Difficulty/Mask_Difficlty/Image_2",
        }
        for image in backend.ui["images"]:
            if image["path"].rsplit("LevelInfoSPUI(Clone)/", 1)[-1] in pooled_paths:
                image["sprite"] = "pooled_star_sprite"
                image["adb_bounds"] = None
            if image["path"].endswith("/panel/passState/Image"):
                image["sprite"] = "2"
        state = make_oracle(backend).campaign_preparation_state("d1")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "d1", 10)
        )
        self.assertEqual(backend.taps, [])

        unknown = make_live_eventsp_map_preparation_backend(profile="d1")
        unknown.buttons["buttons"].append(
            make_button(
                "Switch",
                "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/"
                "panel/Difficulty/Hard/UnknownSwitch",
                raycast_top=None,
            )
        )
        unknown.buttons["button_count"] = len(unknown.buttons["buttons"])
        with self.assertRaisesRegex(SemanticGateClosed, "record is not reviewed"):
            make_oracle(unknown).campaign_preparation_state("d1")
        self.assertEqual(unknown.taps, [])

    def test_live_eventc_c1_map_preparation_accepts_exact_stage_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="c1")
        state = make_oracle(backend).campaign_preparation_state("c1")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "c1", 10)
        )
        self.assertEqual(backend.taps, [])

        wrong_head = make_live_eventsp_map_preparation_backend(profile="c1")
        for image in wrong_head.ui["images"]:
            if image["path"].endswith("/panel/head/Image"):
                image["sprite"] = "haorenlichade_m_qianting"
        with self.assertRaisesRegex(SemanticGateClosed, "image identity is malformed"):
            make_oracle(wrong_head).campaign_preparation_state("c1")
        self.assertEqual(wrong_head.taps, [])

    def test_live_eventb_b2_map_preparation_accepts_only_reviewed_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="b2")
        pooled_paths = {
            "panel/Difficulty/Mask_Normal",
            "panel/Difficulty/Mask_Normal/Image",
            "panel/Difficulty/Mask_Normal/Image_1",
            "panel/Difficulty/Mask_Normal/Image_2",
            "panel/Difficulty/Normal/Mask_Normal_Loop",
        }
        for image in backend.ui["images"]:
            if image["path"].rsplit("LevelInfoSPUI(Clone)/", 1)[-1] in pooled_paths:
                image["sprite"] = "pooled_stage_star_sprite"
        state = make_oracle(backend).campaign_preparation_state("b2")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "b2", 10)
        )
        self.assertEqual(backend.taps, [])

        unknown = make_live_eventsp_map_preparation_backend(profile="b2")
        unknown.buttons["buttons"].append(
            make_button(
                "Switch",
                "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/"
                "panel/Difficulty/Normal/UnknownSwitch",
                raycast_top=None,
            )
        )
        unknown.buttons["button_count"] = len(unknown.buttons["buttons"])
        with self.assertRaisesRegex(SemanticGateClosed, "record is not reviewed"):
            make_oracle(unknown).campaign_preparation_state("b2")
        self.assertEqual(unknown.taps, [])

        bonus_consumed = make_live_eventsp_map_preparation_backend(profile="b2")
        bonus_paths = {
            "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/"
            "panel/Difficulty/Normal/Bonus1",
            "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/"
            "panel/Difficulty/Normal/Bonus1/Image",
        }
        bonus_consumed.ui["images"] = [
            image
            for image in bonus_consumed.ui["images"]
            if image["path"] not in bonus_paths
        ]
        bonus_consumed.ui["image_count"] = len(bonus_consumed.ui["images"])
        state = make_oracle(bonus_consumed).campaign_preparation_state("b2")
        self.assertEqual(state.stage_code, "b2")

        partial_bonus = make_live_eventsp_map_preparation_backend(profile="b2")
        partial_bonus.ui["images"] = [
            image
            for image in partial_bonus.ui["images"]
            if image["path"] != sorted(bonus_paths)[0]
        ]
        partial_bonus.ui["image_count"] = len(partial_bonus.ui["images"])
        with self.assertRaisesRegex(SemanticGateClosed, "image surface is incomplete"):
            make_oracle(partial_bonus).campaign_preparation_state("b2")

    def test_live_eventc_c2_shared_a2_preparation_accepts_exact_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="a2")
        state = make_oracle(backend).campaign_preparation_state("a2")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "a2", 10)
        )
        self.assertEqual(backend.taps, [])

        wrong_head = make_live_eventsp_map_preparation_backend(profile="a2")
        for image in wrong_head.ui["images"]:
            if image["path"].endswith("/panel/head/Image"):
                image["sprite"] = "emotion_zhongxun"
        with self.assertRaisesRegex(SemanticGateClosed, "image identity is malformed"):
            make_oracle(wrong_head).campaign_preparation_state("a2")
        self.assertEqual(wrong_head.taps, [])

    def test_live_eventc_c2_hard_preparation_accepts_exact_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="c2")
        state = make_oracle(backend).campaign_preparation_state("c2")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "c2", 10)
        )
        self.assertEqual(backend.taps, [])

        wrong_points = make_live_eventsp_map_preparation_backend(profile="c2")
        for text in wrong_points.ui["texts"]:
            if text["path"].endswith("/drops/frame/list/item/icon_bg/count"):
                text["text"] = "90"
        with self.assertRaisesRegex(SemanticGateClosed, "text value changed"):
            make_oracle(wrong_points).campaign_preparation_state("c2")
        self.assertEqual(wrong_points.taps, [])

    def test_live_eventc_c3_shared_a3_preparation_accepts_exact_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="a3")
        state = make_oracle(backend).campaign_preparation_state("a3")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "a3", 10)
        )
        self.assertEqual(backend.taps, [])

    def test_live_eventc_c3_hard_preparation_accepts_exact_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="c3")
        state = make_oracle(backend).campaign_preparation_state("c3")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "c3", 10)
        )
        self.assertEqual(backend.taps, [])

    def test_live_eventd_d2_hard_preparation_accepts_exact_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="d2")
        state = make_oracle(backend).campaign_preparation_state("d2")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "d2", 10)
        )
        self.assertEqual(backend.taps, [])

        bonus_consumed = make_live_eventsp_map_preparation_backend(profile="d2")
        bonus_consumed.ui["images"] = [
            image
            for image in bonus_consumed.ui["images"]
            if "/panel/Difficulty/Hard/Bonus1" not in image["path"]
        ]
        bonus_consumed.ui["image_count"] = len(bonus_consumed.ui["images"])
        state = make_oracle(bonus_consumed).campaign_preparation_state("d2")
        self.assertEqual(state.stage_code, "d2")

    def test_live_eventd_d3_hard_preparation_accepts_exact_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="d3")
        state = make_oracle(backend).campaign_preparation_state("d3")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "d3", 10)
        )
        self.assertEqual(backend.taps, [])
        backend.ui["texts"].append(
            make_text(
                "70477",
                "OverlayCamera/Overlay/UIMain/ResPanel(Clone)/frame/gold/gold_value",
            )
        )
        backend.ui["text_count"] += 1
        self.assertEqual(make_oracle(backend).event_coin("d3"), 70477)
        for toggle in backend.ui["toggles"]:
            if toggle["path"].endswith("/AutoFight"):
                toggle["checked"] = False
        backend.ui["images"] = [
            image
            for image in backend.ui["images"]
            if not image["path"].endswith("/AutoFight/Flag")
        ]
        backend.ui["image_count"] = len(backend.ui["images"])
        self.assertEqual(
            make_oracle(backend).campaign_preparation_state("d3").stage_code,
            "d3",
        )
        self.assertEqual(make_oracle(backend).event_coin("d3"), 70477)
        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).event_coin("d2")

        remounted = make_live_eventsp_map_preparation_backend(
            profile="d3", mount="uiorigin"
        )
        state = make_oracle(remounted).campaign_preparation_state("d3")
        self.assertEqual(state.stage_code, "d3")

        dedicated_hard_node = make_live_eventsp_map_preparation_backend(
            profile="d3"
        )
        for records in (
            dedicated_hard_node.buttons["buttons"],
            dedicated_hard_node.ui["texts"],
            dedicated_hard_node.ui["images"],
        ):
            for record in records:
                record["path"] = record["path"].replace(
                    "Chapter_2050006", "Chapter_2050026"
                )
        state = make_oracle(dedicated_hard_node).campaign_preparation_state("d3")
        self.assertEqual(state.stage_code, "d3")

        mixed = make_live_eventsp_map_preparation_backend(
            profile="d3", mount="uiorigin"
        )
        mixed.buttons["buttons"].append(
            make_button(
                "bg",
                "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/bg",
                raycast_top=None,
            )
        )
        mixed.buttons["button_count"] = len(mixed.buttons["buttons"])
        with self.assertRaisesRegex(SemanticGateClosed, "identity is incomplete"):
            make_oracle(mixed).campaign_preparation_state("d3")

    def test_live_eventb_b3_map_preparation_accepts_exact_stage_profile(self):
        backend = make_live_eventsp_map_preparation_backend(profile="b3")
        state = make_oracle(backend).campaign_preparation_state("b3")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "b3", 10)
        )
        self.assertEqual(backend.taps, [])

        wrong_level = make_live_eventsp_map_preparation_backend(profile="b3")
        for text in wrong_level.ui["texts"]:
            if text["path"].endswith("/panel/Level/Text"):
                text["text"] = "LV 55"
        with self.assertRaisesRegex(SemanticGateClosed, "text value changed"):
            make_oracle(wrong_level).campaign_preparation_state("b3")
        self.assertEqual(wrong_level.taps, [])

    def test_live_eventsp_map_preparation_requires_exact_closed_surface(self):
        backend = make_live_eventsp_map_preparation_backend()
        state = make_oracle(backend).campaign_preparation_state("sp")

        self.assertEqual(
            (state.kind, state.stage_code, state.oil_cost), ("map", "sp", 10)
        )
        self.assertEqual(
            state.cancel_button.path,
            "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)/panel/btnBack",
        )
        self.assertEqual(backend.taps, [])

        view_root = "OverlayCamera/Overlay/UIMain/LevelInfoSPUI(Clone)"
        title_en_path = view_root + "/panel/title_form/title_en"

        def record_groups(candidate):
            return (
                candidate.buttons["buttons"],
                candidate.ui["toggles"],
                candidate.ui["texts"],
                candidate.ui["images"],
            )

        def exact_record(candidate, path, *, group=None):
            groups = record_groups(candidate) if group is None else (group,)
            matches = [
                record
                for records in groups
                for record in records
                if record["path"] == path
            ]
            self.assertTrue(matches, path)
            return matches[0]

        def moved(path, replacement):
            candidate = make_live_eventsp_map_preparation_backend()
            exact_record(candidate, path)["path"] = replacement
            return candidate

        hostiles = {
            "unreviewed-bg-child": moved(
                view_root + "/bg/bottom",
                view_root + "/bg/bottom/extra",
            ),
            "unreviewed-panel-child": moved(
                view_root + "/panel/line",
                view_root + "/panel/line/extra",
            ),
            "arbitrary-sibling": moved(
                view_root + "/panel/line",
                view_root + "/other",
            ),
            "extra-prefix": moved(
                view_root + "/panel/line",
                "extra/" + view_root + "/panel/line",
            ),
            "remount": moved(
                view_root + "/panel/line",
                "Remounted/" + view_root + "/panel/line",
            ),
            "cross-camera": moved(
                view_root + "/panel/line",
                view_root.replace("OverlayCamera", "UICamera") + "/panel/line",
            ),
            "nested-family": moved(
                view_root + "/panel/line",
                view_root + "/Nested/LevelInfoSPUI(Clone)/panel/line",
            ),
            "dot": moved(
                view_root + "/panel/line",
                view_root + "/panel/./line",
            ),
            "dotdot": moved(
                view_root + "/panel/line",
                view_root + "/panel/../line",
            ),
            "case": moved(
                view_root + "/panel/line",
                view_root.upper() + "/PANEL/LINE",
            ),
            "guid": moved(
                view_root + "/panel/line",
                "550e8400-e29b-41d4-a716-446655440000/" + view_root + "/panel/line",
            ),
            "remounted-title-en": moved(
                title_en_path,
                "Remounted/" + title_en_path,
            ),
            "case-title-en": moved(
                title_en_path,
                title_en_path.upper(),
            ),
        }
        missing = make_live_eventsp_map_preparation_backend()
        missing.buttons["buttons"] = [
            item
            for item in missing.buttons["buttons"]
            if item["path"] != view_root + "/panel/start_button"
        ]
        missing.buttons["button_count"] = len(missing.buttons["buttons"])
        hostiles["missing-start-button"] = missing

        missing_image = make_live_eventsp_map_preparation_backend()
        missing_image.ui["images"] = [
            item
            for item in missing_image.ui["images"]
            if item["path"] != view_root + "/panel"
        ]
        missing_image.ui["image_count"] = len(missing_image.ui["images"])
        hostiles["missing-panel-image"] = missing_image

        duplicate = make_live_eventsp_map_preparation_backend()
        duplicate.buttons["buttons"].append(
            copy.deepcopy(
                exact_record(
                    duplicate,
                    view_root + "/panel/btnBack",
                    group=duplicate.buttons["buttons"],
                )
            )
        )
        duplicate.buttons["button_count"] = len(duplicate.buttons["buttons"])
        hostiles["duplicate-back"] = duplicate

        wrong_kind = make_live_eventsp_map_preparation_backend()
        wrong_kind.buttons["buttons"] = [
            item
            for item in wrong_kind.buttons["buttons"]
            if item["path"] != view_root + "/panel/head/Image"
        ]
        wrong_kind.buttons["button_count"] = len(wrong_kind.buttons["buttons"])
        wrong_kind.ui["texts"].append(
            make_text("Image", view_root + "/panel/head/Image")
        )
        wrong_kind.ui["text_count"] = len(wrong_kind.ui["texts"])
        hostiles["wrong-kind"] = wrong_kind

        wrong_sprite = make_live_eventsp_map_preparation_backend()
        exact_record(
            wrong_sprite,
            view_root + "/panel/start_button",
            group=wrong_sprite.ui["images"],
        )["sprite"] = "unreviewed"
        hostiles["wrong-sprite"] = wrong_sprite

        wrong_cost = make_live_eventsp_map_preparation_backend()
        exact_record(
            wrong_cost,
            view_root + "/panel/cost/text",
            group=wrong_cost.ui["texts"],
        )["text"] = "10 "
        hostiles["wrong-exact-cost"] = wrong_cost

        null_bounds_elsewhere = make_live_eventsp_map_preparation_backend()
        exact_record(
            null_bounds_elsewhere,
            view_root + "/panel/cost/text",
            group=null_bounds_elsewhere.ui["texts"],
        )["adb_bounds"] = None
        hostiles["null-bounds-elsewhere"] = null_bounds_elsewhere

        nonempty_title_en = make_live_eventsp_map_preparation_backend()
        exact_record(
            nonempty_title_en,
            title_en_path,
            group=nonempty_title_en.ui["texts"],
        )["text"] = "EN"
        hostiles["nonempty-title-en"] = nonempty_title_en

        duplicate_title_en = make_live_eventsp_map_preparation_backend()
        duplicate_title_en.ui["texts"].append(
            copy.deepcopy(
                exact_record(
                    duplicate_title_en,
                    title_en_path,
                    group=duplicate_title_en.ui["texts"],
                )
            )
        )
        duplicate_title_en.ui["text_count"] = len(duplicate_title_en.ui["texts"])
        hostiles["duplicate-title-en"] = duplicate_title_en

        missing_title_en = make_live_eventsp_map_preparation_backend()
        missing_title_en.ui["texts"] = [
            item
            for item in missing_title_en.ui["texts"]
            if item["path"] != title_en_path
        ]
        missing_title_en.ui["text_count"] = len(missing_title_en.ui["texts"])
        hostiles["missing-title-en"] = missing_title_en

        wrong_kind_title_en = make_live_eventsp_map_preparation_backend()
        wrong_kind_title_en.ui["texts"] = [
            item
            for item in wrong_kind_title_en.ui["texts"]
            if item["path"] != title_en_path
        ]
        wrong_kind_title_en.ui["text_count"] = len(wrong_kind_title_en.ui["texts"])
        wrong_kind_title_en.ui["images"].append(make_image(title_en_path, "empty"))
        wrong_kind_title_en.ui["image_count"] = len(wrong_kind_title_en.ui["images"])
        hostiles["wrong-kind-title-en"] = wrong_kind_title_en

        multiplicity = make_live_eventsp_map_preparation_backend()
        multiplicity.ui["images"].append(
            copy.deepcopy(
                exact_record(
                    multiplicity,
                    view_root + "/panel/drops/frame/list/item(Clone)/icon_bg/icon",
                    group=multiplicity.ui["images"],
                )
            )
        )
        multiplicity.ui["image_count"] = len(multiplicity.ui["images"])
        hostiles["multiplicity-abuse"] = multiplicity

        duplicate_root = make_live_eventsp_map_preparation_backend()
        baseline = make_event_preparation_backend("sp", kind="map")
        duplicate_root.buttons["buttons"].extend(baseline.buttons["buttons"])
        duplicate_root.buttons["button_count"] = len(duplicate_root.buttons["buttons"])
        duplicate_root.ui["texts"].extend(baseline.ui["texts"])
        duplicate_root.ui["text_count"] = len(duplicate_root.ui["texts"])
        hostiles["duplicate-view-root"] = duplicate_root

        for case, candidate in hostiles.items():
            with self.subTest(case=case):
                with self.assertRaises(SemanticGateClosed):
                    make_oracle(candidate).campaign_preparation_state("sp")
                adapter = AlasSemanticAdapter(make_oracle(candidate), lambda: None)
                adapter.begin_campaign_pre_sortie("sp")
                context = adapter._campaign_context
                context_before = dict(vars(context))
                ledger_before = dict(adapter._action_ledger._remaining)
                for operation in (
                    lambda: adapter.appear(SimpleNamespace(name="EVENT_CHECK")),
                    lambda: adapter.appear(SimpleNamespace(name="MAP_PREPARATION")),
                    lambda: adapter.click(
                        SimpleNamespace(name="MAP_PREPARATION_CANCEL")
                    ),
                ):
                    with self.assertRaises(SemanticGateClosed):
                        operation()
                    self.assertEqual(candidate.taps, [])
                    self.assertEqual(vars(context), context_before)
                    self.assertEqual(adapter._action_ledger._remaining, ledger_before)
                adapter.end_campaign_pre_sortie()

    def test_campaign_preparation_accepts_only_exact_live_eventsp_roots(self):
        view_root = "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)"
        fleet_root = (
            "OverlayCamera/Overlay/UIMain/"
            "LevelFleetSelectView(Clone)/panel/"
        )
        stage_root = (
            "UICamera/Canvas/UIMain/LevelMainScene(Clone)/"
            "LevelSelectSPFullUI(Clone)/"
        )
        baseline_stage_root = (
            "root/UICamera/Canvas/UIMain/LevelSelectSPFullUI(Clone)/"
        )

        def rewrite(backend, old_root, new_root):
            for button in backend.buttons["buttons"]:
                if button["path"].startswith(old_root):
                    button["path"] = new_root + button["path"][len(old_root) :]
            for group in ("texts", "toggles", "images"):
                for item in backend.ui[group]:
                    if item["path"].startswith(old_root):
                        item["path"] = new_root + item["path"][len(old_root) :]

        def rewrite_exact(backend, old_path, new_path):
            for record in (
                *backend.buttons["buttons"],
                *backend.ui["texts"],
                *backend.ui["toggles"],
                *backend.ui["images"],
            ):
                if record["path"] == old_path:
                    record["path"] = new_path

        backend = make_live_eventsp_fleet_preparation_backend()
        preparation = make_oracle(backend).campaign_preparation_state("sp")
        self.assertIsNotNone(preparation)
        self.assertEqual(preparation.kind, "fleet")
        self.assertEqual(preparation.stage_code, "sp")
        self.assertEqual(
            preparation.cancel_button.path,
            fleet_root + "Fixed/btnBack",
        )
        self.assertEqual(backend.taps, [])

        mixed = {
            "live-overlay-baseline-underlay": (
                make_live_eventsp_fleet_preparation_backend(),
                stage_root,
                baseline_stage_root,
            ),
            "baseline-overlay-live-underlay": (
                make_event_preparation_backend("sp", kind="fleet"),
                baseline_stage_root,
                stage_root,
            ),
        }
        for case, (backend, old_root, new_root) in mixed.items():
            with self.subTest(case=case):
                rewrite(backend, old_root, new_root)
                with self.assertRaisesRegex(
                    SemanticGateClosed, "not a reviewed pair"
                ):
                    make_oracle(backend).campaign_preparation_state("sp")
                self.assertEqual(backend.taps, [])

        anchor_hostiles = {
            "arbitrary-sibling": (view_root + "/bg", view_root + "/other"),
            "deeper-bg": (view_root + "/bg", view_root + "/bg/Nested"),
            "deeper-panel": (
                view_root + "/panel",
                view_root + "/Nested/panel",
            ),
            "remount": (
                view_root + "/bg",
                "Remounted/" + view_root + "/bg",
            ),
            "cross-root": (view_root + "/bg", "root/" + view_root + "/bg"),
            "dot": (view_root + "/bg", view_root + "/./bg"),
            "dotdot": (view_root + "/bg", view_root + "/../bg"),
            "case": (view_root + "/bg", view_root.upper() + "/BG"),
            "guid": (
                view_root + "/bg",
                "550e8400-e29b-41d4-a716-446655440000/"
                + view_root
                + "/bg",
            ),
        }
        for case, (old_path, new_path) in anchor_hostiles.items():
            with self.subTest(anchor=case):
                backend = make_live_eventsp_fleet_preparation_backend()
                rewrite_exact(backend, old_path, new_path)
                with self.assertRaises(SemanticGateClosed):
                    make_oracle(backend).campaign_preparation_state("sp")
                self.assertEqual(backend.taps, [])

        hostile_fleet_roots = (
            "extra/" + fleet_root,
            "Mirror/" + fleet_root,
            "550e8400-e29b-41d4-a716-446655440000/" + fleet_root,
            fleet_root.upper(),
            fleet_root.replace("UIMain/Level", "UIMain/Nested/Level"),
            fleet_root.replace("UIMain/Level", "UIMain/./Level"),
            fleet_root.replace("UIMain/Level", "UIMain/../Level"),
            fleet_root + "Nested/",
        )
        for hostile in hostile_fleet_roots:
            with self.subTest(surface="fleet", hostile=hostile):
                backend = make_live_eventsp_fleet_preparation_backend()
                rewrite(backend, fleet_root, hostile)
                with self.assertRaises(SemanticGateClosed):
                    make_oracle(backend).campaign_preparation_state("sp")
                self.assertEqual(backend.taps, [])

        hostile_stage_roots = (
            "root/" + stage_root,
            "extra/" + stage_root,
            "Mirror/" + stage_root,
            "550e8400-e29b-41d4-a716-446655440000/" + stage_root,
            stage_root.upper(),
            stage_root.replace("UIMain/Level", "UIMain/Nested/Level"),
            stage_root.replace("UIMain/Level", "UIMain/./Level"),
            stage_root.replace("UIMain/Level", "UIMain/../Level"),
            stage_root.replace("LevelMainScene(Clone)/", ""),
        )
        for hostile in hostile_stage_roots:
            with self.subTest(surface="underlay", hostile=hostile):
                backend = make_live_eventsp_fleet_preparation_backend()
                rewrite(backend, stage_root, hostile)
                with self.assertRaises(SemanticGateClosed):
                    make_oracle(backend).campaign_preparation_state("sp")
                self.assertEqual(backend.taps, [])

        duplicate = make_live_eventsp_fleet_preparation_backend()
        baseline = make_event_preparation_backend("sp", kind="fleet")
        duplicate.buttons["buttons"].extend(baseline.buttons["buttons"])
        duplicate.buttons["button_count"] = len(duplicate.buttons["buttons"])
        duplicate.ui["texts"].extend(baseline.ui["texts"])
        duplicate.ui["text_count"] = len(duplicate.ui["texts"])
        with self.assertRaisesRegex(SemanticGateClosed, "ambiguous"):
            make_oracle(duplicate).campaign_preparation_state("sp")
        self.assertEqual(duplicate.taps, [])

    def test_campaign_auto_search_requires_owned_battle_surface_not_map_root(self):
        backend = FakeBackend([])
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/LevelCamera/Canvas/UIMain/LevelGrid/"
                    "DragLayer/plane/display/mask/sea",
                    "sea_day",
                )
            ],
        )

        with self.assertRaisesRegex(
            SemanticTargetMissing, "official auto-search surface is absent"
        ):
            make_oracle(backend).campaign_auto_search_active_state()

        combat_root = (
            "root/UICamera/Canvas/UIMain/CombatUIStandard(Clone)/AutoBtn"
        )
        result_root = (
            "root/UICamera/Canvas/UIMain/NewBattleResultEmptyUI(Clone)/Main"
        )
        backend.ui = make_ui(
            [
                make_text("自动", combat_root + "/Text"),
                make_text("战斗结果", result_root + "/Text"),
            ],
            generation=20,
        )
        with self.assertRaisesRegex(
            SemanticGateClosed, "official auto-search surface is ambiguous"
        ):
            make_oracle(backend).campaign_auto_search_active_state()

        backend.ui = make_ui(
            [make_text("自动", combat_root + "/Text")],
            generation=21,
        )
        active = make_oracle(backend).campaign_auto_search_active_state()
        self.assertEqual(active.generation, 21)
        self.assertEqual(
            active.root_path,
            "root/UICamera/Canvas/UIMain/CombatUIStandard(Clone)",
        )

        backend.ui = make_ui(
            [make_text("自动", combat_root + "/Text")],
            generation=True,
        )
        with self.assertRaisesRegex(SemanticGateClosed, "invalid integer field"):
            make_oracle(backend).campaign_auto_search_active_state()
