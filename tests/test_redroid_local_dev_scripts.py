from __future__ import annotations

import pathlib
import os
import re
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class RedroidLocalDevScriptsTests(unittest.TestCase):
    def test_repeated_start_preserves_android_userdata_mode(self) -> None:
        script = (ROOT / "scripts/wsl/manage-redroid-local-dev.sh").read_text(encoding="utf-8")
        block = re.search(r'    if \[\[ ! -d \$data_root \]\]; then\n        install -d -m 0700 "\$data_root"\n    fi', script)
        self.assertIsNotNone(block)
        if os.name == "nt":
            if not shutil.which("wsl.exe"):
                self.skipTest("WSL shell is unavailable")
            shell = ["wsl.exe", "-d", "Ubuntu-22.04", "--", "bash", "-s"]
        else:
            shell = ["bash", "-s"]
        # A fresh empty temporary directory, never the actual Android data tree.
        command = 'set -eu\ntask_tmp=$(mktemp -d)\ndata_root="$task_tmp/data"\n' + block.group(0) + '\n[ "$(stat -c %a "$data_root")" = 700 ]\nchmod 0771 "$data_root"\n' + block.group(0) + '\n[ "$(stat -c %a "$data_root")" = 771 ]\nrmdir "$data_root" "$task_tmp"\n'
        result = subprocess.run(shell, input=command.encode("utf-8"), capture_output=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

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
        self.assertIn('immersive_mode_confirmations confirmed', script)
        self.assertIn('confirm_immersive == 1', script)
        self.assertNotIn('/dev/null:/vendor/etc/fstab.redroid:ro', script)
        self.assertIn('compressed project OCI archive digest mismatch', script)
        self.assertIn('project OCI archive digest mismatch', script)
        self.assertIn('docker_cmd[@]}\" load -i \"$oci_tar\"', script)
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
        self.assertIn("UseShellExecute = $true", script)
        self.assertIn("ProcessWindowStyle]::Hidden", script)
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
        self.assertIn("redroid-x86_64-candidates\\current", script)
        self.assertIn("redroid-x86_64.oci-build.json", script)
        self.assertIn("redroid-x86_64.oci.tar", script)
        self.assertIn("ALAS_REDROID_LOCAL_OCI_TAR_SHA256", script)
        self.assertIn("ALAS_REDROID_LOCAL_CONFIRM_IMMERSIVE=1", script)
        self.assertIn("alas-redroid-wsl-projectlocal", script)
        self.assertIn("projectlocal-data", script)
        self.assertIn("$linuxHome/.config/alas-redroid/docker", script)
        self.assertNotIn("/home/helenanana", script)

    def test_local_resource_import_is_bounded_and_owner_correct(self) -> None:
        script = (
            ROOT / "scripts" / "wsl" / "copy-local-game-resource-base.sh"
        ).read_text(encoding="utf-8")
        self.assertIn("Project container must be stopped", script)
        self.assertIn("xargs -0 -r -n 12 -P", script)
        self.assertIn("[[ $jobs =~ ^[1-8]$ ]]", script)
        self.assertIn("chown -R 10067:1078", script)
        self.assertIn("chmod 2770", script)
        self.assertIn("chmod 0660", script)
        self.assertNotIn("--delete", script)


if __name__ == "__main__":
    unittest.main()
