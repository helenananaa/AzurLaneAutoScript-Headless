import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from alas_headless.runtime_artifacts import RuntimeLock, resource_set_id
from alas_headless.runtime_backend import BackendKind
from alas_headless.runtime_backend_adb import (
    ExternalAdbBackend as ExternalAdbBackendImplementation,
)
from alas_headless.runtime_backend_deferred import (
    DeferredRuntimeBackend as DeferredRuntimeBackendImplementation,
)
from alas_headless.runtime_backend_kvm import KvmBackend as KvmBackendImplementation
from alas_headless.runtime_backends import (
    DeferredRuntimeBackend,
    ExternalAdbBackend,
    ExternalAdbConfig,
    KvmBackend,
    KvmRuntimeConfig,
    RuntimeBackendNotReady,
    RuntimeIdentityMismatch,
    backend_from_config,
)
from alas_headless.runtime_command import (
    RuntimeCommandResult,
    RuntimeExecutionPolicy,
    RuntimeOwnedProcess,
)

HASH = "a" * 64
COMMIT = "b" * 40
PACKAGE = "com.bilibili.azurlane"
COMPONENT = PACKAGE + "/com.manjuu.azurlane.MainActivity"


def make_lock(backend):
    manifest_hash = HASH
    abi = "arm64-v8a" if backend in ("external-adb", "arm64-qemu") else "x86_64"
    return RuntimeLock.from_mapping(
        {
            "schema": "alas-headless.runtime-lock/v1",
            "core": {
                "core_commit": COMMIT,
                "alas_upstream_commit": "c" * 40,
                "alas_patch_sha256": HASH,
                "alas_patch_series_manifest_sha256": HASH,
            },
            "angle": {
                "revision": "d" * 40,
                "patchset_sha256": HASH,
                "abi": abi,
                "apk_sha256": HASH,
                "observer_schema": "alas-headless.observer/v1",
            },
            "android": {
                "backend": backend,
                "build_fingerprint": "test/android/build",
                "api_level": 35,
                "abi": abi,
                "system_image_sha256": HASH,
                "provision_profile_sha256": HASH,
            },
            "game": {
                "package": PACKAGE,
                "region": "cn",
                "version_name": "9.9.9",
                "version_code": 999,
                "abi": abi,
                "base_apk_sha256": HASH,
                "libil2cpp_sha256": HASH,
            },
            "resources": {
                "resource_set_id": resource_set_id("cn", "9.9.9", manifest_hash),
                "resource_epoch": 1,
                "manifest_sha256": manifest_hash,
                "shared_public_paths": ["game/public-assets"],
            },
            "userdata": {
                "generation": 1,
                "account_scope": (
                    "external-device" if backend == "external-adb" else "per-instance"
                ),
            },
        }
    )


class ScriptedExecutor:
    def __init__(self, results=None):
        self.results = dict(results or {})
        self.calls = []
        self.started = []
        self.stopped = []
        self.policy = RuntimeExecutionPolicy(True, True)

    def run(self, spec):
        self.calls.append(spec)
        value = self.results.get(spec.label, (0, "", ""))
        if isinstance(value, list):
            value = value.pop(0)
        return RuntimeCommandResult(spec.label, value[0], value[1], value[2], 1)

    def start(self, spec, handle_id):
        self.started.append(spec)
        return RuntimeOwnedProcess(handle_id, 4321, spec.label)

    def stop_owned(self, process, timeout_seconds=30.0):
        self.stopped.append(process)
        return 0


class FakeBridge:
    def __init__(self, serial, package, **kwargs):
        self.serial = serial
        self.package = package
        self.pid = 1234
        self.closed = False

    def open(self):
        return self

    def request(self, request):
        if request == "GET /v1/state\n":
            return {
                "protocol_schema": "alas-headless.observer/v1",
                "status": "ok",
                "snapshot": {
                    "protocol_schema": "alas-headless.observer/v1",
                    "status": "ok",
                    "snapshot_schema": 1,
                    "package": PACKAGE,
                    "pid": 1234,
                    "driver_revision": "d" * 40,
                    "generation": 10,
                },
                "buttons": {
                    "protocol_schema": "alas-headless.observer/v1",
                    "semantic_schema": "alas-headless.buttons/v1",
                    "status": "ok",
                    "schema": 1,
                    "package": PACKAGE,
                    "pid": 1234,
                    "driver_revision": "d" * 40,
                    "generation": 10,
                },
            }
        raise AssertionError(request)

    def require_package_compatibility(self, required_primary_abi):
        if required_primary_abi != "arm64-v8a":
            raise AssertionError(required_primary_abi)
        return {
            # Deliberately differs from the runtime lock: updated games must
            # be attempted when the concrete ABI/layout remains compatible.
            "version_name": "10.0.0",
            "version_code": 10000,
            "primary_abi": "arm64-v8a",
            "base_apk_path": "/data/app/pkg/base.apk",
            "il2cpp_path": "/data/app/pkg/lib/arm64/libil2cpp.so",
        }

    def _device_sha256(self, path, **kwargs):
        if path != "/data/app/pkg/lib/arm64/libil2cpp.so":
            raise AssertionError(path)
        return "e" * 64

    def close(self):
        self.closed = True


class FlakyObserverBridge(FakeBridge):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_count = 0

    def request(self, request):
        self.request_count += 1
        if self.request_count == 1:
            raise RuntimeError("observer is still starting")
        return super().request(request)


class StartingObserverBridge(FakeBridge):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_count = 0

    def request(self, request):
        self.request_count += 1
        value = super().request(request)
        if self.request_count == 1:
            value["snapshot"]["status"] = "initializing"
        return value


class RuntimeBackendsTests(unittest.TestCase):
    def test_compatibility_facade_reexports_split_implementations(self):
        self.assertIs(ExternalAdbBackend, ExternalAdbBackendImplementation)
        self.assertIs(KvmBackend, KvmBackendImplementation)
        self.assertIs(DeferredRuntimeBackend, DeferredRuntimeBackendImplementation)

    def test_external_adb_reference_backend_completes_read_only_identity_path(self):
        results = {
            "adb-version": (0, "Android Debug Bridge version 1", ""),
            "adb-get-state": (0, "device", ""),
            "android-boot-completed": (0, "1", ""),
            "android-package-manager": (
                0,
                "package:/system/framework/framework-res.apk",
                "",
            ),
            "game-pid": (0, "1234", ""),
            "game-foreground": (
                0,
                "topResumedActivity=ActivityRecord{x u0 " + COMPONENT + " t1}",
                "",
            ),
            "android-build-fingerprint": (0, "test/android/build", ""),
            "android-primary-abi": (0, "arm64-v8a", ""),
            "android-api-level": (0, "35", ""),
            "angle-package-path": (
                0,
                "package:/data/app/~~install/org.chromium.angle/base.apk",
                "",
            ),
            "angle-apk-sha256": (0, HASH, ""),
        }
        executor = ScriptedExecutor(results)
        backend = ExternalAdbBackend(
            ExternalAdbConfig("device-1", PACKAGE, COMPONENT, "android-arm64-test"),
            executor,
            bridge_factory=FakeBridge,
            sleep=lambda _: None,
        )
        lock = make_lock("external-adb")
        self.assertTrue(backend.probe_host().available)
        artifacts = backend.resolve_artifacts(lock)
        instance = backend.start(backend.provision(artifacts))
        self.assertEqual(backend.wait_adb(instance, 1.0), "device-1")
        self.assertTrue(backend.wait_android_ready(instance, 1.0)["boot_completed"])
        self.assertEqual(backend.wait_game_ready(instance, 1.0)["pid"], 1234)
        self.assertTrue(backend.wait_observer_ready(instance, 1.0)["atomic"])
        actual_fingerprint = backend.fingerprint(instance)
        self.assertEqual(actual_fingerprint["backend"], "external-adb")
        self.assertEqual(actual_fingerprint["game_version"], "10.0.0")
        self.assertEqual(actual_fingerprint["libil2cpp_sha256"], "e" * 64)
        backend.stop(instance)

        executor.results["angle-apk-sha256"] = (0, "b" * 64, "")
        mismatched = ExternalAdbBackend(
            ExternalAdbConfig("device-1", PACKAGE, COMPONENT, "android-arm64-test"),
            executor,
            bridge_factory=FakeBridge,
            sleep=lambda _: None,
        )
        mismatched.resolve_artifacts(lock)
        mismatch_instance = mismatched.start({})
        mismatched.wait_observer_ready(mismatch_instance, 1.0)
        with self.assertRaisesRegex(
            RuntimeIdentityMismatch, "angle-package-fingerprint-mismatch"
        ):
            mismatched.fingerprint(mismatch_instance)
        mismatched.stop(mismatch_instance)

    def test_kvm_backend_refuses_serial_reuse_and_uses_compatibility_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "releases" / "test"
            emulator = release / "emulator" / "emulator"
            emulator_check = release / "emulator" / "emulator-check"
            adb = release / "sdk" / "platform-tools" / "adb"
            avd_home = root / "avd"
            config_path = avd_home / "test.avd" / "config.ini"
            for path in (emulator, emulator_check, adb):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("test", encoding="utf-8")
            config_path.parent.mkdir(parents=True)
            config_path.write_text(
                f"image.sysdir.1={release / 'images'}/\n",
                encoding="utf-8",
            )
            executor = ScriptedExecutor(
                {
                    "emulator-acceleration-check": (0, "accel: 0", ""),
                    "adb-device-inventory": (
                        0,
                        "List of devices attached\n127.0.0.1:5589\tdevice",
                        "",
                    ),
                }
            )
            backend = KvmBackend(
                KvmRuntimeConfig(
                    "127.0.0.1:5589",
                    PACKAGE,
                    COMPONENT,
                    "linux-x86_64-kvm",
                    emulator,
                    emulator_check,
                    adb,
                    "test",
                    avd_home,
                    5588,
                    5043,
                    release,
                    release / "sdk",
                ),
                executor,
                kvm_probe=lambda: (True, "ready", {"kvm_api_version": "12"}),
                release_verifier=lambda path: path,
            )
            self.assertTrue(backend.probe_host().available)
            backend.resolve_artifacts(make_lock("kvm"))
            provisioned = backend.provision({"runtime_lock_sha256": HASH})
            with self.assertRaisesRegex(Exception, "emulator-serial-already-in-use"):
                backend.start(provisioned)
            inventory = next(
                spec for spec in executor.calls if spec.label == "adb-device-inventory"
            )
            self.assertEqual(
                inventory.argv,
                (str(adb), "-P", "5043", "devices"),
            )
            self.assertEqual(
                backend._adb_spec("test", ("get-state",)).argv,
                (str(adb), "-P", "5043", "-s", "127.0.0.1:5589", "get-state"),
            )
            plan = backend.qualification_plan(make_lock("kvm"))
            self.assertFalse(plan["compatibility_start_profile"]["experimental_tuning"])
            self.assertNotIn("vcpu", json.dumps(plan).lower())
            self.assertNotIn("mttcg", json.dumps(plan).lower())

            config_path.write_text(
                "image.sysdir.1=/srv/android-cache/out/kvm-14-r75-x86_64/\n",
                encoding="utf-8",
            )
            rejected = backend.probe_host()
            self.assertFalse(rejected.available)
            self.assertEqual(rejected.reason, "kvm-runtime-release-invalid")
            with self.assertRaisesRegex(
                RuntimeBackendNotReady,
                "kvm-avd-image-sysdir-outside-release",
            ):
                backend.provision({"runtime_lock_sha256": HASH})

    def test_kvm_wait_adb_reconnects_tcp_transport_through_private_server(self):
        executor = ScriptedExecutor(
            {
                "adb-transport-connect": (0, "connected", ""),
                "adb-get-state": (0, "device", ""),
            }
        )
        backend = KvmBackend(
            KvmRuntimeConfig(
                "127.0.0.1:5589",
                PACKAGE,
                COMPONENT,
                "linux-x86_64-kvm",
                Path("/runtime/releases/test/emulator/emulator"),
                Path("/runtime/releases/test/emulator/emulator-check"),
                Path("/runtime/releases/test/sdk/platform-tools/adb"),
                "test",
                Path("/runtime/avd"),
                5588,
                5043,
                Path("/runtime/releases/test"),
                Path("/runtime/releases/test/sdk"),
            ),
            executor,
            kvm_probe=lambda: (True, "ready", {}),
            sleep=lambda _: None,
        )

        self.assertEqual(backend.wait_adb({}, 1.0), "127.0.0.1:5589")
        connect, state = executor.calls
        self.assertEqual(
            connect.argv,
            (
                str(Path("/runtime/releases/test/sdk/platform-tools/adb")),
                "-P",
                "5043",
                "connect",
                "127.0.0.1:5589",
            ),
        )
        self.assertNotIn("-s", connect.argv)
        self.assertTrue(connect.mutating)
        self.assertEqual(
            state.argv,
            (
                str(Path("/runtime/releases/test/sdk/platform-tools/adb")),
                "-P",
                "5043",
                "-s",
                "127.0.0.1:5589",
                "get-state",
            ),
        )

    def test_kvm_emulator_process_path_prefers_verified_release_adb(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "releases" / "test"
            sdk_root = release / "sdk"
            adb = sdk_root / "platform-tools" / "adb"
            backend = KvmBackend(
                KvmRuntimeConfig(
                    "127.0.0.1:5589",
                    PACKAGE,
                    COMPONENT,
                    "linux-x86_64-kvm",
                    release / "emulator" / "emulator",
                    release / "emulator" / "emulator-check",
                    adb,
                    "test",
                    root / "avd",
                    5588,
                    5043,
                    release,
                    sdk_root,
                ),
                ScriptedExecutor(
                    {"adb-device-inventory": (0, "List of devices attached\n", "")}
                ),
                kvm_probe=lambda: (True, "ready", {}),
            )
            inherited = os.pathsep.join((str(root / "host-bin"), "/usr/bin"))
            with patch.dict(os.environ, {"PATH": inherited}, clear=False):
                backend.start({})

            started = backend.executor.started[0]
            expected_platform_tools = str((release / "sdk" / "platform-tools").resolve())
            self.assertEqual(
                started.environment["PATH"],
                expected_platform_tools + os.pathsep + inherited,
            )
            self.assertEqual(started.environment["ANDROID_SDK_ROOT"], str(sdk_root.resolve()))
            self.assertEqual(started.environment["ANDROID_ADB_SERVER_PORT"], "5043")

    def test_kvm_config_rejects_adb_outside_its_pinned_release(self):
        release = Path("/runtime/releases/test")
        with self.assertRaisesRegex(ValueError, "one pinned release"):
            KvmRuntimeConfig(
                "127.0.0.1:5589",
                PACKAGE,
                COMPONENT,
                "linux-x86_64-kvm",
                release / "emulator" / "emulator",
                release / "emulator" / "emulator-check",
                Path("/usr/bin/adb"),
                "test",
                Path("/runtime/avd"),
                5588,
                5043,
                release,
                release / "sdk",
            )

    def test_kvm_wait_adb_retries_connect_after_private_server_restart(self):
        executor = ScriptedExecutor(
            {
                "adb-transport-connect": [
                    (1, "", "server starting"),
                    (0, "connected", ""),
                ],
                "adb-get-state": (0, "device", ""),
            }
        )
        backend = KvmBackend(
            KvmRuntimeConfig(
                "127.0.0.1:5589",
                PACKAGE,
                COMPONENT,
                "linux-x86_64-kvm",
                Path("/runtime/releases/test/emulator/emulator"),
                Path("/runtime/releases/test/emulator/emulator-check"),
                Path("/runtime/releases/test/sdk/platform-tools/adb"),
                "test",
                Path("/runtime/avd"),
                5588,
                5043,
                Path("/runtime/releases/test"),
                Path("/runtime/releases/test/sdk"),
            ),
            executor,
            kvm_probe=lambda: (True, "ready", {}),
            sleep=lambda _: None,
        )

        self.assertEqual(backend.wait_adb({}, 1.0), "127.0.0.1:5589")
        self.assertEqual(
            [spec.label for spec in executor.calls],
            ["adb-transport-connect", "adb-transport-connect", "adb-get-state"],
        )

    def test_kvm_android_ready_waits_for_provisioned_wifi_with_an_ip(self):
        executor = ScriptedExecutor(
            {
                "android-boot-completed": (0, "1", ""),
                "android-package-manager": (
                    0,
                    "package:/system/framework/framework-res.apk",
                    "",
                ),
                "kvm-device-provisioned": [(0, "0", ""), (0, "1", "")],
                "kvm-wifi-status": [
                    (0, "Wifi is not connected", ""),
                    (
                        0,
                        'Wifi is connected to "AndroidWifi"\n'
                        "WifiInfo: IP: /10.0.2.16",
                        "",
                    ),
                ],
            }
        )
        backend = KvmBackend(
            KvmRuntimeConfig(
                "127.0.0.1:5589",
                PACKAGE,
                COMPONENT,
                "linux-x86_64-kvm",
                Path("/runtime/releases/test/emulator/emulator"),
                Path("/runtime/releases/test/emulator/emulator-check"),
                Path("/runtime/releases/test/sdk/platform-tools/adb"),
                "test",
                Path("/runtime/avd"),
                5588,
                5043,
                Path("/runtime/releases/test"),
                Path("/runtime/releases/test/sdk"),
            ),
            executor,
            kvm_probe=lambda: (True, "ready", {}),
            sleep=lambda _: None,
        )

        ready = backend.wait_android_ready({}, 1.0)

        self.assertTrue(ready["boot_completed"])
        self.assertTrue(ready["device_provisioned"])
        self.assertTrue(ready["network_ready"])
        self.assertEqual(
            [spec.label for spec in executor.calls],
            [
                "android-boot-completed",
                "android-package-manager",
                "kvm-device-provisioned",
                "kvm-wifi-status",
                "kvm-device-provisioned",
                "kvm-wifi-status",
            ],
        )

    def test_kvm_android_ready_rejects_boot_without_network_provisioning(self):
        executor = ScriptedExecutor(
            {
                "android-boot-completed": (0, "1", ""),
                "android-package-manager": (
                    0,
                    "package:/system/framework/framework-res.apk",
                    "",
                ),
                "kvm-device-provisioned": (0, "1", ""),
                "kvm-wifi-status": (0, "Wifi is not connected", ""),
            }
        )
        backend = KvmBackend(
            KvmRuntimeConfig(
                "127.0.0.1:5589",
                PACKAGE,
                COMPONENT,
                "linux-x86_64-kvm",
                Path("/runtime/releases/test/emulator/emulator"),
                Path("/runtime/releases/test/emulator/emulator-check"),
                Path("/runtime/releases/test/sdk/platform-tools/adb"),
                "test",
                Path("/runtime/avd"),
                5588,
                5043,
                Path("/runtime/releases/test"),
                Path("/runtime/releases/test/sdk"),
            ),
            executor,
            kvm_probe=lambda: (True, "ready", {}),
            sleep=lambda _: None,
        )

        with self.assertRaisesRegex(
            RuntimeBackendNotReady,
            "kvm-network-provisioning-ready-timeout",
        ):
            backend.wait_android_ready({}, 0.0)

    def test_observer_readiness_retries_transient_transport_failure(self):
        executor = ScriptedExecutor()
        backend = ExternalAdbBackend(
            ExternalAdbConfig("device-1", PACKAGE, COMPONENT, "android-arm64-test"),
            executor,
            bridge_factory=FlakyObserverBridge,
            sleep=lambda _: None,
        )
        backend.resolve_artifacts(make_lock("external-adb"))
        instance = backend.start({})
        state = backend.wait_observer_ready(instance, 1.0)
        self.assertTrue(state["atomic"])
        backend.stop(instance)

    def test_observer_readiness_retries_transient_non_ok_state(self):
        executor = ScriptedExecutor()
        backend = ExternalAdbBackend(
            ExternalAdbConfig("device-1", PACKAGE, COMPONENT, "android-arm64-test"),
            executor,
            bridge_factory=StartingObserverBridge,
            sleep=lambda _: None,
        )
        backend.resolve_artifacts(make_lock("external-adb"))
        instance = backend.start({})
        state = backend.wait_observer_ready(instance, 1.0)
        self.assertTrue(state["atomic"])
        backend.stop(instance)

    def test_game_launch_requires_pinned_angle_route_and_unity_command_line(self):
        results = {
            "angle-setting-read-angle-debug-package": (
                0,
                "org.chromium.angle",
                "",
            ),
            "angle-setting-read-angle-gl-driver-selection-pkgs": (
                0,
                PACKAGE,
                "",
            ),
            "angle-setting-read-angle-gl-driver-selection-values": (
                0,
                "angle",
                "",
            ),
            "angle-setting-read-show-angle-in-use-dialog-box": (0, "0", ""),
            "game-force-stop-before-launch": (0, "", ""),
            "game-launch": (0, "Status: ok", ""),
            "game-pid": (0, "1234", ""),
            "game-foreground": (
                0,
                "topResumedActivity=ActivityRecord{x u0 " + COMPONENT + " t1}",
                "",
            ),
        }
        executor = ScriptedExecutor(results)
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                launch_game=True,
                unity_command_line="-force-gfx-st",
            ),
            executor,
            sleep=lambda _: None,
        )
        state = backend.wait_game_ready({"instance_id": "test"}, 1.0)
        self.assertEqual(state["pid"], 1234)
        launch = next(spec for spec in executor.calls if spec.label == "game-launch")
        unity_value = launch.argv[launch.argv.index("unity") + 1]
        self.assertEqual(unity_value, "\\-force-gfx-st")
        self.assertEqual(backend.unity_command_line, "-force-gfx-st")
        self.assertTrue(launch.mutating)

        executor.results["angle-setting-read-angle-gl-driver-selection-values"] = (
            0,
            "native",
            "",
        )
        with self.assertRaisesRegex(RuntimeIdentityMismatch, "angle-routing-mismatch"):
            backend.wait_game_ready({"instance_id": "test"}, 1.0)

    def test_game_recovery_reuses_pinned_unity_command_line(self):
        results = {
            "angle-setting-read-angle-debug-package": (0, "org.chromium.angle", ""),
            "angle-setting-read-angle-gl-driver-selection-pkgs": (0, PACKAGE, ""),
            "angle-setting-read-angle-gl-driver-selection-values": (0, "angle", ""),
            "angle-setting-read-show-angle-in-use-dialog-box": (0, "0", ""),
            "game-force-stop": (0, "", ""),
            "game-relaunch": (0, "Status: ok", ""),
        }
        executor = ScriptedExecutor(results)
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                unity_command_line="-force-gfx-st",
                allow_game_restart=True,
            ),
            executor,
            sleep=lambda _: None,
        )
        self.assertTrue(backend.supports_recovery("game"))
        backend.restart_game({"instance_id": "test"})
        relaunch = next(
            spec for spec in executor.calls if spec.label == "game-relaunch"
        )
        unity_value = relaunch.argv[relaunch.argv.index("unity") + 1]
        self.assertEqual(unity_value, "\\-force-gfx-st")
        self.assertEqual(backend.unity_command_line, "-force-gfx-st")
        self.assertTrue(relaunch.mutating)

    def test_managed_angle_route_is_restored_after_game_launch(self):
        results = {
            "angle-setting-read-angle-debug-package": [
                (0, "null", ""),
                (0, "org.chromium.angle", ""),
                (0, "org.chromium.angle", ""),
                (0, "null", ""),
            ],
            "angle-setting-read-angle-gl-driver-selection-pkgs": [
                (0, "other.package", ""),
                (0, PACKAGE, ""),
                (0, PACKAGE, ""),
                (0, "other.package", ""),
            ],
            "angle-setting-read-angle-gl-driver-selection-values": [
                (0, "native", ""),
                (0, "angle", ""),
                (0, "angle", ""),
                (0, "native", ""),
            ],
            "angle-setting-read-show-angle-in-use-dialog-box": [
                (0, "1", ""),
                (0, "0", ""),
                (0, "0", ""),
                (0, "1", ""),
            ],
            "game-force-stop-before-launch": (0, "", ""),
            "game-launch": (0, "Status: ok", ""),
            "game-pid": (0, "1234", ""),
            "game-foreground": (
                0,
                "topResumedActivity=ActivityRecord{x u0 " + COMPONENT + " t1}",
                "",
            ),
        }
        executor = ScriptedExecutor(results)
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                launch_game=True,
                manage_angle_routing=True,
                unity_command_line="-force-gfx-st",
            ),
            executor,
            sleep=lambda _: None,
        )
        instance = backend.start({})
        backend.wait_game_ready(instance, 1.0)
        backend.stop(instance)
        labels = [spec.label for spec in executor.calls]
        self.assertIn("angle-setting-delete-angle-debug-package", labels)
        restored_packages = [
            spec
            for spec in executor.calls
            if spec.label == "angle-setting-put-angle-gl-driver-selection-pkgs"
        ]
        self.assertEqual(restored_packages[-1].argv[-1], "other.package")

    def test_deferred_backends_are_visible_but_never_available(self):
        backend = DeferredRuntimeBackend(
            BackendKind.REDROID, "redroid-adapter-not-implemented", "linux-redroid"
        )
        self.assertFalse(backend.probe_host().available)
        self.assertFalse(backend.qualification_plan({})["executable"])

    def test_config_factory_is_strict(self):
        executor = ScriptedExecutor()
        value = {
            "schema": "alas-headless.runtime-config/v1",
            "backend": "external-adb",
            "serial": "device-1",
            "package": PACKAGE,
            "component": COMPONENT,
            "host_class": "android-arm64-test",
        }
        self.assertIsInstance(backend_from_config(value, executor), ExternalAdbBackend)
        invalid = dict(value)
        invalid["unknown"] = True
        with self.assertRaises(ValueError):
            backend_from_config(invalid, executor)

        kvm_example = (
            Path(__file__).resolve().parents[1]
            / "integration"
            / "runtime"
            / "history"
            / "kvm.old-build-host.runtime-config.json"
        )
        kvm = backend_from_config(
            json.loads(kvm_example.read_text(encoding="utf-8")),
            executor,
            kvm_probe=lambda: (True, "ready", {}),
        )
        self.assertIsInstance(kvm, KvmBackend)
        self.assertEqual(kvm.serial, "127.0.0.1:5589")
        self.assertEqual(kvm.config.console_port, 5588)
        self.assertEqual(kvm.adb_server_port, 5043)
        self.assertIn("/releases/kvm-r75-x86_64-v2/", kvm.config.emulator.as_posix())
        self.assertIn("/releases/kvm-r75-x86_64-v2/", kvm.config.adb.as_posix())
        self.assertNotIn("android-build/src", kvm.config.emulator.as_posix())
        self.assertNotIn("android-cache/out", kvm.config.emulator.as_posix())


if __name__ == "__main__":
    unittest.main()
