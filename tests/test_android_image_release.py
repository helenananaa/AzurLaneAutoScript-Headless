from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alas_headless.android_image_release import build_release_manifest
from alas_headless.android_image_release import target_record


class FakePolicy:
    sha256 = "a" * 64


def evidence_identity():
    return {"path": "/evidence.json", "bytes": 1, "sha256": "e" * 64}


def release_inputs(abi: str):
    source_lock = "c" * 64
    provenance = {
        "schema": "alas-headless.android-image-build-provenance/v1",
        "source_lock_sha256": source_lock,
        "target": {"abi": abi},
        "game_artifact_included": False,
        "alas_workload_used": False,
        "platform": "linux/arm64" if abi == "arm64-v8a" else "linux/amd64",
        "performance_claim_allowed": False,
        "resolved_manifest": {"sha256": "3" * 64, "bytes": 1},
        "artifacts": {
            "system.img": {"sha256": "4" * 64, "bytes": 1},
            "vendor.img": {"sha256": "5" * 64, "bytes": 1},
            "redroid-native-fbe-overlay.json": {"sha256": "9" * 64, "bytes": 1},
            "post-patch-state.json": {"sha256": "8" * 64, "bytes": 1},
        },
        "native_fbe_overlay": {
            "schema": "alas-headless.redroid-native-fbe-overlay-validation/v1",
            "outcome": "pass",
            "android_fbe_proven": False,
            "direct_boot_proven": False,
            "source_lock_sha256": source_lock,
            "artifact_sha256": "9" * 64,
        },
        "sbom": {"sha256": "6" * 64, "bytes": 1, "format": "SPDX-2.3"},
        "notices": [{"sha256": "7" * 64, "bytes": 1}],
        "installed_files": {"sha256": "8" * 64, "bytes": 1},
        "host_preflight": {"outcome": "pass"},
        "_evidence_file": evidence_identity(),
    }
    reproducibility = {
        "schema": "alas-headless.android-image-reproducibility/v1",
        "outcome": "pass",
        "target": {"abi": abi},
        "source_lock_sha256": source_lock,
        "alas_workload_used": False,
        "_evidence_file": evidence_identity(),
    }
    rollback = {
        "schema": "alas-headless.redroid-image-rollback/v1",
        "outcome": "pass",
        "abi": abi,
        "previous_image_digest": "sha256:" + "1" * 64,
        "candidate_image_digest": "sha256:" + "c" * 64,
        "candidate_userdata_preserved": True,
        "rollback_snapshot_restored": True,
        "previous_fingerprint_before": "previous/fingerprint",
        "candidate_fingerprint": "candidate/fingerprint",
        "previous_fingerprint_after": "previous/fingerprint",
        "previous_api_before": "31",
        "candidate_api": "34",
        "previous_api_after": "31",
        "lab_cleaned": True,
        "game_installed": False,
        "alas_workload_used": False,
        "_evidence_file": evidence_identity(),
    }
    return provenance, reproducibility, rollback


class AndroidImageReleaseTests(unittest.TestCase):
    def test_host_fbe_volume_set_is_auxiliary_and_cannot_overclaim(self) -> None:
        evidence = {
            "schema": "alas-headless.redroid-host-fbe-volume-set/v1",
            "outcome": "pass",
            "ceiling": "host-fbe-volume-set-qualified",
            "android_fbe_proven": False,
            "direct_boot_proven": False,
            "_evidence_file": evidence_identity(),
        }
        record = target_record(
            "arm64-v8a", None, None, None, {}, None, None,
            fbe_volume_set_evidence=evidence,
        )
        self.assertEqual(record["host_fbe_volume_set"]["outcome"], "pass")
        self.assertNotIn("fbe-volume-set-evidence-overclaims-fbe", record["blockers"])
        evidence["direct_boot_proven"] = True
        record = target_record(
            "arm64-v8a", None, None, None, {}, None, None,
            fbe_volume_set_evidence=evidence,
        )
        self.assertIn("fbe-volume-set-evidence-overclaims-fbe", record["blockers"])

    def test_host_userdata_volume_is_bound_but_cannot_claim_android_fbe(self) -> None:
        evidence = {
            "schema": "alas-headless.redroid-userdata-volume-qualification/v1",
            "outcome": "pass",
            "ceiling": "host-volume-qualified",
            "android_fbe_proven": False,
            "direct_boot_proven": False,
            "_evidence_file": evidence_identity(),
        }
        record = target_record(
            "arm64-v8a", None, None, None, {}, None, None,
            userdata_volume_evidence=evidence,
        )
        self.assertEqual(record["host_userdata_volume"]["outcome"], "pass")
        self.assertNotIn("userdata-volume-evidence-file-invalid", record["blockers"])
        self.assertNotIn("userdata-volume-evidence-overclaims-fbe", record["blockers"])

        overclaim = dict(evidence)
        overclaim["android_fbe_proven"] = True
        record = target_record(
            "arm64-v8a", None, None, None, {}, None, None,
            userdata_volume_evidence=overclaim,
        )
        self.assertIn("userdata-volume-evidence-overclaims-fbe", record["blockers"])

    def test_dual_target_clean_release_can_promote(self) -> None:
        source_lock_sha256 = "c" * 64
        target = {
            "blockers": [],
            "outcome": "platform-and-update-qualified",
            "build_provenance": {"source_lock_sha256": source_lock_sha256},
        }
        value = build_release_manifest(
            FakePolicy(),
            {"commit": "b" * 40, "dirty": False, "source_lock_sha256": source_lock_sha256},
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
                "_evidence_file": evidence_identity(),
            }
            provenance, reproducibility, rollback = release_inputs("arm64-v8a")
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
                    "platform_manifest_digest": "sha256:" + "d" * 64,
                    "platform_descriptor": {"platform": {"architecture": "arm64", "os": "linux"}},
                    "architecture": "arm64",
                    "immutable": True,
                    "_evidence_file": evidence_identity(),
                },
                provenance, reproducibility, rollback,
            )
            self.assertNotIn("image-artifact-missing", record["blockers"])
            self.assertNotIn("image-identity-evidence-file-invalid", record["blockers"])
            self.assertNotIn("gles-contract-evidence-file-invalid", record["blockers"])
            self.assertEqual(record["image_artifact"]["kind"], "oci")

    def test_rollback_candidate_must_match_released_oci_digest(self) -> None:
        provenance, reproducibility, rollback = release_inputs("arm64-v8a")
        rollback["candidate_image_digest"] = "sha256:" + "d" * 64
        record = target_record(
            "arm64-v8a", None, None, None, {}, None, None,
            {"schema": "alas-headless.oci-image-identity/v1",
             "manifest_digest": "sha256:" + "c" * 64,
             "platform_manifest_digest": "sha256:" + "d" * 64,
             "platform_descriptor": {"platform": {"architecture": "arm64", "os": "linux"}},
             "architecture": "arm64", "immutable": True},
            provenance, reproducibility, rollback,
        )
        self.assertIn("image-rollback-candidate-mismatch", record["blockers"])

    def test_oci_identity_fails_closed_on_architecture_and_tag(self) -> None:
        provenance, reproducibility, rollback = release_inputs("arm64-v8a")
        record = target_record(
            "arm64-v8a", None, None, None, {}, None, None,
            {
                "schema": "alas-headless.oci-image-identity/v1",
                "manifest_digest": "latest",
                "platform_manifest_digest": "broken",
                "platform_descriptor": {"platform": {"architecture": "amd64", "os": "linux"}},
                "architecture": "amd64",
                "immutable": False,
                "_evidence_file": evidence_identity(),
            },
            provenance, reproducibility, rollback,
        )
        self.assertIn("image-identity-digest-invalid", record["blockers"])
        self.assertIn("image-identity-abi-mismatch", record["blockers"])
        self.assertIn("image-identity-not-immutable", record["blockers"])

    def test_target_fails_closed_without_supply_chain_and_image_rollback(self) -> None:
        record = target_record("arm64-v8a", None, None, None, {}, None, None)
        self.assertIn("build-provenance-missing", record["blockers"])
        self.assertIn("reproducibility-evidence-missing", record["blockers"])
        self.assertIn("image-rollback-evidence-missing", record["blockers"])

    def test_rollback_requires_candidate_and_restored_platform_identity(self) -> None:
        provenance, reproducibility, rollback = release_inputs("arm64-v8a")
        rollback["candidate_fingerprint"] = rollback["previous_fingerprint_before"]
        rollback["previous_api_after"] = "34"
        record = target_record(
            "arm64-v8a", None, None, None, {}, None, None,
            {"schema": "alas-headless.oci-image-identity/v1",
             "manifest_digest": "sha256:" + "c" * 64,
             "platform_manifest_digest": "sha256:" + "d" * 64,
             "platform_descriptor": {"platform": {"architecture": "arm64", "os": "linux"}},
             "architecture": "arm64", "immutable": True},
            provenance, reproducibility, rollback,
        )
        self.assertIn("image-rollback-candidate-identity-not-proven", record["blockers"])
        self.assertIn("image-rollback-previous-api-not-restored", record["blockers"])


if __name__ == "__main__":
    unittest.main()
