import ast
import unittest
from pathlib import Path

from alas_headless.adapter import ACTION_CAPABILITIES


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


if __name__ == "__main__":
    unittest.main()
