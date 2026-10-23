#!/usr/bin/env python3
"""Start an owned Mac AVD and collect bounded, zero-input development samples."""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import types
from pathlib import Path

_source_package = Path(__file__).resolve().parents[2] / "python" / "alas_headless"
if _source_package.is_dir() and "alas_headless" not in sys.modules:
    package = types.ModuleType("alas_headless")
    package.__path__ = [str(_source_package)]
    package.__package__ = "alas_headless"
    sys.modules["alas_headless"] = package

from alas_headless.runtime_backend_adb import RuntimeAwaitingUserLogin, RuntimeBackendError
from alas_headless.runtime_backend_macos_hvf import MacosHvfBackend
from alas_headless.runtime_backends import backend_from_config
from alas_headless.runtime_command import RuntimeCommandExecutor, RuntimeExecutionPolicy
from alas_headless.oracle.transport import AdbObserverBridge, request_observer_state


def observe(backend, instance):
    try:
        foreground = backend.wait_recovered_game_ready(instance, 1.0)
    except RuntimeAwaitingUserLogin:
        return {"state": "awaiting-user-login", "observer": None, "reentry": "return-to-unity-and-revalidate"}
    except RuntimeBackendError as exc:
        return {"state": exc.code, "observer": None}
    bridge = AdbObserverBridge(backend.serial, backend.package, adb=backend.adb,
                               adb_server_port=backend.adb_server_port, command_timeout_seconds=3.0)
    try:
        bridge.open()
        started = time.monotonic()
        snapshot, buttons, atomic = request_observer_state(bridge.request)
        elapsed = time.monotonic() - started
        # Raw diagnostic counters only: this never admits an input or ALAS task.
        identity_matches = snapshot.get("pid") == bridge.pid == foreground["pid"] and snapshot.get("package") == backend.package
        return {"state": "unity-foreground", "identity_matches": identity_matches,
                "observer": {key: snapshot.get(key) for key in (
                    "status", "pid", "generation", "age_ms", "main_thread")},
                "atomic": atomic, "buttons_generation": buttons.get("generation"),
                "request_ms": elapsed * 1000}
    except Exception as exc:
        return {"state": "observer-unavailable", "error_type": type(exc).__name__}
    finally:
        bridge.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, default=120)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args()
    if any(not math.isfinite(x) or x <= 0 for x in (args.duration, args.interval)):
        parser.error("duration and interval must be positive finite seconds")
    config = json.loads(args.config.read_text(encoding="utf-8"))
    backend = backend_from_config(config, RuntimeCommandExecutor(RuntimeExecutionPolicy(True, True)))
    if not isinstance(backend, MacosHvfBackend):
        parser.error("requires macos-hvf config")
    probe = backend.probe_host()
    if not probe.available:
        parser.error(probe.reason)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        def emit(value):
            output.write(json.dumps(value, sort_keys=True) + "\n")
            output.flush()

        instance = None
        started = time.monotonic()
        try:
            instance = backend.start({})
            backend.wait_adb(instance, 120)
            backend.wait_android_ready(instance, 120)
            try:
                backend.wait_game_ready(instance, 90)
                launch_state = "unity-foreground"
            except RuntimeAwaitingUserLogin:
                launch_state = "awaiting-user-login"
            emit({"event": "startup", "seconds": time.monotonic() - started,
                  "state": launch_state, "null_refresh_hz": backend.config.null_refresh_hz,
                  "scope": "development-prelogin-no-input"})
            deadline = time.monotonic() + args.duration
            while True:
                emit({"event": "sample", "elapsed_seconds": time.monotonic() - started,
                      "metrics": backend.collect_host_metrics(instance),
                      "game": observe(backend, instance)})
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(args.interval, remaining))
        finally:
            if instance is not None:
                backend.stop(instance)
                emit({"event": "cleanup", "owned_runtime_stopped": True})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
