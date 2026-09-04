"""Rewards regression cases for the oracle."""

import copy
import unittest
from alas_headless.semantic_oracle import Point, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
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


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_free_weekly_supply_pack_click_excludes_paid_cards(self):
        root = "OverlayCamera/Overlay/UIMain/"
        free = root + "ChargeGiftShopUI(Clone)/lScrollRect/content/0"
        paid = root + "ChargeGiftShopUI(Clone)/lScrollRect/content/1"
        backend = FakeBackend(
            [
                make_button("homeBtn", root + "buttonList/top/homeBtn"),
                make_button("closeBtn", root + "buttonList/top/closeBtn"),
                make_button("0", free, x=300, y=350, raycast_top=None),
                make_button("1", paid, x=500, y=350, raycast_top=None),
            ]
        )
        toggle = make_toggle(
            root + "buttonList/shop1List/giftPackShop/shop1Tg",
            checked=True,
            raycast_top=None,
        )
        backend.ui = make_ui(
            [
                make_text("商店", root + "buttonList/top/title/Text"),
                make_text(
                    "全部",
                    root
                    + "ChargeGiftShopUI(Clone)/toggleGroup/Toggle/selected/Label",
                ),
                make_text("每周免费礼包", free + "/real_tpl/item_name_mask/item_name"),
                make_text("0", free + "/real_tpl/Price/Text"),
                make_text("限时礼包", paid + "/real_tpl/item_name_mask/item_name"),
                make_text("300", paid + "/real_tpl/Price/Text"),
            ],
            toggles=[toggle],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.free_weekly_supply_pack_available())
        receipt = oracle.click_free_weekly_supply_pack()

        self.assertEqual(receipt.semantic_id, "shop/free-weekly-pack")
        self.assertEqual(backend.taps, [(300, 350)])
        self.assertNotIn((500, 350), backend.taps)

    def test_new_ship_reward_requires_coherent_typed_identity_and_clicks(self):
        root = "root/UICamera/Canvas/UIOrigin/NewShipUI(Clone)/shake_panel/"
        backend = FakeBackend(
            [
                make_button(
                    "click",
                    root + "click",
                    bounds={
                        "left": 0.0,
                        "top": 0.0,
                        "right": 1280.0,
                        "bottom": 720.0,
                    },
                ),
                make_button("property_btn", root + "property_btn", x=1096, y=620),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("西弗吉尼亚", root + "ship_type/name_bg/mask/Text"),
                make_text("USS West Virginia", root + "ship_type/english_name"),
                make_text("终于到我展现力量的时候了吗", root + "dialogue/Text"),
                make_text("战列", root + "dialogue/bg/type"),
                make_text("西弗吉尼亚", root + "dialogue/bg/name"),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.new_ship_reward_visible())
        self.assertTrue(oracle.enabled("reward/new-ship/continue"))
        receipt = oracle.click("reward/new-ship/continue")

        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_new_ship_reward_fails_closed_on_name_overlay_or_raycast_mismatch(self):
        root = "root/UICamera/Canvas/UIOrigin/NewShipUI(Clone)/shake_panel/"
        full_screen = {
            "left": 0.0,
            "top": 0.0,
            "right": 1280.0,
            "bottom": 720.0,
        }
        button = make_button("click", root + "click", bounds=full_screen)
        texts = [
            make_text("舰船甲", root + "ship_type/name_bg/mask/Text"),
            make_text("Ship A", root + "ship_type/english_name"),
            make_text("对白", root + "dialogue/Text"),
            make_text("驱逐", root + "dialogue/bg/type"),
            make_text("舰船乙", root + "dialogue/bg/name"),
        ]
        backend = FakeBackend([button])
        backend.ui = make_ui(texts)
        oracle = make_oracle(backend)
        self.assertFalse(oracle.enabled("reward/new-ship/continue"))

        backend.ui["texts"][-1]["text"] = "舰船甲"
        backend.buttons = make_buttons(
            [
                button,
                make_button(
                    "custom_button_1(Clone)",
                    "root/Overlay/UIMain/Msgbox(Clone)/window/button_container/"
                    "custom_button_1(Clone)",
                ),
            ]
        )
        self.assertFalse(oracle.enabled("reward/new-ship/continue"))

        covered = copy.deepcopy(button)
        covered["raycast_top"] = None
        backend.buttons = make_buttons([covered])
        self.assertFalse(oracle.enabled("reward/new-ship/continue"))
        with self.assertRaisesRegex(SemanticGateClosed, "identity is not proven"):
            oracle.click("reward/new-ship/continue")
        self.assertEqual(backend.taps, [])

    def test_new_ship_reward_accepts_current_dialogue_background_when_click_image_is_lossy(self):
        root = "root/OverlayCamera/Overlay/UIMain/NewShipUI(Clone)/shake_panel/"
        full_screen = {"left": 0.0, "top": 0.0, "right": 1280.0, "bottom": 720.0}
        backend = FakeBackend(
            [
                make_button(
                    "click",
                    root + "click",
                    bounds=full_screen,
                    raycast_top=None,
                )
            ]
        )
        dialogue_background = make_image(
            root + "dialogue/bg", "liaotian04", bounds=full_screen
        )
        backend.ui = make_ui(
            [
                make_text("博伊西", root + "ship_type/name_bg/mask/Text"),
                make_text("USS Boise", root + "ship_type/english_name"),
                make_text("请问，有什么能为您做的吗？", root + "dialogue/Text"),
                make_text("轻巡", root + "dialogue/bg/type"),
                make_text("博伊西", root + "dialogue/bg/name"),
            ],
            images=[dialogue_background],
            generation=14,
        )
        oracle = make_oracle(backend)

        receipt = oracle.click("reward/new-ship/continue")
        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_new_ship_reward_retries_incoherent_transition_before_click(self):
        root = "root/OverlayCamera/Overlay/UIMain/NewShipUI(Clone)/shake_panel/"
        full_screen = {"left": 0.0, "top": 0.0, "right": 1280.0, "bottom": 720.0}
        button = make_button(
            "click", root + "click", bounds=full_screen, raycast_top=None
        )
        dialogue_background = make_image(
            root + "dialogue/bg", "liaotian04", bounds=full_screen
        )
        texts = [
            make_text("博伊西", root + "ship_type/name_bg/mask/Text"),
            make_text("USS Boise", root + "ship_type/english_name"),
            make_text("请问，有什么能为您做的吗？", root + "dialogue/Text"),
            make_text("轻巡", root + "dialogue/bg/type"),
            make_text("博伊西", root + "dialogue/bg/name"),
        ]
        backend = FakeBackend([button])
        backend.snapshot = make_snapshot(generation=13)
        backend.buttons = make_buttons([button], generation=13)
        backend.ui = make_ui(texts, images=[dialogue_background], generation=13)
        backend.snapshot_sequence = [
            make_snapshot(generation=10),
            make_snapshot(generation=13),
        ]
        backend.buttons_sequence = [
            make_buttons([button], generation=10),
            make_buttons([button], generation=13),
        ]
        backend.ui_sequence = [
            make_ui(texts, images=[dialogue_background], generation=7),
            make_ui(texts, images=[dialogue_background], generation=13),
        ]
        oracle = make_oracle(backend)

        receipt = oracle.click("reward/new-ship/continue")

        self.assertEqual(receipt.semantic_id, "reward/new-ship/continue")
        self.assertEqual(receipt.generation, 13)
        self.assertEqual(backend.taps, [(640, 360)])

    def test_reward_summary_counter_requires_exact_typed_page_identity(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                    827,
                    622,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "3",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/counter/finished/Text",
                )
            ]
        )

        self.assertEqual(
            make_oracle(backend).reward_summary_count("commission", "finished"),
            3,
        )

    def test_reward_resource_requires_an_exact_positive_typed_amount(self):
        page = "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)"
        bubble = page + "/frame/resources/canteen/bubble"
        backend = FakeBackend(
            [
                make_button("CommissionInfoUI4Mellow(Clone)", page, 827, 622),
                make_button("bubble", bubble, 142, 67),
            ]
        )
        backend.ui = make_ui([make_text("32", bubble + "/Text")])
        oracle = make_oracle(backend)

        self.assertEqual(oracle.reward_resource_amount("oil"), 32)
        self.assertTrue(oracle.reward_resource_available("oil"))
        receipt = oracle.click_reward_resource("oil")

        self.assertEqual(receipt.semantic_id, "reward/resource/oil")
        self.assertEqual(backend.taps, [(142, 67)])

    def test_reward_resource_zero_requires_the_exact_resource_card(self):
        page = "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)"
        backend = FakeBackend(
            [make_button("CommissionInfoUI4Mellow(Clone)", page, 827, 622)]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    page + "/frame/resources/canteen",
                    "icon_oil",
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.reward_resource_amount("oil"), 0)
        self.assertFalse(oracle.reward_resource_available("oil"))
        with self.assertRaisesRegex(SemanticGateClosed, "no collectible amount"):
            oracle.click_reward_resource("oil")
        self.assertEqual(backend.taps, [])

    def test_reward_summary_retries_a_transitional_counter_frame(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                )
            ]
        )
        backend.ui_sequence = [
            make_ui([], generation=10),
            make_ui(
                [
                    make_text(
                        "1",
                        "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                        "event/frame/counter/finished/Text",
                    )
                ],
                generation=11,
            ),
        ]

        self.assertEqual(
            make_oracle(backend).reward_summary_count("commission", "finished"),
            1,
        )

    def test_reward_summary_zero_requires_exact_section_frame(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                )
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "class/frame",
                    "frame_class",
                )
            ],
        )

        self.assertEqual(
            make_oracle(backend).reward_summary_count("tactical", "ongoing"),
            0,
        )

    def test_reward_go_button_is_distinct_from_finish_button(self):
        backend = FakeBackend(
            [
                make_button(
                    "CommissionInfoUI4Mellow(Clone)",
                    "root/Overlay/UIMain/CommissionInfoUI4Mellow(Clone)",
                    827,
                    622,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                ),
                make_button(
                    "go_btn",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/go_btn",
                    465,
                    294,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.exists("reward/commission/finish"))
        self.assertTrue(oracle.enabled("reward/commission/go"))

    def test_archive_page_allows_only_exact_reward_close_to_cross_owner(self):
        backend = FakeBackend(
            [
                make_button(
                    "close",
                    "OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close",
                    1100,
                    120,
                ),
                make_button(
                    "EX",
                    "UICamera/Canvas/UIOrigin/LevelRemasterView(Clone)/toggles/EX",
                ),
                make_button(
                    "btn_remaster",
                    "UICamera/Canvas/UIMain/LevelMainScene(Clone)/entrance/btns/btn_remaster",
                ),
            ]
        )
        oracle = make_oracle(backend)
        state = oracle.read_state()

        self.assertEqual(
            oracle._blocking_rules(state, "reward/award-info/close"), ()
        )
        self.assertEqual(
            tuple(
                rule.blocker_id
                for rule in oracle._blocking_rules(state, "main/settings")
            ),
            ("award-info", "campaign-menu", "archive-page"),
        )

    def test_ship_exp_blocks_reward_page_but_allows_exact_skip_layer(self):
        backend = FakeBackend(
            [
                make_button(
                    "finish_btn",
                    "root/CommissionInfoUI4Mellow(Clone)/frame/main/content/"
                    "event/frame/finish_btn",
                    465,
                    294,
                ),
                make_button(
                    "skipLayer",
                    "root/ShipExpUI(Clone)/skipLayer",
                    640,
                    360,
                    {"left": 0, "top": 0, "right": 1280, "bottom": 720},
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("reward/commission"))
        self.assertTrue(oracle.enabled("reward/ship-exp/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("reward/commission")
        receipt = oracle.click("reward/ship-exp/close")

        self.assertEqual(receipt.path, "root/ShipExpUI(Clone)/skipLayer")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_weekly_progress_claim_requires_selected_typed_reward_control(self):
        root = "root/TaskScene(Clone)"
        button_path = root + "/pages/TaskListForWeekPage(Clone)/task_progress/get_btn"
        bounds = {"left": 1094, "top": 64, "right": 1247, "bottom": 218}
        backend = FakeBackend(
            [
                make_button(
                    "back_btn", root + "/blur_panel/adapt/top/back_btn", 58, 53
                ),
                make_button(
                    "get_btn", button_path, 1094, 64, bounds, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [],
            images=[
                make_image(
                    root
                    + "/blur_panel/adapt/left_length/frame/tagRoot/weekly/"
                    "selected/Image",
                    "icon_week_sel",
                ),
                make_image(button_path, "get_btn", bounds),
                make_image(
                    button_path + "/enable",
                    "finish_btn_tran_1",
                    {"left": 1191, "top": 69, "right": 1247, "bottom": 125},
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.weekly_mission_progress_claim_available())
        receipt = oracle.click_weekly_mission_progress_claim()

        self.assertEqual(receipt.semantic_id, "task/weekly-progress/claim")
        self.assertEqual(receipt.point, Point(1170.5, 141.0))
        self.assertEqual(backend.taps, [(1170, 141)])
