"""Opsi resources regression cases for the oracle."""

import unittest
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend,
    make_button,
    make_buttons,
    make_image,
    make_oracle,
    make_text,
    make_ui,
)
from tests.semantic_support.oracle_cases import OperationSirenSemanticOracleTestsSupport
from unittest import mock


class OperationSirenSemanticOracleTests(OperationSirenSemanticOracleTestsSupport, unittest.TestCase):
    def test_action_point_entry_uses_exact_stamina_resource_and_proves_popup(self):
        backend = FakeBackend(
            [
                make_button(
                    "stamina",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/"
                    "resources/WorldResPanel(Clone)/res/stamina",
                    x=876,
                    y=37,
                    bounds={"left": 784, "top": 17, "right": 967, "bottom": 57},
                )
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "33",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/"
                    "resources/WorldResPanel(Clone)/res/stamina/value",
                    bounds={"left": 878, "top": 28, "right": 928, "bottom": 46},
                )
            ]
        )
        oracle = make_oracle(backend)
        with mock.patch.object(oracle, "operation_siren_state"):
            receipt = oracle.click_operation_siren_action_point_open()

        self.assertEqual(receipt.semantic_id, "os/action-point/open")
        self.assertEqual(backend.taps, [(903, 37)])

    def test_action_point_state_types_exact_oil_purchase_terms(self):
        backend = self._action_point_backend(
            purchase_text=(
                "花费<color=#92fc63>1000</color>石油购买行动力"
                "<color=#92fc63>100</color>点，本周剩余"
                "<color=#92fc63>5/5</color>次"
            )
        )

        state = make_oracle(backend).operation_siren_action_point_state()

        self.assertEqual(state.current, 139)
        self.assertEqual(state.item_counts, (17077, 92, 0, 0))
        self.assertEqual(state.selected_index, 0)
        self.assertEqual(state.oil_purchase_cost, 1000)
        self.assertEqual(state.oil_purchase_points, 100)
        self.assertEqual(state.oil_purchase_remaining, 5)
        self.assertEqual(state.oil_purchase_limit, 5)

    def test_action_point_state_accepts_current_progressive_purchase_terms(self):
        state = make_oracle(
            self._action_point_backend(
                purchase_text=(
                    "花费<color=#92fc63>2000</color>石油购买行动力"
                    "<color=#92fc63>200</color>点，本周剩余"
                    "<color=#92fc63>3/5</color>次"
                )
            )
        ).operation_siren_action_point_state()

        self.assertEqual(state.oil_purchase_cost, 2000)
        self.assertEqual(state.oil_purchase_points, 200)
        self.assertEqual(state.oil_purchase_remaining, 3)

    def test_action_point_state_omits_purchase_terms_for_box_selection(self):
        state = make_oracle(
            self._action_point_backend(selected_index=1)
        ).operation_siren_action_point_state()

        self.assertIsNone(state.oil_purchase_cost)
        self.assertIsNone(state.oil_purchase_points)
        self.assertIsNone(state.oil_purchase_remaining)
        self.assertIsNone(state.oil_purchase_limit)

    def test_action_point_state_rejects_changed_purchase_amount(self):
        backend = self._action_point_backend(
            purchase_text=(
                "花费<color=#92fc63>1000</color>石油购买行动力"
                "<color=#92fc63>0</color>点，本周剩余"
                "<color=#92fc63>5/5</color>次"
            )
        )

        with self.assertRaisesRegex(SemanticGateClosed, "terms changed"):
            make_oracle(backend).operation_siren_action_point_state()

    def test_current_fleet_repair_uses_left_portrait_agony(self):
        backend = FakeBackend(
            [
                make_button(
                    "back_button",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/top_stage/back_button",
                ),
                make_button(
                    "fleet_bar",
                    "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/other/fleet_bar",
                ),
            ]
        )
        oracle = make_oracle(backend)
        self.assertFalse(oracle.operation_siren_current_fleet_needs_repair())
        agony_path = (
            "root/OverlayCamera/Overlay/UIMain/top/adapt/left_stage/bg/fleet/"
            "vanguard/shiptpl(Clone)/agony"
        )
        backend.buttons = make_buttons(
            backend.buttons["buttons"]
            + [make_button("agony", agony_path, x=238, y=414)]
        )
        self.assertTrue(oracle.operation_siren_current_fleet_needs_repair())

        backend.buttons = make_buttons(
            backend.buttons["buttons"]
            + [
                make_button("agony", agony_path, x=238, y=414),
            ]
        )
        with self.assertRaisesRegex(SemanticGateClosed, "overlap"):
            oracle.operation_siren_current_fleet_needs_repair()

    def test_voucher_archive_singlebox_is_exact_and_confirmable(self):
        root = "OverlayCamera/Overlay/UIMain/ShopsUISinglebox(Clone)/window"
        backend = FakeBackend(
            [
                make_button(
                    "confirm_btn",
                    root + "/actions/confirm_btn",
                    x=786,
                    y=513,
                    raycast_top=None,
                ),
                make_button(
                    "cancel_btn",
                    root + "/actions/cancel_btn",
                    x=494,
                    y=513,
                    raycast_top=None,
                ),
            ]
        )
        backend.ui = make_ui(
            [
                make_text(
                    "档案坐标记录仪2",
                    root + "/item/display_panel/name_container/name/Text",
                ),
                make_text("1", root + "/item/left/IconTpl/icon_bg/count"),
            ],
            images=[
                make_image(
                    root + "/item/left/IconTpl/icon_bg/icon",
                    "Wdanganluopan2",
                )
            ],
        )
        oracle = make_oracle(backend)

        self.assertEqual(
            oracle.operation_siren_voucher_purchase_dialog_quantity(
                "档案坐标记录..", "Wdanganluopan2"
            ),
            1,
        )
        receipt = oracle.click_operation_siren_voucher_purchase_confirm(
            "档案坐标记录..", "Wdanganluopan2", 1
        )
        self.assertEqual(receipt.semantic_id, "os/voucher/purchase/confirm")
        self.assertTrue(receipt.path.endswith("actions/confirm_btn"))
        self.assertEqual(backend.taps, [(786, 513)])
