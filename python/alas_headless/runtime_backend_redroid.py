"""Lifecycle backend for a pre-provisioned containerd Redroid instance."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import math
import re
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

from .runtime_backend import BackendKind, RuntimeProbeResult, built_in_backend_profiles
from .runtime_backend_adb import (
    AdbAttachedBackend,
    RuntimeBackendNotReady,
    RuntimeIdentityMismatch,
    _PACKAGE_PATTERN,
    _validate_adb_identity,
    _validate_adb_server_port,
)
from .runtime_command import RuntimeCommandExecutor, RuntimeCommandResult, RuntimeCommandSpec
from .runtime_trace import RuntimeTraceRecorder


_CONTAINER_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_NAMESPACE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_IMAGE_REFERENCE_PATTERN = re.compile(r"^[A-Za-z0-9._:/-]+:[A-Za-z0-9_.-]+$")
_MANIFEST_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_POSIX_ABSOLUTE_PATH_PATTERN = re.compile(r"^/(?:[^\x00\r\n/]+/?)*$")
_SERIAL_IP_PATTERN = re.compile(r"^([^:]+):([1-9][0-9]{0,4})$")
_LOOP_RECORD_PATTERN = re.compile(r"^/dev/loop([0-9]+):")


def _normalized_architecture(value: str) -> Optional[str]:
    candidate = value.strip().lower()
    if candidate in ("amd64", "x86_64"):
        return "x86_64"
    if candidate in ("arm64", "aarch64"):
        return "arm64-v8a"
    return None


def _validate_private_adb_serial(serial: str) -> None:
    match = _SERIAL_IP_PATTERN.fullmatch(serial)
    if match is None:
        raise ValueError("Redroid ADB serial must use an explicit IP address and port")
    try:
        address = ipaddress.ip_address(match.group(1))
    except ValueError as exc:
        raise ValueError("Redroid ADB serial must use an explicit IP address") from exc
    private_networks = (
        ipaddress.ip_network("10.0.0.0/8"),
        ipaddress.ip_network("172.16.0.0/12"),
        ipaddress.ip_network("192.168.0.0/16"),
        ipaddress.ip_network("127.0.0.0/8"),
    )
    if address.version != 4 or not any(address in network for network in private_networks):
        raise ValueError("Redroid ADB serial must be loopback or RFC1918-private")


def _validate_narrow_path(name: str, value: str) -> None:
    if (
        not isinstance(value, str)
        or _POSIX_ABSOLUTE_PATH_PATTERN.fullmatch(value) is None
        or value == "/"
        or ".." in value.split("/")
    ):
        raise ValueError("Redroid {0} must be a narrow absolute path".format(name))


@dataclass(frozen=True)
class RedroidRuntimeConfig:
    serial: str
    package: str
    component: str
    host_class: str
    container_id: str
    image_reference: str
    image_manifest_digest: str
    userdata_image: str
    metadata_image: str
    start_script: str
    stop_script: Optional[str] = None
    ctr: str = "ctr"
    sudo: str = "sudo"
    namespace: str = "alas-headless"
    adb: str = "adb"
    adb_server_port: int = 5037
    angle_package: str = "org.chromium.angle"
    unity_command_line: Optional[str] = "-force-gfx-st"
    launch_game: bool = True
    manage_angle_routing: bool = False
    allow_game_restart: bool = True
    allow_android_restart: bool = True
    stop_container_on_cleanup: bool = True
    poll_interval_seconds: float = 1.0
    storage_layout: str = "srv-v1"

    def __post_init__(self) -> None:
        _validate_adb_identity(self.serial, self.package, self.component)
        _validate_private_adb_serial(self.serial)
        if _PACKAGE_PATTERN.fullmatch(self.angle_package) is None:
            raise ValueError("ANGLE package is malformed")
        if not isinstance(self.host_class, str) or not self.host_class.strip():
            raise ValueError("Redroid host class cannot be empty")
        if _CONTAINER_NAME_PATTERN.fullmatch(self.container_id) is None:
            raise ValueError("Redroid container ID is malformed")
        if _NAMESPACE_PATTERN.fullmatch(self.namespace) is None:
            raise ValueError("containerd namespace is malformed")
        if _IMAGE_REFERENCE_PATTERN.fullmatch(self.image_reference) is None:
            raise ValueError("Redroid image reference is malformed")
        if _MANIFEST_DIGEST_PATTERN.fullmatch(self.image_manifest_digest) is None:
            raise ValueError("Redroid image manifest digest is malformed")
        for name, value in (
            ("userdata_image", self.userdata_image),
            ("metadata_image", self.metadata_image),
            ("start_script", self.start_script),
        ):
            _validate_narrow_path(name, value)
        if self.stop_script is not None:
            _validate_narrow_path("stop_script", self.stop_script)
        if self.userdata_image == self.metadata_image:
            raise ValueError("Redroid userdata and metadata images must be distinct")
        if self.unity_command_line not in (None, "-force-gfx-st"):
            raise ValueError("Unity command line is not allowlisted")
        for name, value in (("ctr", self.ctr), ("sudo", self.sudo), ("adb", self.adb)):
            if not isinstance(value, str) or not value:
                raise ValueError("Redroid executable cannot be empty: {0}".format(name))
        _validate_adb_server_port(self.adb_server_port)
        for value in (
            self.launch_game,
            self.manage_angle_routing,
            self.allow_game_restart,
            self.allow_android_restart,
            self.stop_container_on_cleanup,
        ):
            if not isinstance(value, bool):
                raise ValueError("Redroid feature switches must be booleans")
        if self.manage_angle_routing and not self.launch_game:
            raise ValueError("managed ANGLE routing requires launch_game")
        if (
            isinstance(self.poll_interval_seconds, bool)
            or not isinstance(self.poll_interval_seconds, (int, float))
            or not math.isfinite(float(self.poll_interval_seconds))
            or self.poll_interval_seconds <= 0
        ):
            raise ValueError("Redroid polling interval must be positive")
        if self.storage_layout != "srv-v1":
            raise ValueError("Redroid storage layout is unsupported")


class RedroidBackend(AdbAttachedBackend):
    """Control one retained containerd container without constructing images."""

    def __init__(
        self,
        config: RedroidRuntimeConfig,
        executor: RuntimeCommandExecutor,
        trace: Optional[RuntimeTraceRecorder] = None,
        **kwargs: Any
    ) -> None:
        self.config = config
        self._pending_android_restart: Dict[str, bool] = {}
        super().__init__(
            built_in_backend_profiles()[BackendKind.REDROID],
            config.serial,
            config.package,
            config.component,
            config.host_class,
            config.adb,
            config.adb_server_port,
            True,
            config.angle_package,
            config.unity_command_line,
            config.manage_angle_routing,
            executor,
            config.launch_game,
            config.poll_interval_seconds,
            trace=trace,
            **kwargs
        )

    def _command(
        self,
        label: str,
        argv: Sequence[str],
        timeout_seconds: float = 30.0,
        mutating: bool = False,
    ) -> RuntimeCommandResult:
        return self.executor.run(
            RuntimeCommandSpec(
                label,
                tuple(argv),
                timeout_seconds=timeout_seconds,
                mutating=mutating,
            )
        )

    def _ctr(
        self,
        label: str,
        *arguments: str,
        timeout_seconds: float = 30.0,
        mutating: bool = False,
    ) -> RuntimeCommandResult:
        return self._command(
            label,
            (self.config.sudo, "-n", self.config.ctr, "-n", self.config.namespace)
            + arguments,
            timeout_seconds,
            mutating,
        )

    @staticmethod
    def _require_success(result: RuntimeCommandResult, failure_code: str) -> str:
        if not result.succeeded:
            raise RuntimeBackendNotReady(failure_code)
        return result.stdout.strip()

    def _image_digest(self) -> str:
        output = self._require_success(
            self._ctr("redroid-images-list", "images", "list"),
            "redroid-image-list-failed",
        )
        matches = []
        for line in output.splitlines():
            fields = line.split()
            if fields and fields[0] == self.config.image_reference:
                matches.extend(
                    field for field in fields[1:] if _MANIFEST_DIGEST_PATTERN.fullmatch(field)
                )
        if len(matches) != 1:
            raise RuntimeIdentityMismatch("redroid-image-target-missing")
        return matches[0]

    def _container_info(self) -> Mapping[str, Any]:
        output = self._require_success(
            self._ctr(
                "redroid-container-info",
                "containers",
                "info",
                self.config.container_id,
            ),
            "redroid-container-inspect-failed",
        )
        try:
            value = json.loads(output)
        except json.JSONDecodeError as exc:
            raise RuntimeIdentityMismatch("redroid-container-inspect-malformed") from exc
        if not isinstance(value, dict):
            raise RuntimeIdentityMismatch("redroid-container-inspect-malformed")
        return value

    def _task_running(self) -> bool:
        output = self._require_success(
            self._ctr("redroid-tasks-list", "tasks", "list"),
            "redroid-task-list-failed",
        )
        records = [line.split() for line in output.splitlines()]
        matches = [record for record in records if record and record[0] == self.config.container_id]
        if len(matches) > 1:
            raise RuntimeIdentityMismatch("redroid-task-state-ambiguous")
        return bool(matches and "RUNNING" in matches[0][1:])

    def _validate_image_and_container(self) -> Mapping[str, Any]:
        if self._image_digest() != self.config.image_manifest_digest:
            raise RuntimeIdentityMismatch("redroid-image-manifest-digest-mismatch")
        info = self._container_info()
        if info.get("ID") != self.config.container_id:
            raise RuntimeIdentityMismatch("redroid-container-id-mismatch")
        if info.get("Image") != self.config.image_reference:
            raise RuntimeIdentityMismatch("redroid-container-image-mismatch")
        labels = info.get("Labels")
        if not isinstance(labels, dict):
            raise RuntimeIdentityMismatch("redroid-container-labels-missing")
        if self._runtime_lock is None:
            raise RuntimeBackendNotReady("runtime-lock-not-resolved")
        document = self._runtime_lock.document
        expected_labels = {
            "io.github.alas-headless.abi": document["android"]["abi"],
            "io.github.alas-headless.build-fingerprint": document["android"]["build_fingerprint"],
            "io.github.alas-headless.game-delivery": "external-install",
            "io.github.alas-headless.storage-layout": self.config.storage_layout,
        }
        if any(labels.get(name) != value for name, value in expected_labels.items()):
            raise RuntimeIdentityMismatch("redroid-container-label-mismatch")
        spec = info.get("Spec")
        linux = spec.get("linux") if isinstance(spec, dict) else None
        devices = linux.get("devices") if isinstance(linux, dict) else None
        if not isinstance(devices, list) or any(
            not isinstance(item, dict) for item in devices
        ):
            raise RuntimeIdentityMismatch("redroid-container-devices-malformed")
        device_paths = {
            item.get("path") for item in devices
        }
        if not {"/dev/block/alas_userdata", "/dev/block/alas_metadata"}.issubset(device_paths):
            raise RuntimeIdentityMismatch("redroid-storage-device-contract-mismatch")
        if any(
            item.get("type") == "b"
            and isinstance(path, str)
            and (re.fullmatch(r"/dev/dm-[0-9]+", path) or path.startswith("/dev/mapper/"))
            for item in devices
            for path in (item.get("path"),)
        ):
            raise RuntimeIdentityMismatch("redroid-container-frozen-dm-device")
        namespaces = linux.get("namespaces")
        if not isinstance(namespaces, list) or any(
            not isinstance(item, dict) for item in namespaces
        ):
            raise RuntimeIdentityMismatch("redroid-container-namespaces-malformed")
        network_namespaces = [
            item for item in namespaces if item.get("type") == "network"
        ]
        if len(network_namespaces) != 1 or network_namespaces[0].get("path") not in (
            None,
            "",
        ):
            raise RuntimeIdentityMismatch("redroid-container-host-network-namespace")
        return info

    def _validate_loop_image(self, label: str, path: str) -> Tuple[int, int]:
        output = self._require_success(
            self._command(
                label,
                (self.config.sudo, "-n", "losetup", "-j", path),
            ),
            "redroid-loop-image-probe-failed",
        )
        records = [line for line in output.splitlines() if line.strip()]
        if len(records) != 1 or ("(" + path + ")") not in records[0]:
            raise RuntimeIdentityMismatch("redroid-loop-image-mismatch")
        match = _LOOP_RECORD_PATTERN.match(records[0])
        if match is None:
            raise RuntimeIdentityMismatch("redroid-loop-device-malformed")
        return 7, int(match.group(1))

    @staticmethod
    def _validate_storage_device_identity(
        info: Mapping[str, Any],
        userdata_device: Tuple[int, int],
        metadata_device: Tuple[int, int],
    ) -> None:
        if userdata_device == metadata_device:
            raise RuntimeIdentityMismatch("redroid-storage-loop-alias")
        devices = info["Spec"]["linux"]["devices"]
        expected = {
            "/dev/block/alas_userdata": userdata_device,
            "/dev/block/alas_metadata": metadata_device,
        }
        for path, identity in expected.items():
            matches = [item for item in devices if item.get("path") == path]
            observed = {
                (item.get("type"), item.get("major"), item.get("minor"))
                for item in matches
            }
            if observed != {("b", identity[0], identity[1])}:
                raise RuntimeIdentityMismatch(
                    "redroid-storage-device-identity-mismatch"
                )

    def _validate_container_and_storage(self) -> None:
        info = self._validate_image_and_container()
        userdata_device = self._validate_loop_image(
            "redroid-userdata-loop", self.config.userdata_image
        )
        metadata_device = self._validate_loop_image(
            "redroid-metadata-loop", self.config.metadata_image
        )
        self._validate_storage_device_identity(
            info, userdata_device, metadata_device
        )

    def _host_architecture(self) -> Optional[str]:
        result = self._command("redroid-host-architecture", ("uname", "-m"))
        return _normalized_architecture(result.stdout) if result.succeeded else None

    def probe_host(self) -> RuntimeProbeResult:
        version = self._ctr("containerd-version", "version")
        normalized = self._host_architecture()
        available = version.succeeded and "Client:" in version.stdout and normalized is not None
        return RuntimeProbeResult(
            available,
            BackendKind.REDROID,
            "ready" if available else "containerd-host-unavailable",
            {
                "host_class": self.host_class,
                "host_architecture": normalized or "unknown",
                "container_sha256": hashlib.sha256(
                    self.config.container_id.encode("utf-8")
                ).hexdigest(),
                "image_manifest_digest": self.config.image_manifest_digest,
            },
        )

    def resolve_artifacts(self, runtime_lock: Mapping[str, Any]) -> Mapping[str, Any]:
        artifacts = dict(super().resolve_artifacts(runtime_lock))
        artifacts.update(
            {
                "container_id": self.config.container_id,
                "image_reference": self.config.image_reference,
                "image_manifest_digest": self.config.image_manifest_digest,
            }
        )
        return artifacts

    def provision(self, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
        provisioned = dict(super().provision(artifacts))
        if self._runtime_lock is None:
            raise RuntimeBackendNotReady("runtime-lock-not-resolved")
        if self._host_architecture() != self._runtime_lock.document["android"]["abi"]:
            raise RuntimeIdentityMismatch("redroid-host-architecture-mismatch")
        self._require_success(
            self._command(
                "redroid-start-script-probe", ("test", "-x", self.config.start_script)
            ),
            "redroid-start-script-unavailable",
        )
        if self.config.stop_script is not None:
            self._require_success(
                self._command(
                    "redroid-stop-script-probe", ("test", "-x", self.config.stop_script)
                ),
                "redroid-stop-script-unavailable",
            )
        self._validate_container_and_storage()
        provisioned["initially_running"] = self._task_running()
        return provisioned

    def _start_runtime(self, label: str) -> None:
        self._require_success(
            self._command(
                label,
                (self.config.start_script,),
                timeout_seconds=180.0,
                mutating=True,
            ),
            "redroid-container-start-failed",
        )
        self._validate_container_and_storage()
        if not self._task_running():
            raise RuntimeBackendNotReady("redroid-task-not-running")

    def start(self, provisioned: Mapping[str, Any]) -> Mapping[str, Any]:
        if provisioned.get("image_manifest_digest") != self.config.image_manifest_digest:
            raise RuntimeIdentityMismatch("redroid-provisioned-image-mismatch")
        initially_running = provisioned.get("initially_running")
        if not isinstance(initially_running, bool):
            raise RuntimeBackendNotReady("redroid-provisioning-state-missing")
        owned = False
        if not initially_running:
            self._start_runtime("redroid-container-start")
            owned = True
        elif not self._task_running():
            raise RuntimeBackendNotReady("redroid-task-not-running")
        return {
            "instance_id": uuid.uuid4().hex,
            "serial": self.serial,
            "container_id": self.config.container_id,
            "image_manifest_digest": self.config.image_manifest_digest,
            "initially_running": initially_running,
            "owned": owned,
        }

    def fingerprint(self, instance: Mapping[str, Any]) -> Mapping[str, Any]:
        if not self._task_running():
            raise RuntimeBackendNotReady("redroid-task-not-running")
        self._validate_container_and_storage()
        return super().fingerprint(instance)

    def restart_game(self, instance: Mapping[str, Any]) -> None:
        if not self.config.allow_game_restart:
            return super().restart_game(instance)
        self._close_observer(instance)
        self._launch_game_process(instance, 60.0, "game-force-stop", "game-relaunch")

    def _stop_task(self, label_prefix: str) -> None:
        if not self._task_running():
            return
        self._require_success(
            self._ctr(
                label_prefix + "-kill",
                "tasks",
                "kill",
                "--signal",
                "SIGTERM",
                self.config.container_id,
                mutating=True,
            ),
            "redroid-task-stop-failed",
        )

        def stopped() -> Optional[Mapping[str, Any]]:
            return {"stopped": True} if not self._task_running() else None

        try:
            self._wait_for(30.0, stopped, "redroid-task-stop-timeout")
        except RuntimeBackendNotReady as exc:
            if exc.code != "redroid-task-stop-timeout":
                raise
            self._require_success(
                self._ctr(
                    label_prefix + "-kill-force",
                    "tasks",
                    "kill",
                    "--signal",
                    "SIGKILL",
                    self.config.container_id,
                    mutating=True,
                ),
                "redroid-task-force-stop-failed",
            )
            self._wait_for(
                30.0, stopped, "redroid-task-force-stop-timeout"
            )
        self._require_success(
            self._ctr(
                label_prefix + "-delete",
                "tasks",
                "delete",
                self.config.container_id,
                mutating=True,
            ),
            "redroid-task-delete-failed",
        )

    def restart_android(self, instance: Mapping[str, Any]) -> None:
        if not self.config.allow_android_restart:
            return super().restart_android(instance)
        instance_id = str(instance.get("instance_id", ""))
        if not instance_id or self._pending_android_restart.get(instance_id):
            raise RuntimeBackendNotReady("redroid-restart-state-invalid")
        self._close_observer(instance)
        self._stop_task("redroid-restart")
        self._stop_host_runtime("redroid-restart-host-stop")
        self._pending_android_restart[instance_id] = True

    def _stop_host_runtime(self, label: str) -> None:
        if self.config.stop_script is None:
            return
        self._require_success(
            self._command(
                label,
                (self.config.stop_script,),
                timeout_seconds=180.0,
                mutating=True,
            ),
            "redroid-host-runtime-stop-failed",
        )

    def wait_android_offline(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        instance_id = str(instance.get("instance_id", ""))
        if not self._pending_android_restart.get(instance_id):
            raise RuntimeBackendNotReady("redroid-restart-state-invalid")
        state = super().wait_android_offline(instance, timeout_seconds)
        self._start_runtime("redroid-restart-start")
        del self._pending_android_restart[instance_id]
        return state

    def supports_recovery(self, recovery: str) -> bool:
        return (
            recovery == "game" and self.config.allow_game_restart
        ) or (
            recovery == "android" and self.config.allow_android_restart
        )

    def stop(self, instance: Mapping[str, Any]) -> None:
        cleanup_failure: Optional[Exception] = None
        instance_id = str(instance.get("instance_id", ""))
        pending_restart = self._pending_android_restart.pop(instance_id, False)
        try:
            super().stop(instance)
        except Exception as exc:
            cleanup_failure = exc
        try:
            if pending_restart and instance.get("initially_running") is True:
                self._start_runtime("redroid-cleanup-start")
            elif (
                instance.get("owned") is True
                and self.config.stop_container_on_cleanup
                and not pending_restart
            ):
                self._stop_task("redroid-cleanup")
                self._stop_host_runtime("redroid-cleanup-host-stop")
        except Exception as exc:
            if cleanup_failure is None:
                cleanup_failure = exc
        if cleanup_failure is not None:
            raise cleanup_failure

    def qualification_plan(
        self, runtime_lock: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        plan = dict(super().qualification_plan(runtime_lock))
        plan.update(
            {
                "container_sha256": hashlib.sha256(
                    self.config.container_id.encode("utf-8")
                ).hexdigest(),
                "image_manifest_digest": self.config.image_manifest_digest,
                "state_changes": [
                    "start-retained-containerd-instance-if-stopped",
                    "stop-only-backend-started-task",
                ]
                + list(plan["state_changes"]),
                "container_contract": {
                    "manifest_digest_verified": True,
                    "persistent_block_userdata": True,
                    "adb_private_only": True,
                    "preprovisioned_container_required": True,
                    "start_script_starts_task": True,
                    "stop_script_cleans_host_runtime": (
                        self.config.stop_script is not None
                    ),
                },
            }
        )
        return plan


__all__ = ["RedroidBackend", "RedroidRuntimeConfig"]
