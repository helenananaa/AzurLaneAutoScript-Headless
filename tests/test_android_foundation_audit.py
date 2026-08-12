from __future__ import annotations

import unittest

from alas_headless.android_foundation_audit import PROBES
from alas_headless.android_foundation_audit import cpu_busy_percent
from alas_headless.android_foundation_audit import parse_total_ram_kib
from alas_headless.android_foundation_audit import parse_ram_breakdown_kib
from alas_headless.android_foundation_audit import native_fbe_passes
from alas_headless.android_image_policy import REQUIRED_PROTECTED_CAPABILITIES
from alas_headless.android_update_lab import AndroidUpdateLabError


class AndroidFoundationAuditTests(unittest.TestCase):
    def test_static_probes_plus_cross_layer_external_storage_cover_policy(self) -> None:
        observed = {probe.capability for probe in PROBES} | {
            "device-encrypted-storage", "external-app-storage"
        }
        self.assertEqual(observed, set(REQUIRED_PROTECTED_CAPABILITIES))

    def test_cpu_busy_percent(self) -> None:
        before = "cpu  100 0 50 850 0 0 0 0 0 0\n"
        after = "cpu  120 0 60 920 0 0 0 0 0 0\n"
        self.assertEqual(cpu_busy_percent(before, after), 30.0)

    def test_cpu_busy_rejects_invalid_delta(self) -> None:
        with self.assertRaises(AndroidUpdateLabError):
            cpu_busy_percent("cpu  1 0 0 9\n", "cpu  1 0 0 9\n")

    def test_total_ram_parser(self) -> None:
        self.assertEqual(parse_total_ram_kib(" Total RAM: 2,013,296K (status normal)"), 2013296)

    def test_ram_breakdown_parser(self) -> None:
        value = parse_ram_breakdown_kib(" Used RAM: 1,000K\n Free RAM: 2,500K\n")
        self.assertEqual(value, {"used_ram_kib": 1000, "free_ram_kib": 2500})

    def test_native_fbe_requires_all_independent_signals(self) -> None:
        values = {
            "crypto_state": "encrypted",
            "crypto_type": "file",
            "package_feature": "true",
            "storage_manager_mode": "native",
            "vold_mount_service": "Service mount: found",
        }
        self.assertTrue(native_fbe_passes(values))
        for name in values:
            changed = dict(values)
            changed[name] = ""
            self.assertFalse(native_fbe_passes(changed), name)

    def test_emulated_fbe_does_not_satisfy_device_storage_gate(self) -> None:
        self.assertFalse(native_fbe_passes({
            "crypto_state": "encrypted",
            "crypto_type": "file",
            "package_feature": "true",
            "storage_manager_mode": "emulated",
            "vold_mount_service": "Service mount: found",
        }))


if __name__ == "__main__":
    unittest.main()
