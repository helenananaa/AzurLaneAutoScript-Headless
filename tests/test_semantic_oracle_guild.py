"""Guild regression cases for the oracle."""

from copy import deepcopy
import unittest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_image,
    make_oracle,
    make_text,
    make_toggle,
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
    def _navigation_backend(self, selected="main", extra_names=()):
        toggles, images = self._guild_nav(selected)
        root = toggles[0]["path"].rsplit("/", 1)[0] + "/"
        toggles.extend(
            make_toggle(root + name, checked=name == selected)
            for name in extra_names
        )
        backend = FakeBackend(
            [make_button(
                "back",
                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back",
                55,
                55,
            )]
        )
        backend.ui = make_ui([], toggles=toggles, images=images)
        return backend

    def test_navigation_accepts_member_and_leader_baselines(self):
        for selected, extra_names in (("main", ()), ("main", ("apply",)), ("apply", ("apply",))):
            with self.subTest(selected=selected, extra_names=extra_names):
                backend = self._navigation_backend(selected, extra_names)
                self.assertTrue(make_oracle(backend).guild_page_visible())
                self.assertEqual(backend.taps, [])

    def test_navigation_accepts_additive_unselected_tabs_and_reordering(self):
        backend = self._navigation_backend(extra_names=("apply", "future"))
        # An unselected, disabled future feature is not needed to identify or
        # operate the existing tabs. Its selection state must still be typed.
        backend.ui["toggles"][-1]["interactable"] = False
        backend.ui["toggles"][-1]["adb_point"] = None
        backend.ui["toggles"].reverse()
        oracle = make_oracle(backend)

        self.assertTrue(oracle.guild_page_visible())
        receipt = oracle.click_toggle("guild/nav/member")

        self.assertEqual(receipt.semantic_id, "guild/nav/member")
        self.assertEqual(backend.taps, [(52, 252)])

    def test_unknown_or_multiple_selected_tabs_do_not_prove_page(self):
        for selected in ("future", "main"):
            with self.subTest(selected=selected):
                backend = self._navigation_backend(selected, ("future",))
                backend.ui["toggles"][-1]["checked"] = True
                backend.ui["toggles"][-1]["interactable"] = False
                backend.ui["toggles"][-1]["adb_point"] = None
                oracle = make_oracle(backend)

                self.assertFalse(oracle.guild_page_visible())
                with self.assertRaises(SemanticGateClosed):
                    oracle.click_toggle("guild/nav/member")
                self.assertEqual(backend.taps, [])

    def test_duplicate_or_conflicting_tab_identity_is_rejected(self):
        for conflict in ("duplicate-known", "path-name-mismatch"):
            with self.subTest(conflict=conflict):
                backend = self._navigation_backend(extra_names=("future",))
                if conflict == "path-name-mismatch":
                    backend.ui["toggles"][0]["path"] += "_different"
                else:
                    duplicate = deepcopy(backend.ui["toggles"][1])
                    duplicate["interactable"] = False
                    backend.ui["toggles"].append(duplicate)
                    backend.ui["toggle_count"] += 1
                oracle = make_oracle(backend)

                self.assertFalse(oracle.guild_page_visible())
                with self.assertRaises(SemanticGateClosed):
                    oracle.click_toggle("guild/nav/member")
                self.assertEqual(backend.taps, [])

    def test_navigation_ignores_inactive_templates_and_unselected_optional_details(self):
        for variation in ("inactive-template", "disabled-template", "optional-identity", "disabled-apply"):
            with self.subTest(variation=variation):
                backend = self._navigation_backend(extra_names=("apply", "future"))
                toggles = backend.ui["toggles"]
                if variation in ("inactive-template", "disabled-template"):
                    duplicate = deepcopy(toggles[0])
                    key = "active_in_hierarchy" if variation == "inactive-template" else "active_and_enabled"
                    duplicate[key] = False
                    toggles.append(duplicate)
                    backend.ui["toggle_count"] += 1
                elif variation == "optional-identity":
                    toggles[-1]["name"] = "future_alias"
                    toggles.append(deepcopy(toggles[-1]))
                    backend.ui["toggle_count"] += 1
                else:
                    toggles[-2]["interactable"] = False
                    toggles[-2]["adb_point"] = None
                    toggles[-2]["adb_bounds"] = None
                oracle = make_oracle(backend)

                self.assertTrue(oracle.guild_page_visible())
                oracle.click_toggle("guild/nav/member")
                self.assertEqual(backend.taps, [(52, 252)])

    def test_inactive_duplicate_only_blocks_its_exact_input_target(self):
        backend = self._navigation_backend()
        duplicate = deepcopy(backend.ui["toggles"][1])
        duplicate["active_in_hierarchy"] = False
        backend.ui["toggles"].append(duplicate)
        backend.ui["toggle_count"] += 1
        oracle = make_oracle(backend)

        self.assertTrue(oracle.guild_page_visible())
        with self.assertRaises(SemanticGateClosed):
            oracle.click_toggle("guild/nav/member")
        self.assertEqual(backend.taps, [])
        oracle.click_toggle("guild/nav/logistics")
        self.assertEqual(backend.taps, [(52, 347)])

    def test_selected_apply_still_requires_actionable_identity(self):
        backend = self._navigation_backend("apply", ("apply",))
        backend.ui["toggles"][-1]["interactable"] = False

        self.assertFalse(make_oracle(backend).guild_page_visible())

    def test_additive_tab_does_not_replace_a_required_tab(self):
        backend = self._navigation_backend(extra_names=("future",))
        backend.ui["toggles"].pop(1)
        backend.ui["toggle_count"] -= 1

        self.assertFalse(make_oracle(backend).guild_page_visible())

    def test_extra_tab_selection_still_requires_a_boolean(self):
        backend = self._navigation_backend(extra_names=("future",))
        backend.ui["toggles"][-1]["checked"] = "false"
        oracle = make_oracle(backend)

        with self.assertRaisesRegex(SemanticGateClosed, "toggle state is malformed"):
            oracle.guild_page_visible()
        self.assertEqual(backend.taps, [])

    def test_additive_tabs_preserve_owner_and_obscured_target_checks(self):
        for conflict in ("wrong-owner", "covered-back", "covered-target", "blocking-popup"):
            with self.subTest(conflict=conflict):
                backend = self._navigation_backend(extra_names=("future",))
                if conflict == "wrong-owner":
                    for toggle in backend.ui["toggles"]:
                        toggle["path"] = "other/" + toggle["path"]
                elif conflict == "covered-back":
                    backend.buttons["buttons"][0]["raycast_top"] = False
                elif conflict == "covered-target":
                    backend.ui["toggles"][1]["raycast_top"] = False
                else:
                    backend.buttons["buttons"].append(make_button(
                        "close",
                        "Overlay/UIMain/GuildMsgBoxUI(Clone)/frame/close",
                    ))
                    backend.buttons["button_count"] += 1
                oracle = make_oracle(backend)

                if conflict in ("wrong-owner", "covered-back"):
                    self.assertFalse(oracle.guild_page_visible())
                with self.assertRaises(SemanticGateClosed):
                    oracle.click_toggle("guild/nav/member")
                self.assertEqual(backend.taps, [])

    def test_logistics_zero_remaining_keeps_typed_rows_but_disables_input(self):
        self._assert_logistics_zero_remaining("707")

    def test_logistics_rich_text_shortage_keeps_typed_rows_but_disables_input(self):
        state = self._assert_logistics_zero_remaining("<color=#FF5C5CFF>487</color>")
        self.assertEqual(state.exchange_items[0].owned, 487)
        self.assertEqual(state.exchange_items[0].required, 600)

    def _assert_logistics_zero_remaining(self, coin_owned):
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
            (("gold", coin_owned, "600"), ("oil", "15K", "200"), ("17041", "14K", "20"))
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
        self.assertEqual(backend.taps, [])
        return state

    def test_report_count_requires_exact_report_root_and_capacity(self):
        root = "root/OverlayCamera/Overlay/UIMain/GuildEventReportUI(Clone)"
        backend = FakeBackend([make_button("GuildEventReportUI(Clone)", root)])
        backend.ui = make_ui([make_text("20/20", root + "/frame/cnt")])

        self.assertEqual(make_oracle(backend).guild_report_count(), 20)
