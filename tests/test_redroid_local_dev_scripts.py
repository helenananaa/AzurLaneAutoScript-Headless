from __future__ import annotations

import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class RedroidLocalDevScriptsTests(unittest.TestCase):
    def test_wsl_manager_keeps_local_dev_boundary_explicit(self) -> None:
        script = (ROOT / "scripts" / "wsl" / "manage-redroid-local-dev.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "redroid/redroid@sha256:0a611199ba2e0b5d60af39b3327a517f6407231f4352114ed3bd3cbfe2be69aa",
            script,
        )
        self.assertIn('127.0.0.1:$adb_port:5555', script)
        self.assertIn('storage_mode=host-directory-persistent', script)
        self.assertNotIn('/dev/null:/vendor/etc/fstab.redroid:ro', script)
        self.assertIn('compressed project OCI archive digest mismatch', script)
        self.assertIn("configured_image_id=", script)
        self.assertIn("expected_image_id=", script)
        self.assertIn('[[ $configured_image_id == "$expected_image_id" ]]', script)
        self.assertIn('--privileged', script)
        self.assertIn('--restart no', script)
        self.assertNotIn('0.0.0.0:', script)
        self.assertNotIn('docker rm', script)

    def test_windows_manager_keeps_wsl_alive_without_visible_window(self) -> None:
        script = (
            ROOT / "scripts" / "windows" / "manage-redroid-wsl-local-dev.ps1"
        ).read_text(encoding="utf-8-sig")
        self.assertIn("CreateNoWindow = $true", script)
        self.assertIn("alas-redroid-wsl-keepalive", script)
        self.assertIn("manage-redroid-local-dev.sh", script)
        self.assertIn("-u root -- bash -lc", script)
        self.assertIn("mount -t binder binder /dev/binderfs", script)
        self.assertIn("127.0.0.1:$adbPort", script)
        self.assertIn("ALAS_REDROID_LOCAL_ADB_PORT=5556", script)
        self.assertIn("ALAS_REDROID_LOCAL_ADB_PORT=5557", script)
        self.assertIn("ALAS_REDROID_LOCAL_CONTAINER=alas-redroid-wsl-api31", script)
        self.assertIn("ALAS_REDROID_LOCAL_DATA_NAME=api31-game-data", script)
        self.assertIn(
            "ALAS_REDROID_LOCAL_IMAGE=redroid/redroid@sha256:a6c464bbedcf1dcb67dbf91f329fbb19bee5b50631f0ca6bda6ed7c41b0e64e2",
            script,
        )
        self.assertIn("'Project', 'Stock', 'Api31'", script)
        self.assertIn(
            "ALAS_REDROID_LOCAL_IMAGE=sha256:881be994eb02237524b070bd15638eaef5cdbc15108355d4137aa9e141854eac",
            script,
        )
        self.assertIn(
            "ALAS_REDROID_LOCAL_OCI_ZST_SHA256=15b15270e06583e7f8b460abd0a23cbbb04ddd9f488a7efe355722d79677c51f",
            script,
        )
        self.assertIn("$linuxHome/.config/alas-redroid/docker", script)
        self.assertNotIn("/home/helenanana", script)


if __name__ == "__main__":
    unittest.main()
