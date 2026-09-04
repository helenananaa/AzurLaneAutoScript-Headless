"""Retirement regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import (
    RetirementNoCandidateReceipt,
    SemanticGateClosed,
)
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_snapshot,
    make_text,
    make_ui,
    set_retirement_selection,
    set_retirement_settings,
)


class RetirementSemanticOracleTests(unittest.TestCase):
    def test_retirement_settings_tolerate_unrelated_global_toggle_cap(self):
        backend = FakeBackend([])
        set_retirement_settings(backend, 20, keep_needed=True)

        state = make_oracle(backend).retirement_settings_state()

        self.assertTrue(state.unique_ship_protection)
        self.assertEqual(state.priority, ("R", "SR", "N"))
        self.assertEqual(state.full_star_policy, "keep_none")
        self.assertEqual(state.no_full_star_policy, "keep_needed")

    def test_retirement_settings_require_every_exact_protection_toggle(self):
        backend = FakeBackend([])
        set_retirement_settings(backend, 20, keep_needed=True)
        backend.ui["toggles"] = [
            item
            for item in backend.ui["toggles"]
            if not item["path"].endswith("notify_tpl_0/on")
        ]
        backend.ui["toggle_count"] = len(backend.ui["toggles"])

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).retirement_settings_state()

    def test_official_no_candidate_tip_survives_exact_network_reconnect(self):
        backend = FakeBackend([])
        stages = []

        def stage_selection(generation):
            set_retirement_selection(backend, generation, 814)

        def stage_settings(generation):
            set_retirement_settings(backend, generation, keep_needed=True)

        def stage_network(generation):
            root = "root/Overlay/UIMain/Msgbox(Clone)/window/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "custom_button_2(Clone)",
                        root + "button_container/custom_button_2(Clone)",
                    ),
                    make_button(
                        "custom_button_1(Clone)",
                        root + "button_container/custom_button_1(Clone)",
                    ),
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text(
                        "服务器连接失败，是否重新连接？\n[NetworkDown]",
                        root + "msg_panel/content",
                    ),
                    make_text(
                        "取 消",
                        root + "button_container/custom_button_2(Clone)/pic",
                    ),
                    make_text(
                        "确 定",
                        root + "button_container/custom_button_1(Clone)/pic",
                    ),
                ],
                generation=generation,
            )

        def stage_no_candidate(generation):
            set_retirement_selection(backend, generation, 814)
            backend.ui["texts"].append(
                make_text(
                    "<color=white>没找到符合条件的舰船</color>",
                    "root/OverlayCamera/Overlay/UIOverlay/TipPanel(Clone)/Grid/"
                    "toolTip(Clone)/Text",
                )
            )
            backend.ui["text_count"] = len(backend.ui["texts"])

        stages.extend(
            [
                lambda: stage_selection(20),
                lambda: stage_settings(21),
                lambda: stage_selection(22),
                lambda: stage_network(23),
                lambda: stage_no_candidate(24),
            ]
        )
        stage_index = 0
        stages[stage_index]()

        def advance():
            nonlocal stage_index
            stage_index += 1
            stages[stage_index]()

        backend.on_tap = advance
        receipt = make_oracle(backend).retire_ships_one_click(True)

        self.assertIsInstance(receipt, RetirementNoCandidateReceipt)
        assert isinstance(receipt, RetirementNoCandidateReceipt)
        self.assertEqual((receipt.capacity_used, receipt.capacity_total), (814, 910))
        self.assertEqual(
            receipt.official_message,
            "<color=white>没找到符合条件的舰船</color>",
        )
        self.assertEqual(
            tuple(action.semantic_id for action in receipt.actions),
            (
                "retirement/settings/open",
                "retirement/settings/close",
                "retirement/one-click",
                "overlay/network-reconnect/confirm",
            ),
        )
        self.assertEqual(stage_index, 4)
        self.assertEqual(len(backend.taps), 4)

    def test_official_retirement_transaction_uses_real_count_and_keeps_equipment(self):
        backend = FakeBackend([])
        stages = []

        def stage_selection(generation, used):
            set_retirement_selection(backend, generation, used)

        def stage_settings(generation):
            set_retirement_settings(backend, generation, keep_needed=True)

        def stage_preconfirm(generation):
            root = "root/UICamera/Canvas/UIOrigin/DestoryInfoUI(Clone)/frame/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "confirm_button",
                        root + "confirm_button",
                        1014,
                        649,
                        raycast_top=None,
                    )
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text("确 定", root + "confirm_button/pic"),
                    make_text("信息", root + "top/title_list/infomation/title"),
                    make_text(
                        "68",
                        "root/UICamera/Canvas/UIOrigin/blur_panel/select_panel/"
                        "bottom_info/bg_input/count",
                    ),
                ],
                generation=generation,
            )

        def stage_warning(generation):
            root = (
                "root/OverlayCamera/Overlay/UIMain/DestoryConfirmWindow(Clone)/window/"
            )
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "confirm_btn", root + "confirm_btn", 793, 505, raycast_top=None
                    )
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text(
                        "选择角色中有<color=#92fc63>精锐以上</color>的角色：",
                        root + "content/Text",
                    ),
                    make_text("是否确认", root + "content/desc/label"),
                ],
                generation=generation,
            )

        def stage_award(generation):
            root = "root/OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/"
            item = root + "items_scroll/content/item_tpl(Clone)/bg/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [make_button("close", root + "close", 640, 482, raycast_top=None)],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text("荣誉勋章", item + "name_mask/name"),
                    make_text("22", item + "icon_bg/count"),
                    make_text("物资", item + "name_mask/name"),
                    make_text("1026", item + "icon_bg/count"),
                ],
                generation=generation,
            )

        def stage_equipment(generation, selected):
            root = "root/OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/main/"
            buttons = [
                make_button(
                    "cancel_btn", root + "cancel_btn", 844, 606, raycast_top=None
                ),
                make_button("ALL", root + "options/ALL", 200, 601, raycast_top=None),
                make_button(
                    "0", root + "frame/view/content/0", 218, 187, raycast_top=None
                ),
                make_button(
                    "1", root + "frame/view/content/1", 336, 187, raycast_top=None
                ),
            ]
            if selected:
                buttons.extend(
                    [
                        make_button(
                            "reduce",
                            root + "frame/view/content/0/frame/bg/selected/reduce",
                            250,
                            156,
                            raycast_top=None,
                        ),
                        make_button(
                            "reduce",
                            root + "frame/view/content/1/frame/bg/selected/reduce",
                            368,
                            156,
                            raycast_top=None,
                        ),
                    ]
                )
            images = []
            if selected:
                images.append(
                    make_image(root + "options/ALL/Background/Checkmark", "toggle_on")
                )
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(buttons, generation=generation)
            backend.ui = make_ui(
                [
                    make_text(
                        "请选择需要拆解的装备，未选的装备将放入仓库",
                        root + "title/Text",
                    ),
                    make_text("取 消", root + "cancel_btn/Image"),
                    make_text("全部", root + "options/ALL/Label"),
                    make_text(
                        "11", root + "frame/view/content/0/frame/bg/icon_bg/count"
                    ),
                    make_text(
                        "6", root + "frame/view/content/1/frame/bg/icon_bg/count"
                    ),
                ],
                images=images,
                generation=generation,
            )
            backend.ui["image_truncated"] = True

        def stage_preserve_confirm(generation):
            root = "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "custom_button_1(Clone)",
                        root + "button_container/custom_button_1(Clone)",
                        790,
                        515,
                        raycast_top=None,
                    )
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text(
                        "不进行任何操作，所有装备会放入"
                        "<color=#5f984d>仓库</color>\n是否退出？",
                        root + "msg_panel/content",
                    )
                ],
                generation=generation,
            )

        stages.extend(
            [
                lambda: stage_selection(20, 882),
                lambda: stage_settings(21),
                lambda: stage_selection(22, 882),
                lambda: stage_preconfirm(23),
                lambda: stage_warning(24),
                lambda: stage_award(25),
                lambda: stage_equipment(26, True),
                lambda: stage_equipment(27, False),
                lambda: stage_preserve_confirm(28),
                lambda: stage_selection(29, 814),
            ]
        )
        stage_index = 0
        stages[stage_index]()

        def advance():
            nonlocal stage_index
            stage_index += 1
            stages[stage_index]()

        backend.on_tap = advance
        receipt = make_oracle(backend).retire_ships_one_click(True)

        self.assertIsNotNone(receipt)
        assert receipt is not None
        self.assertEqual(receipt.retired_count, 68)
        self.assertEqual((receipt.capacity_before, receipt.capacity_after), (882, 814))
        self.assertEqual(receipt.rewards, (("物资", 1026), ("荣誉勋章", 22)))
        self.assertTrue(receipt.rarity_warning_confirmed)
        self.assertTrue(receipt.equipment_preserved)
        self.assertEqual(stage_index, 9)
        self.assertEqual(len(backend.taps), 9)
