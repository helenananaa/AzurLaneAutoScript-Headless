from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from alas_headless.android_kvm_image import KvmImageBuildProfile
from alas_headless.android_kvm_image import KvmImageBuildProfileError


class KvmImageBuildProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        path = Path(__file__).resolve().parents[1] / "integration" / "runtime" / (
            "kvm-image-build-profile.example.json"
        )
        cls.value = json.loads(path.read_text(encoding="utf-8"))

    def test_example_is_stable_and_backend_specific(self) -> None:
        profile = KvmImageBuildProfile.from_mapping(copy.deepcopy(self.value))
        self.assertEqual(profile.document["backend"], "kvm")
        self.assertEqual(profile.document["product"]["abi"], "x86_64")
        self.assertEqual(
            profile.document["product"]["lunch"],
            "alas_kvm_x86_64-trunk_staging-userdebug",
        )
        self.assertEqual(profile.document["product"]["product_out"], "emu64x")
        self.assertEqual(len(profile.document["source_lock_sha256"]), 64)
        self.assertNotIn("shared_source_lock_sha256", profile.document)
        self.assertNotIn("source_overlays", profile.document)
        self.assertNotIn("shared_ccache_allowed", profile.document["build"])
        self.assertEqual(profile.document["runtime"]["console_port"], 5588)
        self.assertTrue(profile.document["build"]["relax_uses_library_check"])
        self.assertEqual(
            profile.document["build"]["dynamic_partitions_size_bytes"],
            5 * 2**28,
        )
        self.assertEqual(
            profile.document["build"]["super_partition_size_bytes"],
            5 * 2**28 + 2**23,
        )
        self.assertEqual(len(profile.sha256), 64)

    def test_rejects_redroid_product(self) -> None:
        value = copy.deepcopy(self.value)
        value["product"]["lunch"] = "redroid_x86_64_only-trunk_staging-userdebug"
        with self.assertRaisesRegex(KvmImageBuildProfileError, "Goldfish"):
            KvmImageBuildProfile.from_mapping(value)

    def test_requires_separate_output(self) -> None:
        value = copy.deepcopy(self.value)
        value["build"]["separate_output_required"] = False
        with self.assertRaisesRegex(KvmImageBuildProfileError, "build contract"):
            KvmImageBuildProfile.from_mapping(value)

    def test_rejects_shared_source_contract(self) -> None:
        value = copy.deepcopy(self.value)
        value["shared_source_lock_sha256"] = value.pop("source_lock_sha256")
        with self.assertRaisesRegex(KvmImageBuildProfileError, "fields differ"):
            KvmImageBuildProfile.from_mapping(value)

    def test_rejects_malformed_source_lock_hash(self) -> None:
        value = copy.deepcopy(self.value)
        value["source_lock_sha256"] = "not-a-hash"
        with self.assertRaisesRegex(KvmImageBuildProfileError, "source lock"):
            KvmImageBuildProfile.from_mapping(value)


if __name__ == "__main__":
    unittest.main()
