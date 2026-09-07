from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from alas_headless.macos_hvf_preflight import preflight_macos_hvf_external_adb
from alas_headless.runtime_command import RuntimeCommandResult, RuntimeExecutionPolicy


PACKAGE = "com.bilibili.azurlane"
COMPONENT = PACKAGE + "/com.manjuu.azurlane.MainActivity"


class ScriptedExecutor:
    def __init__(self, values):
        self.values = values
        self.calls = []
        self.policy = RuntimeExecutionPolicy(True, False)

    def run(self, spec):
        self.calls.append(spec)
        returncode, stdout, stderr = self.values[spec.label]
        return RuntimeCommandResult(spec.label, returncode, stdout, stderr, 1)


class MacosHvfPreflightTests(unittest.TestCase):
    def make_layout(self, root: Path) -> tuple[Path, Path]:
        sdk = root / "Library/Android/sdk"
        emulator = sdk / "emulator/emulator"
        adb = sdk / "platform-tools/adb"
        emulator.parent.mkdir(parents=True)
        adb.parent.mkdir(parents=True)
        emulator.write_text("tool", encoding="utf-8")
        adb.write_text("tool", encoding="utf-8")
        emulator.chmod(0o755)
        adb.chmod(0o755)
        avd_home = root / ".android/avd"
        config = avd_home / "alas_api32_arm64.avd/config.ini"
        config.parent.mkdir(parents=True)
        config.write_text(
            "abi.type=arm64-v8a\n"
            "hw.cpu.arch=arm64\n"
            "image.sysdir.1=system-images/android-32/google_apis/arm64-v8a/\n",
            encoding="utf-8",
        )
        return sdk, avd_home

    @staticmethod
    def successful_commands():
        return {
            "macos-hvf-acceleration-check": (0, "Hypervisor.Framework OS X Version 26.6\n", ""),
            "macos-hvf-avd-inventory": (0, "alas_api32_arm64\n", ""),
            "macos-hvf-adb-inventory": (0, "List of devices attached\nemulator-5554 device product:sdk_gphone64_arm64\n", ""),
            "macos-hvf-guest-abi-list": (0, "arm64-v8a,armeabi-v7a\n", ""),
            "macos-hvf-guest-api-level": (0, "32\n", ""),
            "macos-hvf-guest-build-fingerprint": (0, "google/test/fingerprint\n", ""),
            "macos-hvf-guest-package-paths": (0, "package:/data/app/game/base.apk\n", ""),
            "macos-hvf-guest-foreground": (0, "mResumedActivity: MainActivity\n", ""),
            "macos-hvf-guest-game-pid": (0, "7547\n", ""),
        }

    def test_emits_exact_external_adb_config_without_mutation(self):
        with tempfile.TemporaryDirectory() as temporary:
            sdk, avd_home = self.make_layout(Path(temporary))
            executor = ScriptedExecutor(self.successful_commands())
            evidence = preflight_macos_hvf_external_adb(
                avd_name="alas_api32_arm64",
                sdk_root=sdk,
                avd_home=avd_home,
                package=PACKAGE,
                component=COMPONENT,
                executor=executor,
                platform_name="darwin",
                machine="arm64",
            )

        self.assertEqual(evidence["outcome"], "pass")
        self.assertFalse(evidence["runtime_mutation_requested"])
        self.assertTrue(evidence["adb_server_may_start"])
        self.assertEqual(evidence["selected_serial"], "emulator-5554")
        self.assertEqual(evidence["runtime_config"]["backend"], "external-adb")
        self.assertEqual(evidence["runtime_config"]["unity_command_line"], "-force-gfx-st")
        self.assertTrue(evidence["runtime_config"]["allow_game_restart"])
        self.assertTrue(evidence["runtime_config"]["allow_android_restart"])
        self.assertTrue(all(not call.mutating for call in executor.calls))

    def test_ambiguous_devices_fail_closed_before_guest_probes(self):
        with tempfile.TemporaryDirectory() as temporary:
            sdk, avd_home = self.make_layout(Path(temporary))
            commands = self.successful_commands()
            commands["macos-hvf-adb-inventory"] = (
                0,
                "List of devices attached\n"
                "emulator-5554 device product:first\n"
                "emulator-5556 device product:second\n",
                "",
            )
            executor = ScriptedExecutor(commands)
            evidence = preflight_macos_hvf_external_adb(
                avd_name="alas_api32_arm64",
                sdk_root=sdk,
                avd_home=avd_home,
                package=PACKAGE,
                component=COMPONENT,
                executor=executor,
                platform_name="darwin",
                machine="arm64",
            )

        self.assertEqual(evidence["outcome"], "blocked")
        self.assertIn("running-emulator-selection-ambiguous", evidence["failures"])
        self.assertIsNone(evidence["runtime_config"])
        self.assertFalse(any(call.label.startswith("macos-hvf-guest-") for call in executor.calls))

    def test_wrong_host_and_guest_identity_are_localized_failures(self):
        with tempfile.TemporaryDirectory() as temporary:
            sdk, avd_home = self.make_layout(Path(temporary))
            commands = self.successful_commands()
            commands["macos-hvf-guest-abi-list"] = (0, "x86_64\n", "")
            commands["macos-hvf-guest-api-level"] = (0, "35\n", "")
            executor = ScriptedExecutor(commands)
            evidence = preflight_macos_hvf_external_adb(
                avd_name="alas_api32_arm64",
                sdk_root=sdk,
                avd_home=avd_home,
                package=PACKAGE,
                component=COMPONENT,
                executor=executor,
                platform_name="win32",
                machine="AMD64",
            )

        self.assertEqual(evidence["outcome"], "blocked")
        self.assertIn("apple-silicon-macos-required", evidence["failures"])
        self.assertIn("guest-api-or-abi-mismatch", evidence["failures"])
        self.assertNotIn("game-package-unavailable", evidence["failures"])


if __name__ == "__main__":
    unittest.main()
