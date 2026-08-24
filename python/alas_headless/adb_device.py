"""Small, explicit ADB device selection helpers for live tooling."""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence


_SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


class AdbDeviceSelectionError(RuntimeError):
    """Raised when a live tool cannot bind one exact online ADB device."""


def _online_serials(output: str) -> tuple[str, ...]:
    serials: list[str] = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("List of devices attached"):
            continue
        fields = line.split()
        if len(fields) >= 2 and fields[1] == "device":
            serial = fields[0]
            if _SERIAL_PATTERN.fullmatch(serial) is not None:
                serials.append(serial)
    return tuple(dict.fromkeys(serials))


def resolve_adb_serial(
    adb: str,
    requested: str | None,
    *,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Return the requested online serial, or discover exactly one online device."""

    if not isinstance(adb, str) or not adb:
        raise ValueError("ADB executable cannot be empty")
    if requested is not None and (
        not isinstance(requested, str)
        or _SERIAL_PATTERN.fullmatch(requested) is None
    ):
        raise AdbDeviceSelectionError("ADB serial is malformed")

    try:
        completed = run(
            [adb, "devices"],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AdbDeviceSelectionError("unable to enumerate ADB devices") from exc

    online = _online_serials(completed.stdout)
    if requested is not None:
        if requested not in online:
            raise AdbDeviceSelectionError(
                f"requested ADB device is not online: {requested}"
            )
        return requested
    if not online:
        raise AdbDeviceSelectionError("no online ADB device found")
    if len(online) != 1:
        raise AdbDeviceSelectionError(
            "multiple online ADB devices found; pass --serial explicitly"
        )
    return online[0]


__all__: Sequence[str] = ("AdbDeviceSelectionError", "resolve_adb_serial")
