#!/usr/bin/env python3
"""Run the bounded Hard 11-4 task against the pinned semantic AVD."""

from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alas-headless.hard-live-validation/v1"


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


def run(args: argparse.Namespace) -> Mapping[str, Any]:
    alas_root = args.alas_root.resolve()
    seed = _load(alas_root / "config" / f"{args.seed_config}.json")
    payload = copy.deepcopy(seed)
    payload["Hard"]["Scheduler"].update(
        {"Command": "Hard", "Enable": True}
    )
    payload["Hard"]["Hard"].update(
        {"HardStage": args.stage, "HardFleet": args.hard_fleet}
    )
    config_name = f"_codex_hard_live_{uuid.uuid4().hex}"
    config_path = alas_root / "config" / f"{config_name}.json"
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    budget_names = {
        "ALAS_SEMANTIC_MODE": "1",
        "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
        "ALAS_SEMANTIC_ADB": args.adb,
        "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": (
            "0" if args.manual_resume else "1"
        ),
        "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": (
            "1" if args.manual_resume else "2"
        ),
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": str(args.sortie_budget),
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": (
            "10" if (args.manual_resume or args.manual_clear_start) else "0"
        ),
        "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": (
            "10" if (args.manual_resume or args.manual_clear_start) else "0"
        ),
        "ALAS_SEMANTIC_HARD_MANUAL_CLEAR": (
            "1" if args.manual_clear_start else "0"
        ),
    }
    prior_env = {name: os.environ.get(name) for name in budget_names}
    prior_cwd = Path.cwd()
    os.environ.update(budget_names)
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    instance = None
    started = _now()
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task("Hard")
        instance.run("hard")
        session = instance.device.semantic_adapter
        completion = session.last_campaign_auto_search_completion()
        post = _load(config_path)["Hard"]
        result = {
            "schema": SCHEMA,
            "passed": (
                args.manual_resume
                or args.manual_clear_start
                or completion is not None
            ),
            "started_at": started,
            "finished_at": _now(),
            "stage": args.stage,
            "hard_fleet": args.hard_fleet,
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "sortie_budget": args.sortie_budget,
            "manual_resume": args.manual_resume,
            "manual_clear_start": args.manual_clear_start,
            "scheduler_enabled_after": post["Scheduler"]["Enable"],
            "scheduler_next_run_after": post["Scheduler"]["NextRun"],
            "auto_search_completion": (
                {
                    "stage": completion.stage_code,
                    "result_generation": completion.result_generation,
                    "result_path": completion.result_path,
                    "fleet1_role": completion.fleet1_role,
                    "fleet2_role": completion.fleet2_role,
                    "waited_seconds": completion.waited_seconds,
                    "combat_auto_generation": completion.combat_auto_generation,
                    "combat_auto_proven": completion.combat_auto_proven,
                    "passive_after_sortie": completion.passive_after_sortie,
                }
                if completion is not None
                else None
            ),
            "raw_input_fallback_used": False,
        }
        return result
    except Exception as exc:
        return {
            "schema": SCHEMA,
            "passed": False,
            "started_at": started,
            "finished_at": _now(),
            "stage": args.stage,
            "hard_fleet": args.hard_fleet,
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "sortie_budget": args.sortie_budget,
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "raw_input_fallback_used": False,
        }
    finally:
        if instance is not None:
            device = getattr(instance, "__dict__", {}).get("device")
            session = getattr(device, "__dict__", {}).get("semantic_adapter")
            if session is not None:
                session.close()
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
    parser.add_argument("--stage", default="11-4")
    parser.add_argument("--hard-fleet", type=int, default=1, choices=(1, 2))
    parser.add_argument("--sortie-budget", type=int, default=3, choices=(1, 2, 3))
    parser.add_argument("--manual-resume", action="store_true")
    parser.add_argument("--manual-clear-start", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args)
    _write(args.output, result)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
