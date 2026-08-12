from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from alas_headless.android_image_source import AndroidImageSourceError
from alas_headless.android_image_source import AndroidImageSourceLock


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

    def test_rejects_patch_set_different_from_aosp_tag(self) -> None:
        value = copy.deepcopy(self.value)
        value["redroid"]["patch_set"] = "android-14.0.0_r2"
        with self.assertRaisesRegex(AndroidImageSourceError, "exactly match"):
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


if __name__ == "__main__":
    unittest.main()
