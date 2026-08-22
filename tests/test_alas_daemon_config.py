import ast
import itertools
import json
import unittest
from pathlib import Path

from alas_headless.alas_daemon_config_contract import (
    validate_alas_daemon_config,
    validate_alas_opsi_daemon_config,
)
from alas_headless.alas_daemon_config_replay import verify_daemon_config
from alas_headless.semantic_oracle import SemanticGateClosed


ROOT = Path(__file__).resolve().parents[1]
LIVE_ALAS = Path(r"H:\program\AzurLaneAutoScript-alas-topdown-live")


class AlasDaemonConfigTests(unittest.TestCase):
    def test_exact_live_tree_replay_when_available(self):
        if not LIVE_ALAS.joinpath("module/daemon/daemon.py").is_file():
            self.skipTest("local pinned/patched ALAS verification tree is unavailable")
        result = verify_daemon_config(LIVE_ALAS)
        self.assertTrue(result["passed"])
        self.assertEqual(result["field_count"], 3)
        self.assertEqual(result["accepted_case_count"], 6)
        self.assertEqual(result["invalid_case_count"], 21)
        self.assertEqual(result["daemon_cases"]["disabled"]["result"], "waiting")
        self.assertEqual(result["opsi_cases"]["repair"]["result"], "port_repair")
        self.assertEqual(result["opsi_cases"]["select"]["result"], "nearest_object")
        self.assertEqual(result["mutation_budget"], 0)
        self.assertFalse(result["android_input_injected"])

    def test_all_boolean_combinations_are_classified(self):
        for value in (False, True):
            self.assertEqual(
                validate_alas_daemon_config(enter_map=value).enter_map, value
            )
        for repair_ship, select_enemy in itertools.product((False, True), repeat=2):
            snapshot = validate_alas_opsi_daemon_config(
                repair_ship=repair_ship, select_enemy=select_enemy
            )
            self.assertEqual(
                (snapshot.opsi_repair_ship, snapshot.opsi_select_enemy),
                (repair_ship, select_enemy),
            )

    def test_invalid_single_fields_fail_closed(self):
        invalid = (0, 1, "true", "false", None, [], {})
        for value in invalid:
            with self.subTest(field="enter_map", value=value), self.assertRaises(
                SemanticGateClosed
            ):
                validate_alas_daemon_config(enter_map=value)
        for field in ("repair_ship", "select_enemy"):
            for value in invalid:
                case = {"repair_ship": True, "select_enemy": True}
                case[field] = value
                with self.subTest(field=field, value=value), self.assertRaises(
                    SemanticGateClosed
                ):
                    validate_alas_opsi_daemon_config(**case)

    def test_patch_gates_both_polling_entries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0100-tool-flow-ports.patch"
        ).read_text(encoding="utf-8")
        self.assertEqual(patch.count("validate_alas_daemon_config("), 1)
        self.assertEqual(patch.count("validate_alas_opsi_daemon_config("), 1)

    def test_phase2_runtime_patch_owns_typed_mutation_boundaries(self):
        patch = ROOT.joinpath(
            "integration/alas/series/0400-opsi-general-daemon-runtime.patch"
        ).read_text(encoding="utf-8")
        for marker in (
            "operation_siren_port_repair_allowed",
            "operation_siren_nearest_daemon_target",
            "click_operation_siren_daemon_target",
            "operation_siren_action_point_state",
            "oil_purchase_cost",
            "oil_purchase_points",
            "oil_purchase_remaining",
            "click_operation_siren_action_point_control(True)",
            "Typed oil action point purchase was not proven",
        ):
            self.assertIn(marker, patch)
        self.assertNotIn("ACTION_POINTS_BUY[current]", patch)

    def test_live_oil_transition_proof_is_exact(self):
        proof = json.loads(
            ROOT.joinpath(
                "integration/alas/opsi-general-daemon-oil-transition-proof-20260822.json"
            ).read_text(encoding="utf-8")
        )
        self.assertTrue(proof["passed"])
        self.assertTrue(all(proof["checks"].values()))
        transition = proof["transition"]
        self.assertEqual(
            transition["action_points"]["after"]
            - transition["action_points"]["before"],
            transition["ap_purchase_terms_before"]["points"],
        )
        self.assertEqual(
            transition["oil"]["before"] - transition["oil"]["after"],
            transition["ap_purchase_terms_before"]["cost"],
        )
        self.assertEqual(
            transition["weekly_remaining"]["before"]
            - transition["weekly_remaining"]["after"],
            1,
        )

    def test_sources_compile(self):
        for relative in (
            "python/alas_headless/alas_daemon_config_contract.py",
            "python/alas_headless/alas_daemon_config_replay.py",
            "scripts/python/verify_alas_daemon_config.py",
            "scripts/python/run_alas_opsi_general_daemon_live_validation.py",
            "scripts/python/verify_alas_opsi_action_point_transition.py",
        ):
            ast.parse(ROOT.joinpath(relative).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
