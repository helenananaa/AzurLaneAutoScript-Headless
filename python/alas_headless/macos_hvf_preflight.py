"""Read-only discovery for an Apple Silicon Android Emulator attachment.

The preflight deliberately stops at the existing ``external-adb`` ownership
boundary.  It discovers one exact running emulator and emits a candidate
runtime config, but it never starts an AVD, changes guest settings, launches the
game, or creates an ADB forward.  Like any ADB inventory command, it may start
the host-local ADB server when that server is not already running.
"""

from __future__ import annotations

import os
import platform
import re
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence

from .runtime_command import RuntimeCommandExecutor, RuntimeCommandSpec


PREFLIGHT_SCHEMA = "alas-headless.macos-hvf-external-adb-preflight/v1"
RUNTIME_CONFIG_SCHEMA = "alas-headless.runtime-config/v1"
_EMULATOR_SERIAL = re.compile(r"emulator-[0-9]+")


def _parse_avd_config(path: Path) -> Mapping[str, str]:
    values: Dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _parse_adb_devices(output: str) -> Mapping[str, str]:
    devices: Dict[str, str] = {}
    for line in output.splitlines()[1:]:
        columns = line.split()
        if len(columns) >= 2:
            devices[columns[0]] = columns[1]
    return devices


def _run(
    executor: RuntimeCommandExecutor,
    label: str,
    argv: Sequence[str],
    timeout_seconds: float = 15.0,
) -> Mapping[str, Any]:
    result = executor.run(
        RuntimeCommandSpec(label, tuple(argv), timeout_seconds=timeout_seconds)
    )
    return {
        "succeeded": result.succeeded,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def preflight_macos_hvf_external_adb(
    *,
    avd_name: str,
    sdk_root: Path,
    avd_home: Path,
    package: str,
    component: str,
    executor: RuntimeCommandExecutor,
    serial: Optional[str] = None,
    adb_server_port: int = 5037,
    expected_api_level: int = 32,
    platform_name: Optional[str] = None,
    machine: Optional[str] = None,
) -> Mapping[str, Any]:
    """Inspect one running Mac/HVF AVD without changing host or guest state."""

    observed_platform = platform_name if platform_name is not None else sys.platform
    observed_machine = machine if machine is not None else platform.machine()
    sdk_root = sdk_root.expanduser().resolve(strict=False)
    avd_home = avd_home.expanduser().resolve(strict=False)
    emulator = sdk_root / "emulator" / "emulator"
    adb = sdk_root / "platform-tools" / "adb"
    avd_config_path = avd_home / (avd_name + ".avd") / "config.ini"

    checks: Dict[str, Mapping[str, Any]] = {}
    failures = []

    def record(name: str, passed: bool, reason: str, **details: Any) -> None:
        checks[name] = {"outcome": "pass" if passed else "blocked", **details}
        if not passed:
            failures.append(reason)

    record(
        "host-platform",
        observed_platform == "darwin" and observed_machine in ("arm64", "aarch64"),
        "apple-silicon-macos-required",
        platform=observed_platform,
        machine=observed_machine,
    )
    for name, path in (("emulator-tool", emulator), ("adb-tool", adb)):
        record(
            name,
            path.is_file() and os.access(str(path), os.X_OK),
            name + "-missing-or-not-executable",
            path=str(path),
        )
    record(
        "avd-config",
        avd_config_path.is_file(),
        "avd-config-missing",
        path=str(avd_config_path),
    )

    avd_values: Mapping[str, str] = {}
    if avd_config_path.is_file():
        try:
            avd_values = _parse_avd_config(avd_config_path)
        except OSError:
            failures.append("avd-config-unreadable")
        abi_signals = " ".join(
            avd_values.get(key, "")
            for key in ("abi.type", "hw.cpu.arch", "image.sysdir.1")
        ).lower()
        record(
            "avd-abi",
            "arm64" in abi_signals or "aarch64" in abi_signals,
            "avd-arm64-identity-missing",
            abi_type=avd_values.get("abi.type", ""),
            cpu_arch=avd_values.get("hw.cpu.arch", ""),
            image_sysdir=avd_values.get("image.sysdir.1", ""),
        )

    acceleration: Mapping[str, Any] = {"succeeded": False, "stdout": "", "stderr": ""}
    avd_inventory: Mapping[str, Any] = acceleration
    adb_inventory: Mapping[str, Any] = acceleration
    if emulator.is_file():
        acceleration = _run(
            executor,
            "macos-hvf-acceleration-check",
            (str(emulator), "-accel-check"),
        )
        accel_text = (str(acceleration["stdout"]) + " " + str(acceleration["stderr"])).lower()
        record(
            "hvf-acceleration",
            bool(acceleration["succeeded"]) and "hypervisor.framework" in accel_text,
            "hypervisor-framework-unavailable",
            output=(str(acceleration["stdout"]) or str(acceleration["stderr"])),
        )
        avd_inventory = _run(
            executor,
            "macos-hvf-avd-inventory",
            (str(emulator), "-list-avds"),
        )
        avds = tuple(line.strip() for line in str(avd_inventory["stdout"]).splitlines() if line.strip())
        record(
            "avd-inventory",
            bool(avd_inventory["succeeded"]) and avd_name in avds,
            "configured-avd-not-listed",
            avd_name=avd_name,
            listed_avds=list(avds),
        )

    selected_serial: Optional[str] = None
    devices: Mapping[str, str] = {}
    if adb.is_file():
        adb_prefix = (str(adb), "-P", str(adb_server_port))
        adb_inventory = _run(
            executor,
            "macos-hvf-adb-inventory",
            adb_prefix + ("devices", "-l"),
        )
        devices = _parse_adb_devices(str(adb_inventory["stdout"]))
        ready_emulators = tuple(
            device_serial
            for device_serial, state in devices.items()
            if state == "device" and _EMULATOR_SERIAL.fullmatch(device_serial)
        )
        if serial is not None:
            selected_serial = serial if devices.get(serial) == "device" else None
            selection_reason = "requested-emulator-not-ready"
        elif len(ready_emulators) == 1:
            selected_serial = ready_emulators[0]
            selection_reason = "running-emulator-selection-ambiguous"
        else:
            selection_reason = "running-emulator-selection-ambiguous"
        record(
            "adb-emulator-selection",
            bool(adb_inventory["succeeded"]) and selected_serial is not None,
            selection_reason,
            requested_serial=serial,
            ready_emulators=list(ready_emulators),
        )

    guest: Dict[str, Any] = {}
    if selected_serial is not None:
        adb_prefix = (
            str(adb),
            "-P",
            str(adb_server_port),
            "-s",
            selected_serial,
        )
        probes = {
            "abi_list": ("shell", "getprop", "ro.product.cpu.abilist"),
            "api_level": ("shell", "getprop", "ro.build.version.sdk"),
            "build_fingerprint": ("shell", "getprop", "ro.build.fingerprint"),
            "package_paths": ("shell", "pm", "path", package),
            "foreground": ("shell", "dumpsys", "activity", "activities"),
            "game_pid": ("shell", "pidof", package),
        }
        for name, arguments in probes.items():
            guest[name] = _run(
                executor,
                "macos-hvf-guest-" + name.replace("_", "-"),
                adb_prefix + arguments,
            )
        foreground = guest["foreground"]
        foreground_lines = [
            line.strip()
            for line in str(foreground["stdout"]).splitlines()
            if "topResumedActivity=" in line or "mResumedActivity:" in line
        ]
        guest["foreground"] = {
            **foreground,
            "stdout": foreground_lines[0] if foreground_lines else "",
        }
        abi_output = str(guest["abi_list"]["stdout"])
        api_output = str(guest["api_level"]["stdout"])
        package_output = str(guest["package_paths"]["stdout"])
        record(
            "guest-identity",
            bool(guest["abi_list"]["succeeded"])
            and "arm64-v8a" in abi_output.split(",")
            and bool(guest["api_level"]["succeeded"])
            and api_output == str(expected_api_level),
            "guest-api-or-abi-mismatch",
            abi_list=abi_output,
            api_level=api_output,
            build_fingerprint=str(guest["build_fingerprint"]["stdout"]),
        )
        record(
            "game-package",
            bool(guest["package_paths"]["succeeded"])
            and any(line.startswith("package:") for line in package_output.splitlines()),
            "game-package-unavailable",
            package=package,
            package_paths=package_output.splitlines(),
        )

    outcome = "pass" if not failures else "blocked"
    runtime_config: Optional[Mapping[str, Any]] = None
    if outcome == "pass" and selected_serial is not None:
        runtime_config = {
            "schema": RUNTIME_CONFIG_SCHEMA,
            "backend": "external-adb",
            "serial": selected_serial,
            "package": package,
            "component": component,
            "host_class": "macos-arm64-hvf-external",
            "adb": str(adb),
            "adb_server_port": adb_server_port,
            "connect_transport": False,
            "angle_package": "org.chromium.angle",
            "unity_command_line": "-force-gfx-st",
            "launch_game": True,
            "manage_angle_routing": False,
            "allow_game_restart": True,
            "allow_android_restart": True,
            "poll_interval_seconds": 1.0,
        }

    return {
        "schema": PREFLIGHT_SCHEMA,
        "outcome": outcome,
        "failures": failures,
        "checks": checks,
        "sdk_root": str(sdk_root),
        "avd_home": str(avd_home),
        "avd_name": avd_name,
        "selected_serial": selected_serial,
        "devices": dict(devices),
        "guest": guest,
        "runtime_config": runtime_config,
        "runtime_mutation_requested": False,
        "adb_server_may_start": True,
    }
