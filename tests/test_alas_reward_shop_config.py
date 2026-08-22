import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from alas_headless.alas_reward_shop_config_contract import (
    validate_alas_core_shop_filter,
    validate_alas_merit_shop_filter,
    validate_alas_merit_shop_refresh,
)
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")
FILTER = SimpleNamespace(
    regex=re.compile(r"^(array|cube|book(red|blue|yellow)?t[1-4])$", re.I)
)


class AlasRewardShopConfigTests(unittest.TestCase):
    def test_pinned_defaults_are_covered(self):
        path = PINNED_UPSTREAM / "module/config/config_generated.py"
        if not path.is_file():
            self.skipTest("pinned ALAS tree is unavailable")
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        expected = {
            "MeritShop_Refresh": False,
            "MeritShop_Filter": "Cube",
            "CoreShop_Filter": "Array",
        }
        observed = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in expected:
                    observed[target.id] = ast.literal_eval(node.value)
        self.assertEqual(observed, expected)

    def test_merit_and_core_contracts_accept_exact_values(self):
        self.assertEqual(
            validate_alas_merit_shop_filter(filter_=FILTER, value="Cube"), "Cube"
        )
        self.assertEqual(
            validate_alas_core_shop_filter(filter_=FILTER, value="Array"), "Array"
        )
        for refresh in (False, True):
            self.assertIs(
                validate_alas_merit_shop_refresh(refresh=refresh), refresh
            )

    def test_merit_and_core_contracts_fail_closed(self):
        for validator in (
            validate_alas_merit_shop_filter,
            validate_alas_core_shop_filter,
        ):
            for value in ("Cube > invalid", "Cube >", None, True, 1, [], {}):
                with self.subTest(validator=validator.__name__, value=value):
                    with self.assertRaises(SemanticGateClosed):
                        validator(filter_=FILTER, value=value)
        for value in ("false", None, 0, 1, [], {}):
            with self.subTest(refresh=value), self.assertRaises(SemanticGateClosed):
                validate_alas_merit_shop_refresh(refresh=value)

    def test_runtime_patch_guards_all_three_fields(self):
        path = ROOT / "integration/alas/series/0401-shop-transactions-runtime.patch"
        if not path.is_file():
            self.skipTest("phase-3 patch member has not been generated yet")
        patch = path.read_text(encoding="utf-8")
        self.assertIn("validate_alas_merit_shop_filter", patch)
        self.assertIn("validate_alas_merit_shop_refresh", patch)
        self.assertIn("validate_alas_core_shop_filter", patch)
        self.assertIn("refresh_shop_once", patch)


if __name__ == "__main__":
    unittest.main()
