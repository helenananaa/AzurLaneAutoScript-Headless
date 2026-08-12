"""Qualification-only policy generation from the accepted H05 preflight."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from ..semantic_oracle import SemanticGateClosed
from .policy import RecoveryPolicy, RunPolicy, RunPolicyIdentity


G36_ONE_CLICK_GENERATOR_SCHEMA = (
    "alas-headless.g36-one-click-policy-generator/v1"
)
G36_ONE_CLICK_QUALIFICATION_SCHEMA = (
    "alas-headless.g36-one-click-qualification-policy/v1"
)
G36_ONE_CLICK_CAPABILITY = "campaign.grid_click"
_EXPECTED_GENERATOR_FIELDS = frozenset(
    {
        "schema",
        "profile_id",
        "upstream_alas_commit",
        "runtime_lock_sha256",
        "task_config_sha256",
        "accepted_live_preflight_sha256",
        "accepted_preflight_identity_sha256",
        "deadline_seconds",
        "grant",
        "recovery_policy",
        "production_enabled",
        "live_policy_emitted",
    }
)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise SemanticGateClosed("G36 one-click policy value is not canonical") from exc


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _require_sha256(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SemanticGateClosed("G36 one-click policy invalid " + label)
    return value


def _live_preflight_body(preflight: Mapping[str, Any]) -> Mapping[str, Any]:
    if not isinstance(preflight, Mapping):
        raise SemanticGateClosed("G36 one-click preflight is missing")
    body = dict(preflight)
    body.pop("bundle_sha256", None)
    body.pop("signature", None)
    return body


def g36_preflight_identity_document(
    preflight: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Return the stable target/runtime identity authorized by H05."""

    if (
        preflight.get("schema") != "alas-headless.g36-live-preflight/v1"
        or preflight.get("run_count") != 2
        or preflight.get("same_logical_branch") is not True
        or preflight.get("zero_unknown_calls") is not True
        or preflight.get("grid_input_injected") is not False
        or preflight.get("input_injected") is not False
        or preflight.get("capability_promotion") is not False
        or preflight.get("production_ready") is not False
    ):
        raise SemanticGateClosed("G36 one-click preflight is not accepted")
    runs = preflight.get("runs")
    if not isinstance(runs, list) or len(runs) != 2:
        raise SemanticGateClosed("G36 one-click preflight run count changed")
    first = runs[0]
    if not isinstance(first, Mapping):
        raise SemanticGateClosed("G36 one-click preflight identity is missing")
    stable_fields = (
        "runtime_identity",
        "map_signature_sha256",
        "logical_state_sha256",
        "decision",
        "target_recheck",
        "camera_branch",
        "original_goto_call_order",
        "capability_recovery_closure",
        "stop_boundary",
    )
    if any(
        not isinstance(run, Mapping)
        or any(run.get(field) != first.get(field) for field in stable_fields)
        or run.get("unknown_calls") != []
        or run.get("input_injected") is not False
        for run in runs
    ):
        raise SemanticGateClosed("G36 one-click preflight identity changed")
    return {
        "profile_id": preflight.get("profile_id"),
        "task_config_sha256": preflight.get("task_config_sha256"),
        "defensive_preflight_sha256": preflight.get(
            "defensive_preflight_sha256"
        ),
        **{field: first.get(field) for field in stable_fields},
    }


def g36_preflight_identity_sha256(preflight: Mapping[str, Any]) -> str:
    return _sha256(g36_preflight_identity_document(preflight))


@dataclass(frozen=True)
class G36OneClickQualificationPolicy:
    """One standard run policy plus the exact accepted H05 identity."""

    run_policy: RunPolicy
    accepted_live_preflight_sha256: str
    accepted_preflight_identity_sha256: str
    production_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.run_policy, RunPolicy):
            raise SemanticGateClosed("G36 one-click run policy is missing")
        _require_sha256(
            self.accepted_live_preflight_sha256, "live preflight hash"
        )
        _require_sha256(
            self.accepted_preflight_identity_sha256, "preflight identity hash"
        )
        if (
            dict(self.run_policy.grants) != {G36_ONE_CLICK_CAPABILITY: 1}
            or self.run_policy.deadline_seconds <= 0
            or self.run_policy.deadline_seconds > 60
            or self.run_policy.recovery_policy is not RecoveryPolicy.QUALIFICATION_STOP
            or self.production_enabled is not False
        ):
            raise SemanticGateClosed("G36 one-click authority is not bounded")

    def require_preflight(self, preflight: Mapping[str, Any]) -> None:
        bundle_sha = _require_sha256(
            preflight.get("bundle_sha256"), "live preflight hash"
        )
        signature = preflight.get("signature")
        if (
            bundle_sha != _sha256(_live_preflight_body(preflight))
            or signature != "sha256:" + bundle_sha
            or bundle_sha != self.accepted_live_preflight_sha256
            or g36_preflight_identity_sha256(preflight)
            != self.accepted_preflight_identity_sha256
        ):
            raise SemanticGateClosed("G36 one-click preflight binding changed")

    def document(self) -> Mapping[str, Any]:
        return {
            "schema": G36_ONE_CLICK_QUALIFICATION_SCHEMA,
            "run_policy": self.run_policy.document(),
            "accepted_live_preflight_sha256": self.accepted_live_preflight_sha256,
            "accepted_preflight_identity_sha256": (
                self.accepted_preflight_identity_sha256
            ),
            "production_enabled": False,
        }


def build_g36_one_click_qualification_policy(
    generator: Mapping[str, Any],
    preflight: Mapping[str, Any],
    *,
    expected_identity: RunPolicyIdentity,
) -> G36OneClickQualificationPolicy:
    """Validate inert checked-in inputs and emit an in-memory live policy."""

    if not isinstance(generator, Mapping) or set(generator) != _EXPECTED_GENERATOR_FIELDS:
        raise SemanticGateClosed("G36 one-click generator fields changed")
    if (
        generator.get("schema") != G36_ONE_CLICK_GENERATOR_SCHEMA
        or generator.get("profile_id") != preflight.get("profile_id")
        or generator.get("task_config_sha256")
        != preflight.get("task_config_sha256")
        or generator.get("grant") != {G36_ONE_CLICK_CAPABILITY: 1}
        or generator.get("recovery_policy") != "qualification-stop"
        or generator.get("production_enabled") is not False
        or generator.get("live_policy_emitted") is not False
    ):
        raise SemanticGateClosed("G36 one-click generator is not inert and exact")
    deadline = generator.get("deadline_seconds")
    if isinstance(deadline, bool) or not isinstance(deadline, int) or not 1 <= deadline <= 60:
        raise SemanticGateClosed("G36 one-click deadline is not short")
    accepted_bundle = _require_sha256(
        generator.get("accepted_live_preflight_sha256"), "accepted bundle hash"
    )
    accepted_identity = _require_sha256(
        generator.get("accepted_preflight_identity_sha256"),
        "accepted identity hash",
    )
    if not isinstance(expected_identity, RunPolicyIdentity):
        raise TypeError("G36 one-click expected identity is not typed")
    identity = RunPolicyIdentity(
        upstream_alas_commit=generator.get("upstream_alas_commit"),
        runtime_lock_sha256=generator.get("runtime_lock_sha256"),
        task_config_sha256=generator.get("task_config_sha256"),
    )
    if identity != expected_identity:
        raise SemanticGateClosed("G36 one-click run-policy identity changed")
    result = G36OneClickQualificationPolicy(
        run_policy=RunPolicy(
            profile_id=generator.get("profile_id"),
            identity=identity,
            grants={G36_ONE_CLICK_CAPABILITY: 1},
            deadline_seconds=deadline,
            recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,
        ),
        accepted_live_preflight_sha256=accepted_bundle,
        accepted_preflight_identity_sha256=accepted_identity,
    )
    result.require_preflight(preflight)
    return result


def canonical_g36_one_click_qualification_json(
    policy: G36OneClickQualificationPolicy,
) -> str:
    if not isinstance(policy, G36OneClickQualificationPolicy):
        raise TypeError("G36 one-click policy is not typed")
    return _canonical_bytes(policy.document()).decode("ascii") + "\n"


__all__ = (
    "G36_ONE_CLICK_CAPABILITY",
    "G36_ONE_CLICK_GENERATOR_SCHEMA",
    "G36_ONE_CLICK_QUALIFICATION_SCHEMA",
    "G36OneClickQualificationPolicy",
    "build_g36_one_click_qualification_policy",
    "canonical_g36_one_click_qualification_json",
    "g36_preflight_identity_document",
    "g36_preflight_identity_sha256",
)
