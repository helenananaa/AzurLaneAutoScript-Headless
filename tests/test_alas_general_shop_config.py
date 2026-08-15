import ast
import unittest
from pathlib import Path

from alas_headless.alas_general_shop_config_contract import (
    validate_alas_general_shop_custom_items_config,
    validate_alas_general_shop_refresh,
    validate_alas_general_shop_use_gems,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_general_shop_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasGeneralShopConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/shop/shop_general.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 4)
        self.assertEqual(result["accepted_case_count"], 8)
        self.assertEqual(result["invalid_case_count"], 24)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_purchase_performed"])
        self.assertFalse(result["android_input_injected"])

    def test_boolean_combinations_are_accepted(self):
        for consume_coins in (False, True):
            for buy_skin_box in (False, True):
                with self.subTest(
                    consume_coins=consume_coins,
                    buy_skin_box=buy_skin_box,
                ):
                    snapshot = validate_alas_general_shop_custom_items_config(
                        consume_coins=consume_coins,
                        buy_skin_box=buy_skin_box,
                    )
                    self.assertIs(snapshot.consume_coins, consume_coins)
                    self.assertIs(snapshot.buy_skin_box, buy_skin_box)
        for use_gems in (False, True):
            self.assertIs(
                validate_alas_general_shop_use_gems(use_gems=use_gems),
                use_gems,
            )
        for refresh in (False, True):
            self.assertIs(
                validate_alas_general_shop_refresh(refresh=refresh),
                refresh,
            )

    def test_invalid_values_fail_closed(self):
        for field in ("consume_coins", "buy_skin_box"):
            for value in ("true", None, 0, 1, [], {}):
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_general_shop_custom_items_config(
                        consume_coins=value if field == "consume_coins" else False,
                        buy_skin_box=value if field == "buy_skin_box" else False,
                    )
        for value in ("true", None, 0, 1, [], {}):
            with self.subTest(field="use_gems", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_general_shop_use_gems(use_gems=value)
        for value in ("true", None, 0, 1, [], {}):
            with self.subTest(field="refresh", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_general_shop_refresh(refresh=value)

    def test_patch_gates_custom_item_predicate(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0060-shop-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("diff --git a/module/shop/shop_general.py", patch)
        self.assertEqual(
            patch.count("validate_alas_general_shop_custom_items_config("),
            1,
        )
        self.assertEqual(patch.count("validate_alas_general_shop_use_gems("), 1)
        self.assertEqual(patch.count("validate_alas_general_shop_refresh("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_general_shop_config_contract.py",
            "python/alas_headless/alas_general_shop_config_replay.py",
            "scripts/python/verify_alas_general_shop_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
