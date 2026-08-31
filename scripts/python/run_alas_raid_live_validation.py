#!/usr/bin/env python3
"""Validate one bounded current Raid path through the original ALAS task."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import traceback
import uuid
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> Mapping[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _write(path: Path | None, value: Mapping[str, Any]) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    print(text, end="")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _adb_shell_text(args: argparse.Namespace, *command: str) -> str | None:
    try:
        result = subprocess.run(
            [args.adb, "-s", args.serial, "shell", *command],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = result.stdout.strip()
    return value or None


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def run(args: argparse.Namespace) -> Mapping[str, Any]:
    alas_root = args.alas_root.resolve()
    daily_empty_ex = args.daily_empty_ex
    daily_empty_stage = args.daily_empty_stage
    daily_reward_ex = args.daily_reward_ex
    daily_empty = daily_empty_ex or daily_empty_stage
    daily_battle_count = (
        3 if daily_reward_ex else 1 if args.daily_one_battle else args.daily_battles
    )
    daily_task = daily_empty or daily_reward_ex or daily_battle_count is not None
    if args.use_ticket and daily_task:
        raise ValueError("--use-ticket is only valid for the standalone Raid task")
    if args.daily_stage_filter is not None and not daily_task:
        raise ValueError(
            "--daily-stage-filter requires a RaidDaily validation mode"
        )
    task_name = "RaidDaily" if daily_task else "Raid"
    command_name = "raid_daily" if daily_task else "raid"
    selected_mode = "ex" if daily_empty_ex or daily_reward_ex else args.mode
    configured_stage_filter = args.daily_stage_filter or selected_mode
    payload = copy.deepcopy(_load(args.seed_config.resolve()))
    isolated_next_run = (datetime.now() + timedelta(hours=1)).replace(
        microsecond=0
    ).strftime("%Y-%m-%d %H:%M:%S")
    payload["Alas"]["Emulator"].update(
        {"Serial": args.serial, "ScreenshotMethod": "ADB"}
    )
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    for configured_task, configured_payload in payload.items():
        if configured_task == task_name or not isinstance(configured_payload, dict):
            continue
        scheduler = configured_payload.get("Scheduler")
        if isinstance(scheduler, dict) and "Enable" in scheduler:
            scheduler["Enable"] = False
            # ALAS intentionally clamps implausibly distant task times back to
            # now.  Keep unrelated tasks within its shortest 12-hour horizon
            # while still placing them safely beyond this bounded live run.
            scheduler["NextRun"] = isolated_next_run
    task = payload[task_name]
    task["Scheduler"].update({"Command": task_name, "Enable": True})
    if daily_task:
        task["RaidDaily"].update({"StageFilter": configured_stage_filter})
    else:
        task["Raid"].update(
            {"Mode": selected_mode, "UseTicket": args.use_ticket}
        )
    task["Campaign"].update(
        {
            "Name": "dynamic",
            "Event": "raid_20260827",
            "Mode": "normal",
            "UseClearMode": True,
            "UseFleetLock": True,
            "UseAutoSearch": False,
            "Use2xBook": False,
        }
    )
    task["StopCondition"].update(
        {
            "OilLimit": args.oil_limit,
            # RaidDaily owns a clear-all loop and its upstream argument is
            # intentionally locked to zero.  Only standalone Raid uses the
            # ordinary ALAS run-count stop condition.
            "RunCount": 0 if daily_task else 1,
            "MapAchievement": "non_stop",
            "StageIncrease": False,
            "GetNewShip": False,
            "ReachLevel": 0,
        }
    )
    config_name = f"_codex_current_raid_{uuid.uuid4().hex}"
    config_path = alas_root / "config" / f"{config_name}.json"
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    semantic_env = {
        "ALAS_SEMANTIC_MODE": "1",
        "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
        "ALAS_SEMANTIC_ADB": args.adb,
        "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": (
            "0" if daily_empty else str(daily_battle_count or 1)
        ),
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": (
            "0" if daily_empty else str(daily_battle_count or 1)
        ),
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": (
            "0" if daily_empty else str(24 * (daily_battle_count or 1))
        ),
        "ALAS_SEMANTIC_ALLOW_MISSION_CLAIM_ONCE": (
            "1" if daily_reward_ex else "0"
        ),
    }
    prior_env = {name: os.environ.get(name) for name in semantic_env}
    prior_cwd = Path.cwd()
    os.environ.update(semantic_env)
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    instance = None
    session = None
    started_at = _now()
    stage_receipts: list[dict[str, Any]] = []
    recommend_receipts: list[dict[str, Any]] = []
    fleet_receipts: list[dict[str, Any]] = []
    notice_receipts: list[dict[str, Any]] = []
    sortie_receipts: list[dict[str, Any]] = []
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    runtime_preflight: dict[str, Any] = {}
    login_recovered = False
    ui_recovered = False
    ui_recovery_steps: list[str] = []
    active_combat_recovered = False
    orphan_result_receipts: list[dict[str, Any]] = []
    scheduler_preflight: dict[str, Any] = {}
    mission_claim_dispatches: list[dict[str, Any]] = []
    network_recovery_receipts: list[dict[str, Any]] = []
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from alas_headless import SemanticGateClosed

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task(task_name)
        overrides = dict(
            Campaign_Event="raid_20260827",
            Campaign_Name="dynamic",
            Campaign_Mode="normal",
            StopCondition_OilLimit=args.oil_limit,
        )
        if daily_task:
            overrides.update(
                RaidDaily_StageFilter=configured_stage_filter,
                Reward_CollectOil=False,
                Reward_CollectCoin=False,
                Reward_CollectExp=False,
                Reward_CollectMission=daily_reward_ex,
                Reward_CollectWeeklyMission=False,
            )
        else:
            overrides.update(
                Raid_Mode=selected_mode,
                Raid_UseTicket=args.use_ticket,
            )
        instance.config.override(**overrides)
        next_task = instance.config.get_next()
        scheduler_preflight = {
            "expected": task_name,
            "selected": next_task.command,
            "selected_next_run": str(next_task.next_run),
            "isolated_next_run": isolated_next_run,
            "configured_run_count": instance.config.StopCondition_RunCount,
        }
        if next_task.command != task_name:
            raise RuntimeError(
                "bounded current Raid validation scheduler selected "
                f"{next_task.command!r}, expected {task_name!r}"
            )
        session = instance.device.semantic_adapter
        adapter = session.open()
        oracle = adapter.oracle

        def recover_exact_network_popup() -> bool:
            semantic_id = "overlay/network-reconnect/confirm"
            if not oracle.enabled(semantic_id):
                return False
            receipt = oracle.click(semantic_id)
            post_generation = receipt.generation
            for _ in range(40):
                time.sleep(0.25)
                state = oracle.read_state()
                post_generation = state.generation
                if not oracle.exists(semantic_id):
                    network_recovery_receipts.append(
                        {
                            **asdict(receipt),
                            "post_generation": post_generation,
                            "postcondition": semantic_id + " absent",
                        }
                    )
                    return True
            raise SemanticGateClosed(
                "network reconnect confirmation did not clear its exact popup"
            )

        recover_exact_network_popup()
        observed = oracle.read_state()
        runtime_preflight = {
            "package": observed.snapshot.get("package"),
            "pid": observed.snapshot.get("pid"),
            "generation": observed.generation,
            "scene_handle": observed.scene_handle,
            "status": observed.snapshot.get("status"),
            "age_ms": observed.snapshot.get("age_ms"),
            "main_thread": observed.snapshot.get("main_thread"),
            "driver_revision": observed.snapshot.get("driver_revision"),
        }
        package_dump = _adb_shell_text(
            args, "dumpsys", "package", "com.bilibili.azurlane"
        )
        version_match = (
            re.search(r"\bversionName=([^\s]+)", package_dump)
            if package_dump is not None
            else None
        )
        runtime_preflight["game_version"] = (
            version_match.group(1) if version_match is not None else None
        )
        runtime_preflight["resource_hot_version"] = _adb_shell_text(
            args,
            "cat",
            "/sdcard/Android/data/com.bilibili.azurlane/files/version.txt",
        )
        # Recovery inspects several mutually exclusive Raid owner surfaces.
        # Bind those passive probes to the same immutable ALAS screenshot
        # frame so independent live endpoints cannot drift between checks.
        instance.device.screenshot()
        if oracle.daily_combat_visible():
            # Reattach only to the already-proven CombatUI surface through
            # ALAS's original combat-execute state machine.  Stop that loop at
            # the first typed result instead of letting an ownerless adapter
            # infer a Daily return page; the reviewed orphan-result drain below
            # owns the exact Raid return postcondition.
            from module.combat.combat import Combat

            interrupted_combat = Combat(instance.config, device=instance.device)

            def stop_at_typed_result(drop=None):
                del drop
                return bool(
                    oracle.daily_battle_result_visible()
                    or oracle.campaign_battle_reward_visible()
                )

            interrupted_combat.handle_battle_status = stop_at_typed_result
            interrupted_combat.handle_get_items = stop_at_typed_result
            interrupted_combat.combat_execute(
                auto="combat_auto",
                submarine="do_not_use",
                drop=None,
            )
            active_combat_recovered = True
            ui_recovered = True
            ui_recovery_steps.append("active_combat_execute")
            instance.device.screenshot()
        if session.orphan_combat_result_visible():
            orphan_result_receipts.extend(
                asdict(receipt)
                for receipt in session.recover_orphan_combat_result(
                    current_raid_event="raid_20260827"
                )
            )
            ui_recovery_steps.append("orphan_combat_result")
            ui_recovered = True
            # The final result click can expose the Raid root before its card
            # UI and button projections land within the reviewed coherence
            # window.  This is a passive remount only: wait for either exact
            # stable owner surface and do not issue another input here.
            recovery_deadline = time.monotonic() + 12.0
            while True:
                try:
                    raid_recovered = session.raid_page_visible("raid_20260827")
                except SemanticGateClosed as exc:
                    if str(exc) != "current Raid button and UI snapshots are incoherent":
                        raise
                    raid_recovered = False
                if raid_recovered or oracle.main_page_visible():
                    break
                if time.monotonic() >= recovery_deadline:
                    raise RuntimeError(
                        "current Raid result recovery did not stabilize its owner page"
                    )
                time.sleep(0.25)
            instance.device.screenshot()
        if session.raid_multiple_sortie_visible("raid_20260827"):
            session.click_raid_multiple_sortie_back("raid_20260827")
            deadline = time.monotonic() + 10.0
            while not session.raid_precombat_visible("raid_20260827"):
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "current Raid precombat page did not stabilize after "
                        "multiple-sortie back"
                    )
                time.sleep(0.25)
            ui_recovery_steps.append("multiple_sortie_back")
            ui_recovered = True
            instance.device.screenshot()
        if session.raid_precombat_visible("raid_20260827"):
            # A prior bounded run may have stopped after opening the exact
            # typed precombat surface but before consuming its sortie grant.
            # Back out one owned layer at a time; never click through it as
            # part of a fresh evidence run.
            session.click_raid_precombat_back("raid_20260827")
            deadline = time.monotonic() + 10.0
            while True:
                precombat_visible = session.raid_precombat_visible("raid_20260827")
                fleet_visible = session.raid_fleet_selection_visible(
                    "raid_20260827"
                )
                if not precombat_visible and fleet_visible:
                    break
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "current Raid fleet page did not stabilize after precombat back"
                    )
                time.sleep(0.25)
            ui_recovery_steps.append("precombat_back")
            instance.device.screenshot()
        if session.raid_fleet_selection_visible("raid_20260827"):
            session.click_raid_fleet_back("raid_20260827")
            deadline = time.monotonic() + 10.0
            while not session.raid_page_visible("raid_20260827"):
                if time.monotonic() >= deadline:
                    raise RuntimeError("current Raid page did not recover")
                time.sleep(0.25)
            ui_recovery_steps.append("fleet_back")
            ui_recovered = True
            instance.device.screenshot()
        if (
            not oracle.main_page_visible()
            and not session.raid_page_visible("raid_20260827")
            and oracle.enabled("login/enter")
        ):
            # Keep startup ownership in the original ALAS login state machine.
            # The caller is responsible for the mandatory -force-gfx-st cold
            # launch; this path only completes the exact typed login surface.
            from module.handler.login import LoginHandler

            LoginHandler(instance.config, device=instance.device).handle_app_login()
            login_recovered = True
            # A bulletin can mount just after LoginHandler confirms the main
            # scene. Let the original global UI recovery loop clear that exact
            # overlay and establish page_main before the Raid entry action.
            instance.goto_main()
            ui_recovered = True
        elif oracle.enabled("overlay/bulletin/close"):
            # The bulletin may outlive the process that completed login. Its
            # exact close action belongs to ALAS's global UI recovery loop.
            instance.goto_main()
            ui_recovered = True
        elif oracle.event_story_dialogue_visible():
            # A first-entry Raid story can persist from an interrupted prior
            # run. Resume through ALAS's existing story-skip and page recovery
            # handlers before establishing the validation start page.
            instance.goto_main()
            ui_recovered = True
        elif oracle.exists("task/page/back"):
            # A failed reward-enabled validation can leave the exact TaskScene
            # mounted after the claim popup has already been drained.  Resume
            # through ALAS's normal page graph; the adapter requires the full
            # reviewed mission-page identity before exposing MISSION_CHECK.
            instance.goto_main()
            ui_recovery_steps.append("mission_page_back")
            ui_recovered = True
        recover_exact_network_popup()
        if oracle.main_page_visible():
            try:
                session.enter_raid_page("raid_20260827")
            except SemanticGateClosed:
                # The global reconnect overlay can mount between the main-page
                # proof and the exact Raid entry click. Retry that one entry
                # only after the reviewed popup and its absence postcondition.
                if not recover_exact_network_popup():
                    raise
                session.enter_raid_page("raid_20260827")
        page_deadline = time.monotonic() + 10.0
        while True:
            recover_exact_network_popup()
            try:
                raid_ready = session.raid_page_visible("raid_20260827")
            except SemanticGateClosed as exc:
                if str(exc) != "current Raid button and UI snapshots are incoherent":
                    raise
                # The page root can survive while its cards remount across
                # adjacent observer generations. This is observation-only:
                # wait for the original exact contract and never re-click.
                raid_ready = False
            if raid_ready:
                break
            if time.monotonic() >= page_deadline:
                raise RuntimeError(
                    "current Raid validation requires a stable main or Raid page"
                )
            time.sleep(0.25)

        before = {
            "remaining": session.raid_remain("raid_20260827", selected_mode),
            "points": session.event_points(),
            "sortie_grant": adapter._action_ledger.remaining("campaign.sortie"),
        }
        if (
            daily_battle_count is not None
            and not daily_reward_ex
            and before["remaining"] != daily_battle_count
        ):
            raise RuntimeError(
                "RaidDaily validation requires the expected battle count to "
                "equal the selected stage's live remaining count; observed "
                f"{before['remaining']}, expected {daily_battle_count}"
            )
        original_stage = session.click_raid_stage
        original_recommend = session.click_raid_fleet_recommend
        original_fleet = session.click_raid_fleet_start
        original_notice = session.click_raid_precombat_notice
        original_sortie = session.click_raid_precombat_start
        original_dispatch = adapter._dispatch_mutation

        def record_dispatch(capability: str, operation: object):
            receipt = original_dispatch(capability, operation)
            if capability == "mission.claim":
                mission_claim_dispatches.append(asdict(receipt))
            return receipt

        def record_stage(event: str, mode: str):
            receipt = original_stage(event, mode)
            stage_receipts.append(asdict(receipt))
            return receipt

        def record_fleet(event: str):
            receipt = original_fleet(event)
            fleet_receipts.append(asdict(receipt))
            return receipt

        def record_recommend(event: str):
            receipt = original_recommend(event)
            recommend_receipts.append(asdict(receipt))
            return receipt

        def record_notice(event: str):
            receipt = original_notice(event)
            notice_receipts.append(asdict(receipt))
            return receipt

        def record_sortie(event: str):
            receipt = original_sortie(event)
            sortie_receipts.append(asdict(receipt))
            return receipt

        session.click_raid_stage = record_stage
        session.click_raid_fleet_recommend = record_recommend
        session.click_raid_fleet_start = record_fleet
        session.click_raid_precombat_notice = record_notice
        session.click_raid_precombat_start = record_sortie
        adapter._dispatch_mutation = record_dispatch
        task_result = instance.run(command_name)

        after = {
            "raid_page": session.raid_page_visible("raid_20260827"),
            "remaining": session.raid_remain("raid_20260827", selected_mode),
            "points": session.event_points(),
            "sortie_grant": adapter._action_ledger.remaining("campaign.sortie"),
        }
        if daily_reward_ex:
            ex_battles = len(sortie_receipts)
            claim_count = len(mission_claim_dispatches)
            fresh_claim_path = bool(
                claim_count == 1
                and before["remaining"] == after["remaining"] == 0
            )
            resumed_claim_path = bool(
                claim_count == 0
                and before["remaining"] in (1, 2, 3)
                and after["remaining"] == 0
                and ex_battles == before["remaining"]
            )
            passed = bool(
                task_result is True
                and after["raid_page"]
                and (fresh_claim_path or resumed_claim_path)
                and after["points"] > before["points"]
                and adapter._action_ledger.remaining("mission.claim")
                == 1 - claim_count
                and ex_battles in (1, 2, 3)
                and len(stage_receipts) == ex_battles
                and len(recommend_receipts) <= ex_battles
                and len(fleet_receipts) == ex_battles
                and len(notice_receipts) <= ex_battles
                and after["sortie_grant"] == 3 - ex_battles
            )
        elif daily_empty:
            passed = bool(
                task_result is True
                and after["raid_page"]
                and before["remaining"] == after["remaining"] == 0
                and before["points"] == after["points"]
                and not stage_receipts
                and not recommend_receipts
                and not fleet_receipts
                and not notice_receipts
                and not sortie_receipts
                and before["sortie_grant"] == after["sortie_grant"] == 0
            )
        else:
            expected_battles = daily_battle_count or 1
            passed = bool(
                task_result is True
                and after["raid_page"]
                and before["remaining"] - after["remaining"] == expected_battles
                and after["remaining"] == 0
                and after["points"] > before["points"]
                and len(stage_receipts) == expected_battles
                and len(recommend_receipts) <= expected_battles
                and len(fleet_receipts) == expected_battles
                and len(notice_receipts) <= expected_battles
                and len(sortie_receipts) == expected_battles
                and after["sortie_grant"] == 0
            )
        return {
            "schema": "alas-headless.current-raid-live-validation/v1",
            "passed": passed,
            "started_at": started_at,
            "finished_at": _now(),
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "event": "raid_20260827",
            "task": task_name,
            "mode": selected_mode,
            "configured_stage_filter": configured_stage_filter,
            "daily_battle_count": daily_battle_count,
            "daily_reward_ex": daily_reward_ex,
            "use_ticket": args.use_ticket,
            "task_result": task_result,
            "runtime_preflight": runtime_preflight,
            "scheduler_preflight": scheduler_preflight,
            "login_recovered": login_recovered,
            "ui_recovered": ui_recovered,
            "active_combat_recovered": active_combat_recovered,
            "ui_recovery_steps": ui_recovery_steps,
            "orphan_result_receipts": orphan_result_receipts,
            "mission_claim_dispatches": mission_claim_dispatches,
            "network_recovery_receipts": network_recovery_receipts,
            "before": before,
            "after": after,
            "stage_receipts": stage_receipts,
            "recommend_receipts": recommend_receipts,
            "fleet_receipts": fleet_receipts,
            "notice_receipts": notice_receipts,
            "sortie_receipts": sortie_receipts,
            "raw_input_fallback_used": False,
            "source_sha256": {
                "raid": _sha256(alas_root / "module" / "raid" / "raid.py"),
                "run": _sha256(alas_root / "module" / "raid" / "run.py"),
                "daily": _sha256(alas_root / "module" / "raid" / "daily.py"),
                "adapter": _sha256(ROOT / "python" / "alas_headless" / "alas_adapter.py"),
                "oracle": _sha256(ROOT / "python" / "alas_headless" / "semantic_oracle.py"),
                "runner": _sha256(Path(__file__).resolve()),
            },
        }
    except (Exception, SystemExit) as exc:
        return {
            "schema": "alas-headless.current-raid-live-validation/v1",
            "passed": False,
            "started_at": started_at,
            "finished_at": _now(),
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "event": "raid_20260827",
            "task": task_name,
            "mode": selected_mode,
            "configured_stage_filter": configured_stage_filter,
            "daily_battle_count": daily_battle_count,
            "daily_reward_ex": daily_reward_ex,
            "use_ticket": args.use_ticket,
            "runtime_preflight": runtime_preflight,
            "scheduler_preflight": scheduler_preflight,
            "login_recovered": login_recovered,
            "ui_recovered": ui_recovered,
            "active_combat_recovered": active_combat_recovered,
            "ui_recovery_steps": ui_recovery_steps,
            "orphan_result_receipts": orphan_result_receipts,
            "mission_claim_dispatches": mission_claim_dispatches,
            "network_recovery_receipts": network_recovery_receipts,
            "before": before,
            "after": after,
            "stage_receipts": stage_receipts,
            "recommend_receipts": recommend_receipts,
            "fleet_receipts": fleet_receipts,
            "notice_receipts": notice_receipts,
            "sortie_receipts": sortie_receipts,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "raw_input_fallback_used": False,
        }
    finally:
        if session is not None:
            try:
                session.close()
            except Exception:
                pass
        os.chdir(prior_cwd)
        config_path.unlink(missing_ok=True)
        for name, value in prior_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--seed-config", required=True, type=Path)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument(
        "--mode", default="easy", choices=("easy", "normal", "hard", "ex")
    )
    parser.add_argument(
        "--use-ticket",
        action="store_true",
        help="exercise standalone Raid.UseTicket=true; zero-ticket state falls back to one normal sortie, while positive selection remains fail-closed",
    )
    daily_mode = parser.add_mutually_exclusive_group()
    daily_mode.add_argument(
        "--daily-empty-ex",
        action="store_true",
        help="validate RaidDaily's zero-EX path with all mutation budgets at zero",
    )
    daily_mode.add_argument(
        "--daily-empty-stage",
        action="store_true",
        help="validate --mode as an already-cleared RaidDaily stage with all mutation budgets at zero",
    )
    daily_mode.add_argument(
        "--daily-reward-ex",
        action="store_true",
        help="claim ordinary daily mission rewards and consume up to three granted EX tickets through RaidDaily; an interrupted post-claim run may resume from the exact TaskScene",
    )
    daily_mode.add_argument(
        "--daily-one-battle",
        action="store_true",
        help="validate a selected RaidDaily stage whose live remaining count is exactly one",
    )
    daily_mode.add_argument(
        "--daily-battles",
        type=_positive_int,
        help="validate full clearing a selected RaidDaily stage with this expected live remaining count",
    )
    parser.add_argument(
        "--daily-stage-filter",
        help="override RaidDaily.StageFilter for an ordered multi-stage validation; use with another --daily-* mode",
    )
    parser.add_argument("--oil-limit", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args)
    _write(args.output, result)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
