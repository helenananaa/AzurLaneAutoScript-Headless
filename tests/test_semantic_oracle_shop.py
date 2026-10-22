"""Shop regression cases for the oracle."""

import copy
import unittest
from unittest import mock
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_snapshot,
    make_image,
    make_oracle,
    make_text,
    make_toggle,
    make_ui,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_shop_gift_pack_toggle_uses_its_coherent_frame_pair(self):
        root = "OverlayCamera/Overlay/UIMain/"
        backend = FakeBackend(
            [
                make_button("homeBtn", root + "buttonList/top/homeBtn"),
                make_button("closeBtn", root + "buttonList/top/closeBtn"),
            ]
        )
        toggle = make_toggle(
            root + "buttonList/shop1List/giftPackShop/shop1Tg",
            checked=False,
            raycast_top=None,
        )
        shell_ui = make_ui(
            [make_text("商店", root + "buttonList/top/title/Text")],
            toggles=[toggle],
        )
        # The first Button/UI pair is coherent.  A later UI frame is
        # deliberately incoherent to prove click_toggle does not issue a
        # second, unrelated Shop-shell read before it taps the proven Toggle.
        backend.ui_sequence = [
            shell_ui,
            make_ui(
                [make_text("商店", root + "buttonList/top/title/Text")],
                toggles=[toggle],
                generation=99,
            ),
        ]

        receipt = make_oracle(backend).click_toggle("shop/gift-pack")

        self.assertEqual(receipt.semantic_id, "shop/gift-pack")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_recommendation_shop_home_uses_exact_top_control(self):
        root = "OverlayCamera/Overlay/UIMain/"
        backend = FakeBackend(
            [
                make_button(
                    "homeBtn",
                    root + "buttonList/top/homeBtn",
                    x=1140.0,
                    y=42.0,
                    raycast_top=None,
                ),
                make_button("closeBtn", root + "buttonList/top/closeBtn"),
            ]
        )
        backend.ui = make_ui(
            [make_text("商店", root + "buttonList/top/title/Text")],
            toggles=[
                make_toggle(
                    root + "buttonList/shop1List/giftPackShop/shop1Tg",
                    checked=False,
                    raycast_top=None,
                )
            ],
        )

        receipt = make_oracle(backend).click_recommendation_shop_home()

        self.assertEqual(receipt.semantic_id, "shop/home")
        self.assertEqual(backend.taps, [(1140, 42)])

    def test_general_shop_items_use_exact_typed_cards_and_currency_sprites(self):
        page = "root/OverlayCamera/Overlay/UIMain/"
        shop = page + "ShopSupplyShopUI(Clone)/"
        buttons = [
            make_button("closeBtn", page + "buttonList/top/closeBtn", raycast_top=None),
            make_button("homeBtn", page + "buttonList/top/homeBtn", raycast_top=None),
            *[
                make_button(
                    str(index), shop + f"scroll/content/{index}", raycast_top=None
                )
                for index in range(10)
            ],
        ]
        names = [
            "外观装备箱(滨海极速)",
            "克洛希德科技箱T3",
            "克洛希德科技箱T4",
            "舰艇防御教材T1",
            "通用部件T1",
            "鱼雷部件T3",
            "防空炮部件T3",
            "主炮部件T3",
            "威斯克科技箱T3",
            "舰艇攻击教材T3",
        ]
        prices = [7000, 2000, 5000, 20, 750, 2700, 2400, 3000, 10000, 80]
        amounts = [1, 1, 1, 1, 5, 5, 5, 5, 5, 1]
        costs = [
            "gold",
            "gold",
            "gold",
            "gem",
            "gold",
            "gold",
            "gold",
            "gold",
            "gold",
            "gem",
        ]
        texts = [
            make_text("商店", page + "buttonList/top/title/Text"),
            make_text("35709", page + "buttonList/top/resources/gold/Text"),
            make_text("5022", page + "buttonList/top/resources/gem/Text"),
            make_text(
                "补给商店",
                page + "buttonList/shop1List/supplyShop/shop2List/"
                "supplyShop/selected/name",
            ),
            make_text("军火", shop + "toggleGroup/Toggle/selected/Label"),
        ]
        images = []
        for index, (name, price, amount, cost) in enumerate(
            zip(names, prices, amounts, costs)
        ):
            root = shop + f"scroll/content/{index}"
            texts.extend(
                [
                    make_text(name, root + "/name_mask/name"),
                    make_text(str(amount), root + "/itemBg/item/icon_bg/count"),
                    make_text(str(price), root + "/consume/contain/Text"),
                ]
            )
            images.extend(
                [
                    make_image(root + "/consume/contain/icon", sprite=cost),
                    make_image(
                        root + "/itemBg/item/icon_bg/icon", sprite=str(16000 + index)
                    ),
                ]
            )
        texts.append(
            make_text("可兑换次数4/5", shop + "scroll/content/1/count_contain/label")
        )
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, images=images)
        oracle = make_oracle(backend)

        self.assertTrue(oracle.munitions_page_visible())
        self.assertTrue(oracle.shop_general_nav_selected())
        self.assertTrue(oracle.shop_general_tab_selected())
        items = oracle.general_shop_items()
        self.assertEqual(len(items), 10)
        self.assertEqual(items[1].canonical_name, "BoxT3")
        self.assertEqual((items[1].remaining, items[1].total), (4, 5))
        self.assertEqual(items[9].canonical_name, "BookRedT3")
        self.assertEqual((items[9].cost, items[9].price), ("Gems", 80))
        self.assertEqual(oracle.shop_currency_balance("Coins"), 35709)
        self.assertEqual(oracle.shop_currency_balance("Gems"), 5022)

        # Re-read both snapshots after an actual generation split; no tap and
        # no widened coherence tolerance. Supply-page identity is unchanged.
        original_visible = oracle.munitions_page_visible
        oracle.munitions_page_visible = mock.Mock(return_value=True)
        split = copy.deepcopy(backend.ui)
        split["generation"] = 13
        settled = copy.deepcopy(backend.ui)
        settled["generation"] = 20
        backend.snapshot_sequence = [make_snapshot(generation=10), make_snapshot(generation=20)]
        backend.ui_sequence = [split, settled]
        recovered = oracle.general_shop_items()
        self.assertEqual(len(recovered), 10)
        self.assertEqual(recovered[1].price, 2000)
        self.assertEqual(backend.taps, [])
        backend.snapshot_sequence = [make_snapshot(generation=g) for g in (30,40,50,60)]
        backend.ui_sequence = []
        for generation in (33,43,53,63):
            split_frame = copy.deepcopy(split)
            split_frame["generation"] = generation
            backend.ui_sequence.append(split_frame)
        with self.assertRaisesRegex(SemanticGateClosed, "snapshots are not coherent"):
            oracle.general_shop_items()
        self.assertEqual(backend.taps, [])
        oracle.munitions_page_visible = original_visible
        backend.snapshot = make_snapshot(generation=70)
        backend.buttons["generation"] = 70
        backend.ui["generation"] = 70

        backend.ui["images"][-2]["sprite"] = "unknown"
        with self.assertRaisesRegex(SemanticGateClosed, "currency is unknown"):
            oracle.general_shop_items()

    def test_shop_navigation_and_refresh_use_typed_toggle_and_button_state(self):
        page = "root/OverlayCamera/Overlay/UIMain/"
        shop = page + "ShopSupplyShopUI(Clone)/"
        month_path = page + "buttonList/shop1List/supplyShop/shop2List/monthShop"
        refresh = make_button(
            "timeBtn", shop + "timeBtn", x=894, y=675, raycast_top=None
        )
        refresh["interactable"] = False
        backend = FakeBackend(
            [
                make_button(
                    "closeBtn", page + "buttonList/top/closeBtn", raycast_top=None
                ),
                make_button(
                    "homeBtn", page + "buttonList/top/homeBtn", raycast_top=None
                ),
                *[
                    make_button(
                        str(index), shop + f"scroll/content/{index}", raycast_top=None
                    )
                    for index in range(10)
                ],
                refresh,
            ]
        )
        backend.ui = make_ui(
            [
                make_text("商店", page + "buttonList/top/title/Text"),
                make_text("月度商店", month_path + "/name"),
                make_text(
                    "<size=28>核心月度</size>",
                    shop + "toggleGroup/Toggle/selected/Label",
                ),
                make_text("06:53:43后刷新", shop + "timeBtn/Text"),
            ],
            toggles=[
                make_toggle(
                    month_path,
                    checked=False,
                    raycast_top=None,
                    x=93,
                    y=497,
                )
            ],
            images=[make_image(shop + "timeBtn", sprite="item_refresh")],
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.shop_refresh_available())
        self.assertEqual(oracle.shop_selected_tab_label(), "核心月度")
        receipt = oracle.click_shop_nav("月度商店")
        self.assertEqual(receipt.semantic_id, "shop/navigation/月度商店")
        self.assertEqual(backend.taps, [(93, 497)])

        refresh["interactable"] = True
        backend.buttons = make_buttons(backend.buttons["buttons"])
        self.assertTrue(oracle.shop_refresh_available())
