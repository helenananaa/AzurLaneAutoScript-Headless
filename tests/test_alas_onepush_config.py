import ast
import unittest
from pathlib import Path

from alas_headless.alas_onepush_config_contract import validate_alas_onepush_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_onepush_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasOnePushConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/notify/notify.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 1)
        self.assertEqual(result["accepted_case_count"], 4)
        self.assertEqual(result["invalid_case_count"], 9)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertEqual(result["network_requests"], 0)
        self.assertEqual(result["notification_deliveries"], 0)

    def test_valid_values_preserve_yaml_mapping_streams(self):
        self.assertEqual(
            validate_alas_onepush_config("---\nprovider: mock\n---\ntoken: secret"),
            {"provider": "mock", "token": "secret"},
        )
        self.assertEqual(validate_alas_onepush_config("provider: null"), {"provider": None})

    def test_invalid_values_close_before_provider_lookup(self):
        for value in (None, True, "[", "- item", "7: value", "provider: 7"):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_onepush_config(value)

    def test_patch_gates_onepush_parser_before_provider_lookup(self):
        patch = ROOT.joinpath("integration/alas/series/0001-core-ports.patch").read_text(
            encoding="utf-8"
        )
        self.assertEqual(patch.count("validate_alas_onepush_config(_config)"), 1)

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_onepush_config_contract.py",
            "python/alas_headless/alas_onepush_config_replay.py",
            "scripts/python/verify_alas_onepush_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
