#!/usr/bin/env python3
"""Observe one real OpSi shop inventory and compare the original ALAS presets."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless.adb_device import resolve_adb_serial


def run(args: argparse.Namespace) -> dict:
    alas_root = args.alas_root.resolve()
    seed = json.loads((alas_root / "config" / f"{args.seed_config}.json").read_text(encoding="utf-8"))
    serial = resolve_adb_serial("adb", args.serial)
    payload = copy.deepcopy(seed)
    payload["Alas"]["Emulator"]["Serial"] = serial
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["OpsiShop"]["Scheduler"].update({"Enable": False, "NextRun": "2020-01-01 00:00:00"})
    payload["OpsiShop"]["OpsiShop"].update({
        "PresetFilter": "all",
        "CustomFilter": "DevelopmentMaterialT2 > ActionPoint",
    })
    name = "_codex_opsi_shop_presets_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{name}.json"
    config_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    prior_cwd = Path.cwd()
    prior_env = {key: os.environ.get(key) for key in (
        "ALAS_SEMANTIC_MODE", "ALAS_SEMANTIC_DRIVER_REVISION", "ALAS_SEMANTIC_ADB",
        "ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET",
    )}
    os.environ.update({
        "ALAS_SEMANTIC_MODE": "1",
        "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
        "ALAS_SEMANTIC_ADB": "adb",
        "ALAS_SEMANTIC_SHOP_PURCHASE_BUDGET": "0",
    })
    sys.path.insert(0, str(alas_root))
    result = {"schema": "alas-headless.opsi-shop-presets-readonly/v1", "serial": serial,
              "driver_revision": args.driver_revision, "inventory": [], "presets": {},
              "custom_filter": payload["OpsiShop"]["OpsiShop"]["CustomFilter"],
              "purchase_budget": 0, "passed": False}
    instance = None
    original_filter = None
    original_buy = None
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.os_shop.selector import Selector
        from module.os_shop.shop import OSShop
        from module.config.config import name_to_function

        original_filter = Selector.items_filter_in_os_shop
        original_buy = OSShop.os_shop_buy_execute

        def refuse_purchase(*_args, **_kwargs):
            raise AssertionError("read-only preset probe reached purchase execution")

        def compare_presets(host, items):
            if result["inventory"]:
                raise AssertionError("unexpected second OpsiShop inventory scan")
            semantic = host.device.semantic_adapter
            records = semantic.operation_siren_shop_items()
            result["inventory_generation"] = records[0].generation
            result["ticket_balance"] = semantic.operation_siren_shop_currency()
            result["inventory"] = [
                {"name": item.name, "price": item.price, "currency": item.cost,
                 "remaining": item.count, "total": item.total_count}
                for item in items
            ]
            configured = host.config.OpsiShop_PresetFilter
            try:
                for preset in ("max_benefit", "max_benefit_meta", "no_meta", "all", "custom"):
                    host.config.OpsiShop_PresetFilter = preset
                    selected = original_filter(host, items)
                    result["presets"][preset] = [item.name for item in selected]
            finally:
                host.config.OpsiShop_PresetFilter = configured
            return []

        Selector.items_filter_in_os_shop = compare_presets
        OSShop.os_shop_buy_execute = refuse_purchase
        instance = AzurLaneAutoScript(name)
        task = name_to_function("OpsiShop")
        instance.config.task = task
        instance.config.bind(task)
        result["task_result"] = str(instance.run("opsi_shop"))
        if not result["inventory"] or len(result["presets"]) != 5:
            raise AssertionError("original OpsiShop did not compare one inventory across five presets")
        if result["presets"]["custom"]:
            raise AssertionError("custom filter unexpectedly admitted sold-out items")
        result["passed"] = True
        return result
    finally:
        if original_filter is not None:
            Selector.items_filter_in_os_shop = original_filter
        if original_buy is not None:
            OSShop.os_shop_buy_execute = original_buy
        if instance is not None:
            device = getattr(instance, "__dict__", {}).get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
        os.chdir(prior_cwd)
        config_path.unlink(missing_ok=True)
        for key, value in prior_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = run(args)
    except Exception as exc:
        result = {"schema": "alas-headless.opsi-shop-presets-readonly/v1",
                  "passed": False, "error": type(exc).__name__ + ": " + str(exc)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
