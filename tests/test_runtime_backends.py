import json
import os
import itertools
import sys
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
from alas_headless.runtime_backend_redroid import (
    RedroidBackend as RedroidBackendImplementation,
)
from alas_headless.runtime_backends import (
    DeferredRuntimeBackend,
    ExternalAdbBackend,
    ExternalAdbConfig,
    KvmBackend,
    KvmRuntimeConfig,
    RedroidBackend,
    RedroidRuntimeConfig,
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
                    "main_thread": True,
                    "flags": 15,
                    "ui_stage": 100,
                    "ui_method_mask": 15,
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


class IncompleteObserverBridge(FakeBridge):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_count = 0

    def request(self, request):
        self.request_count += 1
        value = super().request(request)
        if self.request_count == 1:
            value["snapshot"]["ui_method_mask"] = 7
        return value


class RuntimeBackendsTests(unittest.TestCase):
    def test_managed_launch_config_requires_the_headless_unity_extra(self):
        with self.assertRaisesRegex(ValueError, "requires Unity -force-gfx-st"):
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                launch_game=True,
                unity_command_line=None,
            )
        with self.assertRaisesRegex(ValueError, "requires Unity -force-gfx-st"):
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                allow_game_restart=True,
                unity_command_line=None,
            )
        with self.assertRaisesRegex(ValueError, "requires Unity -force-gfx-st"):
            self.redroid_config(unity_command_line=None)

    def test_compatibility_facade_reexports_split_implementations(self):
        self.assertIs(ExternalAdbBackend, ExternalAdbBackendImplementation)
        self.assertIs(KvmBackend, KvmBackendImplementation)
        self.assertIs(DeferredRuntimeBackend, DeferredRuntimeBackendImplementation)
        self.assertIs(RedroidBackend, RedroidBackendImplementation)

    @staticmethod
    def redroid_config(**overrides):
        value = {
            "serial": "172.31.250.11:5555",
            "package": PACKAGE,
            "component": COMPONENT,
            "host_class": "linux-x86_64-redroid",
            "container_id": "alas-redroid-build1-x86-storage1",
            "image_reference": "docker.io/alasheadless/redroid-x86-64:latest",
            "image_manifest_digest": "sha256:" + HASH,
            "userdata_path": "/srv/android-runtime/redroid/alas-headless/build1-x86/data",
            "start_script": "/home/weipa/.local/bin/alas-redroid-start",
            "stop_script": "/home/weipa/.local/bin/alas-redroid-stop",
            "adb_server_port": 5044,
            "launch_game": False,
            "poll_interval_seconds": 0.01,
        }
        value.update(overrides)
        return RedroidRuntimeConfig(**value)

    @staticmethod
    def redroid_provision_results(tasks=None):
        container_info = {
            "ID": "alas-redroid-build1-x86-storage1",
            "Image": "docker.io/alasheadless/redroid-x86-64:latest",
            "Labels": {
                "io.github.alas-headless.abi": "x86_64",
                "io.github.alas-headless.build-fingerprint": "test/android/build",
                "io.github.alas-headless.game-delivery": "external-install",
                "io.github.alas-headless.storage-layout": "host-directory-v1",
            },
            "Spec": {
                "linux": {
                    "namespaces": [
                        {"type": "pid"},
                        {"type": "ipc"},
                        {"type": "uts"},
                        {"type": "mount"},
                        {"type": "network"},
                    ],
                    "devices": [
                        {
                            "path": "/dev/binder",
                            "type": "c",
                            "major": 10,
                            "minor": 63,
                        }
                    ]
                },
                "mounts": [
                    {
                        "destination": "/data",
                        "source": "/srv/android-runtime/redroid/alas-headless/build1-x86/data",
                        "type": "bind",
                        "options": ["rbind", "rw"],
                    }
                ],
            },
        }
        return {
            "containerd-version": (0, "Client:\n  Version: 1.7.24", ""),
            "redroid-host-architecture": (0, "x86_64", ""),
            "redroid-images-list": (
                0,
                "REF TYPE DIGEST SIZE PLATFORMS LABELS\n"
                "docker.io/alasheadless/redroid-x86-64:latest manifest "
                "sha256:" + HASH + " 1.6GiB linux/amd64 -",
                "",
            ),
            "redroid-container-info": (0, json.dumps(container_info), ""),
            "redroid-start-script-probe": (0, "", ""),
            "redroid-stop-script-probe": (0, "", ""),
            "redroid-userdata-path-probe": (0, "", ""),
            "redroid-tasks-list": tasks or [
                (0, "TASK PID STATUS", ""),
                (0, "TASK PID STATUS\nalas-redroid-build1-x86-storage1 123 RUNNING", ""),
                (0, "TASK PID STATUS\nalas-redroid-build1-x86-storage1 123 RUNNING", ""),
                (0, "TASK PID STATUS", ""),
            ],
            "redroid-container-start": (0, "started", ""),
            "redroid-cleanup-kill": (0, "", ""),
            "redroid-cleanup-delete": (0, "", ""),
            "redroid-cleanup-host-stop": (0, "", ""),
        }

    def test_redroid_backend_starts_only_verified_preprovisioned_container(self):
        executor = ScriptedExecutor(self.redroid_provision_results())
        backend = RedroidBackend(self.redroid_config(), executor, sleep=lambda _: None)
        self.assertTrue(backend.probe_host().available)
        artifacts = backend.resolve_artifacts(make_lock("redroid"))
        provisioned = backend.provision(artifacts)
        instance = backend.start(provisioned)
        self.assertTrue(instance["owned"])
        backend.stop(instance)
        labels = [spec.label for spec in executor.calls]
        self.assertIn("redroid-container-start", labels)
        self.assertIn("redroid-cleanup-kill", labels)
        self.assertIn("redroid-cleanup-delete", labels)
        self.assertIn("redroid-cleanup-host-stop", labels)
        host_stop = next(
            spec for spec in executor.calls if spec.label == "redroid-cleanup-host-stop"
        )
        self.assertEqual(host_stop.argv, ("/home/weipa/.local/bin/alas-redroid-stop",))
        self.assertTrue(host_stop.mutating)
        contract = backend.qualification_plan(make_lock("redroid"))[
            "container_contract"
        ]
        self.assertTrue(contract["preprovisioned_container_required"])
        self.assertTrue(contract["start_script_starts_task"])
        self.assertTrue(contract["stop_script_cleans_host_runtime"])

    def test_redroid_backend_allows_task_only_lifecycle_without_stop_script(self):
        results = self.redroid_provision_results()
        executor = ScriptedExecutor(results)
        backend = RedroidBackend(
            self.redroid_config(stop_script=None), executor, sleep=lambda _: None
        )
        artifacts = backend.resolve_artifacts(make_lock("redroid"))
        instance = backend.start(backend.provision(artifacts))
        backend.stop(instance)
        labels = [spec.label for spec in executor.calls]
        self.assertNotIn("redroid-stop-script-probe", labels)
        self.assertNotIn("redroid-cleanup-host-stop", labels)

    def test_redroid_headless_system_ui_disable_is_opt_in_and_idempotent(self):
        base_results = {
            "android-boot-completed": (0, "1", ""),
            "android-package-manager": (
                0,
                "package:/system/framework/framework-res.apk",
                "",
            ),
        }
        default_executor = ScriptedExecutor(dict(base_results))
        default_backend = RedroidBackend(
            self.redroid_config(), default_executor, sleep=lambda _: None
        )
        state = default_backend.wait_android_ready({}, 1.0)
        self.assertNotIn("system_ui_disabled", state)
        self.assertNotIn(
            "redroid-system-ui-disabled",
            [spec.label for spec in default_executor.calls],
        )

        results = dict(base_results)
        results["redroid-system-ui-disabled"] = (
            0,
            "package:com.android.systemui",
            "",
        )
        executor = ScriptedExecutor(results)
        backend = RedroidBackend(
            self.redroid_config(disable_system_ui_for_headless=True),
            executor,
            sleep=lambda _: None,
        )
        self.assertTrue(backend.wait_android_ready({}, 1.0)["system_ui_disabled"])
        labels = [spec.label for spec in executor.calls]
        self.assertNotIn("redroid-system-ui-disable", labels)
        plan = backend.qualification_plan(make_lock("redroid"))
        self.assertIn(
            "disable-systemui-for-headless-runtime-if-enabled",
            plan["state_changes"],
        )

    def test_redroid_headless_system_ui_disable_is_verified(self):
        results = {
            "android-boot-completed": (0, "1", ""),
            "android-package-manager": (
                0,
                "package:/system/framework/framework-res.apk",
                "",
            ),
            "redroid-system-ui-disabled": [
                (0, "", ""),
                (0, "package:com.android.systemui", ""),
            ],
            "redroid-system-ui-disable": (
                0,
                "Package com.android.systemui new state: disabled-user",
                "",
            ),
        }
        executor = ScriptedExecutor(results)
        backend = RedroidBackend(
            self.redroid_config(disable_system_ui_for_headless=True),
            executor,
            sleep=lambda _: None,
        )
        self.assertTrue(backend.wait_android_ready({}, 1.0)["system_ui_disabled"])
        mutation = next(
            spec for spec in executor.calls if spec.label == "redroid-system-ui-disable"
        )
        self.assertTrue(mutation.mutating)
        self.assertEqual(
            mutation.argv[-6:],
            (
                "shell",
                "pm",
                "disable-user",
                "--user",
                "0",
                "com.android.systemui",
            ),
        )

        results["redroid-system-ui-disabled"] = [
            (0, "", ""),
            (0, "", ""),
        ]
        failing = RedroidBackend(
            self.redroid_config(disable_system_ui_for_headless=True),
            ScriptedExecutor(results),
            sleep=lambda _: None,
        )
        with self.assertRaisesRegex(
            RuntimeBackendNotReady, "redroid-system-ui-disable-unconfirmed"
        ):
            failing.wait_android_ready({}, 1.0)

    def test_redroid_backend_escalates_only_after_term_timeout(self):
        running = "TASK PID STATUS\nalas-redroid-build1-x86-storage1 123 RUNNING"
        results = self.redroid_provision_results(
            tasks=[
                (0, "TASK PID STATUS", ""),
                (0, running, ""),
                (0, running, ""),
                (0, running, ""),
                (0, "TASK PID STATUS", ""),
            ]
        )
        results["redroid-cleanup-kill-force"] = (0, "", "")
        clock = itertools.count(0.0, 31.0)
        executor = ScriptedExecutor(results)
        backend = RedroidBackend(
            self.redroid_config(),
            executor,
            sleep=lambda _: None,
            monotonic=lambda: next(clock),
        )
        artifacts = backend.resolve_artifacts(make_lock("redroid"))
        instance = backend.start(backend.provision(artifacts))
        backend.stop(instance)
        forced = next(
            spec for spec in executor.calls if spec.label == "redroid-cleanup-kill-force"
        )
        self.assertEqual(forced.argv[-2:], ("SIGKILL", self.redroid_config().container_id))
        self.assertTrue(forced.mutating)

    def test_redroid_backend_rejects_public_adb_and_image_drift(self):
        with self.assertRaisesRegex(ValueError, "loopback or RFC1918-private"):
            self.redroid_config(serial="8.8.8.8:5555")

        results = self.redroid_provision_results()
        results["redroid-images-list"] = (
            0,
            "REF TYPE DIGEST SIZE PLATFORMS LABELS\n"
            "docker.io/alasheadless/redroid-x86-64:latest manifest "
            "sha256:" + "b" * 64 + " 1.6GiB linux/amd64 -",
            "",
        )
        backend = RedroidBackend(
            self.redroid_config(), ScriptedExecutor(results), sleep=lambda _: None
        )
        backend.resolve_artifacts(make_lock("redroid"))
        with self.assertRaisesRegex(
            RuntimeIdentityMismatch, "redroid-image-manifest-digest-mismatch"
        ):
            backend.provision({})

        results = self.redroid_provision_results()
        results["redroid-host-architecture"] = (0, "aarch64", "")
        backend = RedroidBackend(
            self.redroid_config(), ScriptedExecutor(results), sleep=lambda _: None
        )
        artifacts = backend.resolve_artifacts(make_lock("redroid"))
        with self.assertRaisesRegex(
            RuntimeIdentityMismatch, "redroid-host-architecture-mismatch"
        ):
            backend.provision(artifacts)

    def test_redroid_backend_rejects_wrong_userdata_mount_and_legacy_devices(self):
        results = self.redroid_provision_results()
        info = json.loads(results["redroid-container-info"][1])
        info["Spec"]["mounts"][0]["source"] = "/srv/android-runtime/redroid/wrong-data"
        results["redroid-container-info"] = (0, json.dumps(info), "")
        backend = RedroidBackend(
            self.redroid_config(), ScriptedExecutor(results), sleep=lambda _: None
        )
        artifacts = backend.resolve_artifacts(make_lock("redroid"))
        with self.assertRaisesRegex(
            RuntimeIdentityMismatch, "redroid-userdata-mount-contract-mismatch"
        ):
            backend.provision(artifacts)

        results = self.redroid_provision_results()
        info = json.loads(results["redroid-container-info"][1])
        info["Spec"]["linux"]["devices"].append(
            {"path": "/dev/dm-0", "type": "b", "major": 252, "minor": 0}
        )
        results["redroid-container-info"] = (0, json.dumps(info), "")
        backend = RedroidBackend(
            self.redroid_config(), ScriptedExecutor(results), sleep=lambda _: None
        )
        artifacts = backend.resolve_artifacts(make_lock("redroid"))
        with self.assertRaisesRegex(
            RuntimeIdentityMismatch, "redroid-legacy-storage-device-present"
        ):
            backend.provision(artifacts)

    def test_redroid_backend_requires_private_network_namespace(self):
        for network_namespace in (None, {"type": "network", "path": "/proc/1/ns/net"}):
            results = self.redroid_provision_results()
            info = json.loads(results["redroid-container-info"][1])
            namespaces = info["Spec"]["linux"]["namespaces"]
            info["Spec"]["linux"]["namespaces"] = [
                item for item in namespaces if item.get("type") != "network"
            ]
            if network_namespace is not None:
                info["Spec"]["linux"]["namespaces"].append(network_namespace)
            results["redroid-container-info"] = (0, json.dumps(info), "")
            backend = RedroidBackend(
                self.redroid_config(), ScriptedExecutor(results), sleep=lambda _: None
            )
            artifacts = backend.resolve_artifacts(make_lock("redroid"))
            with self.assertRaisesRegex(
                RuntimeIdentityMismatch, "redroid-container-host-network-namespace"
            ):
                backend.provision(artifacts)

    def test_redroid_backend_android_restart_exposes_offline_boundary(self):
        running = "TASK PID STATUS\nalas-redroid-build1-x86-storage1 123 RUNNING"
        results = self.redroid_provision_results(tasks=[
            (0, running, ""),
            (0, running, ""),
            (0, running, ""),
            (0, "TASK PID STATUS", ""),
            (0, running, ""),
        ])
        results.update(
            {
                "redroid-restart-kill": (0, "", ""),
                "redroid-restart-delete": (0, "", ""),
                "redroid-restart-host-stop": (0, "", ""),
                "adb-restart-boundary": (1, "", "device offline"),
                "redroid-restart-start": (0, "started", ""),
            }
        )
        executor = ScriptedExecutor(results)
        backend = RedroidBackend(self.redroid_config(), executor, sleep=lambda _: None)
        artifacts = backend.resolve_artifacts(make_lock("redroid"))
        instance = backend.start(backend.provision(artifacts))
        self.assertFalse(instance["owned"])
        backend.restart_android(instance)
        self.assertTrue(backend.wait_android_offline(instance, 1.0)["adb_offline_observed"])
        backend.stop(instance)
        labels = [spec.label for spec in executor.calls]
        self.assertIn("redroid-restart-kill", labels)
        self.assertIn("redroid-restart-delete", labels)
        self.assertIn("redroid-restart-host-stop", labels)
        self.assertIn("redroid-restart-start", labels)

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

    def test_adb_commands_are_bound_to_the_configured_server(self):
        executor = ScriptedExecutor()
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                adb="owned-adb",
                adb_server_port=5044,
            ),
            executor,
        )
        self.assertEqual(
            backend._adb_spec("adb-get-state", ("get-state",)).argv,
            (
                "owned-adb",
                "-P",
                "5044",
                "-s",
                "device-1",
                "get-state",
            ),
        )
        with self.assertRaisesRegex(ValueError, "ADB server port"):
            ExternalAdbConfig(
                "device-1",
                PACKAGE,
                COMPONENT,
                "android-arm64-test",
                adb_server_port=0,
            )

    def test_tcp_adb_transport_connects_on_its_private_server_before_ready(self):
        executor = ScriptedExecutor(
            {
                "adb-connect": (0, "connected to 127.0.0.1:5589", ""),
                "adb-get-state": (0, "device", ""),
            }
        )
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "127.0.0.1:5589",
                PACKAGE,
                COMPONENT,
                "linux-x86_64-kvm",
                adb="owned-adb",
                adb_server_port=5043,
                connect_transport=True,
            ),
            executor,
            sleep=lambda _: None,
        )
        self.assertEqual(backend.wait_adb(backend.start({}), 1.0), "127.0.0.1:5589")
        connect = next(spec for spec in executor.calls if spec.label == "adb-connect")
        self.assertEqual(
            connect.argv,
            ("owned-adb", "-P", "5043", "connect", "127.0.0.1:5589"),
        )
        self.assertTrue(connect.mutating)

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
            self.assertEqual(plan["compatibility_start_profile"]["null_refresh_hz"], 30)
            self.assertIn("set-angle-null-refresh-rate", plan["state_changes"])
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
                    cpu_affinity="26-51",
                    numa_node=1,
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
            self.assertEqual(
                started.argv[:7],
                (
                    sys.executable,
                    "-m",
                    "alas_headless.numa_exec",
                    "--node",
                    "1",
                    "--",
                    str(release / "emulator" / "emulator"),
                ),
            )
            numa_check = next(
                spec
                for spec in backend.executor.calls
                if spec.label == "kvm-emulator-numa-memory-policy-check"
            )
            self.assertEqual(
                numa_check.argv,
                (
                    sys.executable,
                    "-m",
                    "alas_headless.numa_exec",
                    "--node",
                    "1",
                    "--check",
                ),
            )
            self.assertTrue(numa_check.mutating)
            affinity = next(
                spec
                for spec in backend.executor.calls
                if spec.label == "kvm-emulator-cpu-affinity"
            )
            self.assertEqual(
                affinity.argv,
                (
                    "taskset",
                    "--all-tasks",
                    "--pid",
                    "--cpu-list",
                    "26-51",
                    "4321",
                ),
            )
            self.assertTrue(affinity.mutating)

            backend.executor.results["kvm-emulator-numa-memory-policy-check"] = (
                1,
                "",
                "set_mempolicy failed",
            )
            unavailable = KvmBackend(
                backend.config,
                backend.executor,
                kvm_probe=lambda: (True, "ready", {}),
            )
            started_count = len(unavailable.executor.started)
            with self.assertRaisesRegex(
                RuntimeBackendNotReady,
                "kvm-emulator-numa-memory-policy-unavailable",
            ):
                unavailable.start({})
            self.assertEqual(len(unavailable.executor.started), started_count)

            backend.executor.results["kvm-emulator-numa-memory-policy-check"] = (
                0,
                "",
                "",
            )
            backend.executor.results["kvm-emulator-cpu-affinity"] = (
                1,
                "",
                "invalid affinity",
            )
            failed = KvmBackend(
                backend.config,
                backend.executor,
                kvm_probe=lambda: (True, "ready", {}),
            )
            with self.assertRaisesRegex(
                RuntimeBackendNotReady,
                "kvm-emulator-cpu-affinity-failed",
            ):
                failed.start({})
            self.assertEqual(failed.executor.stopped[-1].pid, 4321)

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

    def test_kvm_prepares_display_refresh_and_angle_apk_before_every_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = root / "releases" / "test"
            results = {
                "kvm-logical-display-size-set": (0, "", ""),
                "kvm-logical-display-density-set": (0, "", ""),
                "kvm-logical-display-size-readback": (
                    0,
                    "Physical size: 960x540\r\nOverride size: 1280x720\r\n",
                    "",
                ),
                "kvm-logical-display-density-readback": (
                    0,
                    "Physical density: 180\r\nOverride density: 240\r\n",
                    "",
                ),
                "angle-null-refresh-rate-set": (0, "", ""),
                "angle-null-refresh-rate-readback": (0, "30\n", ""),
                "angle-apk-prewarm-path": (
                    0,
                    "package:/data/app/org.chromium.angle/base.apk\n",
                    "",
                ),
                "angle-apk-prewarm-read": (0, "", "14+0 records in\n"),
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
            backend = KvmBackend(
                KvmRuntimeConfig(
                    serial="127.0.0.1:5589",
                    package=PACKAGE,
                    component=COMPONENT,
                    host_class="linux-x86_64-kvm",
                    emulator=release / "emulator" / "emulator",
                    emulator_check=release / "emulator" / "emulator-check",
                    adb=release / "sdk" / "platform-tools" / "adb",
                    avd_name="test",
                    avd_home=root / "avd",
                    console_port=5588,
                    adb_server_port=5043,
                    runtime_release_root=release,
                    sdk_root=release / "sdk",
                ),
                executor,
                kvm_probe=lambda: (True, "ready", {}),
                release_verifier=lambda path: path,
                sleep=lambda _: None,
            )

            state = backend.wait_game_ready({"instance_id": "test"}, 1.0)
            self.assertEqual(state["pid"], 1234)
            labels = [spec.label for spec in executor.calls]
            self.assertLess(
                labels.index("game-force-stop-before-launch"),
                labels.index("kvm-logical-display-size-set"),
            )
            self.assertLess(
                labels.index("kvm-logical-display-density-set"),
                labels.index("angle-null-refresh-rate-set"),
            )
            confirmation = next(
                spec for spec in executor.calls
                if spec.label == "kvm-immersive-tutorial-confirm"
            )
            self.assertEqual(confirmation.argv[-6:], (
                "shell", "settings", "put", "secure",
                "immersive_mode_confirmations", "confirmed",
            ))
            self.assertTrue(confirmation.mutating)
            self.assertLess(labels.index(confirmation.label), labels.index("game-launch"))
            self.assertLess(
                labels.index("angle-null-refresh-rate-set"),
                labels.index("angle-apk-prewarm-path"),
            )
            self.assertLess(
                labels.index("angle-apk-prewarm-read"),
                labels.index("game-launch"),
            )
            size_set = next(
                spec
                for spec in executor.calls
                if spec.label == "kvm-logical-display-size-set"
            )
            self.assertEqual(size_set.argv[-4:], ("shell", "wm", "size", "1280x720"))
            self.assertTrue(size_set.mutating)
            configured = next(
                spec
                for spec in executor.calls
                if spec.label == "angle-null-refresh-rate-set"
            )
            self.assertEqual(
                configured.argv[-4:],
                ("shell", "setprop", "debug.angle.null_refresh_hz", "30"),
            )
            self.assertTrue(configured.mutating)
            prewarm = next(
                spec
                for spec in executor.calls
                if spec.label == "angle-apk-prewarm-read"
            )
            self.assertEqual(
                prewarm.argv[-5:],
                (
                    "shell",
                    "dd",
                    "if=/data/app/org.chromium.angle/base.apk",
                    "of=/dev/null",
                    "bs=1048576",
                ),
            )
            self.assertFalse(prewarm.mutating)
            self.assertEqual(
                backend.qualification_plan(make_lock("kvm"))["compatibility_start_profile"],
                {
                    "gpu": "swiftshader_indirect",
                    "acceleration": "kvm",
                    "snapshots": "load-save-disabled-for-qualification",
                    "experimental_tuning": False,
                    "guest_ram_mib": 3072,
                    "cpu_affinity": "host-default",
                    "numa_memory_node": "host-default",
                    "null_refresh_hz": 30,
                    "physical_display": "960x540@180",
                    "logical_display": "1280x720@240",
                },
            )
            self.assertEqual(
                backend.qualification_plan(make_lock("kvm"))["game_launch_profile"][
                    "null_refresh_hz"
                ],
                30,
            )
            self.assertEqual(
                backend.qualification_plan(make_lock("kvm"))["game_launch_profile"][
                    "angle_apk_prewarm"
                ],
                "required-before-every-game-launch",
            )

            previous_launches = sum(spec.label == "game-relaunch" for spec in executor.calls)
            executor.results["kvm-immersive-tutorial-confirm"] = (1, "", "permission denied")
            with self.assertRaisesRegex(RuntimeBackendNotReady, "immersive-tutorial-confirm-failed"):
                backend.restart_game({"instance_id": "test"})
            self.assertEqual(
                sum(spec.label == "game-relaunch" for spec in executor.calls), previous_launches,
            )
            executor.results["kvm-immersive-tutorial-confirm"] = (0, "", "")
            executor.results["angle-null-refresh-rate-readback"] = (0, "60\n", "")
            with self.assertRaisesRegex(
                RuntimeIdentityMismatch,
                "angle-null-refresh-rate-mismatch",
            ):
                backend.restart_game({"instance_id": "test"})

            executor.results["angle-null-refresh-rate-readback"] = (0, "30\n", "")
            executor.results["angle-apk-prewarm-path"] = (0, "", "")
            with self.assertRaisesRegex(
                RuntimeIdentityMismatch,
                "angle-apk-prewarm-path-mismatch",
            ):
                backend.restart_game({"instance_id": "test"})

            executor.results["angle-apk-prewarm-path"] = (
                0,
                "package:/data/app/org.chromium.angle/base.apk\n",
                "",
            )
            executor.results["angle-apk-prewarm-read"] = (1, "", "read error")
            with self.assertRaisesRegex(
                RuntimeBackendNotReady,
                "angle-apk-prewarm-read-failed",
            ):
                backend.restart_game({"instance_id": "test"})

            executor.results["angle-null-refresh-rate-readback"] = (0, "30\n", "")
            executor.results["angle-apk-prewarm-read"] = (0, "", "")
            executor.results["kvm-logical-display-size-readback"] = (
                0,
                "Physical size: 1280x720\n",
                "",
            )
            executor.results["kvm-logical-display-density-readback"] = (
                0,
                "Physical density: 240\n",
                "",
            )
            backend.restart_game({"instance_id": "test"})

            executor.results["kvm-logical-display-size-readback"] = (
                0,
                "Physical size: 960x540\n",
                "",
            )
            executor.results["kvm-logical-display-density-readback"] = (
                0,
                "Physical density: 180\n",
                "",
            )
            with self.assertRaisesRegex(
                RuntimeIdentityMismatch,
                "logical-display-mismatch",
            ):
                backend.restart_game({"instance_id": "test"})

    def test_kvm_null_refresh_rate_matches_angle_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            release = Path(directory) / "releases" / "test"
            common = {
                "serial": "127.0.0.1:5589",
                "package": PACKAGE,
                "component": COMPONENT,
                "host_class": "linux-x86_64-kvm",
                "emulator": release / "emulator" / "emulator",
                "emulator_check": release / "emulator" / "emulator-check",
                "adb": release / "sdk" / "platform-tools" / "adb",
                "avd_name": "test",
                "avd_home": release.parent.parent / "avd",
                "console_port": 5588,
                "adb_server_port": 5043,
                "runtime_release_root": release,
                "sdk_root": release / "sdk",
            }
            self.assertEqual(KvmRuntimeConfig(**common).null_refresh_hz, 30)
            self.assertIsNone(KvmRuntimeConfig(**common).cpu_affinity)
            self.assertIsNone(KvmRuntimeConfig(**common).numa_node)
            self.assertEqual(
                KvmRuntimeConfig(**common, cpu_affinity="26-51").cpu_affinity,
                "26-51",
            )
            self.assertEqual(KvmRuntimeConfig(**common, numa_node=1).numa_node, 1)
            self.assertIsNone(
                KvmRuntimeConfig(**common, null_refresh_hz=None).null_refresh_hz
            )
            for invalid in (True, 0, 241, 30.0):
                with self.subTest(invalid=invalid), self.assertRaisesRegex(
                    ValueError,
                    "ANGLE NULL refresh rate",
                ):
                    KvmRuntimeConfig(**common, null_refresh_hz=invalid)
            for invalid in (True, "", "51-26", "1,,2", "all"):
                with self.subTest(cpu_affinity=invalid), self.assertRaisesRegex(
                    ValueError,
                    "KVM CPU affinity",
                ):
                    KvmRuntimeConfig(**common, cpu_affinity=invalid)
            for invalid in (True, -1, "1", 1.0):
                with self.subTest(numa_node=invalid), self.assertRaisesRegex(
                    ValueError,
                    "KVM NUMA node",
                ):
                    KvmRuntimeConfig(**common, numa_node=invalid)

    @unittest.skipUnless(os.name == "posix", "POSIX path contract")
    def test_kvm_runtime_accepts_isolated_non_srv_root(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime_root = Path(directory) / "runtime-kvm"
            release = runtime_root / "releases" / "test"
            config = KvmRuntimeConfig(
                serial="127.0.0.1:5589",
                package=PACKAGE,
                component=COMPONENT,
                host_class="linux-x86_64-kvm",
                emulator=release / "emulator" / "emulator",
                emulator_check=release / "emulator" / "emulator-check",
                adb=release / "sdk" / "platform-tools" / "adb",
                avd_name="test",
                avd_home=runtime_root / "avd",
                console_port=5588,
                adb_server_port=5043,
                runtime_release_root=release,
                sdk_root=release / "sdk",
            )

            self.assertEqual(config.runtime_release_root, release)

    @unittest.skipUnless(os.name == "posix", "POSIX symlink contract")
    def test_kvm_runtime_rejects_symlinked_runtime_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real_runtime_root = root / "real-runtime-kvm"
            linked_runtime_root = root / "linked-runtime-kvm"
            real_runtime_root.mkdir()
            linked_runtime_root.symlink_to(real_runtime_root, target_is_directory=True)
            release = linked_runtime_root / "releases" / "test"

            with self.assertRaisesRegex(ValueError, "must not contain symlinks"):
                KvmRuntimeConfig(
                    serial="127.0.0.1:5589",
                    package=PACKAGE,
                    component=COMPONENT,
                    host_class="linux-x86_64-kvm",
                    emulator=release / "emulator" / "emulator",
                    emulator_check=release / "emulator" / "emulator-check",
                    adb=release / "sdk" / "platform-tools" / "adb",
                    avd_name="test",
                    avd_home=linked_runtime_root / "avd",
                    console_port=5588,
                    adb_server_port=5043,
                    runtime_release_root=release,
                    sdk_root=release / "sdk",
                )

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

    def test_observer_readiness_waits_for_complete_main_thread_ui_probe(self):
        executor = ScriptedExecutor()
        backend = ExternalAdbBackend(
            ExternalAdbConfig(
                "device-1", PACKAGE, COMPONENT, "android-arm64-test"
            ),
            executor,
            bridge_factory=IncompleteObserverBridge,
            sleep=lambda _: None,
        )
        backend.resolve_artifacts(make_lock("external-adb"))
        instance = backend.start({})

        state = backend.wait_observer_ready(instance, 1.0)

        self.assertTrue(state["atomic"])
        self.assertEqual(
            backend._bridges[instance["instance_id"]].request_count,
            2,
        )
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
            BackendKind.TCG, "tcg-adapter-not-implemented", "linux-tcg"
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
            "adb_server_port": 5044,
        }
        external_backend = backend_from_config(value, executor)
        self.assertIsInstance(external_backend, ExternalAdbBackend)
        self.assertEqual(external_backend.adb_server_port, 5044)
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
        self.assertEqual(kvm.config.null_refresh_hz, 30)
        self.assertIn("/releases/kvm-r75-x86_64-v2/", kvm.config.emulator.as_posix())
        self.assertIn("/releases/kvm-r75-x86_64-v2/", kvm.config.adb.as_posix())
        self.assertNotIn("android-build/src", kvm.config.emulator.as_posix())
        self.assertNotIn("android-cache/out", kvm.config.emulator.as_posix())

        redroid_value = {
            "schema": "alas-headless.runtime-config/v1",
            "backend": "redroid",
            "serial": "172.31.250.11:5555",
            "package": PACKAGE,
            "component": COMPONENT,
            "host_class": "linux-x86_64-redroid",
            "container_id": "alas-redroid-build1-x86-storage1",
            "image_reference": "docker.io/alasheadless/redroid-x86-64:latest",
            "image_manifest_digest": "sha256:" + HASH,
            "userdata_path": "/srv/android-runtime/redroid/alas-headless/build1-x86/data",
            "start_script": "/home/weipa/.local/bin/alas-redroid-start",
            "adb_server_port": 5045,
        }
        redroid_backend = backend_from_config(redroid_value, executor)
        self.assertIsInstance(redroid_backend, RedroidBackend)
        self.assertEqual(redroid_backend.adb_server_port, 5045)
        invalid_redroid = dict(redroid_value)
        invalid_redroid["unknown"] = True
        with self.assertRaises(ValueError):
            backend_from_config(invalid_redroid, executor)

        current_example = (
            Path(__file__).resolve().parents[1]
            / "integration"
            / "runtime"
            / "kvm.config.example.json"
        )
        current = backend_from_config(
            json.loads(current_example.read_text(encoding="utf-8")),
            executor,
            kvm_probe=lambda: (True, "ready", {}),
        )
        self.assertIsInstance(current, KvmBackend)
        self.assertEqual(current.config.null_refresh_hz, 30)
        self.assertIsNone(current.config.cpu_affinity)
        self.assertIsNone(current.config.numa_node)


if __name__ == "__main__":
    unittest.main()
