#!/usr/bin/env python3
"""Run the original Freebies task across the remaining typed branches."""

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
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from alas_headless.semantic_sources import semantic_source_hashes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


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
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.config.config import name_to_function

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Freebies"]["Scheduler"]["Enable"] = False
    payload["Freebies"]["BattlePass"]["Collect"] = True
    payload["Freebies"]["DataKey"].update(
        {"Collect": True, "ForceCollect": False}
    )
    payload["Freebies"]["Mail"].update(
        {
            "ClaimMaintenance": False,
            "ClaimMerit": False,
            "ClaimTradeLicense": False,
            "DeleteCollected": False,
        }
    )
    payload["Freebies"]["SupplyPack"].update(
        {"Collect": True, "DayOfWeek": 0}
    )
    config_name = "codex_freebies_remaining_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    instance: object | None = None
    result: dict[str, Any] = {"passed": False}
    observations: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    try:
        instance = AzurLaneAutoScript(config_name)
        instance.config.bind("Freebies")
        instance.config.task = name_to_function("Freebies")
        oracle = instance.device.semantic_adapter.open().oracle

        def record_value(method: str) -> None:
            original = getattr(oracle, method)

            def wrapped() -> object:
                value = original()
                observations.append({"method": method, "value": value})
                return value

            setattr(oracle, method, wrapped)

        def record_action(method: str) -> None:
            original = getattr(oracle, method)

            def wrapped(*args: object, **kwargs: object) -> object:
                receipt = original(*args, **kwargs)
                actions.append(
                    {
                        "method": method,
                        "semantic_id": receipt.semantic_id,
                        "generation": receipt.generation,
                        "path": receipt.path,
                    }
                )
                return receipt

            setattr(oracle, method, wrapped)

        for method in (
            "battle_pass_reward_available",
            "war_archives_data_key_text",
            "war_archives_data_key_collected",
            "free_weekly_supply_pack_available",
            "shop_oil",
        ):
            record_value(method)
        for method in (
            "click_battle_pass_entrance",
            "click_battle_pass_claim_all",
            "click_war_archives_data_key_collect",
            "click_data_key_limit_choice",
            "click_free_weekly_supply_pack",
        ):
            record_action(method)

        started = time.monotonic()
        result["task_result"] = instance.run("freebies")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["observations"] = observations
        result["actions"] = actions
        result["scheduler_next_run"] = str(instance.config.Scheduler_NextRun)
        if result["task_result"] is not True:
            raise AssertionError("original ALAS Freebies task did not return success")
        if any(
            action["method"]
            in (
                "click_data_key_limit_choice",
                "click_free_weekly_supply_pack",
            )
            for action in actions
        ):
            raise AssertionError("unavailable remaining branch injected input")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        if instance is not None:
            device = getattr(instance, "__dict__", {}).get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    return {
        "schema": "alas-headless.freebies-remaining-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": {
            "BattlePass.Collect": True,
            "DataKey.Collect": True,
            "DataKey.ForceCollect": False,
            "Mail.*": False,
            "SupplyPack.Collect": True,
            "SupplyPack.DayOfWeek": 0,
        },
        "source_sha256": {
            **semantic_source_hashes(ROOT),
            "freebies": _sha256(alas_root / "module/freebies/freebies.py"),
            "battle_pass": _sha256(alas_root / "module/freebies/battle_pass.py"),
            "data_key": _sha256(alas_root / "module/freebies/data_key.py"),
            "supply_pack": _sha256(alas_root / "module/freebies/supply_pack.py"),
            "adapter": _sha256(ROOT / "python/alas_headless/alas_adapter.py"),
            "oracle": _sha256(ROOT / "python/alas_headless/semantic_oracle.py"),
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
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
