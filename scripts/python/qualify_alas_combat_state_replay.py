"""Replay the pinned 12-4 combat chain against a real ALAS checkout.

This qualification is Device-free.  It reconstructs the reviewed G13 dynamic
state on ALAS's own static map and records virtual combat actions only.
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    Bounds,
    CampaignMapCellState,
    CampaignMapEnemyState,
    CampaignMapFleetState,
    CampaignMapPickupState,
    CampaignMapState,
    Point,
    build_alas_campaign_combat_normal_replay_from_observer,
    canonical_alas_campaign_combat_replay,
    load_alas_combat_observer_fixture,
    load_alas_combat_observer_manifest,
    prepare_alas_campaign_combat_admission,
    preview_alas_campaign_decision,
    replay_alas_campaign_combat_state_machine,
    synchronize_alas_campaign_map,
)
from alas_headless.adapter import (  # noqa: E402
    CombatFlow,
    CombatFlowState,
    load_g36_task_profile,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument("--config", default="semantic_e2e")
    parser.add_argument("--include-automation-confirm", action="store_true")
    parser.add_argument("--include-automation-switch", action="store_true")
    parser.add_argument("--include-get-items", action="store_true")
    parser.add_argument("--include-get-mission", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--observer-fixture", type=Path)
    parser.add_argument(
        "--observer-manifest",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-observer-manifest.json",
    )
    parser.add_argument("--semantic-combat-flow", action="store_true")
    parser.add_argument(
        "--profile",
        type=Path,
        default=(
            ROOT
            / "integration"
            / "alas"
            / "profiles"
            / "g36-12-4-normal-one-battle.zero-input.json"
        ),
    )
    return parser.parse_args()


def node(location) -> str:
    return chr(ord("A") + int(location[0])) + str(int(location[1]) + 1)


def build_state(campaign) -> CampaignMapState:
    cells = []
    land = []
    for grid in campaign.MAP:
        grid_node = node(grid.location)
        if grid.is_land:
            land.append(grid_node)
            continue
        column = int(grid.location[0]) + 1
        row = int(grid.location[1]) + 1
        left = float(column * 40)
        top = float(row * 40)
        cells.append(
            CampaignMapCellState(
                row=row,
                column=column,
                node=grid_node,
                button_path=(
                    f"LevelGrid/chapter_cell_quad_{row}_{column}"
                ),
                point=Point(left + 20.0, top + 20.0),
                bounds=Bounds(left, top, left + 40.0, top + 40.0),
            )
        )
    return CampaignMapState(
        generation=4817,
        stage_code="12-4",
        rows=8,
        columns=11,
        cells=tuple(cells),
        land_nodes=tuple(sorted(land)),
        fleets=(
            CampaignMapFleetState(
                "cell_fleet_shengwang_younv", "D6", 5, 5
            ),
            CampaignMapFleetState("cell_fleet_ying", "F8", 5, 5),
        ),
        enemies=(
            CampaignMapEnemyState(
                6,
                3,
                "C6",
                1204050,
                "zl1",
                1,
                "Main",
                113,
                False,
            ),
            CampaignMapEnemyState(
                6,
                4,
                "D6",
                1204090,
                "hm1",
                1,
                "Carrier",
                113,
                True,
            ),
        ),
        pickups=(CampaignMapPickupState(2, 6, "F2", "ammo", "event4"),),
        displayed_fleet_index=1,
        current_fleet_marker="cell_fleet_shengwang_younv",
        current_fleet_roster_sprites=(
            "dulianglai",
            "kewei_younv",
            "linggu",
            "shengwang_younv",
            "xuefeng",
            "zhuiganzhe",
        ),
    )


def build_observer_prebattle_state(snapshots) -> CampaignMapState:
    """Reconstruct the exact same-cell input state preceding reviewed frames."""

    stable = snapshots[-1].campaign_map
    if stable is None:
        raise SystemExit("observer fixture has no stable campaign map")
    marker = stable.current_fleet_marker
    current = tuple(fleet for fleet in stable.fleets if fleet.marker == marker)
    if len(current) != 1:
        raise SystemExit("observer fixture current fleet is ambiguous")
    target = tuple(cell for cell in stable.cells if cell.node == current[0].node)
    if len(target) != 1:
        raise SystemExit("observer fixture target cell is ambiguous")
    if any(enemy.node == current[0].node for enemy in stable.enemies):
        raise SystemExit("observer stable map still has an enemy on target")
    target_cell = target[0]
    return replace(
        stable,
        generation=snapshots[0].generation - 1,
        fleets=tuple(
            replace(item, ammo=item.ammo + 1)
            if item.marker == marker
            else item
            for item in stable.fleets
        ),
        enemies=stable.enemies
        + (
            CampaignMapEnemyState(
                target_cell.row,
                target_cell.column,
                target_cell.node,
                1204080,
                "hm1",
                1,
                "Carrier",
                113,
                True,
            ),
        ),
    )


def main() -> int:
    args = parse_args()
    alas_root = args.alas_root.resolve()
    if args.semantic_combat_flow and args.observer_fixture is None:
        raise SystemExit("semantic combat flow requires an observer fixture")
    if args.observer_fixture is not None and any(
        (
            args.include_automation_confirm,
            args.include_automation_switch,
            args.include_get_items,
            args.include_get_mission,
        )
    ):
        raise SystemExit("observer fixture determines its own phase sequence")
    observer_fixture = (
        args.observer_fixture.resolve()
        if args.observer_fixture is not None
        else None
    )
    observer_manifest = args.observer_manifest.resolve()
    output = args.output.resolve() if args.output is not None else None
    profile = load_g36_task_profile(args.profile)
    actual_commit = subprocess.run(
        ["git", "-C", str(alas_root), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if actual_commit != profile.upstream_alas_commit:
        raise SystemExit("ALAS checkout does not match the G36 task profile")
    if not (alas_root / "campaign" / "campaign_main" / "campaign_12_4.py").is_file():
        raise SystemExit("ALAS checkout is missing pinned campaign_12_4.py")
    sys.path.insert(0, str(alas_root))
    os.chdir(alas_root)

    from campaign.campaign_main.campaign_12_4 import Campaign
    from module.config.config import AzurLaneConfig

    config = AzurLaneConfig(args.config, task="Campaign")
    config.override(
        Emulator_ScreenshotMethod="ADB",
        Emulator_ControlMethod="ADB",
        Campaign_UseAutoSearch=False,
        Campaign_Use2xBook=False,
        Submarine_Mode="do_not_use",
    )
    campaign = Campaign(config, device=SimpleNamespace(semantic_adapter=True))
    profile.require_alas_config(campaign.config)
    snapshots = None
    manifest = None
    if observer_fixture is None:
        state = build_state(campaign)
    else:
        manifest = load_alas_combat_observer_manifest(observer_manifest)
        snapshots = load_alas_combat_observer_fixture(
            observer_fixture, manifest
        )
        state = build_observer_prebattle_state(snapshots)
    projection = synchronize_alas_campaign_map(campaign, state)
    decision = preview_alas_campaign_decision(campaign, projection)
    admission = prepare_alas_campaign_combat_admission(
        decision, state, input_generation=state.generation
    )
    if snapshots is None or manifest is None:
        replay = canonical_alas_campaign_combat_replay(
            admission,
            include_automation_confirm=args.include_automation_confirm,
            include_automation_switch=args.include_automation_switch,
            include_get_items=args.include_get_items,
            include_get_mission=args.include_get_mission,
        )
    else:
        replay = build_alas_campaign_combat_normal_replay_from_observer(
            admission, snapshots, manifest
        )

    source_map_dict = campaign.MAP.__dict__
    source_grid_dicts = {
        tuple(grid.location): grid.__dict__ for grid in campaign.MAP
    }
    result = replay_alas_campaign_combat_state_machine(
        campaign,
        projection,
        decision,
        admission,
        state,
        replay,
        observation_flow_factory=(
            (lambda frame: CombatFlow(CombatFlowState(frame)))
            if args.semantic_combat_flow
            else None
        ),
    )
    source_restored = (
        campaign.MAP.__dict__ is source_map_dict
        and all(
            campaign.MAP[location].__dict__ is grid_dict
            for location, grid_dict in source_grid_dicts.items()
        )
    )
    passed = bool(
        source_restored
        and result.projected_map_unchanged
        and result.battle_count_after == result.battle_count_before + 1
        and result.ammo_after == result.ammo_before - 1
        and result.target_enemy_cleared
        and result.target_fleet_present
        and (not args.semantic_combat_flow or not result.pixel_accesses)
    )
    document = {
        "schema": (
            "alas-headless.g36-normal-observer-replay/v1"
            if observer_fixture is not None
            else "alas-headless.g19-combat-state-replay/v1"
        ),
        "upstream_alas_commit": actual_commit,
        "profile_id": profile.profile_id,
        "task_config_sha256": profile.sha256,
        "passed": passed,
        "input_injected": False,
        "cells": len(state.cells),
        "land": len(state.land_nodes),
        "stage": result.stage_code,
        "target": result.target_node,
        "battle": [
            result.battle_count_before,
            result.battle_count_after,
        ],
        "ammo": [result.ammo_before, result.ammo_after],
        "expected_end": result.expected_end,
        "phases": result.phases,
        "virtual_actions": result.virtual_actions,
        "virtual_sleeps": result.virtual_sleeps,
        "resource_query_count": len(result.resource_queries),
        "resource_query_names": sorted(set(result.resource_queries)),
        "resource_query_unique_count": len(set(result.resource_queries)),
        "observation_requests": sorted(set(result.observation_requests)),
        "direct_typed_state_reads": sorted(
            set(result.direct_typed_state_reads)
        ),
        "device_methods": sorted(set(result.device_methods)),
        "pixel_accesses": sorted(set(result.pixel_accesses)),
        "source_restored": source_restored,
        "projected_map_unchanged": result.projected_map_unchanged,
    }
    if observer_fixture is not None:
        document.update(
            {
                "observer_fixture_sha256": hashlib.sha256(
                    observer_fixture.read_bytes()
                ).hexdigest(),
                "semantic_combat_flow": args.semantic_combat_flow,
                "capability_promotion": False,
                "production_ready": False,
            }
        )
    encoded = json.dumps(
        document,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8", newline="\n")
    print(encoded, end="")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
