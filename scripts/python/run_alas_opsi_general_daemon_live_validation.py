#!/usr/bin/env python3
"""Exercise bounded OpsiGeneral/OpsiDaemon typed runtime boundaries."""

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
from types import MethodType, SimpleNamespace
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import SemanticGateClosed


SCHEMA = "alas-headless.opsi-general-daemon-live/v1"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resource_snapshot(adapter: Any) -> dict[str, Any]:
    adapter.refresh_frame()
    state = adapter.open().oracle.operation_siren_state()
    try:
        hp = list(adapter.campaign_fleet_hp())
    except SemanticGateClosed as exc:
        hp = {"closed": str(exc)}
    try:
        needs_repair = list(adapter.operation_siren_need_repair())
    except SemanticGateClosed as exc:
        needs_repair = {"closed": str(exc)}
    return {
        "zone_name": state.zone_name,
        "coins": state.coins,
        "action_points": state.action_points,
        "action_point_capacity": state.action_point_capacity,
        "fleet_hp": hp,
        "needs_repair": needs_repair,
    }


def _action_point_ui(adapter: Any) -> dict[str, Any]:
    adapter.refresh_frame()
    oracle = adapter.open().oracle
    state = adapter.operation_siren_action_point_state()
    text_state = oracle.read_text_state()
    ui_state = oracle.read_ui_state()
    return {
        "generation": state.generation,
        "current": state.current,
        "item_counts": list(state.item_counts),
        "selected_index": state.selected_index,
        "oil_purchase_cost": state.oil_purchase_cost,
        "oil_purchase_points": state.oil_purchase_points,
        "oil_purchase_remaining": state.oil_purchase_remaining,
        "oil_purchase_limit": state.oil_purchase_limit,
        "texts": [
            {"path": item.path, "text": item.text}
            for item in text_state.texts
            if "WorldStaminaRecoverUI" in item.path
        ],
        "images": [
            {"path": item.path, "name": item.name, "sprite": item.sprite}
            for item in ui_state.images
            if "WorldStaminaRecoverUI" in item.path
        ],
    }


def _wait_action_point_closed(adapter: Any) -> None:
    for _ in range(24):
        adapter.refresh_frame()
        if not adapter.operation_siren_action_point_visible():
            return
        time.sleep(0.25)
    raise RuntimeError("action point panel did not close")


def _daemon_host(daemon_class: Any, config: Any, device: Any) -> Any:
    host = daemon_class(config=config, device=device)
    for name in (
        "is_combat_executing",
        "combat_appear",
        "handle_battle_status",
        "handle_map_event",
    ):
        setattr(host, name, MethodType(lambda self: False, host))
    host.appear_then_click = MethodType(
        lambda self, button, **kwargs: False,
        host,
    )
    host._nearest_object_click_timer = SimpleNamespace(
        reached=lambda: True,
        reset=lambda: None,
        clear=lambda: None,
    )
    return host


def validate(
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    *,
    consume: bool,
    consume_oil: bool,
) -> dict[str, Any]:
    seed_path = alas_root / "config" / f"{seed_config}.json"
    seed = _read(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    pid_text = subprocess.run(
        ("adb", "-s", serial, "shell", "pidof", package),
        check=True,
        capture_output=True,
        text=True,
        timeout=90,
    ).stdout.strip()
    if not pid_text:
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    for group in payload.values():
        if isinstance(group, dict):
            scheduler = group.get("Scheduler")
            if isinstance(scheduler, dict) and "Enable" in scheduler:
                scheduler["Enable"] = False
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    config_name = "codex_opsi_general_daemon_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)

    result: dict[str, Any] = {
        "schema": SCHEMA,
        "serial": serial,
        "package": package,
        "pid": int(pid_text),
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha256(seed_path),
        "consume_authorized": consume or consume_oil,
        "consume_kind": "oil" if consume_oil else ("box" if consume else "none"),
        "budgets": {
            "operation_siren.action_point_use": int(consume or consume_oil),
            "operation_siren.port_repair": int(consume or consume_oil),
            "operation_siren.daemon_move": int(consume or consume_oil),
        },
        "typed_actions": [],
        "daemon_cases": {},
    }
    instance = None
    previous_cwd = Path.cwd()
    environment_names = (
        "ALAS_SEMANTIC_ADB",
        "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
        "ALAS_SEMANTIC_DRIVER_REVISION",
        "ALAS_SEMANTIC_MODE",
        "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS",
        "ALAS_SEMANTIC_OPSI_ACTION_POINT_USE_BUDGET",
        "ALAS_SEMANTIC_OPSI_DAEMON_MOVE_BUDGET",
        "ALAS_SEMANTIC_OPSI_PORT_REPAIR_BUDGET",
    )
    previous_environment = {
        name: os.environ.get(name) for name in environment_names
    }
    try:
        os.environ.update(
            {
                "ALAS_SEMANTIC_MODE": "1",
                "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
                "ALAS_SEMANTIC_ADB": "adb",
                "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
                "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS": "60000",
                "ALAS_SEMANTIC_OPSI_ACTION_POINT_USE_BUDGET": str(
                    int(consume or consume_oil)
                ),
                "ALAS_SEMANTIC_OPSI_DAEMON_MOVE_BUDGET": str(
                    int(consume or consume_oil)
                ),
                "ALAS_SEMANTIC_OPSI_PORT_REPAIR_BUDGET": str(
                    int(consume or consume_oil)
                ),
            }
        )
        sys.path.insert(0, str(alas_root))
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function
        from module.daemon.os_daemon import AzurLaneDaemon
        from module.os.tasks.obscure import OpsiObscure
        from module.os_handler.assets import PORT_ENTER

        instance = AzurLaneAutoScript(config_name)
        task_name = name_to_function("OpsiObscure")
        instance.config.task = task_name
        instance.config.bind(task_name)
        task = OpsiObscure(config=instance.config, device=instance.device)
        started = time.monotonic()
        adapter = instance.device.semantic_adapter
        adapter.refresh_frame()
        if adapter.operation_siren_action_point_visible():
            adapter.click_operation_siren_action_point_control(False)
            _wait_action_point_closed(adapter)
            adapter.refresh_frame()
        if adapter.open().oracle.operation_siren_local_map_visible():
            result["os_init"] = "already-local-map"
        else:
            task.os_init()
            result["os_init"] = "original-os-init"
        result["before"] = _resource_snapshot(adapter)
        result["port_visible"] = bool(task.appear(PORT_ENTER, offset=(20, 20)))
        try:
            target = adapter.operation_siren_nearest_daemon_target()
            result["daemon_target"] = None if target is None else {
                "generation": target.generation,
                "target_kind": target.target_kind,
                "source_position": list(target.source_position),
                "relative_position": list(target.relative_position),
            }
        except SemanticGateClosed as exc:
            result["daemon_target"] = {"closed": str(exc)}

        task.action_point_enter()
        result["action_point_before"] = _action_point_ui(adapter)
        action_point_before = adapter.operation_siren_action_point_state()
        if action_point_before.selected_index != 0:
            adapter.click_operation_siren_action_point_item(0)
            result["action_point_oil_selection"] = _action_point_ui(adapter)
            adapter.click_operation_siren_action_point_item(
                action_point_before.selected_index
            )
        else:
            result["action_point_oil_selection"] = result["action_point_before"]
        if consume_oil:
            oil_state = adapter.operation_siren_action_point_state()
            if oil_state.selected_index != 0:
                adapter.click_operation_siren_action_point_item(0)
                oil_state = adapter.operation_siren_action_point_state()
            if (
                oil_state.oil_purchase_remaining is None
                or oil_state.oil_purchase_remaining <= 0
                or oil_state.oil_purchase_cost is None
                or oil_state.item_counts[0] < oil_state.oil_purchase_cost + 1000
            ):
                raise RuntimeError("no bounded oil purchase trigger is available")
            task.config.override(
                OpsiGeneral_BuyActionPointLimit=(
                    oil_state.oil_purchase_limit
                    - oil_state.oil_purchase_remaining
                    + 1
                ),
                OpsiGeneral_OilLimit=1000,
                OS_ACTION_POINT_BOX_USE=True,
                OS_ACTION_POINT_PRESERVE=0,
            )
            returned = task.handle_action_point(
                zone=None,
                pinned=None,
                cost=oil_state.current + 100,
                keep_current_ap=False,
            )
            _wait_action_point_closed(adapter)
            task.action_point_enter()
            after_ui = _action_point_ui(adapter)
            if (
                after_ui["current"]
                != oil_state.current + oil_state.oil_purchase_points
                or after_ui["item_counts"][0]
                != oil_state.item_counts[0] - oil_state.oil_purchase_cost
                or after_ui["oil_purchase_remaining"]
                != oil_state.oil_purchase_remaining - 1
            ):
                raise RuntimeError("oil purchase postcondition drifted")
            result["action_point_use"] = {
                "attempted": True,
                "kind": "oil",
                "returned": returned,
                "before": {
                    "current": oil_state.current,
                    "item_counts": list(oil_state.item_counts),
                    "oil_purchase_cost": oil_state.oil_purchase_cost,
                    "oil_purchase_points": oil_state.oil_purchase_points,
                    "oil_purchase_remaining": oil_state.oil_purchase_remaining,
                    "oil_purchase_limit": oil_state.oil_purchase_limit,
                },
                "after": after_ui,
            }
            result["typed_actions"].append("operation_siren.action_point_use")
            adapter.click_operation_siren_action_point_control(False)
        elif (
            consume
            and action_point_before.current <= 180
            and any(action_point_before.item_counts[index] for index in (1, 2, 3))
        ):
            task.config.override(
                OS_ACTION_POINT_BOX_USE=True,
                OS_ACTION_POINT_PRESERVE=0,
            )
            returned = task.handle_action_point(
                zone=None,
                pinned=None,
                cost=action_point_before.current + 1,
                keep_current_ap=False,
            )
            _wait_action_point_closed(adapter)
            task.action_point_enter()
            result["action_point_use"] = {
                "attempted": True,
                "kind": "box",
                "returned": returned,
                "after": _action_point_ui(adapter),
            }
            result["typed_actions"].append("operation_siren.action_point_use")
            adapter.click_operation_siren_action_point_control(False)
        else:
            result["action_point_use"] = {
                "attempted": False,
                "reason": "not-authorized-or-no-safe-under-cap-box-trigger",
            }
            adapter.click_operation_siren_action_point_control(False)

        instance.config.override(
            OpsiDaemon_RepairShip=True,
            OpsiDaemon_SelectEnemy=False,
        )
        repair_host = _daemon_host(
            AzurLaneDaemon, instance.config, instance.device
        )
        original_repair = adapter.click_operation_siren_port_repair

        def observed_repair(confirm):
            receipt = original_repair(confirm)
            if receipt.capability_id is not None:
                result["typed_actions"].append(receipt.capability_id)
            return receipt

        adapter.click_operation_siren_port_repair = observed_repair
        try:
            repair_result = repair_host.run_once()
            result["daemon_cases"]["repair"] = {
                "result": repair_result,
                "closed": None,
            }
        except SemanticGateClosed as exc:
            result["daemon_cases"]["repair"] = {
                "result": None,
                "closed": str(exc),
            }
        finally:
            adapter.click_operation_siren_port_repair = original_repair

        instance.config.override(
            OpsiDaemon_RepairShip=False,
            OpsiDaemon_SelectEnemy=True,
        )
        select_host = _daemon_host(
            AzurLaneDaemon, instance.config, instance.device
        )
        original_move = adapter.click_operation_siren_daemon_target

        def observed_move(target):
            receipt = original_move(target)
            result["typed_actions"].append(receipt.capability_id)
            return receipt

        adapter.click_operation_siren_daemon_target = observed_move
        try:
            select_result = select_host.run_once()
            result["daemon_cases"]["select_enemy"] = {
                "result": select_result,
                "closed": None,
            }
        except SemanticGateClosed as exc:
            result["daemon_cases"]["select_enemy"] = {
                "result": None,
                "closed": str(exc),
            }
        finally:
            adapter.click_operation_siren_daemon_target = original_move

        time.sleep(1.0)
        result["after"] = _resource_snapshot(adapter)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["pixel_access_rejections"] = [
            {
                "operation": record.operation.value,
                "consumer": record.consumer,
            }
            for record in adapter.pixel_access_records()
        ]
        result["passed"] = True
    except BaseException as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["passed"] = False
    finally:
        if instance is not None:
            try:
                instance.device.semantic_adapter.close()
            except Exception:
                pass
        if config_path.exists():
            config_path.unlink()
        os.chdir(previous_cwd)
        if str(alas_root) in sys.path:
            sys.path.remove(str(alas_root))
        for name, value in previous_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--consume", action="store_true")
    parser.add_argument("--consume-oil", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = validate(
        args.alas_root.resolve(),
        args.seed_config,
        args.driver_revision,
        consume=args.consume,
        consume_oil=args.consume_oil,
    )
    if args.output is not None:
        _write((ROOT / args.output).resolve(), result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
