"""Runtime-handle adapter for an already-managed ADB observer bridge."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Mapping, Optional

from ..alas_package_process_lease import AlasPackageProcessLease
from ..runtime_trace import RuntimeTraceRecorder
from ..semantic_oracle import (
    AdbObserverBridge,
    AndroidPackageFingerprint,
    ObserverTransportError,
    SemanticGateClosed,
)
from .ports import RuntimeHandlePort


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")


PINNED_CN_GAME_FINGERPRINT = AndroidPackageFingerprint(
    version_name="9.7.10",
    version_code=9710,
    primary_abi="x86_64",
    base_apk_sha256=(
        "e6d3ef4baac2509cc97a289b91bfd5f9d0dcd7ad8994880a192298983208699f"
    ),
    il2cpp_sha256=(
        "e3f1cfc442b67f1d4c9877fd9ceaedc3d68f2842ad677445241b9cc9c05d1c67"
    ),
)


def semantic_runtime_fingerprint_sha256(
    *,
    package: str,
    component: str,
    driver_revision: str,
    game_fingerprint: AndroidPackageFingerprint,
) -> str:
    """Hash the backend-neutral identity required by one semantic session."""

    if not isinstance(package, str) or not package:
        raise ValueError("runtime fingerprint package is required")
    if not isinstance(component, str) or not component:
        raise ValueError("runtime fingerprint component is required")
    if (
        not isinstance(driver_revision, str)
        or _REVISION_PATTERN.fullmatch(driver_revision) is None
    ):
        raise ValueError("runtime fingerprint driver revision must be pinned")
    if not isinstance(game_fingerprint, AndroidPackageFingerprint):
        raise TypeError("runtime fingerprint requires an Android package fingerprint")
    payload = {
        "component": component,
        "driver_revision": driver_revision,
        "game_fingerprint": asdict(game_fingerprint),
        "package": package,
        "schema": "alas-headless.semantic-runtime-identity/v1",
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


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


@dataclass
class PinnedPackageGate:
    """Cache one independent ADB verification of the installed package."""

    bridge: AdbObserverBridge
    expected: AndroidPackageFingerprint = PINNED_CN_GAME_FINGERPRINT
    _verified_pid: Optional[int] = None

    def accept_process_lease(self, lease: AlasPackageProcessLease) -> None:
        if not isinstance(lease, AlasPackageProcessLease):
            raise SemanticGateClosed("package process lease is not verified")
        if (
            self.bridge.pid is None
            or lease.pid != self.bridge.pid
            or lease.package != self.bridge.package
        ):
            raise SemanticGateClosed("package process lease PID changed")
        self._verified_pid = lease.pid

    def __call__(self) -> None:
        if self.bridge.pid is None:
            raise SemanticGateClosed("ADB observer bridge is not open")
        if self._verified_pid == self.bridge.pid:
            return
        self.bridge.require_package_fingerprint(self.expected)
        self._verified_pid = self.bridge.pid


@dataclass
class RuntimeHandlePackageGate:
    """Bind a prepared backend-neutral handle to one expected identity."""

    handle: RuntimeHandlePort
    expected_fingerprint_sha256: str
    package: str
    driver_revision: str
    process_lease: Optional[AlasPackageProcessLease] = None
    _verified_pid: Optional[int] = None

    def __call__(self) -> None:
        if self.handle.fingerprint_sha256 != self.expected_fingerprint_sha256:
            raise SemanticGateClosed("runtime handle fingerprint changed")
        pid = self.handle.pid
        if self.process_lease is not None and (
            self.process_lease.pid != pid
            or self.process_lease.package != self.package
            or self.process_lease.driver_revision != self.driver_revision
        ):
            raise SemanticGateClosed("package process lease identity changed")
        if self._verified_pid is not None and self._verified_pid != pid:
            raise SemanticGateClosed("runtime handle PID changed")
        self._verified_pid = pid


@dataclass(frozen=True)
class PreparedRuntimeHandle:
    handle: RuntimeHandlePort
    package_gate: Callable[[], None]


@dataclass
class AdbRuntimeHandleFactory:
    """Prepare a bridge-backed handle without exposing ADB to the session."""

    serial: str
    package: str
    adb: str
    command_timeout_seconds: float
    fingerprint_sha256: str
    driver_revision: str
    process_lease: Optional[AlasPackageProcessLease] = None
    trace: Optional[RuntimeTraceRecorder] = None
    _bridge: AdbObserverBridge = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._bridge = AdbObserverBridge(
            self.serial,
            self.package,
            adb=self.adb,
            command_timeout_seconds=self.command_timeout_seconds,
            trace=self.trace,
        )

    def __call__(self) -> PreparedRuntimeHandle:
        self._bridge.open()
        package_gate = PinnedPackageGate(self._bridge)
        if self.process_lease is None:
            package_gate()
        else:
            if self.process_lease.driver_revision != self.driver_revision:
                raise SemanticGateClosed(
                    "package process lease driver revision changed"
                )
            package_gate.accept_process_lease(self.process_lease)
        return PreparedRuntimeHandle(
            handle=AdbRuntimeHandle(
                self._bridge,
                fingerprint_sha256=self.fingerprint_sha256,
            ),
            package_gate=package_gate,
        )

    def close(self) -> None:
        self._bridge.close()
