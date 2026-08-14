import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts.python.audit_alas_adapter_baseline import (
    AdapterBaselineError,
    ROOT,
    canonical_json,
    collect_baseline,
    require_clean_repository,
    tracked_source_paths,
    validate_baseline_document,
)


COMMIT = "a" * 40


class AlasAdapterBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.document = collect_baseline(
            ROOT,
            core_commit=COMMIT,
            tracked_paths=tracked_source_paths(ROOT),
        )

    def test_current_source_inventory_is_exact_and_fail_closed(self):
        document = self.document
        self.assertEqual(document["schema"], "alas-headless.adapter-baseline/v1")
        self.assertEqual(
            document["upstream_alas_commit"],
            "81ccf63b4540f00241628c82a58c02c7a2bb11af",
        )
        self.assertEqual(document["integration_patch"]["changed_file_count"], 96)
        self.assertGreater(document["integration_patch"]["line_count"], 1_000)
        self.assertGreater(
            document["source_metrics"]["alas_adapter"]["line_count"],
            5_000,
        )
        self.assertGreater(
            document["source_metrics"]["semantic_oracle"]["line_count"],
            7_000,
        )
        self.assertEqual(
            document["artifact_sha256"]["patch_series_manifest"],
            "3ea19984b01e60d2320be37a1986380a18ebfaf891144a2fa098cd5b8e86351c",
        )
        self.assertIn(
            "appear",
            document["public_adapter_methods"]["AlasSemanticAdapter"],
        )
        self.assertIn(
            "from_environment",
            document["public_adapter_methods"]["AlasSemanticSession"],
        )
        self.assertIn(
            "ALAS_SEMANTIC_MODE",
            document["semantic_environment_variables"],
        )
        self.assertEqual(
            document["semantic_environment_variables"],
            sorted(set(document["semantic_environment_variables"])),
        )
        self.assertEqual(
            document["combat_coverage"],
            {
                "canonical_resources": 41,
                "canonical_qualified_resources": 18,
                "defensive_resources": 57,
                "defensive_qualified_resources": 23,
                "actions": 39,
                "qualified_actions": 15,
                "blockers": 4,
                "qualified_blockers": 1,
                "branch_review_complete": False,
                "blocker_review_complete": False,
                "fleet_stats_qualified": True,
                "production_ready": False,
            },
        )

    def test_canonical_output_is_byte_stable_and_key_order_independent(self):
        first = canonical_json(self.document)
        reversed_document = dict(reversed(tuple(self.document.items())))
        second = canonical_json(reversed_document)
        self.assertEqual(first, second)
        self.assertEqual(first, canonical_json(json.loads(first)))
        self.assertTrue(first.endswith("\n"))
        self.assertNotIn(str(ROOT), first)

    def test_document_rejects_absolute_paths_timestamps_and_dirty_state(self):
        for field, value in (
            ("dirty", True),
            ("captured_at_utc", "2026-08-12T00:00:00Z"),
            ("git_status", "M python/alas_headless/alas_adapter.py"),
            ("working_tree", "H:\\program\\adapter"),
        ):
            with self.subTest(field=field):
                document = copy.deepcopy(self.document)
                document["source_metrics"][field] = value
                with self.assertRaises(AdapterBaselineError):
                    validate_baseline_document(document)

    def test_document_rejects_missing_identity_and_malformed_coverage(self):
        missing = copy.deepcopy(self.document)
        missing["upstream_alas_commit"] = ""
        with self.assertRaisesRegex(AdapterBaselineError, "identity"):
            validate_baseline_document(missing)

        malformed = copy.deepcopy(self.document)
        malformed["combat_coverage"]["qualified_actions"] = (
            malformed["combat_coverage"]["actions"] + 1
        )
        with self.assertRaisesRegex(AdapterBaselineError, "count"):
            validate_baseline_document(malformed)

        boolean_count = copy.deepcopy(self.document)
        boolean_count["combat_coverage"]["qualified_blockers"] = True
        with self.assertRaisesRegex(AdapterBaselineError, "count"):
            validate_baseline_document(boolean_count)

    def test_output_contains_no_absolute_paths_or_timestamps(self):
        text = canonical_json(self.document)
        self.assertNotIn("H:\\", text)
        self.assertNotIn("/home/", text)
        self.assertNotIn("captured_at", text)
        self.assertNotIn("timestamp", text)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.json"
            path.write_text(text, encoding="utf-8")
            self.assertEqual(path.read_text(encoding="utf-8"), text)

    def test_repository_admission_requires_clean_canonical_commit(self):
        with mock.patch(
            "scripts.python.audit_alas_adapter_baseline._git",
            side_effect=[COMMIT, ""],
        ):
            self.assertEqual(require_clean_repository(ROOT), COMMIT)

        with mock.patch(
            "scripts.python.audit_alas_adapter_baseline._git",
            side_effect=[COMMIT, " M python/alas_headless/alas_adapter.py"],
        ):
            with self.assertRaisesRegex(AdapterBaselineError, "must be clean"):
                require_clean_repository(ROOT)

        with mock.patch(
            "scripts.python.audit_alas_adapter_baseline._git",
            return_value="not-a-commit",
        ):
            with self.assertRaisesRegex(AdapterBaselineError, "commit"):
                require_clean_repository(ROOT)


if __name__ == "__main__":
    unittest.main()
