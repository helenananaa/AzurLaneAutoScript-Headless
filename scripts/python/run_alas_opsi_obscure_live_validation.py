#!/usr/bin/env python3
"""Run a bounded, instrumented original-ALAS OpsiObscure task."""

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

from alas_headless import SemanticGateClosed


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _storage_snapshot(adapter: Any) -> dict[str, Any]:
    adapter.refresh_frame()
    state = adapter.operation_siren_storage_state()
    return {
        "generation": state.generation,
        "obscure_count": state.obscure_count,
        "abyssal_count": state.abyssal_count,
        "sample_count": state.sample_count,
        "items": [
            {
                "item_id": item.item_id,
                "item_type": item.item_type,
                "display_name": item.display_name,
                "count": item.count,
                "actionable": item.actionable,
            }
            for item in state.items
        ],
    }


def validate(
    alas_root: Path,
    seed_config: str,
    driver_revision: str,
    *,
    force_run: bool,
    fleet: int,
    submarine: bool,
    use_logger: bool,
    coordinate_budget: int,
    probe_only: bool,
    map_probe_only: bool,
    order_confirm_probe: str | None,
    order_confirm_cancel: str | None,
    resume_current_zone: bool,
) -> Mapping[str, Any]:
    seed_path = alas_root / "config" / f"{seed_config}.json"
    seed = _read(seed_path)
    serial = seed["Alas"]["Emulator"]["Serial"]
    package = seed["Alas"]["Emulator"]["PackageName"]
    pid = subprocess.run(
        ("adb", "-s", serial, "shell", "pidof", package),
        check=True, capture_output=True, text=True, timeout=90,
    ).stdout.strip()
    if not pid:
        raise RuntimeError("game package is not running")

    payload = copy.deepcopy(seed)
    for group in payload.values():
        if isinstance(group, dict):
            scheduler = group.get("Scheduler")
            if isinstance(scheduler, dict) and "Enable" in scheduler:
                scheduler["Enable"] = False
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["OpsiObscure"]["Scheduler"].update(
        {"Enable": False, "NextRun": "2020-01-01 00:00:00"}
    )
    payload["OpsiObscure"]["OpsiObscure"]["ForceRun"] = force_run
    payload["OpsiObscure"]["OpsiFleet"].update(
        {"Fleet": fleet, "Submarine": submarine}
    )
    payload["OpsiGeneral"]["OpsiGeneral"]["UseLogger"] = use_logger
    config_name = "codex_opsi_obscure_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / f"{config_name}.json"
    _write(config_path, payload)

    result: dict[str, Any] = {
        "schema": "alas-headless.operation-siren-obscure-live-qualification/v1",
        "serial": serial,
        "package": package,
        "pid": int(pid),
        "driver_revision": driver_revision,
        "seed_config": seed_config,
        "seed_config_sha256": _sha(seed_path),
        "configured": {
            "ForceRun": force_run,
            "Fleet": fleet,
            "Submarine": submarine,
            "UseLogger": use_logger,
            "coordinate_budget": coordinate_budget,
            "probe_only": probe_only,
            "map_probe_only": map_probe_only,
            "order_confirm_probe": order_confirm_probe,
            "order_confirm_cancel": order_confirm_cancel,
            "resume_current_zone": resume_current_zone,
        },
        "storage_snapshots": [],
        "checkout_results": [],
        "checkout_prompt_diagnostics": [],
        "fleet_actions": [],
        "order_actions": [],
        "auto_searches": [],
        "map_exits": [],
        "obscure_exit_steps": [],
        "post_search_loot_dismissals": [],
        "after_auto_search": [],
        "task_switch_checks": 0,
    }
    instance = None
    originals: dict[str, Any] = {}
    previous = {
        name: os.environ.get(name)
        for name in (
            "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS",
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
            "ALAS_SEMANTIC_OPSI_COORDINATE_CHECKOUT_BUDGET",
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
                "ALAS_SEMANTIC_OPSI_COORDINATE_CHECKOUT_BUDGET": str(coordinate_budget),
            }
        )
        sys.path.insert(0, str(alas_root))
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.base.timer import Timer
        from module.config.config import AzurLaneConfig, name_to_function
        from module.os.map import OSMap
        from module.os.tasks.obscure import OpsiObscure
        from module.os_handler.storage import StorageHandler

        instance = AzurLaneAutoScript(config_name)
        task_name = name_to_function("OpsiObscure")
        instance.config.task = task_name
        instance.config.bind(task_name)

        if order_confirm_cancel is not None:
            adapter = instance.device.semantic_adapter
            adapter.refresh_frame()
            receipt = adapter.open().oracle.click_operation_siren_order_confirmation(
                order_confirm_cancel, confirm=False
            )
            result["order_confirmation_cancel"] = {
                "semantic_id": receipt.semantic_id,
                "generation": receipt.generation,
            }
            result["task_result"] = True
        elif order_confirm_probe is not None:
            from module.os_handler.assets import ORDER_SCAN, ORDER_SUBMARINE

            task = OpsiObscure(config=instance.config, device=instance.device)
            task.order_enter()
            button = (
                ORDER_SCAN if order_confirm_probe == "scan" else ORDER_SUBMARINE
            )
            if not task.appear_then_click(button, interval=0):
                raise RuntimeError(
                    f"{order_confirm_probe} order is not actionable"
                )
            time.sleep(1.0)
            adapter = instance.device.semantic_adapter
            adapter.refresh_frame()
            oracle = adapter.open().oracle
            button_state = oracle.read_state()
            text_state = oracle.read_text_state()
            result["order_confirmation_ui"] = {
                "button_generation": button_state.generation,
                "text_generation": text_state.generation,
                "buttons": [
                    {
                        "path": item.path,
                        "name": item.name,
                        "active_in_hierarchy": item.active_in_hierarchy,
                        "active_and_enabled": item.active_and_enabled,
                        "interactable": item.interactable,
                    }
                    for item in button_state.buttons
                    if "SVOrderPanel" in item.path or "Msgbox" in item.path
                ],
                "texts": [
                    {
                        "path": item.path,
                        "text": item.text,
                        "active_in_hierarchy": item.active_in_hierarchy,
                        "active_and_enabled": item.active_and_enabled,
                        "truncated": item.truncated,
                    }
                    for item in text_state.texts
                    if "SVOrderPanel" in item.path or "Msgbox" in item.path
                ],
            }
            result["task_result"] = True
        elif map_probe_only:
            adapter = instance.device.semantic_adapter
            adapter.refresh_frame()
            oracle = adapter.open().oracle
            ui_state = oracle.read_ui_state()
            button_state = oracle.read_state()
            text_state = oracle.read_text_state()
            result["map_ui"] = {
                "generation": ui_state.generation,
                "method_mask": ui_state.method_mask,
                "skipped_count": ui_state.skipped_count,
                "image_truncated": ui_state.image_truncated,
                "image_source_count": ui_state.image_source_count,
                "image_source_capacity": ui_state.image_source_capacity,
                "images": [
                    {
                        "path": item.path,
                        "name": item.name,
                        "sprite": item.sprite,
                        "anchor_world_position": item.raw.get(
                            "anchor_world_position"
                        ),
                        "bounds": None if item.bounds is None else [
                            item.bounds.left, item.bounds.top,
                            item.bounds.right, item.bounds.bottom,
                        ],
                    }
                    for item in ui_state.images
                    if item.active_in_hierarchy
                    and item.active_and_enabled
                    and (
                        "/LevelGrid/" in item.path
                        or "/compass_panel/" in item.path
                    )
                ],
                "buttons": [
                    {"path": item.path, "name": item.name}
                    for item in button_state.buttons
                    if item.active_in_hierarchy and (
                        "/LevelGrid/" in item.path
                        or "SVOrderPanel" in item.path
                        or "Msgbox" in item.path
                    )
                ],
                "texts": [
                    {"path": item.path, "text": item.text}
                    for item in text_state.texts
                    if item.active_in_hierarchy and (
                        "SVOrderPanel" in item.path
                        or "Msgbox" in item.path
                        or "LevelOrigin/top" in item.path
                    )
                ],
            }
            result["task_result"] = True
        elif probe_only:
            task = OpsiObscure(config=instance.config, device=instance.device)
            task.storage_enter()
            adapter = task.device.semantic_adapter
            result["storage_snapshots"].append(_storage_snapshot(adapter))
            task.storage_quit()
            result["task_result"] = True
        else:
            for owner, name in (
                (StorageHandler, "storage_checkout_item"),
                (OSMap, "fleet_set"),
                (OSMap, "os_order_execute"),
                (OSMap, "run_auto_search"),
                (OSMap, "map_exit"),
                (OSMap, "handle_after_auto_search"),
            ):
                originals[name] = getattr(owner, name)
            originals["check_task_switch"] = AzurLaneConfig.check_task_switch
            semantic_session = instance.device.semantic_adapter
            originals["click_post_search_loot_back"] = (
                semantic_session.click_operation_siren_post_search_loot_back
            )

            def observed_post_search_loot_back():
                receipt = originals["click_post_search_loot_back"]()
                result["post_search_loot_dismissals"].append({
                    "semantic_id": receipt.semantic_id,
                    "path": receipt.path,
                })
                return receipt

            semantic_session.click_operation_siren_post_search_loot_back = (
                observed_post_search_loot_back
            )

            def observed_checkout(task, item, *args, **kwargs):
                adapter = task.device.semantic_adapter
                before = _storage_snapshot(adapter)
                result["storage_snapshots"].append(before)
                started = time.monotonic()
                original_prompt = (
                    adapter.operation_siren_storage_checkout_prompt_visible
                )

                def observed_prompt():
                    returned = original_prompt()
                    if not returned and len(result["checkout_prompt_diagnostics"]) < 4:
                        oracle = adapter.open().oracle
                        buttons = oracle.read_state()
                        ui = oracle.read_ui_state()
                        result["checkout_prompt_diagnostics"].append({
                            "generation": ui.generation,
                            "buttons": [
                                {
                                    "path": entry.path,
                                    "name": entry.name,
                                    "active": entry.active_in_hierarchy,
                                    "enabled": entry.active_and_enabled,
                                    "interactable": entry.interactable,
                                }
                                for entry in buttons.buttons
                                if "Msgbox" in entry.path
                            ],
                            "texts": [
                                {"path": entry.path, "text": entry.text}
                                for entry in ui.texts
                                if "Msgbox" in entry.path
                            ],
                        })
                    return returned

                adapter.operation_siren_storage_checkout_prompt_visible = (
                    observed_prompt
                )
                try:
                    returned = originals["storage_checkout_item"](
                        task, item, *args, **kwargs
                    )
                finally:
                    adapter.operation_siren_storage_checkout_prompt_visible = (
                        original_prompt
                    )
                result["checkout_results"].append({
                    "item": item,
                    "available_before": before["obscure_count"],
                    "returned": returned,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                })
                return returned

            def observed_fleet(task, value, *args, **kwargs):
                returned = originals["fleet_set"](task, value, *args, **kwargs)
                result["fleet_actions"].append({"requested": value, "returned": returned})
                return returned

            def observed_order(task, *args, **kwargs):
                returned = originals["os_order_execute"](task, *args, **kwargs)
                result["order_actions"].append({
                    "recon_scan": kwargs.get("recon_scan"),
                    "submarine_call": kwargs.get("submarine_call"),
                    "returned": returned,
                })
                return returned

            def observed_auto_search(task, *args, **kwargs):
                started = time.monotonic()
                returned = originals["run_auto_search"](task, *args, **kwargs)
                result["auto_searches"].append({
                    "rescan": kwargs.get("rescan"),
                    "finished_combat": returned,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                })
                return returned

            def observed_map_exit(task, *args, **kwargs):
                returned = originals["map_exit"](task, *args, **kwargs)
                result["map_exits"].append({"returned": returned})
                return returned

            def observed_after(task, *args, **kwargs):
                returned = originals["handle_after_auto_search"](task, *args, **kwargs)
                result["after_auto_search"].append({"returned": returned})
                return returned

            def observed_switch(config, message=""):
                result["task_switch_checks"] += 1
                return None

            StorageHandler.storage_checkout_item = observed_checkout
            OSMap.fleet_set = observed_fleet
            OSMap.os_order_execute = observed_order
            OSMap.run_auto_search = observed_auto_search
            OSMap.map_exit = observed_map_exit
            OSMap.handle_after_auto_search = observed_after
            AzurLaneConfig.check_task_switch = observed_switch

            started = time.monotonic()
            if resume_current_zone:
                task = OpsiObscure(
                    config=instance.config, device=instance.device
                )
                if task.is_in_map_order():
                    task.order_quit()
                task.zone_init()
                semantic_session = task.device.semantic_adapter
                if semantic_session.operation_siren_post_search_loot_visible():
                    semantic_session.click_operation_siren_post_search_loot_back()
                    for _ in range(20):
                        time.sleep(0.25)
                        semantic_session.refresh_frame()
                        if not semantic_session.operation_siren_post_search_loot_visible():
                            break
                    else:
                        raise RuntimeError(
                            "post-search loot overlay did not close"
                        )
                passage = (
                    semantic_session
                    .operation_siren_obscure_exit_passage_position()
                )
                if not task.is_in_special_zone() and passage is None:
                    raise RuntimeError("current zone is not an exact special zone")
                if passage is None:
                    task.fleet_set(fleet)
                    task.os_order_execute(
                        recon_scan=True, submarine_call=submarine
                    )
                    task.run_auto_search(rescan=False)
                task.handle_os_map_fleet_lock(enable=False)
                for _ in range(8):
                    try:
                        receipt = (
                            semantic_session
                            .click_operation_siren_obscure_exit_passage()
                        )
                    except SemanticGateClosed as exc:
                        if "outside safe view" not in str(exc):
                            raise
                        swipe = (
                            semantic_session
                            .operation_siren_obscure_exit_camera_swipe()
                        )
                        result["obscure_exit_steps"].append({
                            "semantic_id": swipe.semantic_id,
                            "start": list(swipe.start),
                            "end": list(swipe.end),
                        })
                        continue
                    result["obscure_exit_steps"].append({
                        "semantic_id": receipt.semantic_id,
                    })
                    task.wait_until_walk_stable(
                        confirm_timer=Timer(1.5, count=4),
                        walk_out_of_step=False,
                    )
                    semantic_session.refresh_frame()
                    if task.is_in_special_zone():
                        break
                else:
                    raise RuntimeError("obscure exit passage did not mount exit")
                task.map_exit()
                task.handle_after_auto_search()
                result["task_result"] = True
            else:
                result["task_result"] = instance.run("opsi_obscure")
            result["elapsed_seconds"] = round(time.monotonic() - started, 3)
            result["final_config"] = {"NextRun": str(instance.config.Scheduler_NextRun)}

        errors = []
        if not any((
            map_probe_only,
            order_confirm_probe,
            order_confirm_cancel,
            resume_current_zone,
        )) and not result["storage_snapshots"]:
            errors.append("typed storage state was not observed")
        if probe_only and any(
            result[key] for key in ("checkout_results", "fleet_actions", "order_actions", "auto_searches")
        ):
            errors.append("probe-only mode performed task actions")
        if not probe_only and result["checkout_results"]:
            checkout = result["checkout_results"][0]
            entered = bool(checkout["returned"])
            downstream = all(
                result[key]
                for key in ("fleet_actions", "order_actions", "auto_searches", "map_exits", "after_auto_search")
            )
            if entered != downstream:
                errors.append("coordinate checkout and downstream clear chain disagree")
        result["validation_errors"] = errors
        result["passed"] = not errors and result.get("task_result") is True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["passed"] = False
    finally:
        if originals:
            from module.config.config import AzurLaneConfig
            from module.os.map import OSMap
            from module.os_handler.storage import StorageHandler

            StorageHandler.storage_checkout_item = originals["storage_checkout_item"]
            for name in ("fleet_set", "os_order_execute", "run_auto_search", "map_exit", "handle_after_auto_search"):
                setattr(OSMap, name, originals[name])
            AzurLaneConfig.check_task_switch = originals["check_task_switch"]
        if instance is not None:
            session = getattr(getattr(instance, "device", None), "__dict__", {}).get("semantic_adapter")
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
        "obscure_task": _sha(alas_root / "module" / "os" / "tasks" / "obscure.py"),
        "storage_handler": _sha(alas_root / "module" / "os_handler" / "storage.py"),
        "adapter": _sha(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
        "oracle": _sha(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--force-run", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--fleet", type=int, choices=(1, 2, 3, 4), default=1)
    parser.add_argument("--submarine", action="store_true")
    parser.add_argument("--use-logger", action="store_true")
    parser.add_argument("--coordinate-budget", type=int, default=0)
    parser.add_argument("--probe-only", action="store_true")
    parser.add_argument("--map-probe-only", action="store_true")
    parser.add_argument(
        "--order-confirm-probe", choices=("scan", "submarine")
    )
    parser.add_argument(
        "--order-confirm-cancel", choices=("scan", "submarine")
    )
    parser.add_argument("--resume-current-zone", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.coordinate_budget < 0:
        parser.error("--coordinate-budget must be non-negative")
    if sum(bool(value) for value in (
        args.probe_only, args.map_probe_only, args.order_confirm_probe,
        args.order_confirm_cancel, args.resume_current_zone,
    )) > 1:
        parser.error("probe modes are mutually exclusive")
    output = args.output.resolve()
    result = validate(
        args.alas_root.resolve(), args.seed_config, args.driver_revision,
        force_run=args.force_run, fleet=args.fleet, submarine=args.submarine,
        use_logger=args.use_logger, coordinate_budget=args.coordinate_budget,
        probe_only=args.probe_only, map_probe_only=args.map_probe_only,
        order_confirm_probe=args.order_confirm_probe,
        order_confirm_cancel=args.order_confirm_cancel,
        resume_current_zone=args.resume_current_zone,
    )
    _write(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
