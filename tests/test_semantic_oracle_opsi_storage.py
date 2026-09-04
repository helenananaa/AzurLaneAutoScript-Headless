"""Opsi storage regression cases for the oracle."""

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
    def test_storage_controls_accept_delegated_overlay_raycast(self):
        local_map_root = "root/OverlayCamera/Overlay/UIMain/top/adapt/"
        inventory = make_button(
            "inventory_button",
            local_map_root + "right_stage/btn_list/dock/inventory_button",
            raycast_top=None,
        )
        oracle = make_oracle(FakeBackend([inventory]))
        with mock.patch.object(oracle, "operation_siren_state"):
            self.assertTrue(oracle.enabled("os/map/storage"))

        storage_back = make_button(
            "back_btn",
            "root/UICamera/Canvas/UIMain/WorldInventoryUI(Clone)/adapt/"
            "blur_panel/adapt/top/back_btn",
            raycast_top=None,
        )
        oracle = make_oracle(FakeBackend([storage_back]))
        self.assertTrue(oracle.enabled("os/storage/back"))

    def test_storage_state_types_exact_tuning_sample_identity(self):
        root = (
            "root/OverlayCamera/Overlay/UIMain/WorldInventoryUI(Clone)/adapt/"
            "item_scrollview/Viewport/item_grid/301"
        )
        back = make_button(
            "back_btn",
            "root/UICamera/Canvas/UIMain/WorldInventoryUI(Clone)/adapt/"
            "blur_panel/adapt/top/back_btn",
            raycast_top=None,
        )
        backend = FakeBackend([back, make_button("301", root, x=200, y=180)])
        backend.ui = make_ui(
            [
                make_text("效能样本-攻击", root + "/bg/name"),
                make_text("7", root + "/bg/icon_bg/count"),
            ],
            images=[
                make_image(
                    root + "/bg/icon_bg/icon",
                    "Wyangben1",
                    {"left": 140, "top": 100, "right": 260, "bottom": 220},
                )
            ],
        )
        oracle = make_oracle(backend)

        state = oracle.operation_siren_storage_state()

        self.assertEqual(state.sample_count, 7)
        self.assertEqual(state.items[0].item_type, "SAMPLE_OFFENSE")
        backend.ui["images"][0]["sprite"] = "Wyangben2"
        with self.assertRaisesRegex(SemanticGateClosed, "identity changed"):
            oracle.operation_siren_storage_state()

    def test_mission_checkout_can_exclude_the_monthly_boss_row(self):
        row_root = (
            "root/OverlayCamera/Overlay/UIMain/WorldInformationUI(Clone)/adapt/"
            "right_panel/main/viewport/content/"
        )
        monthly_row = make_button(
            "btn_go",
            row_root + "task_tpl/base_panel/btn_go",
            x=1070,
            y=220,
            bounds={"left": 1024, "top": 203, "right": 1116, "bottom": 238},
            raycast_top=None,
        )
        daily_row = make_button(
            "btn_go",
            row_root + "task_tpl(Clone)/base_panel/btn_go",
            x=1070,
            y=350,
            bounds={"left": 1024, "top": 333, "right": 1116, "bottom": 368},
            raycast_top=None,
        )
        close = make_button(
            "close_btn",
            "root/OverlayCamera/Overlay/UIMain/WorldInformationUI(Clone)/adapt/"
            "right_panel/title/close_btn",
            raycast_top=None,
        )
        backend = FakeBackend([close, monthly_row, daily_row])
        backend.ui = make_ui(
            [
                make_text(
                    "任务总汇",
                    "root/OverlayCamera/Overlay/UIMain/WorldInformationUI(Clone)/"
                    "adapt/right_panel/title/task_all",
                ),
                make_text(
                    "普通作战·仲裁机关",
                    row_root + "task_tpl/base_panel/base_show/title/Text",
                    bounds={"left": 568, "top": 181, "right": 775, "bottom": 212},
                ),
            ]
        )
        oracle = make_oracle(backend)

        self.assertEqual(oracle.operation_siren_month_boss_difficulty(), "normal")
        self.assertTrue(oracle.operation_siren_mission_checkout_available())
        self.assertTrue(
            oracle.operation_siren_mission_checkout_available(
                exclude_monthly_boss=True
            )
        )
        receipt = oracle.click_operation_siren_mission_checkout(
            exclude_monthly_boss=True
        )
        self.assertEqual(receipt.semantic_id, "os/mission-list/checkout")
        self.assertEqual(backend.taps, [(1070, 350)])

        backend.buttons = make_buttons([close, monthly_row])
        self.assertFalse(
            oracle.operation_siren_mission_checkout_available(
                exclude_monthly_boss=True
            )
        )
        with self.assertRaisesRegex(SemanticGateClosed, "mission row is absent"):
            oracle.click_operation_siren_mission_checkout(
                exclude_monthly_boss=True
            )
