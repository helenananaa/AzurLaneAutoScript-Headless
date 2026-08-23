#!/usr/bin/env python3
"""Run one bounded Event-family task against the pinned semantic AVD."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
TASKS = ("Event", "Event2", "EventA", "EventB", "EventC", "EventD", "EventSp")
DAILY_TASKS = ("EventA", "EventB", "EventC", "EventD")
RUN_METHODS = {
    "Event": "event",
    "Event2": "event2",
    "EventA": "event_a",
    "EventB": "event_b",
    "EventC": "event_c",
    "EventD": "event_d",
    "EventSp": "event_sp",
}
SCHEMA = "alas-headless.event-task-live-validation/v1"
SHARED_HARD_STAGE_ENTRANCES = {
    **{f"c{index}": f"a{index}" for index in range(1, 4)},
    **{f"d{index}": f"b{index}" for index in range(1, 4)},
}


def _stage_difficulty(stage: str) -> str:
    code = stage.strip().lower()
    return "hard" if code.startswith(("c", "d")) else "normal"


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


def _wait_for_startup_surface(
    semantic_session: Any,
    *,
    timeout_seconds: float = 60.0,
) -> tuple[Any, Any, Mapping[str, bool]]:
    """Wait for one reviewed cold-start surface without issuing game input."""

    deadline = time.monotonic() + timeout_seconds
    while True:
        frame = semantic_session.refresh_frame(include_ui=False)
        oracle = semantic_session.open().oracle
        surfaces = {
            "main_page": _surface_visible(oracle.main_page_visible),
            "campaign_map": _surface_visible(oracle.campaign_is_in_map),
            "event_page": _surface_visible(oracle.event_campaign_page_visible),
            "login": bool(
                oracle.enabled("login/enter")
                or oracle.login_update_download_available()
                or oracle.login_update_in_progress()
                or oracle.login_update_restart_prompt_available()
            ),
        }
        if any(surfaces.values()):
            return frame, oracle, surfaces
        if time.monotonic() >= deadline:
            raise RuntimeError("reviewed campaign startup surface did not appear")
        time.sleep(0.5)


def _recover_inherited_preparation(oracle: Any, stage: str) -> int:
    """Close at most one inherited fleet layer and its map detail layer."""

    stage_code = stage.lower()

    def read_state() -> tuple[Any, str]:
        candidates = [stage_code]
        shared = SHARED_HARD_STAGE_ENTRANCES.get(stage_code)
        if shared is not None:
            candidates.append(shared)
        last_identity_error: Exception | None = None
        for candidate in candidates:
            try:
                return oracle.campaign_preparation_state(candidate), candidate
            except Exception as exc:
                if not (
                    exc.__class__.__name__ == "SemanticGateClosed"
                    and str(exc).endswith("stage identity changed")
                ):
                    raise
                last_identity_error = exc
        assert last_identity_error is not None
        raise last_identity_error

    recovered = 0
    for _ in range(2):
        state, observed_stage_code = read_state()
        if state is None:
            break
        kind = getattr(state, "kind", None)
        if kind == "fleet":
            oracle.cancel_campaign_fleet_preparation(observed_stage_code)
        elif kind == "map":
            oracle.cancel_campaign_map_preparation(observed_stage_code)
        else:
            raise RuntimeError(f"unknown campaign preparation kind: {kind!r}")
        recovered += 1
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                next_state, _next_stage_code = read_state()
            except Exception as exc:
                if exc.__class__.__name__ not in (
                    "SemanticGateClosed",
                    "SemanticTargetMissing",
                ):
                    raise
                time.sleep(0.25)
                continue
            if next_state is None or getattr(next_state, "kind", None) != kind:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(
                f"campaign {kind} preparation did not close after typed cancel"
            )
    return recovered


def _configure(
    seed: Mapping[str, Any],
    *,
    serial: str,
    task: str,
    event: str,
    stage: str,
    use_auto_search: bool,
) -> dict[str, Any]:
    payload = copy.deepcopy(seed)
    emulator = payload["Alas"]["Emulator"]
    emulator["Serial"] = serial
    # A live-qualification run must never enter ALAS's multi-method benchmark:
    # that path probes unrelated transports and can hang before the semantic
    # session exists.  ADB is the reviewed frame transport for this AVD; all
    # task actions remain owned by the semantic adapter.
    emulator["ScreenshotMethod"] = "ADB"
    target = payload[task]
    target["Scheduler"]["Command"] = task
    target["Scheduler"]["Enable"] = True
    target["Campaign"].update(
        {
            "Name": "dynamic" if task in DAILY_TASKS else stage,
            "Event": event,
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
    target["Fleet"]["Fleet1"] = 1
    target["Fleet"]["Fleet2"] = 2 if use_auto_search else 0
    target["Fleet"]["FleetOrder"] = (
        "fleet1_mob_fleet2_boss"
        if use_auto_search
        else "fleet1_all_fleet2_standby"
    )
    target["Submarine"]["Fleet"] = 0
    target["Submarine"]["Mode"] = "do_not_use"
    target["HpControl"]["UseHpBalance"] = False
    target["HpControl"]["UseEmergencyRepair"] = False
    target["HpControl"]["UseLowHpRetreat"] = False
    if task in DAILY_TASKS:
        target["EventDaily"]["StageFilter"] = stage
        target["EventDaily"]["LastStage"] = 0
    return payload


def run(args: argparse.Namespace) -> Mapping[str, Any]:
    alas_root = args.alas_root.resolve()
    seed_path = alas_root / "config" / f"{args.seed_config}.json"
    seed = _load_json(seed_path)
    payload = _configure(
        seed,
        serial=args.serial,
        task=args.task,
        event=args.event,
        stage=args.stage,
        use_auto_search=args.use_auto_search,
    )
    config_name = f"_codex_event_live_{args.task.lower()}_{uuid.uuid4().hex}"
    config_path = alas_root / "config" / f"{config_name}.json"
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    environment_names = (
        "ALAS_SEMANTIC_MODE",
        "ALAS_SEMANTIC_DRIVER_REVISION",
        "ALAS_SEMANTIC_ADB",
        "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
        "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS",
        "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET",
    )
    prior_env = {name: os.environ.get(name) for name in environment_names}
    os.environ.update(
        {
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
            "ALAS_SEMANTIC_ADB": args.adb,
            "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
            "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS": "60000",
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

    prior_cwd = Path.cwd()
    instance = None
    login_recovery_performed = False
    orphan_result_recovery_count = 0
    preparation_recovery_count = 0
    started_at = _utc_now()
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task(args.task)
        runtime_name = "dynamic" if args.task in DAILY_TASKS else args.stage
        runtime_overrides = {
            "Campaign_Event": args.event,
            "Campaign_Name": runtime_name,
            "Campaign_Mode": "normal",
            "Campaign_UseClearMode": args.use_auto_search,
            "Campaign_UseFleetLock": False,
            "Campaign_UseAutoSearch": args.use_auto_search,
            "Campaign_Use2xBook": False,
            "StopCondition_OilLimit": 0,
            "StopCondition_RunCount": 1,
            "StopCondition_MapAchievement": "non_stop",
            "StopCondition_StageIncrease": False,
            "StopCondition_GetNewShip": False,
            "StopCondition_ReachLevel": 0,
            "Fleet_Fleet1": 1,
            "Fleet_Fleet2": 2 if args.use_auto_search else 0,
            "Fleet_FleetOrder": (
                "fleet1_mob_fleet2_boss"
                if args.use_auto_search
                else "fleet1_all_fleet2_standby"
            ),
            "Submarine_Fleet": 0,
            "Submarine_Mode": "do_not_use",
            "HpControl_UseHpBalance": False,
            "HpControl_UseEmergencyRepair": False,
            "HpControl_UseLowHpRetreat": False,
        }
        if args.task in DAILY_TASKS:
            runtime_overrides.update(
                {
                    "EventDaily_StageFilter": args.stage,
                    "EventDaily_LastStage": 0,
                }
            )
        instance.config.override(**runtime_overrides)
        effective_config = {
            "event": instance.config.Campaign_Event,
            "name": instance.config.Campaign_Name,
            "mode": instance.config.Campaign_Mode,
            "use_auto_search": instance.config.Campaign_UseAutoSearch,
            "run_count": instance.config.StopCondition_RunCount,
        }
        if effective_config != {
            "event": args.event,
            "name": runtime_name,
            "mode": "normal",
            "use_auto_search": args.use_auto_search,
            "run_count": 1,
        }:
            raise RuntimeError(
                f"effective Event configuration drifted: {effective_config!r}"
            )
        semantic_session = instance.device.semantic_adapter
        # A cold game start publishes the observer socket before Unity has
        # committed its first semantic frame.  Enter through the session clock
        # so that this one explicitly bounded startup gap is retried without
        # weakening any target or input gate.
        startup_frame, startup_oracle, startup_surfaces = _wait_for_startup_surface(
            semantic_session
        )
        starting_surface = {
            "main_page": startup_surfaces["main_page"],
            "campaign_map": startup_surfaces["campaign_map"],
            "event_page": startup_surfaces["event_page"],
            "generation": startup_frame.generation,
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
        if semantic_session.orphan_combat_result_visible():
            orphan_result_recovery_count = len(
                semantic_session.recover_orphan_combat_result()
            )
        preparation_recovery_count = _recover_inherited_preparation(
            semantic_session.open().oracle,
            args.stage,
        )
        run_result = instance.run(RUN_METHODS[args.task])
        post = _load_json(config_path)
        task_post = post[args.task]
        adapter = instance.device.semantic_adapter.open()
        state = adapter.oracle.read_state()
        final_surface = {
            "main_page": _surface_visible(adapter.oracle.main_page_visible),
            "campaign_map": _surface_visible(adapter.oracle.campaign_is_in_map),
            "event_page": _surface_visible(adapter.oracle.event_campaign_page_visible),
        }
        run_count = task_post["StopCondition"]["RunCount"]
        enabled = task_post["Scheduler"]["Enable"]
        passed = bool(
            run_result
            and run_count == 0
            and isinstance(enabled, bool)
            and final_surface["event_page"]
        )
        return {
            "schema": SCHEMA,
            "passed": passed,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "task": args.task,
            "stage": args.stage,
            "event": args.event,
            "mode": _stage_difficulty(args.stage),
            "upstream_invocation_mode": "normal",
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "scheduler_command": task_post["Scheduler"]["Command"],
            "effective_config": effective_config,
            "run_result": bool(run_result),
            "run_count_before": 1,
            "run_count_after": run_count,
            "scheduler_enabled_after": enabled,
            "event_daily_last_stage_after": (
                task_post["EventDaily"]["LastStage"]
                if args.task in DAILY_TASKS
                else None
            ),
            "use_auto_search": args.use_auto_search,
            "login_recovery_performed": login_recovery_performed,
            "orphan_result_recovery_count": orphan_result_recovery_count,
            "preparation_recovery_count": preparation_recovery_count,
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
    parser.add_argument("--serial", default="emulator-5580")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--task", required=True, choices=TASKS)
    parser.add_argument("--event", default="event_20260813_cn")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--use-auto-search", action="store_true")
    parser.add_argument("--combat-budget", type=int, default=12)
    parser.add_argument("--viewport-swipe-budget", type=int, default=4)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.combat_budget < 0 or args.viewport_swipe_budget < 0:
        parser.error("budgets must be non-negative")
    return args


def main() -> int:
    args = parse_args()
    result = run(args)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
