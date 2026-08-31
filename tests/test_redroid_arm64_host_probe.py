from __future__ import annotations

import unittest

from alas_headless.redroid_arm64_host import probe_redroid_arm64_host


class RedroidArm64HostProbeTests(unittest.TestCase):
    @staticmethod
    def probe(kernel_config: str):
        return probe_redroid_arm64_host(
            architecture="aarch64",
            docker_cli_present=True,
            cgroup_v2_present=True,
            binder_present=True,
            image="registry.example/redroid@sha256:" + "a" * 64,
            kernel_release="6.1.176-alas-va-test",
            kernel_config_source="/proc/config.gz",
            kernel_config=kernel_config,
        )

    def test_39_bit_va_kernel_allows_old_luajit_game_capability(self) -> None:
        evidence = self.probe("CONFIG_ARM64=y\nCONFIG_ARM64_VA_BITS=39\n")
        self.assertEqual(evidence["outcome"], "pass")
        self.assertEqual(evidence["kernel_va_bits"], 39)
        self.assertEqual(evidence["game_lightuserdata_va_outcome"], "pass")
        self.assertEqual(evidence["failures"], [])

    def test_48_bit_va_kernel_blocks_only_the_game_pointer_capability(self) -> None:
        evidence = self.probe("CONFIG_ARM64=y\nCONFIG_ARM64_VA_BITS=48\n")
        self.assertEqual(evidence["outcome"], "blocked")
        self.assertEqual(evidence["kernel_va_bits"], 48)
        self.assertEqual(evidence["game_lightuserdata_va_outcome"], "blocked")
        self.assertEqual(
            evidence["failures"],
            ["arm64-game-lightuserdata-va-window-exceeds-47-bits"],
        )

    def test_missing_kernel_config_fails_closed_with_reentry_reason(self) -> None:
        evidence = probe_redroid_arm64_host(
            architecture="aarch64",
            docker_cli_present=True,
            cgroup_v2_present=True,
            binder_present=True,
            image="registry.example/redroid@sha256:" + "b" * 64,
            kernel_release="6.1.176-alas-va-test",
            kernel_config_source=None,
            kernel_config=None,
        )
        self.assertEqual(evidence["outcome"], "blocked")
        self.assertEqual(evidence["kernel_va_bits"], None)
        self.assertEqual(evidence["failures"], ["arm64-kernel-config-unavailable"])


if __name__ == "__main__":
    unittest.main()
