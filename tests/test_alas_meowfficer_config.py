import ast
import unittest
from pathlib import Path
from alas_headless.alas_meowfficer_config_contract import validate_alas_meowfficer_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_meowfficer_config import verify_clean_upstream

ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"E:\Disk0Merged\H\program\AzurLaneAutoScript-upstream-readonly")

class AlasMeowfficerConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/meowfficer/meowfficer.py").is_file(): self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"]); self.assertEqual(result["field_count"], 9); self.assertGreaterEqual(result["accepted_case_count"], 18); self.assertEqual(result["mutation_budget"], 0); self.assertFalse(result["android_input_injected"])
    def test_bounds_and_type_errors_fail_closed(self):
        values = dict(buy_amount=1, fort_chore_meowfficer=True, overflow_coins=-1, train_enable=True, train_mode="seamlessly", retain_talented_gold=True, retain_talented_purple=True, enhance_index=1, max_feed_level=5)
        for key, value in (("buy_amount", True), ("overflow_coins", -2), ("train_mode", "invalid"), ("enhance_index", 0), ("max_feed_level", "31")):
            with self.subTest(key=key), self.assertRaises(SemanticGateClosed):
                candidate = dict(values); candidate[key] = value; validate_alas_meowfficer_config(**candidate)
    def test_disabled_training_leaves_purchase_and_fort_configuration_usable(self):
        values = dict(
            buy_amount=1, fort_chore_meowfficer=True, overflow_coins=-1,
            train_enable=False, train_mode="obsolete-mode",
            retain_talented_gold=None, retain_talented_purple="obsolete",
            enhance_index=None, max_feed_level=999,
        )
        snapshot = validate_alas_meowfficer_config(**values)
        self.assertEqual(snapshot.buy_amount, 1)
        self.assertTrue(snapshot.fort_chore_meowfficer)
        for field in ("train_mode", "retain_talented_gold", "retain_talented_purple",
                      "enhance_index", "max_feed_level"):
            self.assertIsNone(getattr(snapshot, field))
        with self.assertRaises(SemanticGateClosed):
            validate_alas_meowfficer_config(**{**values, "train_enable": True})
    def test_sources_compile(self):
        for relative in ("python/alas_headless/alas_meowfficer_config_contract.py", "python/alas_headless/alas_meowfficer_config_replay.py", "scripts/python/verify_alas_meowfficer_config.py"):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))
