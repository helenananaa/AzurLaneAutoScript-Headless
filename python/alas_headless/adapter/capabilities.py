"""Canonical semantic capability inventories and closure reports."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from .policy import RecoveryPolicy


CAPABILITY_REPORT_SCHEMA = "alas-headless.capability-closure/v1"
LEGACY_CAPABILITY_TASK_CONFIG_SHA256 = (
    "dc5f75742bd2e66dd83f82bbce11f5224de0052bac545a3f9e4c605332fbaae7"
)
RECOVERY_QUALIFICATION_STOP = "recovery.qualification_stop"
RECOVERY_MANUAL_TAKEOVER = "recovery.manual_takeover"

ACTION_CAPABILITIES = frozenset(
    {
        "awaken.execute",
        "build.submit",
        "campaign.camera_positioning",
        "campaign.grid_click",
        "campaign.fleet_mutation",
        "campaign.sortie",
        "campaign.stage_entry",
        "campaign.viewport_swipe",
        "commission.reward",
        "commission.start",
        "daily.execute",
        "dorm.collect",
        "dorm.feed",
        "enhancement.execute",
        "exercise.execute",
        "exercise.refresh",
        "guild.claim",
        "guild.dispatch",
        "guild.exchange",
        "mail.mutation",
        "meta.assist",
        "minigame.play",
        "mission.claim",
        "operation_siren.coordinate_checkout",
        "research.reward",
        "research.start",
        "retirement.execute",
        "shop.purchase",
        "tactical.assign",
        "tactical.reward",
    }
)

_CAPABILITY_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)+$")
_PROFILE_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def _capability_set(values: Iterable[str], label: str) -> frozenset[str]:
    try:
        normalized = frozenset(values)
    except TypeError as exc:
        raise TypeError("{0} capabilities must be iterable".format(label)) from exc
    if any(
        not isinstance(value, str) or _CAPABILITY_PATTERN.fullmatch(value) is None
        for value in normalized
    ):
        raise ValueError("{0} capability is not canonical".format(label))
    return normalized


def recovery_capability(policy: RecoveryPolicy) -> str:
    if policy is RecoveryPolicy.QUALIFICATION_STOP:
        return RECOVERY_QUALIFICATION_STOP
    if policy is RecoveryPolicy.MANUAL_TAKEOVER:
        return RECOVERY_MANUAL_TAKEOVER
    raise TypeError("recovery policy is not supported")


@dataclass(frozen=True)
class TaskCapabilityProfile:
    profile_id: str
    task_config_sha256: str = LEGACY_CAPABILITY_TASK_CONFIG_SHA256
    required_observations: frozenset[str] = frozenset()
    required_actions: frozenset[str] = frozenset()
    required_grants: frozenset[str] = frozenset()
    required_recoveries: frozenset[str] = frozenset()
    required_evidence: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.profile_id, str)
            or _PROFILE_PATTERN.fullmatch(self.profile_id) is None
        ):
            raise ValueError("capability profile ID is not canonical")
        if (
            not isinstance(self.task_config_sha256, str)
            or _SHA256_PATTERN.fullmatch(self.task_config_sha256) is None
        ):
            raise ValueError("capability task-config hash is malformed")
        for name in (
            "required_observations",
            "required_actions",
            "required_grants",
            "required_recoveries",
            "required_evidence",
        ):
            object.__setattr__(self, name, _capability_set(getattr(self, name), name))
        if not self.required_grants.issubset(self.required_actions):
            raise ValueError("required grants must name required action capabilities")


@dataclass(frozen=True)
class CapabilityInventory:
    observations: frozenset[str] = frozenset()
    actions: frozenset[str] = frozenset()
    recoveries: frozenset[str] = frozenset()
    evidence: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        for name in ("observations", "actions", "recoveries", "evidence"):
            object.__setattr__(self, name, _capability_set(getattr(self, name), name))


DEFAULT_CAPABILITY_INVENTORY = CapabilityInventory(
    actions=ACTION_CAPABILITIES,
    # Qualification-stop is implemented by the current fail-closed session.
    # Manual takeover remains a policy enum, but is not advertised as an
    # available recovery capability until its ownership boundary is built.
    recoveries=frozenset({RECOVERY_QUALIFICATION_STOP}),
)


@dataclass(frozen=True)
class CapabilityClosureReport:
    profile_id: str
    task_config_sha256: str
    required: Mapping[str, tuple[str, ...]]
    available: Mapping[str, tuple[str, ...]]
    granted_actions: tuple[str, ...]
    selected_recovery: str
    missing: Mapping[str, tuple[str, ...]]
    forbidden_grants: tuple[str, ...]
    forbidden_recoveries: tuple[str, ...]
    ready: bool
    sha256: str = field(init=False)

    def __post_init__(self) -> None:
        for name in ("required", "available", "missing"):
            value = getattr(self, name)
            if not isinstance(value, Mapping):
                raise TypeError("capability report section is not a mapping")
            object.__setattr__(
                self,
                name,
                MappingProxyType(
                    {key: tuple(children) for key, children in value.items()}
                ),
            )
        object.__setattr__(
            self,
            "sha256",
            hashlib.sha256(_canonical_bytes(self.document())).hexdigest(),
        )

    def document(self) -> Mapping[str, Any]:
        return {
            "schema": CAPABILITY_REPORT_SCHEMA,
            "profile_id": self.profile_id,
            "task_config_sha256": self.task_config_sha256,
            "required": {key: list(value) for key, value in self.required.items()},
            "available": {key: list(value) for key, value in self.available.items()},
            "granted_actions": list(self.granted_actions),
            "selected_recovery": self.selected_recovery,
            "missing": {key: list(value) for key, value in self.missing.items()},
            "forbidden_grants": list(self.forbidden_grants),
            "forbidden_recoveries": list(self.forbidden_recoveries),
            "ready": self.ready,
        }


def _canonical_bytes(document: Mapping[str, Any]) -> bytes:
    return json.dumps(
        document,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_capability_report_json(report: CapabilityClosureReport) -> str:
    if not isinstance(report, CapabilityClosureReport):
        raise TypeError("capability report is not typed")
    return _canonical_bytes(report.document()).decode("utf-8") + "\n"


def capability_closure_report(
    profile: TaskCapabilityProfile,
    inventory: CapabilityInventory,
    grants: Mapping[str, int],
    recovery_policy: RecoveryPolicy,
) -> CapabilityClosureReport:
    if not isinstance(profile, TaskCapabilityProfile):
        raise TypeError("capability profile is not typed")
    if not isinstance(inventory, CapabilityInventory):
        raise TypeError("capability inventory is not typed")
    if not isinstance(grants, Mapping):
        raise TypeError("capability grants must be a mapping")
    positive_grants = set()
    for capability, amount in grants.items():
        _capability_set((capability,), "grant")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            raise ValueError("capability grant must be a non-negative integer")
        if amount:
            positive_grants.add(capability)

    selected_recovery = recovery_capability(recovery_policy)
    required = {
        "observations": tuple(sorted(profile.required_observations)),
        "actions": tuple(sorted(profile.required_actions)),
        "grants": tuple(sorted(profile.required_grants)),
        "recoveries": tuple(sorted(profile.required_recoveries)),
        "evidence": tuple(sorted(profile.required_evidence)),
    }
    available = {
        "observations": tuple(sorted(inventory.observations)),
        "actions": tuple(sorted(inventory.actions)),
        "recoveries": tuple(sorted(inventory.recoveries)),
        "evidence": tuple(sorted(inventory.evidence)),
    }
    missing = {
        "observations": tuple(
            sorted(profile.required_observations - inventory.observations)
        ),
        "actions": tuple(sorted(profile.required_actions - inventory.actions)),
        "grants": tuple(sorted(profile.required_grants - positive_grants)),
        "recoveries": tuple(
            sorted(
                profile.required_recoveries
                - inventory.recoveries.intersection({selected_recovery})
            )
        ),
        "evidence": tuple(sorted(profile.required_evidence - inventory.evidence)),
    }
    forbidden_grants = tuple(sorted(positive_grants - profile.required_grants))
    forbidden_recoveries = (
        tuple(sorted({selected_recovery} - profile.required_recoveries))
        if profile.required_actions or profile.required_recoveries
        else ()
    )
    ready = (
        not any(missing.values()) and not forbidden_grants and not forbidden_recoveries
    )
    return CapabilityClosureReport(
        profile_id=profile.profile_id,
        task_config_sha256=profile.task_config_sha256,
        required=required,
        available=available,
        granted_actions=tuple(sorted(positive_grants)),
        selected_recovery=selected_recovery,
        missing=missing,
        forbidden_grants=forbidden_grants,
        forbidden_recoveries=forbidden_recoveries,
        ready=ready,
    )


def compatibility_profile(
    profile_id: str,
    grants: Mapping[str, int],
    recovery_policy: RecoveryPolicy = RecoveryPolicy.QUALIFICATION_STOP,
    task_config_sha256: str = LEGACY_CAPABILITY_TASK_CONFIG_SHA256,
) -> TaskCapabilityProfile:
    actions = frozenset(
        capability for capability, amount in grants.items() if amount > 0
    )
    recoveries = (
        frozenset({recovery_capability(recovery_policy)}) if actions else frozenset()
    )
    return TaskCapabilityProfile(
        profile_id=profile_id,
        task_config_sha256=task_config_sha256,
        required_actions=actions,
        required_grants=actions,
        required_recoveries=recoveries,
    )
