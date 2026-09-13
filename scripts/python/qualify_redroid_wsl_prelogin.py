#!/usr/bin/env python3
"""Exercise local Project lifecycle up to the empty SDK login boundary.

This is a qualification harness, not an ALAS login or task implementation.
It never inputs credentials or submits a login control.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from alas_headless.runtime_artifacts import RuntimeLock
from alas_headless.runtime_backends import backend_from_config, WslRedroidBackend, RuntimeBackendNotReady
from alas_headless.runtime_command import RuntimeCommandExecutor, RuntimeExecutionPolicy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute:
        parser.error("--execute is required for game and container restart qualification")
    args.output.mkdir(parents=True, exist_ok=False)
    config = json.loads(args.config.read_text(encoding="utf-8-sig"))
    lock = RuntimeLock.from_mapping(json.loads(args.lock.read_text(encoding="utf-8-sig")))
    backend = backend_from_config(config, RuntimeCommandExecutor(RuntimeExecutionPolicy(True, True)))
    if not isinstance(backend, WslRedroidBackend):
        parser.error("this harness requires the WSL Project backend")
    root = Path(__file__).resolve().parents[2]
    implementation_paths = (Path(__file__).resolve(), root / "python/alas_headless/runtime_backend_redroid_wsl.py",
        root / "scripts/windows/manage-redroid-wsl-local-dev.ps1", root / "scripts/wsl/manage-redroid-local-dev.sh")
    implementation_hashes = {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest() for path in implementation_paths}
    report = {"schema": "alas-headless.redroid-wsl-prelogin/v1", "scope": "local-wsl-project-prelogin-lifecycle",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(), "passed": False,
        "runtime_lock_sha256": lock.sha256, "cycles": [], "account_input_injected": False,
        "implementation_sha256": implementation_hashes,
        "gameplay_inputs": 0, "premium_currency_spent": False, "alas_workload_qualified": False}
    instance = None

    def checkpoint():
        (args.output / "manifest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def finish_cycle(name, started):
        observer = backend.wait_observer_ready(instance, 40)
        print(name + ": observer progressed " + str(observer), flush=True)
        report["cycles"].append({"name": name, "observer": observer})
        checkpoint()
        deadline = time.monotonic() + 90
        next_observation = time.monotonic() + 5
        while True:
            try:
                boundary = backend.inspect_login_boundary()
                break
            except RuntimeBackendNotReady as exc:
                if exc.code != "sdk-login-not-foreground" or time.monotonic() >= deadline:
                    raise
                if time.monotonic() >= next_observation:
                    try:
                        fresh = backend.wait_observer_ready(instance, 30)
                        report["cycles"][-1].setdefault("startup_observations", []).append(fresh)
                        print(name + ": startup observer " + str(fresh), flush=True)
                        checkpoint()
                    except RuntimeBackendNotReady as observer_exc:
                        if observer_exc.code != "observer-main-activity-not-foreground":
                            raise
                        # A native login transition is allowed only after its
                        # own exact empty-control inspection on the next pass.
                    next_observation = time.monotonic() + 5
                time.sleep(1)
        report["cycles"][-1].update(login_boundary=boundary, elapsed_seconds=round(time.monotonic() - started, 3))
        print(name + ": empty native login confirmed", flush=True)
        checkpoint()

    try:
        probe = backend.probe_host()
        if not probe.available:
            raise RuntimeBackendNotReady(probe.reason)
        report["host"] = dict(probe.host_fingerprint)
        artifacts = backend.resolve_artifacts(lock)
        provisioned = backend.provision(artifacts)
        instance = backend.start(provisioned)
        report["instance"] = dict(instance)
        backend.wait_adb(instance, 30)
        backend.wait_android_ready(instance, 60)
        # Refuse to disturb an account-bearing runtime in this account-free harness.
        report["initial_login_boundary"] = backend.inspect_login_boundary()
        started = time.monotonic()
        backend.wait_game_ready(instance, 60)
        finish_cycle("cold-start", started)
        started = time.monotonic()
        backend.restart_game(instance)
        backend.wait_recovered_game_ready(instance, 60)
        finish_cycle("game-restart", started)
        started = time.monotonic()
        backend.restart_android(instance)
        report["android_restart_boundary"] = dict(backend.wait_android_offline(instance, 30))
        backend.wait_adb(instance, 60)
        backend.wait_android_ready(instance, 90)
        backend.wait_game_ready(instance, 60)
        finish_cycle("android-restart", started)
        report["container_after"] = {key: backend._container_info().get(key) for key in ("Id", "Image", "Mounts", "State")}
        report["passed"] = True
    except Exception as exc:
        report["failure"] = {"type": type(exc).__name__, "code": getattr(exc, "code", str(exc))}
        print("FAIL: " + str(report["failure"]), flush=True)
    finally:
        if instance is not None:
            try:
                backend.stop(instance)
                report["cleanup_passed"] = True
            except Exception as exc:
                report["cleanup_passed"] = False
                report["cleanup_error"] = str(exc)
                report["passed"] = False
        report["implementation_unchanged_during_run"] = all(hashlib.sha256(path.read_bytes()).hexdigest() == implementation_hashes[str(path.relative_to(root))] for path in implementation_paths)
        if not report["implementation_unchanged_during_run"]:
            report["passed"] = False
        checkpoint()
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
