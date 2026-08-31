from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from alas_headless.android_kvm_source import KvmImageSourceLock
from alas_headless.android_kvm_source import KvmImageSourceLockError


class KvmImageSourceLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        path = cls.root / "integration" / "runtime" / (
            "kvm-image-source-lock.example.json"
        )
        cls.value = json.loads(path.read_text(encoding="utf-8"))

    def test_example_is_clean_aosp_and_self_contained(self) -> None:
        lock = KvmImageSourceLock.from_mapping(copy.deepcopy(self.value))
        self.assertEqual(lock.document["backend"], "kvm")
        self.assertNotIn("redroid", lock.document)
        self.assertEqual(lock.document["platform"]["revision"], "android-14.0.0_r75")
        self.assertEqual(
            {item["project"] for item in lock.document["project_patches"]},
            {
                "frameworks/base",
                "build/make",
                "device/generic/goldfish",
                "external/chromium-webview",
                "external/noto-fonts",
            },
        )

    def test_patch_payloads_are_owned_and_content_addressed(self) -> None:
        for item in self.value["project_patches"]:
            path = self.root / item["path"]
            self.assertTrue(path.is_file())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])

    def test_rejects_redroid_block(self) -> None:
        value = copy.deepcopy(self.value)
        value["redroid"] = {}
        with self.assertRaisesRegex(KvmImageSourceLockError, "fields differ"):
            KvmImageSourceLock.from_mapping(value)

    def test_rejects_redroid_only_loader_patch(self) -> None:
        value = copy.deepcopy(self.value)
        value["project_patches"][0]["project"] = "frameworks/native"
        with self.assertRaisesRegex(KvmImageSourceLockError, "target differs"):
            KvmImageSourceLock.from_mapping(value)


if __name__ == "__main__":
    unittest.main()
