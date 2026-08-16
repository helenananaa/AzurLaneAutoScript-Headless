#!/usr/bin/env python3
"""Run one resource-receipted, bounded ALAS Gacha task on the live client."""

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
POOL_INDEX = {"event": 0, "light": 1, "heavy": 2, "special": 3}

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


def _load_modules(alas_root: Path, driver_revision: str) -> SimpleNamespace:
    os.environ["ALAS_SEMANTIC_MODE"] = "1"
    os.environ["ALAS_SEMANTIC_DRIVER_REVISION"] = driver_revision
    os.environ["ALAS_SEMANTIC_ADB"] = "adb"
    if str(ROOT / "python") not in sys.path:
        sys.path.insert(0, str(ROOT / "python"))
    if str(alas_root) not in sys.path:
        sys.path.insert(0, str(alas_root))
    os.chdir(alas_root)
    from alas import AzurLaneAutoScript
    from module.config.config import name_to_function

    return SimpleNamespace(
        AzurLaneAutoScript=AzurLaneAutoScript,
        name_to_function=name_to_function,
    )


def _close(instance: object) -> None:
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


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


def _read_build_state(serial: str, driver_revision: str, pool: str) -> dict[str, Any]:
    from alas_headless import AlasSemanticSession, SemanticGateClosed

    session = AlasSemanticSession(serial=serial, driver_revision=driver_revision)
    adapter = None
    try:
        adapter = session.open()
        adapter.begin_build()
        if adapter.oracle.main_page_visible():
            adapter.click("MAIN_GOTO_BUILD")
            time.sleep(2)
        try:
            selected_pool = adapter.oracle.build_selected_pool().value
        except SemanticGateClosed:
            adapter.oracle.build_queue_timers()
            adapter.click("GACHA_SIDE_NAVBAR_0_0")
            time.sleep(1)
            selected_pool = adapter.oracle.build_selected_pool().value
        if selected_pool != pool:
            adapter.click("CONSTRUCT_BOTTOM_NAVBAR_{0}_0".format(POOL_INDEX[pool]))
            time.sleep(1)
            selected_pool = adapter.oracle.build_selected_pool().value
        costs = adapter.oracle.build_costs()
        coins = adapter.oracle.build_coins_owned()
        adapter.click("GACHA_SIDE_NAVBAR_0_1")
        time.sleep(1)
        timers = adapter.oracle.build_queue_timers()
        quick_counts = tuple(
            item
            for item in adapter.oracle.read_ui_state().texts
            if item.path.endswith("BuildShipDetailUI1(Clone)/quick_count/value")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and item.text.strip().isdigit()
        )
        if len(quick_counts) != 1:
            raise AssertionError("construction queue quick-item count is absent or ambiguous")
        return {
            "pool": selected_pool,
            "cubes_owned": costs.cubes_owned,
            "cubes_per_build": costs.cubes_per_build,
            "coins_owned": coins,
            "coins_per_build": costs.coins_per_build,
            "queue_timers": list(timers),
            "queue_empty": all(value == "99:99:99" for value in timers),
            "quick_items_owned": int(quick_counts[0].text.strip()),
        }
    finally:
        if adapter is not None:
            try:
                adapter.end_build()
            except Exception:
                pass
        session.close()


def _validate(
    *,
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    pool: str,
    amount: int,
    use_ticket: bool,
    use_drill: bool,
    output: Path,
) -> Mapping[str, Any]:
    if pool not in POOL_INDEX:
        raise ValueError("live construction pool is not a normal typed pool")
    if not 1 <= amount <= 10:
        raise ValueError("amount must be 1..10")
    if use_ticket:
        raise ValueError("this receipt is intentionally limited to cube/coin construction")
    seed_path = alas_root / "config" / f"{seed_config}.json"
    seed = _read_json(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    if not isinstance(serial, str) or not serial:
        raise AssertionError("seed config has no emulator serial")
    if not isinstance(package, str) or not package:
        raise AssertionError("seed config has no package")
    if not _adb(serial, "shell", "pidof", package):
        raise RuntimeError("game package is not running")

    before = _read_build_state(serial, driver_revision, pool)
    if not before["queue_empty"]:
        raise RuntimeError("live build queue is not empty before qualification")
    payload = copy.deepcopy(seed)
    payload["Alas"]["Error"].update(
        {
            "HandleError": False,
            "SaveError": False,
        }
    )
    payload["Gacha"]["Scheduler"]["Enable"] = False
    payload["Gacha"]["Gacha"].update(
        {
            "Pool": pool,
            "Amount": amount,
            "UseTicket": use_ticket,
            "UseDrill": use_drill,
        }
    )
    config_name = "codex_gacha_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write_json(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.gacha-live-validation/v1",
        "serial": serial,
        "package": package,
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "gacha": payload["Gacha"]["Gacha"],
        "before": before,
        "source_sha256": {
            "gacha_reward": _sha256(alas_root / "module" / "gacha" / "gacha_reward.py"),
            "args": _sha256(alas_root / "module" / "config" / "argument" / "args.json"),
        },
    }
    instance = None
    previous_budget = os.environ.get("ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET")
    try:
        os.environ["ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET"] = "2" if use_drill else "1"
        modules = _load_modules(alas_root, driver_revision)
        instance = modules.AzurLaneAutoScript(config_name)
        instance.config.bind("Gacha")
        instance.config.task = modules.name_to_function("Gacha")
        started = time.monotonic()
        result["task_result"] = instance.run("gacha")
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    finally:
        _close(instance) if instance is not None else None
        if previous_budget is None:
            os.environ.pop("ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET", None)
        else:
            os.environ["ALAS_SEMANTIC_BUILD_SUBMIT_BUDGET"] = previous_budget
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()

    after = _read_build_state(serial, driver_revision, pool)
    expected_cubes = before["cubes_per_build"] * amount
    expected_coins = before["coins_per_build"] * amount
    result["after"] = after
    result["resource_delta"] = {
        "cubes": before["cubes_owned"] - after["cubes_owned"],
        "coins": before["coins_owned"] - after["coins_owned"],
    }
    result["expected_resource_delta"] = {
        "cubes": expected_cubes,
        "coins": expected_coins,
    }
    result["queue_postcondition"] = {
        "empty_before": before["queue_empty"],
        "nonempty_after": not after["queue_empty"],
        "empty_after": after["queue_empty"],
        "timer_count": len(after["queue_timers"]),
    }
    result["quick_item_delta"] = (
        before["quick_items_owned"] - after["quick_items_owned"]
    )
    if result["task_result"] is not True:
        raise AssertionError("ALAS Gacha task did not return success")
    if result["resource_delta"] != result["expected_resource_delta"]:
        raise AssertionError("live Gacha resource delta differs from confirmed order")
    if not use_drill and not result["queue_postcondition"]["nonempty_after"]:
        raise AssertionError("submitted construction did not enter the live queue")
    if use_drill and not result["queue_postcondition"]["empty_after"]:
        raise AssertionError("drill-enabled construction did not return to an empty queue")
    if use_drill and result["quick_item_delta"] < 1:
        raise AssertionError("drill-enabled construction did not consume quick-finish tools")
    result["passed"] = True
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--pool", choices=tuple(POOL_INDEX), required=True)
    parser.add_argument("--amount", type=int, required=True)
    parser.add_argument("--use-drill", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result: Mapping[str, Any] = {"passed": False}
    try:
        result = _validate(
            alas_root=args.alas_root.resolve(),
            seed_config=args.seed_config,
            driver_revision=args.driver_revision,
            pool=args.pool,
            amount=args.amount,
            use_ticket=False,
            use_drill=args.use_drill,
            output=output,
        )
        return 0
    except BaseException as exc:
        result = {"passed": False, "error": f"{type(exc).__name__}: {exc}"}
        raise
    finally:
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_json(output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2), end="\n")


if __name__ == "__main__":
    raise SystemExit(main())
