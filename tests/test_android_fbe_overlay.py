from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from alas_headless.android_fbe_overlay import AndroidFbeOverlayError
from alas_headless.android_fbe_overlay import validate_fbe_overlay
from alas_headless.android_image_source import AndroidImageSourceLock


class AndroidFbeOverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.overlay = Path(__file__).resolve().parents[1] / "integration" / "runtime" / (
            "redroid-native-fbe"
        )

    def test_locked_overlay_passes_without_claiming_runtime_fbe(self) -> None:
        source_lock = AndroidImageSourceLock.from_path(
            self.overlay.parent / "android-image-source-lock.example.json"
        )
        result = validate_fbe_overlay(self.overlay, source_lock)
        self.assertEqual(result["outcome"], "pass")
        self.assertFalse(result["game_artifact_included"])
        self.assertFalse(result["android_fbe_proven"])
        self.assertFalse(result["direct_boot_proven"])
        self.assertEqual(result["source_lock_sha256"], source_lock.sha256)

    def test_modified_fstab_is_rejected_by_digest(self) -> None:
        with TemporaryDirectory() as directory:
            copied = Path(directory) / "overlay"
            shutil.copytree(self.overlay, copied)
            with (copied / "fstab.redroid").open("a", encoding="utf-8") as handle:
                handle.write("# unreviewed change\n")
            with self.assertRaisesRegex(AndroidFbeOverlayError, "digest mismatch"):
                validate_fbe_overlay(copied)

    def test_runtime_evidence_cannot_be_relaxed(self) -> None:
        with TemporaryDirectory() as directory:
            copied = Path(directory) / "overlay"
            shutil.copytree(self.overlay, copied)
            lock_path = copied / "overlay-lock.json"
            value = json.loads(lock_path.read_text(encoding="utf-8"))
            value["android_fbe_runtime_evidence_required"] = False
            lock_path.write_text(json.dumps(value), encoding="utf-8")
            with self.assertRaisesRegex(AndroidFbeOverlayError, "must remain mandatory"):
                validate_fbe_overlay(copied)


if __name__ == "__main__":
    unittest.main()
