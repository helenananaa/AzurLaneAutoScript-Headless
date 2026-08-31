#!/usr/bin/env python3
"""Validate Daemon.EnterMap through a reversible typed 1-1 preparation flow."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


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


def validate(
    *, alas_root: Path, seed_config: str, driver_revision: str
) -> Mapping[str, Any]:
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
    config_name = "codex_daemon_enter_map_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    prior_cwd = Path.cwd()
    prior_env = {
        key: os.environ.get(key)
        for key in (
            "ALAS_SEMANTIC_MODE",
            "ALAS_SEMANTIC_DRIVER_REVISION",
            "ALAS_SEMANTIC_ADB",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET",
        )
    }
    os.environ.update(
        {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
            "ALAS_SEMANTIC_ADB": "adb",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": "1",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": "0",
        }
    )
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    instance: object | None = None
    result: dict[str, Any] = {"passed": False, "temporary_config": config_path.name}
    try:
        os.chdir(alas_root)
        from alas_headless import SemanticGateClosed
        from module.campaign.assets import CHAPTER_PREV
        from module.daemon.daemon import AzurLaneDaemon
        from module.map.map_operation import MAP_PREPARATION_CANCEL

        instance = AzurLaneDaemon(config_name, task="Daemon")
        session = instance.device.semantic_adapter
        adapter = session.open()
        if not adapter.oracle.main_page_visible():
            raise SemanticGateClosed("Daemon EnterMap validation requires main page")

        taps: list[list[int]] = []
        dispatches: list[str] = []
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
        adapter.begin_campaign_pre_sortie("1-1", mode="normal")
        try:
            instance.config.override(
                Campaign_Name="1-1",
                Campaign_Event="campaign_main",
                Campaign_Mode="normal",
            )
            instance.ui_goto_campaign()
            chapter_inputs = 0
            for _ in range(20):
                chapter_state = adapter.oracle.campaign_page_state()
                if any(stage.stage_code == "1-1" for stage in chapter_state.stages):
                    break
                numeric = tuple(
                    int(stage.stage_code.split("-", 1)[0])
                    for stage in chapter_state.stages
                    if "-" in stage.stage_code
                )
                if not numeric or min(numeric) <= 1:
                    raise SemanticGateClosed("1-1 is not reachable by chapter previous")
                previous_generation = chapter_state.generation
                instance.device.click(CHAPTER_PREV)
                chapter_inputs += 1

                def chapter_advanced() -> object:
                    current = adapter.oracle.campaign_page_state()
                    if current.generation <= previous_generation:
                        raise SemanticGateClosed("campaign chapter did not advance")
                    return current

                adapter.oracle._retry_transition_read(
                    chapter_advanced, attempts=40, interval_seconds=0.2
                )
            else:
                raise SemanticGateClosed("1-1 chapter navigation exceeded its bound")
            entrance = copy.copy(instance.ENTRANCE)
            entrance.name = "1-1"
            entrance.semantic_campaign_stage_code = "1-1"
            oil_before = adapter.oracle.campaign_oil()
            instance.device.click(entrance)
            map_state = adapter.oracle._retry_transition_read(
                lambda: adapter.oracle.campaign_map_preparation_state("1-1"),
                attempts=60,
                interval_seconds=0.2,
            )
            taps_before_daemon = len(taps)
            outcome = instance.run_once()
            daemon_tap_count = len(taps) - taps_before_daemon
            fleet_state = adapter.oracle._retry_transition_read(
                lambda: adapter.oracle.campaign_fleet_preparation_state("1-1"),
                attempts=60,
                interval_seconds=0.2,
            )
            instance.device.click(MAP_PREPARATION_CANCEL)
            proof = adapter.oracle._retry_transition_read(
                adapter.confirm_campaign_pre_sortie,
                attempts=60,
                interval_seconds=0.2,
            )
            oil_after = adapter.oracle.campaign_oil()
        finally:
            adapter.end_campaign_pre_sortie()

        pid_after = _adb(serial, "shell", "pidof", package)
        if outcome != "map_preparation":
            raise AssertionError("Daemon did not own the map-preparation branch")
        if oil_after != oil_before:
            raise AssertionError("reversible Daemon preparation changed oil")
        if pid_after != pid_before:
            raise AssertionError("game PID changed during Daemon EnterMap validation")
        if dispatches != ["campaign.stage_entry"]:
            raise AssertionError("Daemon EnterMap used an unexpected mutation capability")
        if daemon_tap_count != 1:
            raise AssertionError("Daemon map-preparation branch did not use one typed tap")
        result.update(
            {
                "passed": True,
                "outcome": outcome,
                "pid_before": pid_before,
                "pid_after": pid_after,
                "oil_before": oil_before,
                "oil_after": oil_after,
                "map_preparation": asdict(map_state),
                "fleet_preparation": asdict(fleet_state),
                "restoration_proof": asdict(proof),
                "typed_taps": taps,
                "chapter_navigation_taps": chapter_inputs,
                "daemon_branch_taps": daemon_tap_count,
                "mutation_dispatches": dispatches,
                "sortie_started": False,
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

    return {
        "schema": "alas-headless.daemon-enter-map-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {"Daemon.EnterMap": True, "stage": "1-1"},
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
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve() if args.output else None
    result = validate(
        alas_root=args.alas_root,
        seed_config=args.seed_config,
        driver_revision=args.driver_revision,
    )
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if output is not None:
        output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
