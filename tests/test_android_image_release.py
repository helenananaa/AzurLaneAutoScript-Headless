from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alas_headless.android_image_release import build_release_manifest
from alas_headless.android_image_release import target_record


class FakePolicy:
    sha256 = "a" * 64


class AndroidImageReleaseTests(unittest.TestCase):
    def test_dual_target_clean_release_can_promote(self) -> None:
        target = {"blockers": [], "outcome": "platform-and-update-qualified"}
        value = build_release_manifest(
            FakePolicy(),
            {"commit": "b" * 40, "dirty": False},
            {"x86_64": target, "arm64-v8a": target},
        )
        self.assertEqual(value["promotion"]["outcome"], "pass")
        self.assertFalse(value["alas_workload_qualified"])
        self.assertFalse(value["game_artifact_included"])

    def test_missing_arm_evidence_and_dirty_source_block_promotion(self) -> None:
        value = build_release_manifest(
            FakePolicy(),
            {"commit": "b" * 40, "dirty": True},
            {
                "x86_64": {"blockers": [], "outcome": "platform-and-update-qualified"},
                "arm64-v8a": {"blockers": ["image-artifact-missing"], "outcome": "blocked"},
            },
        )
        self.assertEqual(value["promotion"]["outcome"], "blocked")
        self.assertIn("arm64-v8a:image-artifact-missing", value["promotion"]["blockers"])
        self.assertIn("source:dirty-worktree", value["promotion"]["blockers"])

    def test_target_set_is_exact(self) -> None:
        with self.assertRaises(ValueError):
            build_release_manifest(FakePolicy(), {"dirty": False}, {"x86_64": {}})

    def test_arm64_oci_identity_is_accepted_as_image_artifact(self) -> None:
        with TemporaryDirectory() as directory:
            apk = Path(directory) / "arm.apk"
            import zipfile

            with zipfile.ZipFile(apk, "w") as archive:
                archive.writestr("lib/arm64-v8a/libmarker.so", b"marker")
            evidence = {
                "schema": "test/v1",
                "outcome": "pass",
                "abi": "arm64-v8a",
                "game_installed": False,
                "alas_workload_used": False,
                "apk_sha256": None,
            }
            record = target_record(
                "arm64-v8a",
                apk,
                apk,
                None,
                {gate: evidence for gate in (
                    "gles-contract", "unity-contract", "observer-contract"
                )},
                None,
                None,
                {
                    "schema": "alas-headless.oci-image-identity/v1",
                    "manifest_digest": "sha256:" + "c" * 64,
                    "architecture": "arm64",
                    "immutable": True,
                },
            )
            self.assertNotIn("image-artifact-missing", record["blockers"])
            self.assertEqual(record["image_artifact"]["kind"], "oci")

    def test_oci_identity_fails_closed_on_architecture_and_tag(self) -> None:
        record = target_record(
            "arm64-v8a", None, None, None, {}, None, None,
            {
                "schema": "alas-headless.oci-image-identity/v1",
                "manifest_digest": "latest",
                "architecture": "amd64",
                "immutable": False,
            },
        )
        self.assertIn("image-identity-digest-invalid", record["blockers"])
        self.assertIn("image-identity-abi-mismatch", record["blockers"])
        self.assertIn("image-identity-not-immutable", record["blockers"])


if __name__ == "__main__":
    unittest.main()
