"""Runtime-handle adapter for an already-managed ADB observer bridge."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Optional

from ..alas_package_process_lease import AlasPackageProcessLease
from ..runtime_trace import RuntimeTraceRecorder
from ..semantic_oracle import (
    AdbObserverBridge,
    AndroidPackageFingerprint,
    ObserverResponseTimeout,
    ObserverTransportError,
    SemanticGateClosed,
)
from ..oracle.transport import observer_snapshot_semantic_ready
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
    required_primary_abi: str = "x86_64",
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
    if not isinstance(required_primary_abi, str) or not required_primary_abi:
        raise ValueError("runtime fingerprint required primary ABI is missing")
    # Installed game versions and hashes are intentionally excluded.  The
    # runtime identity pins the package/component, supported ABI, and observer
    # driver; updated clients are attempted and fail only on a concrete runtime
    # incompatibility.
    payload = {
        "component": component,
        "driver_revision": driver_revision,
        "package_compatibility": {
            "primary_abi": required_primary_abi,
        },
        "package": package,
        "schema": "alas-headless.semantic-runtime-identity/v2",
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
    """Cache one independent ADB compatibility check for the live package."""

    bridge: AdbObserverBridge
    required_primary_abi: str = "x86_64"
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
        self.bridge.require_package_compatibility(self.required_primary_abi)
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
    required_primary_abi: str = "x86_64"
    adb_server_port: int = 5037
    process_lease: Optional[AlasPackageProcessLease] = None
    trace: Optional[RuntimeTraceRecorder] = None
    _bridge: AdbObserverBridge = field(init=False, repr=False)
    _preverified_restart_pid: Optional[int] = field(
        default=None,
        init=False,
        repr=False,
    )

    _OBSERVER_STARTUP_TIMEOUT_SECONDS = 600.0
    _OBSERVER_STARTUP_POLL_SECONDS = 1.0
    _OBSERVER_STARTUP_MAX_AGE_MS = 5_000.0
    _OBSERVER_STARTUP_PID_POLL_SECONDS = 10.0

    def __post_init__(self) -> None:
        if (
            not isinstance(self.required_primary_abi, str)
            or not self.required_primary_abi
        ):
            raise ValueError("required primary ABI is missing")
        self._bridge = AdbObserverBridge(
            self.serial,
            self.package,
            adb=self.adb,
            adb_server_port=self.adb_server_port,
            command_timeout_seconds=self.command_timeout_seconds,
            trace=self.trace,
        )

    def __call__(self) -> PreparedRuntimeHandle:
        self._bridge.open()
        package_gate = PinnedPackageGate(
            self._bridge,
            required_primary_abi=self.required_primary_abi,
        )
        if self.process_lease is None:
            if self._preverified_restart_pid == self._bridge.pid:
                package_gate._verified_pid = self._bridge.pid
                self._wait_for_restarted_observer()
                self._preverified_restart_pid = None
            else:
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

    def _wait_for_restarted_observer(self) -> None:
        """Wait for a fresh snapshot after ``am start`` returns.

        Android's ``-W`` completion only proves that the Activity was launched.
        The publisher SDK and Unity/IL2CPP can still be initializing, during
        which the observer socket either closes a request without a payload or
        returns the explicit ``unavailable`` status.  Only those two startup
        states are retryable; every other protocol or transport failure remains
        fail-closed.
        """

        expected_pid = self._bridge.pid
        deadline = time.monotonic() + self._OBSERVER_STARTUP_TIMEOUT_SECONDS
        next_pid_check = (
            time.monotonic() + self._OBSERVER_STARTUP_PID_POLL_SECONDS
        )
        while True:
            response: Optional[Mapping[str, Any]] = None
            try:
                response = self._bridge.request("GET /v1/state\n")
            except ObserverTransportError as exc:
                if (
                    not isinstance(exc, ObserverResponseTimeout)
                    and str(exc) != "observer returned an empty response"
                ):
                    raise
            if response is not None:
                status = response.get("status")
                if status == "ok":
                    snapshot = response.get("snapshot")
                    if not isinstance(snapshot, Mapping):
                        raise ObserverTransportError(
                            "ready observer response has no snapshot"
                        )
                    age_ms = snapshot.get("age_ms")
                    if (
                        snapshot.get("status") == "ok"
                        and snapshot.get("pid") == expected_pid
                        and snapshot.get("driver_revision") == self.driver_revision
                        and observer_snapshot_semantic_ready(snapshot)
                        and isinstance(age_ms, (int, float))
                        and not isinstance(age_ms, bool)
                        and 0 <= age_ms <= self._OBSERVER_STARTUP_MAX_AGE_MS
                    ):
                        return
                elif status != "unavailable":
                    raise ObserverTransportError(
                        "observer returned an unexpected startup status"
                    )
            now = time.monotonic()
            if now >= next_pid_check:
                if self._bridge.package_pid() != expected_pid:
                    raise ObserverTransportError(
                        "game PID changed while observer was starting"
                    )
                next_pid_check = now + self._OBSERVER_STARTUP_PID_POLL_SECONDS
            if now >= deadline:
                raise ObserverTransportError(
                    "observer did not become ready after game restart"
                )
            time.sleep(self._OBSERVER_STARTUP_POLL_SECONDS)

    def close(self) -> None:
        self._bridge.close()

    def restart_game(self, component: str) -> None:
        self.close()
        self._preverified_restart_pid = None
        self._bridge.restart_game(
            component,
            required_primary_abi=self.required_primary_abi,
        )
        self._preverified_restart_pid = self._bridge.pid
