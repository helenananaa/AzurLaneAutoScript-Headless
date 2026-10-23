#!/usr/bin/env python3
"""Collect exact account-free Mac/HVF runtime artifacts from a running AVD."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import types
from pathlib import Path
from typing import Sequence


_source_package = Path(__file__).resolve().parents[2] / "python" / "alas_headless"
if _source_package.is_dir() and "alas_headless" not in sys.modules:
    package_module = types.ModuleType("alas_headless")
    package_module.__path__ = [str(_source_package)]
    package_module.__package__ = "alas_headless"
    sys.modules["alas_headless"] = package_module

from alas_headless.macos_hvf_identity import (
    IDENTITY_SCHEMA,
    build_platform_resource_manifest,
    build_provision_profile,
    file_sha256,
    write_canonical_document,
)
from alas_headless.macos_hvf_preflight import preflight_macos_hvf_external_adb
from alas_headless.oracle.transport import AdbObserverBridge
from alas_headless.runtime_command import RuntimeCommandExecutor, RuntimeExecutionPolicy


def main(argv: Sequence[str] = ()) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--avd-name", required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--avd-home", required=True, type=Path)
    parser.add_argument("--console-port", required=True, type=int)
    parser.add_argument("--adb-server-port", type=int, default=5037)
    parser.add_argument("--package", default="com.bilibili.azurlane")
    parser.add_argument("--identity-output", required=True, type=Path)
    parser.add_argument("--provision-profile-output", required=True, type=Path)
    parser.add_argument("--resource-manifest-output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv else None)
    outputs = (
        args.identity_output,
        args.provision_profile_output,
        args.resource_manifest_output,
    )
    if any(path.exists() for path in outputs):
        parser.error("identity outputs must not already exist")

    executor = RuntimeCommandExecutor(RuntimeExecutionPolicy(True, False))
    preflight = preflight_macos_hvf_external_adb(
        avd_name=args.avd_name,
        sdk_root=args.sdk_root,
        avd_home=args.avd_home,
        package=args.package,
        component=args.package + "/com.manjuu.azurlane.MainActivity",
        serial=args.serial,
        adb_server_port=args.adb_server_port,
        expected_api_level=32,
        executor=executor,
    )
    if preflight["outcome"] != "pass":
        raise RuntimeError("macOS HVF preflight did not pass")
    avd_config = args.avd_home / (args.avd_name + ".avd") / "config.ini"
    values = {}
    for line in avd_config.read_text(encoding="utf-8").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    image_directory = Path(values["image.sysdir.1"].rstrip("/\\"))
    if not image_directory.is_absolute():
        image_directory = args.sdk_root / image_directory
    image_directory = image_directory.resolve()
    sdk_root = args.sdk_root.resolve()
    image_directory.relative_to(sdk_root)
    system_image = image_directory / "system.img"
    system_image_relative = system_image.relative_to(sdk_root).as_posix()

    emulator = sdk_root / "emulator/emulator"
    version = subprocess.run(
        (str(emulator), "-version"),
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout.splitlines()[0].strip()
    bridge = AdbObserverBridge(
        args.serial,
        args.package,
        adb=str(sdk_root / "platform-tools/adb"),
        adb_server_port=args.adb_server_port,
        command_timeout_seconds=30.0,
    )
    game = bridge.package_fingerprint()
    android_fingerprint = bridge._run(("shell", "getprop", "ro.build.fingerprint"))
    api_level = int(bridge._run(("shell", "getprop", "ro.build.version.sdk")))
    android_abi = bridge._run(("shell", "getprop", "ro.product.cpu.abi"))
    angle_paths = [
        line[len("package:") :]
        for line in bridge._run(("shell", "pm", "path", "org.chromium.angle")).splitlines()
        if line.startswith("package:")
    ]
    if len(angle_paths) != 1:
        raise RuntimeError("expected exactly one ANGLE APK")
    angle_sha256 = bridge._device_sha256(angle_paths[0])
    system_sha256 = file_sha256(system_image)
    profile = build_provision_profile(
        avd_name=args.avd_name,
        avd_config_sha256=file_sha256(avd_config),
        sdk_root=str(sdk_root),
        system_image_relative_path=system_image_relative,
        system_image_sha256=system_sha256,
        emulator_version=version,
        acceleration="hypervisor.framework",
        console_port=args.console_port,
        adb_server_port=args.adb_server_port,
        android_fingerprint=android_fingerprint,
        api_level=api_level,
        abi=android_abi,
    )
    profile_sha256 = write_canonical_document(args.provision_profile_output, profile)
    resource_manifest = build_platform_resource_manifest(
        args.package, game.version_name, game.version_code
    )
    resource_sha256 = write_canonical_document(
        args.resource_manifest_output, resource_manifest
    )
    identity = {
        "schema": IDENTITY_SCHEMA,
        "outcome": "pass",
        "platform": sys.platform,
        "machine": platform.machine().lower(),
        "avd_name": args.avd_name,
        "serial": args.serial,
        "package": args.package,
        "android_fingerprint": android_fingerprint,
        "api_level": api_level,
        "android_abi": android_abi,
        "system_image_sha256": system_sha256,
        "provision_profile_sha256": profile_sha256,
        "angle_apk_sha256": angle_sha256,
        "game_version_name": game.version_name,
        "game_version_code": game.version_code,
        "game_abi": game.primary_abi,
        "game_base_apk_sha256": game.base_apk_sha256,
        "game_libil2cpp_sha256": game.il2cpp_sha256,
        "resource_manifest_sha256": resource_sha256,
        "account_data_collected": False,
    }
    write_canonical_document(args.identity_output, identity)
    print(json.dumps(identity, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
