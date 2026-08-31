"""Linux KVM Android Emulator reference backend."""

from __future__ import annotations

import math
import os
import re
import stat
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional, Tuple

from .runtime_backend import BackendKind, RuntimeProbeResult, built_in_backend_profiles
from .runtime_backend_adb import (
    AdbAttachedBackend,
    RuntimeBackendNotReady,
    RuntimeIdentityMismatch,
    _PACKAGE_PATTERN,
    _validate_adb_identity,
    _validate_adb_server_port,
)
from .runtime_command import (
    RuntimeCommandExecutor,
    RuntimeCommandSpec,
    RuntimeOwnedProcess,
)
from .runtime_trace import RuntimeTraceRecorder
from .kvm_runtime_bundle import verify_pinned_runtime_release


@dataclass(frozen=True)
class KvmRuntimeConfig:
    serial: str
    package: str
    component: str
    host_class: str
    emulator: Path
    emulator_check: Path
    adb: Path
    avd_name: str
    avd_home: Path
    console_port: int
    adb_server_port: int
    runtime_release_root: Path
    sdk_root: Optional[Path] = None
    angle_package: str = "org.chromium.angle"
    unity_command_line: Optional[str] = "-force-gfx-st"
    null_refresh_hz: Optional[int] = 30
    cpu_affinity: Optional[str] = None
    numa_node: Optional[int] = None
    launch_game: bool = True
    manage_angle_routing: bool = False
    poll_interval_seconds: float = 1.0

    def __post_init__(self) -> None:
        _validate_adb_identity(self.serial, self.package, self.component)
        if _PACKAGE_PATTERN.fullmatch(self.angle_package) is None:
            raise ValueError("ANGLE package is malformed")
        if self.unity_command_line not in (None, "-force-gfx-st"):
            raise ValueError("Unity command line is not allowlisted")
        if self.null_refresh_hz is not None and (
            isinstance(self.null_refresh_hz, bool)
            or not isinstance(self.null_refresh_hz, int)
            or not 1 <= self.null_refresh_hz <= 240
        ):
            raise ValueError("ANGLE NULL refresh rate must be in [1, 240]")
        if self.cpu_affinity is not None:
            if not isinstance(self.cpu_affinity, str) or re.fullmatch(
                r"[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*",
                self.cpu_affinity,
            ) is None:
                raise ValueError("KVM CPU affinity must be a canonical CPU list")
            for item in self.cpu_affinity.split(","):
                bounds = tuple(int(value) for value in item.split("-"))
                if len(bounds) == 2 and bounds[0] > bounds[1]:
                    raise ValueError("KVM CPU affinity range is reversed")
        if self.numa_node is not None and (
            isinstance(self.numa_node, bool)
            or not isinstance(self.numa_node, int)
            or self.numa_node < 0
        ):
            raise ValueError("KVM NUMA node must be a non-negative integer")
        if (
            not isinstance(self.host_class, str)
            or not self.host_class.strip()
            or not isinstance(self.avd_name, str)
            or not self.avd_name.strip()
        ):
            raise ValueError("KVM host class and AVD name cannot be empty")
        for path in (
            self.emulator,
            self.emulator_check,
            self.adb,
            self.avd_home,
            self.runtime_release_root,
        ):
            if not isinstance(path, Path):
                raise ValueError("KVM runtime paths must be pathlib.Path values")
        if self.sdk_root is not None and not isinstance(self.sdk_root, Path):
            raise ValueError("KVM SDK root must be a pathlib.Path value")
        release = self.runtime_release_root
        if release.parent.name != "releases" or not release.name:
            raise ValueError("KVM runtime release root must be under releases")
        expected_runtime_paths = {
            "emulator": release / "emulator" / "emulator",
            "emulator_check": release / "emulator" / "emulator-check",
            "adb": release / "sdk" / "platform-tools" / "adb",
            "sdk_root": release / "sdk",
        }
        actual_runtime_paths = {
            "emulator": self.emulator,
            "emulator_check": self.emulator_check,
            "adb": self.adb,
            "sdk_root": self.sdk_root,
        }
        if actual_runtime_paths != expected_runtime_paths:
            raise ValueError("KVM runtime tools must belong to one pinned release")
        runtime_root = release.parent.parent
        if self.avd_home != runtime_root / "avd":
            raise ValueError("KVM AVD home must belong to the pinned runtime root")
        if os.name == "posix":
            for candidate in (release, self.avd_home):
                cursor = Path(candidate.anchor)
                for part in candidate.parts[1:]:
                    cursor /= part
                    if cursor.is_symlink():
                        raise ValueError("KVM runtime paths must not contain symlinks")
        if not isinstance(self.launch_game, bool) or not isinstance(
            self.manage_angle_routing, bool
        ):
            raise ValueError("KVM launch switches must be boolean")
        if self.manage_angle_routing and not self.launch_game:
            raise ValueError("managed ANGLE routing requires launch_game")
        if (
            isinstance(self.console_port, bool)
            or not isinstance(self.console_port, int)
            or not 5554 <= self.console_port <= 5680
            or self.console_port % 2
        ):
            raise ValueError("KVM emulator console port must be even and in [5554, 5680]")
        allowed_serials = {
            "emulator-{0}".format(self.console_port),
            "127.0.0.1:{0}".format(self.console_port + 1),
        }
        if self.serial not in allowed_serials:
            raise ValueError("KVM ADB transport must match its emulator console port")
        _validate_adb_server_port(self.adb_server_port)
        if (
            isinstance(self.poll_interval_seconds, bool)
            or not isinstance(self.poll_interval_seconds, (int, float))
            or not math.isfinite(float(self.poll_interval_seconds))
            or self.poll_interval_seconds <= 0
        ):
            raise ValueError("KVM polling interval must be positive")


def probe_linux_kvm() -> Tuple[bool, str, Mapping[str, str]]:
    if os.name != "posix":
        return False, "linux-required", {"platform": os.name}
    path = Path("/dev/kvm")
    try:
        mode = path.stat().st_mode
    except OSError:
        return False, "kvm-device-missing", {"platform": os.name}
    if not stat.S_ISCHR(mode):
        return False, "kvm-device-not-character", {"platform": os.name}
    if not os.access(str(path), os.R_OK | os.W_OK):
        return False, "kvm-device-permission-denied", {"platform": os.name}
    try:
        import fcntl

        descriptor = os.open(str(path), os.O_RDWR | getattr(os, "O_CLOEXEC", 0))
        try:
            api_version = int(fcntl.ioctl(descriptor, 0xAE00, 0))
        finally:
            os.close(descriptor)
    except (ImportError, OSError) as exc:
        return False, "kvm-ioctl-failed", {
            "platform": os.name,
            "exception_type": type(exc).__name__,
        }
    if api_version != 12:
        return False, "kvm-api-version-unexpected", {
            "platform": os.name,
            "kvm_api_version": str(api_version),
        }
    return True, "ready", {
        "platform": os.name,
        "kvm_api_version": str(api_version),
    }


class KvmBackend(AdbAttachedBackend):
    _LOGICAL_DISPLAY_WIDTH = 1280
    _LOGICAL_DISPLAY_HEIGHT = 720
    _LOGICAL_DISPLAY_DENSITY = 240

    def __init__(
        self,
        config: KvmRuntimeConfig,
        executor: RuntimeCommandExecutor,
        trace: Optional[RuntimeTraceRecorder] = None,
        kvm_probe: Callable[[], Tuple[bool, str, Mapping[str, str]]] = probe_linux_kvm,
        release_verifier: Callable[[Path], Path] = verify_pinned_runtime_release,
        **kwargs: Any
    ) -> None:
        self.config = config
        self.kvm_probe = kvm_probe
        self.release_verifier = release_verifier
        self._owned_processes: Dict[str, RuntimeOwnedProcess] = {}
        super().__init__(
            built_in_backend_profiles()[BackendKind.KVM],
            config.serial,
            config.package,
            config.component,
            config.host_class,
            str(config.adb),
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

    @property
    def avd_config_path(self) -> Path:
        return self.config.avd_home / (self.config.avd_name + ".avd") / "config.ini"

    def _require_release_avd(self) -> Path:
        release = self.release_verifier(self.config.runtime_release_root)
        try:
            lines = self.avd_config_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RuntimeBackendNotReady("kvm-avd-config-missing") from exc
        values = [
            line.split("=", 1)[1]
            for line in lines
            if line.startswith("image.sysdir.1=")
        ]
        if len(values) != 1:
            raise RuntimeBackendNotReady("kvm-avd-image-sysdir-invalid")
        actual = Path(values[0].rstrip("/\\")).resolve(strict=False)
        expected = (release / "images").resolve(strict=False)
        if actual != expected:
            raise RuntimeBackendNotReady("kvm-avd-image-sysdir-outside-release")
        return release

    def probe_host(self) -> RuntimeProbeResult:
        available, reason, fingerprint = self.kvm_probe()
        required = (
            self.config.emulator,
            self.config.emulator_check,
            self.config.adb,
            self.avd_config_path,
        )
        missing = [str(path) for path in required if not Path(path).is_file()]
        if missing:
            available = False
            reason = "kvm-runtime-path-missing"
        if available:
            try:
                self._require_release_avd()
            except Exception:
                available = False
                reason = "kvm-runtime-release-invalid"
        if available:
            acceleration = self.executor.run(
                RuntimeCommandSpec(
                    "emulator-acceleration-check",
                    (str(self.config.emulator_check), "accel"),
                    timeout_seconds=30.0,
                )
            )
            if not acceleration.succeeded:
                available = False
                reason = "emulator-acceleration-check-failed"
        host_fingerprint = dict(fingerprint)
        host_fingerprint["host_class"] = self.host_class
        if missing:
            host_fingerprint["missing_path_count"] = str(len(missing))
        return RuntimeProbeResult(available, BackendKind.KVM, reason, host_fingerprint)

    def provision(self, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
        provisioned = super().provision(artifacts)
        release = self._require_release_avd()
        provisioned.update(
            {
                "avd_name": self.config.avd_name,
                "avd_config": str(self.avd_config_path.resolve()),
                "runtime_release_root": str(release.resolve()),
            }
        )
        return provisioned

    def wait_adb(self, instance: Mapping[str, Any], timeout_seconds: float) -> str:
        """Reconnect the TCP transport through the dedicated ADB server."""

        def ready() -> Optional[Mapping[str, Any]]:
            connect = self.executor.run(
                RuntimeCommandSpec(
                    "adb-transport-connect",
                    (
                        str(self.config.adb),
                        "-P",
                        str(self.config.adb_server_port),
                        "connect",
                        self.serial,
                    ),
                    timeout_seconds=5.0,
                    mutating=True,
                )
            )
            if not connect.succeeded:
                return None
            state = self._adb("adb-get-state", ("get-state",), timeout_seconds=5.0)
            if state.succeeded and state.stdout.strip() == "device":
                return {"serial": self.serial}
            return None

        self._wait_for(timeout_seconds, ready, "adb-ready-timeout")
        return self.serial

    def wait_android_ready(
        self, instance: Mapping[str, Any], timeout_seconds: float
    ) -> Mapping[str, Any]:
        """Wait for Goldfish provisioning, not only the early boot property."""

        framework = super().wait_android_ready(instance, timeout_seconds)

        def ready() -> Optional[Mapping[str, Any]]:
            provisioned = self._adb(
                "kvm-device-provisioned",
                ("shell", "settings", "get", "global", "device_provisioned"),
                timeout_seconds=5.0,
            )
            wifi = self._adb(
                "kvm-wifi-status",
                ("shell", "cmd", "wifi", "status"),
                timeout_seconds=5.0,
            )
            if (
                provisioned.succeeded
                and provisioned.stdout.strip() == "1"
                and wifi.succeeded
                and "Wifi is connected" in wifi.stdout
                and "IP: /" in wifi.stdout
            ):
                return {
                    **framework,
                    "device_provisioned": True,
                    "network_ready": True,
                }
            return None

        return self._wait_for(
            timeout_seconds,
            ready,
            "kvm-network-provisioning-ready-timeout",
        )

    def start(self, provisioned: Mapping[str, Any]) -> Mapping[str, Any]:
        devices = self.executor.run(
            RuntimeCommandSpec(
                "adb-device-inventory",
                (
                    str(self.config.adb),
                    "-P",
                    str(self.config.adb_server_port),
                    "devices",
                ),
                timeout_seconds=10.0,
            )
        )
        if not devices.succeeded:
            raise RuntimeBackendNotReady("adb-device-inventory-failed")
        for line in devices.stdout.splitlines()[1:]:
            columns = line.split()
            if columns and columns[0] == self.serial:
                raise RuntimeBackendNotReady("emulator-serial-already-in-use")
        environment = {
            "ANDROID_AVD_HOME": str(self.config.avd_home.resolve()),
            "ADB_SERVER_PORT": str(self.config.adb_server_port),
            "ANDROID_ADB_SERVER_PORT": str(self.config.adb_server_port),
        }
        if self.config.sdk_root is not None:
            environment["ANDROID_SDK_ROOT"] = str(self.config.sdk_root.resolve())
        platform_tools = (
            self.config.runtime_release_root / "sdk" / "platform-tools"
        ).resolve()
        inherited_path = os.environ.get("PATH", "")
        environment["PATH"] = str(platform_tools) + (
            os.pathsep + inherited_path if inherited_path else ""
        )
        arguments = (
            str(self.config.emulator),
            "-avd",
            self.config.avd_name,
            "-port",
            str(self.config.console_port),
            "-no-window",
            "-no-audio",
            "-no-boot-anim",
            "-no-snapshot-load",
            "-no-snapshot-save",
            "-gpu",
            "swiftshader_indirect",
            "-accel",
            "on",
            "-camera-back",
            "none",
            "-camera-front",
            "none",
            "-no-metrics",
        )
        if self.config.numa_node is not None:
            numa_prefix = (
                sys.executable,
                "-m",
                "alas_headless.numa_exec",
                "--node",
                str(self.config.numa_node),
            )
            checked = self.executor.run(
                RuntimeCommandSpec(
                    "kvm-emulator-numa-memory-policy-check",
                    numa_prefix + ("--check",),
                    timeout_seconds=10.0,
                    mutating=True,
                    environment=environment,
                )
            )
            self._require_success(
                checked,
                "kvm-emulator-numa-memory-policy-unavailable",
            )
            arguments = numa_prefix + ("--",) + arguments
        instance_id = uuid.uuid4().hex
        process = self.executor.start(
            RuntimeCommandSpec(
                "kvm-emulator-start",
                arguments,
                timeout_seconds=30.0,
                mutating=True,
                environment=environment,
            ),
            handle_id=instance_id,
        )
        if self.config.cpu_affinity is not None:
            try:
                affinity = self.executor.run(
                    RuntimeCommandSpec(
                        "kvm-emulator-cpu-affinity",
                        (
                            "taskset",
                            "--all-tasks",
                            "--pid",
                            "--cpu-list",
                            self.config.cpu_affinity,
                            str(process.pid),
                        ),
                        timeout_seconds=10.0,
                        mutating=True,
                    )
                )
                self._require_success(
                    affinity,
                    "kvm-emulator-cpu-affinity-failed",
                )
            except Exception:
                self.executor.stop_owned(process, timeout_seconds=30.0)
                raise
        self._owned_processes[instance_id] = process
        return {
            "instance_id": instance_id,
            "serial": self.serial,
            "owned": True,
            "pid": process.pid,
        }

    def _configure_null_refresh_rate(self) -> None:
        rate = self.config.null_refresh_hz
        if rate is None:
            return
        configured = self._adb(
            "angle-null-refresh-rate-set",
            (
                "shell",
                "setprop",
                "debug.angle.null_refresh_hz",
                str(rate),
            ),
            mutating=True,
        )
        self._require_success(configured, "angle-null-refresh-rate-set-failed")
        observed = self._adb(
            "angle-null-refresh-rate-readback",
            ("shell", "getprop", "debug.angle.null_refresh_hz"),
        )
        if not observed.succeeded or observed.stdout.strip() != str(rate):
            raise RuntimeIdentityMismatch("angle-null-refresh-rate-mismatch")

    def _prewarm_angle_apk(self) -> None:
        path_result = self._adb(
            "angle-apk-prewarm-path",
            ("shell", "pm", "path", self.config.angle_package),
        )
        path_output = self._require_success(
            path_result,
            "angle-apk-prewarm-package-unavailable",
        )
        paths = [
            line[len("package:") :]
            for line in path_output.splitlines()
            if line.startswith("package:")
        ]
        if (
            len(paths) != 1
            or re.fullmatch(r"/[A-Za-z0-9._/+=:@~-]+", paths[0]) is None
        ):
            raise RuntimeIdentityMismatch("angle-apk-prewarm-path-mismatch")
        prewarmed = self._adb(
            "angle-apk-prewarm-read",
            (
                "shell",
                "dd",
                "if={0}".format(paths[0]),
                "of=/dev/null",
                "bs=1048576",
            ),
            timeout_seconds=30.0,
        )
        self._require_success(prewarmed, "angle-apk-prewarm-read-failed")

    @staticmethod
    def _effective_display_value(
        output: str,
        label: str,
        value_pattern: str,
    ) -> Tuple[int, ...]:
        physical = re.search(
            r"^Physical " + re.escape(label) + r": " + value_pattern + r"\r?$",
            output,
            re.MULTILINE,
        )
        override = re.search(
            r"^Override " + re.escape(label) + r": " + value_pattern + r"\r?$",
            output,
            re.MULTILINE,
        )
        selected = override or physical
        if selected is None:
            raise RuntimeIdentityMismatch("logical-display-readback-malformed")
        return tuple(int(value) for value in selected.groups())

    def _configure_logical_display(self) -> None:
        logical_size = "{0}x{1}".format(
            self._LOGICAL_DISPLAY_WIDTH,
            self._LOGICAL_DISPLAY_HEIGHT,
        )
        size_set = self._adb(
            "kvm-logical-display-size-set",
            ("shell", "wm", "size", logical_size),
            mutating=True,
        )
        self._require_success(size_set, "logical-display-size-set-failed")
        density_set = self._adb(
            "kvm-logical-display-density-set",
            (
                "shell",
                "wm",
                "density",
                str(self._LOGICAL_DISPLAY_DENSITY),
            ),
            mutating=True,
        )
        self._require_success(density_set, "logical-display-density-set-failed")
        size_readback = self._adb(
            "kvm-logical-display-size-readback",
            ("shell", "wm", "size"),
        )
        density_readback = self._adb(
            "kvm-logical-display-density-readback",
            ("shell", "wm", "density"),
        )
        self._require_success(size_readback, "logical-display-size-readback-failed")
        self._require_success(
            density_readback,
            "logical-display-density-readback-failed",
        )
        effective_size = self._effective_display_value(
            size_readback.stdout,
            "size",
            r"([0-9]+)x([0-9]+)",
        )
        effective_density = self._effective_display_value(
            density_readback.stdout,
            "density",
            r"([0-9]+)",
        )
        if effective_size != (
            self._LOGICAL_DISPLAY_WIDTH,
            self._LOGICAL_DISPLAY_HEIGHT,
        ) or effective_density != (self._LOGICAL_DISPLAY_DENSITY,):
            raise RuntimeIdentityMismatch("logical-display-mismatch")

    def _prepare_game_cold_launch(self, instance: Mapping[str, Any]) -> None:
        # The emulator framebuffer is deliberately smaller, while Unity and
        # ALAS retain their qualified 1280x720 semantic coordinate surface.
        self._configure_logical_display()
        # SurfaceNULL reads this property when the game's EGL surface is
        # created, so every cold launch and recovery restart must set it first.
        self._configure_null_refresh_rate()
        # The old KVM host repeatedly exposed a first-process race while
        # competing EGL initialization paths loaded the APK ANGLE driver from
        # cold storage. Reading the exact selected APK here closes that measured
        # window without changing renderer selection or introducing a pixel
        # fallback.
        self._prewarm_angle_apk()

    def stop(self, instance: Mapping[str, Any]) -> None:
        cleanup_failure: Optional[Exception] = None
        try:
            self._restore_angle_routing(instance)
        except Exception as exc:
            cleanup_failure = exc
        try:
            self._close_observer(instance)
        except Exception as exc:
            if cleanup_failure is None:
                cleanup_failure = exc
        instance_id = str(instance.get("instance_id", ""))
        process = self._owned_processes.pop(instance_id, None)
        if process is not None:
            try:
                self._adb(
                    "emulator-stop",
                    ("emu", "kill"),
                    timeout_seconds=15.0,
                    mutating=True,
                )
            except Exception as exc:
                if cleanup_failure is None:
                    cleanup_failure = exc
            try:
                self.executor.stop_owned(process, timeout_seconds=30.0)
            except Exception as exc:
                if cleanup_failure is None:
                    cleanup_failure = exc
        if cleanup_failure is not None:
            raise cleanup_failure

    def restart_game(self, instance: Mapping[str, Any]) -> None:
        self._close_observer(instance)
        self._launch_game_process(
            instance,
            60.0,
            "game-force-stop",
            "game-relaunch",
        )

    def restart_android(self, instance: Mapping[str, Any]) -> None:
        self._close_observer(instance)
        result = self._adb("android-reboot", ("reboot",), mutating=True)
        self._require_success(result, "android-reboot-failed")

    def supports_recovery(self, recovery: str) -> bool:
        return recovery in ("game", "android")

    def qualification_plan(
        self, runtime_lock: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        plan = dict(super().qualification_plan(runtime_lock))
        plan["state_changes"] = [
            "start-owned-emulator",
            "launch-game" if self.launch_game else "observe-existing-game",
            "create-adb-forward",
            "stop-owned-emulator",
        ]
        plan["compatibility_start_profile"] = {
            "gpu": "swiftshader_indirect",
            "acceleration": "kvm",
            "snapshots": "load-save-disabled-for-qualification",
            "experimental_tuning": False,
            "guest_ram_mib": 3072,
            "cpu_affinity": self.config.cpu_affinity or "host-default",
            "numa_memory_node": (
                self.config.numa_node
                if self.config.numa_node is not None
                else "host-default"
            ),
            "null_refresh_hz": self.config.null_refresh_hz,
            "physical_display": "960x540@180",
            "logical_display": "1280x720@240",
        }
        plan["game_launch_profile"] = {
            "force_stop_before_launch": self.launch_game,
            "unity_command_line": self.unity_command_line,
            "null_refresh_hz": self.config.null_refresh_hz,
            "angle_apk_prewarm": "required-before-every-game-launch",
            "angle_routing": (
                "managed-ephemeral" if self.manage_angle_routing else "verify-only"
            ),
        }
        plan["state_changes"].insert(1, "set-canonical-logical-display")
        if self.config.null_refresh_hz is not None:
            plan["state_changes"].insert(2, "set-angle-null-refresh-rate")
        if self.manage_angle_routing:
            plan["state_changes"].insert(3, "temporarily-set-and-restore-angle-routing")
        return plan
