import ast
import unittest
from pathlib import Path
from alas_headless.alas_guild_config_contract import validate_alas_guild_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_guild_config import verify_clean_upstream

ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")

class AlasGuildConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/guild/guild_reward.py").is_file(): self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"]); self.assertEqual(result["field_count"], 9); self.assertGreater(result["accepted_case_count"], 64); self.assertEqual(result["mutation_budget"], 0); self.assertFalse(result["android_input_injected"])
    def test_bounds_and_type_errors_fail_closed(self):
        values = dict(logistics_enable=True, logistics_select_new_mission=False, logistics_exchange_filter="Coin", operation_enable=True, operation_select_new_operation=False, operation_new_operation_max_date=15, operation_join_threshold=1, operation_attack_boss=True, operation_boss_fleet_recommend=False)
        for key, value in (("operation_new_operation_max_date", 32), ("operation_join_threshold", 1.1), ("operation_attack_boss", 1)):
            with self.subTest(key=key), self.assertRaises(SemanticGateClosed):
                candidate = dict(values); candidate[key] = value; validate_alas_guild_config(**candidate)
    def test_sources_compile(self):
        for relative in ("python/alas_headless/alas_guild_config_contract.py", "python/alas_headless/alas_guild_config_replay.py", "scripts/python/verify_alas_guild_config.py"):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))
