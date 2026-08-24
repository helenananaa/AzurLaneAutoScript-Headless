#!/usr/bin/env python3
"""Run one bounded Main-family task against the pinned semantic AVD."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
TASKS = ("Main", "Main2", "Main3")
SCHEMA = "alas-headless.main-task-live-validation/v1"
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless.adb_device import resolve_adb_serial  # noqa: E402


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _close_semantic_session(instance: object) -> None:
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _surface_visible(probe: Any) -> bool:
    try:
        return bool(probe())
    except Exception as exc:
        if exc.__class__.__name__ != "SemanticGateClosed":
            raise
        return False


def _configure(
    seed: Mapping[str, Any], *, task: str, stage: str, use_auto_search: bool,
    fleet_order: str
) -> dict[str, Any]:
    payload = copy.deepcopy(seed)
    target = payload[task]
    target["Scheduler"]["Command"] = task
    target["Scheduler"]["Enable"] = True
    target["Campaign"].update(
        {
            "Name": stage,
            "Event": "campaign_main",
            "Mode": "normal",
            "UseClearMode": use_auto_search,
            "UseFleetLock": False,
            "UseAutoSearch": use_auto_search,
            "Use2xBook": False,
        }
    )
    target["StopCondition"].update(
        {
            "OilLimit": 0,
            "RunCount": 1,
            "MapAchievement": "non_stop",
            "StageIncrease": False,
            "GetNewShip": False,
            "ReachLevel": 0,
        }
    )
    target["Submarine"]["Fleet"] = 0
    target["Submarine"]["Mode"] = "do_not_use"
    if stage == "12-4" and use_auto_search:
        target["Fleet"]["Fleet1"] = 1
        target["Fleet"]["Fleet2"] = 2
        target["Fleet"]["FleetOrder"] = fleet_order
    if stage == "1-1":
        target["Fleet"]["Fleet2"] = 0
        target["Fleet"]["FleetOrder"] = "fleet1_all_fleet2_standby"
    target["HpControl"]["UseHpBalance"] = False
    target["HpControl"]["UseEmergencyRepair"] = False
    target["HpControl"]["UseLowHpRetreat"] = False
    return payload


def run(args: argparse.Namespace) -> Mapping[str, Any]:
    alas_root = args.alas_root.resolve()
    seed_path = alas_root / "config" / f"{args.seed_config}.json"
    seed = _load_json(seed_path)
    payload = _configure(
        seed,
        task=args.task,
        stage=args.stage,
        use_auto_search=args.use_auto_search,
        fleet_order=args.fleet_order,
    )
    config_name = f"_codex_main_live_{args.task.lower()}_{uuid.uuid4().hex}"
    config_path = alas_root / "config" / f"{config_name}.json"
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    prior_cwd = Path.cwd()
    prior_env = {
        name: os.environ.get(name)
        for name in (
            "ALAS_SEMANTIC_MODE",
            "ALAS_SEMANTIC_DRIVER_REVISION",
            "ALAS_SEMANTIC_ADB",
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET",
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET",
        )
    }
    os.environ.update(
        {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
            "ALAS_SEMANTIC_ADB": args.adb,
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": "1",
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": "6",
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": "1",
            "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": str(args.combat_budget),
            "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": str(
                args.viewport_swipe_budget
            ),
        }
    )
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    instance = None
    login_recovery_performed = False
    started_at = _utc_now()
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task(args.task)
        semantic_session = instance.device.semantic_adapter
        startup_oracle = semantic_session.open().oracle
        startup_state = startup_oracle.read_state()
        starting_surface = {
            "main_page": _surface_visible(startup_oracle.main_page_visible),
            "campaign_map": _surface_visible(startup_oracle.campaign_is_in_map),
            "campaign_entry": _surface_visible(
                startup_oracle.campaign_menu_is_entry
            ),
            "generation": startup_state.generation,
        }
        if (
            startup_oracle.enabled("login/enter")
            or startup_oracle.login_update_download_available()
            or startup_oracle.login_update_in_progress()
            or startup_oracle.login_update_restart_prompt_available()
        ):
            from module.handler.login import LoginHandler

            LoginHandler(instance.config, device=instance.device).handle_app_login()
            login_recovery_performed = True
        run_result = instance.run(args.task.lower())
        post = _load_json(config_path)
        task_post = post[args.task]
        session = instance.device.semantic_adapter
        adapter = session.open()
        state = adapter.oracle.read_state()
        completion = session.last_campaign_auto_search_completion()
        final_surface = {
            "main_page": _surface_visible(adapter.oracle.main_page_visible),
            "campaign_map": _surface_visible(adapter.oracle.campaign_is_in_map),
            "campaign_entry": _surface_visible(
                adapter.oracle.campaign_menu_is_entry
            ),
        }
        run_count = task_post["StopCondition"]["RunCount"]
        enabled = task_post["Scheduler"]["Enable"]
        passed = bool(run_result) and run_count == 0 and enabled is False
        return {
            "schema": SCHEMA,
            "passed": passed,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "task": args.task,
            "stage": args.stage,
            "event": "campaign_main",
            "mode": "normal",
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "scheduler_command": task_post["Scheduler"]["Command"],
            "run_result": bool(run_result),
            "run_count_before": 1,
            "run_count_after": run_count,
            "scheduler_enabled_after": enabled,
            "use_auto_search": args.use_auto_search,
            "fleet_order": args.fleet_order,
            "auto_search_completion": (
                {
                    "stage": completion.stage_code,
                    "result_generation": completion.result_generation,
                    "result_path": completion.result_path,
                    "fleet1_role": completion.fleet1_role,
                    "fleet2_role": completion.fleet2_role,
                    "waited_seconds": completion.waited_seconds,
                    "combat_auto_generation": (
                        completion.combat_auto_generation
                    ),
                    "combat_auto_proven": completion.combat_auto_proven,
                    "passive_after_sortie": completion.passive_after_sortie,
                }
                if completion is not None
                else None
            ),
            "login_recovery_performed": login_recovery_performed,
            "starting_surface": starting_surface,
            "budgets": {
                "stage_entry": 1,
                "fleet_mutation": 6,
                "sortie": 1,
                "combat": args.combat_budget,
                "viewport_swipe": args.viewport_swipe_budget,
            },
            "observer": {
                "generation": state.generation,
                "scene_handle": state.scene_handle,
                "button_count": len(state.buttons),
            },
            "final_surface": final_surface,
            "raw_input_fallback_used": False,
        }
    finally:
        if instance is not None:
            _close_semantic_session(instance)
        os.chdir(prior_cwd)
        config_path.unlink(missing_ok=True)
        for name, value in prior_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument(
        "--serial",
        help="exact online ADB serial; auto-discovered only when exactly one is online",
    )
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--task", required=True, choices=TASKS)
    parser.add_argument("--stage", default="1-1")
    parser.add_argument("--use-auto-search", action="store_true")
    parser.add_argument(
        "--fleet-order",
        choices=(
            "fleet1_mob_fleet2_boss",
            "fleet1_boss_fleet2_mob",
        ),
        default="fleet1_mob_fleet2_boss",
    )
    parser.add_argument("--combat-budget", type=int, default=8)
    parser.add_argument("--viewport-swipe-budget", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.combat_budget < 0 or args.viewport_swipe_budget < 0:
        parser.error("budgets must be non-negative")
    return args


def main() -> int:
    args = parse_args()
    args.serial = resolve_adb_serial(args.adb, args.serial)
    result = run(args)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
