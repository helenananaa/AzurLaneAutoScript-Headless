from __future__ import annotations

import json
import hashlib
import tempfile
import unittest
from pathlib import Path

from alas_headless.runtime_backend import BackendKind
from alas_headless.runtime_artifacts import RuntimeLock
from alas_headless.runtime_backend_macos_hvf import (
    MacosHvfBackend,
    MacosHvfRuntimeConfig,
)
from alas_headless.runtime_backends import backend_from_config
from alas_headless.runtime_backends import RuntimeIdentityMismatch
from alas_headless.runtime_command import (
    RuntimeCommandResult,
    RuntimeExecutionPolicy,
    RuntimeOwnedProcess,
)


PACKAGE = "com.bilibili.azurlane"
COMPONENT = PACKAGE + "/com.manjuu.azurlane.MainActivity"


class ScriptedExecutor:
    def __init__(self, values=None):
        self.values = dict(values or {})
        self.calls = []
        self.started = []
        self.stopped = []
        self.policy = RuntimeExecutionPolicy(True, True)

    def run(self, spec):
        self.calls.append(spec)
        returncode, stdout, stderr = self.values.get(spec.label, (0, "", ""))
        return RuntimeCommandResult(spec.label, returncode, stdout, stderr, 1)

    def start(self, spec, handle_id):
        self.started.append(spec)
        return RuntimeOwnedProcess(handle_id, 4321, spec.label)

    def stop_owned(self, process, timeout_seconds=30.0):
        self.stopped.append(process)
        return 0


class MacosHvfBackendTests(unittest.TestCase):
    def make_config(self, root: Path, **overrides):
        sdk = root / "Library/Android/sdk"
        emulator = sdk / "emulator/emulator"
        adb = sdk / "platform-tools/adb"
        emulator.parent.mkdir(parents=True)
        adb.parent.mkdir(parents=True)
        emulator.write_text("tool", encoding="utf-8")
        adb.write_text("tool", encoding="utf-8")
        avd_home = root / ".android/avd"
        config_path = avd_home / "alas_api32_arm64.avd/config.ini"
        config_path.parent.mkdir(parents=True)
        config_path.write_text(
            "abi.type=arm64-v8a\n"
            "hw.cpu.arch=arm64\n"
            "image.sysdir.1=system-images/android-32/google_apis/arm64-v8a/\n",
            encoding="utf-8",
        )
        system_image = sdk / "system-images/android-32/google_apis/arm64-v8a/system.img"
        system_image.parent.mkdir(parents=True)
        system_image.write_bytes(b"system-image")
        provision_profile = root / "macos-hvf-provision-profile.json"
        provision_profile.write_text("{}", encoding="utf-8")
        values = {
            "serial": "emulator-5554",
            "package": PACKAGE,
            "component": COMPONENT,
            "host_class": "macos-arm64-hvf",
            "emulator": emulator,
            "adb": adb,
            "sdk_root": sdk,
            "avd_name": "alas_api32_arm64",
            "avd_home": avd_home,
            "provision_profile": provision_profile,
            "console_port": 5554,
            "poll_interval_seconds": 0.01,
        }
        values.update(overrides)
        return MacosHvfRuntimeConfig(**values)

    def test_probe_accepts_hvf_and_arm64_avd_without_exact_os_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.make_config(Path(temporary))
            executor = ScriptedExecutor(
                {
                    "macos-hvf-acceleration-check": (
                        0,
                        "accel: 0\nHypervisor.Framework OS X Version 99.1\n",
                        "",
                    ),
                    "macos-hvf-avd-inventory": (0, "alas_api32_arm64\n", ""),
                }
            )
            backend = MacosHvfBackend(
                config,
                executor,
                host_probe=lambda: (
                    True,
                    "ready",
                    {"platform": "darwin", "machine": "arm64"},
                ),
            )
            probe = backend.probe_host()

        self.assertTrue(probe.available)
        self.assertEqual(probe.backend, BackendKind.MACOS_HVF)
        self.assertEqual(probe.host_fingerprint["acceleration"], "hypervisor.framework")

    def test_unavailable_host_stays_local_to_macos_backend(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.make_config(Path(temporary))
            executor = ScriptedExecutor()
            backend = MacosHvfBackend(
                config,
                executor,
                host_probe=lambda: (
                    False,
                    "macos-required",
                    {"platform": "win32", "machine": "AMD64"},
                ),
            )
            probe = backend.probe_host()

        self.assertFalse(probe.available)
        self.assertEqual(probe.reason, "macos-required")
        self.assertNotIn("acceleration", probe.host_fingerprint)
        self.assertEqual(executor.calls, [])

    def test_start_and_stop_own_only_the_spawned_emulator(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = self.make_config(Path(temporary))
            executor = ScriptedExecutor(
                {"macos-hvf-adb-device-inventory": (0, "List of devices attached\n", "")}
            )
            backend = MacosHvfBackend(config, executor)
            instance = backend.start({})
            backend.stop(instance)

        self.assertTrue(instance["owned"])
        self.assertEqual(instance["serial"], "emulator-5554")
        arguments = executor.started[0].argv
        self.assertIn("-accel", arguments)
        self.assertIn("-no-window", arguments)
        self.assertNotIn("taskset", arguments)
        self.assertNotIn("numactl", arguments)
        self.assertTrue(executor.started[0].mutating)
        self.assertEqual(len(executor.stopped), 1)
        self.assertTrue(backend.supports_recovery("game"))
        self.assertTrue(backend.supports_recovery("android"))

    def test_factory_loads_example_and_rejects_unowned_linux_tuning(self):
        root = Path(__file__).resolve().parents[1]
        value = json.loads(
            (root / "integration/runtime/macos-hvf.config.example.json").read_text(
                encoding="utf-8"
            )
        )
        backend = backend_from_config(value, ScriptedExecutor())
        self.assertIsInstance(backend, MacosHvfBackend)
        invalid = dict(value, cpu_affinity="0-3")
        with self.assertRaisesRegex(ValueError, "unknown=cpu_affinity"):
            backend_from_config(invalid, ScriptedExecutor())

    def test_example_runtime_lock_is_arm64_and_owned_by_macos_hvf(self):
        root = Path(__file__).resolve().parents[1]
        lock = RuntimeLock.from_mapping(
            json.loads(
                (
                    root
                    / "integration/runtime/runtime-lock.macos-hvf.example.json"
                ).read_text(encoding="utf-8")
            )
        )
        self.assertEqual(lock.document["android"]["backend"], "macos-hvf")
        self.assertEqual(lock.document["android"]["abi"], "arm64-v8a")
        self.assertEqual(lock.document["userdata"]["account_scope"], "per-instance")

    def test_runtime_lock_rejects_x86_guest_for_macos_hvf(self):
        root = Path(__file__).resolve().parents[1]
        value = json.loads(
            (
                root / "integration/runtime/runtime-lock.macos-hvf.example.json"
            ).read_text(encoding="utf-8")
        )
        value["angle"]["abi"] = "x86_64"
        value["android"]["abi"] = "x86_64"
        value["game"]["abi"] = "x86_64"
        with self.assertRaisesRegex(
            ValueError, "macos-hvf requires the arm64-v8a ABI"
        ):
            RuntimeLock.from_mapping(value)

    def test_provision_binds_system_image_and_profile_hashes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = self.make_config(root)
            value = json.loads(
                (
                    Path(__file__).resolve().parents[1]
                    / "integration/runtime/runtime-lock.macos-hvf.example.json"
                ).read_text(encoding="utf-8")
            )
            system_image = (
                config.sdk_root
                / "system-images/android-32/google_apis/arm64-v8a/system.img"
            )
            value["android"]["system_image_sha256"] = hashlib.sha256(
                system_image.read_bytes()
            ).hexdigest()
            value["android"]["provision_profile_sha256"] = hashlib.sha256(
                config.provision_profile.read_bytes()
            ).hexdigest()
            lock = RuntimeLock.from_mapping(value)
            backend = MacosHvfBackend(config, ScriptedExecutor())
            artifacts = backend.resolve_artifacts(lock)
            provisioned = backend.provision(artifacts)
            self.assertEqual(provisioned["system_image"], str(system_image.resolve()))
            system_image.write_bytes(b"drift")
            with self.assertRaisesRegex(
                RuntimeIdentityMismatch, "system-image-hash-mismatch"
            ):
                backend.provision(artifacts)

    def test_config_rejects_mismatched_serial_and_non_headless_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "serial must match"):
                self.make_config(root, serial="emulator-5556")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError, "requires Unity -force-gfx-st"):
                self.make_config(root, unity_command_line="")


if __name__ == "__main__":
    unittest.main()
