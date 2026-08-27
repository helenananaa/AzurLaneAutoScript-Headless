from __future__ import annotations

import unittest

from alas_headless.redroid_x86_host import (
    classify_kernel_event_errors,
    probe_redroid_x86_host,
)


CUSTOM_CONFIG = """\
CONFIG_ANDROID_BINDER_IPC=m
CONFIG_DM_CRYPT=m
CONFIG_DM_DEFAULT_KEY=y
CONFIG_DM_VERITY=m
CONFIG_IP_NF_FILTER=m
CONFIG_NF_CONNTRACK=m
CONFIG_QFMT_V2=m
"""
MODULES = (
    "binder_linux",
    "dm_crypt",
    "dm_verity",
    "iptable_filter",
    "nf_conntrack",
    "quota_v2",
)


class RedroidX86HostProbeTests(unittest.TestCase):
    @staticmethod
    def probe(**overrides):
        values = {
            "architecture": "x86_64",
            "ctr_cli_present": True,
            "cgroup_v2_present": True,
            "image": "docker.io/alas/redroid@sha256:" + "a" * 64,
            "kernel_release": "6.17.13-alas-dmdefault",
            "kernel_config_source": "/boot/config-6.17.13-alas-dmdefault",
            "kernel_config": CUSTOM_CONFIG,
            "dm_targets": ("crypt", "default-key", "verity"),
            "available_modules": MODULES,
            "loaded_modules": MODULES,
            "recovery_default_kernel": "7.0.0-1011-aws",
        }
        values.update(overrides)
        return probe_redroid_x86_host(**values)

    def test_complete_custom_kernel_and_stock_recovery_default_pass(self) -> None:
        evidence = self.probe()
        self.assertEqual(evidence["outcome"], "pass")
        self.assertEqual(evidence["failures"], [])

    def test_stock_kernel_without_default_key_is_blocked(self) -> None:
        evidence = self.probe(
            kernel_release="7.0.0-1011-aws",
            kernel_config=CUSTOM_CONFIG.replace("CONFIG_DM_DEFAULT_KEY=y\n", ""),
            dm_targets=("crypt", "verity"),
            recovery_default_kernel="6.17.13-alas-dmdefault",
        )
        self.assertEqual(evidence["outcome"], "blocked")
        self.assertIn("x86-dm-default-key-config-unavailable", evidence["failures"])
        self.assertIn("x86-dm-default-key-target-unavailable", evidence["failures"])
        self.assertNotIn("experimental-kernel-is-recovery-default", evidence["failures"])

    def test_missing_required_module_is_blocked(self) -> None:
        evidence = self.probe(
            available_modules=tuple(item for item in MODULES if item != "binder_linux")
        )
        self.assertEqual(evidence["outcome"], "blocked")
        self.assertIn("binder_linux-module-unavailable", evidence["failures"])

    def test_available_but_unloaded_quota_module_is_blocked(self) -> None:
        evidence = self.probe(
            loaded_modules=tuple(item for item in MODULES if item != "quota_v2")
        )
        self.assertEqual(evidence["outcome"], "blocked")
        self.assertIn("quota_v2-module-not-loaded", evidence["failures"])

    def test_experimental_kernel_cannot_be_recovery_default(self) -> None:
        evidence = self.probe(
            recovery_default_kernel="6.17.13-alas-dmdefault"
        )
        self.assertEqual(evidence["outcome"], "blocked")
        self.assertIn("experimental-kernel-is-recovery-default", evidence["failures"])

    def test_observed_io_error_spelling_stops_future_runs(self) -> None:
        evidence = classify_kernel_event_errors(
            "ueventd: Error reading from Uevent Fd: I/O error\n"
            "ueventd: Error reading from Uevent Fd: I/O error\n"
            "NetlinkListener: recvmsg failed (I/O error)\n"
        )
        self.assertEqual(evidence["outcome"], "repeated-eio")
        self.assertEqual(evidence["uevent_io_error_count"], 2)
        self.assertEqual(evidence["netlink_io_error_count"], 1)

    def test_unrelated_kernel_messages_do_not_trip_event_stop(self) -> None:
        evidence = classify_kernel_event_errors(
            "EXT4-fs: mounted filesystem\ncontainerd: task started\n"
        )
        self.assertEqual(evidence["outcome"], "clear")
        self.assertEqual(evidence["total_io_error_count"], 0)


if __name__ == "__main__":
    unittest.main()
