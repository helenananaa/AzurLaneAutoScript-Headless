from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path
from unittest.mock import patch

from alas_headless.android_image_source import AndroidImageSourceError
from alas_headless.android_image_source import AndroidImageSourceLock
from alas_headless.android_image_source import disk_checks
from alas_headless.android_image_source import host_preflight
from alas_headless.android_image_source import memory_checks
from alas_headless.android_image_source import webview_projects_for_abi
from alas_headless.android_image_source import verify_remote_refs


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

    def test_locked_project_patch_files_match_their_digests(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for item in self.value["project_patches"]:
            with self.subTest(path=item["path"]):
                self.assertEqual(
                    hashlib.sha256((root / item["path"]).read_bytes()).hexdigest(),
                    item["sha256"],
                )

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

    def test_remote_verification_scopes_webview_refs_to_selected_abi(self) -> None:
        projects = self.value["redroid"]["webview_projects"]
        x86_names = {
            item["name"] for item in webview_projects_for_abi(projects, "x86_64")
        }
        self.assertEqual(x86_names, {
            "chromium-webview-stub",
            "android_external_chromium-webview_prebuilt_x86",
            "android_external_chromium-webview_prebuilt_x86_64",
        })
        arm_names = {
            item["name"] for item in webview_projects_for_abi(projects, "arm64-v8a")
        }
        self.assertEqual(arm_names, {
            "chromium-webview-stub",
            "android_external_chromium-webview_prebuilt_arm",
            "android_external_chromium-webview_prebuilt_arm64",
        })
        self.assertEqual(len(webview_projects_for_abi(projects, "all")), 5)

    def test_remote_verification_rejects_unknown_abi(self) -> None:
        with self.assertRaisesRegex(AndroidImageSourceError, "unsupported"):
            webview_projects_for_abi(
                self.value["redroid"]["webview_projects"], "x86"
            )

    def test_remote_verification_allows_moved_branch_with_pinned_build_commit(
        self,
    ) -> None:
        lock = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))
        moved_name = "android_external_chromium-webview_prebuilt_x86_64"
        moved_tip = "9" * 40

        def fake_run(arguments, **_kwargs):
            class Result:
                returncode = 0
                stderr = ""

            result = Result()
            if arguments[1] == "ls-remote":
                url, ref = arguments[2], arguments[3]
                expected = next(
                    (
                        item["commit"]
                        for item in lock.document["redroid"]["webview_projects"]
                        if item["url"] == url
                    ),
                    None,
                )
                if ref == "refs/heads/main" and moved_name in url:
                    result.stdout = moved_tip + "\t" + ref + "\n"
                elif expected:
                    result.stdout = expected + "\t" + ref + "\n"
                else:
                    source = lock.document
                    expected_by_ref = {
                        "refs/tags/android-14.0.0_r75": source["platform"]["tag_object"],
                        "refs/heads/14.0.0": source["redroid"]["local_manifests_commit"],
                        "refs/heads/master": source["redroid"]["patches_commit"],
                        "refs/heads/redroid-14.0.0": source["redroid"]["projects"][0]["commit"],
                    }
                    result.stdout = expected_by_ref[ref] + "\t" + ref + "\n"
            elif arguments[1] == "init":
                result.stdout = ""
            elif arguments[3] == "fetch":
                result.stdout = ""
            else:
                result.stdout = lock.document["platform"]["commit"] + "\n"
            return result

        with patch(
            "alas_headless.android_image_source.subprocess.run",
            side_effect=fake_run,
        ):
            result = verify_remote_refs(lock, abi="x86_64")
        self.assertEqual(result["outcome"], "pass")
        moved = next(
            item for item in result["refs"] if moved_name in item["name"]
        )
        self.assertEqual(moved["expected_commit"], "74bc304c32135220898a0f9a8c8661d9747a60b8")
        self.assertEqual(moved["observed_commit"], moved_tip)
        self.assertEqual(moved["ref_state"], "advertised-tip-moved")

    def test_remote_verification_still_rejects_unavailable_branch(self) -> None:
        lock = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))

        class Missing:
            returncode = 2
            stdout = ""
            stderr = "not found"

        with patch(
            "alas_headless.android_image_source.subprocess.run",
            return_value=Missing(),
        ):
            result = verify_remote_refs(lock, abi="x86_64")
        self.assertEqual(result["outcome"], "blocked")
        self.assertTrue(result["blockers"])
        self.assertTrue(
            all(item["ref_state"] == "unavailable" for item in result["refs"][:-1])
        )

    def test_prepared_source_may_supply_pinned_objects_during_remote_outage(
        self,
    ) -> None:
        lock = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))

        class Result:
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(arguments, **_kwargs):
            result = Result()
            if arguments[1] == "ls-remote":
                result.returncode = 2
                result.stderr = "network unavailable"
            elif len(arguments) > 3 and arguments[3] == "fetch":
                result.returncode = 2
                result.stderr = "network unavailable"
            return result

        with patch(
            "alas_headless.android_image_source.subprocess.run",
            side_effect=fake_run,
        ), patch(
            "alas_headless.android_image_source._local_git_object_available",
            return_value=True,
        ), patch(
            "alas_headless.android_image_source._local_tag_commit",
            return_value=lock.document["platform"]["commit"],
        ):
            result = verify_remote_refs(
                lock, abi="x86_64", prepared_source_root=Path("prepared")
            )
        self.assertEqual(result["outcome"], "pass")
        self.assertTrue(
            all(item["outcome"] == "pass" for item in result["refs"])
        )
        self.assertTrue(
            result["refs"][0]["ref_state"] == "prepared-local-platform-commit"
        )
        self.assertTrue(
            all(
                item["ref_state"] == "prepared-local-object"
                for item in result["refs"][1:-1]
            )
        )
        self.assertEqual(
            result["refs"][-1]["verification_source"], "prepared-local-tag"
        )

    def test_rejects_32_bit_or_single_arch_product(self) -> None:
        value = copy.deepcopy(self.value)
        value["products"] = value["products"][:1]
        with self.assertRaisesRegex(AndroidImageSourceError, "exact 64-bit"):
            AndroidImageSourceLock.from_mapping(value)

    def test_targets_use_android_14_release_aware_lunch_choices(self) -> None:
        lock = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))
        self.assertEqual(
            [item["lunch"] for item in lock.document["products"]],
            [
                "redroid_x86_64_only-trunk_staging-userdebug",
                "redroid_arm64_only-trunk_staging-userdebug",
            ],
        )

    def test_rejects_game_artifact_in_build(self) -> None:
        value = copy.deepcopy(self.value)
        value["build"]["game_artifact_allowed"] = True
        with self.assertRaisesRegex(AndroidImageSourceError, "external"):
            AndroidImageSourceLock.from_mapping(value)

    def test_project_patch_is_content_addressed(self) -> None:
        value = copy.deepcopy(self.value)
        value["project_patches"][0]["sha256"] = "main"
        with self.assertRaisesRegex(AndroidImageSourceError, "sha256"):
            AndroidImageSourceLock.from_mapping(value)

    def test_webview_patch_target_is_narrowly_approved(self) -> None:
        lock = AndroidImageSourceLock.from_mapping(copy.deepcopy(self.value))
        webview = [
            item for item in lock.document["project_patches"]
            if item["project"] == "external/chromium-webview"
        ]
        self.assertEqual(len(webview), 1)
        self.assertTrue(
            webview[0]["path"].endswith(
                "0005-redroid-webview-x86_64-only-prebuilt.patch"
            )
        )

    def test_rejects_unapproved_project_patch_target(self) -> None:
        value = copy.deepcopy(self.value)
        value["project_patches"][0]["project"] = "system/core"
        with self.assertRaisesRegex(AndroidImageSourceError, "not approved"):
            AndroidImageSourceLock.from_mapping(value)

    def test_locale_and_font_patch_targets_are_narrowly_approved(self) -> None:
        value = copy.deepcopy(self.value)
        template = copy.deepcopy(value["project_patches"][0])
        template["path"] = "integration/runtime/aosp-patches/0007-test.patch"
        template["sha256"] = "a" * 64
        template["commit_message"] = "ALAS: test target"
        for project in ("device/redroid", "external/noto-fonts"):
            item = copy.deepcopy(template)
            item["project"] = project
            value["project_patches"].append(item)
            template["path"] = "integration/runtime/aosp-patches/0008-test.patch"
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

    def test_wsl_memory_policy_requires_ram_and_swap(self) -> None:
        gib = 1024 ** 3
        build = self.value["build"]
        allowed = memory_checks(58 * gib, 16 * gib, "microsoft-standard-WSL2", build)
        self.assertTrue(all(allowed.values()))
        low_ram = memory_checks(57 * gib, 16 * gib, "microsoft-standard-WSL2", build)
        self.assertFalse(low_ram["ram_floor"])
        self.assertTrue(low_ram["swap_floor"])
        low_swap = memory_checks(58 * gib, 15 * gib, "microsoft-standard-WSL2", build)
        self.assertTrue(low_swap["ram_floor"])
        self.assertFalse(low_swap["swap_floor"])

    def test_native_memory_policy_keeps_64_gib_floor(self) -> None:
        gib = 1024 ** 3
        build = self.value["build"]
        rejected = memory_checks(63 * gib, 64 * gib, "6.8.0-generic", build)
        self.assertFalse(rejected["ram_floor"])
        allowed = memory_checks(64 * gib, 0, "6.8.0-generic", build)
        self.assertTrue(all(allowed.values()))

    def test_rejects_unsafe_wsl_resource_policy(self) -> None:
        for field, value, message in (
            ("minimum_ram_gib", 57, "RAM floor"),
            ("minimum_swap_gib", 15, "swap floor"),
        ):
            with self.subTest(field=field):
                source = copy.deepcopy(self.value)
                source["build"]["wsl"][field] = value
                with self.assertRaisesRegex(AndroidImageSourceError, message):
                    AndroidImageSourceLock.from_mapping(source)

    def test_legacy_job_count_metadata_does_not_gate_source_compatibility(self) -> None:
        value = copy.deepcopy(self.value)
        value["build"]["wsl"]["maximum_build_jobs"] = 24
        AndroidImageSourceLock.from_mapping(value)

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
