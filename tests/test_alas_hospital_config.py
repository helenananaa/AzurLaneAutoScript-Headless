import ast
import unittest
from pathlib import Path

from alas_headless.alas_hospital_config_contract import validate_alas_hospital_config
from alas_headless.semantic_oracle import SemanticGateClosed
from scripts.python.verify_alas_hospital_config import verify_clean_upstream


ROOT = Path(__file__).resolve().parents[1]
PINNED_UPSTREAM = Path(r"H:\program\AzurLaneAutoScript-upstream-readonly")


class AlasHospitalConfigTests(unittest.TestCase):
    def test_exact_pinned_upstream_replay_when_available(self):
        if not PINNED_UPSTREAM.joinpath("module/event_hospital/combat.py").is_file():
            self.skipTest("local pinned ALAS verification tree is unavailable")
        result = verify_clean_upstream(PINNED_UPSTREAM)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 1)
        self.assertEqual(result["accepted_case_count"], 2)
        self.assertEqual(result["invalid_case_count"], 7)
        self.assertEqual(result["mutation_budget"], 0)
        self.assertEqual(result["fleet_recommend_actions"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_only_real_booleans_are_admitted(self):
        self.assertTrue(validate_alas_hospital_config(use_recommend_fleet=True).use_recommend_fleet)
        self.assertFalse(validate_alas_hospital_config(use_recommend_fleet=False).use_recommend_fleet)
        for value in (None, 0, 1, "true", [], {}):
            with self.subTest(value=value), self.assertRaises(SemanticGateClosed):
                validate_alas_hospital_config(use_recommend_fleet=value)

    def test_patch_gates_before_hospital_ui_and_preparation_loop(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0165-hospital-config-contract.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_hospital_config("), 2)
        preparation_guard = patch.index("validate_alas_hospital_config(")
        run_guard = patch.rindex("validate_alas_hospital_config(")
        self.assertLess(run_guard, patch.index("if self.event_time_limit_triggered()"))
        self.assertLess(preparation_guard, patch.index("self.handle_fleet_recommend"))

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_hospital_config_contract.py",
            "python/alas_headless/alas_hospital_config_replay.py",
            "scripts/python/verify_alas_hospital_config.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
