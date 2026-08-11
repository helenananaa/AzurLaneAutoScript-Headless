from __future__ import annotations

import unittest

from alas_headless.android_image_release import build_release_manifest


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


if __name__ == "__main__":
    unittest.main()
