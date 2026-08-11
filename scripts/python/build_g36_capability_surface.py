"""Freeze the reviewed G36 source/replay capability requirement surface."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "python"))

from alas_headless import (  # noqa: E402
    ALAS_COMBAT_ACTION_TARGET_NAMES,
    ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES,
    ALAS_COMBAT_NESTED_BRANCH_ROOTS,
    ALAS_COMBAT_REPLAY_RESOURCE_NAMES,
    ALAS_COMBAT_REPLAY_TIMER_BOUNDARIES,
    verify_alas_combat_branch_replay_record,
)
from alas_headless.adapter import load_g36_task_profile  # noqa: E402


SCHEMA = "alas-headless.g36-capability-surface/v1"
_NORMAL_SCHEMA = "alas-headless.g19-combat-state-replay/v1"
_DEFENSIVE_ROOTS = {
    "alternate-result": {
        "resources": [
            "BATTLE_STATUS_A",
            "BATTLE_STATUS_B",
            "BATTLE_STATUS_C",
            "BATTLE_STATUS_D",
            "EXP_INFO_A",
            "EXP_INFO_B",
        ],
        "configuration": [],
    },
    "ambush": {
        "resources": ["MAP_AMBUSH_EVADE"],
        "configuration": ["MAP_HAS_AMBUSH", "Campaign_AmbushEvade"],
    },
    "automation": {
        "resources": [
            "AUTOMATION_CONFIRM",
            "AUTOMATION_CONFIRM_CHECK",
            "AUTOMATION_OFF",
            "AUTOMATION_ON",
        ],
        "configuration": ["Fleet_Fleet1Mode"],
    },
    "guild-popup": {
        "resources": ["GUILD_POPUP_CANCEL", "GUILD_POPUP_CONFIRM"],
        "configuration": [],
    },
    "mis-click": {
        "resources": ["EXERCISE_CHECK", "MUNITIONS_CHECK"],
        "configuration": [],
    },
    "mission-popup": {
        "resources": ["MISSION_POPUP_ACK", "MISSION_POPUP_GO"],
        "configuration": [],
    },
    "network-popup": {
        "resources": ["POPUP_CANCEL", "POPUP_CONFIRM", "POPUP_CONFIRM_WHITE"],
        "configuration": [],
    },
    "retirement": {
        "resources": ["RETIRE_APPEAR_1", "IN_RETIREMENT_CHECK"],
        "configuration": ["Retirement_RetireMode"],
    },
    "story": {
        "resources": ["STORY_SKIP_3", "STORY_LETTERS_ONLY", "STORY_CLOSE"],
        "configuration": ["Campaign_Event", "STORY_ALLOW_SKIP", "STORY_OPTION"],
    },
}
_DEVICE_PATTERN = re.compile(r"^device\.([a-zA-Z_][a-zA-Z0-9_]*)")


class G36CapabilitySurfaceError(RuntimeError):
    """The frozen source/replay surface is incomplete or has drifted."""


def _read_json(path: Path) -> Mapping[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise G36CapabilitySurfaceError() from exc
    if not isinstance(value, Mapping):
        raise G36CapabilitySurfaceError()
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strings(value: Any) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise G36CapabilitySurfaceError()
    return value


def _normal_expected_resources() -> set[str]:
    expected = set(ALAS_COMBAT_REPLAY_RESOURCE_NAMES)
    expected.difference_update(("AUTOMATION_CONFIRM", "EXP_INFO_A", "EXP_INFO_B"))
    return expected


def build_surface(
    *,
    normal_path: Path,
    defensive_path: Path,
    profile_path: Path,
) -> Mapping[str, Any]:
    normal = _read_json(normal_path)
    defensive = _read_json(defensive_path)
    profile = load_g36_task_profile(profile_path)
    if (
        normal.get("schema") != _NORMAL_SCHEMA
        or normal.get("passed") is not True
        or normal.get("input_injected") is not False
        or normal.get("upstream_alas_commit") != profile.upstream_alas_commit
        or normal.get("profile_id") != profile.profile_id
        or normal.get("task_config_sha256") != profile.sha256
        or normal.get("stage") != "12-4"
        or normal.get("expected_end") != "with_searching"
    ):
        raise G36CapabilitySurfaceError()
    verified_defensive = verify_alas_combat_branch_replay_record(defensive)
    if verified_defensive.get("passed") is not True:
        raise G36CapabilitySurfaceError()

    normal_resources = set(_strings(normal.get("resource_query_names")))
    expected_normal_resources = _normal_expected_resources()
    normal_added = sorted(normal_resources - expected_normal_resources)
    normal_removed = sorted(expected_normal_resources - normal_resources)
    if normal_added or normal_removed:
        raise G36CapabilitySurfaceError()

    scenarios = defensive.get("scenarios")
    if not isinstance(scenarios, list):
        raise G36CapabilitySurfaceError()
    defensive_resources: set[str] = set()
    defensive_actions: set[str] = set()
    defensive_sleeps: set[str] = set()
    defensive_device_methods: set[str] = set()
    scenario_names: list[str] = []
    for scenario in scenarios:
        if not isinstance(scenario, Mapping) or not isinstance(
            scenario.get("name"), str
        ):
            raise G36CapabilitySurfaceError()
        scenario_names.append(scenario["name"])
        defensive_resources.update(_strings(scenario.get("resource_queries")))
        defensive_actions.update(_strings(scenario.get("virtual_actions")))
        defensive_sleeps.update(_strings(scenario.get("virtual_sleeps")))
        for call in _strings(scenario.get("call_order")):
            matched = _DEVICE_PATTERN.match(call)
            if matched is not None:
                defensive_device_methods.add(matched.group(1))

    reviewed_resources = set(ALAS_COMBAT_DEFENSIVE_RESOURCE_NAMES)
    unknown_defensive = sorted(defensive_resources - reviewed_resources)
    if unknown_defensive:
        raise G36CapabilitySurfaceError()
    nested = {
        key: list(value) for key, value in ALAS_COMBAT_NESTED_BRANCH_ROOTS.items()
    }
    for name, value in nested.items():
        if _DEFENSIVE_ROOTS.get(name, {}).get("resources") != value:
            raise G36CapabilitySurfaceError()

    observation_requests = set(_strings(normal.get("observation_requests")))
    observation_requests.update("appear:" + name for name in defensive_resources)
    normal_actions = set(_strings(normal.get("virtual_actions")))
    all_observed_actions = normal_actions | defensive_actions
    reviewed_actions = set(ALAS_COMBAT_ACTION_TARGET_NAMES)
    unknown_actions = sorted(
        action
        for action in all_observed_actions
        if not action.startswith("campaign_grid:") and action not in reviewed_actions
    )
    if unknown_actions:
        raise G36CapabilitySurfaceError()

    normal_device_methods = set(_strings(normal.get("device_methods")))
    document = {
        "schema": SCHEMA,
        "upstream_alas_commit": profile.upstream_alas_commit,
        "profile_id": profile.profile_id,
        "task_config_sha256": profile.sha256,
        "normal_replay_sha256": _sha256(normal_path),
        "defensive_replay_sha256": _sha256(defensive_path),
        "input_injected": False,
        "surface": {
            "observation_requests_by_primitive": sorted(observation_requests),
            "direct_typed_state_reads": sorted(
                set(_strings(normal.get("direct_typed_state_reads")))
            ),
            "action_targets": sorted(all_observed_actions),
            "reviewed_possible_action_targets": sorted(reviewed_actions),
            "pixel_accesses": sorted(
                set(_strings(normal.get("pixel_accesses")))
                | {"crop:INFO_BAR_DETECT"}
            ),
            "sleep_boundaries": sorted(
                set(_strings(normal.get("virtual_sleeps"))) | defensive_sleeps
            ),
            "timer_boundaries": sorted(ALAS_COMBAT_REPLAY_TIMER_BOUNDARIES),
            "device_methods": sorted(
                normal_device_methods | defensive_device_methods
            ),
            "configuration_reachable_defensive_roots": {
                name: {
                    "resources": value["resources"],
                    "configuration": value["configuration"],
                    "closure": "requires-h04-review",
                }
                for name, value in sorted(_DEFENSIVE_ROOTS.items())
            },
        },
        "comparison": {
            "g19_normal_resources_added": normal_added,
            "g19_normal_resources_removed": normal_removed,
            "g28_scenario_names": scenario_names,
            "g28_observed_resources_outside_reviewed_surface": unknown_defensive,
            "observed_actions_outside_reviewed_surface": unknown_actions,
        },
        "review": {
            "status": "reviewed-surface-only",
        "normal_reference": "docs/g19-alas-combat-state-replay-validation-report.md",
            "defensive_reference": "integration/alas/combat-defensive-branch-replay-g28.json",
            "capability_promotion": False,
            "production_ready": False,
        },
    }
    return document


def canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ) + "\n"


def parse_args(argv: Sequence[str] = ()) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal", required=True, type=Path)
    parser.add_argument(
        "--defensive",
        type=Path,
        default=ROOT / "integration" / "alas" / "combat-defensive-branch-replay-g28.json",
    )
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
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args(list(argv) if argv else None)


def main(argv: Sequence[str] = ()) -> int:
    arguments = parse_args(argv)
    document = build_surface(
        normal_path=arguments.normal,
        defensive_path=arguments.defensive,
        profile_path=arguments.profile,
    )
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        canonical_json(document), encoding="utf-8", newline="\n"
    )
    print(canonical_json(document), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
