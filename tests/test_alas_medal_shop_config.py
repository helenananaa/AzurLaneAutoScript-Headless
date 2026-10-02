import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from alas_headless.alas_medal_shop_config_contract import (
    MEDAL_SHOP_SECONDARY_CHOICES,
    validate_alas_medal_shop_filter,
    validate_alas_medal_shop_secondary_choices,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_medal_shop_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")
FILTER_CONTRACT = SimpleNamespace(
    regex=re.compile(
        r"^(dr|pr|book(red|yellow|blue)t[23]|retrofit|foodt[56]|plate(general|wild)?t[1-3])$",
        flags=re.IGNORECASE,
    )
)
SECONDARY_DEFAULTS = {
    field: choices[0] for field, choices in MEDAL_SHOP_SECONDARY_CHOICES.items()
}


class AlasMedalShopConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/shop/shop_medal.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 7)
        self.assertEqual(result["accepted_case_count"], 30)
        self.assertEqual(result["invalid_case_count"], 19)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_purchase_performed"])
        self.assertFalse(result["real_refresh_performed"])
        self.assertFalse(result["android_input_injected"])

    def test_valid_values_are_accepted(self):
        for value in ("DR > PR > BookRedT3", " DR ＞ FoodT6 ", " \n ", ">", " ＞ "):
            self.assertEqual(
                validate_alas_medal_shop_filter(filter_=FILTER_CONTRACT, value=value),
                value,
            )
        for field, choices in MEDAL_SHOP_SECONDARY_CHOICES.items():
            for choice in choices:
                values = dict(SECONDARY_DEFAULTS)
                values[field] = choice
                snapshot = validate_alas_medal_shop_secondary_choices(
                    **{key.lower(): value for key, value in values.items()}
                )
                self.assertEqual(getattr(snapshot, field.lower()), choice)

    def test_invalid_values_fail_closed(self):
        for value in ("DR > invalid", "DR >", None, True, 1, [], {}):
            with self.subTest(field="filter", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_medal_shop_filter(filter_=FILTER_CONTRACT, value=value)
        for field in MEDAL_SHOP_SECONDARY_CHOICES:
            for value in ("invalid", None):
                values = dict(SECONDARY_DEFAULTS)
                values[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_medal_shop_secondary_choices(
                        **{key.lower(): choice for key, choice in values.items()}
                    )

    def test_patch_gates_medal_shop_entry_decisions(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0060-shop-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("diff --git a/module/shop/shop_medal.py", patch)
        self.assertEqual(patch.count("validate_alas_medal_shop_filter("), 1)
        self.assertEqual(patch.count("validate_alas_medal_shop_secondary_choices("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_medal_shop_config_contract.py",
            "python/alas_headless/alas_medal_shop_config_replay.py",
            "scripts/python/verify_alas_medal_shop_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
