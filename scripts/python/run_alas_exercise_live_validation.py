#!/usr/bin/env python3
"""Run one bounded original-ALAS Exercise attempt on the live client."""

from __future__ import annotations

import argparse
import copy
import json
import os
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(alas_root: Path, seed_config: str, serial: str,
             driver_revision: str, mode: str, strategy: str,
             opponent_trial: int, low_hp_threshold: float, expect_outcome: str,
             execute_budget: int, refresh_budget: int,
             navigate_from_chapter: bool = False) -> dict:
    seed = json.loads((alas_root / "config" / (seed_config + ".json")).read_text(encoding="utf-8"))
    package = seed["Alas"]["Emulator"]["PackageName"]
    subprocess.run(("adb", "-s", serial, "shell", "pidof", package), check=True,
                   capture_output=True, timeout=30)
    payload = copy.deepcopy(seed)
    payload["Alas"]["Emulator"]["Serial"] = serial
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    payload["Exercise"]["Scheduler"]["Enable"] = False
    payload["Exercise"]["Exercise"].update({
        "ExerciseStrategy": strategy,
        "OpponentChooseMode": mode,
        "OpponentTrial": opponent_trial,
        "LowHpThreshold": low_hp_threshold,
    })
    name = "codex_exercise_live_" + uuid.uuid4().hex
    config_path = alas_root / "config" / (name + ".json")
    write_json(config_path, payload)
    result = {"passed": False, "mode": mode, "strategy": strategy,
              "opponent_trial": opponent_trial, "serial": serial,
              "expect_outcome": expect_outcome,
              "navigate_from_chapter": navigate_from_chapter,
              "execute_budget": execute_budget,
              "refresh_budget": refresh_budget}
    instance = None
    adapter = None
    old = {key: os.environ.get(key) for key in (
        "ALAS_SEMANTIC_EXERCISE_EXECUTE_BUDGET",
        "ALAS_SEMANTIC_EXERCISE_REFRESH_BUDGET",
    )}
    try:
        os.environ.update({
            "ALAS_SEMANTIC_MODE": "1",
            "ALAS_SEMANTIC_DRIVER_REVISION": driver_revision,
            "ALAS_SEMANTIC_ADB": "adb",
            "ALAS_SEMANTIC_EXERCISE_EXECUTE_BUDGET": str(execute_budget),
            "ALAS_SEMANTIC_EXERCISE_REFRESH_BUDGET": str(refresh_budget),
        })
        sys.path.insert(0, str(alas_root))
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.config.config import name_to_function

        instance = AzurLaneAutoScript(name)
        instance.config.bind("Exercise")
        instance.config.task = name_to_function("Exercise")
        from module.exercise.exercise import Exercise
        from module.ui.page import page_campaign, page_exercise

        exercise = Exercise(config=instance.config, device=instance.device)
        if navigate_from_chapter:
            exercise.ui_ensure(page_campaign)
            if not instance.device.semantic_adapter.open().oracle.campaign_page_is_normal():
                raise RuntimeError("original ALAS did not reach a campaign chapter")
            result["chapter_navigation_confirmed"] = True
        exercise.ui_ensure(page_exercise)
        adapter = instance.device.semantic_adapter.open()
        if adapter.oracle.campaign_menu_is_entry():
            adapter.oracle.click_campaign_exercise_entrance()
            for _ in range(80):
                time.sleep(0.25)
                if adapter.oracle.exercise_page_visible():
                    break
            else:
                raise RuntimeError("campaign menu did not enter Exercise")
        if adapter.oracle.exercise_opponent_detail_visible():
            adapter.oracle.click_exercise_opponent_back()
            for _ in range(60):
                time.sleep(0.25)
                if adapter.oracle.exercise_page_visible():
                    break
            else:
                raise RuntimeError("Exercise detail did not return to overview")
        if adapter.oracle.daily_precombat_visible() and adapter.oracle.exercise_page_visible():
            adapter.oracle.click_daily_precombat_back()
            for _ in range(60):
                time.sleep(0.25)
                if (adapter.oracle.exercise_page_visible()
                        and not adapter.oracle.daily_precombat_visible()):
                    break
            else:
                raise RuntimeError("Exercise preparation did not return to overview")
        if not adapter.oracle.exercise_page_visible():
            for _ in range(120):
                if adapter.oracle.exercise_merit_shop_visible():
                    adapter.oracle.click_exercise_merit_shop_close()
                elif adapter.oracle.exercise_reward_item_info_visible():
                    adapter.oracle.click_exercise_reward_item_info_cancel()
                elif adapter.oracle.daily_battle_result_visible():
                    adapter.oracle.click_daily_battle_result()
                elif adapter.oracle.award_info_page_visible():
                    adapter.oracle.click_exercise_award_info_close()
                elif adapter.oracle.enabled("reward/award-info1/close"):
                    adapter.oracle.click("reward/award-info1/close")
                time.sleep(0.25)
                if adapter.oracle.exercise_page_visible():
                    break
            else:
                raise RuntimeError("Exercise result stack did not return to overview")
        for _ in range(80):
            if adapter.oracle.exercise_page_visible():
                break
            time.sleep(0.25)
        else:
            raise RuntimeError("Exercise overview did not stabilize")
        before = adapter.oracle.exercise_remaining()
        result["remaining_before"] = before
        result["period_before"] = adapter.oracle.exercise_period_remaining_text()
        for _ in range(80):
            try:
                result["powers_before"] = [
                    adapter.oracle.exercise_opponent_power(i) for i in range(1, 5)
                ]
                break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError("Exercise rival powers did not stabilize")
        started = time.monotonic()
        result["task_result"] = instance.run("exercise", skip_first_screenshot=False)
        result["elapsed_seconds"] = round(time.monotonic() - started, 3)
        result["result_stack_receipts"] = [
            receipt.semantic_id
            for receipt in instance.device.semantic_adapter.complete_exercise_battle_result()
        ]
        instance.device.semantic_adapter.exercise_wait_overview()
        after = adapter.oracle.exercise_remaining()
        result["remaining_after"] = after
        result["execute_grant_remaining"] = adapter._action_ledger.remaining("exercise.execute")
        result["refresh_grant_remaining"] = adapter._action_ledger.remaining("exercise.refresh")
        result["observed_outcome"] = (
            "complete" if after == before - 1 else
            "no-action" if (after == before
                            and result["execute_grant_remaining"] == execute_budget) else
            "low-hp-quit" if after == before else "unexpected"
        )
        expected_after = (
            (before - 1,) if expect_outcome == "complete" else
            (before,) if expect_outcome in ("low-hp-quit", "no-action") else
            (before - 1, before)
        )
        if result["task_result"] is not True or after not in expected_after:
            raise AssertionError(
                "original Exercise attempt did not reach expected {0} outcome".format(
                    expect_outcome
                )
            )
        expected_execute_remaining = (
            execute_budget if result["observed_outcome"] == "no-action" else 0
        )
        if result["execute_grant_remaining"] != expected_execute_remaining:
            raise AssertionError("Exercise execution budget did not match the outcome")
        if expect_outcome == "auto" and result["observed_outcome"] not in (
            "complete", "low-hp-quit", "no-action"
        ):
            raise AssertionError("Exercise automatic outcome is not classified")
        if result["observed_outcome"] == "no-action" and strategy != "aggressive" and before > 5:
            raise AssertionError("Exercise retained attempts without a proven preserve threshold")
        if result["refresh_grant_remaining"] > refresh_budget:
            raise AssertionError("Exercise refresh budget increased")
        result["passed"] = True
    except BaseException as exc:
        result["error"] = type(exc).__name__ + ": " + str(exc)
        result["traceback"] = traceback.format_exc()
    finally:
        if instance is not None:
            session = getattr(getattr(instance, "device", None), "semantic_adapter", None)
            if session is not None:
                session.close()
        config_path.unlink(missing_ok=True)
        result["temporary_config_removed"] = not config_path.exists()
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    return {"schema": "alas-headless.exercise-live-validation/v1",
            "driver_revision": driver_revision, **result}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alas-root", type=Path, required=True)
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--serial", required=True)
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--strategy", choices=("aggressive", "sun18", "sun12", "sun0", "sat18", "sat12", "sat0", "fri18"), default="aggressive")
    parser.add_argument("--opponent-trial", type=int, default=1)
    parser.add_argument("--mode", choices=("leftmost", "easiest", "max_exp", "easiest_else_exp"), default="easiest")
    parser.add_argument("--low-hp-threshold", type=float, default=0.0)
    parser.add_argument("--expect-outcome",
                        choices=("complete", "low-hp-quit", "retry-terminal", "no-action", "auto"),
                        default="complete")
    parser.add_argument("--execute-budget", type=int, default=1)
    parser.add_argument("--refresh-budget", type=int, default=0)
    parser.add_argument("--navigate-from-chapter", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    result = validate(args.alas_root.resolve(), args.seed_config, args.serial,
                      args.driver_revision, args.mode, args.strategy,
                      args.opponent_trial, args.low_hp_threshold, args.expect_outcome,
                      args.execute_budget, args.refresh_budget,
                      args.navigate_from_chapter)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json(output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
