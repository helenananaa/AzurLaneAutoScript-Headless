from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alas_headless.android_foundation_audit import AUDIT_SCHEMA
from alas_headless.android_image_slimming import qualify_slimming_change
from alas_headless.android_image_supply_chain import PROVENANCE_SCHEMA


class AndroidImageSlimmingTests(unittest.TestCase):
    def evidence(self, directory: Path):
        baseline_inventory = directory / "baseline.txt"
        candidate_inventory = directory / "candidate.txt"
        baseline_inventory.write_text("system/bin/init\nsystem/app/removable.apk\n", encoding="utf-8")
        candidate_inventory.write_text("system/bin/init\n", encoding="utf-8")
        def provenance(size):
            return {
                "schema": PROVENANCE_SCHEMA, "source_lock_sha256": "a" * 64,
                "target": {"abi": "arm64-v8a"},
                "artifacts": {"system.img": {"bytes": size}, "vendor.img": {"bytes": 10}},
                "game_artifact_included": False, "alas_workload_used": False,
            }
        scoped_pass = {"outcome": "pass", "game_installed": False, "alas_workload_used": False}
        audit = dict(scoped_pass, schema=AUDIT_SCHEMA, identity={"abi_list": "arm64-v8a"})
        return baseline_inventory, candidate_inventory, provenance(100), provenance(80), scoped_pass, audit

    def test_single_declared_removal_with_all_gates_passes(self) -> None:
        with TemporaryDirectory() as raw:
            paths = self.evidence(Path(raw))
            baseline_i, candidate_i, baseline, candidate, passed, audit = paths
            result = qualify_slimming_change(
                {"change_id": "remove-one", "hypothesis": "save bytes",
                 "allowed_removed_files": ["system/app/removable.apk"],
                 "alas_workload_required": False},
                baseline, candidate, baseline_i, candidate_i, audit,
                {name: passed for name in ("gles-contract", "unity-contract", "observer-contract")},
                passed, passed,
            )
            self.assertEqual(result["outcome"], "pass")
            self.assertEqual(result["saved_payload_bytes"], 20)

    def test_undeclared_removal_and_failed_gate_block(self) -> None:
        with TemporaryDirectory() as raw:
            baseline_i, candidate_i, baseline, candidate, passed, audit = self.evidence(Path(raw))
            failed = dict(passed, outcome="blocked")
            result = qualify_slimming_change(
                {"change_id": "remove-one", "hypothesis": "save bytes",
                 "allowed_removed_files": [], "alas_workload_required": False},
                baseline, candidate, baseline_i, candidate_i, audit,
                {"gles-contract": failed, "unity-contract": passed, "observer-contract": passed},
                passed, passed,
            )
            self.assertIn("unexpected-files-removed", result["blockers"])
            self.assertIn("gles-contract-not-pass", result["blockers"])

    def test_no_size_reduction_blocks_cosmetic_pruning_claim(self) -> None:
        with TemporaryDirectory() as raw:
            baseline_i, candidate_i, baseline, candidate, passed, audit = self.evidence(Path(raw))
            candidate["artifacts"]["system.img"]["bytes"] = 100
            result = qualify_slimming_change(
                {"change_id": "remove-one", "hypothesis": "save bytes",
                 "allowed_removed_files": ["system/app/removable.apk"],
                 "alas_workload_required": False},
                baseline, candidate, baseline_i, candidate_i, audit,
                {name: passed for name in ("gles-contract", "unity-contract", "observer-contract")},
                passed, passed,
            )
            self.assertIn("payload-size-not-reduced", result["blockers"])


if __name__ == "__main__":
    unittest.main()
