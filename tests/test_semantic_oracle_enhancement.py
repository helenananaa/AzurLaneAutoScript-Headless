"""Enhancement regression cases for the oracle."""

import copy
import unittest
from alas_headless.semantic_oracle import (
    EnhancementNoMaterialReceipt,
    SemanticGateClosed,
    enhancement_config_policy,
)
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
    set_enhancement_page,
)
from tests.semantic_support.oracle_cases import SemanticOracleTestsSupport


class SemanticOracleTests(SemanticOracleTestsSupport, unittest.TestCase):
    def test_meowfficer_enhance_state_and_submit_use_reviewed_controls(self):
        root = "root/UICamera/Canvas/UIMain/CommanderCatUI(Clone)/blur_panel/"
        play = root + "CommanderCatPlayUI(Clone)/select_panel/"
        backend = FakeBackend(
            [
                make_button("back_btn", root + "top/back_btn", raycast_top=None),
                make_button(
                    "add", play + "frame/list/commandeTF/add", raycast_top=None
                ),
                make_button("confirm_btn", play + "confirm_btn", raycast_top=None),
            ]
        )
        backend.ui = make_ui(
            [
                make_text("LV.9", play + "exp_bg/level_bg/Text"),
                make_text("4000", root + "top/res/gold/Text"),
            ]
        )
        oracle = make_oracle(backend)

        state = oracle.meowfficer_enhance_state()

        self.assertEqual((state.level, state.coins), (9, 4000))
        self.assertTrue(oracle.enabled("meowfficer/enhance/submit"))
        oracle.click("meowfficer/enhance/submit")
        self.assertEqual(backend.taps, [(640, 360)])

    def test_meowfficer_enhance_prompt_is_scoped_to_play_ui(self):
        root = (
            "root/OverlayCamera/Overlay/UIMain/CommanderCatPlayUI(Clone)/"
            "CommanderMsgBoxUI(Clone)/frame/"
        )
        backend = FakeBackend(
            [
                make_button("cancel_btn", root + "cancel_btn", raycast_top=None),
                make_button("confirm_btn", root + "confirm_btn", raycast_top=None),
            ]
        )
        oracle = make_oracle(backend)

        self.assertTrue(oracle.enabled("meowfficer/enhance/cancel"))
        self.assertTrue(oracle.enabled("meowfficer/enhance/confirm"))


class EnhancementSemanticOracleTests(unittest.TestCase):
    def test_dock_favourite_uses_on_layer_as_positive_state_discriminator(self):
        root = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/switch/toggles/"
            "preference_toggle/"
        )
        filter_path = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button"

        for enabled, current_name, expected_point in (
            (True, "off", (820, 30)),
            (False, "on", (760, 30)),
        ):
            with self.subTest(enabled=enabled):
                backend = FakeBackend(
                    [
                        make_button(
                            "index_button",
                            filter_path,
                            40,
                            40,
                            bounds={"left": 20, "top": 20, "right": 60, "bottom": 60},
                        )
                    ]
                )
                filter_image = make_image(
                    filter_path,
                    "shaixuan_off",
                    {"left": 20, "top": 20, "right": 60, "bottom": 60},
                )
                on = make_image(
                    root + "on",
                    "changyong_butten01",
                    {"left": 740, "top": 10, "right": 780, "bottom": 50},
                )
                off = make_image(
                    root + "off",
                    "changyong_butten02",
                    {"left": 800, "top": 10, "right": 840, "bottom": 50},
                )
                on["raycast_target"] = True
                off["raycast_target"] = True

                def set_scope(name):
                    backend.ui = make_ui(
                        [
                            make_text(
                                "20/500",
                                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/Text",
                            ),
                            make_text(
                                "船坞容量:",
                                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/capacity/label",
                            ),
                        ],
                        images=[
                            filter_image,
                            *( (on, off) if name == "on" else (off,) ),
                        ],
                    )

                set_scope(current_name)
                backend.on_tap = lambda: set_scope("on" if enabled else "off")

                receipt = make_oracle(backend).set_enhancement_dock_favourite(enabled)

                self.assertEqual(
                    receipt.semantic_id,
                    "enhancement/dock/favourite/" + ("on" if enabled else "off"),
                )
                self.assertEqual(backend.taps, [expected_point])

    def test_detailed_config_is_normalized_without_random_fallback(self):
        policy = enhancement_config_policy("favourite", 5, "DD > cl > repair")

        self.assertEqual(policy.target_scope.value, "favourite")
        self.assertEqual(policy.check_per_category, 5)
        self.assertEqual(policy.ship_types, ("dd", "cl", "repair"))

    def test_invalid_or_duplicate_filter_fails_closed(self):
        with self.assertRaises(ValueError):
            enhancement_config_policy("all", 5, "dd > typo")
        with self.assertRaises(ValueError):
            enhancement_config_policy("all", 5, "dd > DD")
        with self.assertRaises(ValueError):
            enhancement_config_policy("all", 0, None)

    def test_candidate_favourite_uses_common_toggle_and_returns_to_dock(self):
        backend = FakeBackend([])
        dock_root = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/"
        )
        card_path = (
            "UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/"
            "ships/201351"
        )

        def set_dock(generation):
            filter_path = dock_root + "index_button"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button("201351", card_path, 170, 200),
                    make_button("index_button", filter_path, 40, 40),
                ],
                generation=generation,
            )
            backend.ui = make_ui(
                [
                    make_text("20/500", dock_root + "capacity/Text"),
                    make_text("船坞容量:", dock_root + "capacity/label"),
                    make_text(
                        "那智.改",
                        card_path + "/content/info/name_mask/name",
                        {"left": 155, "top": 185, "right": 185, "bottom": 198},
                    ),
                    make_text(
                        "1",
                        card_path + "/content/dockyard/lv/Text",
                        {"left": 160, "top": 200, "right": 180, "bottom": 215},
                    ),
                ],
                images=[
                    make_image(
                        filter_path,
                        "shaixuan_on",
                        {"left": 20, "top": 20, "right": 60, "bottom": 60},
                    )
                ],
                generation=generation,
            )

        def set_ship_detail(generation, *, detail, common):
            set_enhancement_page(backend, generation)
            backend.buttons["buttons"].append(
                make_button(
                    "back_btn",
                    "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back_btn",
                    57,
                    53,
                )
            )
            backend.buttons["button_count"] = len(backend.buttons["buttons"])
            detail_path = (
                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/left_length/"
                "frame/root/detail_toggle"
            )
            backend.ui["toggles"].append(
                make_toggle(detail_path, checked=detail, x=52, y=439)
            )
            if detail:
                common_path = (
                    "OverlayCamera/Overlay/UIMain/detail_container(Adapt)/"
                    "detail_container/ShipDetailView(Clone)/common_toggle"
                )
                backend.ui["toggles"].append(
                    make_toggle(
                        common_path,
                        checked=common,
                        x=1180,
                        y=718,
                        bounds={
                            "left": 1138,
                            "top": 628,
                            "right": 1222,
                            "bottom": 718,
                        },
                    )
                )
                backend.ui["images"].append(
                    make_image(
                        common_path + ("/on" if common else "/off"),
                        "common_active" if common else "common_deactive",
                        {
                            "left": 1138,
                            "top": 628,
                            "right": 1222,
                            "bottom": 718,
                        },
                    )
                )
            backend.ui["toggle_count"] = len(backend.ui["toggles"])
            backend.ui["image_count"] = len(backend.ui["images"])

        set_dock(10)
        stage = 0

        def advance():
            nonlocal stage
            if stage == 0:
                set_ship_detail(11, detail=False, common=False)
            elif stage == 1:
                set_ship_detail(12, detail=True, common=False)
            elif stage == 2:
                set_ship_detail(13, detail=True, common=True)
            elif stage == 3:
                set_dock(14)
            else:
                self.fail("unexpected favourite-toggle input")
            stage += 1

        backend.on_tap = advance

        receipts = make_oracle(backend).set_enhancement_dock_candidate_favourite(
            0, 201351, "那智.改", 1, True
        )

        self.assertEqual(
            tuple(item.semantic_id for item in receipts),
            (
                "enhancement/dock/ship/201351",
                "enhancement/detail/tab",
                "enhancement/detail/favourite/on",
                "enhancement/detail/back",
            ),
        )
        self.assertEqual(
            backend.taps,
            [(170, 200), (52, 439), (1180, 718), (57, 53)],
        )

    def test_preview_reads_exact_target_attributes_and_materials(self):
        backend = FakeBackend([])
        set_enhancement_page(
            backend,
            20,
            materials=((0, "xiaolietuquan"), (1, "Z21")),
        )
        backend.ui["image_truncated"] = True

        preview = make_oracle(backend).enhancement_preview()

        self.assertEqual(preview.target_name, "那智.改")
        self.assertEqual(preview.material_count, 2)
        self.assertEqual(
            tuple((item.level, item.rarity_sprite) for item in preview.materials),
            ((1, "bg1"), (1, "bg1")),
        )
        cannon = next(item for item in preview.attributes if item.name == "炮击")
        self.assertEqual(
            (
                cannon.current,
                cannon.maximum,
                cannon.addition,
                cannon.exp_current,
                cannon.exp_total,
            ),
            (196, 197, 1, 25, 25),
        )
        self.assertTrue(preview.image_snapshot_truncated)
        self.assertFalse(preview.material_protection_proven)

    def test_recommend_and_clear_are_non_destructive_and_receipted(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)
        stages = [
            lambda: set_enhancement_page(
                backend, 21, materials=((0, "xiaolietuquan"),)
            ),
            lambda: set_enhancement_page(backend, 22),
        ]
        stage = 0

        def advance():
            nonlocal stage
            stages[stage]()
            stage += 1

        backend.on_tap = advance
        oracle = make_oracle(backend)

        preview = oracle.recommend_enhancement_materials()
        receipt = oracle.clear_enhancement_materials()

        self.assertEqual(preview.material_count, 1)
        self.assertEqual(receipt.semantic_id, "enhancement/clear")
        self.assertEqual(backend.taps, [(1024, 626), (856, 626)])
        self.assertEqual(oracle.enhancement_preview().material_count, 0)

    def test_missing_material_rarity_fails_closed(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20, materials=((0, "xiaolietuquan"),))
        backend.ui["images"] = [
            item
            for item in backend.ui["images"]
            if not item["path"].endswith("shiptpl/IconTpl/icon_bg")
        ]
        backend.ui["image_count"] = len(backend.ui["images"])

        with self.assertRaises(SemanticGateClosed):
            make_oracle(backend).enhancement_preview()

    def test_complete_whitelisted_material_cards_prove_protection(self):
        backend = FakeBackend([])
        set_enhancement_page(
            backend,
            20,
            materials=((0, "xiaolietuquan"), (1, "Z21")),
            complete_card_images=True,
        )

        preview = make_oracle(backend).enhancement_preview()

        self.assertTrue(preview.material_protection_proven)
        self.assertEqual(
            (preview.image_source_count, preview.image_source_capacity),
            (6000, 16384),
        )

    def test_unexpected_material_overlay_refuses_protection_proof(self):
        backend = FakeBackend([])
        set_enhancement_page(
            backend,
            20,
            materials=((0, "xiaolietuquan"),),
            complete_card_images=True,
        )
        root = (
            "OverlayCamera/Overlay/UIMain/blur_panel(Adapt)/blur_panel/main/"
            "bg/add_ship_panel/ships/shiptpl"
        )
        backend.ui["images"].append(
            make_image(root + "/IconTpl/icon_bg/lock", "ship_lock")
        )
        backend.ui["image_count"] = len(backend.ui["images"])

        preview = make_oracle(backend).enhancement_preview()

        self.assertFalse(preview.material_protection_proven)

    def test_official_enhancement_confirms_only_a_protected_preview(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)
        stages = [
            lambda: set_enhancement_page(
                backend,
                21,
                materials=((0, "xiaolietuquan"), (1, "Z21")),
                complete_card_images=True,
            ),
            lambda: set_enhancement_page(backend, 22, enhanced=True),
        ]
        stage = 0

        def advance():
            nonlocal stage
            stages[stage]()
            stage += 1

        backend.on_tap = advance

        receipt = make_oracle(backend).enhance_with_official_recommendation()

        self.assertEqual(receipt.consumed_count, 2)
        self.assertEqual(receipt.confirmation.semantic_id, "enhancement/confirm")
        self.assertEqual(
            next(
                item.current for item in receipt.attributes_after if item.name == "炮击"
            ),
            197,
        )
        self.assertTrue(receipt.equipment_preserved)
        self.assertEqual(receipt.equipment_quantities, ())
        self.assertEqual(backend.taps, [(1024, 626), (1191, 626)])

    def test_official_enhancement_waits_past_transitional_empty_material_panel(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)
        stage = 0

        def advance():
            nonlocal stage
            if stage == 0:
                set_enhancement_page(
                    backend,
                    21,
                    materials=((0, "xiaolietuquan"),),
                    complete_card_images=True,
                )
            else:
                set_enhancement_page(backend, 22)
                interim_snapshot = copy.deepcopy(backend.snapshot)
                interim_buttons = copy.deepcopy(backend.buttons)
                interim_ui = copy.deepcopy(backend.ui)
                set_enhancement_page(backend, 23, enhanced=True)
                final_snapshot = copy.deepcopy(backend.snapshot)
                final_buttons = copy.deepcopy(backend.buttons)
                final_ui = copy.deepcopy(backend.ui)
                backend.snapshot_sequence = [interim_snapshot, final_snapshot]
                backend.buttons_sequence = [interim_buttons, final_buttons]
                backend.ui_sequence = [interim_ui, final_ui]
            stage += 1

        backend.on_tap = advance

        receipt = make_oracle(backend).enhance_with_official_recommendation()

        self.assertEqual(receipt.generation_after, 23)
        self.assertEqual(receipt.consumed_count, 1)
        cannon = next(
            item for item in receipt.attributes_after if item.name == "炮击"
        )
        self.assertEqual((cannon.current, cannon.addition), (197, 0))

    def test_official_enhancement_preserves_followup_equipment(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)
        equipment_root = (
            "root/OverlayCamera/Overlay/UIMain/ResolveEquipmentUI(Clone)/main/"
        )

        def equipment_page(generation, selected):
            buttons = [
                make_button(
                    "cancel_btn",
                    equipment_root + "cancel_btn",
                    844,
                    606,
                    raycast_top=True,
                ),
                make_button(
                    "ALL",
                    equipment_root + "options/ALL",
                    200,
                    601,
                    raycast_top=True,
                ),
            ]
            if selected:
                buttons.append(
                    make_button(
                        "reduce",
                        equipment_root
                        + "frame/view/content/0/frame/bg/selected/reduce",
                        250,
                        156,
                        raycast_top=True,
                    )
                )
            images = []
            if selected:
                images.append(
                    make_image(
                        equipment_root + "options/ALL/Background/Checkmark",
                        "toggle_on",
                    )
                )
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(buttons, generation=generation)
            backend.ui = make_ui(
                [
                    make_text(
                        "请选择需要拆解的装备，未选的装备将放入仓库",
                        equipment_root + "title/Text",
                    ),
                    make_text("取 消", equipment_root + "cancel_btn/Image"),
                    make_text("全部", equipment_root + "options/ALL/Label"),
                    make_text(
                        "14",
                        equipment_root + "frame/view/content/0/frame/bg/icon_bg/count",
                    ),
                ],
                images=images,
                generation=generation,
            )

        def preserve_confirmation(generation):
            root = "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
            backend.snapshot = make_snapshot(generation=generation)
            backend.buttons = make_buttons(
                [
                    make_button(
                        "custom_button_1(Clone)",
                        root + "button_container/custom_button_1(Clone)",
                        790,
                        515,
                        raycast_top=True,
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

        stages = [
            lambda: set_enhancement_page(
                backend,
                21,
                materials=((0, "xiaolietuquan"),),
                complete_card_images=True,
            ),
            lambda: equipment_page(22, True),
            lambda: equipment_page(23, False),
            lambda: preserve_confirmation(24),
            lambda: set_enhancement_page(backend, 25, enhanced=True),
        ]
        stage = 0

        def advance():
            nonlocal stage
            stages[stage]()
            stage += 1

        backend.on_tap = advance

        receipt = make_oracle(backend).enhance_with_official_recommendation()

        self.assertEqual(receipt.equipment_quantities, ((0, 14),))
        self.assertTrue(receipt.equipment_preserved)
        self.assertEqual(
            tuple(action.semantic_id for action in receipt.equipment_actions),
            (
                "enhancement/equipment/deselect-all",
                "enhancement/equipment/cancel-disassembly",
                "enhancement/equipment/preserve/confirm",
            ),
        )
        self.assertEqual(len(backend.taps), 5)

    def test_equipment_preservation_still_rejects_wrong_or_obscured_confirmation(self):
        root = "root/OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        message = "不进行任何操作，所有装备会放入<color=#5f984d>仓库</color>\n是否退出？"
        for case in ("text", "raycast", "loading", "duplicate"):
            with self.subTest(case=case):
                button = make_button("custom_button_1(Clone)", root + "button_container/custom_button_1(Clone)")
                buttons = [button]
                if case == "raycast":
                    button["raycast_top"] = None
                elif case == "loading":
                    buttons.append(make_button("loading", "root/UIOverlay/Loading(Clone)/mask"))
                elif case == "duplicate":
                    buttons.append(dict(button))
                backend = FakeBackend(buttons)
                backend.ui = make_ui([make_text(
                    "其他确认" if case == "text" else message, root + "msg_panel/content"
                )])
                with self.assertRaises(SemanticGateClosed):
                    make_oracle(backend)._click_retirement_button(
                        "enhancement/equipment/preserve/confirm",
                        "Msgbox(Clone)/window/button_container/custom_button_1(Clone)",
                        identity_text_suffix="Msgbox(Clone)/window/msg_panel/content",
                        identity_text=message,
                    )
                self.assertEqual(backend.taps, [])

    def test_official_enhancement_skips_when_recommendation_is_empty(self):
        backend = FakeBackend([])
        set_enhancement_page(backend, 20)

        receipt = make_oracle(backend).enhance_with_official_recommendation(
            timeout_seconds=0.01
        )

        self.assertIsInstance(receipt, EnhancementNoMaterialReceipt)
        self.assertEqual(receipt.target_name, "那智.改")
        self.assertEqual(backend.taps, [(1024, 626)])
