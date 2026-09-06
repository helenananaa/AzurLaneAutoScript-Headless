from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from alas_headless.android_build_domain import AndroidBuildDomain
from alas_headless.android_build_domain import AndroidBuildDomainError
from alas_headless.android_build_domain import require_isolated_domain_pair


ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "integration" / "runtime" / (
    "android-build-domain.redroid.example.json"
)
X86_EXAMPLE = ROOT / "integration" / "runtime" / (
    "android-build-domain.redroid.x86_64.example.json"
)


def kvm_sibling(value: dict) -> dict:
    result = copy.deepcopy(value)
    result["backend"] = "kvm"
    for name, path in result["paths"].items():
        result["paths"][name] = path.replace("redroid", "kvm")
    return result


class AndroidBuildDomainTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.value = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def test_redroid_example_is_valid_and_stable(self) -> None:
        first = AndroidBuildDomain.from_mapping(
            copy.deepcopy(self.value), expected_backend="redroid"
        )
        second = AndroidBuildDomain.from_path(
            EXAMPLE, expected_backend="redroid"
        )
        self.assertEqual(first.sha256, second.sha256)
        self.assertEqual(first.document["backend"], "redroid")
        self.assertEqual(first.document["schema"], "alas-headless.android-build-domain/v3")
        self.assertEqual(len(first.sha256), 64)

    def test_redroid_x86_example_matches_the_new_host_wrapper(self) -> None:
        domain = AndroidBuildDomain.from_path(
            X86_EXAMPLE, expected_backend="redroid"
        )
        self.assertEqual(
            domain.path("output_root"), "/srv/android-build/redroid/out/x86_64"
        )
        self.assertEqual(
            domain.path("ccache_root"), "/srv/android-build/redroid/ccache/x86_64"
        )
        self.assertEqual(
            domain.path("temp_root"), "/srv/android-build/redroid/tmp/x86_64"
        )
        self.assertEqual(
            domain.path("archive_root"), "/srv/android-build/redroid/archive/images"
        )
        self.assertEqual(
            domain.path("evidence_root"), "/srv/android-build/redroid/evidence"
        )

    def test_redroid_entry_rejects_kvm_domain(self) -> None:
        with self.assertRaisesRegex(AndroidBuildDomainError, "must be redroid"):
            AndroidBuildDomain.from_mapping(
                kvm_sibling(self.value), expected_backend="redroid"
            )

    def test_rejects_overlap_inside_one_domain(self) -> None:
        value = copy.deepcopy(self.value)
        value["paths"]["ccache_root"] = value["paths"]["output_root"] + "/ccache"
        with self.assertRaisesRegex(
            AndroidBuildDomainError, "must stay under|must not overlap"
        ):
            AndroidBuildDomain.from_mapping(value)

    def test_rejects_mutable_path_owned_by_the_other_backend(self) -> None:
        value = copy.deepcopy(self.value)
        value["paths"]["ccache_root"] = "/srv/android-build/kvm/ccache/foreign"
        with self.assertRaisesRegex(AndroidBuildDomainError, "must stay under"):
            AndroidBuildDomain.from_mapping(value, expected_backend="redroid")

    def test_harmless_backend_siblings_are_allowed(self) -> None:
        redroid = AndroidBuildDomain.from_mapping(copy.deepcopy(self.value))
        kvm = AndroidBuildDomain.from_mapping(kvm_sibling(self.value))
        require_isolated_domain_pair(redroid, kvm)
        self.assertNotEqual(redroid.path("output_root"), kvm.path("output_root"))

    def test_rejects_legacy_lock_fields(self) -> None:
        value = copy.deepcopy(self.value)
        value["locks"] = {"build_lock": "/run/legacy.lock"}
        with self.assertRaisesRegex(AndroidBuildDomainError, "fields differ"):
            AndroidBuildDomain.from_mapping(value)

    def test_pair_rejects_cross_field_overlap(self) -> None:
        kvm_value = kvm_sibling(self.value)
        kvm_value["paths"]["ccache_root"] = self.value["paths"]["output_root"]
        with self.assertRaisesRegex(AndroidBuildDomainError, "must stay under"):
            AndroidBuildDomain.from_mapping(kvm_value)

    def test_build_and_rebind_are_lock_free(self) -> None:
        build = (ROOT / "scripts" / "wsl" / "build-redroid-images.sh").read_text(
            encoding="utf-8"
        )
        project_rebind = (
            ROOT / "scripts" / "python" / "rebind_android_build_project_patches.py"
        ).read_text(encoding="utf-8")
        source_rebind = (
            ROOT / "scripts" / "python" / "rebind_android_build_source_lock.py"
        ).read_text(encoding="utf-8")
        self.assertIn("require_isolated_domain_pair", build)
        self.assertNotIn("flock", build)
        self.assertNotIn("hot_output", build)
        self.assertNotIn('value["locks"]', build)
        for script in (project_rebind, source_rebind):
            self.assertIn('expected_backend="redroid"', script)
            self.assertIn('domain.path("source_root")', script)
            self.assertNotIn("exclusive_file_lock", script)
            self.assertNotIn("build_lock", script)
            self.assertNotIn('add_argument("--source-root"', script)
            self.assertNotIn('add_argument("--resume-marker"', script)

    def test_lock_based_cli_names_are_retired(self) -> None:
        scripts = ROOT / "scripts" / "python"
        self.assertFalse((scripts / "manage_android_hot_output.py").exists())
        self.assertFalse((scripts / "preflight_android_build_domains_v2.py").exists())
        manager = (scripts / "manage_android_output.py").read_text(encoding="utf-8")
        preflight = (scripts / "preflight_android_build_domains.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("require_output_buildable", manager)
        self.assertIn("lock-free KVM/Redroid domain pair", preflight)
        self.assertNotIn("exclusive_file_lock", manager + preflight)


if __name__ == "__main__":
    unittest.main()
