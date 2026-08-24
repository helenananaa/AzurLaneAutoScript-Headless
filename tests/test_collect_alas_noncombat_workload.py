import argparse
import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "python" / "collect_alas_noncombat_workload.py"
SPEC = importlib.util.spec_from_file_location("collect_noncombat_workload", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC is not None and SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class NoncombatWorkloadCollectorTests(unittest.TestCase):
    def test_profile_registry_contains_only_zero_resource_profiles(self):
        self.assertEqual(
            set(MODULE.PROFILE_DEFINITIONS),
            {"semantic-io", "reward-readonly", "restart-warm", "idle-soak"},
        )
        self.assertEqual(
            set(MODULE.PROFILE_DEFINITIONS), set(MODULE.RUNNER_FACTORIES)
        )
        self.assertTrue(
            all(
                definition["in_game_resource_mutation_expected"] is False
                for definition in MODULE.PROFILE_DEFINITIONS.values()
            )
        )

    def test_idle_metadata_keeps_duration_in_workload_identity(self):
        args = argparse.Namespace(profile="idle-soak", idle_duration_seconds=1800.0)
        actual = MODULE.workload_metadata(args)
        self.assertEqual(actual["id"], "idle-soak")
        self.assertEqual(actual["duration_seconds"], 1800.0)

    def test_preflight_is_recorded_as_outside_measurement(self):
        preflight = {
            "performed": True,
            "measurement_included": False,
            "postcondition": "unobstructed-typed-main",
        }
        args = argparse.Namespace(
            profile="idle-soak",
            idle_duration_seconds=30.0,
            preflight=preflight,
        )
        actual = MODULE.workload_metadata(args)
        self.assertEqual(actual["preflight"], preflight)
        self.assertFalse(actual["preflight"]["measurement_included"])

    def test_reward_receipt_counts_original_dispatch_evidence(self):
        args = argparse.Namespace(profile="reward-readonly")
        result = {
            "passed": True,
            "run_id": "run-2",
            "workload": {"id": "reward-readonly"},
            "device": {"serial": "emulator-5580"},
            "safety": {"in_game_resource_mutation_expected": False},
            "runner_result": {
                "cases": [
                    {"dispatches": []},
                    {"dispatches": []},
                ]
            },
        }
        receipt = MODULE.resource_receipt_for(args, result)
        self.assertEqual(receipt["observed_mutation_dispatches"], 0)
        self.assertTrue(receipt["zero_resource_contract_passed"])

    def test_semantic_io_receipt_is_honest_about_unobserved_counters(self):
        args = argparse.Namespace(profile="semantic-io")
        result = {
            "passed": True,
            "run_id": "run-3",
            "workload": {"id": "semantic-io"},
            "device": {"serial": "emulator-5580"},
            "safety": {"in_game_resource_mutation_expected": False},
            "runner_result": {"passed": True},
        }
        receipt = MODULE.resource_receipt_for(args, result)
        self.assertIsNone(receipt["observed_mutation_dispatches"])
        self.assertFalse(receipt["resource_counters_directly_observed"])


if __name__ == "__main__":
    unittest.main()
