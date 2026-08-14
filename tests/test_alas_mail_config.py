import ast
import unittest
from pathlib import Path

from alas_headless.alas_mail_config_contract import validate_alas_mail_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]


class AlasMailConfigTests(unittest.TestCase):
    def test_all_boolean_combinations_are_classified(self):
        for mask in range(16):
            values = [bool(mask & (1 << bit)) for bit in range(4)]
            snapshot = validate_alas_mail_config(
                claim_merit=values[0],
                claim_maintenance=values[1],
                claim_trade_license=values[2],
                delete_collected=values[3],
            )
            self.assertEqual(snapshot.has_claim_selection, any(values[:3]))

    def test_non_boolean_values_fail_closed(self):
        for value in (None, 0, 1, "true"):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_mail_config(
                    claim_merit=value,
                    claim_maintenance=False,
                    claim_trade_license=False,
                    delete_collected=False,
                )

    def test_patch_validates_before_mail_context_and_navigation(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0010-mission-mail-flow-ports.patch"
        ).read_text(encoding="utf-8")
        validation = patch.index("semantic_adapter.validate_mail_config(")
        self.assertLess(validation, patch.index("semantic_adapter.begin_mail()"))
        self.assertLess(validation, patch.index("self.ui_ensure("))

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_mail_config_contract.py",
            "python/alas_headless/alas_mail_config_replay.py",
            "scripts/python/verify_alas_mail_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
