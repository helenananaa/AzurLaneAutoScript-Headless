"""Fail-closed H05 bundle for repeated, input-free G36 live preflights."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping, Sequence

from ..semantic_oracle import SemanticGateClosed


G36_LIVE_PREFLIGHT_SCHEMA = "alas-headless.g36-live-preflight/v1"
_STOP_BOUNDARY = "original-device-click-grid"
_GOTO_CALL_ORDER = (
    "hp_retreat_triggered",
    "fleet_set",
    "in_sight",
    "focus_to_grid_center",
    "convert_global_to_local",
    "ambush_color_initial",
    "enemy_searching_color_initial",
    "device.click",
)
_REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_NODE_PATTERN = re.compile(r"^[A-Z][1-9][0-9]*$")


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_sha256(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SemanticGateClosed("G36 live preflight invalid " + field)
    return value


def _validate_run(
    run: Mapping[str, Any], index: int, defensive_preflight_sha256: str
) -> None:
    prefix = "G36 live preflight run {0} ".format(index)
    if run.get("schema") != "alas-headless.g36-live-preflight-run/v1":
        raise SemanticGateClosed(prefix + "schema changed")
    identity = run.get("runtime_identity")
    if not isinstance(identity, Mapping):
        raise SemanticGateClosed(prefix + "runtime identity missing")
    for name in (
        "fingerprint_sha256",
        "game_fingerprint_sha256",
        "observer_apk_sha256",
    ):
        _require_sha256(identity.get(name), name)
    if (
        identity.get("package") != "com.bilibili.azurlane"
        or identity.get("component")
        != "com.bilibili.azurlane/com.manjuu.azurlane.MainActivity"
        or not isinstance(identity.get("serial"), str)
        or not identity.get("serial")
        or not isinstance(identity.get("pid"), int)
        or identity.get("pid", 0) <= 0
        or not isinstance(identity.get("driver_revision"), str)
        or _REVISION_PATTERN.fullmatch(identity.get("driver_revision", "")) is None
    ):
        raise SemanticGateClosed(prefix + "runtime identity changed")
    surface = identity.get("surface")
    if not isinstance(surface, Mapping) or surface != {
        "width": 1280,
        "height": 720,
    }:
        raise SemanticGateClosed(prefix + "surface identity changed")
    generations = run.get("generations")
    if (
        not isinstance(generations, Mapping)
        or not all(
            isinstance(generations.get(name), int) and generations[name] > 0
            for name in ("map", "decision", "target_recheck")
        )
        or not (
            generations["map"]
            <= generations["decision"]
            < generations["target_recheck"]
        )
    ):
        raise SemanticGateClosed(prefix + "generations are not fresh")
    for name in ("map_signature_sha256", "logical_state_sha256"):
        _require_sha256(run.get(name), name)
    decision = run.get("decision")
    target = run.get("target_recheck")
    if not isinstance(decision, Mapping) or not isinstance(target, Mapping):
        raise SemanticGateClosed(prefix + "decision evidence missing")
    route_nodes = decision.get("route_nodes")
    if (
        decision.get("stage_code") != "12-4"
        or decision.get("battle_count") != 0
        or decision.get("branch_name") != "battle_0"
        or decision.get("fleet_index") != 1
        or not isinstance(decision.get("fleet_marker"), str)
        or not decision.get("fleet_marker")
        or decision.get("target_kind") != "enemy"
        or decision.get("expected") != "combat"
        or isinstance(decision.get("cost"), bool)
        or not isinstance(decision.get("cost"), int)
        or decision.get("cost", -1) < 0
        or not isinstance(decision.get("origin_node"), str)
        or not isinstance(decision.get("target_node"), str)
        or not isinstance(route_nodes, list)
        or not 1 <= len(route_nodes) <= 4
        or any(
            not isinstance(node, str)
            or _NODE_PATTERN.fullmatch(node) is None
            for node in route_nodes
        )
        or len(route_nodes) != len(set(route_nodes))
        or route_nodes[0] != decision.get("origin_node")
        or route_nodes[-1] != decision.get("target_node")
        or decision.get("goto_nodes") != [decision.get("target_node")]
    ):
        raise SemanticGateClosed(prefix + "original ALAS decision malformed")
    if (
        target.get("node") != decision.get("target_node")
        or target.get("top_raycast") is not True
        or not isinstance(target.get("path"), str)
        or not target.get("path")
        or not isinstance(target.get("point"), Mapping)
        or not isinstance(target.get("bounds"), Mapping)
        or not all(
            isinstance(target["point"].get(name), (int, float))
            and not isinstance(target["point"].get(name), bool)
            for name in ("x", "y")
        )
        or not all(
            isinstance(target["bounds"].get(name), (int, float))
            and not isinstance(target["bounds"].get(name), bool)
            for name in ("left", "top", "right", "bottom")
        )
        or not (
            target["bounds"]["left"]
            <= target["point"]["x"]
            <= target["bounds"]["right"]
            and target["bounds"]["top"]
            <= target["point"]["y"]
            <= target["bounds"]["bottom"]
        )
    ):
        raise SemanticGateClosed(prefix + "target recheck changed")
    if tuple(run.get("original_goto_call_order", ())) != _GOTO_CALL_ORDER:
        raise SemanticGateClosed(prefix + "original goto boundary changed")
    closure = run.get("capability_recovery_closure")
    if (
        not isinstance(closure, Mapping)
        or closure.get("defensive_preflight_sha256")
        != defensive_preflight_sha256
        or closure.get("closure_complete") is not True
        or closure.get("grid_click_allowed") is not False
        or closure.get("recovery_policy") != "qualification-stop"
    ):
        raise SemanticGateClosed(prefix + "capability closure changed")
    if (
        run.get("stop_boundary") != _STOP_BOUNDARY
        or run.get("unknown_calls") != []
        or run.get("grid_input_injected") is not False
        or run.get("android_input_injected") is not False
        or run.get("camera_input_injected") is not False
        or run.get("input_injected") is not False
    ):
        raise SemanticGateClosed(prefix + "did not remain input-free")
    camera = run.get("camera_branch")
    if not isinstance(camera, Mapping) or camera.get("owner") != "original-alas":
        raise SemanticGateClosed(prefix + "camera ownership changed")
    if camera.get("required") is not False:
        raise SemanticGateClosed(prefix + "requires a camera input")


def build_g36_live_preflight_bundle(
    *,
    profile: Mapping[str, Any],
    defensive_preflight: Mapping[str, Any],
    runs: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Validate two unchanged-state runs and return their hash signature."""

    if profile.get("schema") != "alas-headless.g36-task-profile/v1":
        raise SemanticGateClosed("G36 live preflight profile changed")
    task_config_sha256 = _canonical_sha256(profile)
    if (
        defensive_preflight.get("schema")
        != "alas-headless.g36-defensive-preflight/v1"
        or defensive_preflight.get("closure_complete") is not True
        or defensive_preflight.get("grid_click_allowed") is not False
        or defensive_preflight.get("input_injected") is not False
        or defensive_preflight.get("stop_boundary") != _STOP_BOUNDARY
        or defensive_preflight.get("profile_id") != profile.get("profile_id")
        or defensive_preflight.get("upstream_alas_commit")
        != profile.get("upstream_alas_commit")
        or defensive_preflight.get("task_config_sha256")
        != task_config_sha256
    ):
        raise SemanticGateClosed("G36 live defensive closure changed")
    if len(runs) < 2:
        raise SemanticGateClosed("G36 live preflight requires two runs")
    checked = [dict(run) for run in runs]
    defensive_preflight_sha256 = _canonical_sha256(defensive_preflight)
    for index, run in enumerate(checked, start=1):
        _validate_run(run, index, defensive_preflight_sha256)

    first = checked[0]
    stable_fields = (
        "map_signature_sha256",
        "logical_state_sha256",
        "decision",
        "target_recheck",
        "camera_branch",
        "original_goto_call_order",
        "stop_boundary",
        "capability_recovery_closure",
    )
    identity_fields = (
        "fingerprint_sha256",
        "game_fingerprint_sha256",
        "observer_apk_sha256",
        "package",
        "component",
        "serial",
        "pid",
        "driver_revision",
        "surface",
    )
    for index, run in enumerate(checked[1:], start=2):
        if any(run.get(name) != first.get(name) for name in stable_fields):
            raise SemanticGateClosed(
                "G36 live preflight nondeterministic run {0}".format(index)
            )
        if any(
            run["runtime_identity"].get(name)
            != first["runtime_identity"].get(name)
            for name in identity_fields
        ):
            raise SemanticGateClosed(
                "G36 live preflight runtime changed in run {0}".format(index)
            )
        if run["generations"]["map"] <= checked[index - 2]["generations"][
            "target_recheck"
        ]:
            raise SemanticGateClosed("G36 live preflight runs are not ordered")

    body = {
        "schema": G36_LIVE_PREFLIGHT_SCHEMA,
        "profile_id": profile.get("profile_id"),
        "task_config_sha256": task_config_sha256,
        "defensive_preflight_sha256": defensive_preflight_sha256,
        "run_count": len(checked),
        "runs": checked,
        "same_logical_branch": True,
        "zero_unknown_calls": True,
        "grid_input_injected": False,
        "input_injected": False,
        "capability_promotion": False,
        "production_ready": False,
    }
    digest = _canonical_sha256(body)
    return dict(body, bundle_sha256=digest, signature="sha256:" + digest)


__all__ = (
    "G36_LIVE_PREFLIGHT_SCHEMA",
    "build_g36_live_preflight_bundle",
)
