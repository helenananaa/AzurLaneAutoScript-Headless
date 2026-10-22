#!/usr/bin/env python3
"""Run one bounded original ALAS WarArchives campaign on typed Unity state."""

from __future__ import annotations

import argparse
import copy
import dataclasses
import json
import os
import sys
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alas-headless.war-archives-live-validation/v1"
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless.adb_device import resolve_adb_serial  # noqa: E402


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
    payload["Alas"]["Emulator"].update(
        {"Serial": args.serial, "ScreenshotMethod": "ADB"}
    )
    payload["Alas"]["Error"].update({"HandleError": False, "SaveError": False})
    task = payload["WarArchives"]
    task["Scheduler"].update({"Command": "WarArchives", "Enable": True})
    task["Campaign"].update(
        {
            "Name": args.stage,
            "Event": args.event,
            "Mode": args.mode,
            "UseClearMode": True,
            "UseFleetLock": False,
            "UseAutoSearch": args.auto_search,
            "Use2xBook": False,
        }
    )
    task["StopCondition"].update(
        {
            "OilLimit": args.oil_limit,
            "RunCount": 1,
            "MapAchievement": "non_stop",
            "StageIncrease": False,
            "GetNewShip": False,
            "ReachLevel": 0,
        }
    )
    task["Submarine"].update({"Fleet": 0, "Mode": "do_not_use"})
    config_name = f"_codex_war_archives_{uuid.uuid4().hex}"
    config_path = alas_root / "config" / f"{config_name}.json"
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    semantic_env = {
        "ALAS_SEMANTIC_MODE": "1",
        "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
        "ALAS_SEMANTIC_ADB": args.adb,
        "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": "1",
        # Two fleet selections plus ALAS's move-and-return fleet switches.
        "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": "8",
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": "1",
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": "24",
        "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": "24",
        "ALAS_SEMANTIC_CAMPAIGN_CAMERA_POSITIONING_BUDGET": "2",
    }
    prior_env = {name: os.environ.get(name) for name in semantic_env}
    prior_cwd = Path.cwd()
    os.environ.update(semantic_env)
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    instance = None
    started = _now()
    navigation: list[dict[str, Any]] = []
    counters: list[tuple[int, int]] = []
    entry_confirmations: list[dict[str, Any]] = []
    movement_proofs: list[dict[str, Any]] = []
    battle_proofs: list[dict[str, Any]] = []
    execute_restore = None
    resumed_map_before = False
    try:
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript
        from module.campaign.campaign_base import CampaignBase

        if getattr(args, 'max_probe_battles', 0):
            execute_restore = CampaignBase.execute_a_battle
            def bounded_battle(host):
                result = execute_restore(host)
                if host.battle_count >= args.max_probe_battles:
                    proof = host.device.semantic_adapter.confirm_campaign_combat(host.battle_count)
                    battle_proofs.append(dataclasses.asdict(proof))
                    host.withdraw(skip_first_screenshot=False)
                return result
            CampaignBase.execute_a_battle = bounded_battle

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task("WarArchives")
        session = instance.device.semantic_adapter
        adapter = session.open()
        oracle = adapter.oracle
        resumed_map_before = oracle.campaign_is_in_map()

        original_open = session.open_war_archives_campaign
        original_counter = session.war_archives_data_key_count
        original_confirm = session.confirm_war_archives_entry_if_present
        original_finish_movement = session.finish_campaign_movement

        def record_movement(battle_count):
            proof = original_finish_movement(battle_count)
            if proof is not None:
                movement_proofs.append(dict(stage=proof.stage_code,
                    fleet_index=proof.fleet_index, target=proof.target_node,
                    battle_count_before=proof.battle_count_before,
                    battle_count_after=proof.battle_count_after,
                    ammo_before=proof.ammo_before, ammo_after=proof.ammo_after,
                    input_generation=proof.input_generation, map_generation=proof.map_generation,
                    input_path=proof.input_path))
            return proof

        def record_open(event: str, category: str):
            receipt = original_open(event, category)
            navigation.append(
                {
                    "event": event,
                    "category": category,
                    "semantic_id": receipt.semantic_id,
                    "generation": receipt.generation,
                    "path": receipt.path,
                }
            )
            return receipt

        def record_counter():
            value = original_counter()
            counters.append(value)
            return value

        def record_confirm():
            receipt = original_confirm()
            if receipt is not None:
                entry_confirmations.append(
                    {
                        "semantic_id": receipt.semantic_id,
                        "generation": receipt.generation,
                        "path": receipt.path,
                    }
                )
            return receipt

        session.open_war_archives_campaign = record_open
        session.war_archives_data_key_count = record_counter
        session.confirm_war_archives_entry_if_present = record_confirm
        session.finish_campaign_movement = record_movement
        result_value = instance.run("war_archives")
        completion = session.last_campaign_auto_search_completion()
        post = _load(config_path)["WarArchives"]
        passed = bool(
            result_value is True
            and ((navigation and counters) or resumed_map_before)
            and post["StopCondition"]["RunCount"] == 0
            and (not getattr(args, 'max_probe_battles', 0) or bool(battle_proofs))
        )
        return {
            "schema": SCHEMA,
            "passed": passed,
            "started_at": started,
            "finished_at": _now(),
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "event": args.event,
            "stage": args.stage,
            "mode": args.mode,
            "auto_search": args.auto_search,
            "task_result": result_value,
            "movement_proofs": movement_proofs,
            "battle_proofs": battle_proofs,
            "max_probe_battles": getattr(args, 'max_probe_battles', 0),
            "resumed_map_before": resumed_map_before,
            "navigation": navigation,
            "entry_confirmations": entry_confirmations,
            "data_key_observations": [
                {"current": current, "total": total}
                for current, total in counters
            ],
            "run_count_after": post["StopCondition"]["RunCount"],
            "scheduler_enabled_after": post["Scheduler"]["Enable"],
            "scheduler_next_run_after": post["Scheduler"]["NextRun"],
            "auto_search_completion": (
                {
                    "stage": completion.stage_code,
                    "result_generation": completion.result_generation,
                    "result_path": completion.result_path,
                    "waited_seconds": completion.waited_seconds,
                }
                if completion is not None
                else None
            ),
            "raw_input_fallback_used": False,
        }
    except (Exception, SystemExit) as exc:
        return {
            "schema": SCHEMA,
            "passed": False,
            "started_at": started,
            "finished_at": _now(),
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "event": args.event,
            "stage": args.stage,
            "mode": args.mode,
            "resumed_map_before": resumed_map_before,
            "navigation": navigation,
            "entry_confirmations": entry_confirmations,
            "data_key_observations": [
                {"current": current, "total": total}
                for current, total in counters
            ],
            "error": f"{type(exc).__name__}: {exc}",
            "movement_proofs": movement_proofs,
            "battle_proofs": battle_proofs,
            "max_probe_battles": getattr(args, 'max_probe_battles', 0),
            "traceback": traceback.format_exc(),
            "raw_input_fallback_used": False,
        }
    finally:
        if execute_restore is not None:
            CampaignBase.execute_a_battle = execute_restore
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
    parser.add_argument("--serial")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--event", default="war_archives_20190321_en")
    parser.add_argument("--stage", default="A1")
    parser.add_argument("--mode", default="normal", choices=("normal", "hard"))
    parser.add_argument("--auto-search", action="store_true")
    parser.add_argument("--oil-limit", type=int, default=1000)
    parser.add_argument('--max-probe-battles', type=int, default=0,
                        help='Qualification only: verify the last battle and use original withdrawal at this count')
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.max_probe_battles < 0:
        parser.error('--max-probe-battles must be nonnegative')
    return args


def main() -> int:
    args = parse_args()
    args.serial = resolve_adb_serial(args.adb, args.serial)
    result = run(args)
    _write(args.output, result)
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
