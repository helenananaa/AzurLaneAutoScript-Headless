"""Transport regression cases for the adapter."""

import unittest
from alas_headless import (
    AndroidPackageFingerprint,
    PinnedPackageGate,
    SemanticGateClosed,
)
from alas_headless.semantic_oracle import ObserverTransportError
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import (
    FakePackageBridge,
    ScriptedAdbBridge,
    bridge_package,
)


class AlasSemanticAdapterTests(AlasSemanticAdapterTestsSupport, unittest.TestCase):
    def test_package_gate_verifies_once_per_bridge_pid(self):
        bridge = FakePackageBridge()
        gate = PinnedPackageGate(bridge)

        gate()
        gate()
        bridge.pid = 5678
        gate()

        self.assertEqual(
            bridge.calls,
            ["x86_64", "x86_64"],
        )

    def test_package_gate_requires_open_bridge(self):
        bridge = FakePackageBridge()
        bridge.pid = None

        with self.assertRaises(SemanticGateClosed):
            PinnedPackageGate(bridge)()


class PackageFingerprintTests(unittest.TestCase):
    def test_swipe_uses_one_exact_adb_input_command(self):
        command = (
            "shell",
            "input",
            "swipe",
            "1257",
            "330",
            "1257",
            "390",
            "500",
        )
        bridge = ScriptedAdbBridge({command: ""})

        bridge.swipe(1257, 330, 1257, 390, 500)

    def test_reads_independent_version_abi_and_hash_identity(self):
        expected = AndroidPackageFingerprint(
            version_name="9.7.10",
            version_code=9710,
            primary_abi="x86_64",
            base_apk_sha256="a" * 64,
            il2cpp_sha256="b" * 64,
        )
        native_dir = "/data/app/~~token/pkg/lib/x86_64"
        base_apk = "/data/app/~~token/pkg/base.apk"
        il2cpp = native_dir + "/libil2cpp.so"
        bridge = ScriptedAdbBridge(
            {
                ("shell", "dumpsys", "package", bridge_package()): (
                    "versionCode=9710 minSdk=21\n"
                    "versionName=9.7.10\n"
                    "primaryCpuAbi=x86_64\n"
                    "legacyNativeLibraryDir={0}\n".format(native_dir)
                ),
                ("shell", "pm", "path", bridge_package()): "package:" + base_apk,
                (
                    "shell",
                    "find",
                    native_dir,
                    "-type",
                    "f",
                    "-name",
                    "libil2cpp.so",
                    "-print",
                ): il2cpp,
                ("shell", "sha256sum", base_apk): "{0}  {1}".format(
                    expected.base_apk_sha256, base_apk
                ),
                ("shell", "sha256sum", il2cpp): "{0}  {1}".format(
                    expected.il2cpp_sha256, il2cpp
                ),
            }
        )

        self.assertEqual(bridge.require_package_fingerprint(expected), expected)

    def test_compatibility_rejects_only_concrete_unsupported_abi(self):
        native_dir = "/data/app/~~new-token/pkg/lib/arm64"
        bridge = ScriptedAdbBridge(
            {
                ("shell", "dumpsys", "package", bridge_package()): (
                    "versionCode=10000 minSdk=21\n"
                    "versionName=10.0.0\n"
                    "primaryCpuAbi=arm64-v8a\n"
                    "legacyNativeLibraryDir={0}\n".format(native_dir)
                ),
            }
        )

        with self.assertRaisesRegex(SemanticGateClosed, "ABI is unsupported"):
            bridge.require_package_compatibility("x86_64")

        self.assertEqual(len(bridge.calls), 1)

    def test_retries_exact_device_hash_once_after_cold_start_adb_failure(self):
        path = "/data/app/~~token/pkg/base.apk"
        testcase = self

        class HashRetryBridge(ScriptedAdbBridge):
            def __init__(self):
                super().__init__({})
                self.calls = 0

            def _run(self, arguments, timeout_seconds=None):
                testcase.assertEqual(
                    tuple(arguments), ("shell", "sha256sum", path)
                )
                testcase.assertEqual(timeout_seconds, 120.0)
                self.calls += 1
                if self.calls == 1:
                    raise ObserverTransportError("transient adb failure")
                return "{0}  {1}".format("a" * 64, path)

        bridge = HashRetryBridge()
        bridge._DEVICE_SHA256_RETRY_DELAY_SECONDS = 0.0

        self.assertEqual(bridge._device_sha256(path), "a" * 64)
        self.assertEqual(bridge.calls, 2)

    def test_rejects_non_allowlisted_fingerprint(self):
        expected = AndroidPackageFingerprint("1", 1, "x86_64", "a" * 64, "b" * 64)
        actual = AndroidPackageFingerprint("2", 2, "x86_64", "c" * 64, "d" * 64)

        class MismatchBridge(ScriptedAdbBridge):
            def package_fingerprint(self):
                return actual

        with self.assertRaises(SemanticGateClosed):
            MismatchBridge({}).require_package_fingerprint(expected)
