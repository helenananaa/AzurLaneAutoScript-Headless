from __future__ import annotations

import subprocess

import pytest

from alas_headless.adb_device import AdbDeviceSelectionError, resolve_adb_serial


def _runner(stdout: str):
    def run(*_args, **_kwargs):
        return subprocess.CompletedProcess(["adb", "devices"], 0, stdout, "")

    return run


def test_discovers_the_only_online_device() -> None:
    output = "List of devices attached\nlocal-1\tdevice product:test\n"
    assert resolve_adb_serial("adb", None, run=_runner(output)) == "local-1"


def test_explicit_serial_must_be_online() -> None:
    output = "List of devices attached\nlocal-1\tdevice\n"
    with pytest.raises(AdbDeviceSelectionError, match="not online"):
        resolve_adb_serial("adb", "local-2", run=_runner(output))


def test_ambiguous_discovery_requires_explicit_serial() -> None:
    output = "List of devices attached\nlocal-1\tdevice\nlocal-2\tdevice\n"
    with pytest.raises(AdbDeviceSelectionError, match="multiple online"):
        resolve_adb_serial("adb", None, run=_runner(output))


def test_offline_and_unauthorized_devices_are_not_candidates() -> None:
    output = (
        "List of devices attached\n"
        "local-1\toffline\n"
        "local-2\tunauthorized\n"
    )
    with pytest.raises(AdbDeviceSelectionError, match="no online"):
        resolve_adb_serial("adb", None, run=_runner(output))
