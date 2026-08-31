#!/usr/bin/env python3
"""Run one bounded original GemsFarming task against the semantic AVD."""

from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "alas-headless.gems-farming-task-live-validation/v1"
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


def _campaign_page_visible(oracle: Any) -> bool:
    try:
        oracle.campaign_page_state()
        return True
    except Exception as exc:
        if exc.__class__.__name__ not in (
            "SemanticGateClosed",
            "SemanticTargetMissing",
        ):
            raise
        return False


def _recover_formation_startup(
    oracle: Any, *, mode: str = "normal", hard_stage: str = "11-4"
) -> Mapping[str, Any] | None:
    """Leave only the exact normal Formation surface before Campaign starts."""

    if mode == "hard":
        try:
            state = oracle.campaign_fleet_selection_state(hard_stage)
        except Exception as exc:
            if exc.__class__.__name__ not in (
                "SemanticGateClosed",
                "SemanticTargetMissing",
            ):
                raise
        else:
            if state.hard_mode:
                receipt = oracle.click("campaign/fleet-preparation/cancel")
                for _ in range(50):
                    oracle._sleep(0.1)
                    if _campaign_page_visible(oracle):
                        break
                else:
                    raise RuntimeError(
                        "campaign page did not appear after hard fleet back"
                    )
                return {
                    "surface": "hard-fleet-preparation",
                    "semantic_id": receipt.semantic_id,
                    "generation": receipt.generation,
                }

    if any(
        _surface_visible(probe)
        for probe in (
            oracle.main_page_visible,
            oracle.campaign_is_in_map,
            oracle.campaign_menu_is_entry,
        )
    ) or _campaign_page_visible(oracle):
        return None
    state = oracle.read_state()
    dock_back_suffix = "Overlay/UIMain/blur_panel/adapt/top/back"
    dock_backs = tuple(
        item
        for item in state.buttons
        if item.path.endswith(dock_back_suffix)
        and item.name == "back"
        and item.active_in_hierarchy
        and item.active_and_enabled
        and item.interactable
        and item.bounds is not None
        and item.point is not None
    )
    dock_surface = any(
        "/DockyardUI(Clone)/" in item.path for item in state.buttons
    )
    if dock_surface and len(dock_backs) == 1:
        receipt = oracle.click("tactical/dock/back")
        for _ in range(50):
            oracle._sleep(0.1)
            try:
                fleet_state = oracle.campaign_fleet_selection_state(hard_stage)
            except Exception as exc:
                if exc.__class__.__name__ not in (
                    "SemanticGateClosed",
                    "SemanticTargetMissing",
                ):
                    raise
            else:
                if fleet_state.hard_mode:
                    break
        else:
            raise RuntimeError("hard fleet overlay did not appear after Dock back")
        followup = _recover_formation_startup(
            oracle, mode=mode, hard_stage=hard_stage
        )
        return {
            "surface": "hard-replacement-dock",
            "semantic_id": receipt.semantic_id,
            "generation": receipt.generation,
            "followup": followup,
        }
    preparation_back_path = (
        "OverlayCamera/Overlay/UIMain/LevelStageInfoView(Clone)/panel/btnBack"
    )
    preparation_backs = tuple(
        item
        for item in state.buttons
        if item.path == preparation_back_path
        and item.name == "btnBack"
        and item.active_in_hierarchy
        and item.active_and_enabled
        and item.interactable
        and item.bounds is not None
        and item.point is not None
    )
    if len(preparation_backs) == 1:
        receipt = oracle.click("campaign/map-preparation/cancel")
        for _ in range(50):
            oracle._sleep(0.1)
            if _campaign_page_visible(oracle):
                break
        else:
            raise RuntimeError("campaign page did not appear after preparation back")
        return {
            "surface": "map-preparation",
            "semantic_id": receipt.semantic_id,
            "generation": receipt.generation,
        }
    path = "UICamera/Canvas/UIMain/FormationUI(Clone)/blur_panel/top/back_btn"
    buttons = tuple(
        item
        for item in state.buttons
        if item.path == path
        and item.name == "back_btn"
        and item.active_in_hierarchy
        and item.active_and_enabled
        and item.interactable
        and item.bounds is not None
        and item.point is not None
    )
    if len(buttons) != 1:
        raise RuntimeError("GemsFarming startup surface is not reviewed")
    receipt = oracle._gems_equipment_click_button(
        state, buttons[0], "gems-farming/startup/formation/back"
    )

    for _ in range(50):
        oracle._sleep(0.1)
        if _surface_visible(oracle.main_page_visible):
            break
    else:
        raise RuntimeError("main page did not appear after Formation back")
    return {
        "surface": "formation",
        "semantic_id": receipt.semantic_id,
        "generation": receipt.generation,
    }


def _configure(
    seed: Mapping[str, Any], *, mode: str = "normal", hard_stage: str = "11-4"
) -> dict[str, Any]:
    if mode not in ("normal", "hard"):
        raise ValueError("GemsFarming qualification mode must be normal or hard")
    payload = copy.deepcopy(seed)
    isolated_next_run = (
        datetime.now().replace(microsecond=0) + timedelta(hours=1)
    ).strftime("%Y-%m-%d %H:%M:%S")
    for task in payload.values():
        if isinstance(task, dict) and isinstance(task.get("Scheduler"), dict):
            if "Enable" in task["Scheduler"]:
                task["Scheduler"]["Enable"] = False
            if "NextRun" in task["Scheduler"]:
                task["Scheduler"]["NextRun"] = isolated_next_run
    target = payload["GemsFarming"]
    target["Scheduler"].update(
        {
            "Command": "GemsFarming",
            "Enable": True,
            "NextRun": "2020-01-01 00:00:00",
        }
    )
    target["GemsFarming"].update(
        {
            "ChangeFlagship": "ship_equip" if mode == "normal" else "ship",
            "CommonCV": "ranger",
            "ChangeVanguard": "disabled",
            "CommonDD": "any",
            "CommissionLimit": False,
        }
    )
    target["EquipmentCode"]["ExportToConfig"] = True
    target["Campaign"].update(
        {
            "Name": "1-1" if mode == "normal" else hard_stage,
            "Event": "campaign_main",
            "Mode": mode,
            "UseClearMode": False,
            "UseFleetLock": False,
            "UseAutoSearch": False,
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
    target["Fleet"].update(
        {
            "Fleet1": 6 if mode == "normal" else 1,
            "Fleet2": 0 if mode == "normal" else 2,
            "FleetOrder": "fleet1_all_fleet2_standby",
        }
    )
    target["Submarine"].update(
        {"Fleet": 0, "Mode": "do_not_use"}
    )
    target["Emotion"].update(
        {
            "Mode": "calculate_ignore",
            "Fleet1Value": 150,
            "Fleet1Record": _utc_now().replace("T", " ")[:19],
            "Fleet1Recover": "not_in_dormitory",
            "Fleet1Oath": False,
        }
    )
    return payload


def run(args: argparse.Namespace) -> Mapping[str, Any]:
    alas_root = args.alas_root.resolve()
    seed_path = alas_root / "config" / f"{args.seed_config}.json"
    payload = _configure(
        _load_json(seed_path), mode=args.mode, hard_stage=args.hard_stage
    )
    config_name = f"_codex_gems_farming_live_{uuid.uuid4().hex}"
    config_path = alas_root / "config" / f"{config_name}.json"
    config_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    environment = {
        "ALAS_SEMANTIC_MODE": "1",
        "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
        "ALAS_SEMANTIC_ADB": args.adb,
        "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": "1",
        "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": "4",
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": str(args.sortie_budget),
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": str(args.combat_budget),
        "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": str(
            args.viewport_swipe_budget
        ),
    }
    prior_env = {name: os.environ.get(name) for name in environment}
    os.environ.update(environment)
    for path in (ROOT / "python", alas_root):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    prior_cwd = Path.cwd()
    instance = None
    started_at = _utc_now()
    try:
        random.seed(args.random_seed)
        os.chdir(alas_root)
        from alas import AzurLaneAutoScript

        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task("GemsFarming")
        # EventGeneral is bound ahead of GemsFarming and therefore owns shared
        # Campaign/Fleet/StopCondition arguments.  Pin this one qualification
        # run through ALAS' normal runtime override mechanism, as the Event
        # task live runner does, rather than relying on the shadowed JSON group.
        stage = "1-1" if args.mode == "normal" else args.hard_stage
        fleet_index = 6 if args.mode == "normal" else 1
        change_flagship = "ship_equip" if args.mode == "normal" else "ship"
        instance.config.override(
            Campaign_Event="campaign_main",
            Campaign_Name=stage,
            Campaign_Mode=args.mode,
            Campaign_UseClearMode=False,
            Campaign_UseFleetLock=False,
            Campaign_UseAutoSearch=False,
            Campaign_Use2xBook=False,
            StopCondition_OilLimit=0,
            StopCondition_MapAchievement="non_stop",
            StopCondition_StageIncrease=False,
            StopCondition_GetNewShip=False,
            StopCondition_ReachLevel=0,
            Fleet_Fleet1=fleet_index,
            Fleet_Fleet2=0 if args.mode == "normal" else 2,
            Fleet_FleetOrder="fleet1_all_fleet2_standby",
            Submarine_Fleet=0,
            Submarine_Mode="do_not_use",
        )
        # RunCount is deliberately mutable: CampaignRun decrements it and its
        # stop condition persists zero.  Keeping it in ``overridden`` would
        # reapply one after every config reload and permit another stage.
        instance.config.StopCondition_RunCount = 1
        session = instance.device.semantic_adapter
        oracle = session.open().oracle
        runtime_configuration = {
            "campaign_name": instance.config.Campaign_Name,
            "campaign_mode": instance.config.Campaign_Mode,
            "fleet1": instance.config.Fleet_Fleet1,
            "run_count": instance.config.StopCondition_RunCount,
            "change_flagship": instance.config.GemsFarming_ChangeFlagship,
            "common_cv": instance.config.GemsFarming_CommonCV,
            "change_vanguard": instance.config.GemsFarming_ChangeVanguard,
        }
        expected_configuration = {
            "campaign_name": stage,
            "campaign_mode": args.mode,
            "fleet1": fleet_index,
            "run_count": 1,
            "change_flagship": change_flagship,
            "common_cv": "ranger",
            "change_vanguard": "disabled",
        }
        if runtime_configuration != expected_configuration:
            raise RuntimeError(
                "GemsFarming runtime configuration changed: "
                + repr(runtime_configuration)
            )
        startup_recovery = _recover_formation_startup(
            oracle, mode=args.mode, hard_stage=stage
        )
        starting_state = oracle.read_state()
        starting_surface = {
            "main_page": _surface_visible(oracle.main_page_visible),
            "campaign_map": _surface_visible(oracle.campaign_is_in_map),
            "campaign_entry": _surface_visible(oracle.campaign_menu_is_entry),
            "campaign_page": _campaign_page_visible(oracle),
            "generation": starting_state.generation,
        }

        hard_preparation = None
        hard_replacement_trace: dict[str, Any] | None = None
        if args.mode == "hard":
            try:
                before = oracle._gems_farming_hard_role_cards(
                    stage, 1, "flagship"
                )[3]
            except Exception as exc:
                if exc.__class__.__name__ not in (
                    "SemanticGateClosed",
                    "SemanticTargetMissing",
                ):
                    raise
                before = ()
                after = ()
                semantic_id = "gems-farming/hard/vacancy-offsurface"
                generation = oracle.read_state().generation
            else:
                if len(before) == 3:
                    receipt = session.gems_farming_hard_unmount(
                        stage, 1, "flagship"
                    )
                    after = oracle._gems_farming_hard_role_cards(
                        stage, 1, "flagship"
                    )[3]
                    if after != before[1:]:
                        raise RuntimeError(
                            "typed hard flagship vacancy was not proven"
                        )
                    semantic_id = receipt.semantic_id
                    generation = receipt.generation
                elif len(before) == 2:
                    after = before
                    semantic_id = "gems-farming/hard/existing-vacancy"
                    generation = oracle.read_state().generation
                else:
                    raise RuntimeError("hard flagship row has an unexpected size")
            hard_preparation = {
                "before": list(before),
                "after_unmount": list(after),
                "semantic_id": semantic_id,
                "generation": generation,
            }

            hard_replacement_trace = {"open_calls": 0, "confirmed": []}
            original_hard_open = session.gems_farming_hard_open_slot
            original_hard_satisfied = (
                session.campaign_fleet_operator_hard_satisfied
            )
            original_candidates = session.gems_farming_candidates
            original_confirm = session.gems_farming_confirm_candidate_selection
            original_favourite = oracle.set_enhancement_dock_favourite
            seeded_hard_vacancy = False

            def traced_hard_satisfied(row_key: str) -> Any:
                nonlocal seeded_hard_vacancy
                if (
                    args.seed_hard_vacancy
                    and row_key == "fleet1"
                    and not seeded_hard_vacancy
                ):
                    before = oracle._gems_farming_hard_role_cards(
                        stage, 1, "flagship"
                    )[3]
                    if len(before) != 3:
                        raise RuntimeError(
                            "hard vacancy seed requires a full flagship row"
                        )
                    receipt = session.gems_farming_hard_unmount(
                        stage, 1, "flagship"
                    )
                    after = oracle._gems_farming_hard_role_cards(
                        stage, 1, "flagship"
                    )[3]
                    if after != before[1:]:
                        raise RuntimeError(
                            "hard vacancy seed postcondition was not proven"
                        )
                    assert hard_replacement_trace is not None
                    hard_replacement_trace["seed_vacancy"] = {
                        "before": list(before),
                        "after": list(after),
                        "semantic_id": receipt.semantic_id,
                        "generation": receipt.generation,
                    }
                    seeded_hard_vacancy = True
                return original_hard_satisfied(row_key)

            def favourite_layers() -> list[dict[str, Any]]:
                _, current_ui = oracle._enhancement_dock_records()
                return [
                    {
                        "path": item.path,
                        "sprite": item.sprite,
                        "active_in_hierarchy": item.active_in_hierarchy,
                        "active_and_enabled": item.active_and_enabled,
                        "raycast_target": item.raycast_target,
                    }
                    for item in current_ui.images
                    if "/switch/toggles/preference_toggle/" in item.path
                ]

            def traced_favourite(enabled: bool) -> Any:
                assert hard_replacement_trace is not None
                observation = {
                    "requested": enabled,
                    "before": favourite_layers(),
                }
                receipt = original_favourite(enabled)
                observation["receipt"] = (
                    None
                    if receipt is None
                    else {
                        "semantic_id": receipt.semantic_id,
                        "generation": receipt.generation,
                    }
                )
                observation["after"] = favourite_layers()
                hard_replacement_trace.setdefault("favourite", []).append(
                    observation
                )
                return receipt

            def traced_hard_open(*values: Any, **keywords: Any) -> Any:
                assert hard_replacement_trace is not None
                hard_replacement_trace["open_calls"] += 1
                preparation = oracle.campaign_fleet_selection_state(stage)
                current_ui = oracle.read_ui_state()
                hard_replacement_trace["fleet_preparation"] = {
                    "hard_requirements": [
                        {
                            "label": item.label,
                            "comparator": item.comparator,
                            "target": item.target,
                            "actual": item.actual,
                        }
                        for item in preparation.hard_requirements
                    ],
                    "ship_list_images": [
                        {
                            "path": item.path,
                            "name": item.name,
                            "sprite": item.sprite,
                        }
                        for item in current_ui.images
                        if "LevelFleetSelectView(Clone)/panel/ShipList/fleet/"
                        in item.path
                        and item.active_in_hierarchy
                        and item.active_and_enabled
                        and not item.truncated
                    ],
                    "ship_list_texts": [
                        {"path": item.path, "text": item.text}
                        for item in current_ui.texts
                        if "LevelFleetSelectView(Clone)/panel/ShipList/fleet/"
                        in item.path
                        and item.active_in_hierarchy
                        and item.active_and_enabled
                        and not item.truncated
                    ],
                }
                return original_hard_open(*values, **keywords)

            def traced_confirm(candidate: Any, role: str) -> Any:
                receipt = original_confirm(candidate, role)
                assert hard_replacement_trace is not None
                hard_replacement_trace["confirmed"].append(
                    {
                        "role": role,
                        "ship_id": candidate.ship_id,
                        "ship_name": candidate.ship_name,
                        "ship_sprite": candidate.ship_sprite,
                        "level": candidate.level,
                        "emotion": candidate.emotion,
                    }
                )
                return receipt

            def traced_candidates(*values: Any, **keywords: Any) -> Any:
                candidates = original_candidates(*values, **keywords)
                assert hard_replacement_trace is not None
                hard_replacement_trace["eligible_candidates"] = [
                    {
                        "ship_id": item.ship_id,
                        "ship_name": item.ship_name,
                        "ship_sprite": item.ship_sprite,
                        "ship_type": item.ship_type,
                        "rarity": item.rarity,
                        "level": item.level,
                        "emotion": item.emotion,
                        "fleet_index": item.fleet_index,
                        "status": item.status,
                    }
                    for item in candidates
                ]
                if not candidates:
                    button_state = oracle.read_state()
                    hard_replacement_trace["dock_buttons"] = [
                        {
                            "name": item.name,
                            "path": item.path,
                            "actionable": item.actionable,
                            "bounds": (
                                None
                                if item.bounds is None
                                else {
                                    "left": item.bounds.left,
                                    "top": item.bounds.top,
                                    "right": item.bounds.right,
                                    "bottom": item.bounds.bottom,
                                }
                            ),
                        }
                        for item in button_state.buttons
                        if "DockyardUI(Clone)" in item.path
                        or "ship_container/ships" in item.path
                    ]
                    hard_replacement_trace["typed_dock_candidates"] = [
                        {
                            "ship_id": item.ship_id,
                            "ship_name": item.ship_name,
                            "ship_sprite": item.ship_sprite,
                            "ship_type": item.ship_type,
                            "rarity": item.rarity,
                            "level": item.level,
                            "emotion": item.emotion,
                            "fleet_index": item.fleet_index,
                            "status": item.status,
                        }
                        for item in oracle.gems_farming_dock_candidates()
                    ]
                    oracle.set_gems_farming_dock_filter(
                        "flagship", ("all",), enhanceable_only=False
                    )
                    hard_replacement_trace["no_limit_typed_candidates"] = [
                        {
                            "ship_id": item.ship_id,
                            "ship_name": item.ship_name,
                            "ship_sprite": item.ship_sprite,
                            "ship_type": item.ship_type,
                            "rarity": item.rarity,
                            "level": item.level,
                            "emotion": item.emotion,
                            "fleet_index": item.fleet_index,
                            "status": item.status,
                        }
                        for item in oracle.gems_farming_dock_candidates()
                    ]
                    oracle.set_enhancement_dock_filter(
                        None, enhanceable_only=False
                    )
                    hard_replacement_trace["unfiltered_visible_cards"] = [
                        {
                            "ship_id": item.ship_id,
                            "ship_name": item.ship_name,
                            "level": item.level,
                        }
                        for item in oracle.enhancement_dock_candidates()
                    ]
                    if args.output is not None:
                        output_path = args.output
                        if not output_path.is_absolute():
                            output_path = prior_cwd / output_path
                        probe_path = output_path.with_suffix(".dock-probe.json")
                        probe_path.parent.mkdir(parents=True, exist_ok=True)
                        probe_path.write_text(
                            json.dumps(
                                hard_replacement_trace,
                                ensure_ascii=False,
                                indent=2,
                            )
                            + "\n",
                            encoding="utf-8",
                        )
                return candidates

            session.gems_farming_hard_open_slot = traced_hard_open
            session.campaign_fleet_operator_hard_satisfied = traced_hard_satisfied
            session.gems_farming_candidates = traced_candidates
            session.gems_farming_confirm_candidate_selection = traced_confirm
            oracle.set_enhancement_dock_favourite = traced_favourite

        run_result = instance.run("gems_farming")
        post = _load_json(config_path)["GemsFarming"]
        state = oracle.read_state()
        run_count = post["StopCondition"]["RunCount"]
        scheduler_enabled = post["Scheduler"]["Enable"]
        hard_replacement_required = args.mode == "hard" and args.seed_hard_vacancy
        hard_replacement_passed = (
            not hard_replacement_required
            or (
                hard_replacement_trace is not None
                and hard_replacement_trace["open_calls"] == 1
                and len(hard_replacement_trace["confirmed"]) == 1
                and hard_replacement_trace["confirmed"][0]["role"] == "flagship"
                and hard_replacement_trace["confirmed"][0]["ship_sprite"]
                == "tujizhe"
            )
        )
        task_completion_passed = (
            bool(run_result)
            and run_count == 0
            and scheduler_enabled is False
        )
        passed = task_completion_passed and hard_replacement_passed
        return {
            "schema": SCHEMA,
            "passed": passed,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "task": "GemsFarming",
            "task_method": "AzurLaneAutoScript.gems_farming",
            "campaign_run_method": "GemsFarming.run",
            "stage": stage,
            "event": "campaign_main",
            "mode": args.mode,
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "configuration": {
                "change_flagship": change_flagship,
                "common_cv": "ranger",
                "change_vanguard": "disabled",
                "run_count_before": 1,
                "run_count_after": run_count,
                "scheduler_enabled_after": scheduler_enabled,
            },
            "run_result": bool(run_result),
            "qualification": {
                "task_completion_passed": task_completion_passed,
                "hard_replacement_required": hard_replacement_required,
                "hard_replacement_passed": hard_replacement_passed,
            },
            "starting_surface": starting_surface,
            "startup_recovery": startup_recovery,
            "hard_preparation": hard_preparation,
            "hard_replacement_trace": hard_replacement_trace,
            "final_surface": {
                "main_page": _surface_visible(oracle.main_page_visible),
                "campaign_map": _surface_visible(oracle.campaign_is_in_map),
                "campaign_entry": _surface_visible(oracle.campaign_menu_is_entry),
                "campaign_page": _campaign_page_visible(oracle),
            },
            "budgets": {
                "stage_entry": 1,
                "fleet_mutation": 4,
                "sortie": args.sortie_budget,
                "combat": args.combat_budget,
                "viewport_swipe": args.viewport_swipe_budget,
            },
            "observer": {
                "generation": state.generation,
                "scene_handle": state.scene_handle,
                "button_count": len(state.buttons),
            },
            "raw_input_fallback_used": False,
            "qualification_random_seed": args.random_seed,
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
    parser.add_argument("--serial")
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--seed-config", default="semantic_e2e")
    parser.add_argument("--mode", choices=("normal", "hard"), default="normal")
    parser.add_argument("--hard-stage", default="11-4")
    parser.add_argument("--seed-hard-vacancy", action="store_true")
    parser.add_argument("--sortie-budget", type=int, default=1)
    parser.add_argument("--combat-budget", type=int, default=8)
    parser.add_argument("--viewport-swipe-budget", type=int, default=4)
    parser.add_argument("--random-seed", type=int, default=20260825)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if (
        args.sortie_budget < 0
        or args.combat_budget < 0
        or args.viewport_swipe_budget < 0
    ):
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
