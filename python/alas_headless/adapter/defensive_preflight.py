"""Explicit H04 defensive closure for the frozen G36 qualification slice."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Tuple

from ..alas_combat_observer import (
    AlasCombatObserverManifest,
    alas_combat_observer_manifest_to_json,
)
from ..semantic_oracle import SemanticGateClosed
from .policy import RecoveryPolicy, RunPolicy
from .task_profile import G36TaskProfile


G36_DEFENSIVE_PREFLIGHT_SCHEMA = "alas-headless.g36-defensive-preflight/v1"
G36_DEFENSIVE_ROOT_SPECS: Mapping[str, Mapping[str, Tuple[str, ...]]] = (
    MappingProxyType(
        {
            "alternate-result": MappingProxyType(
                {
                    "resources": (
                        "BATTLE_STATUS_A",
                        "BATTLE_STATUS_B",
                        "BATTLE_STATUS_C",
                        "BATTLE_STATUS_D",
                        "EXP_INFO_A",
                        "EXP_INFO_B",
                    ),
                    "actions": (
                        "BATTLE_STATUS_A",
                        "BATTLE_STATUS_B",
                        "BATTLE_STATUS_C",
                        "BATTLE_STATUS_D",
                        "EXP_INFO_A",
                        "EXP_INFO_B",
                    ),
                    "scenarios": (
                        "battle-status-a",
                        "battle-status-b",
                        "battle-status-c",
                        "battle-status-d",
                        "exp-info-a",
                        "exp-info-b",
                    ),
                }
            ),
            "ambush": MappingProxyType(
                {
                    "resources": ("MAP_AMBUSH_EVADE",),
                    "actions": ("MAP_AMBUSH_EVADE",),
                    "scenarios": ("ambush-evade-success",),
                }
            ),
            "automation": MappingProxyType(
                {
                    "resources": (
                        "AUTOMATION_CONFIRM",
                        "AUTOMATION_CONFIRM_CHECK",
                        "AUTOMATION_OFF",
                        "AUTOMATION_ON",
                    ),
                    "actions": (
                        "AUTOMATION_CONFIRM",
                        "AUTOMATION_SWITCH",
                        "BATTLE_PREPARATION",
                    ),
                    "scenarios": (),
                }
            ),
            "guild-popup": MappingProxyType(
                {
                    "resources": (
                        "GUILD_POPUP_CANCEL",
                        "GUILD_POPUP_CONFIRM",
                    ),
                    "actions": (
                        "GUILD_POPUP_CANCEL",
                        "GUILD_POPUP_CONFIRM",
                    ),
                    "scenarios": (
                        "guild-popup-confirm",
                        "guild-popup-cancel",
                    ),
                }
            ),
            "mis-click": MappingProxyType(
                {
                    "resources": ("EXERCISE_CHECK", "MUNITIONS_CHECK"),
                    "actions": (),
                    "scenarios": (),
                }
            ),
            "mission-popup": MappingProxyType(
                {
                    "resources": ("MISSION_POPUP_ACK", "MISSION_POPUP_GO"),
                    "actions": ("MISSION_POPUP_ACK", "MISSION_POPUP_GO"),
                    "scenarios": (
                        "mission-popup-go",
                        "mission-popup-ack",
                    ),
                }
            ),
            "network-popup": MappingProxyType(
                {
                    "resources": (
                        "POPUP_CANCEL",
                        "POPUP_CONFIRM",
                        "POPUP_CONFIRM_WHITE",
                    ),
                    "actions": (
                        "POPUP_CANCEL",
                        "POPUP_CONFIRM",
                        "POPUP_CONFIRM_WHITE",
                    ),
                    "scenarios": (),
                }
            ),
            "retirement": MappingProxyType(
                {
                    "resources": ("RETIRE_APPEAR_1", "IN_RETIREMENT_CHECK"),
                    "actions": ("RETIRE_APPEAR_1",),
                    "scenarios": (
                        "retirement-entry",
                        "retirement-dispatch",
                    ),
                }
            ),
            "story": MappingProxyType(
                {
                    "resources": (
                        "STORY_SKIP_3",
                        "STORY_LETTERS_ONLY",
                        "STORY_CLOSE",
                    ),
                    "actions": (
                        "STORY_SKIP",
                        "STORY_LETTERS_ONLY",
                        "STORY_CLOSE",
                    ),
                    "scenarios": (
                        "story-letters-only",
                        "story-skip",
                        "story-close",
                    ),
                }
            ),
        }
    )
)


class DefensiveResolution(str, Enum):
    QUALIFIED_EVIDENCE = "qualified-evidence"
    QUALIFICATION_STOP = "qualification-stop"


@dataclass(frozen=True)
class DefensivePreflightRow:
    root: str
    configuration: Tuple[str, ...]
    configuration_values: Tuple[Tuple[str, Any], ...]
    resources: Tuple[str, ...]
    actions: Tuple[str, ...]
    qualified_resources: Tuple[str, ...]
    missing_resources: Tuple[str, ...]
    qualified_actions: Tuple[str, ...]
    missing_actions: Tuple[str, ...]
    source_scenarios: Tuple[str, ...]
    resolution: DefensiveResolution
    recovery_before_grid: bool
    implicit_unknown: bool = False


@dataclass(frozen=True)
class G36DefensivePreflightReport:
    profile_id: str
    upstream_alas_commit: str
    task_config_sha256: str
    capability_surface_sha256: str
    observer_manifest_sha256: str
    normal_replay_sha256: str
    defensive_replay_sha256: str
    run_policy_sha256: str
    stop_boundary: str
    recovery_policy: str
    rows: Tuple[DefensivePreflightRow, ...]
    closure_complete: bool
    grid_click_allowed: bool
    input_injected: bool = False
    capability_promotion: bool = False
    production_ready: bool = False


def _sha256_json(value: Mapping[str, Any]) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _qualified_resource_names(
    manifest: AlasCombatObserverManifest,
) -> frozenset[str]:
    return frozenset(
        mapping.resource_name for mapping in manifest.resources if mapping.qualified
    )


def _qualified_action_names(
    manifest: AlasCombatObserverManifest,
) -> frozenset[str]:
    return frozenset(
        mapping.action_name for mapping in manifest.actions if mapping.qualified
    )


def build_g36_defensive_preflight(
    *,
    profile: G36TaskProfile,
    surface: Mapping[str, Any],
    manifest: AlasCombatObserverManifest,
    normal_replay: Mapping[str, Any],
    defensive_replay: Mapping[str, Any],
    policy: RunPolicy,
) -> G36DefensivePreflightReport:
    """Close every H02 root explicitly without granting the grid click."""

    if not isinstance(profile, G36TaskProfile):
        raise SemanticGateClosed("defensive preflight profile is not typed")
    if not isinstance(manifest, AlasCombatObserverManifest):
        raise SemanticGateClosed("defensive preflight manifest is not typed")
    if not isinstance(policy, RunPolicy):
        raise SemanticGateClosed("defensive preflight policy is not typed")
    if policy.profile_id != profile.profile_id:
        raise SemanticGateClosed("defensive preflight policy profile changed")
    if policy.identity.task_config_sha256 != profile.sha256:
        raise SemanticGateClosed("defensive preflight task hash changed")
    if policy.recovery_policy is not RecoveryPolicy.QUALIFICATION_STOP:
        raise SemanticGateClosed("defensive preflight requires qualification-stop")
    if policy.deadline_seconds != 0 or any(policy.grants.values()):
        raise SemanticGateClosed("defensive preflight policy must remain zero-input")

    if (
        surface.get("schema") != "alas-headless.g36-capability-surface/v1"
        or surface.get("profile_id") != profile.profile_id
        or surface.get("task_config_sha256") != profile.sha256
        or surface.get("upstream_alas_commit") != profile.upstream_alas_commit
    ):
        raise SemanticGateClosed("defensive preflight capability surface changed")
    roots = surface.get("surface", {}).get(
        "configuration_reachable_defensive_roots"
    )
    if not isinstance(roots, Mapping) or set(roots) != set(
        G36_DEFENSIVE_ROOT_SPECS
    ):
        raise SemanticGateClosed("defensive preflight root inventory changed")
    possible_actions = set(
        surface.get("surface", {}).get("reviewed_possible_action_targets", ())
    )
    required_actions = {
        action
        for spec in G36_DEFENSIVE_ROOT_SPECS.values()
        for action in spec["actions"]
    }
    if not required_actions.issubset(possible_actions):
        raise SemanticGateClosed("defensive preflight action inventory changed")
    if (
        normal_replay.get("schema")
        != "alas-headless.g36-normal-observer-replay/v1"
        or normal_replay.get("passed") is not True
        or normal_replay.get("input_injected") is not False
        or normal_replay.get("production_ready") is not False
    ):
        raise SemanticGateClosed("defensive preflight normal replay changed")
    if (
        defensive_replay.get("schema")
        != "alas-headless.g28-combat-defensive-branch-replay/v1"
        or defensive_replay.get("passed") is not True
        or defensive_replay.get("source_restored") is not True
        or defensive_replay.get("input_injected") is not False
    ):
        raise SemanticGateClosed("defensive branch replay changed")
    observed_scenarios = tuple(
        scenario.get("name") for scenario in defensive_replay.get("scenarios", ())
    )
    expected_scenarios = tuple(
        scenario
        for spec in G36_DEFENSIVE_ROOT_SPECS.values()
        for scenario in spec["scenarios"]
    )
    if len(observed_scenarios) != 16 or set(observed_scenarios) != set(
        expected_scenarios
    ):
        raise SemanticGateClosed("defensive branch scenario inventory changed")

    qualified_resources = _qualified_resource_names(manifest)
    qualified_actions = _qualified_action_names(manifest)
    rows = []
    for root in sorted(G36_DEFENSIVE_ROOT_SPECS):
        spec = G36_DEFENSIVE_ROOT_SPECS[root]
        surface_row = roots[root]
        if (
            not isinstance(surface_row, Mapping)
            or tuple(surface_row.get("resources", ())) != spec["resources"]
        ):
            raise SemanticGateClosed(
                "defensive preflight root resources changed: " + root
            )
        configuration = tuple(surface_row.get("configuration", ()))
        if any(name not in profile.alas_config for name in configuration):
            raise SemanticGateClosed(
                "defensive preflight configuration is absent: " + root
            )
        resources = spec["resources"]
        actions = spec["actions"]
        present_resources = tuple(
            name for name in resources if name in qualified_resources
        )
        present_actions = tuple(name for name in actions if name in qualified_actions)
        missing_resources = tuple(
            name for name in resources if name not in qualified_resources
        )
        missing_actions = tuple(
            name for name in actions if name not in qualified_actions
        )
        fully_qualified = not missing_resources and not missing_actions
        resolution = (
            DefensiveResolution.QUALIFIED_EVIDENCE
            if fully_qualified
            else DefensiveResolution.QUALIFICATION_STOP
        )
        rows.append(
            DefensivePreflightRow(
                root=root,
                configuration=configuration,
                configuration_values=tuple(
                    (name, profile.alas_config[name]) for name in configuration
                ),
                resources=resources,
                actions=actions,
                qualified_resources=present_resources,
                missing_resources=missing_resources,
                qualified_actions=present_actions,
                missing_actions=missing_actions,
                source_scenarios=spec["scenarios"],
                resolution=resolution,
                recovery_before_grid=not fully_qualified,
            )
        )
    closure_complete = bool(
        rows
        and all(
            not row.implicit_unknown
            and (
                row.resolution is DefensiveResolution.QUALIFIED_EVIDENCE
                or (
                    row.resolution is DefensiveResolution.QUALIFICATION_STOP
                    and row.recovery_before_grid
                )
            )
            for row in rows
        )
    )
    return G36DefensivePreflightReport(
        profile_id=profile.profile_id,
        upstream_alas_commit=profile.upstream_alas_commit,
        task_config_sha256=profile.sha256,
        capability_surface_sha256=_sha256_json(surface),
        observer_manifest_sha256=_sha256_json(
            alas_combat_observer_manifest_to_json(manifest)
        ),
        normal_replay_sha256=_sha256_json(normal_replay),
        defensive_replay_sha256=_sha256_json(defensive_replay),
        run_policy_sha256=policy.sha256,
        stop_boundary=profile.qualification["preflight_stop_boundary"],
        recovery_policy=policy.recovery_policy.value,
        rows=tuple(rows),
        closure_complete=closure_complete,
        grid_click_allowed=closure_complete
        and all(
            row.resolution is DefensiveResolution.QUALIFIED_EVIDENCE
            for row in rows
        ),
    )


def g36_defensive_preflight_to_json(
    report: G36DefensivePreflightReport,
) -> Mapping[str, Any]:
    if not isinstance(report, G36DefensivePreflightReport):
        raise SemanticGateClosed("defensive preflight report is not typed")
    return {
        "schema": G36_DEFENSIVE_PREFLIGHT_SCHEMA,
        "profile_id": report.profile_id,
        "upstream_alas_commit": report.upstream_alas_commit,
        "task_config_sha256": report.task_config_sha256,
        "capability_surface_sha256": report.capability_surface_sha256,
        "observer_manifest_sha256": report.observer_manifest_sha256,
        "normal_replay_sha256": report.normal_replay_sha256,
        "defensive_replay_sha256": report.defensive_replay_sha256,
        "run_policy_sha256": report.run_policy_sha256,
        "stop_boundary": report.stop_boundary,
        "recovery_policy": report.recovery_policy,
        "rows": [
            {
                "root": row.root,
                "configuration": list(row.configuration),
                "configuration_values": dict(row.configuration_values),
                "resources": list(row.resources),
                "actions": list(row.actions),
                "qualified_resources": list(row.qualified_resources),
                "missing_resources": list(row.missing_resources),
                "qualified_actions": list(row.qualified_actions),
                "missing_actions": list(row.missing_actions),
                "source_scenarios": list(row.source_scenarios),
                "resolution": row.resolution.value,
                "recovery_before_grid": row.recovery_before_grid,
                "implicit_unknown": row.implicit_unknown,
            }
            for row in report.rows
        ],
        "closure_complete": report.closure_complete,
        "grid_click_allowed": report.grid_click_allowed,
        "input_injected": report.input_injected,
        "capability_promotion": report.capability_promotion,
        "production_ready": report.production_ready,
    }


__all__ = (
    "DefensivePreflightRow",
    "DefensiveResolution",
    "G36_DEFENSIVE_PREFLIGHT_SCHEMA",
    "G36_DEFENSIVE_ROOT_SPECS",
    "G36DefensivePreflightReport",
    "build_g36_defensive_preflight",
    "g36_defensive_preflight_to_json",
)
