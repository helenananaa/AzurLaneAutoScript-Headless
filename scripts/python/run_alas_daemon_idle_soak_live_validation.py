#!/usr/bin/env python3
"""Run the original ALAS Daemon polling loop on a typed main-page idle state."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: {0}".format(path))
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _adb(serial: str, *arguments: str) -> str:
    return subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    ).stdout.strip()


def _forwards(serial: str, package: str) -> list[str]:
    lines = subprocess.run(
        ("adb", "forward", "--list"),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    ).stdout.splitlines()
    return sorted(line for line in lines if serial in line or package in line)


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    duration_seconds: float,
    sample_interval_seconds: float,
) -> Mapping[str, Any]:
    if duration_seconds < 30:
        raise ValueError("duration_seconds must be at least 30")
    if not 0 <= sample_interval_seconds <= 5:
        raise ValueError("sample_interval_seconds must be between 0 and 5")
    alas_root = alas_root.resolve()
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    pid_before = _adb(serial, "shell", "pidof", package)
    if not pid_before:
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Daemon"]["Daemon"]["EnterMap"] = True
    config_name = "codex_daemon_idle_soak_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    prior_cwd = Path.cwd()
    prior_env = {
        key: os.environ.get(key)
        for key in (
            "ALAS_SEMANTIC_MODE",
            "ALAS_SEMANTIC_DRIVER_REVISION",
            "ALAS_SEMANTIC_ADB",
        )
    }
    os.environ.update(
        {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
            "ALAS_SEMANTIC_ADB": "adb",
        }
    )
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    instance: object | None = None
    result: dict[str, Any] = {
        "passed": False,
        "temporary_config": config_path.name,
        "started_at": _utc_now(),
    }
    forwards_before = _forwards(serial, package)
    try:
        os.chdir(alas_root)
        from alas_headless import SemanticGateClosed
        from module.daemon.daemon import AzurLaneDaemon
        from module.handler.login import LoginHandler

        instance = AzurLaneDaemon(config_name, task="Daemon")
        session = instance.device.semantic_adapter
        adapter = session.open()
        try:
            adapter.oracle.main_page_receipt()
        except SemanticGateClosed:
            if (
                adapter.oracle.enabled("login/enter")
                or adapter.oracle.login_update_download_available()
                or adapter.oracle.login_update_in_progress()
                or adapter.oracle.login_update_restart_prompt_available()
            ):
                LoginHandler(
                    config=instance.config, device=instance.device
                ).handle_app_login()
            elif adapter.oracle.enabled("meowfficer/page/back"):
                adapter.oracle.click("meowfficer/page/back")
                adapter.oracle._retry_transition_read(
                    adapter.oracle.main_page_receipt,
                    attempts=30,
                    interval_seconds=0.2,
                )
            else:
                instance.ui_goto_main()
        initial_page = adapter.oracle.main_page_receipt()
        initial_observer = adapter.oracle.read_state()

        taps: list[list[int]] = []
        dispatches: list[str] = []
        results: dict[str, int] = {}
        generations = [initial_observer.generation]
        original_tap = adapter.oracle._tap
        original_dispatch = adapter._dispatch_mutation

        def record_tap(x: int, y: int) -> None:
            taps.append([x, y])
            original_tap(x, y)

        def record_dispatch(capability: str, operation: object) -> object:
            dispatches.append(capability)
            return original_dispatch(capability, operation)

        adapter.oracle._tap = record_tap
        adapter._dispatch_mutation = record_dispatch
        deadline = time.monotonic() + duration_seconds
        iterations = 0
        while time.monotonic() < deadline:
            outcome = instance.run_once()
            results[outcome] = results.get(outcome, 0) + 1
            current = adapter.oracle.read_state()
            adapter.oracle.main_page_receipt()
            generations.append(current.generation)
            iterations += 1
            if sample_interval_seconds:
                time.sleep(sample_interval_seconds)

        final_page = adapter.oracle.main_page_receipt()
        final_observer = adapter.oracle.read_state()
        pid_after = _adb(serial, "shell", "pidof", package)
        if results != {"idle": iterations} or iterations < 2:
            raise AssertionError("Daemon soak left the exact idle branch")
        if taps or dispatches:
            raise AssertionError("idle Daemon soak unexpectedly injected input")
        if pid_after != pid_before:
            raise AssertionError("game PID changed during Daemon soak")
        if final_observer.generation <= initial_observer.generation:
            raise AssertionError("observer generation did not advance during Daemon soak")
        if any(later < earlier for earlier, later in zip(generations, generations[1:])):
            raise AssertionError("observer generation moved backwards during Daemon soak")
        result.update(
            {
                "passed": True,
                "finished_at": _utc_now(),
                "duration_seconds": duration_seconds,
                "iterations": iterations,
                "outcomes": results,
                "pid_before": pid_before,
                "pid_after": pid_after,
                "generation_before": initial_observer.generation,
                "generation_after": final_observer.generation,
                "unique_generation_samples": len(set(generations)),
                "main_page_before": asdict(initial_page),
                "main_page_after": asdict(final_page),
                "typed_taps": taps,
                "mutation_dispatches": dispatches,
            }
        )
    finally:
        if instance is not None:
            device = getattr(instance, "__dict__", {}).get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
        os.chdir(prior_cwd)
        for key, value in prior_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
    forwards_after = _forwards(serial, package)
    result["observer_forwards_before"] = forwards_before
    result["observer_forwards_after"] = forwards_after
    if forwards_after != forwards_before:
        raise AssertionError("Daemon soak leaked an observer forward")

    return {
        "schema": "alas-headless.daemon-idle-soak-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {"Daemon.EnterMap": True},
        **result,
        "source_sha256": {
            "daemon": _sha256(alas_root / "module" / "daemon" / "daemon.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "runner": _sha256(Path(__file__)),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--duration-seconds", type=float, default=180)
    parser.add_argument("--sample-interval-seconds", type=float, default=0.25)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve() if args.output else None
    result = validate(
        alas_root=args.alas_root,
        seed_config=args.seed_config,
        driver_revision=args.driver_revision,
        duration_seconds=args.duration_seconds,
        sample_interval_seconds=args.sample_interval_seconds,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output is not None:
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
