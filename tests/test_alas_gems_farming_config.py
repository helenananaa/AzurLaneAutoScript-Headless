import ast
import unittest
from pathlib import Path
from alas_headless.alas_gems_farming_config_contract import validate_alas_gems_farming_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_gems_farming_config import verify_clean_upstream

ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")

class AlasGemsFarmingConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/campaign/gems_farming.py").is_file(): self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"]); self.assertEqual(result["field_count"], 5); self.assertEqual(result["accepted_case_count"], 300); self.assertEqual(result["mutation_budget"], 0); self.assertFalse(result["android_input_injected"])
    def test_bounds_and_type_errors_fail_closed(self):
        values = dict(change_flagship="ship", common_cv="any", change_vanguard="ship", common_dd="any", commission_limit=True)
        for key, value in (("change_flagship", "all"), ("common_cv", None), ("change_vanguard", True), ("common_dd", "dd"), ("commission_limit", 0)):
            with self.subTest(key=key), self.assertRaises(SemanticGateClosed):
                candidate = dict(values); candidate[key] = value; validate_alas_gems_farming_config(**candidate)
    def test_sources_compile(self):
        for relative in ("python/alas_headless/alas_gems_farming_config_contract.py", "python/alas_headless/alas_gems_farming_config_replay.py", "scripts/python/verify_alas_gems_farming_config.py"):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))
