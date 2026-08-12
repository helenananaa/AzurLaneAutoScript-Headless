from __future__ import annotations

import copy
import unittest

from alas_headless.android_userdata_volume import qualify_userdata_volume
from alas_headless.android_userdata_volume import qualify_fbe_volume_set


class AndroidUserdataVolumeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.probe = {
            "schema": "alas-headless.redroid-userdata-volume-probe/v1",
            "role": "userdata",
            "scope": "empty-lab-volume",
            "created_new": True,
            "backing_file_existed_before": False,
            "production_data_touched": False,
            "backing_file": "/var/lib/redroid-volumes/lab.img",
            "block_device": "/dev/loop7",
            "root_source": "/dev/nvme0n1p2",
            "mountpoint": "/mnt/redroid-userdata-lab",
            "filesystem_type": "ext4",
            "filesystem_features": ["has_journal", "ext_attr", "encrypt"],
            "mounted_read_write": True,
            "empty_before_mount": True,
            "android_fbe_claimed": False,
        }

    def test_pass_is_explicitly_bounded_below_android_fbe(self) -> None:
        result = qualify_userdata_volume(self.probe)
        self.assertEqual(result["outcome"], "pass")
        self.assertEqual(result["ceiling"], "host-volume-qualified")
        self.assertFalse(result["android_fbe_proven"])
        self.assertFalse(result["direct_boot_proven"])

    def test_rejects_missing_encrypt_feature(self) -> None:
        probe = copy.deepcopy(self.probe)
        probe["filesystem_features"].remove("encrypt")
        result = qualify_userdata_volume(probe)
        self.assertIn("ext4-encrypt-feature-missing", result["blockers"])

    def test_rejects_production_data_overlap(self) -> None:
        probe = copy.deepcopy(self.probe)
        probe["backing_file"] = "/var/lib/redroid/data/userdata.img"
        result = qualify_userdata_volume(probe)
        self.assertIn("backing-file-overlaps-production-data", result["blockers"])

    def test_rejects_production_mountpoint(self) -> None:
        probe = copy.deepcopy(self.probe)
        probe["mountpoint"] = "/var/lib/redroid/data"
        result = qualify_userdata_volume(probe)
        self.assertIn("unsafe-or-production-mountpoint", result["blockers"])

    def test_rejects_host_root_device(self) -> None:
        probe = copy.deepcopy(self.probe)
        probe["block_device"] = probe["root_source"]
        result = qualify_userdata_volume(probe)
        self.assertIn("userdata-reuses-host-root-device", result["blockers"])

    def test_rejects_android_fbe_claim(self) -> None:
        probe = copy.deepcopy(self.probe)
        probe["android_fbe_claimed"] = True
        result = qualify_userdata_volume(probe)
        self.assertIn("host-volume-must-not-claim-android-fbe", result["blockers"])

    def test_distinct_userdata_and_metadata_form_host_volume_set(self) -> None:
        userdata = qualify_userdata_volume(self.probe)
        metadata_probe = copy.deepcopy(self.probe)
        metadata_probe["role"] = "metadata"
        metadata_probe["backing_file"] = "/var/lib/redroid-volumes/metadata.img"
        metadata_probe["filesystem_uuid"] = "metadata-uuid"
        metadata = qualify_userdata_volume(metadata_probe)
        result = qualify_fbe_volume_set(userdata, metadata)
        self.assertEqual(result["outcome"], "pass")
        self.assertFalse(result["android_fbe_proven"])

        metadata["probe"]["filesystem_uuid"] = self.probe.get("filesystem_uuid")
        result = qualify_fbe_volume_set(userdata, metadata)
        self.assertIn("volume-filesystem-uuids-not-distinct", result["blockers"])


if __name__ == "__main__":
    unittest.main()
