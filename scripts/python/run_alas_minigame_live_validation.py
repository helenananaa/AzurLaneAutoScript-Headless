#!/usr/bin/env python3
"""Run one real ALAS Fushun minigame task with exactly one ticket grant."""

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
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from alas_headless.semantic_sources import semantic_source_hashes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
        encoding="utf-8",
    )


def _receipt(receipt: object) -> dict[str, Any]:
    return {
        "semantic_id": getattr(receipt, "semantic_id", None),
        "generation": getattr(receipt, "generation", None),
        "path": getattr(receipt, "path", None),
        "capability_id": getattr(receipt, "capability_id", None),
        "policy_sha256": getattr(receipt, "policy_sha256", None),
    }


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
    os.environ["ALAS_SEMANTIC_MINIGAME_PLAY_BUDGET"] = "1"
    for path in (ROOT / "python", alas_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript

    return SimpleNamespace(AzurLaneAutoScript=AzurLaneAutoScript)


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _main_visible(serial: str, driver_revision: str) -> bool:
    from alas_headless import AlasSemanticSession

    session = AlasSemanticSession(serial=serial, driver_revision=driver_revision)
    try:
        return session.open().oracle.main_page_visible()
    finally:
        session.close()


def validate(
    *, alas_root: Path, seed_config: str, driver_revision: str
) -> Mapping[str, Any]:
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
    if not _main_visible(serial, driver_revision):
        raise AssertionError("Minigame validation must start at the main page")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    config_name = "codex_minigame_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    instance: object | None = None
    result: dict[str, Any] = {
        "temporary_config": config_path.name,
        "passed": False,
    }
    try:
        modules = _load_modules(alas_root, driver_revision)
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Minigame")
        adapter = instance.device.semantic_adapter.open()
        dispatches: list[dict[str, Any]] = []
        original_dispatch = adapter._dispatch_mutation

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            dispatches.append({"capability": capability, "receipt": _receipt(receipt)})
            return receipt

        adapter._dispatch_mutation = record_dispatch
        started = time.monotonic()
        instance.minigame()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["game_room_after_task"] = adapter.oracle.game_room_page_visible()
        result["remaining_minigame_play_grant"] = adapter._action_ledger.remaining(
            "minigame.play"
        )
        result["dispatches"] = dispatches
        if not result["game_room_after_task"]:
            raise AssertionError("Minigame did not return to the game room")
        if result["remaining_minigame_play_grant"] != 0:
            raise AssertionError("Minigame did not consume exactly one ticket grant")
        if [item["capability"] for item in dispatches] != ["minigame.play"]:
            raise AssertionError("Minigame issued an unexpected mutation sequence")
        input_receipt = dispatches[0]["receipt"]
        if input_receipt["capability_id"] != "minigame.play":
            raise AssertionError("Minigame receipt is not authority-bound")
        cleanup = adapter.oracle.click("game-room/home")
        result["cleanup"] = _receipt(cleanup)
        time.sleep(0.75)
        result["passed"] = True
    finally:
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
    if not _main_visible(serial, driver_revision):
        raise AssertionError("Minigame cleanup did not restore the main page")
    return {
        "schema": "alas-headless.minigame-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "source_sha256": {
            **semantic_source_hashes(ROOT),
            "minigame": _sha256(alas_root / "module" / "minigame" / "minigame.py"),
            "new_year_challenge": _sha256(
                alas_root / "module" / "minigame" / "new_year_challenge.py"
            ),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
        },
        "ticket_grant": 1,
        "postcondition": {"main_page_visible_after_cleanup": True},
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
    result: Mapping[str, Any] = {"passed": False}
    try:
        result = validate(
            alas_root=arguments.alas_root.resolve(),
            seed_config=arguments.seed_config,
            driver_revision=arguments.driver_revision,
        )
        return 0
    except BaseException as exc:
        result = {"passed": False, "error": type(exc).__name__ + ": " + str(exc)}
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_json(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")


if __name__ == "__main__":
    raise SystemExit(main())
