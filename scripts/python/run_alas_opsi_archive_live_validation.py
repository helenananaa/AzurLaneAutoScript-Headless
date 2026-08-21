#!/usr/bin/env python3
"""Run one bounded OpsiArchive purchase and archive-zone completion."""

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
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate(
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    transaction_budget: int,
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / f"{seed_config}.json"
    seed = _read(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    pid = subprocess.run(
        ("adb", "-s", serial, "shell", "pidof", package),
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    ).stdout.strip()
    if not pid:
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    for group in payload.values():
        if not isinstance(group, dict):
            continue
        scheduler = group.get("Scheduler")
        if isinstance(scheduler, dict) and "Enable" in scheduler:
            scheduler["Enable"] = False
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["OpsiExplore"]["Scheduler"]["Enable"] = False
    payload["OpsiArchive"]["Scheduler"].update(
        {"Enable": False, "NextRun": "2020-01-01 00:00:00"}
    )
    payload["OpsiArchive"]["OpsiFleet"].update(
        {"Fleet": 1, "Submarine": False}
    )
    config_name = "codex_opsi_archive_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.operation-siren-archive-live-qualification/v1",
        "serial": serial,
        "package": package,
        "pid": int(pid),
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha(seed_path),
        "configured": {"Fleet": 1, "Submarine": False},
        "transaction_budget": transaction_budget,
        "transactions": [],
        "mission_passes": [],
    }
    instance = None
    original_purchase = None
    original_finish = None
    original_task_switch = None
    previous = {
        name: os.environ.get(name)
        for name in (
            "ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET",
            "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS",
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
        )
    }
    try:
        os.environ.update(
            {
                "ALAS_SEMANTIC_MODE": "1",
                "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
                "ALAS_SEMANTIC_ADB": "adb",
                "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
                "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS": "60000",
                "ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET": str(transaction_budget),
            }
        )
        sys.path.insert(0, str(alas_root))
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from alas_headless.alas_adapter import AlasSemanticAdapter
        from module.config.config import name_to_function
        from module.config.config import AzurLaneConfig
        from module.os.tasks.daily import OpsiDaily

        original_purchase = (
            AlasSemanticAdapter.purchase_operation_siren_voucher_item_once
        )
        original_finish = OpsiDaily.os_finish_daily_mission
        original_task_switch = AzurLaneConfig.check_task_switch

        def observed_purchase(adapter, index, name, price, currency="Voucher"):
            before_items = adapter.oracle.operation_siren_voucher_items()
            before = next(item for item in before_items if item.index == index)
            balance_before = adapter.oracle.operation_siren_voucher_currency()
            receipt = original_purchase(adapter, index, name, price, currency)
            after_items = adapter.oracle.operation_siren_voucher_items()
            after = next(item for item in after_items if item.index == index)
            balance_after = adapter.oracle.operation_siren_voucher_currency()
            result["transactions"].append(
                {
                    "index": index,
                    "canonical_name": name,
                    "icon_sprite": before.icon_sprite,
                    "price": price,
                    "remaining_before": before.remaining,
                    "remaining_after": after.remaining,
                    "balance_before": balance_before,
                    "balance_after": balance_after,
                    "receipt": receipt.semantic_id,
                    "capability": receipt.capability_id,
                }
            )
            return receipt

        def observed_finish(task, *args, **kwargs):
            started = time.monotonic()
            transaction_count_before = len(result["transactions"])
            count = original_finish(task, *args, **kwargs)
            result["mission_passes"].append(
                {
                    "completed_count": count,
                    "transaction_count_before": transaction_count_before,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                }
            )
            return count

        AlasSemanticAdapter.purchase_operation_siren_voucher_item_once = (
            observed_purchase
        )
        OpsiDaily.os_finish_daily_mission = observed_finish
        AzurLaneConfig.check_task_switch = lambda self, message="": None
        instance = AzurLaneAutoScript(config_name)
        task = name_to_function("OpsiArchive")
        instance.config.task = task
        instance.config.bind(task)
        started = time.monotonic()
        result["task_result"] = instance.run("opsi_archive")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        validation_errors = []
        if len(result["transactions"]) != transaction_budget:
            validation_errors.append(
                "bounded OpsiArchive run did not use its exact logger budget"
            )
        elif transaction_budget == 1:
            tx = result["transactions"][0]
            if (
                not tx["canonical_name"].startswith("LoggerArchive")
                or tx["remaining_after"] != tx["remaining_before"] - 1
                or tx["balance_after"] != tx["balance_before"] - tx["price"]
                or tx["capability"] != "shop.purchase"
            ):
                validation_errors.append(
                    "OpsiArchive purchase postcondition is inconsistent"
                )
        archive_missions = sum(
            value["completed_count"]
            for value in result["mission_passes"]
            if transaction_budget == 0
            or value["transaction_count_before"] >= 1
        )
        if archive_missions < 1:
            validation_errors.append(
                "OpsiArchive did not complete its available archive mission chain"
            )
        result["validation_errors"] = validation_errors
        result["passed"] = not validation_errors
    except BaseException as exc:
        # Preserve any already-observed purchase and mission evidence when a
        # later live step fails.  The caller still exits non-zero via
        # ``passed=False``, but the receipt remains diagnostically useful.
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["passed"] = False
    finally:
        if original_purchase is not None:
            AlasSemanticAdapter.purchase_operation_siren_voucher_item_once = (
                original_purchase
            )
        if original_finish is not None:
            OpsiDaily.os_finish_daily_mission = original_finish
        if original_task_switch is not None:
            AzurLaneConfig.check_task_switch = original_task_switch
        if instance is not None:
            device = instance.__dict__.get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    result["source_sha256"] = {
        "archive_task": _sha(alas_root / "module" / "os" / "tasks" / "archive.py"),
        "map_event": _sha(alas_root / "module" / "os_handler" / "map_event.py"),
        "voucher_shop": _sha(alas_root / "module" / "shop" / "shop_voucher.py"),
        "adapter": _sha(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
        "oracle": _sha(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument(
        "--transaction-budget", type=int, choices=(0, 1), default=1
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result: Mapping[str, Any] = {"passed": False}
    try:
        result = validate(
            args.alas_root.resolve(),
            args.seed_config,
            args.driver_revision,
            args.transaction_budget,
        )
        return 0 if result.get("passed") is True else 1
    except BaseException as exc:
        result = {"passed": False, "error": type(exc).__name__ + ": " + str(exc)}
        raise
    finally:
        _write(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
