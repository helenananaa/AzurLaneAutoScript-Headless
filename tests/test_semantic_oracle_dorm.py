"""Dorm regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import DormState, SemanticGateClosed
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
    def test_dorm_state_uses_exact_typed_summary(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    page + "bottomPanel/bottomright/decorate_btn",
                    977,
                    640,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("6/6", page + "bottomPanel/bottomleft/train_btn/Text"),
                make_text("0/40000", page + "bottomPanel/bottomleft/feed_btn/Text"),
                make_text("454", page + "topPanel/btns/topright/comfortable/Text"),
                make_text("1F", page + "topPanel/btns/topright/switch/Text"),
                make_text("", page + "bottomPanel/bottomleft/feed_btn/time"),
            ]
        )

        state = make_oracle(backend).dorm_state()

        self.assertEqual(
            state,
            DormState(
                occupied_slots=6,
                total_slots=6,
                food=0,
                food_capacity=40000,
                comfort=454,
                floor=1,
                food_countdown_seconds=None,
            ),
        )

    def test_dorm_state_accepts_delegated_manage_raycast_with_exact_summary(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    page + "bottomPanel/bottomright/decorate_btn",
                    977,
                    640,
                    raycast_top=False,
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text("6/6", page + "bottomPanel/bottomleft/train_btn/Text"),
                make_text("0/40000", page + "bottomPanel/bottomleft/feed_btn/Text"),
                make_text("454", page + "topPanel/btns/topright/comfortable/Text"),
                make_text("1F", page + "topPanel/btns/topright/switch/Text"),
                make_text("", page + "bottomPanel/bottomleft/feed_btn/time"),
            ]
        )

        self.assertEqual(make_oracle(backend).dorm_state().total_slots, 6)

    def test_dorm_state_rejects_inconsistent_capacity(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [make_button("decorate_btn", page + "bottomPanel/bottomright/decorate_btn")]
        )
        backend.ui = make_ui(
            [
                make_text("7/6", page + "bottomPanel/bottomleft/train_btn/Text"),
                make_text("1/40000", page + "bottomPanel/bottomleft/feed_btn/Text"),
                make_text("454", page + "topPanel/btns/topright/comfortable/Text"),
                make_text("1F", page + "topPanel/btns/topright/switch/Text"),
                make_text("01:02:03", page + "bottomPanel/bottomleft/feed_btn/time"),
            ]
        )

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).dorm_state()

    def test_dorm_statistics_blocks_page_but_allows_exact_confirm(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    page + "bottomPanel/bottomright/decorate_btn",
                ),
                make_button(
                    "confirm_btn",
                    "root/Overlay/UIMain/BackYardStatisticsUI(Clone)/"
                    "painting/confirm_btn",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("dorm/page/manage"))
        self.assertTrue(oracle.enabled("dorm/statistics/confirm"))

    def test_dorm_feed_uses_food_card_image_not_purchase_plus(self):
        dorm = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
        feed = "root/UICamera/Canvas/UIMain/BackYardFeedUI(Clone)/"
        backend = FakeBackend(
            [
                make_button(
                    "decorate_btn",
                    dorm + "bottomPanel/bottomright/decorate_btn",
                ),
                make_button("close", feed + "close", 320, 540),
            ]
        )
        texts = [make_text("0/40000", feed + "frame/Text")]
        images = []
        for offset, item_id in enumerate(range(50001, 50007)):
            root = feed + "frame/food_{0}/".format(item_id)
            texts.extend(
                [
                    make_text(
                        "食物{0}".format((1, 2, 3, 5, 10, 20)[offset] * 1000),
                        root + "Text",
                    ),
                    make_text(str(10 - offset), root + "icon_bg/count"),
                ]
            )
            image = make_image(
                root + "icon_bg",
                "bg2",
                {
                    "left": 395 + offset * 128,
                    "top": 375,
                    "right": 499 + offset * 128,
                    "bottom": 480,
                },
            )
            image["raycast_target"] = True
            image["raycast_top"] = True
            images.append(image)
        backend.ui = make_ui(texts, images=images)
        oracle = make_oracle(backend)

        state = oracle.dorm_feed_state()
        receipt = oracle.click_dorm_food(50001)

        self.assertEqual(state.items[0].count, 10)
        self.assertEqual(state.items[0].button.name, "icon_bg")
        self.assertTrue(receipt.path.endswith("food_50001/icon_bg"))
        self.assertEqual(backend.taps, [(447, 428)])

    def test_current_dorm_furniture_purchase_uses_typed_gold_controls(self):
        shop = "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/"
        cards = shop + "pages/BackYardFurniturePage(Clone)/adpter/frame/bg/content/"
        dialog = "OverlayCamera/Overlay/UIMain/FurnitureMsgboxPage(Clone)/frame/"
        buttons = [
            make_button(str(index), cards + str(index), 320 + index * 90, 260)
            for index in range(8)
        ]
        buttons.extend(
            [
                make_button("gold_purchase_btn", dialog + "btns/gold_purchase_btn", 904, 508),
                make_button("gem_purchase_btn", dialog + "btns/gem_purchase_btn", 725, 508),
                make_button("close_btn", dialog + "close_btn", 968, 194),
                make_button("right_arr", dialog + "count/right_arr", 929, 334),
                make_button("left_arr", dialog + "count/left_arr", 694, 334),
            ]
        )
        backend = FakeBackend(buttons)
        texts = [
            make_text("item-{0}".format(index), cards + str(index) + "/name")
            for index in range(8)
        ]
        texts.extend(
            [
                make_text("10 days", cards + "0/time/Text"),
                make_text("limited wall", dialog + "name"),
                make_text("1", dialog + "count/Text"),
                make_text("", dialog + "max_cnt"),
                make_text("150", dialog + "price/gold_text"),
                make_text("450", dialog + "price/gem_text"),
                make_text("4512", shop + "adpter/top/res_gold/Text"),
                make_text("5422", shop + "adpter/top/res_gem/Text"),
            ]
        )
        backend.ui = make_ui(texts)
        oracle = make_oracle(backend)

        self.assertEqual(oracle.dorm_furniture_time_limited_item_indices(), (0,))
        purchase = oracle.dorm_furniture_purchase_state()
        balance = oracle.dorm_furniture_shop_balance()
        receipt = oracle.click_dorm_furniture_purchase("gold")
        close = oracle.close_dorm_furniture_purchase()

        self.assertEqual(purchase.item_name, "limited wall")
        self.assertEqual(purchase.quantity, 1)
        self.assertIsNone(purchase.maximum_quantity)
        self.assertEqual((purchase.gold_price, purchase.gem_price), (150, 450))
        self.assertEqual((balance.dorm_coins, balance.gems), (4512, 5422))
        self.assertTrue(receipt.path.endswith("gold_purchase_btn"))
        self.assertTrue(close.path.endswith("close_btn"))
        self.assertEqual(backend.taps, [(904, 508), (968, 194)])

    def test_current_dorm_furniture_theme_details_uses_exact_typed_image(self):
        shop = "UICamera/Canvas/UIMain/NewBackYardShopUI(Clone)/"
        themes = shop + "pages/BackYardThemePage(Clone)/list/frame/mask/content/"
        buttons = [
            make_button(str(index), themes + str(index), 220 + index * 90, 610)
            for index in range(7)
        ]
        backend = FakeBackend(buttons)
        detail = make_image(
            "OverlayCamera/Overlay/UIMain/adpter/descript/btn_goumai",
            "buy_bg",
            {"left": 997.0, "top": 444.0, "right": 1265.0, "bottom": 496.0},
        )
        detail["raycast_target"] = True
        backend.ui = make_ui([], images=[detail])
        oracle = make_oracle(backend)

        receipt = oracle.click_dorm_furniture_theme_details()

        self.assertEqual(receipt.semantic_id, "dorm/furniture/theme/details")
        self.assertTrue(receipt.path.endswith("descript/btn_goumai"))
        self.assertEqual(backend.taps, [(1131, 470)])

    def test_current_dorm_furniture_theme_uses_distinct_set_and_all_controls(self):
        root = "OverlayCamera/Overlay/UIMain/BackYardThemeInfoPage(Clone)"
        frame = root + "/frame/"
        buttons = [
            make_button("BackYardThemeInfoPage(Clone)", root, 640, 360),
            make_button("purchase_btn", frame + "purchase_btn", 632, 649),
            make_button("purchase_all_btn", frame + "purchase_all_btn", 945, 649),
            make_button("back", frame + "back", 107, 131),
        ]
        backend = FakeBackend(buttons)
        oracle = make_oracle(backend)

        one = oracle.click_dorm_furniture_theme_purchase_option("set")
        all_items = oracle.click_dorm_furniture_theme_purchase_option("all")
        back = oracle.close_dorm_furniture_theme_details()

        self.assertEqual(one.semantic_id, "dorm/furniture/theme/set")
        self.assertEqual(all_items.semantic_id, "dorm/furniture/theme/all")
        self.assertEqual(back.semantic_id, "dorm/furniture/theme/back")
        self.assertEqual(backend.taps, [(632, 649), (945, 649), (107, 131)])

    def test_current_dorm_furniture_theme_payment_is_gold_only_and_typed(self):
        root = "OverlayCamera/Overlay/UIMain/ThemeMsgboxPage(Clone)"
        frame = root + "/frame/"
        buttons = [
            make_button("ThemeMsgboxPage(Clone)", root, 640, 360),
            make_button("gold_purchase_btn", frame + "btns/gold_purchase_btn", 808, 491),
            make_button("close_btn", frame + "close_btn", 968, 194),
        ]
        backend = FakeBackend(buttons)
        backend.ui = make_ui(
            [
                make_text("limited theme", frame + "name"),
                make_text("1", frame + "count/Text"),
                make_text("1330", frame + "price/gold_text"),
            ]
        )
        oracle = make_oracle(backend)

        purchase = oracle.dorm_furniture_theme_purchase_state()
        commit = oracle.click_dorm_furniture_theme_purchase_gold()
        close = oracle.close_dorm_furniture_theme_purchase()

        self.assertEqual(purchase.theme_name, "limited theme")
        self.assertEqual((purchase.quantity, purchase.gold_price), (1, 1330))
        self.assertEqual(commit.semantic_id, "dorm/furniture/theme/purchase/gold")
        self.assertEqual(close.semantic_id, "dorm/furniture/theme/purchase/close")
        self.assertEqual(backend.taps, [(808, 491), (968, 194)])

    def test_dorm_back_accepts_only_reviewed_delegated_raycast(self):
        path = (
            "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main/"
            "topPanel/btns/topleft/return"
        )
        bounds = {"left": 15, "top": 10, "right": 85, "bottom": 79}
        backend = FakeBackend(
            [
                make_button(
                    "return",
                    path,
                    x=50,
                    y=44,
                    bounds=bounds,
                    raycast_top=False,
                )
            ]
        )
        images = [
            make_image(path, "back_btn_bg", bounds=bounds),
            make_image(
                path + "/Image",
                "return",
                bounds={"left": 40, "top": 29, "right": 60, "bottom": 59},
            ),
            make_image(
                path + "/s",
                "back_btn_s1",
                bounds={"left": 10, "top": 10, "right": 90, "bottom": 87},
            ),
        ]
        for image in images:
            image["raycast_target"] = True
        backend.ui = make_ui([], images=images)
        oracle = make_oracle(backend)

        receipt = oracle.click("dorm/page/back")
        self.assertEqual(receipt.semantic_id, "dorm/page/back")
        self.assertEqual(backend.taps, [(50, 44)])

        backend.ui["images"][2]["sprite"] = "unexpected"
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click("dorm/page/back")
        self.assertEqual(backend.taps, [(50, 44)])

    def test_dorm_empty_food_cancel_requires_reviewed_popup_structure(self):
        root = "root/OverlayCamera/Overlay/UIMain/CourtYardEmptyFoodUI(Clone)"
        path = root + "/frame/cancel_btn"
        bounds = {"left": 418, "top": 489, "right": 622, "bottom": 555}
        backend = FakeBackend(
            [
                make_button(
                    "cancel_btn",
                    path,
                    x=520,
                    y=522,
                    bounds=bounds,
                    raycast_top=None,
                ),
                make_button("close", "root/UICamera/Canvas/UIMain/BackYardFeedUI(Clone)/close", raycast_top=False),
            ]
        )
        images = [
            make_image(path, "btn_yellow", bounds=bounds),
            make_image(
                root + "/frame/Image",
                "hungry",
                bounds={"left": 356, "top": 177, "right": 924, "bottom": 465},
            ),
            make_image(
                root + "/frame",
                "msg_bg",
                bounds={"left": 304, "top": 117, "right": 976, "bottom": 572},
            ),
        ]
        for image in images:
            image["raycast_target"] = True
        backend.ui = make_ui([], images=images)
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("dorm/empty-food/cancel"))
        receipt = oracle.click("dorm/empty-food/cancel")
        self.assertEqual(receipt.semantic_id, "dorm/empty-food/cancel")
        self.assertEqual(backend.taps, [(520, 522)])

        backend.ui["images"][1]["sprite"] = "unexpected"
        self.assertFalse(oracle.enabled("dorm/empty-food/cancel"))
        with self.assertRaisesRegex(SemanticGateClosed, "not actionable"):
            oracle.click("dorm/empty-food/cancel")
        self.assertEqual(backend.taps, [(520, 522)])

    def test_dorm_page_controls_require_reviewed_typed_structure(self):
        page = "root/UICamera/Canvas/UIMain/CourtYardUI(Clone)/main"
        feed = page + "/bottomPanel/bottomleft/feed_btn"
        collect = page + "/rightPanel/onekey"
        backend = FakeBackend(
            [
                make_button(
                    "return",
                    page + "/topPanel/btns/topleft/return",
                    raycast_top=False,
                ),
                make_button(
                    "decorate_btn",
                    page + "/bottomPanel/bottomright/decorate_btn",
                    raycast_top=False,
                ),
                make_button(
                    "feed_btn",
                    feed,
                    x=304,
                    y=631,
                    bounds={"left": 212, "top": 564, "right": 396, "bottom": 698},
                    raycast_top=False,
                ),
                make_button("onekey", collect, x=1210, y=509, raycast_top=False),
            ]
        )
        one_key = make_image(
            collect,
            "onekey",
            bounds={"left": 1152, "top": 453, "right": 1267, "bottom": 565},
        )
        one_key["raycast_target"] = True
        backend.ui = make_ui(
            [
                make_text("食量", feed + "/label"),
                make_text("0/40000", feed + "/Text"),
            ],
            images=[
                make_image(
                    feed + "/icon",
                    "btn_feed",
                    bounds={"left": 221, "top": 548, "right": 317, "bottom": 658},
                ),
                make_image(
                    feed + "/bg",
                    "btn_72",
                    bounds={"left": 213, "top": 651, "right": 394, "bottom": 699},
                ),
                one_key,
            ],
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("dorm/feed"))
        self.assertTrue(oracle.enabled("dorm/collect"))
        oracle.click("dorm/feed")
        oracle.click("dorm/collect")
        self.assertEqual(backend.taps, [(269, 603), (1210, 509)])

        # A natively proven Button point must not be redirected to a
        # decorative child Image whose raycast_target is false.
        backend.buttons['buttons'][2]['raycast_top'] = True
        oracle.click('dorm/feed')
        self.assertEqual(backend.taps[-1], (304, 631))
        backend.buttons['buttons'][2]['raycast_top'] = False

        backend.ui["texts"][0]["text"] = "unexpected"
        self.assertFalse(oracle.enabled("dorm/feed"))
        self.assertFalse(oracle.enabled("dorm/collect"))
