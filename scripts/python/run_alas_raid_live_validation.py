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
from datetime import datetime, timezone
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


def run(args: argparse.Namespace) -> Mapping[str, Any]:
    alas_root = args.alas_root.resolve()
    daily_empty_ex = args.daily_empty_ex
    task_name = "RaidDaily" if daily_empty_ex else "Raid"
    command_name = "raid_daily" if daily_empty_ex else "raid"
    selected_mode = "ex" if daily_empty_ex else args.mode
    payload = copy.deepcopy(_load(args.seed_config.resolve()))
    payload["Alas"]["Emulator"].update(
        {"Serial": args.serial, "ScreenshotMethod": "ADB"}
    )
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    task = payload[task_name]
    task["Scheduler"].update({"Command": task_name, "Enable": True})
    if daily_empty_ex:
        task["RaidDaily"].update({"StageFilter": "ex"})
    else:
        task["Raid"].update({"Mode": selected_mode, "UseTicket": False})
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
            "RunCount": 0 if daily_empty_ex else 1,
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
            "0" if daily_empty_ex else "1"
        ),
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": "0" if daily_empty_ex else "1",
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": "0" if daily_empty_ex else "24",
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
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task(task_name)
        overrides = dict(
            Campaign_Event="raid_20260827",
            Campaign_Name="dynamic",
            Campaign_Mode="normal",
            StopCondition_OilLimit=args.oil_limit,
            StopCondition_RunCount=0 if daily_empty_ex else 1,
        )
        if daily_empty_ex:
            overrides.update(
                RaidDaily_StageFilter="ex",
                Reward_CollectOil=False,
                Reward_CollectCoin=False,
                Reward_CollectExp=False,
                Reward_CollectMission=False,
                Reward_CollectWeeklyMission=False,
            )
        else:
            overrides.update(Raid_Mode=selected_mode, Raid_UseTicket=False)
        instance.config.override(**overrides)
        session = instance.device.semantic_adapter
        adapter = session.open()
        oracle = adapter.oracle
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
        if session.raid_fleet_selection_visible("raid_20260827"):
            session.click_raid_fleet_back("raid_20260827")
            deadline = time.monotonic() + 10.0
            while not session.raid_page_visible("raid_20260827"):
                if time.monotonic() >= deadline:
                    raise RuntimeError("current Raid page did not recover")
                time.sleep(0.25)
            ui_recovery_steps.append("fleet_back")
            ui_recovered = True
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
        if oracle.main_page_visible():
            session.enter_raid_page("raid_20260827")
        if not session.raid_page_visible("raid_20260827"):
            raise RuntimeError("current Raid validation requires main or Raid page")

        before = {
            "remaining": session.raid_remain("raid_20260827", selected_mode),
            "points": session.event_points(),
            "sortie_grant": adapter._action_ledger.remaining("campaign.sortie"),
        }
        original_stage = session.click_raid_stage
        original_recommend = session.click_raid_fleet_recommend
        original_fleet = session.click_raid_fleet_start
        original_notice = session.click_raid_precombat_notice
        original_sortie = session.click_raid_precombat_start

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
        task_result = instance.run(command_name)

        after = {
            "raid_page": session.raid_page_visible("raid_20260827"),
            "remaining": session.raid_remain("raid_20260827", selected_mode),
            "points": session.event_points(),
            "sortie_grant": adapter._action_ledger.remaining("campaign.sortie"),
        }
        if daily_empty_ex:
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
            passed = bool(
                task_result is True
                and after["raid_page"]
                and before["remaining"] - after["remaining"] == 1
                and after["points"] > before["points"]
                and len(stage_receipts) == 1
                and len(recommend_receipts) <= 1
                and len(fleet_receipts) == 1
                and len(notice_receipts) <= 1
                and len(sortie_receipts) == 1
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
            "task_result": task_result,
            "runtime_preflight": runtime_preflight,
            "login_recovered": login_recovered,
            "ui_recovered": ui_recovered,
            "ui_recovery_steps": ui_recovery_steps,
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
            "runtime_preflight": runtime_preflight,
            "login_recovered": login_recovered,
            "ui_recovered": ui_recovered,
            "ui_recovery_steps": ui_recovery_steps,
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
        "--daily-empty-ex",
        action="store_true",
        help="validate RaidDaily's zero-EX path with all mutation budgets at zero",
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
