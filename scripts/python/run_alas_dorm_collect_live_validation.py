#!/usr/bin/env python3
"""Verify one real original-ALAS dorm quick-collect transition."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _adb(serial: str, *arguments: str) -> str:
    completed = subprocess.run(
        ("adb", "-s", serial, *arguments),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=90,
    )
    return completed.stdout.strip()


def _load_modules(alas_root: Path, driver_revision: str) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    os.environ["ALAS_SEMANTIC_DORM_COLLECT_BUDGET"] = "1"
    for path in (ROOT / "python", alas_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.config.config import name_to_function

    return SimpleNamespace(
        AzurLaneAutoScript=AzurLaneAutoScript,
        name_to_function=name_to_function,
    )


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _dorm_snapshot(serial: str, driver_revision: str) -> Mapping[str, Any]:
    from alas_headless import AlasSemanticSession

    with AlasSemanticSession(serial=serial, driver_revision=driver_revision) as adapter:
        oracle = adapter.oracle
        actions: list[str] = []
        if not oracle.enabled("dorm/page/manage"):
            if oracle.exists("dorm/page/manage"):
                # A proven empty-food modal leaves the owned CourtYard page
                # mounted underneath it.  The loop below closes only that
                # exact modal before taking the typed dorm snapshot.
                pass
            elif oracle.enabled("dorm-menu/dorm"):
                entry = oracle.click("dorm-menu/dorm")
                actions.append(entry.semantic_id)
            elif oracle.main_page_visible():
                entry = oracle.click("main/live")
                actions.append(entry.semantic_id)
                oracle.wait_for(
                    "dorm-menu/dorm", 15, minimum_generation=entry.generation
                )
                entry = oracle.click("dorm-menu/dorm")
                actions.append(entry.semantic_id)
            else:
                raise AssertionError("dorm snapshot cannot prove main or dorm page")

            deadline = time.monotonic() + 25
            while not oracle.enabled("dorm/page/manage"):
                if oracle.enabled("dorm/empty-food/cancel"):
                    cancel = oracle.click("dorm/empty-food/cancel")
                    actions.append(cancel.semantic_id)
                    continue
                if time.monotonic() >= deadline:
                    raise AssertionError("dorm page did not mount")
                time.sleep(0.25)

        state = oracle.dorm_state()
        snapshot = {
            "actions": actions,
            "state": asdict(state),
            "quick_collect_available": oracle.enabled("dorm/collect"),
        }
        if oracle.enabled("dorm/page/back"):
            cleanup = oracle.click("dorm/page/back")
            actions.append(cleanup.semantic_id)
            oracle.wait_for("main/task", 15, minimum_generation=cleanup.generation)
        if not oracle.main_page_visible():
            raise AssertionError("dorm snapshot cleanup did not restore main page")
        snapshot["cleanup"] = {"actions": actions, "main": True}
        return snapshot


def validate(*, alas_root: Path, seed_config: str, driver_revision: str) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not isinstance(serial, str) or not serial:
        raise AssertionError("seed config has no emulator serial")
    if not isinstance(package, str) or not package:
        raise AssertionError("seed config has no package")
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    before = _dorm_snapshot(serial, driver_revision)
    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Dorm"]["Scheduler"]["Enable"] = False
    payload["Dorm"]["Dorm"].update({"Collect": True, "Feed": False})
    payload["Dorm"]["BuyFurniture"]["Enable"] = False
    config_name = "codex_dorm_collect_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    result: dict[str, Any] = {"passed": False, "before": before}
    instance: object | None = None
    adapter: object | None = None
    dispatches: list[dict[str, Any]] = []
    prior_budget = os.environ.get("ALAS_SEMANTIC_DORM_COLLECT_BUDGET")
    try:
        if not before["quick_collect_available"]:
            raise AssertionError("dorm quick collect is not available before task")
        modules = _load_modules(alas_root, driver_revision)
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Dorm")
        instance.config.task = modules.name_to_function("Dorm")
        adapter = instance.device.semantic_adapter.open()
        original_dispatch = adapter._dispatch_mutation

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            dispatches.append(
                {
                    "capability": capability,
                    "semantic_id": getattr(receipt, "semantic_id", None),
                    "generation": getattr(receipt, "generation", None),
                    "path": getattr(receipt, "path", None),
                }
            )
            return receipt

        adapter._dispatch_mutation = record_dispatch
        started = time.monotonic()
        result["task_result"] = instance.run("dorm")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["dispatches"] = dispatches
        result["dorm_collect_grant_remaining"] = adapter._action_ledger.remaining(
            "dorm.collect"
        )
        if result["task_result"] is not True:
            raise AssertionError("original ALAS Dorm task did not return success")
        if len(dispatches) != 1 or dispatches[0]["capability"] != "dorm.collect" or dispatches[0]["semantic_id"] != "dorm/collect":
            raise AssertionError("dorm task did not issue exactly one typed quick collect")
        if result["dorm_collect_grant_remaining"] != 0:
            raise AssertionError("dorm task did not exhaust its quick-collect grant")
        instance.device.semantic_adapter.close()
        instance.device.semantic_adapter = None
        after = _dorm_snapshot(serial, driver_revision)
        result["after"] = after
        if after["state"]["occupied_slots"] != before["state"]["occupied_slots"]:
            raise AssertionError("dorm task changed the typed occupied-slot state")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        result["dispatches"] = dispatches
        if adapter is not None:
            result["dorm_collect_grant_remaining"] = adapter._action_ledger.remaining(
                "dorm.collect"
            )
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        if prior_budget is None:
            os.environ.pop("ALAS_SEMANTIC_DORM_COLLECT_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_DORM_COLLECT_BUDGET"] = prior_budget

    return {
        "schema": "alas-headless.dorm-collect-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {"Dorm.Collect": True, "Dorm.Feed": False},
        "source_sha256": {
            "dorm": _sha256(alas_root / "module" / "dorm" / "dorm.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    result = validate(
        alas_root=arguments.alas_root.resolve(),
        seed_config=arguments.seed_config,
        driver_revision=arguments.driver_revision,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
