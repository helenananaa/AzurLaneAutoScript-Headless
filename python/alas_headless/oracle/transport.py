"""Transport for the typed ALAS boundary."""

from __future__ import annotations

import json
import math
import re
import socket
import subprocess
import time
from typing import Any, Callable, Mapping, Optional, Sequence, Tuple
from ..runtime_trace import RuntimeTraceRecorder
from .contracts import AndroidPackageFingerprint, OBSERVER_SCHEMA
from .errors import ObserverResponseTimeout, ObserverTransportError, SemanticGateClosed


def encode_adb_shell_string_extra(value: str) -> str:
    """Keep a leading dash as string data across adb's shell argv reparse."""

    if not isinstance(value, str) or not value:
        raise ValueError("ADB shell string extra must be non-empty")
    return "\\" + value if value.startswith("-") else value


def observer_snapshot_semantic_ready(snapshot: Mapping[str, Any]) -> bool:
    """Return whether the main-thread typed UI publisher is fully ready."""

    def exact_integer(name: str, expected: int) -> bool:
        value = snapshot.get(name)
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and value == expected
        )

    return bool(
        snapshot.get("main_thread") is True
        and exact_integer("flags", 15)
        and exact_integer("ui_stage", 100)
        and exact_integer("ui_method_mask", 15)
    )


def request_observer_state(
    request: Callable[[str], Mapping[str, Any]],
) -> Tuple[Mapping[str, Any], Mapping[str, Any], bool]:
    """Read snapshot/buttons in one round trip, with an explicit legacy fallback."""

    combined = request("GET /v1/state\n")
    combined_response = (
        isinstance(combined, Mapping)
        and combined.get("protocol_schema") == OBSERVER_SCHEMA
        and combined.get("status") == "ok"
        and isinstance(combined.get("snapshot"), Mapping)
        and isinstance(combined.get("buttons"), Mapping)
    )
    if combined_response:
        return combined["snapshot"], combined["buttons"], True
    if isinstance(combined, Mapping) and combined.get("status") == "bad-request":
        # Compatibility with pre-state observer builds. The atomic endpoint
        # reduces this pair to one socket round trip without changing cadence.
        return (
            request("GET /v1/snapshot\n"),
            request("GET /v1/buttons\n"),
            False,
        )
    if (
        isinstance(combined, Mapping)
        and combined.get("protocol_schema") == OBSERVER_SCHEMA
        and combined.get("status") == "unavailable"
    ):
        raise ObserverTransportError("observer is unavailable")
    raise ObserverTransportError("combined observer response is malformed")


class TcpObserverTransport:
    """One-request-per-connection client for an ADB-forwarded observer socket."""

    def __init__(
        self,
        host: str,
        port: int,
        timeout_seconds: float = 3.0,
        maximum_response_bytes: int = 4 * 1024 * 1024,
        trace: Optional[RuntimeTraceRecorder] = None,
    ) -> None:
        self._host = host
        self._port = port
        self._timeout_seconds = timeout_seconds
        self._maximum_response_bytes = maximum_response_bytes
        self._trace = trace

    def request(self, request_line: str) -> Mapping[str, Any]:
        number = r'[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?'
        projection = re.fullmatch(r'GET /v1/globe-projection (' + number + r') (' + number + r')\n', request_line)
        projection_request = projection is not None and all(math.isfinite(float(v)) for v in projection.groups())
        drag = re.fullmatch(r'GET /v1/(?:os-map-drag|globe-map-drag) ' + ' '.join(['(' + number + ')'] * 4) + r'\n', request_line)
        drag_request = drag is not None and all(math.isfinite(float(v)) for v in drag.groups())
        if request_line not in (
            "GET /v1/snapshot\n",
            "GET /v1/buttons\n",
            "GET /v1/ui\n",
            "GET /v1/state\n",
        ) and not projection_request and not drag_request:
            raise ObserverTransportError(
                "client refused an unsupported observer request"
            )
        started_ns = time.monotonic_ns()
        endpoint = request_line.split(" ", 1)[1].strip()
        connected = False
        try:
            with socket.create_connection(
                (self._host, self._port), self._timeout_seconds
            ) as client:
                connected = True
                client.settimeout(self._timeout_seconds)
                client.sendall(request_line.encode("ascii"))
                chunks = bytearray()
                while True:
                    chunk = client.recv(8192)
                    if not chunk:
                        break
                    chunks.extend(chunk)
                    if len(chunks) > self._maximum_response_bytes:
                        raise ObserverTransportError(
                            "observer response exceeded size limit"
                        )
                    if b"\n" in chunk:
                        break
        except ObserverTransportError as exc:
            if self._trace is not None:
                self._trace.emit(
                    "observer.request",
                    outcome="error",
                    duration_ns=time.monotonic_ns() - started_ns,
                    fields={"endpoint": endpoint, "exception_type": type(exc).__name__},
                )
            raise
        except TimeoutError as exc:
            if self._trace is not None:
                self._trace.emit(
                    "observer.request",
                    outcome="error",
                    duration_ns=time.monotonic_ns() - started_ns,
                    fields={"endpoint": endpoint, "exception_type": type(exc).__name__},
                )
            if connected:
                raise ObserverResponseTimeout(
                    "observer response timed out"
                ) from exc
            raise ObserverTransportError("observer socket request failed") from exc
        except OSError as exc:
            if self._trace is not None:
                self._trace.emit(
                    "observer.request",
                    outcome="error",
                    duration_ns=time.monotonic_ns() - started_ns,
                    fields={"endpoint": endpoint, "exception_type": type(exc).__name__},
                )
            raise ObserverTransportError("observer socket request failed") from exc

        line = bytes(chunks).split(b"\n", 1)[0]
        if not line:
            if self._trace is not None:
                self._trace.emit(
                    "observer.request",
                    outcome="error",
                    duration_ns=time.monotonic_ns() - started_ns,
                    fields={"endpoint": endpoint, "failure_stage": "empty-response"},
                )
            raise ObserverTransportError("observer returned an empty response")
        try:
            value = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            if self._trace is not None:
                self._trace.emit(
                    "observer.request",
                    outcome="error",
                    duration_ns=time.monotonic_ns() - started_ns,
                    fields={"endpoint": endpoint, "failure_stage": "decode-json"},
                )
            raise ObserverTransportError("observer returned invalid JSON") from exc
        if not isinstance(value, dict):
            if self._trace is not None:
                self._trace.emit(
                    "observer.request",
                    outcome="error",
                    duration_ns=time.monotonic_ns() - started_ns,
                    fields={"endpoint": endpoint, "failure_stage": "response-shape"},
                )
            raise ObserverTransportError("observer response is not a JSON object")
        if self._trace is not None:
            trace_fields = {"endpoint": endpoint, "response_bytes": len(line)}
            identity_source = value
            if endpoint == "/v1/state" and isinstance(value.get("snapshot"), dict):
                identity_source = value["snapshot"]
            generation = identity_source.get("generation")
            age_ms = identity_source.get("age_ms")
            if isinstance(generation, int) and not isinstance(generation, bool):
                trace_fields["generation"] = generation
            if isinstance(age_ms, (int, float)) and not isinstance(age_ms, bool):
                trace_fields["snapshot_age_ms"] = age_ms
            self._trace.emit(
                "observer.request",
                duration_ns=time.monotonic_ns() - started_ns,
                fields=trace_fields,
            )
        return value


class AdbObserverBridge:
    """ADB forwarding, foreground inspection, and tap injection for one game PID."""

    _FOREGROUND_PATTERN = re.compile(
        r"(?:topResumedActivity|mResumedActivity)\s*[:=].*?\bu\d+\s+([^\s}]+/[^\s}]+)"
    )
    _DEVICE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9_./:+@=~-]+$")
    _SHA256_PATTERN = re.compile(r"^([0-9a-fA-F]{64})(?:\s|$)")
    _DEVICE_SHA256_MAX_ATTEMPTS = 2
    _DEVICE_SHA256_RETRY_DELAY_SECONDS = 3.0
    _PACKAGE_IDENTITY_TIMEOUT_SECONDS = 30.0
    _PACKAGE_PROCESS_TIMEOUT_SECONDS = 30.0

    def __init__(
        self,
        serial: str,
        package: str,
        adb: str = "adb",
        adb_server_port: Optional[int] = None,
        command_timeout_seconds: float = 10.0,
        trace: Optional[RuntimeTraceRecorder] = None,
    ) -> None:
        self.serial = serial
        self.package = package
        self.adb = adb
        if (
            adb_server_port is not None
            and (
                isinstance(adb_server_port, bool)
                or not isinstance(adb_server_port, int)
                or not 1 <= adb_server_port <= 65535
            )
        ):
            raise ValueError("ADB server port must be in [1, 65535]")
        self.adb_server_port = adb_server_port
        self.command_timeout_seconds = command_timeout_seconds
        self.trace = trace
        self.pid: Optional[int] = None
        self.port: Optional[int] = None
        self.transport: Optional[TcpObserverTransport] = None

    def _run(
        self,
        arguments: Sequence[str],
        timeout_seconds: Optional[float] = None,
    ) -> str:
        timeout = (
            self.command_timeout_seconds if timeout_seconds is None else timeout_seconds
        )
        operation = self._classify_adb_operation(arguments)
        started_ns = time.monotonic_ns()
        try:
            prefix = [self.adb]
            if self.adb_server_port is not None:
                prefix.extend(("-P", str(self.adb_server_port)))
            completed = subprocess.run(
                [*prefix, "-s", self.serial, *arguments],
                check=True,
                capture_output=True,
                text=False,
                timeout=timeout,
            )
            # ADB emits UTF-8 independently of Windows' locale. Decode on the
            # calling thread so malformed output is a classified failure.
            output = completed.stdout.decode('utf-8')
        except (OSError, subprocess.SubprocessError, UnicodeError) as exc:
            if self.trace is not None:
                self.trace.emit(
                    "adb.command",
                    outcome="error",
                    duration_ns=time.monotonic_ns() - started_ns,
                    fields={
                        "operation": operation,
                        "exception_type": type(exc).__name__,
                    },
                )
            raise ObserverTransportError("ADB command failed") from exc
        if self.trace is not None:
            self.trace.emit(
                "adb.command",
                duration_ns=time.monotonic_ns() - started_ns,
                fields={"operation": operation},
            )
        return output.strip()

    @staticmethod
    def _classify_adb_operation(arguments: Sequence[str]) -> str:
        parts = tuple(arguments)
        if parts == ("get-state",):
            return "get-state"
        if parts[:2] == ("shell", "pidof"):
            return "pidof-package"
        if parts[:2] == ("forward", "--remove"):
            return "forward-remove"
        if parts[:1] == ("forward",):
            return "forward-add"
        if parts[:4] == ("shell", "dumpsys", "activity", "activities"):
            return "foreground-activity"
        if parts[:3] == ("shell", "dumpsys", "package"):
            return "package-metadata"
        if parts[:3] == ("shell", "input", "tap"):
            return "input-tap"
        if parts[:3] == ("shell", "input", "swipe"):
            return "input-swipe"
        if parts[:2] == ("shell", "sha256sum"):
            return "file-sha256"
        if parts[:3] == ("shell", "pm", "path"):
            return "package-path"
        if parts[:4] == ("shell", "settings", "get", "global"):
            return "settings-read"
        if parts[:4] in (
            ("shell", "settings", "put", "global"),
            ("shell", "settings", "delete", "global"),
        ):
            return "settings-write"
        if parts[:2] == ("shell", "find"):
            return "file-find"
        return "other"

    def open(self) -> "AdbObserverBridge":
        if self.transport is not None:
            return self
        if self._run(("get-state",)) != "device":
            raise ObserverTransportError("ADB device is not ready")
        pid_text = self._run(
            ("shell", "pidof", self.package),
            timeout_seconds=self._PACKAGE_PROCESS_TIMEOUT_SECONDS,
        )
        if not pid_text.isdigit():
            raise ObserverTransportError("expected exactly one numeric game PID")
        self.pid = int(pid_text)
        port_text = self._run(
            (
                "forward",
                "tcp:0",
                "localabstract:alas.g3.{0}".format(self.pid),
            )
        )
        if not port_text.isdigit():
            raise ObserverTransportError("ADB did not return a forwarding port")
        self.port = int(port_text)
        self.transport = TcpObserverTransport("127.0.0.1", self.port, trace=self.trace)
        return self

    def close(self) -> None:
        if self.port is not None:
            try:
                self._run(("forward", "--remove", "tcp:{0}".format(self.port)))
            finally:
                self.transport = None
                self.port = None

    def restart_game(
        self,
        component: str,
        *,
        expected_package_fingerprint: Optional[AndroidPackageFingerprint] = None,
        required_primary_abi: Optional[str] = None,
    ) -> None:
        """Cold-restart the configured game with the required headless Unity flag."""

        if self.transport is not None:
            raise ObserverTransportError(
                "observer bridge must be closed before game restart"
            )
        if not component or not component.startswith(self.package + "/"):
            raise ObserverTransportError("game restart component is not pinned")
        previous_pid = self.pid
        # A busy emulator can take longer than the ordinary read timeout to
        # tear down Unity and its updater.  This exact, pinned force-stop is
        # idempotent; allow a bounded command window before relaunching.
        force_stop_timeout = max(self.command_timeout_seconds, 30.0)
        try:
            self._run(
                ("shell", "am", "force-stop", self.package),
                timeout_seconds=force_stop_timeout,
            )
        except ObserverTransportError as exc:
            # ``am force-stop`` can finish on-device just after the host-side
            # adb wait expires.  A heavily loaded emulator can still expose
            # the old PID for a short interval, so require bounded, repeated
            # proof that the exact package process has disappeared.
            stop_deadline = time.monotonic() + 90.0
            while True:
                try:
                    stopped_pid = self._run(
                        ("shell", "pidof", self.package),
                        timeout_seconds=force_stop_timeout,
                    )
                except ObserverTransportError:
                    if time.monotonic() >= stop_deadline:
                        raise exc
                else:
                    if not stopped_pid:
                        break
                    if not stopped_pid.isdigit():
                        raise exc
                    if time.monotonic() >= stop_deadline:
                        raise exc
                time.sleep(1.0)
        if (
            expected_package_fingerprint is not None
            and required_primary_abi is not None
        ):
            raise ValueError("package restart verification mode is ambiguous")
        if expected_package_fingerprint is not None:
            self.require_package_fingerprint(expected_package_fingerprint)
        elif required_primary_abi is not None:
            self.require_package_compatibility(required_primary_abi)
        self._run(
            (
                "shell",
                "am",
                "start",
                "-W",
                "--es",
                "unity",
                encode_adb_shell_string_extra("-force-gfx-st"),
                "-n",
                component,
            ),
            timeout_seconds=max(self.command_timeout_seconds, 60.0),
        )
        pid_text = self._run(
            ("shell", "pidof", self.package),
            timeout_seconds=self._PACKAGE_PROCESS_TIMEOUT_SECONDS,
        )
        if not pid_text.isdigit():
            raise ObserverTransportError(
                "expected exactly one numeric game PID after cold restart"
            )
        current_pid = int(pid_text)
        if previous_pid is not None and current_pid == previous_pid:
            raise ObserverTransportError(
                "game PID did not change after cold restart"
            )
        self.pid = current_pid

    def __enter__(self) -> "AdbObserverBridge":
        return self.open()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.close()

    def request(self, request_line: str) -> Mapping[str, Any]:
        if self.transport is None:
            raise ObserverTransportError("ADB observer bridge is not open")
        return self.transport.request(request_line)

    def foreground_component(self) -> str:
        output = self._run(
            ("shell", "dumpsys", "activity", "activities"),
            timeout_seconds=max(self.command_timeout_seconds, 30.0),
        )
        match = self._FOREGROUND_PATTERN.search(output)
        return match.group(1) if match else ""

    def package_pid(self) -> Optional[int]:
        """Return the exact package PID, or ``None`` when it is not running."""

        pid_text = self._run(
            ("shell", "pidof", self.package),
            timeout_seconds=self._PACKAGE_PROCESS_TIMEOUT_SECONDS,
        )
        if not pid_text:
            return None
        if not pid_text.isdigit():
            raise ObserverTransportError("expected exactly one numeric game PID")
        return int(pid_text)

    def tap(self, x: float, y: float) -> None:
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in (x, y)):
            raise ValueError("typed tap point must contain finite numbers")
        # Keep down and up separated for the Unity input loop. Both endpoints
        # remain the caller's single reviewed point; this introduces no drag.
        self._run(("shell", "input", "swipe", str(x), str(y), str(x), str(y), "100"))

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int,
    ) -> None:
        self._run(
            (
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration_ms),
            )
        )

    @classmethod
    def _device_path(cls, value: str, field: str) -> str:
        path = value.strip()
        if not cls._DEVICE_PATH_PATTERN.fullmatch(path):
            raise SemanticGateClosed(
                "unsafe or malformed device path: {0}".format(field)
            )
        return path

    def _device_sha256(
        self,
        path: str,
        *,
        timeout_seconds: float = 120.0,
        max_attempts: Optional[int] = None,
    ) -> str:
        safe_path = self._device_path(path, "sha256 target")
        # The pinned base APK is large enough that hashing it on an emulator can
        # legitimately exceed the normal short ADB command timeout.  A just
        # cold-started emulator can additionally starve the first shell child;
        # retry only this read-only, exact-path hash once.  There is no cache or
        # fallback value: both package hashes must still match the allowlist.
        attempts = (
            self._DEVICE_SHA256_MAX_ATTEMPTS
            if max_attempts is None
            else max_attempts
        )
        if isinstance(attempts, bool) or not isinstance(attempts, int) or attempts <= 0:
            raise ValueError("device sha256 attempts must be a positive integer")
        for attempt in range(attempts):
            try:
                output = self._run(
                    ("shell", "sha256sum", safe_path),
                    timeout_seconds=timeout_seconds,
                )
                break
            except ObserverTransportError:
                if attempt + 1 == attempts:
                    raise
                time.sleep(self._DEVICE_SHA256_RETRY_DELAY_SECONDS)
        match = self._SHA256_PATTERN.match(output)
        if match is None:
            raise SemanticGateClosed("device sha256 output is malformed")
        return match.group(1).lower()

    def package_fingerprint(self) -> AndroidPackageFingerprint:
        """Read the installed game identity without trusting observer output."""

        identity_timeout = max(
            self.command_timeout_seconds,
            self._PACKAGE_IDENTITY_TIMEOUT_SECONDS,
        )
        package_dump = self._run(
            ("shell", "dumpsys", "package", self.package),
            timeout_seconds=identity_timeout,
        )
        version_code_match = re.search(r"\bversionCode=(\d+)", package_dump)
        version_name_match = re.search(r"\bversionName=([^\r\n]+)", package_dump)
        primary_abi_match = re.search(r"\bprimaryCpuAbi=([^\r\n]+)", package_dump)
        native_dir_match = re.search(
            r"\b(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\r\n]+)",
            package_dump,
        )
        if not all(
            (
                version_code_match,
                version_name_match,
                primary_abi_match,
                native_dir_match,
            )
        ):
            raise SemanticGateClosed("installed package identity is incomplete")

        base_output = self._run(
            ("shell", "pm", "path", self.package),
            timeout_seconds=identity_timeout,
        )
        base_paths = [
            line[len("package:") :]
            for line in base_output.splitlines()
            if line.startswith("package:")
        ]
        if len(base_paths) != 1:
            raise SemanticGateClosed("expected exactly one base APK path")
        base_path = self._device_path(base_paths[0], "base APK")
        native_dir = self._device_path(native_dir_match.group(1), "nativeLibraryDir")
        il2cpp_output = self._run(
            (
                "shell",
                "find",
                native_dir,
                "-type",
                "f",
                "-name",
                "libil2cpp.so",
                "-print",
            ),
            timeout_seconds=identity_timeout,
        )
        il2cpp_paths = [
            line.strip() for line in il2cpp_output.splitlines() if line.strip()
        ]
        if len(il2cpp_paths) != 1:
            raise SemanticGateClosed("expected exactly one libil2cpp.so")
        il2cpp_path = self._device_path(il2cpp_paths[0], "libil2cpp.so")

        return AndroidPackageFingerprint(
            version_name=version_name_match.group(1).strip(),
            version_code=int(version_code_match.group(1)),
            primary_abi=primary_abi_match.group(1).strip(),
            # The pinned APK is currently 1.73 GB.  On a cold AVD disk its
            # sequential read can exceed two separate 120-second attempts;
            # one continuous bounded pass preserves progress and exactness.
            base_apk_sha256=self._device_sha256(
                base_path,
                timeout_seconds=480.0,
                max_attempts=1,
            ),
            il2cpp_sha256=self._device_sha256(il2cpp_path),
        )

    def require_package_compatibility(
        self,
        required_primary_abi: str = "x86_64",
    ) -> Mapping[str, Any]:
        """Prove only the package shape required to attempt semantic startup.

        Game versions and file hashes are deliberately not allowlisted here.
        An updated client is allowed to start and the observer/mapping contracts
        report concrete incompatibilities if they are actually encountered.
        """

        if not isinstance(required_primary_abi, str) or not required_primary_abi:
            raise ValueError("required package ABI is missing")
        identity_timeout = max(
            self.command_timeout_seconds,
            self._PACKAGE_IDENTITY_TIMEOUT_SECONDS,
        )
        package_dump = self._run(
            ("shell", "dumpsys", "package", self.package),
            timeout_seconds=identity_timeout,
        )
        version_code_match = re.search(r"\bversionCode=(\d+)", package_dump)
        version_name_match = re.search(r"\bversionName=([^\r\n]+)", package_dump)
        primary_abi_match = re.search(r"\bprimaryCpuAbi=([^\r\n]+)", package_dump)
        native_dir_match = re.search(
            r"\b(?:legacyNativeLibraryDir|nativeLibraryDir)=([^\r\n]+)",
            package_dump,
        )
        if not all(
            (
                version_code_match,
                version_name_match,
                primary_abi_match,
                native_dir_match,
            )
        ):
            raise SemanticGateClosed("installed package identity is incomplete")
        primary_abi = primary_abi_match.group(1).strip()
        if primary_abi != required_primary_abi:
            raise SemanticGateClosed("installed package ABI is unsupported")

        path_output = self._run(
            ("shell", "pm", "path", self.package),
            timeout_seconds=identity_timeout,
        )
        package_paths = [
            self._device_path(line[len("package:") :], "package APK")
            for line in path_output.splitlines()
            if line.startswith("package:")
        ]
        base_paths = [path for path in package_paths if path.endswith("/base.apk")]
        if len(base_paths) != 1:
            raise SemanticGateClosed("expected exactly one base APK path")

        native_dir = self._device_path(native_dir_match.group(1), "nativeLibraryDir")
        il2cpp_output = self._run(
            (
                "shell",
                "find",
                native_dir,
                "-type",
                "f",
                "-name",
                "libil2cpp.so",
                "-print",
            ),
            timeout_seconds=identity_timeout,
        )
        il2cpp_paths = [
            self._device_path(line.strip(), "libil2cpp.so")
            for line in il2cpp_output.splitlines()
            if line.strip()
        ]
        if len(il2cpp_paths) != 1:
            raise SemanticGateClosed("expected exactly one libil2cpp.so")
        return {
            "version_name": version_name_match.group(1).strip(),
            "version_code": int(version_code_match.group(1)),
            "primary_abi": primary_abi,
            "base_apk_path": base_paths[0],
            "il2cpp_path": il2cpp_paths[0],
        }

    def require_package_fingerprint(
        self, expected: AndroidPackageFingerprint
    ) -> AndroidPackageFingerprint:
        actual = self.package_fingerprint()
        if actual != expected:
            raise SemanticGateClosed("installed package fingerprint is not allowlisted")
        return actual
