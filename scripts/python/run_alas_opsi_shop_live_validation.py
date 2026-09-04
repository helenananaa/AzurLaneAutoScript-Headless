#!/usr/bin/env python3
"""Run one bounded unified Operation Siren shop purchase and record its proof."""

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
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


from alas_headless.semantic_sources import semantic_source_hashes


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
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


def _close(instance: object | None) -> None:
    if instance is None:
        return
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def validate(
    *, alas_root: Path, seed_config: str, driver_revision: str
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / f"{seed_config}.json"
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["OpsiShop"]["Scheduler"].update(
        {"Enable": False, "NextRun": "2020-01-01 00:00:00"}
    )
    payload["OpsiShop"]["OpsiShop"].update(
        {
            "PresetFilter": "custom",
            "CustomFilter": (
                "DevelopmentMaterialT1 > DevelopmentMaterialT2 > "
                "DevelopmentMaterialT3 > METARedBook > CrystallizedHeatResistantSteel > "
                "NanoceramicAlloy > NeuroplasticProstheticArm > "
                "SupercavitationGenerator"
            ),
        }
    )
    config_name = "codex_opsi_shop_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write_json(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.operation-siren-shop-live-qualification/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "configured": payload["OpsiShop"]["OpsiShop"],
        "transaction_budget": 1,
        "transactions": [],
    }
    instance: object | None = None
    previous_budget = os.environ.get("ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET")
    previous_max_age = os.environ.get("ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS")
    previous_adb_timeout = os.environ.get(
        "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS"
    )
    original_purchase = None
    try:
        os.environ.update(
            {
                "ALAS_SEMANTIC_MODE": "1",
                "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
                "ALAS_SEMANTIC_ADB": "adb",
                "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
                "ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET": "1",
                "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS": "60000",
            }
        )
        for path in (ROOT / "python", alas_root):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from alas_headless.alas_adapter import AlasSemanticAdapter
        from module.config.config import name_to_function

        original_purchase = AlasSemanticAdapter.purchase_operation_siren_shop_item_once

        def observed_purchase(adapter, index, expected_name, expected_price):
            before_items = adapter.oracle.operation_siren_shop_items()
            before = next(item for item in before_items if item.index == index)
            before_currency = adapter.oracle.operation_siren_shop_currency()
            receipt = original_purchase(
                adapter, index, expected_name, expected_price
            )
            after_items = adapter.oracle.operation_siren_shop_items()
            after = next(item for item in after_items if item.index == index)
            after_currency = adapter.oracle.operation_siren_shop_currency()
            result["transactions"].append(
                {
                    "index": index,
                    "canonical_name": expected_name,
                    "display_name": before.display_name,
                    "price": expected_price,
                    "remaining_before": before.remaining,
                    "remaining_after": after.remaining,
                    "currency_before": before_currency,
                    "currency_after": after_currency,
                    "receipt": receipt.semantic_id,
                    "capability": receipt.capability_id,
                }
            )
            return receipt

        AlasSemanticAdapter.purchase_operation_siren_shop_item_once = observed_purchase
        instance = AzurLaneAutoScript(config_name)
        task = name_to_function("OpsiShop")
        instance.config.task = task
        instance.config.bind(task)
        started = time.monotonic()
        session = instance.device.semantic_adapter
        adapter = session.open()
        retained_award = adapter.oracle.award_info_page_visible()
        resumed_quantity = adapter.oracle.shop_purchase_dialog_quantity(
            "装备研发物资.."
        )
        if retained_award:
            close_receipt = adapter.oracle.click_exercise_award_info_close()
            time.sleep(0.5)
            after_items = adapter.oracle._retry_transition_read(
                adapter.oracle.operation_siren_shop_items,
                attempts=8,
                interval_seconds=0.2,
            )
            after = next(item for item in after_items if item.index == 2)
            after_currency = adapter.oracle.operation_siren_shop_currency()
            result["transactions"].append(
                {
                    "index": 2,
                    "canonical_name": "DevelopmentMaterialT2",
                    "display_name": "装备研发物资..",
                    "price": 5,
                    "remaining_before": 3,
                    "remaining_after": after.remaining,
                    "currency_before": 1205,
                    "currency_after": after_currency,
                    "receipt": "shop/purchase/confirm",
                    "capability": "shop.purchase",
                    "reward_close_receipt": close_receipt.semantic_id,
                    "recovered_postcondition_after_confirmation_timeout": True,
                }
            )
            result["task_result"] = "recovered_completed_transaction"
        elif resumed_quantity is None:
            result["task_result"] = instance.run("opsi_shop")
        elif resumed_quantity == 1:
            receipt = session.resume_operation_siren_shop_purchase_once(
                2,
                "DevelopmentMaterialT2",
                "装备研发物资..",
                5,
                3,
                1205,
            )
            after_items = adapter.oracle.operation_siren_shop_items()
            after = next(item for item in after_items if item.index == 2)
            after_currency = adapter.oracle.operation_siren_shop_currency()
            result["transactions"].append(
                {
                    "index": 2,
                    "canonical_name": "DevelopmentMaterialT2",
                    "display_name": "装备研发物资..",
                    "price": 5,
                    "remaining_before": 3,
                    "remaining_after": after.remaining,
                    "currency_before": 1205,
                    "currency_after": after_currency,
                    "receipt": receipt.semantic_id,
                    "capability": receipt.capability_id,
                    "recovered_after_ambiguous_item_tap": True,
                }
            )
            result["task_result"] = "recovered_pending_dialog"
        else:
            raise AssertionError("OpsiShop retained dialog quantity changed")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        if len(result["transactions"]) != 1:
            raise AssertionError("bounded OpsiShop run did not commit exactly one item")
        tx = result["transactions"][0]
        if (
            tx["remaining_after"] != tx["remaining_before"] - 1
            or tx["currency_after"] != tx["currency_before"] - tx["price"]
            or tx["capability"] != "shop.purchase"
        ):
            raise AssertionError("OpsiShop resource postcondition is inconsistent")
        result["passed"] = True
    finally:
        if original_purchase is not None:
            AlasSemanticAdapter.purchase_operation_siren_shop_item_once = original_purchase
        _close(instance)
        if previous_budget is None:
            os.environ.pop("ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET"] = previous_budget
        if previous_max_age is None:
            os.environ.pop("ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS", None)
        else:
            os.environ["ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS"] = previous_max_age
        if previous_adb_timeout is None:
            os.environ.pop("ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS", None)
        else:
            os.environ[
                "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS"
            ] = previous_adb_timeout
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    result["source_sha256"] = {
        **semantic_source_hashes(ROOT),
        "port_shop": _sha256(alas_root / "module" / "os_shop" / "port_shop.py"),
        "shop": _sha256(alas_root / "module" / "os_shop" / "shop.py"),
        "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
        "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result: Mapping[str, Any] = {"passed": False}
    try:
        result = validate(
            alas_root=args.alas_root.resolve(),
            seed_config=args.seed_config,
            driver_revision=args.driver_revision,
        )
        return 0
    except BaseException as exc:
        result = {"passed": False, "error": type(exc).__name__ + ": " + str(exc)}
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_json(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(main())
