"""Enhancement regression cases for the adapter."""

import unittest
from alas_headless import Bounds, Point, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from types import SimpleNamespace
from unittest.mock import Mock, patch


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_meowfficer_enhancement_plans_are_admitted(self):
        adapter, oracle, gate_calls = self.make_adapter()

        for mode, sunday in (("seamlessly", False), ("once_a_day", True)):
            with self.subTest(mode=mode, sunday=sunday):
                adapter.admit_meowfficer_training_plan(mode=mode, sunday=sunday)

        self.assertEqual(oracle.click_calls, [])
        self.assertEqual(gate_calls, [True, True])

    def test_meowfficer_enhance_no_feed_material_returns_to_dock(self):
        adapter, oracle, _ = self.make_adapter()
        target = SimpleNamespace(
            path="cat/one",
            level=8,
            selected=True,
            point=Point(100, 100),
            bounds=Bounds(80, 80, 120, 120),
        )
        oracle.meowfficer_dock_state = Mock(
            side_effect=[SimpleNamespace(coins=5000), SimpleNamespace(coins=5000)]
        )
        oracle.meowfficer_dock_cats = Mock(return_value=(target,))
        oracle.meowfficer_enhance_state = Mock(
            side_effect=[
                SimpleNamespace(generation=10, level=8, coins=5000),
                SimpleNamespace(generation=11, level=8, coins=5000),
            ]
        )
        oracle.meowfficer_feed_state = Mock(
            return_value=SimpleNamespace(
                generation=10, selected=0, capacity=10, candidates=()
            )
        )

        result = adapter.enhance_meowfficer(index=1, max_feed_level=1)

        self.assertEqual(result, "success")
        self.assertEqual(
            oracle.click_calls,
            [
                "meowfficer/enhance/open",
                "meowfficer/feed/open",
                "meowfficer/feed/cancel",
                "meowfficer/enhance/back",
            ],
        )

    @patch("alas_headless.alas_adapter.time.sleep", return_value=None)
    def test_meowfficer_enhance_selects_eligible_feed_and_proves_spend(self, _sleep):
        adapter, oracle, _ = self.make_adapter()
        target = SimpleNamespace(
            path="cat/target",
            level=8,
            selected=True,
            point=Point(100, 100),
            bounds=Bounds(80, 80, 120, 120),
        )
        material = SimpleNamespace(
            path="cat/material",
            level=1,
            selected=False,
            point=Point(200, 100),
            bounds=Bounds(180, 80, 220, 120),
        )
        selected_material = SimpleNamespace(**{**vars(material), "selected": True})
        oracle.meowfficer_dock_state = Mock(
            side_effect=[SimpleNamespace(coins=5000), SimpleNamespace(coins=4000)]
        )
        oracle.meowfficer_dock_cats = Mock(return_value=(target,))
        oracle.meowfficer_enhance_state = Mock(
            side_effect=[
                SimpleNamespace(generation=10, level=8, coins=5000),
                SimpleNamespace(generation=12, level=8, coins=5000),
                SimpleNamespace(generation=13, level=9, coins=4000),
                SimpleNamespace(generation=14, level=9, coins=4000),
            ]
        )
        oracle.meowfficer_feed_state = Mock(
            side_effect=[
                SimpleNamespace(
                    generation=11,
                    selected=0,
                    capacity=10,
                    candidates=(material,),
                ),
                SimpleNamespace(
                    generation=12,
                    selected=1,
                    capacity=10,
                    candidates=(selected_material,),
                ),
                SimpleNamespace(
                    generation=14,
                    selected=0,
                    capacity=10,
                    candidates=(),
                ),
            ]
        )
        oracle.click_meowfficer_cat = Mock(return_value=SimpleNamespace())
        oracle.enabled_values["meowfficer/enhance/confirm"] = False

        result = adapter.enhance_meowfficer(index=1, max_feed_level=1)

        self.assertEqual(result, "success")
        oracle.click_meowfficer_cat.assert_called_once_with(material)
        self.assertEqual(
            oracle.click_calls,
            [
                "meowfficer/enhance/open",
                "meowfficer/feed/open",
                "meowfficer/feed/confirm",
                "meowfficer/enhance/submit",
                "meowfficer/feed/open",
                "meowfficer/feed/cancel",
                "meowfficer/enhance/back",
            ],
        )

    def test_enhancement_task_honours_favourite_filter_and_check_budget(self):
        adapter, oracle, gate_calls = self.make_adapter(enhancement_budget=2)

        consumed = self.run_enhancement_ports(adapter, "favourite", 3, "dd > cl")
        receipts = adapter.enhancement_receipts()

        self.assertEqual(consumed, 0)
        self.assertEqual(len(receipts), 2)
        self.assertTrue(all(item.capability_id == "enhancement.execute" for item in receipts))
        self.assertEqual(
            oracle.enhancement_calls,
            [
                ("favourite", True),
                ("filter", "dd"),
                ("candidates", "dd"),
                ("open", 100001),
                ("recommend", "dd"),
                ("back", "dd"),
                ("candidates", "dd"),
                ("favourite", True),
                ("filter", "cl"),
                ("candidates", "cl"),
                ("open", 100002),
                ("recommend", "cl"),
                ("back", "cl"),
                ("reset", None),
            ],
        )
        self.assertEqual(adapter._action_ledger.remaining("enhancement.execute"), 0)
        self.assertEqual(len(gate_calls), 1)

    def test_enhancement_task_is_default_denied_before_navigation(self):
        adapter, oracle, _ = self.make_adapter()

        with self.assertRaisesRegex(SemanticGateClosed, "positive transaction budget"):
            adapter.begin_enhancement_task("all", 5, None)

        self.assertEqual(oracle.enhancement_calls, [])
