#!/usr/bin/env python3
"""Run the bounded original-ALAS Daily task against the live semantic adapter."""

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
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from alas_headless.semantic_sources import semantic_source_hashes


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _adb(serial: str, *args: str) -> str:
    return subprocess.run(
        ("adb", "-s", serial, *args), check=True, capture_output=True,
        text=True, encoding="utf-8", timeout=90,
    ).stdout.strip()


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    budget: int,
    remain_cap: int,
) -> Mapping[str, Any]:
    if remain_cap < 1:
        raise ValueError("remain_cap must be positive")
    seed_path = alas_root / "config" / (seed_config + ".json")
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Daily"]["Scheduler"]["Enable"] = False
    payload["Daily"]["Daily"].update({
        "UseDailySkip": False,
        "EscortMission": "skip",
        "AdvanceMission": "skip",
        "FierceAssault": "first",
        "FierceAssaultFleet": 1,
        "TacticalTraining": "second",
        "TacticalTrainingFleet": 2,
        "SupplyLineDisruption": "skip",
        "ModuleDevelopment": "skip",
        "EmergencyModuleDevelopment": "skip",
    })
    config_name = "codex_daily_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)

    prior = os.environ.get("ALAS_SEMANTIC_DAILY_EXECUTE_BUDGET")
    instance: object | None = None
    adapter: Any = None
    result: dict[str, Any] = {"passed": False}
    try:
        os.environ.update({
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
            "ALAS_SEMANTIC_ADB": "adb",
            "ALAS_SEMANTIC_DAILY_EXECUTE_BUDGET": str(budget),
        })
        for path in (ROOT / "python", alas_root):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function

        instance = AzurLaneAutoScript(config_name)
        instance.config.bind("Daily")
        instance.config.task = name_to_function("Daily")
        adapter = instance.device.semantic_adapter.open()
        read_live_remain = instance.device.semantic_adapter.daily_current_remain
        instance.device.semantic_adapter.daily_current_remain = (
            lambda: min(read_live_remain(), remain_cap)
        )
        if adapter.oracle.daily_precombat_visible():
            instance.device.semantic_adapter.click_daily_precombat_back()
            for _ in range(60):
                time.sleep(0.25)
                if adapter.oracle.daily_detail_visible():
                    break
            else:
                raise RuntimeError("Daily precombat did not return to detail")
        if adapter.oracle.daily_detail_visible():
            for attempt in range(60):
                if attempt % 12 == 0:
                    instance.device.semantic_adapter.click_daily_back()
                time.sleep(0.25)
                if (
                    adapter.oracle.daily_page_visible()
                    and not adapter.oracle.daily_detail_visible()
                ):
                    break
            else:
                raise RuntimeError("Daily detail did not return to overview")
        if adapter.oracle.daily_page_visible():
            instance.device.semantic_adapter.click_daily_back()
            for _ in range(60):
                time.sleep(0.25)
                if adapter.oracle.campaign_menu_is_entry():
                    break
            else:
                raise RuntimeError("Daily overview did not return to campaign menu")
            instance.device.semantic_adapter.refresh_frame()
            adapter.oracle.click_campaign_daily_entrance()
            for _ in range(60):
                time.sleep(0.25)
                if (
                    adapter.oracle.daily_page_visible()
                    and not adapter.oracle.daily_detail_visible()
                ):
                    break
            else:
                raise RuntimeError("campaign menu did not return to Daily overview")
        started = time.monotonic()
        result["task_result"] = instance.run("daily", skip_first_screenshot=True)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        receipts = adapter.daily_execution_receipts()
        result["execution_receipts"] = [asdict(item) for item in receipts]
        result["daily_grant_remaining"] = adapter._action_ledger.remaining("daily.execute")
        kinds = [item.semantic_id.split("/")[2] for item in receipts]
        if result["task_result"] is not True:
            raise AssertionError("original ALAS Daily task did not return success")
        if not 2 <= len(receipts) <= budget:
            raise AssertionError("Daily task did not stay within its bounded grant")
        if result["daily_grant_remaining"] != budget - len(receipts):
            raise AssertionError("Daily action ledger does not match its receipts")
        if set(kinds) != {"tactical_training", "fierce_assault"}:
            raise AssertionError("Daily task did not execute both configured challenge types")
        if any(
            ("/tactical_training/stage/2/fleet/2" not in item.semantic_id)
            if kind == "tactical_training"
            else ("/fierce_assault/stage/1/fleet/1" not in item.semantic_id)
            for item, kind in zip(receipts, kinds)
        ):
            raise AssertionError("Daily execution receipt differs from configured stage or fleet")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        if adapter is not None:
            result["execution_receipts"] = [asdict(item) for item in adapter.daily_execution_receipts()]
            result["daily_grant_remaining"] = adapter._action_ledger.remaining("daily.execute")
        if instance is not None:
            session = getattr(getattr(instance, "device", None), "semantic_adapter", None)
            if session is not None:
                session.close()
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        if prior is None:
            os.environ.pop("ALAS_SEMANTIC_DAILY_EXECUTE_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_DAILY_EXECUTE_BUDGET"] = prior

    return {
        "schema": "alas-headless.daily-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "configured": payload["Daily"]["Daily"],
        "budget": budget,
        "validation_remain_cap": remain_cap,
        "source_sha256": {
            **semantic_source_hashes(ROOT),
            "daily": _sha256(alas_root / "module" / "daily" / "daily.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
            "runner": _sha256(Path(__file__).resolve()),
        },
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--budget", type=int, default=6)
    parser.add_argument("--remain-cap", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result = validate(
        alas_root=args.alas_root.resolve(), seed_config=args.seed_config,
        driver_revision=args.driver_revision, budget=args.budget,
        remain_cap=args.remain_cap,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
