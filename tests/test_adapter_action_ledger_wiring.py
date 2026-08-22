import ast
import unittest
from pathlib import Path

from alas_headless import (
    ActionReceipt,
    Bounds,
    Point,
    SemanticGateClosed,
)
from alas_headless.adapter import (
    ACTION_CAPABILITIES,
    ActionLedger,
    DEFAULT_CAPABILITY_INVENTORY,
    RecoveryPolicy,
    StaleFrameError,
    compatibility_policy_sha256,
    compatibility_profile,
)
from alas_headless.alas_adapter import AlasSemanticAdapter
from alas_headless.semantic_oracle import OperationSirenDaemonTarget


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

    @staticmethod
    def _opsi_adapter(oracle, grants=None):
        if grants is None:
            return AlasSemanticAdapter(oracle, lambda: None)
        profile = compatibility_profile("opsi-runtime", grants)
        ledger = ActionLedger(
            profile=profile,
            inventory=DEFAULT_CAPABILITY_INVENTORY,
            grants=grants,
            recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
            policy_sha256=compatibility_policy_sha256(
                "opsi-runtime", grants
            ),
        )
        return AlasSemanticAdapter(
            oracle,
            lambda: None,
            action_ledger=ledger,
        )

    def test_opsi_resource_and_daemon_actions_default_to_zero_authority(self):
        class Oracle:
            calls = []

            def click_operation_siren_action_point_control(self, use):
                self.calls.append(("action_point", use))
                return self.receipt("os/action-point/use")

            def click_operation_siren_port_repair(self, confirm):
                self.calls.append(("port_repair", confirm))
                return self.receipt("os/port/dock/repair-confirm")

            def click_operation_siren_daemon_target(self, target):
                self.calls.append(("daemon_move", target.relative_position))
                return self.receipt("os/map/grid/relative/-1/0")

            @staticmethod
            def receipt(semantic_id):
                return ActionReceipt(
                    semantic_id=semantic_id,
                    generation=7,
                    point=Point(640.0, 360.0),
                    bounds=Bounds(600.0, 320.0, 680.0, 400.0),
                    path="root/target",
                )

        oracle = Oracle()
        adapter = self._opsi_adapter(oracle)
        target = OperationSirenDaemonTarget(
            generation=7,
            target_kind="enemy",
            source_position=(-1, 0),
            relative_position=(-1, 0),
        )

        self.assertFalse(adapter.operation_siren_action_point_use_allowed())
        self.assertFalse(adapter.operation_siren_port_repair_allowed())
        self.assertFalse(adapter.operation_siren_daemon_move_allowed())
        with self.assertRaisesRegex(SemanticGateClosed, "action point use"):
            adapter.click_operation_siren_action_point_control(True)
        with self.assertRaisesRegex(SemanticGateClosed, "port repair"):
            adapter.click_operation_siren_port_repair(True)
        with self.assertRaisesRegex(SemanticGateClosed, "daemon movement"):
            adapter.click_operation_siren_daemon_target(target)
        self.assertEqual(oracle.calls, [])

        adapter.click_operation_siren_action_point_control(False)
        adapter.click_operation_siren_port_repair(False)
        self.assertEqual(
            oracle.calls,
            [("action_point", False), ("port_repair", False)],
        )

    def test_opsi_resource_and_daemon_actions_consume_single_typed_grants(self):
        class Oracle:
            calls = []

            @staticmethod
            def receipt(semantic_id):
                return ActionReceipt(
                    semantic_id=semantic_id,
                    generation=8,
                    point=Point(640.0, 360.0),
                    bounds=Bounds(600.0, 320.0, 680.0, 400.0),
                    path="root/target",
                )

            def click_operation_siren_action_point_control(self, use):
                self.calls.append("action_point")
                return self.receipt("os/action-point/use")

            def click_operation_siren_port_repair(self, confirm):
                self.calls.append("port_repair")
                return self.receipt("os/port/dock/repair-confirm")

            def click_operation_siren_daemon_target(self, target):
                self.calls.append("daemon_move")
                return self.receipt("os/map/grid/relative/-1/0")

        oracle = Oracle()
        grants = {
            "operation_siren.action_point_use": 1,
            "operation_siren.port_repair": 1,
            "operation_siren.daemon_move": 1,
        }
        adapter = self._opsi_adapter(oracle, grants)
        target = OperationSirenDaemonTarget(
            generation=8,
            target_kind="enemy",
            source_position=(-1, 0),
            relative_position=(-1, 0),
        )

        receipts = (
            adapter.click_operation_siren_action_point_control(True),
            adapter.click_operation_siren_port_repair(True),
            adapter.click_operation_siren_daemon_target(target),
        )
        self.assertEqual(
            tuple(receipt.capability_id for receipt in receipts),
            tuple(grants),
        )
        self.assertEqual(oracle.calls, ["action_point", "port_repair", "daemon_move"])
        with self.assertRaises(SemanticGateClosed):
            adapter.click_operation_siren_action_point_control(True)
        with self.assertRaises(SemanticGateClosed):
            adapter.click_operation_siren_port_repair(True)
        with self.assertRaises(SemanticGateClosed):
            adapter.click_operation_siren_daemon_target(target)
        self.assertEqual(oracle.calls, ["action_point", "port_repair", "daemon_move"])

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
