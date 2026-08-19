#!/usr/bin/env python3
"""Run the actual current Dorm furniture scheduler branch without spending gems."""

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


def _load_modules(
    alas_root: Path, driver_revision: str, *, shop_purchase_budget: int
) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    os.environ["ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET"] = str(shop_purchase_budget)
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


def validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    buy_option: str,
    expect_purchase: bool,
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

    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Dorm"]["Dorm"].update({"Collect": False, "Feed": False})
    payload["Dorm"]["BuyFurniture"].update(
        {
            "Enable": True,
            "BuyOption": buy_option,
            "LastRun": "2020-01-01 00:00:00",
        }
    )
    config_name = "codex_dorm_furniture_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (config_name + ".json")
    _write_json(config_path, payload)
    instance: object | None = None
    result: dict[str, Any] = {"temporary_config": config_path.name, "passed": False}
    try:
        modules = _load_modules(
            alas_root, driver_revision, shop_purchase_budget=1
        )
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Dorm")
        adapter = instance.device.semantic_adapter.open()
        if adapter.oracle.enabled("dorm/statistics/confirm"):
            adapter.oracle.click("dorm/statistics/confirm")
            time.sleep(0.75)
        if adapter.oracle.dorm_empty_food_cancel_available():
            adapter.oracle.click("dorm/empty-food/cancel")
            time.sleep(0.75)
        on_dorm_page = False
        if not adapter.oracle.main_page_visible():
            from alas_headless import SemanticGateClosed

            try:
                adapter.oracle.dorm_state()
                on_dorm_page = True
            except SemanticGateClosed:
                pass
        if not (adapter.oracle.main_page_visible() or on_dorm_page):
            raise AssertionError("Dorm validation must start on the main or dorm page")
        dispatches: list[dict[str, Any]] = []
        balances: list[dict[str, Any]] = []
        original_dispatch = adapter._dispatch_mutation
        original_balance = adapter.oracle.dorm_furniture_shop_balance

        def record_dispatch(capability: str, operation: object) -> object:
            receipt = original_dispatch(capability, operation)
            dispatches.append({"capability": capability, "receipt": _receipt(receipt)})
            return receipt

        adapter._dispatch_mutation = record_dispatch
        def record_balance() -> object:
            balance = original_balance()
            balances.append(
                {
                    "generation": balance.generation,
                    "dorm_coins": balance.dorm_coins,
                    "gems": balance.gems,
                }
            )
            return balance

        adapter.oracle.dorm_furniture_shop_balance = record_balance
        before_last_run = instance.config.BuyFurniture_LastRun
        started = time.monotonic()
        instance.dorm()
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        persisted = _read_json(config_path)
        after_last_run = persisted["Dorm"]["BuyFurniture"]["LastRun"]
        result["before_last_run"] = before_last_run.isoformat()
        result["after_last_run"] = after_last_run
        result["dispatches"] = dispatches
        result["balances"] = balances
        result["shop_purchase_grant_remaining"] = adapter._action_ledger.remaining(
            "shop.purchase"
        )
        if adapter.oracle.dorm_empty_food_cancel_available():
            result["empty_food_cleanup"] = _receipt(
                adapter.oracle.click("dorm/empty-food/cancel")
            )
            time.sleep(0.75)
        result["dorm_after_task"] = adapter.oracle.dorm_state().__dict__
        if after_last_run <= before_last_run.isoformat(sep=" "):
            raise AssertionError("BuyFurniture LastRun was not committed after the run")
        coin_values = [item["dorm_coins"] for item in balances]
        if expect_purchase:
            if (
                len(dispatches) != 1
                or dispatches[0]["capability"] != "shop.purchase"
                or dispatches[0]["receipt"]["semantic_id"]
                != "dorm/furniture/theme/purchase/gold"
            ):
                raise AssertionError(
                    "theme purchase did not consume one exact shop authority"
                )
            if result["shop_purchase_grant_remaining"] != 0:
                raise AssertionError(
                    "theme purchase did not exhaust its transaction budget"
                )
            if len(coin_values) < 2 or coin_values[-1] >= coin_values[0]:
                raise AssertionError("theme purchase did not prove a furniture-coin debit")
        else:
            if dispatches or result["shop_purchase_grant_remaining"] != 1:
                raise AssertionError(
                    "no-candidate boundary unexpectedly consumed transaction authority"
                )
            if coin_values and coin_values[-1] != coin_values[0]:
                raise AssertionError("no-candidate boundary changed furniture coins")
        cleanup = adapter.oracle.click("dorm/page/back")
        result["cleanup"] = _receipt(cleanup)
        time.sleep(0.75)
        result["main_page_visible_after_cleanup"] = adapter.oracle.main_page_visible()
        if not result["main_page_visible_after_cleanup"]:
            raise AssertionError("Dorm furniture cleanup did not restore the main page")
        result["passed"] = True
    finally:
        _close(instance)
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
    return {
        "schema": "alas-headless.dorm-furniture-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "source_sha256": {
            "buy_furniture": _sha256(alas_root / "module" / "dorm" / "buy_furniture.py"),
            "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
            "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
        },
        "configured": {
            "Dorm.Collect": False,
            "Dorm.Feed": False,
            "BuyFurniture.Enable": True,
            "BuyFurniture.BuyOption": buy_option,
        },
        "expect_purchase": expect_purchase,
        **result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--buy-option", choices=("set", "all"), required=True)
    parser.add_argument(
        "--expect-purchase", choices=("true", "false"), default="true"
    )
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    output = arguments.output.resolve()
    result: Mapping[str, Any] = {"passed": False}
    try:
        result = validate(
            alas_root=arguments.alas_root.resolve(),
            seed_config=arguments.seed_config,
            driver_revision=arguments.driver_revision,
            buy_option=arguments.buy_option,
            expect_purchase=arguments.expect_purchase == "true",
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
