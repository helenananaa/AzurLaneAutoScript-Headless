"""Guild regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_image,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import (
    GuildSemanticOracleTestsSupport,
    SemanticOracleTestsSupport,
)


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_guild_shop_refresh_prompt_is_exact_and_confirmable(self):
        page = "root/OverlayCamera/Overlay/UIMain/"
        shop = page + "ShopSupplyShopUI(Clone)/"
        popup = page + "Msgbox(Clone)/window/"
        confirm = popup + "button_container/custom_button_1(Clone)"
        cancel = popup + "button_container/custom_button_2(Clone)"
        backend = FakeBackend(
            [
                make_button("closeBtn", page + "buttonList/top/closeBtn", raycast_top=None),
                make_button("homeBtn", page + "buttonList/top/homeBtn", raycast_top=None),
                *[
                    make_button(str(index), shop + f"scroll/content/{index}", raycast_top=None)
                    for index in range(10)
                ],
                make_button("custom_button_1(Clone)", confirm),
                make_button("custom_button_2(Clone)", cancel),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("商店", page + "buttonList/top/title/Text"),
                make_text(
                    "补给商店",
                    page + "buttonList/shop1List/supplyShop/shop2List/"
                    "supplyShop/selected/name",
                ),
                make_text("舰队", shop + "toggleGroup/Toggle/selected/Label"),
                make_text("确 定", confirm + "/pic"),
                make_text("取 消", cancel + "/pic"),
                make_text(
                    "是否花费50<color=#92fc63>舰队币</color>刷新商品列表",
                    popup + "msg_panel/content",
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.shop_refresh_prompt(), ("GuildCoins", 50))
        receipt = oracle.click_shop_refresh_confirm("GuildCoins", 50)

        self.assertEqual(receipt.semantic_id, "shop/refresh/confirm")
        self.assertEqual(len(backend.taps), 1)

    def test_guild_message_blocks_main_but_allows_exact_close(self):
        backend = FakeBackend(
            [
                make_button("task", "root/frame/bottom/frame/task", 875, 684),
                make_button(
                    "close",
                    "Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/close",
                    1150,
                    90,
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertFalse(oracle.enabled("main/task"))
        self.assertTrue(oracle.enabled("overlay/guild-message/close"))
        with self.assertRaises(SemanticGateClosed):
            oracle.click("main/task")
        receipt = oracle.click("overlay/guild-message/close")

        self.assertEqual(receipt.semantic_id, "overlay/guild-message/close")
        self.assertEqual(backend.taps, [(1150, 90)])


class GuildSemanticOracleTests(GuildSemanticOracleTestsSupport, unittest.TestCase):
    def test_logistics_zero_remaining_keeps_typed_rows_but_disables_input(self):
        page = "root/OverlayCamera/Overlay/UIMain/TaskPanel(Adapt)/TaskPanel/"
        toggles, images = self._guild_nav("office")
        buttons = [
            make_button(
                "back",
                "root/OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back",
                55,
                55,
            )
        ]
        texts = [
            make_text("0/3", page + "SupplyPanel/frame/open/Text"),
            make_text("100/<size=40>100</size>", page + "open/top/progress"),
            make_text("今日可完成：0次", page + "SubmitPanel/cnt/Text"),
        ]
        for index, (sprite, owned, required) in enumerate(
            (("gold", "707", "600"), ("oil", "15K", "200"), ("17041", "14K", "20"))
        ):
            left = 440 + index * 198
            row = page + "SubmitPanel/list/" + ("tpl" if index == 0 else "tpl(Clone)")
            button = make_button(
                "submit",
                row + "/submit",
                left + 72,
                626,
                bounds={"left": left, "top": 607, "right": left + 144, "bottom": 646},
                raycast_top=None,
            )
            button["interactable"] = False
            buttons.append(button)
            texts.extend(
                (
                    make_text(
                        owned + "/" + required,
                        row + "/item/Text",
                        {"left": left + 30, "top": 530, "right": left + 114, "bottom": 553},
                    ),
                    make_text(
                        "75",
                        row + "/award/Text",
                        {"left": left + 80, "top": 564, "right": left + 100, "bottom": 586},
                    ),
                )
            )
            images.append(
                make_image(
                    row + "/item/icon_bg/icon",
                    sprite,
                    {"left": left + 31, "top": 470, "right": left + 113, "bottom": 552},
                )
            )
        images.append(make_image(page + "open/mask_all", "finish_mask1"))
        backend = FakeBackend(buttons)
        backend.ui = make_ui(texts, toggles=toggles, images=images)

        state = make_oracle(backend).guild_logistics_state()

        self.assertEqual(state.exchange_remaining, 0)
        self.assertTrue(state.mission_finished)
        self.assertFalse(state.mission_claimable)
        self.assertEqual(tuple(item.icon_sprite for item in state.exchange_items), ("gold", "oil", "17041"))
        self.assertTrue(all(not item.button.interactable for item in state.exchange_items))

    def test_report_count_requires_exact_report_root_and_capacity(self):
        root = "root/OverlayCamera/Overlay/UIMain/GuildEventReportUI(Clone)"
        backend = FakeBackend([make_button("GuildEventReportUI(Clone)", root)])
        backend.ui = make_ui([make_text("20/20", root + "/frame/cnt")])

        self.assertEqual(make_oracle(backend).guild_report_count(), 20)
