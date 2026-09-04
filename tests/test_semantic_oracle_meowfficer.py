"""Meowfficer regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import Point, SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_image,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_meowfficer_dock_state_uses_exact_typed_counters(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/box/"
        backend = FakeBackend(
            [
                make_button("back_btn", root + "top/back_btn", raycast_top=None),
                make_button("home", dock + "home", 870, 622, raycast_top=None),
                make_button(
                    "reserve_btn", dock + "reserve_btn", 1032, 622, raycast_top=None
                ),
                make_button(
                    "boxes_btn", dock + "boxes_btn", 1185, 622, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", dock + "home/Text"),
                make_text("1/10", dock + "boxes_btn/Text"),
                make_text("15/15", dock + "reserve_btn/Text"),
                make_text("34/40", dock + "capcity/Text"),
                make_text("707", root + "top/res/gold/Text"),
                make_text("2205", root + "top/res/1/Text"),
                make_text("1531", root + "top/res/2/Text"),
                make_text("479", root + "top/res/3/Text"),
            ]
        )

        state = make_oracle(backend).meowfficer_dock_state()

        self.assertEqual(state.purchased, 15)
        self.assertEqual(state.purchase_total, 15)
        self.assertEqual(state.coins, 707)
        self.assertEqual(state.capacity_used, 34)
        self.assertEqual(state.capacity_total, 40)
        self.assertEqual(state.fort_current, 0)
        self.assertEqual(state.training_finished, 1)
        self.assertEqual(state.box_counts, (2205, 1531, 479))

    def test_meowfficer_back_uses_visible_part_of_clipped_button(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/box/"
        backend = FakeBackend(
            [
                make_button(
                    "back_btn",
                    root + "top/back_btn",
                    -14,
                    0,
                    bounds={"left": -14, "top": 0, "right": 90, "bottom": 78},
                    raycast_top=None,
                ),
                make_button("home", dock + "home", 870, 622, raycast_top=None),
                make_button(
                    "reserve_btn", dock + "reserve_btn", 1032, 622, raycast_top=None
                ),
                make_button(
                    "boxes_btn", dock + "boxes_btn", 1185, 622, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", dock + "home/Text"),
                make_text("1/10", dock + "boxes_btn/Text"),
                make_text("15/15", dock + "reserve_btn/Text"),
                make_text("34/40", dock + "capcity/Text"),
                make_text("707", root + "top/res/gold/Text"),
                make_text("2205", root + "top/res/1/Text"),
                make_text("1531", root + "top/res/2/Text"),
                make_text("479", root + "top/res/3/Text"),
            ]
        )

        receipt = make_oracle(backend).click("meowfficer/page/back")

        self.assertEqual(receipt.point, Point(45.0, 39.0))
        self.assertEqual(backend.taps, [(45, 39)])

    def test_meowfficer_dock_rejects_malformed_purchase_counter(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/box/"
        backend = FakeBackend(
            [
                make_button("home", dock + "home", 870, 622, raycast_top=None),
                make_button(
                    "reserve_btn", dock + "reserve_btn", 1032, 622, raycast_top=None
                ),
                make_button(
                    "boxes_btn", dock + "boxes_btn", 1185, 622, raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", dock + "home/Text"),
                make_text("1/10", dock + "boxes_btn/Text"),
                make_text("已满", dock + "reserve_btn/Text"),
                make_text("34/40", dock + "capcity/Text"),
                make_text("707", root + "top/res/gold/Text"),
                make_text("2205", root + "top/res/1/Text"),
                make_text("1531", root + "top/res/2/Text"),
                make_text("479", root + "top/res/3/Text"),
            ]
        )

        with self.assertRaisesRegex(SemanticGateClosed, "purchase"):
            make_oracle(backend).meowfficer_dock_state()

    def test_meowfficer_training_state_uses_exact_typed_counters(self):
        root = "root/OverlayCamera/Overlay/UIMain/CommanderBoxesUI(Clone)/frame/"
        boxes = root + "boxes/"
        backend = FakeBackend(
            [
                make_button("close_btn", root + "close_btn", raycast_top=None),
                make_button("finish_btn", boxes + "finish_btn", raycast_top=None),
                make_button("start_btn", boxes + "start_btn", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("4/4", boxes + "statistics/traning"),
                make_text("6/6", boxes + "statistics/wait"),
            ]
        )

        state = make_oracle(backend).meowfficer_training_state()

        self.assertEqual(state.active_training, 4)
        self.assertEqual(state.active_capacity, 4)
        self.assertEqual(state.waiting, 6)
        self.assertEqual(state.waiting_capacity, 6)
        self.assertEqual(state.completed, 0)

    def test_meowfficer_purchase_state_uses_asset_derived_exact_paths(self):
        root = "root/OverlayCamera/Overlay/UIMain/CommanderReserveUI(Clone)/frame/"
        controls = root + "bg1/"
        backend = FakeBackend(
            [
                make_button("min", controls + "count/min", raycast_top=None),
                make_button("add", controls + "count/add", raycast_top=None),
                make_button("max", controls + "max", raycast_top=None),
                make_button("Button", controls + "Button", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("3", controls + "count/Text"),
                make_text("3000", controls + "price_all/Text"),
            ]
        )
        oracle = make_oracle(backend)

        state = oracle.meowfficer_purchase_state()

        self.assertEqual(state.generation, 10)
        self.assertEqual(state.count, 3)
        self.assertEqual(state.total_price, 3000)
        self.assertTrue(oracle.enabled("meowfficer/buy/submit"))

    def test_meowfficer_purchase_prompt_is_scoped_to_reserve_ui(self):
        root = (
            "root/OverlayCamera/Overlay/UIMain/CommanderReserveUI(Clone)/"
            "CommanderMsgBoxUI(Clone)/frame/"
        )
        backend = FakeBackend(
            [
                make_button("cancel_btn", root + "cancel_btn", raycast_top=None),
                make_button("confirm_btn", root + "confirm_btn", raycast_top=None),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("meowfficer/buy/cancel"))
        self.assertTrue(oracle.enabled("meowfficer/buy/confirm"))

    def test_meowfficer_dock_cats_use_exact_card_bounds_and_selection(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/"
        box = dock + "box/"
        card = dock + "frame/content/ComanderCatTpl/info/"
        first_bounds = {"left": 680, "top": 180, "right": 760, "bottom": 280}
        second_bounds = {"left": 810, "top": 180, "right": 890, "bottom": 280}
        backend = FakeBackend(
            [
                make_button("back_btn", root + "top/back_btn", raycast_top=None),
                make_button("home", box + "home", raycast_top=None),
                make_button("reserve_btn", box + "reserve_btn", raycast_top=None),
                make_button("boxes_btn", box + "boxes_btn", raycast_top=None),
                make_button(
                    "icon", card + "icon", 720, 230,
                    bounds=first_bounds, raycast_top=None,
                ),
                make_button(
                    "icon", card + "icon", 850, 230,
                    bounds=second_bounds, raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", box + "home/Text"),
                make_text("0/10", box + "boxes_btn/Text"),
                make_text("0/15", box + "reserve_btn/Text"),
                make_text("2/40", box + "capcity/Text"),
                make_text("5000", root + "top/res/gold/Text"),
                make_text("3", root + "top/res/1/Text"),
                make_text("4", root + "top/res/2/Text"),
                make_text("5", root + "top/res/3/Text"),
                make_text("LV.8", card + "level_bg/Text", first_bounds),
                make_text("1", card + "level_bg/Text", second_bounds),
            ],
            images=[make_image(dock + "frame/content/ComanderCatTpl/up", bounds=first_bounds)],
        )
        oracle = make_oracle(backend)

        cats = oracle.meowfficer_dock_cats()

        self.assertEqual(tuple(item.level for item in cats), (8, 1))
        self.assertEqual(tuple(item.selected for item in cats), (True, False))
        receipt = oracle.click_meowfficer_cat(cats[1])
        self.assertEqual(receipt.semantic_id, "meowfficer/cat/select")
        self.assertEqual(backend.taps, [(850, 230)])

    def test_meowfficer_feed_state_maps_selected_material_by_bounds(self):
        root = (
            "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
            "CommanderCatPlayUI(Clone)/CommanderCatDockUI(Clone)/"
        )
        card = root + "frame/content/ComanderCatTpl/info/"
        card_bounds = {"left": 760, "top": 160, "right": 840, "bottom": 260}
        backend = FakeBackend(
            [
                make_button("cancel_btn", root + "bottom/cancel_btn", raycast_top=None),
                make_button("select_btn", root + "bottom/select_btn", raycast_top=None),
                make_button(
                    "icon", card + "icon", 800, 210,
                    bounds=card_bounds, raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("1/10", root + "bottom/value/Text"),
                make_text("LV.1", card + "level_bg/Text", card_bounds),
            ],
            images=[
                make_image(
                    root + "frame/content/ComanderCatTpl/up", bounds=card_bounds
                )
            ],
        )
        oracle = make_oracle(backend)

        state = oracle.meowfficer_feed_state()

        self.assertEqual(state.selected, 1)
        self.assertEqual(state.capacity, 10)
        self.assertTrue(state.candidates[0].selected)
        self.assertTrue(oracle.enabled("meowfficer/feed/confirm"))

    def test_meowfficer_dock_cats_accept_live_numeric_card_nodes(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/"
        box = dock + "box/"
        first = dock + "frame/content/0/"
        second = dock + "frame/content/1/"
        first_bounds = {"left": 720, "top": 130, "right": 845, "bottom": 260}
        second_bounds = {"left": 850, "top": 130, "right": 975, "bottom": 260}
        backend = FakeBackend(
            [
                make_button("back_btn", root + "top/back_btn", raycast_top=None),
                make_button("home", box + "home", raycast_top=None),
                make_button("reserve_btn", box + "reserve_btn", raycast_top=None),
                make_button("boxes_btn", box + "boxes_btn", raycast_top=None),
                make_button(
                    "info", first + "info", 784, 195,
                    bounds=first_bounds, raycast_top=None,
                ),
                make_button(
                    "info", second + "info", 914, 195,
                    bounds=second_bounds, raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", box + "home/Text"),
                make_text("7/10", box + "boxes_btn/Text"),
                make_text("15/15", box + "reserve_btn/Text"),
                make_text("38/40", box + "capcity/Text"),
                make_text("109505", root + "top/res/gold/Text"),
                make_text("469", root + "top/res/1/Text"),
                make_text("4", root + "top/res/2/Text"),
                make_text("5", root + "top/res/3/Text"),
                make_text("30", first + "info/level_bg/Text", first_bounds),
                make_text("5", second + "info/level_bg/Text", second_bounds),
            ],
            images=[make_image(first + "up", bounds=first_bounds)],
        )
        oracle = make_oracle(backend)

        cats = oracle.meowfficer_dock_cats()

        self.assertEqual(tuple(item.level for item in cats), (30, 5))
        self.assertEqual(tuple(item.selected for item in cats), (True, False))
        receipt = oracle.click_meowfficer_cat(cats[1])
        self.assertEqual(receipt.path, second + "info")
        self.assertEqual(backend.taps, [(914, 195)])

    def test_meowfficer_dock_cats_reject_more_than_live_viewport(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        dock = root + "pages/CommanderCatDockUI(Clone)/"
        box = dock + "box/"
        cards = []
        levels = []
        for index in range(17):
            left = 40 + (index % 4) * 130
            top = 120 + (index // 4) * 110
            bounds = {
                "left": left,
                "top": top,
                "right": left + 100,
                "bottom": top + 100,
            }
            path = dock + f"frame/content/{index}/info"
            cards.append(
                make_button(
                    "info", path, left + 50, top + 50,
                    bounds=bounds, raycast_top=None,
                )
            )
            levels.append(make_text("1", path + "/level_bg/Text", bounds))
        backend = FakeBackend(
            [
                make_button("back_btn", root + "top/back_btn", raycast_top=None),
                make_button("home", box + "home", raycast_top=None),
                make_button("reserve_btn", box + "reserve_btn", raycast_top=None),
                make_button("boxes_btn", box + "boxes_btn", raycast_top=None),
                *cards,
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/8", box + "home/Text"),
                make_text("0/10", box + "boxes_btn/Text"),
                make_text("0/15", box + "reserve_btn/Text"),
                make_text("17/40", box + "capcity/Text"),
                make_text("5000", root + "top/res/gold/Text"),
                make_text("3", root + "top/res/1/Text"),
                make_text("4", root + "top/res/2/Text"),
                make_text("5", root + "top/res/3/Text"),
                *levels,
            ]
        )
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "cat grid is ambiguous"):
            oracle.meowfficer_dock_cats()

    def test_meowfficer_fort_chores_use_asset_derived_clone_paths(self):
        root = "root/OverlayCamera/Overlay/UIMain/CommanderHomeUI(Clone)/bg/frame/"
        content = root + "scrollrect/content/"
        backend = FakeBackend(
            [
                make_button("close_btn", root + "close_btn", raycast_top=None),
                make_button(
                    "play",
                    content + "tpl/unlock/bubble/play",
                    100,
                    200,
                    raycast_top=None,
                ),
                make_button(
                    "clean",
                    content + "tpl(Clone)/unlock/bubble/clean",
                    300,
                    400,
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("2/8", root + "cnt/Text"),
                make_text("LV.3", root + "title/Text"),
            ]
        )
        oracle = make_oracle(backend)

        paths = oracle.meowfficer_fort_chore_paths()

        self.assertEqual(
            paths,
            (
                content + "tpl(Clone)/unlock/bubble/clean",
                content + "tpl/unlock/bubble/play",
            ),
        )
        receipt = oracle.click_meowfficer_fort_chore(paths[0])
        self.assertEqual(receipt.semantic_id, "meowfficer/fort/chore/clean")
        self.assertEqual(backend.taps, [(300, 400)])

    def test_meowfficer_completed_slots_include_clone_rows_and_use_button_center(self):
        root = "root/OverlayCamera/Overlay/UIMain/CommanderBoxesUI(Clone)/frame/"
        boxes = root + "boxes/"
        content = boxes + "mask/content/"
        backend = FakeBackend(
            [
                make_button("close_btn", root + "close_btn", raycast_top=None),
                make_button("finish_btn", boxes + "finish_btn", raycast_top=None),
                make_button("start_btn", boxes + "start_btn", raycast_top=None),
                make_button(
                    "frame",
                    content + "frame",
                    438,
                    190,
                    bounds={"left": 252, "top": 190, "right": 624, "bottom": 354},
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("0/4", boxes + "statistics/traning"),
                make_text("0/6", boxes + "statistics/wait"),
                make_text("COMPLETE", content + "frame/ongoing/time/Text"),
                make_text(
                    "COMPLETE",
                    content + "frame(Clone)/ongoing/time/Text",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.meowfficer_training_state().completed, 2)
        receipt = oracle.click("meowfficer/train/complete/first")

        self.assertEqual(receipt.point, Point(438.0, 272.0))
        self.assertEqual(backend.taps, [(438, 272)])

    def test_meowfficer_queue_prompt_accepts_exact_partial_capacity(self):
        root = "root/OverlayCamera/Overlay/UIMain/"
        prompt = root + "CommanderMsgBoxUI(Clone)/frame/"
        pool = root + "CommanderBoxesUI(Clone)/CommanderBuildPoolUI(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "cancel_btn", prompt + "cancel_btn", raycast_top=None
                ),
                make_button(
                    "confirm_btn", prompt + "confirm_btn", raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "<color=#847D7B>selected 1 box</color>",
                    prompt + "bg/content/Text",
                ),
                make_text("1/1", pool + "statistics/Text"),
            ],
            images=[
                make_image(
                    pool + "frame/bg/content/queue/list1/pos/icon",
                    sprite="ssr1",
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("meowfficer/queue/confirm"))
        oracle.click("meowfficer/queue/confirm")

        self.assertEqual(backend.taps, [(640, 360)])

    def test_meowfficer_acquisition_classifies_tiered_and_tierless_talents(self):
        root = "root/OverlayCamera/Overlay/UIMain/GetCommanderUI(Clone)/"
        backend = FakeBackend(
            [
                make_button("click", root + "click", raycast_top=None),
                make_button(
                    "lock",
                    root + "left_panel/btns/lock",
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("COMMAND MEOW", root + "main/bg/Image"),
                make_text("260825", root + "main/info/content/copyright/Text"),
            ],
            images=[
                make_image(root + "main/info/content/rarity/value", sprite="SSR"),
                make_image(
                    root + "main/info/content/talents/talent/icon",
                    sprite="hangmu_one_1",
                ),
                make_image(
                    root + "main/info/content/talents/talent(Clone)/icon",
                    sprite="chongying_two_2",
                ),
            ],
        )
        oracle = make_oracle(backend)

        state = oracle.meowfficer_acquisition_state()

        self.assertEqual(state.generation, 10)
        self.assertEqual(state.identity, "260825")
        self.assertEqual(state.rarity, "SSR")
        self.assertFalse(state.has_special_talent)
        self.assertTrue(oracle.enabled("meowfficer/get/lock"))
        self.assertFalse(oracle.enabled("meowfficer/get/unlock"))
        oracle.click("meowfficer/get/lock")
        self.assertEqual(backend.taps, [(640, 360)])

        backend.ui["images"][-1]["sprite"] = "rainbow_unique"
        self.assertTrue(oracle.meowfficer_acquisition_state().has_special_talent)

    def test_meowfficer_acquisition_rejects_ambiguous_lock_state(self):
        root = "root/OverlayCamera/Overlay/UIMain/GetCommanderUI(Clone)/"
        backend = FakeBackend(
            [
                make_button("click", root + "click", raycast_top=None),
                make_button("lock", root + "left_panel/btns/lock", raycast_top=None),
                make_button(
                    "unlock", root + "left_panel/btns/unlock", raycast_top=None
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("COMMAND MEOW", root + "main/bg/Image"),
                make_text("260825", root + "main/info/content/copyright/Text"),
            ],
            images=[
                make_image(root + "main/info/content/rarity/value", sprite="SSR"),
                make_image(
                    root + "main/info/content/talents/talent/icon",
                    sprite="rainbow_unique",
                ),
            ],
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("meowfficer/get/lock"))
        self.assertFalse(oracle.enabled("meowfficer/get/unlock"))

    def test_meowfficer_training_state_rejects_over_capacity_counter(self):
        root = "root/OverlayCamera/Overlay/UIMain/CommanderBoxesUI(Clone)/frame/"
        boxes = root + "boxes/"
        backend = FakeBackend(
            [
                make_button("close_btn", root + "close_btn", raycast_top=None),
                make_button("finish_btn", boxes + "finish_btn", raycast_top=None),
                make_button("start_btn", boxes + "start_btn", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("5/4", boxes + "statistics/traning"),
                make_text("6/6", boxes + "statistics/wait"),
            ]
        )

        with self.assertRaisesRegex(SemanticGateClosed, "inconsistent"):
            make_oracle(backend).meowfficer_training_state()
