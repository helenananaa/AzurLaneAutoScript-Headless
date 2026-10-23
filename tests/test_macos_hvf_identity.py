from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alas_headless.macos_hvf_identity import (
    IDENTITY_SCHEMA,
    angle_patchset_manifest,
    build_platform_resource_manifest,
    build_provision_profile,
    build_runtime_lock,
    file_sha256,
    write_canonical_document,
)


HASH = "a" * 64


class MacosHvfIdentityTests(unittest.TestCase):
    def test_canonical_documents_are_exclusive_and_hash_exact_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "document.json"
            digest = write_canonical_document(path, {"z": 1, "a": "值"})
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["a"], "值")
            with self.assertRaisesRegex(ValueError, "must not already exist"):
                write_canonical_document(path, {"a": 2})

    def test_resource_manifest_makes_no_public_resource_claim(self):
        value = build_platform_resource_manifest("com.example.game", "1.2.3", 123)
        self.assertEqual(value["claim_scope"], "none-platform-lifecycle-only")
        self.assertEqual(value["shared_public_paths"], [])

    def test_provision_profile_records_decision_relevant_identity(self):
        value = build_provision_profile(
            avd_name="arm64",
            avd_config_sha256=HASH,
            sdk_root="/Users/test/Library/Android/sdk",
            system_image_relative_path="system-images/android-32/arm64-v8a/system.img",
            system_image_sha256=HASH,
            emulator_version="Android emulator version 37",
            acceleration="hypervisor.framework",
            console_port=5554,
            adb_server_port=5037,
            android_fingerprint="google/test",
            api_level=32,
            abi="arm64-v8a",
        )
        self.assertEqual(value["acceleration"], "hypervisor.framework")
        self.assertEqual(value["logical_display"], "1280x720@240")

    def test_patchset_manifest_is_path_stable_and_content_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("patches/angle/a.patch", "patches/angle-g3/b.patch", "overlays/angle-g3/x.cc"):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(relative, encoding="utf-8")
            value = angle_patchset_manifest(root)
        self.assertEqual([entry["path"] for entry in value["entries"]], [
            "patches/angle/a.patch",
            "patches/angle-g3/b.patch",
            "overlays/angle-g3/x.cc",
        ])

    def test_runtime_lock_accepts_exact_receipts_and_rejects_profile_drift(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "integration/alas/series").mkdir(parents=True)
            (root / "integration/alas/upstream-lock.json").write_text(
                json.dumps({"commit": "c" * 40}), encoding="utf-8"
            )
            (root / "integration/alas/0001-semantic-oracle-hooks.patch").write_text("patch", encoding="utf-8")
            (root / "integration/alas/series/series.json").write_text("{}", encoding="utf-8")
            (root / "ANGLE_REVISION").write_text("d" * 40, encoding="utf-8")
            profile = root / "profile.json"
            resource = root / "resource.json"
            profile.write_text("profile", encoding="utf-8")
            resource.write_text("resource", encoding="utf-8")
            identity = {
                "schema": IDENTITY_SCHEMA,
                "outcome": "pass",
                "platform": "darwin",
                "machine": "arm64",
                "android_abi": "arm64-v8a",
                "game_abi": "arm64-v8a",
                "provision_profile_sha256": file_sha256(profile),
                "resource_manifest_sha256": file_sha256(resource),
                "api_level": 32,
                "game_version_code": 9710,
                "game_version_name": "9.7.10",
                "package": "com.bilibili.azurlane",
                "android_fingerprint": "google/test",
                "system_image_sha256": HASH,
                "angle_apk_sha256": HASH,
                "game_base_apk_sha256": HASH,
                "game_libil2cpp_sha256": HASH,
            }
            with patch(
                "alas_headless.macos_hvf_identity._git", return_value="b" * 40
            ):
                lock = build_runtime_lock(
                    repo_root=root,
                    identity=identity,
                    provision_profile=profile,
                    resource_manifest=resource,
                    angle_patchset_sha256=HASH,
                )
            self.assertEqual(lock.document["android"]["backend"], "macos-hvf")
            profile.write_text("drift", encoding="utf-8")
            with patch(
                "alas_headless.macos_hvf_identity._git", return_value="b" * 40
            ), self.assertRaisesRegex(ValueError, "profile receipt mismatch"):
                build_runtime_lock(
                    repo_root=root,
                    identity=identity,
                    provision_profile=profile,
                    resource_manifest=resource,
                    angle_patchset_sha256=HASH,
                )


if __name__ == "__main__":
    unittest.main()

