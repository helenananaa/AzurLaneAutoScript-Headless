#!/usr/bin/env python3
"""Run one bounded Main-family task against the pinned semantic AVD."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
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


def _book_consumption_complete(preparations, menus, count):
    return (len(preparations) == len(menus) == count and all(
        before["use_2x_book"] is True and before["book_selected"] is True
        and type(before["book_count"]) is int and type(after["book_count"]) is int
        and before["book_count"] - after["book_count"] == 1
        for before, after in zip(preparations, menus)))


def _configure(
    seed: Mapping[str, Any], *, task: str, stage: str, use_auto_search: bool,
    fleet_order: str, use_2x_book: bool = False,
    use_clear_mode: bool | None = None, use_fleet_lock: bool = False,
    fleet1: int | None = None, fleet2: int | None = None,
    run_count: int = 1,
    submarine_fleet: int = 0, submarine_mode: str = 'do_not_use',
    submarine_auto_mode: str = 'sub_standby',
    submarine_distance: str | None = None,
) -> dict[str, Any]:
    if type(run_count) is not int or run_count < 1:
        raise ValueError("run_count must be a positive integer")
    payload = copy.deepcopy(seed)
    # A dedicated Main qualification must not be preempted by an unrelated
    # due task from the seed. Only this disposable configuration is changed;
    # production scheduling and the source seed remain untouched.
    for name, section in payload.items():
        if name != task and isinstance(section, dict):
            scheduler = section.get("Scheduler")
            if isinstance(scheduler, dict) and "Enable" in scheduler:
                scheduler["Enable"] = False
                # Pinned ALAS force-enables Commission/Research/Reward on
                # config load. Keep their original scheduler logic intact by
                # making them not due in this disposable test configuration.
                scheduler["NextRun"] = (datetime.now() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S")
    target = payload[task]
    target["Scheduler"]["Command"] = task
    target["Scheduler"]["Enable"] = True
    target["Campaign"].update(
        {
            "Name": stage,
            "Event": "campaign_main",
            "Mode": "normal",
            "UseClearMode": use_auto_search if use_clear_mode is None else use_clear_mode,
            "UseFleetLock": use_fleet_lock,
            "UseAutoSearch": use_auto_search,
            "Use2xBook": use_2x_book,
        }
    )
    target["StopCondition"].update(
        {
            "OilLimit": 0,
            "RunCount": run_count,
            "MapAchievement": "non_stop",
            "StageIncrease": False,
            "GetNewShip": False,
            "ReachLevel": 0,
        }
    )
    target["Submarine"].update(Fleet=submarine_fleet, Mode=submarine_mode,
                              AutoSearchMode=submarine_auto_mode)
    if submarine_distance is not None:
        target['Submarine']['DistanceToBoss'] = submarine_distance
    if stage == "12-4" and use_auto_search:
        target["Fleet"]["Fleet1"] = 1
        target["Fleet"]["Fleet2"] = 2
        target["Fleet"]["FleetOrder"] = fleet_order
    if stage == "1-1":
        target["Fleet"]["Fleet2"] = 0
        target["Fleet"]["FleetOrder"] = "fleet1_all_fleet2_standby"
    if fleet1 is not None:
        target["Fleet"]["Fleet1"] = fleet1
    if fleet2 is not None:
        target["Fleet"]["Fleet2"] = fleet2
        target["Fleet"]["FleetOrder"] = fleet_order
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
        use_2x_book=getattr(args, "use_2x_book", False),
        use_clear_mode=getattr(args, "use_clear_mode", None),
        use_fleet_lock=getattr(args, "use_fleet_lock", False),
        fleet1=getattr(args, "fleet1", None),
        fleet2=getattr(args, "fleet2", None),
        run_count=getattr(args, "run_count", 1),
        submarine_fleet=getattr(args, 'submarine_fleet', 0),
        submarine_mode=getattr(args, 'submarine_mode', 'do_not_use'),
        submarine_auto_mode=getattr(args, 'submarine_auto_mode', 'sub_standby'),
        submarine_distance=getattr(args, 'submarine_distance', None),
    )
    payload["Alas"]["Emulator"]["Serial"] = args.serial
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
            "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": str(getattr(args, "run_count", 1)),
            "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": str(8 * getattr(args, "run_count", 1)),
            "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": str(getattr(args, "run_count", 1)),
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
    strategy_range_restore = None
    login_recovery_performed = False
    started_at = _utc_now()
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript

        if getattr(args, 'observe_submarine_range', False):
            from module.handler.strategy import StrategyHandler
            original_strategy_set = StrategyHandler.handle_strategy
            def observe_strategy_range(host, index):
                already_fixed = getattr(host, f'fleet_{index}_formation_fixed')
                result = original_strategy_set(host, index)
                if host.config.Submarine_Fleet and not already_fixed:
                    host.strategy_open()
                    host.strategy_set_execute(sub_view=True)
                    host.strategy_close()
                return result
            strategy_range_restore = (StrategyHandler, original_strategy_set)
            StrategyHandler.handle_strategy = observe_strategy_range

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task(args.task)
        semantic_session = instance.device.semantic_adapter
        startup_oracle = semantic_session.open().oracle
        completed_sorties = []
        preparations = []
        observed_adapter = semantic_session.open()
        submarine_moves = []
        submarine_strategy = []
        original_end_campaign = observed_adapter.end_campaign_pre_sortie
        def record_campaign_end():
            context = observed_adapter._campaign_context
            if context is not None:
                submarine_moves.extend(copy.deepcopy(context.submarine_move_history))
                submarine_strategy.extend(dataclasses.asdict(r) for r in context.submarine_strategy_receipts)
            return original_end_campaign()
        observed_adapter.end_campaign_pre_sortie = record_campaign_end
        combat_admissions = []
        original_combat_admission = observed_adapter.authorize_campaign_combat
        def record_combat_admission(decision, state):
            admission = original_combat_admission(decision, state)
            if admission is not None:
                combat_admissions.append(dict(generation=state.generation, battle_count=decision.battle_count,
                    target=decision.target_node, expected=decision.expected,
                    submarine=dataclasses.asdict(state.submarine) if state.submarine else None,
                    hunting_nodes=state.submarine_hunting_nodes,
                    submarine_destination=decision.submarine_destination_node))
            return admission
        observed_adapter.authorize_campaign_combat = record_combat_admission
        submarine_calls = []
        original_submarine_call = startup_oracle.click_campaign_submarine_call
        def record_submarine_call(*positional, **keywords):
            receipt = original_submarine_call(*positional, **keywords)
            submarine_calls.append(dataclasses.asdict(receipt))
            return receipt
        startup_oracle.click_campaign_submarine_call = record_submarine_call
        submarine_observations = []
        submarine_seen_controls = set()
        original_auto_state = startup_oracle.campaign_official_combat_auto_state
        def record_combat_submarine():
            active = original_auto_state()
            if getattr(args, 'submarine_fleet', 0) and active and len(submarine_observations) < 48:
                state = startup_oracle.read_state()
                ui = startup_oracle.read_ui_state()
                fragment = 'CombatUIStandard(Clone)/'
                def relevant(path):
                    return fragment in path and not any(part in path for part in
                        ('/HPTextCharacterContainer/', '/HPBarContainer/', '/AirFighterContainer/'))
                controls = {('button', x.path, x.interactable) for x in state.buttons if relevant(x.path)}
                controls.update(('toggle', x.path, x.checked) for x in ui.toggles if relevant(x.path))
                controls.update(('image', x.path, x.sprite) for x in ui.images if relevant(x.path))
                controls.update(('text', x.path, x.text) for x in ui.texts
                    if relevant(x.path) and ('Weapon_button_container/' in x.path or 'sub' in x.path.lower()))
                if controls <= submarine_seen_controls:
                    return active
                submarine_seen_controls.update(controls)
                submarine_observations.append(dict(generation=state.generation, ui_generation=ui.generation,
                    image_truncated=ui.image_truncated,
                    toggles=[dataclasses.asdict(x) for x in ui.toggles if relevant(x.path)],
                    buttons=[dataclasses.asdict(x) for x in state.buttons if relevant(x.path)],
                    images=[dataclasses.asdict(x) for x in ui.images if relevant(x.path)],
                    texts=[dataclasses.asdict(x) for x in ui.texts if relevant(x.path)]))
            return active
        startup_oracle.campaign_official_combat_auto_state = record_combat_submarine
        original_authorize = observed_adapter.authorize_campaign_sortie
        def record_preparation(*positional, **keywords):
            allowed = original_authorize(*positional, **keywords)
            if allowed:
                state, _, selected, count = startup_oracle._campaign_2x_book_control("prep")
                preparations.append(dict(generation=state.generation,
                    mode="prep", use_2x_book=keywords["use_2x_book"], book_selected=selected, book_count=count))
            return allowed
        observed_adapter.authorize_campaign_sortie = record_preparation
        original_continue_authorize = observed_adapter.authorize_campaign_auto_search_continue
        def record_continue_preparation(**keywords):
            allowed = original_continue_authorize(**keywords)
            if allowed:
                state, _, selected, count = startup_oracle._campaign_2x_book_control('auto')
                preparations.append(dict(generation=state.generation, mode='auto',
                    use_2x_book=keywords['use_2x_book'], book_selected=selected, book_count=count))
            return allowed
        observed_adapter.authorize_campaign_auto_search_continue = record_continue_preparation
        go_receipts = []
        original_go = startup_oracle.click_campaign_auto_search_reentry
        def record_go():
            receipt = original_go()
            go_receipts.append(dataclasses.asdict(receipt))
            return receipt
        startup_oracle.click_campaign_auto_search_reentry = record_go
        original_wait = observed_adapter.wait_campaign_auto_search_completion
        def record_completion(*positional, **keywords):
            proof = original_wait(*positional, **keywords)
            completed_sorties.append({
                "submarine_call_receipts": {str(key):dataclasses.asdict(value) for key, value in
                    observed_adapter._campaign_context.submarine_call_receipts.items()},
                "completion": dataclasses.asdict(proof),
                "sortie": dataclasses.asdict(observed_adapter._campaign_context.sortie_proof),
                "remaining_sortie_budget": observed_adapter._action_ledger.remaining("campaign.sortie"),
            })
            if proof.result_exit_receipt is None:
                record_result_menu('qualification/observe-result')
            return proof
        observed_adapter.wait_campaign_auto_search_completion = record_completion
        auto_menus = []
        auto_book_checks = []
        original_click = startup_oracle.click
        def record_result_menu(semantic_id, *positional, **keywords):
            if semantic_id in ("reward/campaign-total/exit", "qualification/observe-result") and len(auto_menus) < len(preparations):
                menu_state = startup_oracle.read_state()
                menu_ui = startup_oracle.read_ui_state()
                fragment = "LevelStageTotalRewardPanel(Clone)/"
                book_counts = [int(x.text.strip()) for x in menu_ui.texts
                    if x.path.endswith("/Window/Fixed/SpList/Item/Active/Item/IconTpl/icon_bg/count")
                    and not x.truncated and x.text.strip().isdigit()]
                auto_menus.append({
                    "book_count": book_counts[0] if len(book_counts) == 1 else None,
                    "generation": menu_state.generation,
                    "ui_generation": menu_ui.generation,
                    "buttons": [dataclasses.asdict(x) for x in menu_state.buttons if fragment in x.path],
                    "images": [dataclasses.asdict(x) for x in menu_ui.images if fragment in x.path],
                    "texts": [dataclasses.asdict(x) for x in menu_ui.texts if fragment in x.path],
                })
                if getattr(args, "verify_auto_book", False) and not auto_book_checks:
                    from module.handler.fast_forward import FastForwardHandler
                    from module.handler.assets import BOOK_CHECK_AUTO, BOOK_BOX_AUTO
                    handler = FastForwardHandler(instance.config, device=instance.device)
                    before = startup_oracle.campaign_2x_book_selected(mode="auto")
                    check = {"before": before, "states": [], "error": None}
                    auto_book_checks.append(check)
                    try:
                        if type(before) is not bool:
                            raise RuntimeError("AUTO book control is absent")
                        for selected in (not before, before):
                            # These are two separate qualification cases,
                            # not one retry of the same ALAS interval probe.
                            handler.interval_clear(BOOK_CHECK_AUTO)
                            handled = handler._set_2x_book_status(
                                "on" if selected else "off", BOOK_CHECK_AUTO, BOOK_BOX_AUTO)
                            observed = startup_oracle.campaign_2x_book_selected(mode="auto")
                            check["states"].append({"requested": selected, "observed": observed, "handled": handled})
                            if not handled or observed is not selected:
                                raise RuntimeError("AUTO book postcondition failed")
                    except Exception as exc:
                        check["error"] = type(exc).__name__ + ": " + str(exc)
                        failed_ui = startup_oracle.read_ui_state()
                        check["images"] = [dataclasses.asdict(x) for x in failed_ui.images if "/SpList/" in x.path]
                    # No Continue is sent. The original exit still executes;
                    # the next PREP re-proves the configured book selection.
            if semantic_id == 'qualification/observe-result':
                return None
            return original_click(semantic_id, *positional, **keywords)
        startup_oracle.click = record_result_menu
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
        try:
            run_result = instance.run(args.task.lower())
        except (Exception, SystemExit) as exc:
            return dict(schema=SCHEMA, passed=False, started_at=started_at, finished_at=_utc_now(),
                task=args.task, stage=args.stage, serial=args.serial,
                run_count_requested=args.run_count, execution_status='incomplete',
                error=type(exc).__name__ + ': ' + str(exc),
                preparations=preparations, completed_sorties=completed_sorties,
                auto_menu_observations=auto_menus, continuation_receipts=go_receipts,
                submarine_observations=submarine_observations, submarine_calls=submarine_calls,
                combat_admissions=combat_admissions,
                submarine_moves=submarine_moves, submarine_strategy=submarine_strategy)
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
        if args.use_auto_search:
            passed = passed and len(completed_sorties) == getattr(args, "run_count", 1)
        if getattr(args, 'require_auto_continue', False):
            passed = passed and len(go_receipts) == args.run_count - 1
        if getattr(args, "use_2x_book", False):
            passed = passed and _book_consumption_complete(preparations, auto_menus, getattr(args, "run_count", 1))
        if getattr(args, "verify_auto_book", False):
            passed = passed and len(auto_book_checks) == 1 and auto_book_checks[0]["error"] is None
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
            "run_count_before": getattr(args, "run_count", 1),
            "run_count_after": run_count,
            "scheduler_enabled_after": enabled,
            "use_auto_search": args.use_auto_search,
            "use_2x_book": getattr(args, "use_2x_book", False),
            "auto_menu_observations": auto_menus,
            "completed_sorties": completed_sorties,
            "continuation_receipts": go_receipts,
            "submarine_observations": submarine_observations,
            "submarine_calls": submarine_calls,
            "combat_admissions": combat_admissions,
            "submarine_moves": submarine_moves,
            "submarine_strategy": submarine_strategy,
            "observe_submarine_range": getattr(args, 'observe_submarine_range', False),
            "submarine_configuration": payload[args.task]['Submarine'],
            "preparations": preparations,
            "auto_book_checks": auto_book_checks,
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
                "stage_entry": getattr(args, "run_count", 1),
                "fleet_mutation": 8 * getattr(args, "run_count", 1),
                "sortie": getattr(args, "run_count", 1),
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
        if strategy_range_restore is not None:
            strategy_range_restore[0].handle_strategy = strategy_range_restore[1]
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
    parser.add_argument("--run-count", type=int, default=1)
    parser.add_argument("--use-auto-search", action="store_true")
    parser.add_argument("--use-2x-book", action="store_true")
    parser.add_argument("--require-auto-continue", action="store_true",
                        help="Require run_count-1 real ButtonGO receipts in this qualification")
    parser.add_argument("--verify-auto-book", action="store_true",
                        help="Exercise original AUTO book switch and restore it before exiting the first result")
    parser.add_argument("--use-clear-mode", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--use-fleet-lock", action="store_true")
    parser.add_argument("--fleet1", type=int, choices=range(1, 7))
    parser.add_argument('--submarine-fleet', type=int, choices=(0, 1, 2), default=0)
    parser.add_argument('--submarine-mode', choices=('do_not_use', 'hunt_only', 'boss_only', 'hunt_and_boss', 'every_combat'), default='do_not_use')
    parser.add_argument('--submarine-auto-mode', choices=('sub_standby', 'sub_auto_call'), default='sub_standby')
    parser.add_argument('--submarine-distance', choices=('to_boss_position', '1_grid_to_boss', '2_grid_to_boss', 'use_open_ocean_support'))
    parser.add_argument('--observe-submarine-range', action='store_true',
        help='Use original StrategyHandler to keep range visible during this qualification run; no battle decisions are replaced.')
    parser.add_argument("--fleet2", type=int, choices=range(0, 7))
    parser.add_argument(
        "--fleet-order",
        choices=(
            "fleet1_mob_fleet2_boss",
            "fleet1_boss_fleet2_mob",
            "fleet1_all_fleet2_standby",
            "fleet1_standby_fleet2_all",
        ),
        default="fleet1_mob_fleet2_boss",
    )
    parser.add_argument("--combat-budget", type=int, default=8,
        help='Reviewed map grid-input budget, including noncombat route waypoints; not a count of battles.')
    parser.add_argument("--viewport-swipe-budget", type=int, default=2)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.run_count < 1:
        parser.error("run-count must be positive")
    if args.combat_budget < 0 or args.viewport_swipe_budget < 0:
        parser.error("budgets must be non-negative")
    return args


def main() -> int:
    args = parse_args()
    args.serial = resolve_adb_serial(args.adb, args.serial)
    try:
        result = run(args)
    except (Exception, SystemExit) as exc:
        # A failed final observation must still leave an honest failure
        # receipt. It says nothing about actions/resources already consumed.
        result = {
            "schema": SCHEMA, "passed": False, "finished_at": _utc_now(),
            "task": args.task, "stage": args.stage, "serial": args.serial,
            "run_count_requested": args.run_count,
            "error": type(exc).__name__ + ": " + str(exc),
            "execution_status": "incomplete",
        }
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    # Keep stdout lossless even under Windows legacy console encodings;
    # the retained file above remains human-readable UTF-8.
    print(json.dumps(result, ensure_ascii=True, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
