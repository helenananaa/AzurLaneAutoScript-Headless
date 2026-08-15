import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace

from alas_headless.alas_guild_shop_config_contract import (
    GUILD_SHOP_SECONDARY_CHOICES,
    validate_alas_guild_shop_filter,
    validate_alas_guild_shop_refresh,
    validate_alas_guild_shop_secondary_choices,
)
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_guild_shop_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")
FILTER_CONTRACT = SimpleNamespace(
    regex=re.compile(
        r"^(plate(general|gun|torpedo|antiair|plane)?t[2-4]|bookt[23]|pr|cat(general|t[23])?|chip|retrofit|foodt[56]|box(general|t[34])?)$",
        flags=re.IGNORECASE,
    )
)
SECONDARY_DEFAULTS = {
    field: choices[0] for field, choices in GUILD_SHOP_SECONDARY_CHOICES.items()
}


class AlasGuildShopConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/shop/shop_guild.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 14)
        self.assertEqual(result["accepted_case_count"], 56)
        self.assertEqual(result["invalid_case_count"], 37)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["real_purchase_performed"])
        self.assertFalse(result["real_refresh_performed"])
        self.assertFalse(result["android_input_injected"])

    def test_valid_values_are_accepted(self):
        for refresh in (False, True):
            self.assertIs(validate_alas_guild_shop_refresh(refresh=refresh), refresh)
        for value in ("PlateT4 > BookT3 > PR", " PlateT4 ＞ FoodT6 ", " \n "):
            self.assertEqual(
                validate_alas_guild_shop_filter(filter_=FILTER_CONTRACT, value=value),
                value,
            )
        for field, choices in GUILD_SHOP_SECONDARY_CHOICES.items():
            for choice in choices:
                values = dict(SECONDARY_DEFAULTS)
                values[field] = choice
                snapshot = validate_alas_guild_shop_secondary_choices(
                    **{key.lower(): value for key, value in values.items()}
                )
                self.assertEqual(getattr(snapshot, field.lower()), choice)

    def test_invalid_values_fail_closed(self):
        for value in ("true", None, 0, 1, [], {}):
            with self.subTest(field="refresh", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_guild_shop_refresh(refresh=value)
        for value in ("PlateT4 > invalid", "PlateT4 >", None, True, 1, [], {}):
            with self.subTest(field="filter", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_guild_shop_filter(filter_=FILTER_CONTRACT, value=value)
        for field in GUILD_SHOP_SECONDARY_CHOICES:
            for value in ("invalid", None):
                values = dict(SECONDARY_DEFAULTS)
                values[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_guild_shop_secondary_choices(
                        **{key.lower(): choice for key, choice in values.items()}
                    )

    def test_patch_gates_guild_shop_entry_decisions(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0060-shop-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertIn("diff --git a/module/shop/shop_guild.py", patch)
        self.assertEqual(patch.count("validate_alas_guild_shop_refresh("), 1)
        self.assertEqual(patch.count("validate_alas_guild_shop_filter("), 1)
        self.assertEqual(patch.count("validate_alas_guild_shop_secondary_choices("), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_guild_shop_config_contract.py",
            "python/alas_headless/alas_guild_shop_config_replay.py",
            "scripts/python/verify_alas_guild_shop_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
