import ast
import unittest
from pathlib import Path

from alas_headless import (
    ActionReceipt,
    Bounds,
    Point,
    SemanticGateClosed,
)
from alas_headless.adapter import ACTION_CAPABILITIES, StaleFrameError
from alas_headless.alas_adapter import AlasSemanticAdapter


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "python" / "alas_headless" / "alas_adapter.py"


class ActionLedgerWiringTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = ast.parse(SOURCE.read_text(encoding="utf-8"))

    def test_every_current_mutation_capability_has_a_central_dispatch_site(self):
        dispatched = set()
        for node in ast.walk(self.tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_dispatch_mutation"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                dispatched.add(node.args[0].value)
            if (
                isinstance(node, ast.Assign)
                and any(
                    isinstance(target, ast.Name) and target.id == "capability"
                    for target in node.targets
                )
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                dispatched.add(node.value.value)
        self.assertEqual(dispatched, ACTION_CAPABILITIES)

    def test_every_legacy_budget_consumption_function_dispatches_through_ledger(self):
        uncovered = []
        for function in (
            node
            for node in ast.walk(self.tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        ):
            consumes_budget = any(
                isinstance(child, ast.AugAssign)
                and isinstance(child.op, ast.Sub)
                and isinstance(child.target, ast.Attribute)
                and child.target.attr.endswith("budget")
                for child in ast.walk(function)
            )
            dispatches = any(
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr == "_dispatch_mutation"
                for child in ast.walk(function)
            )
            if consumes_budget and not dispatches:
                uncovered.append(function.name)
        self.assertEqual(uncovered, [])

    def test_daily_start_is_single_use_and_produces_typed_receipt(self):
        class Oracle:
            starts = 0

            def daily_fleet_index(self):
                return 4

            def click_daily_precombat_start(self):
                self.starts += 1
                return ActionReceipt(
                    semantic_id="daily/precombat/start",
                    generation=7,
                    point=Point(1142.0, 641.0),
                    bounds=Bounds(1080.0, 610.0, 1200.0, 680.0),
                    path="PreCombatUI(Clone)/adapt/right/start",
                )

        oracle = Oracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None, daily_execute_budget=1)
        adapter._daily_kind = "tactical_training"
        adapter._daily_stage = 2

        receipt = adapter.click_daily_precombat_start()
        self.assertEqual(
            receipt.semantic_id,
            "daily/execute/tactical_training/stage/2/fleet/4",
        )
        self.assertEqual(receipt.capability_id, "daily.execute")
        self.assertEqual(adapter.daily_execution_receipts(), (receipt,))
        self.assertEqual(adapter.click_daily_precombat_start(), receipt)
        self.assertEqual(oracle.starts, 1)

    def test_daily_bulk_quick_run_spends_one_execution_grant(self):
        class Oracle:
            clicks = 0

            def click_daily_run_choice(self, choice):
                self.clicks += 1
                return ActionReceipt(
                    semantic_id="daily/run/" + choice,
                    generation=9,
                    point=Point(1078.0, 322.0),
                    bounds=Bounds(987.0, 279.0, 1169.0, 365.0),
                    path="Overlay/selected/stagetpl/quickly/bg/mult",
                )

        oracle = Oracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None, daily_execute_budget=1)
        adapter._daily_kind = "fierce_assault"
        adapter._daily_stage = 1
        button = type("Button", (), {"name": "DAILY_SKIP"})()

        receipt = adapter.click(button)

        self.assertEqual(
            receipt.semantic_id,
            "daily/execute/fierce_assault/stage/1/quick/all",
        )
        self.assertEqual(receipt.capability_id, "daily.execute")
        self.assertEqual(adapter.daily_execution_receipts(), (receipt,))
        self.assertEqual(oracle.clicks, 1)

    def test_daily_stage_click_is_idempotent_during_its_transition(self):
        class Oracle:
            clicks = 0

            def click_daily_stage(self, index):
                self.clicks += 1
                return ActionReceipt(
                    semantic_id="daily/stage/{0}".format(index),
                    generation=5,
                    point=Point(600.0, 360.0),
                    bounds=Bounds(400.0, 300.0, 800.0, 420.0),
                    path="DailyLevelUI(Clone)/stage",
                )

            def daily_selected_stage_visible(self, index):
                return False

        oracle = Oracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter._daily_kind = "fierce_assault"

        receipt = adapter.click_daily_stage(1)
        self.assertEqual(adapter.click_daily_stage(1), receipt)
        self.assertEqual(oracle.clicks, 1)

    def test_daily_selected_stage_does_not_repeat_stage_click(self):
        class Oracle:
            clicks = 0
            def click_daily_stage(self, index):
                self.clicks += 1
                return ActionReceipt(
                    semantic_id="daily/stage/1",
                    generation=5,
                    point=Point(600.0, 200.0),
                    bounds=Bounds(380.0, 130.0, 1180.0, 280.0),
                    path="DailyLevelUI(Clone)/stage",
                )

            def daily_selected_stage_visible(self, index):
                return True

        oracle = Oracle()
        adapter = AlasSemanticAdapter(oracle, lambda: None)
        adapter._daily_kind = "fierce_assault"

        adapter.click_daily_stage(1)
        selected = adapter.click_daily_stage(1)
        self.assertEqual(selected.semantic_id, "daily/stage/1")
        self.assertEqual(adapter.click_daily_stage(1), selected)
        self.assertEqual(oracle.clicks, 1)

    def test_daily_result_accepts_a_proven_transition_during_frame_refresh(self):
        class Oracle:
            page_reads = 0

            def daily_page_visible(self):
                self.page_reads += 1
                return self.page_reads > 1

            def daily_battle_result_visible(self):
                return True

            def click_daily_battle_result(self):
                raise SemanticGateClosed("daily battle result is absent")

        adapter = AlasSemanticAdapter(Oracle(), lambda: None)
        adapter._refresh_tactical_input_frame = lambda: None

        self.assertEqual(adapter.complete_daily_battle_result(), ())

    def test_daily_result_reobserves_after_a_stale_transition_frame(self):
        class Oracle:
            page_reads = 0

            def daily_page_visible(self):
                self.page_reads += 1
                return self.page_reads > 1

            def daily_battle_result_visible(self):
                return True

        adapter = AlasSemanticAdapter(Oracle(), lambda: None)
        adapter._refresh_tactical_input_frame = lambda: (_ for _ in ()).throw(
            StaleFrameError()
        )

        self.assertEqual(adapter.complete_daily_battle_result(), ())


if __name__ == "__main__":
    unittest.main()
