from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from alas_headless.android_image_source import AndroidImageSourceError
from alas_headless.android_image_source import AndroidImageSourceLock
from alas_headless.android_image_source import disk_checks
from alas_headless.android_image_source import host_preflight


class AndroidImageSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parents[1] / "integration" / "runtime" / (
            "android-image-source-lock.example.json"
        )
        cls.value = json.loads(path.read_text(encoding="utf-8"))

    def test_example_is_stable_and_dual_abi(self) -> None:
        first = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))
        second = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(len(first.sha256), 64)
        self.assertEqual([item["abi"] for item in first.document["products"]], [
            "x86_64", "arm64-v8a"
        ])

    def test_rejects_moving_or_short_source_identity(self) -> None:
        value = copy.deepcopy(self.value)
        value["redroid"]["patches_commit"] = "master"
        with self.assertRaisesRegex(AndroidImageSourceError, "immutable Git commit"):
            AndroidImageSourceLock.from_mapping(value)

    def test_platform_annotated_tag_and_peeled_commit_are_both_locked(self) -> None:
        lock = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))
        self.assertNotEqual(
            lock.document["platform"]["tag_object"],
            lock.document["platform"]["commit"],
        )

    def test_rejects_nondeterministic_build_identity(self) -> None:
        value = copy.deepcopy(self.value)
        value["build"]["build_username"] = "root"
        with self.assertRaisesRegex(AndroidImageSourceError, "must be deterministic"):
            AndroidImageSourceLock.from_mapping(value)
        value = copy.deepcopy(self.value)
        value["build"]["git_identity"]["email"] = "root@builder"
        with self.assertRaisesRegex(AndroidImageSourceError, "git_identity"):
            AndroidImageSourceLock.from_mapping(value)

    def test_rejects_patch_set_different_from_aosp_tag(self) -> None:
        value = copy.deepcopy(self.value)
        value["redroid"]["patch_set"] = "android-14.0.0_r2"
        with self.assertRaisesRegex(AndroidImageSourceError, "exactly match"):
            AndroidImageSourceLock.from_mapping(value)

    def test_rejects_unlocked_transitive_redroid_project(self) -> None:
        value = copy.deepcopy(self.value)
        value["redroid"]["projects"][1]["commit"] = "master"
        with self.assertRaisesRegex(AndroidImageSourceError, "immutable Git commit"):
            AndroidImageSourceLock.from_mapping(value)

    def test_rejects_missing_transitive_redroid_project(self) -> None:
        value = copy.deepcopy(self.value)
        value["redroid"]["projects"].pop()
        with self.assertRaisesRegex(AndroidImageSourceError, "all Redroid"):
            AndroidImageSourceLock.from_mapping(value)

    def test_rejects_unlocked_webview_project(self) -> None:
        value = copy.deepcopy(self.value)
        value["redroid"]["webview_projects"][0]["commit"] = "main"
        with self.assertRaisesRegex(AndroidImageSourceError, "immutable Git commit"):
            AndroidImageSourceLock.from_mapping(value)

    def test_rejects_missing_webview_abi_project(self) -> None:
        value = copy.deepcopy(self.value)
        value["redroid"]["webview_projects"].pop()
        with self.assertRaisesRegex(AndroidImageSourceError, "all WebView"):
            AndroidImageSourceLock.from_mapping(value)

    def test_rejects_32_bit_or_single_arch_product(self) -> None:
        value = copy.deepcopy(self.value)
        value["products"] = value["products"][:1]
        with self.assertRaisesRegex(AndroidImageSourceError, "exact 64-bit"):
            AndroidImageSourceLock.from_mapping(value)

    def test_rejects_game_artifact_in_build(self) -> None:
        value = copy.deepcopy(self.value)
        value["build"]["game_artifact_allowed"] = True
        with self.assertRaisesRegex(AndroidImageSourceError, "external"):
            AndroidImageSourceLock.from_mapping(value)

    def test_wsl_requires_real_backing_drive_capacity(self) -> None:
        gib = 1024 ** 3
        missing = disk_checks(600 * gib, 400 * gib, "microsoft-standard-WSL2", None)
        self.assertFalse(missing["backing_disk_verified"])
        self.assertFalse(missing["disk_floor"])
        low = disk_checks(600 * gib, 400 * gib, "microsoft-standard-WSL2", 218 * gib)
        self.assertTrue(low["backing_disk_verified"])
        self.assertFalse(low["disk_floor"])
        enough = disk_checks(600 * gib, 400 * gib, "microsoft-standard-WSL2", 500 * gib)
        self.assertTrue(all(enough.values()))

    def test_host_preflight_records_work_and_evidence_devices(self) -> None:
        lock = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))
        result = host_preflight(lock, Path.cwd(), evidence_root=Path.cwd())
        self.assertTrue(result["checks"]["work_and_evidence_same_device"])
        self.assertEqual(result["work_device"], result["evidence_device"])
        self.assertIn("system_root_device", result)

    def test_non_root_device_requirement_fails_on_system_root(self) -> None:
        lock = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))
        result = host_preflight(
            lock, Path("/"), evidence_root=Path("/"), require_non_root_device=True
        )
        self.assertFalse(result["checks"]["work_device_not_system_root"])


if __name__ == "__main__":
    unittest.main()
