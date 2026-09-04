"""Meowfficer regression cases for the adapter."""

import unittest
from alas_headless import Bounds, Point, SemanticGateClosed
from alas_headless.semantic_oracle import ActionReceipt
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_meowfficer_check_color_only_matches_the_dock_page(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.enabled_values.update(
            {
                "meowfficer/page/back": False,
                "meowfficer/get/result/close": False,
                "meowfficer/queue/close": False,
                "meowfficer/train/close": True,
                "meowfficer/fort/close": False,
            }
        )

        self.assertFalse(
            adapter.match_template_color(NamedButton("MEOWFFICER_CHECK"))
        )
        adapter.click(NamedButton("MEOWFFICER_CHECK"))

        self.assertEqual(oracle.click_calls, ["meowfficer/train/close"])
        self.assertEqual(len(gate_calls), 2)

    def test_meowfficer_fort_zero_occupied_slots_is_a_safe_noop(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.meowfficer_dock_state = Mock(
            return_value=SimpleNamespace(fort_current=0, fort_total=8)
        )

        self.assertFalse(adapter.meowfficer_fort_chore_available())
        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(gate_calls, [True])

    def test_meowfficer_fort_occupied_slots_are_admitted(self):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.meowfficer_dock_state = Mock(
            return_value=SimpleNamespace(fort_current=1, fort_total=8)
        )

        self.assertTrue(adapter.meowfficer_fort_chore_available())

        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(gate_calls, [True])

    @patch("alas_headless.alas_adapter.time.sleep", return_value=None)
    def test_meowfficer_fort_runs_one_exact_chore_to_idle(self, _sleep):
        adapter, oracle, _ = self.make_adapter()
        path = (
            "root/CommanderHomeUI(Clone)/bg/frame/scrollrect/content/"
            "tpl/unlock/bubble/play"
        )
        receipt = ActionReceipt(
            semantic_id="meowfficer/fort/chore/play",
            generation=10,
            point=Point(10, 20),
            bounds=Bounds(0, 0, 20, 40),
            path=path,
        )
        oracle.enabled_values["reward/award-info/close"] = False
        oracle.meowfficer_fort_chore_paths = Mock(side_effect=[(path,), ()])
        oracle.click_meowfficer_fort_chore = Mock(return_value=receipt)

        receipts = adapter.run_meowfficer_fort_chores()

        self.assertEqual(receipts, (receipt,))
        oracle.click_meowfficer_fort_chore.assert_called_once_with(path)

    def test_meowfficer_purchase_uses_exact_selected_count_and_postconditions(self):
        adapter, oracle, gate_calls = self.make_adapter()
        before = SimpleNamespace(
            purchased=0,
            purchase_total=15,
            coins=10000,
            box_counts=(10, 20, 30),
        )
        after = SimpleNamespace(
            purchased=3,
            purchase_total=15,
            coins=7000,
            box_counts=(11, 21, 31),
        )
        oracle.meowfficer_dock_state = Mock(side_effect=[before, after])
        oracle.meowfficer_purchase_state = Mock(
            side_effect=[
                SimpleNamespace(generation=10, count=1, total_price=0),
                SimpleNamespace(generation=11, count=2, total_price=1500),
                SimpleNamespace(generation=12, count=3, total_price=3000),
            ]
        )

        result = adapter.buy_meowfficer_boxes(3)

        self.assertIs(result, after)
        self.assertEqual(
            oracle.click_calls,
            [
                "meowfficer/buy/enter",
                "meowfficer/buy/add",
                "meowfficer/buy/add",
                "meowfficer/buy/submit",
            ],
        )
        self.assertEqual(gate_calls, [True])

    def test_meowfficer_purchase_rejects_quota_before_input(self):
        adapter, oracle, _ = self.make_adapter()
        oracle.meowfficer_dock_state = Mock(
            return_value=SimpleNamespace(
                purchased=14,
                purchase_total=15,
                coins=10000,
                box_counts=(10, 20, 30),
            )
        )

        with self.assertRaisesRegex(SemanticGateClosed, "quota"):
            adapter.buy_meowfficer_boxes(2)

        self.assertEqual(oracle.click_calls, [])

    def test_meowfficer_once_a_day_non_sunday_plan_is_admitted(self):
        adapter, oracle, gate_calls = self.make_adapter()

        adapter.admit_meowfficer_training_plan(mode="once_a_day", sunday=False)

        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(gate_calls, [True])

    @patch("alas_headless.alas_adapter.time.sleep", return_value=None)
    def test_meowfficer_acquisition_allows_ordinary_tiered_cat(self, _sleep):
        adapter, oracle, gate_calls = self.make_adapter()
        oracle.enabled_values.update(
            {
                "meowfficer/get/result/close": False,
                "meowfficer/get/lock-cancel": False,
            }
        )
        oracle.meowfficer_training_state = Mock(
            side_effect=[SemanticGateClosed("acquiring"), SimpleNamespace()]
        )
        oracle.meowfficer_acquisition_state = Mock(
            return_value=SimpleNamespace(
                generation=10,
                identity="260825",
                rarity="SSR",
                talent_sprites=("hangmu_one_1", "chongying_two_2"),
                has_special_talent=False,
            )
        )

        collected = adapter.finish_meowfficer_acquisition(
            retain_talented_gold=True,
            retain_talented_purple=True,
        )

        self.assertEqual(collected, 1)
        self.assertEqual(oracle.click_calls, ["meowfficer/get/continue"])
        self.assertEqual(gate_calls, [True])

    @patch("alas_headless.alas_adapter.time.sleep", return_value=None)
    def test_meowfficer_acquisition_locks_reviewed_special_talent(self, _sleep):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values.update(
            {
                "meowfficer/get/result/close": False,
                "meowfficer/get/lock-cancel": False,
                "meowfficer/get/lock": True,
                "meowfficer/get/unlock": False,
            }
        )
        oracle.meowfficer_training_state = Mock(
            side_effect=[
                SemanticGateClosed("acquiring"),
                SemanticGateClosed("confirming"),
                SimpleNamespace(),
            ]
        )
        oracle.meowfficer_acquisition_state = Mock(
            return_value=SimpleNamespace(
                generation=10,
                identity="special-1",
                rarity="SSR",
                talent_sprites=("rainbow_unique",),
                has_special_talent=True,
            )
        )

        collected = adapter.finish_meowfficer_acquisition(
            retain_talented_gold=True,
            retain_talented_purple=True,
        )

        self.assertEqual(collected, 1)
        self.assertEqual(
            oracle.click_calls,
            [
                "meowfficer/get/lock",
                "meowfficer/get/continue",
                "meowfficer/get/lock-confirm",
            ],
        )

    @patch("alas_headless.alas_adapter.time.sleep", return_value=None)
    def test_meowfficer_acquisition_allows_identical_cards_after_generation_advance(
        self, _sleep
    ):
        adapter, oracle, _ = self.make_adapter()
        oracle.enabled_values.update(
            {
                "meowfficer/get/result/close": False,
                "meowfficer/get/lock-cancel": False,
            }
        )
        oracle.meowfficer_training_state = Mock(
            side_effect=[
                SemanticGateClosed("first"),
                SemanticGateClosed("second"),
                SimpleNamespace(),
            ]
        )
        oracle.meowfficer_acquisition_state = Mock(
            side_effect=[
                SimpleNamespace(
                    generation=10,
                    identity="same-card",
                    rarity="R",
                    talent_sprites=("ordinary_1",),
                    has_special_talent=False,
                ),
                SimpleNamespace(
                    generation=11,
                    identity="same-card",
                    rarity="R",
                    talent_sprites=("ordinary_1",),
                    has_special_talent=False,
                ),
            ]
        )

        collected = adapter.finish_meowfficer_acquisition(
            retain_talented_gold=True,
            retain_talented_purple=True,
        )

        self.assertEqual(collected, 2)
        self.assertEqual(
            oracle.click_calls,
            ["meowfficer/get/continue", "meowfficer/get/continue"],
        )
