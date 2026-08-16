#!/usr/bin/env python3
"""Run one original ALAS Reward mission-claim branch on the current client."""

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
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
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


def _load_modules(
    alas_root: Path,
    driver_revision: str,
    *,
    mission_claim_enabled: bool,
) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    os.environ["ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE"] = (
        "1" if mission_claim_enabled else "0"
    )
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


def _cleanup_to_main(serial: str) -> Mapping[str, Any]:
    """Use a fresh observer lease after ALAS releases its task frame."""

    from alas_headless.alas_adapter import AlasSemanticSession

    with AlasSemanticSession.from_environment(serial=serial) as session:
        oracle = session.oracle
        if oracle.exists("task/page/back"):
            cleanup = oracle.click("task/page/back")
            oracle.wait_for(
                "main/task", 15, minimum_generation=cleanup.generation
            )
            result: dict[str, Any] = {
                "semantic_id": cleanup.semantic_id,
                "generation": cleanup.generation,
                "path": cleanup.path,
            }
        else:
            result = {"semantic_id": None}
        result["main_page_visible"] = oracle.main_page_visible()
        if not result["main_page_visible"]:
            raise AssertionError("Reward mission cleanup did not restore the main page")
        return result


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    mode: str,
    mission_claim_enabled: bool,
) -> Mapping[str, Any]:
    if mode not in ("daily", "weekly"):
        raise ValueError("reward mission validation mode must be daily or weekly")
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

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Reward"]["Reward"].update(
        {
            "CollectOil": False,
            "CollectCoin": False,
            "CollectExp": False,
            "CollectMission": mode == "daily" and mission_claim_enabled,
            "CollectWeeklyMission": mode == "weekly" and mission_claim_enabled,
        }
    )
    config_name = "codex_reward_mission_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    instance: object | None = None
    result: dict[str, Any] = {"temporary_config": config_path.name, "passed": False}
    try:
        modules = _load_modules(
            alas_root,
            driver_revision,
            mission_claim_enabled=mission_claim_enabled,
        )
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Reward")
        adapter = instance.device.semantic_adapter.open()
        dispatches: list[dict[str, Any]] = []
        original_dispatch = adapter._dispatch_mutation

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            dispatches.append(
                {
                    "capability": capability,
                    "semantic_id": getattr(receipt, "semantic_id", None),
                    "generation": getattr(receipt, "generation", None),
                    "path": getattr(receipt, "path", None),
                    "policy_sha256": getattr(receipt, "policy_sha256", None),
                    "remaining_after_dispatch": getattr(
                        receipt, "remaining_after_dispatch", None
                    ),
                }
            )
            return receipt

        adapter._dispatch_mutation = record_dispatch
        started = time.monotonic()
        instance.reward()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["dispatches"] = dispatches
        result["mission_claim_grant_remaining"] = adapter._action_ledger.remaining(
            "mission.claim"
        )
        if mission_claim_enabled and (
            len(dispatches) != 1 or dispatches[0]["capability"] != "mission.claim"
        ):
            raise AssertionError("Reward mission run did not use exactly one claim grant")
        if not mission_claim_enabled and dispatches:
            raise AssertionError("disabled Reward mission claim dispatched a mutation")
        typed_claim_targets = {
            "daily": {
                "task/claim/all",
                "task/claim/row/0",
                "task/claim/row/1",
                "task/claim/row/2",
                "task/claim/row/3",
                "task/claim/row/4",
            },
            "weekly": {"task/weekly-progress/claim"},
        }
        if mission_claim_enabled and (
            dispatches[0]["semantic_id"] not in typed_claim_targets[mode]
        ):
            raise AssertionError("Reward mission run did not use a typed claim target")
        if result["mission_claim_grant_remaining"] != 0:
            raise AssertionError("Reward mission claim grant was not exhausted")
        semantic_session = instance.device.semantic_adapter
        semantic_session.close()
        instance.device.semantic_adapter = None
        result["cleanup"] = _cleanup_to_main(serial)
        result["main_page_visible_after_cleanup"] = result["cleanup"][
            "main_page_visible"
        ]
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
    return {
        "schema": "alas-headless.reward-mission-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "source_sha256": {
            "reward": _sha256(alas_root / "module" / "reward" / "reward.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
        },
        "configured": {
            "Reward.CollectOil": False,
            "Reward.CollectCoin": False,
            "Reward.CollectExp": False,
            "Reward.CollectMission": mode == "daily" and mission_claim_enabled,
            "Reward.CollectWeeklyMission": mode == "weekly" and mission_claim_enabled,
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--mode", choices=("daily", "weekly"), default="daily")
    parser.add_argument(
        "--mission-claim-enabled",
        choices=("true", "false"),
        default="true",
        help="set the selected mission-claim option explicitly",
    )
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    result = validate(
        alas_root=arguments.alas_root.resolve(),
        seed_config=arguments.seed_config,
        driver_revision=arguments.driver_revision,
        mode=arguments.mode,
        mission_claim_enabled=arguments.mission_claim_enabled == "true",
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
