"""Apple Silicon macOS Android Emulator / Hypervisor.Framework backend."""

from __future__ import annotations

import math
import os
import platform
import re
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
from .runtime_command import RuntimeCommandExecutor, RuntimeCommandSpec, RuntimeOwnedProcess
from .runtime_trace import RuntimeTraceRecorder


@dataclass(frozen=True)
class MacosHvfRuntimeConfig:
    serial: str
    package: str
    component: str
    host_class: str
    emulator: Path
    adb: Path
    sdk_root: Path
    avd_name: str
    avd_home: Path
    console_port: int
    adb_server_port: int = 5037
    angle_package: str = "org.chromium.angle"
    unity_command_line: str = "-force-gfx-st"
    null_refresh_hz: Optional[int] = 30
    launch_game: bool = True
    manage_angle_routing: bool = False
    poll_interval_seconds: float = 1.0

    def __post_init__(self) -> None:
        _validate_adb_identity(self.serial, self.package, self.component)
        _validate_adb_server_port(self.adb_server_port)
        if _PACKAGE_PATTERN.fullmatch(self.angle_package) is None:
            raise ValueError("ANGLE package is malformed")
        if self.unity_command_line != "-force-gfx-st":
            raise ValueError("macOS HVF game launch requires Unity -force-gfx-st")
        if not isinstance(self.host_class, str) or not self.host_class.strip():
            raise ValueError("macOS HVF host class cannot be empty")
        if not isinstance(self.avd_name, str) or not self.avd_name.strip():
            raise ValueError("macOS HVF AVD name cannot be empty")
        if not isinstance(self.launch_game, bool) or not isinstance(
            self.manage_angle_routing, bool
        ):
            raise ValueError("macOS HVF launch switches must be boolean")
        if self.manage_angle_routing and not self.launch_game:
            raise ValueError("managed ANGLE routing requires launch_game")
        if self.null_refresh_hz is not None and (
            isinstance(self.null_refresh_hz, bool)
            or not isinstance(self.null_refresh_hz, int)
            or not 1 <= self.null_refresh_hz <= 240
        ):
            raise ValueError("ANGLE NULL refresh rate must be in [1, 240]")
        if (
            isinstance(self.poll_interval_seconds, bool)
            or not isinstance(self.poll_interval_seconds, (int, float))
            or not math.isfinite(float(self.poll_interval_seconds))
            or self.poll_interval_seconds <= 0
        ):
            raise ValueError("macOS HVF polling interval must be positive")
        if (
            isinstance(self.console_port, bool)
            or not isinstance(self.console_port, int)
            or not 5554 <= self.console_port <= 5680
            or self.console_port % 2
        ):
            raise ValueError("macOS HVF console port must be even and in [5554, 5680]")
        if self.serial != "emulator-{0}".format(self.console_port):
            raise ValueError("macOS HVF serial must match its emulator console port")
        for path in (self.emulator, self.adb, self.sdk_root, self.avd_home):
            if not isinstance(path, Path):
                raise ValueError("macOS HVF runtime paths must be pathlib.Path values")
        sdk_root = self.sdk_root.resolve(strict=False)
        if self.emulator.resolve(strict=False) != sdk_root / "emulator" / "emulator":
            raise ValueError("macOS HVF emulator must belong to the configured SDK")
        if self.adb.resolve(strict=False) != sdk_root / "platform-tools" / "adb":
            raise ValueError("macOS HVF ADB must belong to the configured SDK")


def probe_apple_silicon_macos() -> Tuple[bool, str, Mapping[str, str]]:
    machine = platform.machine().lower()
    fingerprint = {"platform": sys.platform, "machine": machine}
    if sys.platform != "darwin":
        return False, "macos-required", fingerprint
    if machine not in ("arm64", "aarch64"):
        return False, "apple-silicon-required", fingerprint
    return True, "ready", fingerprint


class MacosHvfBackend(AdbAttachedBackend):
    _LOGICAL_DISPLAY_WIDTH = 1280
    _LOGICAL_DISPLAY_HEIGHT = 720
    _LOGICAL_DISPLAY_DENSITY = 240

    def __init__(
        self,
        config: MacosHvfRuntimeConfig,
        executor: RuntimeCommandExecutor,
        trace: Optional[RuntimeTraceRecorder] = None,
        host_probe: Callable[[], Tuple[bool, str, Mapping[str, str]]] = probe_apple_silicon_macos,
        **kwargs: Any,
    ) -> None:
        self.config = config
        self.host_probe = host_probe
        self._owned_processes: Dict[str, RuntimeOwnedProcess] = {}
        super().__init__(
            built_in_backend_profiles()[BackendKind.MACOS_HVF],
            config.serial,
            config.package,
            config.component,
            config.host_class,
            str(config.adb),
            config.adb_server_port,
            False,
            config.angle_package,
            config.unity_command_line,
            config.manage_angle_routing,
            executor,
            config.launch_game,
            config.poll_interval_seconds,
            trace=trace,
            **kwargs,
        )

    @property
    def avd_config_path(self) -> Path:
        return self.config.avd_home / (self.config.avd_name + ".avd") / "config.ini"

    def _require_arm64_avd(self) -> Mapping[str, str]:
        try:
            lines = self.avd_config_path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise RuntimeBackendNotReady("macos-hvf-avd-config-missing") from exc
        values = {
            key.strip(): value.strip()
            for line in lines
            if "=" in line
            for key, value in (line.split("=", 1),)
        }
        identity = " ".join(
            values.get(name, "")
            for name in ("abi.type", "hw.cpu.arch", "image.sysdir.1")
        ).lower()
        if "arm64" not in identity and "aarch64" not in identity:
            raise RuntimeIdentityMismatch("macos-hvf-avd-abi-mismatch")
        return values

    def probe_host(self) -> RuntimeProbeResult:
        available, reason, fingerprint = self.host_probe()
        avd_verified = False
        acceleration_verified = False
        missing = [
            str(path)
            for path in (self.config.emulator, self.config.adb, self.avd_config_path)
            if not path.is_file()
        ]
        if missing:
            available = False
            reason = "macos-hvf-runtime-path-missing"
        if available:
            try:
                self._require_arm64_avd()
                avd_verified = True
            except Exception:
                available = False
                reason = "macos-hvf-avd-invalid"
        if available:
            acceleration = self.executor.run(
                RuntimeCommandSpec(
                    "macos-hvf-acceleration-check",
                    (str(self.config.emulator), "-accel-check"),
                    timeout_seconds=30.0,
                )
            )
            acceleration_text = (acceleration.stdout + " " + acceleration.stderr).lower()
            if not acceleration.succeeded or "hypervisor.framework" not in acceleration_text:
                available = False
                reason = "macos-hvf-acceleration-unavailable"
            else:
                acceleration_verified = True
        if available:
            inventory = self.executor.run(
                RuntimeCommandSpec(
                    "macos-hvf-avd-inventory",
                    (str(self.config.emulator), "-list-avds"),
                    timeout_seconds=30.0,
                )
            )
            avds = {line.strip() for line in inventory.stdout.splitlines() if line.strip()}
            if not inventory.succeeded or self.config.avd_name not in avds:
                available = False
                reason = "macos-hvf-avd-not-listed"
        host_fingerprint = dict(fingerprint)
        host_fingerprint["host_class"] = self.host_class
        if avd_verified:
            host_fingerprint["guest_architecture"] = "arm64-v8a"
        if acceleration_verified:
            host_fingerprint["acceleration"] = "hypervisor.framework"
        if missing:
            host_fingerprint["missing_path_count"] = str(len(missing))
        return RuntimeProbeResult(
            available, BackendKind.MACOS_HVF, reason, host_fingerprint
        )

    def provision(self, artifacts: Mapping[str, Any]) -> Mapping[str, Any]:
        provisioned = dict(super().provision(artifacts))
        self._require_arm64_avd()
        provisioned.update(
            {
                "avd_name": self.config.avd_name,
                "avd_config": str(self.avd_config_path.resolve()),
                "sdk_root": str(self.config.sdk_root.resolve()),
            }
        )
        return provisioned

    def start(self, provisioned: Mapping[str, Any]) -> Mapping[str, Any]:
        inventory = self.executor.run(
            RuntimeCommandSpec(
                "macos-hvf-adb-device-inventory",
                (
                    str(self.config.adb),
                    "-P",
                    str(self.config.adb_server_port),
                    "devices",
                ),
                timeout_seconds=10.0,
            )
        )
        if not inventory.succeeded:
            raise RuntimeBackendNotReady("adb-device-inventory-failed")
        for line in inventory.stdout.splitlines()[1:]:
            columns = line.split()
            if columns and columns[0] == self.serial:
                raise RuntimeBackendNotReady("emulator-serial-already-in-use")
        environment = {
            "ANDROID_AVD_HOME": str(self.config.avd_home.resolve()),
            "ANDROID_SDK_ROOT": str(self.config.sdk_root.resolve()),
            "ADB_SERVER_PORT": str(self.config.adb_server_port),
            "ANDROID_ADB_SERVER_PORT": str(self.config.adb_server_port),
        }
        inherited_path = os.environ.get("PATH", "")
        platform_tools = self.config.sdk_root / "platform-tools"
        environment["PATH"] = str(platform_tools.resolve()) + (
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
        instance_id = uuid.uuid4().hex
        process = self.executor.start(
            RuntimeCommandSpec(
                "macos-hvf-emulator-start",
                arguments,
                timeout_seconds=30.0,
                mutating=True,
                environment=environment,
            ),
            handle_id=instance_id,
        )
        self._owned_processes[instance_id] = process
        return {
            "instance_id": instance_id,
            "serial": self.serial,
            "owned": True,
            "pid": process.pid,
        }

    @staticmethod
    def _effective_display_value(output: str, label: str, pattern: str) -> Tuple[int, ...]:
        physical = re.search(
            r"^Physical " + re.escape(label) + r": " + pattern + r"\r?$",
            output,
            re.MULTILINE,
        )
        override = re.search(
            r"^Override " + re.escape(label) + r": " + pattern + r"\r?$",
            output,
            re.MULTILINE,
        )
        selected = override or physical
        if selected is None:
            raise RuntimeIdentityMismatch("logical-display-readback-malformed")
        return tuple(int(value) for value in selected.groups())

    def _prepare_game_cold_launch(self, instance: Mapping[str, Any]) -> None:
        size = "{0}x{1}".format(self._LOGICAL_DISPLAY_WIDTH, self._LOGICAL_DISPLAY_HEIGHT)
        self._require_success(
            self._adb("macos-hvf-logical-display-size-set", ("shell", "wm", "size", size), mutating=True),
            "logical-display-size-set-failed",
        )
        self._require_success(
            self._adb(
                "macos-hvf-logical-display-density-set",
                ("shell", "wm", "density", str(self._LOGICAL_DISPLAY_DENSITY)),
                mutating=True,
            ),
            "logical-display-density-set-failed",
        )
        size_result = self._adb("macos-hvf-logical-display-size-readback", ("shell", "wm", "size"))
        density_result = self._adb(
            "macos-hvf-logical-display-density-readback", ("shell", "wm", "density")
        )
        self._require_success(size_result, "logical-display-size-readback-failed")
        self._require_success(density_result, "logical-display-density-readback-failed")
        if self._effective_display_value(size_result.stdout, "size", r"([0-9]+)x([0-9]+)") != (
            self._LOGICAL_DISPLAY_WIDTH,
            self._LOGICAL_DISPLAY_HEIGHT,
        ) or self._effective_display_value(density_result.stdout, "density", r"([0-9]+)") != (
            self._LOGICAL_DISPLAY_DENSITY,
        ):
            raise RuntimeIdentityMismatch("logical-display-mismatch")
        if self.config.null_refresh_hz is not None:
            rate = str(self.config.null_refresh_hz)
            self._require_success(
                self._adb(
                    "macos-hvf-angle-null-refresh-rate-set",
                    ("shell", "setprop", "debug.angle.null_refresh_hz", rate),
                    mutating=True,
                ),
                "angle-null-refresh-rate-set-failed",
            )
            observed = self._adb(
                "macos-hvf-angle-null-refresh-rate-readback",
                ("shell", "getprop", "debug.angle.null_refresh_hz"),
            )
            if not observed.succeeded or observed.stdout.strip() != rate:
                raise RuntimeIdentityMismatch("angle-null-refresh-rate-mismatch")

    def restart_game(self, instance: Mapping[str, Any]) -> None:
        self._close_observer(instance)
        self._launch_game_process(instance, 60.0, "game-force-stop", "game-relaunch")

    def restart_android(self, instance: Mapping[str, Any]) -> None:
        self._close_observer(instance)
        result = self._adb("android-reboot", ("reboot",), mutating=True)
        self._require_success(result, "android-reboot-failed")

    def supports_recovery(self, recovery: str) -> bool:
        return recovery in ("game", "android")

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
                self._adb("macos-hvf-emulator-stop", ("emu", "kill"), timeout_seconds=15.0, mutating=True)
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

    def qualification_plan(self, runtime_lock: Mapping[str, Any]) -> Mapping[str, Any]:
        plan = dict(super().qualification_plan(runtime_lock))
        plan["state_changes"] = [
            "start-owned-emulator",
            "set-canonical-logical-display",
            "launch-game" if self.launch_game else "observe-existing-game",
            "create-and-remove-adb-forward",
            "stop-owned-emulator",
        ]
        if self.config.null_refresh_hz is not None:
            plan["state_changes"].insert(2, "set-angle-null-refresh-rate")
        if self.manage_angle_routing:
            plan["state_changes"].insert(3, "temporarily-set-and-restore-angle-routing")
        plan["compatibility_start_profile"] = {
            "host": "apple-silicon-macos",
            "guest_abi": "arm64-v8a",
            "acceleration": "hypervisor.framework",
            "gpu": "swiftshader_indirect",
            "snapshots": "load-save-disabled-for-qualification",
            "null_refresh_hz": self.config.null_refresh_hz,
            "logical_display": "1280x720@240",
            "multi_instance_qualified": False,
        }
        plan["game_launch_profile"] = {
            "force_stop_before_launch": self.launch_game,
            "unity_command_line": self.unity_command_line,
            "angle_routing": "managed-ephemeral" if self.manage_angle_routing else "verify-only",
        }
        return plan


__all__ = ["MacosHvfBackend", "MacosHvfRuntimeConfig", "probe_apple_silicon_macos"]
