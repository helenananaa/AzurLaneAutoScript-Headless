"""Runtime-handle adapter for an already-managed ADB observer bridge."""

from __future__ import annotations

import re
from typing import Any, Mapping

from ..semantic_oracle import AdbObserverBridge, ObserverTransportError


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class AdbRuntimeHandle:
    """Expose bridge I/O without acquiring any backend lifecycle authority.

    The wrapped bridge must be prepared and owned by the caller.  This adapter
    deliberately has no open, close, provision, start, stop, or reconnect
    operation; it only translates the existing bridge surface to the v2
    ``RuntimeHandlePort`` names.
    """

    __slots__ = ("__bridge", "__fingerprint_sha256")

    def __init__(
        self,
        bridge: AdbObserverBridge,
        *,
        fingerprint_sha256: str,
    ) -> None:
        if not isinstance(bridge, AdbObserverBridge):
            raise TypeError("ADB runtime handle requires an AdbObserverBridge")
        if (
            not isinstance(fingerprint_sha256, str)
            or _SHA256_PATTERN.fullmatch(fingerprint_sha256) is None
        ):
            raise ValueError(
                "runtime handle fingerprint must be a lowercase SHA-256"
            )
        self.__bridge = bridge
        self.__fingerprint_sha256 = fingerprint_sha256

    @property
    def fingerprint_sha256(self) -> str:
        return self.__fingerprint_sha256

    @property
    def pid(self) -> int:
        pid = self.__bridge.pid
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise ObserverTransportError(
                "ADB observer bridge has no attached game PID"
            )
        return pid

    def observer_request(self, request_line: str) -> Mapping[str, Any]:
        return self.__bridge.request(request_line)

    def foreground_component(self) -> str:
        return self.__bridge.foreground_component()

    def tap(self, x: int, y: int) -> None:
        self.__bridge.tap(x, y)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int,
    ) -> None:
        self.__bridge.swipe(x1, y1, x2, y2, duration_ms)
