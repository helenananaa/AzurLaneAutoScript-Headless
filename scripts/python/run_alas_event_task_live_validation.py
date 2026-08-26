#!/usr/bin/env python3
"""Run one bounded Event-family task against the pinned semantic AVD."""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import hmac
import importlib
import importlib.abc
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "python") not in sys.path:
    sys.path.insert(0, str(ROOT / "python"))

from alas_headless.runner_supervision import (  # noqa: E402
    RECORD_CLEANUP,
    RECORD_RESULT,
    WORKER_ACTIVATION_HANDLE_ENV,
    WORKER_CLEANUP_HANDLE_ENV,
    WORKER_CLEANUP_SCHEMA,
    WORKER_CONFIG_HANDLE_ENV,
    WORKER_CONTROL_ENV,
    WORKER_CONTROL_HANDLE_ENV,
    WORKER_LEASE_HANDLE_ENV,
    WORKER_RESULT_HANDLE_ENV,
    WORKER_RESULT_SCHEMA,
    WORKER_ROLE_ENV,
    WORKER_SEED_HANDLE_ENV,
    WORKER_CLEANUP_GRACE_SECONDS,
    ConfigFileState,
    FileIdentity,
    ForwardLease,
    ExclusiveFile,
    ImmutableInputFile,
    MAX_CONFIG_BYTES,
    ProcessSupervisionResult,
    RunBinding,
    RunnerStopRequested,
    SeedSource,
    WindowsWorkerJob,
    WorkerControl,
    WorkerHandles,
    WorkerTerminal,
    MAX_WORKER_RESULT_BYTES,
    adb_forward_inventory,
    adb_remove_forward,
    adb_verified_game_pid,
    bind_record,
    binding_digest,
    build_config_ownership,
    canonical_json_bytes,
    close_inherited_handle,
    create_activation_pipe,
    delete_owned_config_windows,
    ensure_secret_free_payload,
    exclusive_create,
    file_identity_from_fd,
    file_identity_from_path,
    inspect_owned_config,
    insert_config_marker,
    install_worker_stop_handler,
    normalize_system_exit_code,
    open_immutable_input,
    process_identity,
    public_exception_descriptor,
    read_bytes_handle,
    read_owned_file,
    redact_secret_representations,
    remaining_seconds,
    safe_exception_type,
    send_activation,
    secret_free_exception_label,
    select_forward_cleanup,
    shutdown_worker,
    supervise_process,
    strict_json_mapping_bytes,
    validate_control_lease,
    validate_total_deadline,
    validate_worker_control_root,
    verify_bound_record,
    worker_control_from_activation,
    verify_initial_config,
    write_bytes_handle,
    write_json_handle,
    write_owned_file,
)
from alas_headless.adb_device import resolve_adb_serial  # noqa: E402


TASKS = ("Event", "Event2", "EventA", "EventB", "EventC", "EventD", "EventSp")
DAILY_TASKS = ("EventA", "EventB", "EventC", "EventD")
RUN_METHODS = {
    "Event": "event",
    "Event2": "event2",
    "EventA": "event_a",
    "EventB": "event_b",
    "EventC": "event_c",
    "EventD": "event_d",
    "EventSp": "event_sp",
}
SCHEMA = "alas-headless.event-task-live-validation/v1"
SHARED_HARD_STAGE_ENTRANCES = {
    **{f"c{index}": f"a{index}" for index in range(1, 4)},
    **{f"d{index}": f"b{index}" for index in range(1, 4)},
}
AUTO_SEARCH_ROOTS = (
    "ChapterPreCombatUI(Clone)",
    "CombatUIStandard(Clone)",
    "NewBattleResultEmptyUI(Clone)",
)
TOTAL_RESULT_EXIT_SUFFIX = "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"
EVENT_SP_ATTEMPT_PATH = re.compile(
    r"(?:.*/)?LevelSelectSPFullUI\(Clone\)/Battle/(?:"
    r"MapItems/List/Item(?:\(Clone\))?/Selected/Count|"
    r"Nodes/Chapter_[0-9]+/main/triesLimit/Text"
    r")"
)
EVENT_SP_ATTEMPT_TEXT = re.compile(
    r"(?:<color=#[0-9A-Fa-f]{8}>)?(0/1)(?:</color>)?"
)
EVENT_SP_EXECUTION_BUDGETS = {
    "stage_entry": 1,
    # Normal-mode reconciliation of the reviewed (1, 2, 0) fleet tuple needs
    # at most: clear fleet 2, clear submarine, select fleet 1, select fleet 2.
    # The adapter preflights the exact sequence before spending any of these.
    "fleet_mutation": 4,
    "sortie": 1,
    "combat": 0,
    "grid_click": 0,
    "viewport_swipe": 0,
    "camera_positioning": 0,
    "recovery_total": 0,
}
LEGACY_EXECUTION_BUDGET_DEFAULTS = {
    "stage_entry": 1,
    "fleet_mutation": 6,
    "sortie": 1,
    "combat": 12,
    "grid_click": 12,
    "viewport_swipe": 4,
    "camera_positioning": 0,
}
GAME_PACKAGE = "com.bilibili.azurlane"
EVENT_SP_SEED_NAME = "template"
EVENT_SP_SEED_CAPABILITY = "alas.eventsp.pinned-template/v1"
EVENT_SP_TEMPLATE_SHA256 = (
    "2de0a47643d9ad73417473f66be75dadcc1a82e11d405e1f2421ade3e31eaced"
)
EVENT_SP_TEMPLATE_UNPROVEN = "event_sp.template_seed_unproven"
EVENT_SP_TEMPLATE_CHANGED = "event_sp.template_seed_changed"
MATERIALIZED_ALAS_CAPABILITY_ID = "alas.eventsp.materialized-fleet-rollback-guard/v4"
MATERIALIZED_ALAS_PROOF_SCHEMA = "alas-headless.materialized-alas-proof/v3"
MATERIALIZED_ALAS_CONTROL_SCHEMA = "alas-headless.materialized-alas-control/v4"
MATERIALIZED_ALAS_LOADED_SCHEMA = "alas-headless.materialized-alas-loaded/v3"
MATERIALIZED_ALAS_CONTROL_ENV = "ALAS_EVENT_RUNNER_INTERNAL_MATERIALIZATION"
MATERIALIZED_ALAS_RELATIVE_PATH = Path("module/map/map_operation.py")
MATERIALIZED_ALAS_MODULE_NAME = "module.map.map_operation"
MATERIALIZED_ALAS_LOADER_ID = "verified-canonical-source-bytes/v3"
MATERIALIZED_ALAS_CANONICAL_SOURCE_SHA256 = (
    "c7901c1b850e75c1441f0dd441532bab06ca08ee3677481687cc129aa58e8505"
)
MATERIALIZED_ALAS_SEMANTIC_BRANCH_SHA256 = (
    "1803fd9c558a4cb2b99ae3ea837993e22a5f8131cf099ae1a9ffa9f87b5f6d3e"
)
MATERIALIZED_ALAS_MAX_SOURCE_BYTES = 2 * 1024 * 1024
MATERIALIZED_ALAS_MAX_CONTROL_BYTES = 8 * 1024
MATERIALIZED_ALAS_UNPROVEN = "event_sp.materialized_fleet_noop_guard_unproven"
MATERIALIZED_ALAS_CHANGED = "event_sp.materialized_fleet_noop_guard_changed"
MATERIALIZED_ALAS_BASELINE = "fully_qualified_baseline"
MATERIALIZED_ALAS_COMPATIBLE = "best_effort_compatible"
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class MaterializedAlasAdmissionError(RuntimeError):
    """Stable, secret-free admission failure for the materialized ALAS tree."""

    def __init__(self, classification: str) -> None:
        if classification not in (
            MATERIALIZED_ALAS_UNPROVEN,
            MATERIALIZED_ALAS_CHANGED,
        ):
            raise ValueError("materialized ALAS classification is unsupported")
        self.classification = classification
        super().__init__(classification)


class EventSpTemplateAdmissionError(RuntimeError):
    """Stable, secret-free admission failure for the pinned config template."""

    def __init__(self, classification: str) -> None:
        if classification not in (
            EVENT_SP_TEMPLATE_UNPROVEN,
            EVENT_SP_TEMPLATE_CHANGED,
        ):
            raise ValueError("EventSp template classification is unsupported")
        self.classification = classification
        super().__init__(classification)


def _attribute_chain(node: ast.AST) -> tuple[str, ...] | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None
    parts.append(node.id)
    return tuple(reversed(parts))


def _call_matches(node: ast.AST, chain: tuple[str, ...]) -> bool:
    return isinstance(node, ast.Call) and _attribute_chain(node.func) == chain


def _static_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _static_string(node.left)
        right = _static_string(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _calls_in(node: ast.AST, chain: tuple[str, ...]) -> tuple[ast.Call, ...]:
    return tuple(
        candidate for candidate in ast.walk(node) if _call_matches(candidate, chain)
    )


def _direct_call_statement(statement: ast.stmt, chain: tuple[str, ...]) -> bool:
    return (
        isinstance(statement, ast.Expr)
        and _call_matches(statement.value, chain)
        and not statement.value.args
        and not statement.value.keywords
    )


def _direct_statement_index(statements: list[ast.stmt], chain: tuple[str, ...]) -> int:
    matches = [
        index
        for index, statement in enumerate(statements)
        if _direct_call_statement(statement, chain)
    ]
    if len(matches) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    return matches[0]


def _normalized_ast_value(value: Any) -> Any:
    if isinstance(value, ast.AST):
        return {
            "node": type(value).__name__,
            "fields": [
                [name, _normalized_ast_value(field)]
                for name, field in ast.iter_fields(value)
            ],
        }
    if isinstance(value, list):
        return [_normalized_ast_value(item) for item in value]
    if isinstance(value, tuple):
        return {
            "scalar": "tuple",
            "items": [_normalized_ast_value(item) for item in value],
        }
    if value is None:
        return {"scalar": "none"}
    if value is Ellipsis:
        return {"scalar": "ellipsis"}
    if isinstance(value, bool):
        return {"scalar": "bool", "value": value}
    if isinstance(value, int):
        return {"scalar": "int", "value": str(value)}
    if isinstance(value, float):
        return {"scalar": "float", "value": repr(value)}
    if isinstance(value, complex):
        return {"scalar": "complex", "value": repr(value)}
    if isinstance(value, str):
        return {"scalar": "str", "value": value}
    if isinstance(value, bytes):
        return {"scalar": "bytes", "value": value.hex()}
    raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)


def _normalized_ast_sha256(node: ast.AST) -> str:
    payload = json.dumps(
        _normalized_ast_value(node),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8", errors="strict")
    return hashlib.sha256(payload).hexdigest()


def _validate_materialized_enter_map(tree: ast.Module) -> str:
    classes = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "MapOperation"
    ]
    if len(classes) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    methods = [
        node
        for node in classes[0].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "enter_map"
    ]
    if (
        len(methods) != 1
        or not isinstance(methods[0], ast.FunctionDef)
        or methods[0].decorator_list
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    method = methods[0]

    adapter_stores = [
        node
        for node in ast.walk(method)
        if isinstance(node, ast.Name)
        and isinstance(node.ctx, ast.Store)
        and node.id == "semantic_adapter"
    ]
    adapter_assignments = [
        node
        for node in method.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
        and node.targets[0].id == "semantic_adapter"
    ]
    if len(adapter_stores) != 1 or len(adapter_assignments) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    adapter_assignment = adapter_assignments[0]
    adapter_value = adapter_assignment.value
    if (
        not isinstance(adapter_value, ast.Call)
        or not isinstance(adapter_value.func, ast.Name)
        or adapter_value.func.id != "getattr"
        or adapter_value.keywords
        or len(adapter_value.args) != 3
        or _attribute_chain(adapter_value.args[0]) != ("self", "device")
        or not isinstance(adapter_value.args[1], ast.Constant)
        or adapter_value.args[1].value != "semantic_adapter"
        or not isinstance(adapter_value.args[2], ast.Constant)
        or adapter_value.args[2].value is not None
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    adapter_index = method.body.index(adapter_assignment)
    top_level_with = [
        (index, statement)
        for index, statement in enumerate(method.body)
        if isinstance(statement, ast.With)
    ]
    if len(top_level_with) != 1 or adapter_index >= top_level_with[0][0]:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    campaign_with = top_level_with[0][1]
    while_loops = [
        statement
        for statement in campaign_with.body
        if isinstance(statement, ast.While)
    ]
    if len(while_loops) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    campaign_loop = while_loops[0]

    active_chain = ("semantic_adapter", "campaign_pre_sortie_active")
    semantic_branches = [
        statement
        for statement in campaign_loop.body
        if isinstance(statement, ast.If)
        and len(_calls_in(statement.test, active_chain)) == 1
    ]
    if len(semantic_branches) != 1 or len(_calls_in(method, active_chain)) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    semantic_branch = semantic_branches[0]
    semantic_test = semantic_branch.test
    if (
        not isinstance(semantic_test, ast.BoolOp)
        or not isinstance(semantic_test.op, ast.And)
        or len(semantic_test.values) != 2
        or not isinstance(semantic_test.values[0], ast.Compare)
        or not isinstance(semantic_test.values[0].left, ast.Name)
        or semantic_test.values[0].left.id != "semantic_adapter"
        or len(semantic_test.values[0].ops) != 1
        or not isinstance(semantic_test.values[0].ops[0], ast.IsNot)
        or len(semantic_test.values[0].comparators) != 1
        or not isinstance(semantic_test.values[0].comparators[0], ast.Constant)
        or semantic_test.values[0].comparators[0].value is not None
        or not _call_matches(semantic_test.values[1], active_chain)
        or semantic_test.values[1].args
        or semantic_test.values[1].keywords
        or semantic_branch.orelse
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    authorize_chain = (
        "semantic_adapter",
        "authorize_campaign_fleet_preparation",
    )
    required_chain = (
        "semantic_adapter",
        "campaign_fleet_preparation_required",
    )
    legacy_chain = ("self", "fleet_preparation")
    confirm_chain = ("semantic_adapter", "confirm_campaign_fleet_selection")
    if (
        any(
            len(_calls_in(semantic_branch, chain)) != 1
            for chain in (authorize_chain, required_chain, legacy_chain, confirm_chain)
        )
        or len(_calls_in(method, authorize_chain)) != 1
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    fleet_branches = [
        statement
        for statement in semantic_branch.body
        if isinstance(statement, ast.If)
        and len(_calls_in(statement, authorize_chain)) == 1
    ]
    if len(fleet_branches) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    fleet_branch = fleet_branches[0]
    fleet_test = fleet_branch.test
    if (
        not isinstance(fleet_test, ast.Call)
        or _attribute_chain(fleet_test.func) != ("self", "appear")
        or len(fleet_test.args) != 1
        or not isinstance(fleet_test.args[0], ast.Name)
        or fleet_test.args[0].id != "FLEET_PREPARATION"
        or fleet_branch.orelse
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    fleet_tries = [
        statement for statement in fleet_branch.body if isinstance(statement, ast.Try)
    ]
    if len(fleet_tries) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    try_node = fleet_tries[0]
    if (
        try_node.orelse
        or len(try_node.finalbody) != 1
        or not isinstance(try_node.finalbody[0], ast.If)
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    rollback_if = try_node.finalbody[0]
    if (
        not isinstance(rollback_if.test, ast.UnaryOp)
        or not isinstance(rollback_if.test.op, ast.Not)
        or not isinstance(rollback_if.test.operand, ast.Name)
        or rollback_if.test.operand.id != "sortie_clicked"
        or rollback_if.orelse
        or len(rollback_if.body) != 1
        or not isinstance(rollback_if.body[0], ast.Try)
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    rollback_try = rollback_if.body[0]
    close_chain = (
        "semantic_adapter",
        "close_campaign_fleet_dropdown_for_rollback",
    )
    cancel_chain = ("self", "enter_map_cancel")
    if (
        rollback_try.handlers
        or rollback_try.orelse
        or len(rollback_try.body) != 1
        or not _direct_call_statement(rollback_try.body[0], close_chain)
        or len(rollback_try.finalbody) != 1
        or not isinstance(rollback_try.finalbody[0], ast.Expr)
        or not _call_matches(rollback_try.finalbody[0].value, cancel_chain)
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    close_call = rollback_try.body[0].value
    cancel_call = rollback_try.finalbody[0].value
    assert isinstance(close_call, ast.Call) and isinstance(cancel_call, ast.Call)
    if (
        close_call.args
        or close_call.keywords
        or cancel_call.args
        or len(cancel_call.keywords) != 1
        or cancel_call.keywords[0].arg != "skip_first_screenshot"
        or not isinstance(cancel_call.keywords[0].value, ast.Constant)
        or cancel_call.keywords[0].value.value is not False
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    authorize_locations = [
        (index, statement)
        for index, statement in enumerate(try_node.body)
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and isinstance(statement.targets[0], ast.Name)
        and statement.targets[0].id == "fleet_authorized"
        and _call_matches(statement.value, authorize_chain)
    ]
    if len(authorize_locations) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    authorize_index, authorize = authorize_locations[0]
    if adapter_assignment.lineno >= authorize.lineno:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    call = authorize.value
    assert isinstance(call, ast.Call)
    expected_arguments = (
        ("self", "config", "Fleet_Fleet1"),
        ("self", "config", "Fleet_Fleet2"),
        ("self", "config", "Submarine_Fleet"),
    )
    if (
        call.keywords
        or tuple(_attribute_chain(argument) for argument in call.args)
        != expected_arguments
        or authorize_index + 1 >= len(try_node.body)
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    authorized = try_node.body[authorize_index + 1]
    authorized_branches = [
        node
        for node in try_node.body
        if isinstance(node, ast.If)
        and isinstance(node.test, ast.Name)
        and node.test.id == "fleet_authorized"
    ]
    if (
        len(authorized_branches) != 1
        or authorized is not authorized_branches[0]
        or not isinstance(authorized, ast.If)
        or authorized.orelse
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    guard_candidates = [
        (index, statement)
        for index, statement in enumerate(authorized.body)
        if isinstance(statement, ast.If)
        and _call_matches(statement.test, required_chain)
    ]
    if len(guard_candidates) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    guard_index, guard = guard_candidates[0]
    guard_call = guard.test
    assert isinstance(guard_call, ast.Call)
    if (
        guard_call.args
        or guard_call.keywords
        or guard.orelse
        or len(guard.body) != 1
        or not _direct_call_statement(guard.body[0], legacy_chain)
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    if len(_calls_in(authorized, legacy_chain)) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    permitted_legacy_attribute = guard.body[0].value.func
    legacy_attributes = [
        node
        for node in ast.walk(semantic_branch)
        if isinstance(node, ast.Attribute) and node.attr == "fleet_preparation"
    ]
    forbidden_dynamic_references = [
        node
        for node in ast.walk(semantic_branch)
        if (isinstance(node, ast.Constant) and node.value == "fleet_preparation")
        or (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "fleet_preparation"
        )
        or isinstance(
            node,
            (
                ast.Lambda,
                ast.FunctionDef,
                ast.AsyncFunctionDef,
                ast.ClassDef,
                ast.ListComp,
                ast.SetComp,
                ast.DictComp,
                ast.GeneratorExp,
            ),
        )
    ]
    if (
        legacy_attributes != [permitted_legacy_attribute]
        or forbidden_dynamic_references
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    # The compatibility path may tolerate unrelated source drift, but it must
    # still prove that no second call path can bypass the reviewed guard.  This
    # deliberately checks semantic references rather than the entire file hash.
    permitted_fleet_calls = _calls_in(method, legacy_chain)
    permitted_fleet_attributes = {
        id(call.func) for call in permitted_fleet_calls if isinstance(call.func, ast.Attribute)
    }
    all_fleet_attributes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr == "fleet_preparation"
    ]
    global_dynamic_fleet_references = [
        node
        for node in ast.walk(tree)
        if (isinstance(node, ast.Constant) and node.value == "fleet_preparation")
        or (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id == "fleet_preparation"
        )
        or (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and _static_string(node.args[1]) == "fleet_preparation"
        )
    ]
    if (
        len(permitted_fleet_calls) != 2
        or len(all_fleet_attributes) != 2
        or {id(node) for node in all_fleet_attributes} != permitted_fleet_attributes
        or global_dynamic_fleet_references
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    reviewed_self_calls = {
        ("self", "appear"),
        ("self", "device", "click"),
        ("self", "enter_map_cancel"),
        legacy_chain,
        ("self", "handle_2x_book_setting"),
        ("self", "handle_auto_search"),
        ("self", "handle_auto_search_setting"),
        ("self", "handle_auto_submarine_call_disable"),
        ("self", "is_in_auto_search_menu"),
        ("self", "is_in_map"),
    }
    if any(
        chain is not None
        and chain[:1] == ("self",)
        and chain not in reviewed_self_calls
        for chain in (
            _attribute_chain(node.func)
            for node in ast.walk(semantic_branch)
            if isinstance(node, ast.Call)
        )
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    allowed_authorized_calls = {
        ("semantic_adapter", "prepare_campaign_hard_fleets"),
        ("self", "handle_2x_book_setting"),
        required_chain,
        legacy_chain,
        confirm_chain,
        ("self", "handle_auto_submarine_call_disable"),
        ("self", "handle_auto_search_setting"),
        ("semantic_adapter", "authorize_campaign_sortie"),
        ("self", "device", "click"),
        ("fleet_timer", "reset"),
        ("campaign_timer", "reset"),
    }
    authorized_call_chains = [
        _attribute_chain(node.func)
        for node in ast.walk(authorized)
        if isinstance(node, ast.Call)
    ]
    if any(chain not in allowed_authorized_calls for chain in authorized_call_chains):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)

    two_x_indices = [
        index
        for index, statement in enumerate(authorized.body)
        if isinstance(statement, ast.Expr)
        and _call_matches(statement.value, ("self", "handle_2x_book_setting"))
    ]
    if len(two_x_indices) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    two_x_index = two_x_indices[0]
    two_x_statement = authorized.body[two_x_index]
    assert isinstance(two_x_statement, ast.Expr)
    two_x_call = two_x_statement.value
    assert isinstance(two_x_call, ast.Call)
    if (
        two_x_call.args
        or len(two_x_call.keywords) != 1
        or two_x_call.keywords[0].arg != "mode"
        or not isinstance(two_x_call.keywords[0].value, ast.Constant)
        or two_x_call.keywords[0].value.value != "prep"
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    confirm_index = _direct_statement_index(authorized.body, confirm_chain)
    auto_submarine_index = _direct_statement_index(
        authorized.body, ("self", "handle_auto_submarine_call_disable")
    )
    auto_search_index = _direct_statement_index(
        authorized.body, ("self", "handle_auto_search_setting")
    )
    checked_indices = [
        index
        for index, statement in enumerate(authorized.body)
        if isinstance(statement, ast.Assign)
        and len(statement.targets) == 1
        and _attribute_chain(statement.targets[0]) == ("self", "map_fleet_checked")
        and isinstance(statement.value, ast.Constant)
        and statement.value.value is True
    ]
    sortie_indices = [
        index
        for index, statement in enumerate(authorized.body)
        if isinstance(statement, ast.If)
        and _call_matches(
            statement.test, ("semantic_adapter", "authorize_campaign_sortie")
        )
    ]
    if len(checked_indices) != 1 or len(sortie_indices) != 1:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    sortie = authorized.body[sortie_indices[0]]
    assert isinstance(sortie, ast.If)
    sortie_clicks = _calls_in(sortie, ("self", "device", "click"))
    if (
        sortie.orelse
        or len(sortie_clicks) != 1
        or len(sortie_clicks[0].args) != 1
        or sortie_clicks[0].keywords
        or not isinstance(sortie_clicks[0].args[0], ast.Name)
        or sortie_clicks[0].args[0].id != "FLEET_PREPARATION"
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    sortie_call = sortie.test
    assert isinstance(sortie_call, ast.Call)
    expected_sortie_keywords = {
        "use_auto_search": ("self", "map_is_auto_search"),
        "use_2x_book": ("self", "map_is_2x_book"),
        "submarine_mode": ("self", "config", "Submarine_Mode"),
        "fleet_order": ("self", "config", "Fleet_FleetOrder"),
    }
    if (
        sortie_call.args
        or len(sortie_call.keywords) != len(expected_sortie_keywords)
        or {
            keyword.arg: _attribute_chain(keyword.value)
            for keyword in sortie_call.keywords
        }
        != expected_sortie_keywords
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    if not (
        two_x_index
        < guard_index
        < confirm_index
        < auto_submarine_index
        < auto_search_index
        < checked_indices[0]
        < sortie_indices[0]
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    return _normalized_ast_sha256(semantic_branch)


def _is_reparse(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _same_file(metadata: os.stat_result, other: os.stat_result) -> bool:
    try:
        return os.path.samestat(metadata, other)
    except (AttributeError, OSError, ValueError):
        return (metadata.st_dev, metadata.st_ino) == (other.st_dev, other.st_ino)


def _same_open_snapshot(metadata: os.stat_result, other: os.stat_result) -> bool:
    return _same_file(metadata, other) and (
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    ) == (other.st_size, other.st_mtime_ns, other.st_ctime_ns)


def _same_file_size(metadata: os.stat_result, other: os.stat_result) -> bool:
    return _same_file(metadata, other) and metadata.st_size == other.st_size


@dataclass(frozen=True)
class _VerifiedMaterializedAlasSource:
    root: Path
    origin: Path
    source: bytes
    proof: dict[str, str]


def _canonical_materialized_source(payload: bytes) -> bytes:
    if payload.startswith(b"\xef\xbb\xbf"):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    source = payload.decode("utf-8", errors="strict")
    return source.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _read_verified_materialized_alas_source(
    alas_root: Path, *, classification: str
) -> _VerifiedMaterializedAlasSource:
    try:
        root = alas_root.resolve(strict=True)
        root_before = os.stat(root, follow_symlinks=False)
        if not stat.S_ISDIR(root_before.st_mode) or _is_reparse(root_before):
            raise MaterializedAlasAdmissionError(classification)
        candidate = root / MATERIALIZED_ALAS_RELATIVE_PATH
        resolved = candidate.resolve(strict=True)
        if resolved != candidate or not resolved.is_file():
            raise MaterializedAlasAdmissionError(classification)
        path_before = os.stat(resolved, follow_symlinks=False)
        if (
            not stat.S_ISREG(path_before.st_mode)
            or _is_reparse(path_before)
            or path_before.st_size <= 0
            or path_before.st_size > MATERIALIZED_ALAS_MAX_SOURCE_BYTES
        ):
            raise MaterializedAlasAdmissionError(classification)
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOINHERIT", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(resolved, flags)
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            opened_before = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(opened_before.st_mode)
                or _is_reparse(opened_before)
                or not _same_file_size(opened_before, path_before)
            ):
                raise MaterializedAlasAdmissionError(classification)
            payload = stream.read(MATERIALIZED_ALAS_MAX_SOURCE_BYTES + 1)
            opened_after = os.fstat(stream.fileno())
            path_after = os.stat(resolved, follow_symlinks=False)
            root_after = os.stat(root, follow_symlinks=False)
            if (
                len(payload) != opened_before.st_size
                or len(payload) > MATERIALIZED_ALAS_MAX_SOURCE_BYTES
                or not _same_open_snapshot(opened_before, opened_after)
                or not _same_file_size(opened_after, path_after)
                or not _same_file(root_before, root_after)
                or not stat.S_ISDIR(root_after.st_mode)
                or _is_reparse(path_after)
                or _is_reparse(root_after)
            ):
                raise MaterializedAlasAdmissionError(classification)
        canonical_payload = _canonical_materialized_source(payload)
        canonical_sha256 = hashlib.sha256(canonical_payload).hexdigest()
        tree = ast.parse(
            canonical_payload.decode("utf-8", errors="strict"),
            filename=MATERIALIZED_ALAS_RELATIVE_PATH.as_posix(),
        )
        semantic_branch_sha256 = _validate_materialized_enter_map(tree)
    except MaterializedAlasAdmissionError as exc:
        if exc.classification != classification:
            raise MaterializedAlasAdmissionError(classification) from exc
        raise
    except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError) as exc:
        raise MaterializedAlasAdmissionError(classification) from exc
    proof = {
        "schema": MATERIALIZED_ALAS_PROOF_SCHEMA,
        "capability_id": MATERIALIZED_ALAS_CAPABILITY_ID,
        "relative_path": MATERIALIZED_ALAS_RELATIVE_PATH.as_posix(),
        "canonical_source_sha256": canonical_sha256,
        "semantic_branch_sha256": semantic_branch_sha256,
    }
    return _VerifiedMaterializedAlasSource(root, resolved, canonical_payload, proof)


def _materialized_alas_proof(alas_root: Path) -> dict[str, str]:
    return dict(
        _read_verified_materialized_alas_source(
            alas_root, classification=MATERIALIZED_ALAS_UNPROVEN
        ).proof
    )


def _materialized_alas_support_classification(proof: Mapping[str, Any]) -> str:
    if (
        proof.get("canonical_source_sha256")
        == MATERIALIZED_ALAS_CANONICAL_SOURCE_SHA256
        and proof.get("semantic_branch_sha256")
        == MATERIALIZED_ALAS_SEMANTIC_BRANCH_SHA256
    ):
        return MATERIALIZED_ALAS_BASELINE
    return MATERIALIZED_ALAS_COMPATIBLE


def _validate_materialized_alas_proof(value: Any) -> dict[str, str]:
    expected = {
        "schema",
        "capability_id",
        "relative_path",
        "canonical_source_sha256",
        "semantic_branch_sha256",
    }
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("schema") != MATERIALIZED_ALAS_PROOF_SCHEMA
        or value.get("capability_id") != MATERIALIZED_ALAS_CAPABILITY_ID
        or value.get("relative_path") != MATERIALIZED_ALAS_RELATIVE_PATH.as_posix()
        or not isinstance(value.get("canonical_source_sha256"), str)
        or _SHA256_HEX.fullmatch(value["canonical_source_sha256"]) is None
        or not isinstance(value.get("semantic_branch_sha256"), str)
        or _SHA256_HEX.fullmatch(value["semantic_branch_sha256"]) is None
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    return dict(value)


def _validate_loaded_materialized_alas(
    value: Any, *, expected_proof: Mapping[str, Any]
) -> dict[str, Any]:
    expected = {
        "schema",
        "capability_id",
        "loader_id",
        "module_name",
        "relative_path",
        "canonical_source_sha256",
        "semantic_branch_sha256",
        "support_classification",
        "load_count",
        "proof",
    }
    proof = _validate_materialized_alas_proof(expected_proof)
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or value.get("schema") != MATERIALIZED_ALAS_LOADED_SCHEMA
        or value.get("capability_id") != MATERIALIZED_ALAS_CAPABILITY_ID
        or value.get("loader_id") != MATERIALIZED_ALAS_LOADER_ID
        or value.get("module_name") != MATERIALIZED_ALAS_MODULE_NAME
        or value.get("relative_path") != MATERIALIZED_ALAS_RELATIVE_PATH.as_posix()
        or value.get("canonical_source_sha256") != proof["canonical_source_sha256"]
        or value.get("semantic_branch_sha256") != proof["semantic_branch_sha256"]
        or value.get("support_classification")
        != _materialized_alas_support_classification(proof)
        or not isinstance(value.get("load_count"), int)
        or isinstance(value.get("load_count"), bool)
        or value["load_count"] < 1
        or _validate_materialized_alas_proof(value.get("proof")) != proof
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
    return dict(value)


class _VerifiedMapOperationImporter(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    """Import only map_operation from the already verified immutable bytes."""

    def __init__(self, verified: _VerifiedMaterializedAlasSource) -> None:
        self.verified = verified
        self.loaded_digest: str | None = None
        self.load_count = 0

    def find_spec(
        self,
        fullname: str,
        path: Any = None,
        target: ModuleType | None = None,
    ) -> Any:
        if fullname != MATERIALIZED_ALAS_MODULE_NAME:
            return None
        if target is not None and target.__name__ != MATERIALIZED_ALAS_MODULE_NAME:
            raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
        if path is None:
            raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
        try:
            parents = {Path(item).resolve(strict=True) for item in path}
        except (OSError, TypeError, ValueError) as exc:
            raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED) from exc
        if self.verified.origin.parent not in parents:
            raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
        spec = importlib.util.spec_from_loader(
            fullname, self, origin=str(self.verified.origin)
        )
        if spec is None:
            raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
        return spec

    def create_module(self, spec: Any) -> ModuleType | None:
        if (
            spec.name != MATERIALIZED_ALAS_MODULE_NAME
            or spec.origin != str(self.verified.origin)
            or spec.loader is not self
        ):
            raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
        return None

    def exec_module(self, module: ModuleType) -> None:
        spec = module.__spec__
        if (
            module.__name__ != MATERIALIZED_ALAS_MODULE_NAME
            or spec is None
            or spec.name != MATERIALIZED_ALAS_MODULE_NAME
            or spec.origin != str(self.verified.origin)
            or spec.loader is not self
        ):
            raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
        digest = hashlib.sha256(self.verified.source).hexdigest()
        if digest != self.verified.proof["canonical_source_sha256"]:
            raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
        module.__file__ = str(self.verified.origin)
        code = compile(
            self.verified.source,
            str(self.verified.origin),
            "exec",
            dont_inherit=True,
        )
        exec(code, module.__dict__)
        self.loaded_digest = digest
        self.load_count += 1


def _install_verified_map_operation_importer(
    verified: _VerifiedMaterializedAlasSource,
) -> _VerifiedMapOperationImporter:
    if MATERIALIZED_ALAS_MODULE_NAME in sys.modules or any(
        isinstance(finder, _VerifiedMapOperationImporter) for finder in sys.meta_path
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
    importer = _VerifiedMapOperationImporter(verified)
    sys.meta_path.insert(0, importer)
    return importer


def _confirm_verified_map_operation_loaded(
    importer: _VerifiedMapOperationImporter,
) -> dict[str, Any]:
    module = sys.modules.get(MATERIALIZED_ALAS_MODULE_NAME)
    spec = getattr(module, "__spec__", None)
    proof = _validate_materialized_alas_proof(importer.verified.proof)
    if (
        module is None
        or module.__loader__ is not importer
        or spec is None
        or spec.loader is not importer
        or spec.name != MATERIALIZED_ALAS_MODULE_NAME
        or spec.origin != str(importer.verified.origin)
        or importer.loaded_digest != proof["canonical_source_sha256"]
        or importer.load_count < 1
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
    return {
        "schema": MATERIALIZED_ALAS_LOADED_SCHEMA,
        "capability_id": MATERIALIZED_ALAS_CAPABILITY_ID,
        "loader_id": MATERIALIZED_ALAS_LOADER_ID,
        "module_name": MATERIALIZED_ALAS_MODULE_NAME,
        "relative_path": MATERIALIZED_ALAS_RELATIVE_PATH.as_posix(),
        "canonical_source_sha256": proof["canonical_source_sha256"],
        "semantic_branch_sha256": proof["semantic_branch_sha256"],
        "support_classification": _materialized_alas_support_classification(proof),
        "load_count": importer.load_count,
        "proof": proof,
    }


def _materialization_control_record(
    proof: Mapping[str, Any],
    *,
    run_id: str,
    task: str,
    stage: str,
    event: str,
    deadline_seconds: int,
    parent_pid: int,
    alas_root: Path,
) -> dict[str, Any]:
    proof = _validate_materialized_alas_proof(proof)
    body: dict[str, Any] = {
        "schema": MATERIALIZED_ALAS_CONTROL_SCHEMA,
        "run_id": run_id,
        "task": task,
        "stage": stage,
        "event": event,
        "deadline_seconds": deadline_seconds,
        "parent_pid": parent_pid,
        "alas_root": str(alas_root),
        "proof": proof,
    }
    return body


def _validate_materialization_control_record(
    value: Mapping[str, Any],
    *,
    control: WorkerControl,
    args: argparse.Namespace,
) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    body = dict(value)
    expected_fields = {
        "schema",
        "run_id",
        "task",
        "stage",
        "event",
        "deadline_seconds",
        "parent_pid",
        "alas_root",
        "proof",
    }
    if (
        set(body) != expected_fields
        or body.get("schema") != MATERIALIZED_ALAS_CONTROL_SCHEMA
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    if dict(value) != dict(control.materialization_control):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    binding = control.binding
    try:
        args_root = args.alas_root.resolve(strict=True)
    except OSError as exc:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED) from exc
    if (
        body.get("run_id") != binding.run_id
        or body.get("task") != binding.task
        or body.get("stage") != binding.stage
        or body.get("event") != binding.event
        or body.get("deadline_seconds") != binding.deadline_seconds
        or body.get("parent_pid") != binding.parent_pid
        or body.get("alas_root") != str(args_root)
    ):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    return _validate_materialized_alas_proof(body.get("proof"))


def _worker_materialization_admission(
    environment: Mapping[str, str],
    *,
    control: WorkerControl,
    args: argparse.Namespace,
) -> _VerifiedMaterializedAlasSource:
    raw = environment.get(MATERIALIZED_ALAS_CONTROL_ENV)
    if not isinstance(raw, str):
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN)
    try:
        encoded = raw.encode("utf-8", errors="strict")
        value = strict_json_mapping_bytes(
            encoded,
            maximum=MATERIALIZED_ALAS_MAX_CONTROL_BYTES,
            label="materialized ALAS control",
        )
    except (UnicodeError, ValueError) as exc:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_UNPROVEN) from exc
    proof = _validate_materialization_control_record(value, control=control, args=args)
    observed = _read_verified_materialized_alas_source(
        args.alas_root, classification=MATERIALIZED_ALAS_CHANGED
    )
    if observed.proof != proof:
        raise MaterializedAlasAdmissionError(MATERIALIZED_ALAS_CHANGED)
    return observed


@dataclass
class _WorkerRunStatus:
    phase: str = "pre_init"
    execution_state: str = "not_started"
    cleanup: Mapping[str, Any] | None = None
    seed_handle_consumed: bool = False


def _is_generation(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _stage_difficulty(stage: str) -> str:
    code = stage.strip().lower()
    return "hard" if code.startswith(("c", "d")) else "normal"


def _total_deadline(args: argparse.Namespace) -> int | None:
    """Validate EventSp's outer deadline before any runtime or config access."""

    value = getattr(args, "total_deadline_seconds", None)
    if (
        getattr(args, "task", None) == "EventSp"
        and getattr(args, "use_auto_search", None) is True
    ):
        if value is None:
            raise ValueError("EventSp qualification requires --total-deadline-seconds")
        return validate_total_deadline(value)
    return None


def _event_sp_seed_name(args: argparse.Namespace) -> str | None:
    """Reject every EventSp auto-search seed except the pinned tracked template."""

    value = getattr(args, "seed_config", None)
    if (
        getattr(args, "task", None) == "EventSp"
        and getattr(args, "use_auto_search", None) is True
    ):
        if value != EVENT_SP_SEED_NAME:
            raise ValueError("EventSp qualification requires --seed-config=template")
        return EVENT_SP_SEED_NAME
    return value


def _require_mapping_path(
    value: Mapping[str, Any], path: tuple[str, ...]
) -> Mapping[str, Any]:
    current: Any = value
    for component in path:
        if not isinstance(current, Mapping) or component not in current:
            raise ValueError("pinned template structure is incomplete")
        current = current[component]
    if not isinstance(current, Mapping):
        raise ValueError("pinned template group is malformed")
    return current


def _validate_event_sp_template_structure(value: Mapping[str, Any]) -> None:
    emulator = _require_mapping_path(value, ("Alas", "Emulator"))
    for field in (
        "Serial",
        "PackageName",
        "ServerName",
        "ScreenshotMethod",
        "ControlMethod",
    ):
        if not isinstance(emulator.get(field), str):
            raise ValueError("pinned template emulator field is malformed")
    required_groups = {
        "Scheduler": ("Enable", "Command"),
        "Campaign": (
            "Name",
            "Event",
            "Mode",
            "UseClearMode",
            "UseFleetLock",
            "UseAutoSearch",
            "Use2xBook",
        ),
        "StopCondition": (
            "OilLimit",
            "RunCount",
            "MapAchievement",
            "StageIncrease",
            "GetNewShip",
            "ReachLevel",
        ),
        "Fleet": ("Fleet1", "Fleet2", "FleetOrder"),
        "Submarine": ("Fleet", "Mode"),
        "HpControl": (
            "UseHpBalance",
            "UseEmergencyRepair",
            "UseLowHpRetreat",
        ),
        "Storage": ("Storage",),
    }
    for group_name, fields in required_groups.items():
        group = _require_mapping_path(value, ("EventSp", group_name))
        if any(field not in group for field in fields):
            raise ValueError("pinned EventSp template structure is incomplete")
    storage = _require_mapping_path(value, ("EventSp", "Storage", "Storage"))
    if storage:
        raise ValueError("pinned EventSp template storage is not pristine")


def _validate_event_sp_template_payload(payload: bytes) -> Mapping[str, Any]:
    try:
        value = strict_json_mapping_bytes(
            payload,
            maximum=MAX_CONFIG_BYTES,
            label="pinned EventSp template",
        )
        _validate_event_sp_template_structure(value)
    except ValueError as exc:
        raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_UNPROVEN) from exc
    return value


def _event_sp_template_support_classification(sha256: str) -> str:
    if hmac.compare_digest(sha256, EVENT_SP_TEMPLATE_SHA256):
        return MATERIALIZED_ALAS_BASELINE
    return MATERIALIZED_ALAS_COMPATIBLE


def _admit_event_sp_template(
    alas_root: Path,
    *,
    input_factory: Any = open_immutable_input,
) -> tuple[ImmutableInputFile, SeedSource, Mapping[str, Any]]:
    expected_root = alas_root / "config"
    expected_path = expected_root / "template.json"
    source_file: ImmutableInputFile | None = None
    try:
        source_file, payload = input_factory(expected_path, maximum=MAX_CONFIG_BYTES)
        if (
            not isinstance(source_file, ImmutableInputFile)
            or source_file.path != expected_path
            or source_file.root_path != expected_root
        ):
            raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_UNPROVEN)
        value = _validate_event_sp_template_payload(payload)
        if source_file.size != len(payload) or not hmac.compare_digest(
            source_file.sha256, hashlib.sha256(payload).hexdigest()
        ):
            raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_CHANGED)
        source = source_file.source(
            capability=EVENT_SP_SEED_CAPABILITY,
            seed_name=EVENT_SP_SEED_NAME,
        )
        return source_file, source, value
    except EventSpTemplateAdmissionError:
        if source_file is not None:
            source_file.close_parent()
        raise
    except BaseException as exc:
        if source_file is not None:
            source_file.close_parent()
        raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_UNPROVEN) from exc


def _read_worker_event_sp_template(
    control: WorkerControl, args: argparse.Namespace
) -> Mapping[str, Any]:
    source = control.seed_source
    try:
        validate_worker_control_root(control)
    except (OSError, RuntimeError, ValueError) as exc:
        raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_CHANGED) from exc
    try:
        payload, identity = read_bytes_handle(control.handles.seed, MAX_CONFIG_BYTES)
    except BaseException as exc:
        raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_CHANGED) from exc
    try:
        alas_root = args.alas_root.resolve(strict=True)
    except OSError as exc:
        raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_CHANGED) from exc
    expected_root = alas_root / "config"
    expected_path = expected_root / "template.json"
    if (
        _event_sp_seed_name(args) != EVENT_SP_SEED_NAME
        or source.capability != EVENT_SP_SEED_CAPABILITY
        or source.seed_name != EVENT_SP_SEED_NAME
        or source.path != expected_path
        or source.root_path != expected_root
    ):
        raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_UNPROVEN)
    if (
        identity != source.identity
        or len(payload) != source.size
        or not hmac.compare_digest(hashlib.sha256(payload).hexdigest(), source.sha256)
    ):
        raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_CHANGED)
    try:
        validate_worker_control_root(control)
    except (OSError, RuntimeError, ValueError) as exc:
        raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_CHANGED) from exc
    return _validate_event_sp_template_payload(payload)


def _execution_budgets(args: argparse.Namespace) -> dict[str, int | None]:
    """Validate the complete run contract before config, ALAS, or environment use."""

    argument_names = {
        "stage_entry": "stage_entry_budget",
        "fleet_mutation": "fleet_mutation_budget",
        "sortie": "sortie_budget",
        "combat": "combat_budget",
        "viewport_swipe": "viewport_swipe_budget",
        "camera_positioning": "camera_positioning_budget",
        "recovery_total": "recovery_total",
    }
    if getattr(args, "task", None) == "EventSp":
        stage = getattr(args, "stage", None)
        if not isinstance(stage, str) or stage.strip().lower() != "sp":
            raise ValueError("EventSp qualification requires the exact SP stage")
        if getattr(args, "use_auto_search", None) is not True:
            raise ValueError("EventSp qualification requires --use-auto-search")
        budgets: dict[str, int | None] = {}
        for capability, expected in EVENT_SP_EXECUTION_BUDGETS.items():
            argument_name = argument_names.get(capability)
            if argument_name is None:
                # grid_click is the adapter capability funded by combat_budget.
                value = budgets["combat"]
            else:
                value = getattr(args, argument_name, None)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value != expected
            ):
                flag = "--" + (argument_name or "combat_budget").replace("_", "-")
                raise ValueError(
                    "EventSp qualification requires {0}={1}".format(flag, expected)
                )
            budgets[capability] = value
        return budgets

    budgets = dict(LEGACY_EXECUTION_BUDGET_DEFAULTS)
    for capability, argument_name in argument_names.items():
        value = getattr(args, argument_name, None)
        if capability == "recovery_total":
            budgets[capability] = value
            continue
        if value is not None:
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError("budgets must be non-negative integers")
            budgets[capability] = value
            if capability == "combat":
                budgets["grid_click"] = value
    if budgets["camera_positioning"] not in (0, 1, 2):
        raise ValueError("camera positioning budget must be at most two")
    return budgets


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _public_error(
    exc: BaseException, *, purpose: str, classification: str | None = None
) -> dict[str, Any]:
    result = dict(public_exception_descriptor(exc, purpose))
    if classification is not None:
        result["classification"] = classification
    return result


def _execution_claim(
    *,
    activation_may_have_been_delivered: bool,
    trusted_execution_state: str | None = None,
) -> dict[str, Any]:
    """Derive the execution claim from schema-checked, run-bound evidence."""

    if trusted_execution_state is not None:
        if trusted_execution_state == "not_started":
            return {"execution_state": "not_started", "executed": False}
        if trusted_execution_state in ("started", "unknown", "finished"):
            return {"execution_state": trusted_execution_state, "executed": None}
        raise ValueError("trusted worker execution state is unsupported")
    if activation_may_have_been_delivered:
        return {"execution_state": "unknown", "executed": None}
    return {"execution_state": "not_started", "executed": False}


def _public_json_bytes(value: Mapping[str, Any], control: WorkerControl) -> bytes:
    ensure_secret_free_payload(value, control.activation_token)
    return canonical_json_bytes(value)


def _write_public_json_handle(
    handle: int,
    value: Mapping[str, Any],
    control: WorkerControl,
    *,
    expected_identity: FileIdentity | None = None,
) -> FileIdentity:
    ensure_secret_free_payload(value, control.activation_token)
    if expected_identity is None:
        return write_json_handle(handle, value)
    return write_json_handle(handle, value, expected_identity=expected_identity)


def _load_json(path: Path) -> Mapping[str, Any]:
    return strict_json_mapping_bytes(
        path.read_bytes(), maximum=2 * 1024 * 1024, label=str(path)
    )


def _close_semantic_session(instance: object) -> None:
    device = getattr(instance, "__dict__", {}).get("device")
    session = getattr(device, "__dict__", {}).get("semantic_adapter")
    if session is not None:
        session.close()


def _surface_visible(probe: Any, *, strict: bool = False) -> bool:
    try:
        return bool(probe())
    except Exception as exc:
        if exc.__class__.__name__ != "SemanticGateClosed" or strict:
            raise
        return False


def _serialize_proof(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, Mapping):
        return dict(value)
    return dict(vars(value))


def _classify_event_sp_run_error(exc: Exception) -> str:
    message = str(exc).lower()
    classifications = (
        ("result target is ambiguous", "event_sp.total_result_target_ambiguous"),
        (
            "official combat automation is disabled",
            "event_sp.official_combat_auto_disabled",
        ),
        (
            "official combat automation was not proven",
            "event_sp.official_combat_auto_not_proven",
        ),
        ("generation did not advance", "event_sp.generation_not_advanced"),
        ("did not advance generation", "event_sp.generation_not_advanced"),
        ("stale", "event_sp.semantic_snapshot_stale"),
        ("ambiguous", "event_sp.semantic_target_ambiguous"),
        ("incomplete", "event_sp.evidence_stage_incomplete"),
        ("did not reach the total-reward", "event_sp.completion_stage_missing"),
    )
    for fragment, classification in classifications:
        if fragment in message:
            return classification
    return "event_sp.run_failed"


def _event_sp_attempt_observation(
    oracle: Any,
    *,
    minimum_generation: int,
) -> tuple[Mapping[str, Any] | None, tuple[str, ...]]:
    """Read the unique final SP daily-attempt text from typed Unity UI state."""

    try:
        ui_state = oracle.read_ui_state()
    except Exception as exc:
        if exc.__class__.__name__ not in (
            "SemanticGateClosed",
            "SemanticTargetMissing",
        ):
            raise
        return None, ("event_sp.final_attempt_snapshot_unavailable",)
    if (
        not _is_generation(minimum_generation)
        or not _is_generation(ui_state.generation)
        or ui_state.generation < minimum_generation
        or ui_state.generation > minimum_generation + 2
    ):
        return None, ("event_sp.final_attempt_snapshot_incoherent",)
    matches = []
    for item in ui_state.texts:
        if (
            EVENT_SP_ATTEMPT_PATH.fullmatch(item.path) is None
            or not isinstance(item.text, str)
            or not item.active_in_hierarchy
            or not item.active_and_enabled
            or item.truncated
        ):
            continue
        text_match = EVENT_SP_ATTEMPT_TEXT.fullmatch(item.text.strip())
        if text_match is not None:
            matches.append((item, text_match.group(1)))
    if len(matches) != 1:
        return None, ("event_sp.final_attempt_text_absent_or_ambiguous",)
    item, normalized_text = matches[0]
    return (
        {
            "generation": ui_state.generation,
            "path": item.path,
            "text": normalized_text,
            "raw_text": item.text.strip(),
        },
        (),
    )


def _validate_event_sp_auto_search_evidence(
    *,
    task: str,
    stage: str,
    use_auto_search: bool,
    sortie_proof: Any,
    completion_proof: Any,
    final_generation: int,
    final_surface: Mapping[str, bool],
    run_count_before: int,
    run_count_after: Any,
    attempt_observation: Mapping[str, Any] | None,
    attempt_errors: tuple[str, ...] = (),
    bundle_errors: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Classify every required same-process EventSp evidence boundary."""

    if task != "EventSp":
        return ()
    errors: list[str] = list(attempt_errors)
    errors.extend("event_sp." + item for item in bundle_errors)
    if stage.strip().lower() != "sp":
        errors.append("event_sp.stage_identity_mismatch")
    if not use_auto_search:
        errors.append("event_sp.auto_search_required")

    sortie_generation = map_generation = None
    if sortie_proof is None:
        errors.append("event_sp.sortie_proof_missing")
    else:
        if getattr(sortie_proof, "stage_code", None) != "sp":
            errors.append("event_sp.sortie_proof_stage_mismatch")
        sortie_generation = getattr(sortie_proof, "sortie_generation", None)
        map_generation = getattr(sortie_proof, "map_generation", None)
        if (
            not _is_generation(sortie_generation)
            or not _is_generation(map_generation)
            or map_generation <= sortie_generation
        ):
            errors.append("event_sp.auto_search_start_generation_not_advanced")
        root_path = getattr(sortie_proof, "map_root_path", "")
        if not isinstance(root_path, str) or not root_path.endswith(AUTO_SEARCH_ROOTS):
            errors.append("event_sp.auto_search_start_root_unreviewed")

    exit_receipt = None
    result_generation = combat_auto_generation = None
    if completion_proof is None:
        errors.append("event_sp.completion_proof_missing")
    else:
        if getattr(completion_proof, "stage_code", None) != "sp":
            errors.append("event_sp.completion_proof_stage_mismatch")
        if getattr(completion_proof, "combat_auto_proven", None) is not True:
            errors.append("event_sp.official_combat_auto_not_proven")
        if getattr(completion_proof, "passive_after_sortie", None) is not True:
            errors.append("event_sp.post_sortie_path_was_not_passive")
        combat_auto_generation = getattr(
            completion_proof, "combat_auto_generation", None
        )
        if (
            not _is_generation(combat_auto_generation)
            or not _is_generation(map_generation)
            or combat_auto_generation <= map_generation
        ):
            errors.append("event_sp.combat_auto_generation_not_advanced")
        result_generation = getattr(completion_proof, "result_generation", None)
        if (
            not _is_generation(result_generation)
            or not _is_generation(combat_auto_generation)
            or result_generation <= combat_auto_generation
        ):
            errors.append("event_sp.total_result_generation_not_advanced")
        result_path = getattr(completion_proof, "result_path", None)
        if not isinstance(result_path, str) or not result_path.endswith(
            TOTAL_RESULT_EXIT_SUFFIX
        ):
            errors.append("event_sp.total_result_path_unreviewed")
        exit_receipt = getattr(completion_proof, "result_exit_receipt", None)
        if exit_receipt is None:
            errors.append("event_sp.result_exit_receipt_missing")
        else:
            if (
                getattr(exit_receipt, "semantic_id", None)
                != "reward/campaign-total/exit"
                or getattr(exit_receipt, "path", None) != result_path
            ):
                errors.append("event_sp.result_exit_receipt_target_mismatch")
            receipt_generation = getattr(exit_receipt, "generation", None)
            if (
                not _is_generation(receipt_generation)
                or not _is_generation(result_generation)
                or receipt_generation < result_generation
            ):
                errors.append("event_sp.result_exit_receipt_stale")

    receipt_generation = getattr(exit_receipt, "generation", None)
    if (
        not _is_generation(final_generation)
        or not _is_generation(receipt_generation)
        or final_generation <= receipt_generation
    ):
        errors.append("event_sp.final_surface_generation_not_advanced")
    if final_surface.get("event_page") is not True:
        errors.append("event_sp.final_event_page_missing")
    if run_count_before != 1 or run_count_after != 0:
        errors.append("event_sp.run_count_postcondition_failed")
    if attempt_observation is None:
        if not attempt_errors:
            errors.append("event_sp.final_attempt_observation_missing")
    else:
        if attempt_observation.get("text") != "0/1":
            errors.append("event_sp.final_attempt_postcondition_failed")
        attempt_generation = attempt_observation.get("generation")
        if (
            not _is_generation(attempt_generation)
            or not _is_generation(final_generation)
            or attempt_generation < final_generation
            or attempt_generation > final_generation + 2
        ):
            errors.append("event_sp.final_attempt_snapshot_incoherent")
        attempt_path = attempt_observation.get("path")
        if (
            not isinstance(attempt_path, str)
            or EVENT_SP_ATTEMPT_PATH.fullmatch(attempt_path) is None
        ):
            errors.append("event_sp.final_attempt_path_unreviewed")
    return tuple(dict.fromkeys(errors))


def _wait_for_startup_surface(
    semantic_session: Any,
    *,
    timeout_seconds: float = 60.0,
    strict: bool = False,
) -> tuple[Any, Any, Mapping[str, bool]]:
    """Wait for one reviewed cold-start surface without issuing game input."""

    deadline = time.monotonic() + timeout_seconds
    while True:
        frame = semantic_session.refresh_frame(include_ui=False)
        oracle = semantic_session.open().oracle
        surfaces = {
            "main_page": _surface_visible(oracle.main_page_visible, strict=strict),
            "campaign_map": _surface_visible(oracle.campaign_is_in_map, strict=strict),
            "event_page": _surface_visible(
                oracle.event_campaign_page_visible, strict=strict
            ),
            "login": bool(
                oracle.enabled("login/enter")
                or oracle.login_update_download_available()
                or oracle.login_update_in_progress()
                or oracle.login_update_restart_prompt_available()
            ),
        }
        if any(surfaces.values()):
            return frame, oracle, surfaces
        if time.monotonic() >= deadline:
            raise RuntimeError("reviewed campaign startup surface did not appear")
        time.sleep(0.5)


def _inherited_preparation_state(oracle: Any, stage: str) -> tuple[Any, str]:
    """Read the exact preparation state, including reviewed hard-stage aliases."""

    stage_code = stage.lower()
    candidates = [stage_code]
    shared = SHARED_HARD_STAGE_ENTRANCES.get(stage_code)
    if shared is not None:
        candidates.append(shared)
    last_identity_error: Exception | None = None
    for candidate in candidates:
        try:
            return oracle.campaign_preparation_state(candidate), candidate
        except Exception as exc:
            if not (
                exc.__class__.__name__ == "SemanticGateClosed"
                and str(exc).endswith("stage identity changed")
            ):
                raise
            last_identity_error = exc
    assert last_identity_error is not None
    raise last_identity_error


def _event_sp_clean_start_stop(
    semantic_session: Any,
    oracle: Any,
    surfaces: Mapping[str, bool],
    stage: str,
) -> str | None:
    """Classify inherited EventSp state without issuing recovery input."""

    if surfaces.get("login") is True:
        return "event_sp.clean_start.login"
    if semantic_session.orphan_combat_result_visible():
        return "event_sp.clean_start.orphan_result"
    state, _observed_stage_code = _inherited_preparation_state(oracle, stage)
    if state is None:
        if surfaces.get("event_page") is True:
            selected = oracle.campaign_stage_state(stage)
            if getattr(selected, "remaining_attempts", None) == 0:
                return "event_sp.clean_start.attempt_exhausted"
        return None
    kind = getattr(state, "kind", None)
    if kind not in ("fleet", "map"):
        raise RuntimeError(f"unknown campaign preparation kind: {kind!r}")
    return "event_sp.clean_start.inherited_{0}_preparation".format(kind)


def _recover_inherited_preparation(oracle: Any, stage: str) -> int:
    """Close at most one inherited fleet layer and its map detail layer."""

    recovered = 0
    for _ in range(2):
        state, observed_stage_code = _inherited_preparation_state(oracle, stage)
        if state is None:
            break
        kind = getattr(state, "kind", None)
        if kind == "fleet":
            oracle.cancel_campaign_fleet_preparation(observed_stage_code)
        elif kind == "map":
            oracle.cancel_campaign_map_preparation(observed_stage_code)
        else:
            raise RuntimeError(f"unknown campaign preparation kind: {kind!r}")
        recovered += 1
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            try:
                next_state, _next_stage_code = _inherited_preparation_state(
                    oracle, stage
                )
            except Exception as exc:
                if exc.__class__.__name__ not in (
                    "SemanticGateClosed",
                    "SemanticTargetMissing",
                ):
                    raise
                time.sleep(0.25)
                continue
            if next_state is None or getattr(next_state, "kind", None) != kind:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(
                f"campaign {kind} preparation did not close after typed cancel"
            )
    return recovered


def _configure(
    seed: Mapping[str, Any],
    *,
    serial: str,
    task: str,
    event: str,
    stage: str,
    use_auto_search: bool,
) -> dict[str, Any]:
    payload = copy.deepcopy(seed)
    emulator = payload["Alas"]["Emulator"]
    emulator["Serial"] = serial
    # A live-qualification run must never enter ALAS's multi-method benchmark:
    # that path probes unrelated transports and can hang before the semantic
    # session exists.  ADB is the reviewed frame transport for this AVD; all
    # task actions remain owned by the semantic adapter.
    emulator["ScreenshotMethod"] = "ADB"
    target = payload[task]
    target["Scheduler"]["Command"] = task
    target["Scheduler"]["Enable"] = True
    target["Campaign"].update(
        {
            "Name": "dynamic" if task in DAILY_TASKS else stage,
            "Event": event,
            "Mode": "normal",
            "UseClearMode": use_auto_search,
            "UseFleetLock": False,
            "UseAutoSearch": use_auto_search,
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
    target["Fleet"]["Fleet1"] = 1
    target["Fleet"]["Fleet2"] = 2 if use_auto_search else 0
    target["Fleet"]["FleetOrder"] = (
        "fleet1_mob_fleet2_boss" if use_auto_search else "fleet1_all_fleet2_standby"
    )
    target["Submarine"]["Fleet"] = 0
    target["Submarine"]["Mode"] = "do_not_use"
    target["HpControl"]["UseHpBalance"] = False
    target["HpControl"]["UseEmergencyRepair"] = False
    target["HpControl"]["UseLowHpRetreat"] = False
    if task in DAILY_TASKS:
        target["EventDaily"]["StageFilter"] = stage
        target["EventDaily"]["LastStage"] = 0
    return payload


def _write_worker_forward_lease(
    semantic_session: Any,
    control: WorkerControl,
) -> ForwardLease:
    """Lease the exact dynamic forward created by this worker's session."""

    factory = getattr(semantic_session, "_runtime_handle_factory", None)
    bridge = getattr(factory, "_bridge", None)
    port = getattr(bridge, "port", None)
    pid = getattr(bridge, "pid", None)
    serial = getattr(bridge, "serial", None)
    if (
        isinstance(port, bool)
        or not isinstance(port, int)
        or not 1 <= port <= 65535
        or isinstance(pid, bool)
        or not isinstance(pid, int)
        or pid != control.verified_game_pid
        or serial != control.serial
    ):
        raise RuntimeError("worker observer forward identity is not exact")
    lease = ForwardLease(
        binding=control.binding,
        serial=control.serial,
        local="tcp:{0}".format(port),
        remote="localabstract:alas.g3.{0}".format(pid),
        verified_game_pid=pid,
        starting_forwards=control.starting_forwards,
    )
    _write_public_json_handle(
        control.handles.lease, lease.to_bound_mapping(control), control
    )
    return lease


def _worker_terminal_priority(exc: BaseException) -> int:
    if isinstance(exc, RunnerStopRequested):
        return 0
    if isinstance(exc, SystemExit):
        return 1
    return 2


def _failure_isolated_worker_cleanup(
    *,
    instance: object | None,
    prior_cwd: Path,
    config_path: Path,
    prior_env: Mapping[str, str | None],
    remove_config: bool = True,
    worker_control: WorkerControl | None = None,
    terminal_errors: list[BaseException] | None = None,
) -> dict[str, Any]:
    """Attempt every host cleanup item even if an earlier item fails."""

    actions: list[str] = []
    errors: list[dict[str, str]] = []

    def attempt(label: str, operation: Any) -> None:
        try:
            operation()
            actions.append(label)
        except BaseException as exc:
            errors.append(
                {"item": label, **_public_error(exc, purpose="worker_cleanup")}
            )
            if terminal_errors is not None and not isinstance(exc, Exception):
                terminal_errors.append(exc)

    if instance is not None:
        attempt("semantic_session_close", lambda: _close_semantic_session(instance))
    else:
        actions.append("semantic_session_not_constructed")
    attempt("cwd_restore", lambda: os.chdir(prior_cwd))
    if remove_config:
        attempt("temp_config_remove", lambda: config_path.unlink(missing_ok=True))
    else:
        actions.append("temp_config_deferred_to_parent")

    def restore_environment() -> None:
        for name, value in prior_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    attempt("environment_restore", restore_environment)
    config_state = None
    if worker_control is not None:
        try:
            config_state = inspect_owned_config(worker_control).to_mapping()
            actions.append("temp_config_state_captured")
        except BaseException as exc:
            errors.append(
                {
                    "item": "temp_config_state_capture",
                    **_public_error(exc, purpose="config_state_capture"),
                }
            )
            if terminal_errors is not None and not isinstance(exc, Exception):
                terminal_errors.append(exc)
    config_present_after = (
        bool(config_state.get("exists")) if isinstance(config_state, Mapping) else False
    )
    try:
        config_present_after = config_path.exists()
    except BaseException as exc:
        errors.append(
            {
                "item": "temp_config_presence_capture",
                **_public_error(exc, purpose="config_presence_capture"),
            }
        )
        if terminal_errors is not None and not isinstance(exc, Exception):
            terminal_errors.append(exc)
    return {
        "completed": not errors,
        "actions": actions,
        "errors": errors,
        "temp_config_path": str(config_path),
        "temp_config_present_after": config_present_after,
        "config_state": config_state,
    }


def run(
    args: argparse.Namespace,
    *,
    worker_control: WorkerControl | None = None,
    _worker_status: _WorkerRunStatus | None = None,
) -> Mapping[str, Any]:
    total_deadline = _total_deadline(args)
    _event_sp_seed_name(args)
    if args.task == "EventSp" and args.use_auto_search and worker_control is None:
        raise RuntimeError(
            "EventSp auto-search execution requires supervised worker activation"
        )
    if worker_control is not None and not worker_control.activation_verified:
        raise RuntimeError("worker control has no live activation authority")
    if worker_control is not None and (
        args.task != "EventSp"
        or total_deadline != worker_control.binding.deadline_seconds
        or getattr(args, "serial", None) != worker_control.serial
        or getattr(args, "stage", None) != worker_control.binding.stage
        or getattr(args, "event", None) != worker_control.binding.event
    ):
        raise RuntimeError(
            "supervised worker contract does not match its control lease"
        )
    execution_budgets = _execution_budgets(args)
    if worker_control is not None and execution_budgets != dict(
        worker_control.execution_budgets
    ):
        raise RuntimeError("supervised worker budget contract changed")
    worker_status = _worker_status or _WorkerRunStatus()
    materialized_alas = None
    materialized_importer = None
    if args.task == "EventSp" and args.use_auto_search:
        assert worker_control is not None
        verified_materialization = _worker_materialization_admission(
            os.environ, control=worker_control, args=args
        )
        materialized_importer = _install_verified_map_operation_importer(
            verified_materialization
        )
    alas_root = args.alas_root.resolve()
    if worker_control is None:
        config_name = f"_codex_event_live_{args.task.lower()}_{uuid.uuid4().hex}"
        config_path = alas_root / "config" / f"{config_name}.json"
    else:
        config_name = worker_control.binding.config_name
        config_path = worker_control.binding.config_path
        expected_config_path = alas_root / "config" / f"{config_name}.json"
        if config_path != expected_config_path:
            raise RuntimeError("worker config path escaped the exact ALAS config root")

    environment_names = (
        "ALAS_SEMANTIC_MODE",
        "ALAS_SEMANTIC_DRIVER_REVISION",
        "ALAS_SEMANTIC_ADB",
        "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS",
        "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS",
        "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET",
        "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET",
    )
    prior_env = {name: os.environ.get(name) for name in environment_names}
    prior_cwd = Path.cwd()
    instance = None
    login_recovery_performed = False
    orphan_result_recovery_count = 0
    preparation_recovery_count = 0
    qualification_stop = None
    started_at = _utc_now()
    result_payload: dict[str, Any] | None = None
    active_terminal: BaseException | None = None
    try:
        if worker_control is None:
            seed_path = alas_root / "config" / f"{args.seed_config}.json"
            seed = _load_json(seed_path)
        else:
            try:
                seed = _read_worker_event_sp_template(worker_control, args)
            finally:
                # read_bytes_handle owns and closes the inherited duplicate,
                # including strict-read failure paths.
                worker_status.seed_handle_consumed = True
        payload = _configure(
            seed,
            serial=args.serial,
            task=args.task,
            event=args.event,
            stage=args.stage,
            use_auto_search=args.use_auto_search,
        )
        for path in (ROOT / "python", alas_root):
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        worker_status.phase = "config_write"
        if worker_control is None:
            config_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        else:
            insert_config_marker(
                payload, worker_control.binding, worker_control.config_ownership
            )
            write_json_handle(
                worker_control.handles.config,
                payload,
                expected_identity=worker_control.config_ownership.initial_identity,
            )
            verify_initial_config(worker_control)
        os.environ.update(
            {
                "ALAS_SEMANTIC_MODE": "1",
                "ALAS_SEMANTIC_DRIVER_REVISION": args.driver_revision,
                "ALAS_SEMANTIC_ADB": args.adb,
                "ALAS_SEMANTIC_ADB_COMMAND_TIMEOUT_SECONDS": "30",
                "ALAS_SEMANTIC_OBSERVER_MAX_AGE_MS": "60000",
                "ALAS_SEMANTIC_CAMPAIGN_STAGE_ENTRY_BUDGET": str(
                    execution_budgets["stage_entry"]
                ),
                "ALAS_SEMANTIC_CAMPAIGN_FLEET_MUTATION_BUDGET": str(
                    execution_budgets["fleet_mutation"]
                ),
                "ALAS_SEMANTIC_CAMPAIGN_SORTIE_BUDGET": str(
                    execution_budgets["sortie"]
                ),
                "ALAS_SEMANTIC_CAMPAIGN_COMBAT_BUDGET": str(
                    execution_budgets["combat"]
                ),
                "ALAS_SEMANTIC_CAMPAIGN_VIEWPORT_SWIPE_BUDGET": str(
                    execution_budgets["viewport_swipe"]
                ),
            }
        )
        os.chdir(alas_root)
        worker_status.phase = "alas_import"
        if materialized_importer is not None:
            importlib.import_module(MATERIALIZED_ALAS_MODULE_NAME)
            materialized_alas = _confirm_verified_map_operation_loaded(
                materialized_importer
            )
        from alas import AzurLaneAutoScript

        worker_status.phase = "alas_construct"
        instance = AzurLaneAutoScript(config_name)
        instance.config.init_task(args.task)
        runtime_name = "dynamic" if args.task in DAILY_TASKS else args.stage
        runtime_overrides = {
            "Campaign_Event": args.event,
            "Campaign_Name": runtime_name,
            "Campaign_Mode": "normal",
            "Campaign_UseClearMode": args.use_auto_search,
            "Campaign_UseFleetLock": False,
            "Campaign_UseAutoSearch": args.use_auto_search,
            "Campaign_Use2xBook": False,
            "StopCondition_OilLimit": 0,
            "StopCondition_RunCount": 1,
            "StopCondition_MapAchievement": "non_stop",
            "StopCondition_StageIncrease": False,
            "StopCondition_GetNewShip": False,
            "StopCondition_ReachLevel": 0,
            "Fleet_Fleet1": 1,
            "Fleet_Fleet2": 2 if args.use_auto_search else 0,
            "Fleet_FleetOrder": (
                "fleet1_mob_fleet2_boss"
                if args.use_auto_search
                else "fleet1_all_fleet2_standby"
            ),
            "Submarine_Fleet": 0,
            "Submarine_Mode": "do_not_use",
            "HpControl_UseHpBalance": False,
            "HpControl_UseEmergencyRepair": False,
            "HpControl_UseLowHpRetreat": False,
        }
        if args.task in DAILY_TASKS:
            runtime_overrides.update(
                {
                    "EventDaily_StageFilter": args.stage,
                    "EventDaily_LastStage": 0,
                }
            )
        instance.config.override(**runtime_overrides)
        effective_config = {
            "event": instance.config.Campaign_Event,
            "name": instance.config.Campaign_Name,
            "mode": instance.config.Campaign_Mode,
            "use_auto_search": instance.config.Campaign_UseAutoSearch,
            "run_count": instance.config.StopCondition_RunCount,
        }
        if effective_config != {
            "event": args.event,
            "name": runtime_name,
            "mode": "normal",
            "use_auto_search": args.use_auto_search,
            "run_count": 1,
        }:
            raise RuntimeError(
                f"effective Event configuration drifted: {effective_config!r}"
            )
        semantic_session = instance.device.semantic_adapter
        # A cold game start publishes the observer socket before Unity has
        # committed its first semantic frame.  Enter through the session clock
        # so that this one explicitly bounded startup gap is retried without
        # weakening any target or input gate.
        worker_status.phase = "startup"
        startup_frame, startup_oracle, startup_surfaces = _wait_for_startup_surface(
            semantic_session,
            strict=args.task == "EventSp",
        )
        if worker_control is not None:
            _write_worker_forward_lease(semantic_session, worker_control)
        starting_surface = {
            "main_page": startup_surfaces["main_page"],
            "campaign_map": startup_surfaces["campaign_map"],
            "event_page": startup_surfaces["event_page"],
            "generation": startup_frame.generation,
        }
        if args.task == "EventSp":
            qualification_stop = _event_sp_clean_start_stop(
                semantic_session,
                startup_oracle,
                startup_surfaces,
                args.stage,
            )
        else:
            if (
                startup_oracle.enabled("login/enter")
                or startup_oracle.login_update_download_available()
                or startup_oracle.login_update_in_progress()
                or startup_oracle.login_update_restart_prompt_available()
            ):
                from module.handler.login import LoginHandler

                LoginHandler(instance.config, device=instance.device).handle_app_login()
                login_recovery_performed = True
            if semantic_session.orphan_combat_result_visible():
                orphan_result_recovery_count = len(
                    semantic_session.recover_orphan_combat_result()
                )
            preparation_recovery_count = _recover_inherited_preparation(
                semantic_session.open().oracle,
                args.stage,
            )
        if qualification_stop is not None:
            run_result = False
            run_error = {
                "type": "QualificationStop",
                "message": qualification_stop,
                "classification": qualification_stop,
            }
        else:
            if args.task == "EventSp":
                semantic_session.bind_next_campaign_evidence_owner("EventSp")
            run_error = None
            try:
                worker_status.phase = "task_run"
                worker_status.execution_state = "started"
                run_result = instance.run(RUN_METHODS[args.task])
                worker_status.execution_state = "finished"
            except Exception as exc:
                if args.task != "EventSp":
                    raise
                run_result = False
                run_error = _public_error(
                    exc,
                    purpose="event_sp_task_run",
                    classification=_classify_event_sp_run_error(exc),
                )
        worker_status.phase = "post_run"
        post = _load_json(config_path)
        task_post = post[args.task]
        adapter = instance.device.semantic_adapter.open()
        final_surface = {
            "main_page": _surface_visible(adapter.oracle.main_page_visible),
            "campaign_map": _surface_visible(adapter.oracle.campaign_is_in_map),
            "event_page": _surface_visible(adapter.oracle.event_campaign_page_visible),
        }
        state = adapter.oracle.read_state()
        run_count = task_post["StopCondition"]["RunCount"]
        enabled = task_post["Scheduler"]["Enable"]
        evidence_bundle = None
        bundle_errors: tuple[str, ...] = ()
        if args.task == "EventSp":
            evidence_bundle = semantic_session.consume_campaign_auto_search_evidence(
                expected_owner="EventSp",
                expected_stage_code=args.stage,
                expected_mode=_stage_difficulty(args.stage),
            )
            if evidence_bundle is None:
                bundle_errors = ("evidence_bundle_missing_or_consumed",)
        sortie_proof = (
            evidence_bundle.sortie_proof if evidence_bundle is not None else None
        )
        completion_proof = (
            evidence_bundle.completion_proof if evidence_bundle is not None else None
        )
        if evidence_bundle is not None:
            bundle_errors = evidence_bundle.integrity_errors
        attempt_observation = None
        attempt_errors: tuple[str, ...] = ()
        if args.task == "EventSp":
            attempt_observation, attempt_errors = _event_sp_attempt_observation(
                adapter.oracle,
                minimum_generation=state.generation,
            )
        validation_errors = list(
            _validate_event_sp_auto_search_evidence(
                task=args.task,
                stage=args.stage,
                use_auto_search=args.use_auto_search,
                sortie_proof=sortie_proof,
                completion_proof=completion_proof,
                final_generation=state.generation,
                final_surface=final_surface,
                run_count_before=1,
                run_count_after=run_count,
                attempt_observation=attempt_observation,
                attempt_errors=attempt_errors,
                bundle_errors=bundle_errors,
            )
        )
        if run_error is not None:
            validation_errors.insert(0, run_error["classification"])
        runner_recovery_total = (
            int(login_recovery_performed)
            + orphan_result_recovery_count
            + preparation_recovery_count
        )
        if args.task == "EventSp" and runner_recovery_total != 0:
            raise RuntimeError("EventSp runner recovery budget changed")
        passed = bool(
            run_result
            and run_count == 0
            and isinstance(enabled, bool)
            and final_surface["event_page"]
            and not validation_errors
        )
        result_payload = {
            "schema": SCHEMA,
            "passed": passed,
            "started_at": started_at,
            "finished_at": _utc_now(),
            "task": args.task,
            "stage": args.stage,
            "event": args.event,
            "mode": _stage_difficulty(args.stage),
            "upstream_invocation_mode": "normal",
            "serial": args.serial,
            "driver_revision": args.driver_revision,
            "scheduler_command": task_post["Scheduler"]["Command"],
            "effective_config": effective_config,
            "run_result": bool(run_result),
            "run_error": run_error,
            "run_count_before": 1,
            "run_count_after": run_count,
            "scheduler_enabled_after": enabled,
            "event_daily_last_stage_after": (
                task_post["EventDaily"]["LastStage"]
                if args.task in DAILY_TASKS
                else None
            ),
            "use_auto_search": args.use_auto_search,
            "materialized_alas": materialized_alas,
            "login_recovery_performed": login_recovery_performed,
            "orphan_result_recovery_count": orphan_result_recovery_count,
            "preparation_recovery_count": preparation_recovery_count,
            "recovery_total": runner_recovery_total,
            "qualification_stop": qualification_stop,
            "starting_surface": starting_surface,
            "budgets": execution_budgets,
            "observer": {
                "generation": state.generation,
                "scene_handle": state.scene_handle,
                "button_count": len(state.buttons),
            },
            "final_surface": final_surface,
            "event_sp_auto_search_evidence": {
                "bundle": _serialize_proof(evidence_bundle),
                "sortie": _serialize_proof(sortie_proof),
                "completion": _serialize_proof(completion_proof),
                "final_attempt": attempt_observation,
            },
            "validation_errors": validation_errors,
            "raw_input_fallback_used": False,
        }
        return result_payload
    except BaseException as exc:
        active_terminal = exc
        raise
    finally:
        cleanup_terminals: list[BaseException] = []
        cleanup = _failure_isolated_worker_cleanup(
            instance=instance,
            prior_cwd=prior_cwd,
            config_path=config_path,
            prior_env=prior_env,
            remove_config=worker_control is None,
            worker_control=worker_control,
            terminal_errors=cleanup_terminals,
        )
        worker_status.cleanup = cleanup
        if worker_control is not None:
            try:
                cleanup_wrapper = bind_record(
                    worker_control,
                    RECORD_CLEANUP,
                    {
                        "schema": WORKER_CLEANUP_SCHEMA,
                        "binding": worker_control.binding.to_mapping(),
                        "binding_digest": binding_digest(worker_control.binding),
                        "cleanup": cleanup,
                    },
                )
                _write_public_json_handle(
                    worker_control.handles.cleanup,
                    cleanup_wrapper,
                    worker_control,
                )
            except BaseException as exc:
                cleanup["completed"] = False
                cleanup["errors"].append(
                    {
                        "item": "cleanup_status_write",
                        **_public_error(exc, purpose="cleanup_status_write"),
                    }
                )
                if not isinstance(exc, Exception):
                    cleanup_terminals.append(exc)
        if result_payload is not None:
            result_payload["worker_cleanup"] = cleanup
            if not cleanup["completed"]:
                result_payload["passed"] = False
                result_payload["validation_errors"] = list(
                    dict.fromkeys(
                        [
                            *result_payload.get("validation_errors", ()),
                            "runner.worker_cleanup_incomplete",
                        ]
                    )
                )
        if cleanup_terminals:
            terminal = min(cleanup_terminals, key=_worker_terminal_priority)
            if active_terminal is None or _worker_terminal_priority(
                terminal
            ) < _worker_terminal_priority(active_terminal):
                raise terminal


def _optional_json(
    path: Path, *, maximum: int = MAX_WORKER_RESULT_BYTES
) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        if not isinstance(path, Path):
            raise TypeError("JSON path is not a pathlib.Path")
        if not path.is_file():
            return None, None
        size = path.stat().st_size
        if size == 0:
            return None, None
        if size > maximum:
            raise ValueError("JSON artifact is oversized")
        with path.open("rb") as stream:
            payload = stream.read(maximum + 1)
        return (
            strict_json_mapping_bytes(
                payload, maximum=maximum, label="runner JSON artifact"
            ),
            None,
        )
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        return None, secret_free_exception_label(exc, "json_artifact_read")


def _optional_owned_json(
    owned: ExclusiveFile | None, *, maximum: int = MAX_WORKER_RESULT_BYTES
) -> tuple[Mapping[str, Any] | None, str | None]:
    try:
        if not isinstance(owned, ExclusiveFile) or owned.fd < 0 or not owned.owned:
            raise TypeError("owned JSON artifact is unavailable")
        owned.validate_master()
        payload = read_owned_file(owned, maximum)
        if not payload:
            return None, None
        return (
            strict_json_mapping_bytes(
                payload, maximum=maximum, label="owned runner JSON artifact"
            ),
            None,
        )
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        return None, secret_free_exception_label(exc, "owned_json_read")


def _owned_artifact_cleanup(
    owned_files: Mapping[str, ExclusiveFile],
    control_root: Path | None,
    *,
    termination_confirmed: bool,
    skip_labels: tuple[str, ...] = (),
    remove_control_root: bool = True,
) -> dict[str, Any]:
    actions: list[str] = []
    blockers: list[str] = []
    details: dict[str, Any] = {}
    if not termination_confirmed:
        blockers.append("runner.worker_termination_unconfirmed")
        details["artifacts_retained"] = [
            str(item.path) for item in owned_files.values() if item.owned
        ]
        return {
            "completed": False,
            "actions": actions,
            "blockers": blockers,
            "details": details,
        }
    for label, owned in owned_files.items():
        if label in skip_labels:
            continue
        if not owned.owned:
            continue
        try:
            owned.remove_owned_path()
            actions.append(label + "_removed")
        except BaseException as exc:
            blockers.append("runner.cleanup.owned_path_remove_failed")
            details.setdefault("owned_path_errors", []).append(
                {"item": label, **_public_error(exc, purpose="owned_path_remove")}
            )
    if control_root is not None and remove_control_root:
        try:
            control_root.rmdir()
            actions.append("internal_control_directory_removed")
        except OSError as exc:
            blockers.append("runner.cleanup.internal_directory_remove_failed")
            details["internal_directory_error"] = _public_error(
                exc, purpose="internal_directory_remove"
            )
    return {
        "completed": not blockers,
        "actions": actions,
        "blockers": list(dict.fromkeys(blockers)),
        "details": details,
    }


def _parent_fallback_cleanup(
    control: WorkerControl,
    *,
    owned_files: Mapping[str, ExclusiveFile],
    control_root: Path,
    termination_confirmed: bool,
    worker_activated: bool,
    worker_cleanup: Mapping[str, Any] | None,
    cleanup_deadline: float,
    monotonic: Any = time.monotonic,
    adb: str,
    forward_inventory: Any = adb_forward_inventory,
    remove_forward: Any = adb_remove_forward,
) -> dict[str, Any]:
    """Recover only resources proven to belong to this exact run."""

    actions: list[str] = []
    blockers: list[str] = []
    details: dict[str, Any] = {
        "config_path": str(control.binding.config_path),
        "forward": None,
    }
    if not termination_confirmed:
        blockers.append("runner.worker_termination_unconfirmed")
        details["artifacts_retained"] = [
            str(item.path) for item in owned_files.values()
        ]
        return {
            "completed": False,
            "actions": actions,
            "blockers": blockers,
            "details": details,
        }

    if worker_activated:
        lease = None
        lease_mapping, lease_error = _optional_owned_json(owned_files.get("lease"))
        if lease_error is not None:
            blockers.append("runner.cleanup.forward_lease_malformed")
            details["forward_lease_error"] = lease_error
        elif lease_mapping:
            try:
                lease = ForwardLease.from_bound_mapping(lease_mapping, control)
            except Exception as exc:
                blockers.append("runner.cleanup.forward_lease_malformed")
                details["forward_lease_error"] = _public_error(
                    exc, purpose="forward_lease_validation"
                )
        if "runner.cleanup.forward_lease_malformed" not in blockers:
            try:
                ending = forward_inventory(
                    adb,
                    control.serial,
                    timeout_seconds=remaining_seconds(cleanup_deadline, monotonic),
                )
                decision = select_forward_cleanup(
                    binding=control.binding,
                    serial=control.serial,
                    verified_game_pid=control.verified_game_pid,
                    starting=control.starting_forwards,
                    ending=ending,
                    lease=lease,
                )
                blockers.extend(decision.blockers)
                details["forward"] = {
                    "source": decision.source,
                    "already_absent": decision.already_absent,
                    "record": decision.record.to_mapping() if decision.record else None,
                }
                if decision.record is not None and not decision.blockers:
                    remove_forward(
                        adb,
                        decision.record,
                        timeout_seconds=remaining_seconds(cleanup_deadline, monotonic),
                    )
                    verified = forward_inventory(
                        adb,
                        control.serial,
                        timeout_seconds=remaining_seconds(cleanup_deadline, monotonic),
                    )
                    if decision.record in verified:
                        raise RuntimeError("exact forward remained after removal")
                    actions.append("observer_forward_removed")
                elif decision.already_absent:
                    actions.append("observer_forward_already_absent")
            except TimeoutError as exc:
                blockers.append("runner.cleanup.deadline_exhausted")
                details["forward_cleanup_error"] = _public_error(
                    exc, purpose="forward_cleanup_deadline"
                )
            except KeyboardInterrupt:
                # Preserve the runner-wide interrupt classification.  The
                # outer ownership envelope retains artifacts when this occurs
                # after supervision, so no partial cleanup is promoted.
                raise
            except Exception as exc:
                blockers.append("runner.cleanup.forward_cleanup_failed")
                details["forward_cleanup_error"] = _public_error(
                    exc, purpose="forward_cleanup"
                )

    config_file = owned_files.get("config")
    control_file = owned_files.get("control")
    config_safely_absent = False
    if config_file is None or control_file is None:
        blockers.append("runner.cleanup.config_ownership_missing")
    elif config_file.fd >= 0:
        if worker_activated:
            blockers.append("runner.cleanup.config_data_handle_state_invalid")
        else:
            try:
                config_file.remove_owned_path()
                actions.append("config_removed_before_activation")
                config_safely_absent = True
            except BaseException as exc:
                blockers.append("runner.cleanup.config_initial_remove_failed")
                details["config_cleanup_error"] = _public_error(
                    exc, purpose="config_initial_remove"
                )
    else:
        try:
            state_mapping = (
                worker_cleanup.get("config_state")
                if isinstance(worker_cleanup, Mapping)
                else None
            )
            final_state = ConfigFileState.from_mapping(state_mapping)
            delete_result = delete_owned_config_windows(
                control_file, control, final_state
            )
            details["config_state"] = delete_result.state.to_mapping()
            if delete_result.blocker is not None:
                blockers.append(delete_result.blocker)
            elif delete_result.deleted:
                actions.append("config_removed_by_validated_handle")
                config_safely_absent = True
                config_file.owned = False
            elif delete_result.already_absent:
                actions.append("config_already_absent")
                config_safely_absent = True
                config_file.owned = False
        except BaseException as exc:
            blockers.append("runner.cleanup.config_final_state_malformed")
            details["config_cleanup_error"] = _public_error(
                exc, purpose="config_final_state"
            )

    artifact_cleanup = _owned_artifact_cleanup(
        owned_files,
        control_root,
        termination_confirmed=True,
        skip_labels=("config", "control"),
        remove_control_root=False,
    )
    actions.extend(artifact_cleanup["actions"])
    blockers.extend(artifact_cleanup["blockers"])
    details.update(artifact_cleanup["details"])
    if config_safely_absent and control_file is not None and control_file.owned:
        try:
            if worker_activated:
                validate_control_lease(control_file, control)
            control_file.remove_owned_path()
            actions.append("control_removed_after_config")
        except BaseException as exc:
            blockers.append("runner.cleanup.config_control_remove_failed")
            details["control_cleanup_error"] = _public_error(
                exc, purpose="config_control_remove"
            )
    elif control_file is not None and control_file.owned:
        details["config_control_retained"] = str(control_file.path)
    if not any(item.owned for item in owned_files.values()):
        try:
            control_root.rmdir()
            actions.append("internal_control_directory_removed")
        except OSError as exc:
            blockers.append("runner.cleanup.internal_directory_remove_failed")
            details["internal_directory_error"] = _public_error(
                exc, purpose="internal_directory_remove"
            )
    if blockers:
        details["artifacts_retained"] = [
            str(item.path) for item in owned_files.values() if item.owned
        ]
    return {
        "completed": not blockers,
        "actions": actions,
        "blockers": list(dict.fromkeys(blockers)),
        "details": details,
    }


def _validate_worker_cleanup(
    value: Mapping[str, Any], control: WorkerControl
) -> Mapping[str, Any]:
    value = verify_bound_record(control, RECORD_CLEANUP, value)
    if set(value) != {"schema", "binding", "binding_digest", "cleanup"}:
        raise ValueError("worker cleanup wrapper is malformed")
    if value.get("schema") != WORKER_CLEANUP_SCHEMA:
        raise ValueError("worker cleanup schema is unsupported")
    if value.get("binding") != control.binding.to_mapping():
        raise ValueError("worker cleanup binding does not match this run")
    if value.get("binding_digest") != binding_digest(control.binding):
        raise ValueError("worker cleanup binding digest does not match this run")
    cleanup = value.get("cleanup")
    if not isinstance(cleanup, Mapping):
        raise ValueError("worker cleanup payload is malformed")
    if not isinstance(cleanup.get("completed"), bool):
        raise ValueError("worker cleanup completion is malformed")
    actions = cleanup.get("actions")
    errors = cleanup.get("errors")
    if not isinstance(actions, list) or any(
        not isinstance(item, str) for item in actions
    ):
        raise ValueError("worker cleanup actions are malformed")
    if not isinstance(errors, list) or any(
        not isinstance(item, Mapping) for item in errors
    ):
        raise ValueError("worker cleanup errors are malformed")
    if cleanup.get("temp_config_path") != str(control.binding.config_path):
        raise ValueError("worker cleanup config path changed")
    if not isinstance(cleanup.get("temp_config_present_after"), bool):
        raise ValueError("worker cleanup config state is malformed")
    if set(cleanup) != {
        "completed",
        "actions",
        "errors",
        "temp_config_path",
        "temp_config_present_after",
        "config_state",
    }:
        raise ValueError("worker cleanup fields are malformed")
    state_mapping = cleanup.get("config_state")
    if state_mapping is None:
        if cleanup.get("completed") is True or not any(
            item.get("item") == "temp_config_state_capture"
            for item in errors
            if isinstance(item, Mapping)
        ):
            raise ValueError("worker cleanup config state is missing without proof")
        return cleanup
    state = ConfigFileState.from_mapping(state_mapping)
    if state.exists != cleanup.get("temp_config_present_after"):
        raise ValueError("worker cleanup config existence is inconsistent")
    return cleanup


def _validate_worker_result(
    value: Mapping[str, Any],
    control: WorkerControl,
    args: argparse.Namespace,
    worker_cleanup: Mapping[str, Any],
    *,
    expected_materialization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("worker result wrapper is malformed")
    value = verify_bound_record(control, RECORD_RESULT, value)
    if value.get("schema") != WORKER_RESULT_SCHEMA:
        raise ValueError("worker result wrapper schema is unsupported")
    if value.get("binding") != control.binding.to_mapping():
        raise ValueError("worker result binding does not match this run")
    if value.get("binding_digest") != binding_digest(control.binding):
        raise ValueError("worker result binding digest does not match this run")
    terminal_kind = value.get("terminal_kind")
    if terminal_kind in ("fatal", "stop_requested"):
        if set(value) != {
            "schema",
            "binding",
            "binding_digest",
            "terminal_kind",
            "terminal",
        }:
            raise ValueError("worker fatal result wrapper is malformed")
        terminal = WorkerTerminal.from_bound_mapping(
            value.get("terminal"), control
        )
        if terminal.terminal_kind != terminal_kind:
            raise ValueError("worker terminal kind changed")
        cleanup_digest = hashlib.sha256(
            canonical_json_bytes(worker_cleanup)
        ).hexdigest()
        expected_cleanup_status = (
            "complete" if worker_cleanup.get("completed") is True else "failed"
        )
        if (
            terminal.cleanup_status != expected_cleanup_status
            or terminal.cleanup_digest != cleanup_digest
        ):
            raise ValueError("worker terminal cleanup reference changed")
        executed: bool | None
        if terminal.execution_state == "not_started":
            executed = False
        else:
            executed = None
        public_terminal = dict(terminal.to_mapping())
        public_terminal["message"] = terminal.classification
        return {
            "schema": SCHEMA,
            "passed": False,
            "executed": executed,
            "execution_state": terminal.execution_state,
            "capability_promotion": False,
            "task": args.task,
            "stage": args.stage,
            "event": args.event,
            "run_result": False,
            "run_error": {
                "type": terminal.exception_type,
                "message": terminal.classification,
                "classification": terminal.classification,
                "phase": terminal.phase,
                "exit_code": terminal.exit_code,
                "traceback_digest": terminal.traceback_digest,
            },
            "validation_errors": [terminal.classification],
            "raw_input_fallback_used": False,
            "worker_cleanup": dict(worker_cleanup),
            "worker_terminal": public_terminal,
        }
    if terminal_kind != "completed" or set(value) != {
        "schema",
        "binding",
        "binding_digest",
        "terminal_kind",
        "result",
    }:
        raise ValueError("worker completed result wrapper is malformed")
    result = value.get("result")
    if not isinstance(result, Mapping):
        raise ValueError("worker result payload is malformed")
    expected = {
        "schema": SCHEMA,
        "task": control.binding.task,
        "stage": control.binding.stage,
        "event": control.binding.event,
        "serial": control.serial,
        "driver_revision": args.driver_revision,
        "use_auto_search": True,
    }
    for field, expected_value in expected.items():
        if result.get(field) != expected_value:
            raise ValueError("worker result {0} changed".format(field))
    if expected_materialization is not None:
        _validate_loaded_materialized_alas(
            result.get("materialized_alas"),
            expected_proof=expected_materialization,
        )
    for field in (
        "passed",
        "executed",
        "capability_promotion",
        "run_result",
        "raw_input_fallback_used",
    ):
        if not isinstance(result.get(field), bool):
            raise ValueError("worker result {0} is not a strict boolean".format(field))
    if result["raw_input_fallback_used"]:
        raise ValueError("worker result used a raw input fallback")
    if result["capability_promotion"] != result["passed"]:
        raise ValueError("worker result capability promotion is inconsistent")
    if not isinstance(result.get("started_at"), str) or not result["started_at"]:
        raise ValueError("worker result start time is missing")
    if not isinstance(result.get("finished_at"), str) or not result["finished_at"]:
        raise ValueError("worker result finish time is missing")
    if result.get("run_error") is not None and not isinstance(
        result.get("run_error"), Mapping
    ):
        raise ValueError("worker result error is malformed")
    validation_errors = result.get("validation_errors")
    if not isinstance(validation_errors, list) or any(
        not isinstance(item, str) for item in validation_errors
    ):
        raise ValueError("worker validation errors are malformed")
    for field in (
        "budgets",
        "event_sp_auto_search_evidence",
        "final_surface",
        "worker_cleanup",
    ):
        if not isinstance(result.get(field), Mapping):
            raise ValueError("worker result {0} is malformed".format(field))
    if result["worker_cleanup"] != worker_cleanup:
        raise ValueError("worker result cleanup status changed")
    validated = dict(result)
    validated["execution_state"] = (
        "finished" if validated["executed"] else "not_started"
    )
    return validated


def _close_parent_resources(
    owned_files: Mapping[str, ExclusiveFile],
    activation_pipe: Any,
    seed_file: ImmutableInputFile | None = None,
) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []

    def attempt(label: str, operation: Any) -> None:
        try:
            operation()
        except BaseException as exc:
            errors.append(
                {"item": label, **_public_error(exc, purpose="parent_resource_close")}
            )

    if activation_pipe is not None:
        attempt("activation_read_close", activation_pipe.close_parent_read)
        attempt("activation_write_close", activation_pipe.close_parent_write)
    for label, owned in owned_files.items():
        if owned.child_handle >= 0:
            attempt(label + "_child_handle_close", owned.close_child_handle)
        if owned.fd >= 0:
            attempt(label + "_handle_close", owned.close_parent)
    if seed_file is not None:
        if seed_file.child_handle >= 0:
            attempt("seed_child_handle_close", seed_file.close_child_handle)
        if seed_file.fd >= 0:
            attempt("seed_handle_close", seed_file.close_parent)
    return errors


def _finalize_parent_resources(
    *,
    process: Any,
    job: Any,
    owned_files: Mapping[str, ExclusiveFile],
    activation_pipe: Any,
    seed_file: ImmutableInputFile | None = None,
) -> list[dict[str, str]]:
    """Close every acquired host handle independently and record every error."""

    errors: list[dict[str, str]] = []

    def attempt(label: str, operation: Any) -> None:
        try:
            operation()
        except BaseException as exc:
            errors.append(
                {"item": label, **_public_error(exc, purpose="parent_finalization")}
            )

    if job is not None:
        # Keep the attribute lookup inside the isolated operation as well.  A
        # native-wrapper teardown bug must not skip the process/pipe/file
        # finalizers that follow it.
        attempt("job_close", lambda: job.close())

    def close_worker_process_handle() -> None:
        process_handle = getattr(process, "_handle", None)
        close_process_handle = getattr(process_handle, "Close", None)
        if callable(close_process_handle) and not bool(
            getattr(process_handle, "closed", False)
        ):
            close_process_handle()

    if process is not None:
        attempt("worker_process_handle_close", close_worker_process_handle)
    try:
        errors.extend(
            _close_parent_resources(owned_files, activation_pipe, seed_file=seed_file)
        )
    except BaseException as exc:
        # _close_parent_resources isolates each normal resource.  This final
        # guard also contains hostile Mapping/pipe wrappers used by callers.
        errors.append(
            {
                "item": "parent_resource_close",
                **_public_error(exc, purpose="parent_resource_close"),
            }
        )
    return errors


def _add_cleanup_blocker(
    report: dict[str, Any], blocker: str, *, detail: Any = None
) -> None:
    report["completed"] = False
    report["blockers"] = list(dict.fromkeys([*report.get("blockers", ()), blocker]))
    if detail is not None:
        report.setdefault("details", {})[blocker] = detail


def _record_finalization_errors(
    result: dict[str, Any] | None, errors: list[dict[str, str]]
) -> None:
    if result is None or not errors:
        return
    result["passed"] = False
    result["capability_promotion"] = False
    existing_validation_errors = result.get("validation_errors")
    if not isinstance(existing_validation_errors, list):
        existing_validation_errors = []
    result["validation_errors"] = list(
        dict.fromkeys(
            [*existing_validation_errors, "runner.cleanup.resource_close_failed"]
        )
    )
    supervision = result.get("supervision")
    if not isinstance(supervision, dict):
        supervision = {}
        result["supervision"] = supervision
    lifecycle_errors = supervision.get("lifecycle_errors")
    if not isinstance(lifecycle_errors, list):
        lifecycle_errors = []
    supervision["lifecycle_errors"] = [*lifecycle_errors, *errors]
    parent_cleanup = supervision.get("parent_cleanup")
    if isinstance(parent_cleanup, dict):
        _add_cleanup_blocker(
            parent_cleanup,
            "runner.cleanup.resource_close_failed",
            detail=errors,
        )


def _process_result_with_error(
    process_result: ProcessSupervisionResult,
    message: str,
    *,
    termination_confirmed: bool | None = None,
) -> ProcessSupervisionResult:
    return ProcessSupervisionResult(
        reason=process_result.reason,
        termination_mode=process_result.termination_mode,
        returncode=process_result.returncode,
        termination_confirmed=(
            process_result.termination_confirmed
            if termination_confirmed is None
            else termination_confirmed
        ),
        cooperative_stop_requested=process_result.cooperative_stop_requested,
        forced_terminate=process_result.forced_terminate,
        forced_kill=process_result.forced_kill,
        errors=(*process_result.errors, message),
    )


def _supervision_failure_result(
    args: argparse.Namespace,
    control: WorkerControl,
    process_result: Any,
    parent_cleanup: Mapping[str, Any],
    worker_cleanup: Mapping[str, Any] | None,
    *,
    activation_may_have_been_delivered: bool,
    started_at: str | None = None,
) -> dict[str, Any]:
    if process_result.reason == "deadline":
        classification = "event_sp.runner_deadline_exceeded"
        error_type = "RunnerDeadlineExceeded"
    elif process_result.reason == "interrupted":
        classification = "runner.interrupted"
        error_type = "RunnerInterrupted"
    elif not process_result.termination_confirmed:
        classification = "runner.worker_termination_unconfirmed"
        error_type = "WorkerTerminationUnconfirmed"
    else:
        classification = "runner.worker_supervision_failed"
        error_type = "WorkerSupervisionError"
    blockers = list(parent_cleanup.get("blockers", ()))
    execution = _execution_claim(
        activation_may_have_been_delivered=activation_may_have_been_delivered
    )
    return {
        "schema": SCHEMA,
        "passed": False,
        **execution,
        "capability_promotion": False,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "task": args.task,
        "stage": args.stage,
        "event": args.event,
        "mode": _stage_difficulty(args.stage),
        "serial": args.serial,
        "driver_revision": args.driver_revision,
        "use_auto_search": args.use_auto_search,
        "run_result": False,
        "run_error": {
            "type": error_type,
            "message": classification,
            "classification": classification,
        },
        "validation_errors": list(dict.fromkeys([classification, *blockers])),
        "supervision": {
            "binding": control.binding.to_mapping(),
            "run_id": control.binding.run_id,
            "total_deadline_seconds": control.binding.deadline_seconds,
            "deadline_triggered": process_result.reason == "deadline",
            "interrupted": process_result.reason == "interrupted",
            "termination_mode": process_result.termination_mode,
            "worker_returncode": process_result.returncode,
            "cooperative_stop_requested": (process_result.cooperative_stop_requested),
            "forced_worker_terminate": process_result.forced_terminate,
            "forced_worker_kill": process_result.forced_kill,
            "termination_confirmed": process_result.termination_confirmed,
            "lifecycle_errors": list(process_result.errors),
            "worker_cleanup": worker_cleanup,
            "parent_cleanup": parent_cleanup,
        },
        "raw_input_fallback_used": False,
    }


def _setup_failure_result(
    args: argparse.Namespace,
    *,
    run_id: str,
    deadline_seconds: int,
    started_at: str,
    classification: str,
    error: BaseException,
    parent_cleanup: Mapping[str, Any],
    activation_may_have_been_delivered: bool = False,
    process_result: ProcessSupervisionResult | None = None,
) -> dict[str, Any]:
    if (
        process_result is not None
        and not process_result.termination_confirmed
        and classification == "runner.setup_failed"
    ):
        classification = "runner.worker_termination_unconfirmed"
    blockers = list(parent_cleanup.get("blockers", ()))
    execution = _execution_claim(
        activation_may_have_been_delivered=activation_may_have_been_delivered
    )
    return {
        "schema": SCHEMA,
        "passed": False,
        **execution,
        "capability_promotion": False,
        "started_at": started_at,
        "finished_at": _utc_now(),
        "task": args.task,
        "stage": args.stage,
        "event": args.event,
        "mode": _stage_difficulty(args.stage),
        "serial": args.serial,
        "driver_revision": args.driver_revision,
        "use_auto_search": args.use_auto_search,
        "run_result": False,
        "run_error": _public_error(
            error, purpose="runner_setup", classification=classification
        ),
        "validation_errors": list(dict.fromkeys([classification, *blockers])),
        "supervision": {
            "binding": None,
            "run_id": run_id,
            "total_deadline_seconds": deadline_seconds,
            "deadline_triggered": classification == "event_sp.runner_deadline_exceeded",
            "interrupted": classification == "runner.interrupted",
            "termination_mode": (
                process_result.termination_mode
                if process_result is not None
                else "worker_not_started"
            ),
            "worker_returncode": (
                process_result.returncode if process_result is not None else None
            ),
            "cooperative_stop_requested": bool(
                process_result and process_result.cooperative_stop_requested
            ),
            "forced_worker_terminate": bool(
                process_result and process_result.forced_terminate
            ),
            "forced_worker_kill": bool(process_result and process_result.forced_kill),
            "termination_confirmed": (
                process_result.termination_confirmed
                if process_result is not None
                else True
            ),
            "lifecycle_errors": (
                list(process_result.errors) if process_result is not None else []
            ),
            "worker_cleanup": None,
            "parent_cleanup": parent_cleanup,
        },
        "raw_input_fallback_used": False,
    }


def _unconfirmed_process_result(reason: str, *errors: str) -> ProcessSupervisionResult:
    return ProcessSupervisionResult(
        reason=reason,
        termination_mode=reason + "_unconfirmed",
        returncode=None,
        termination_confirmed=False,
        cooperative_stop_requested=False,
        forced_terminate=False,
        forced_kill=False,
        errors=tuple(errors),
    )


def _shutdown_for_runner_failure(
    process: Any,
    job: Any,
    shutdown: Any,
    *,
    reason: str,
    original: BaseException,
) -> ProcessSupervisionResult:
    original_error = secret_free_exception_label(original, "runner")
    try:
        result = shutdown(process, job, reason=reason)
        if not isinstance(result, ProcessSupervisionResult):
            raise TypeError("shutdown returned an invalid result")
        return _process_result_with_error(result, original_error)
    except BaseException as exc:
        return _unconfirmed_process_result(
            reason,
            original_error,
            secret_free_exception_label(exc, "shutdown"),
        )


def _retained_parent_cleanup(
    owned_files: Mapping[str, ExclusiveFile],
    control: WorkerControl | None,
    *,
    blocker: str,
    error: BaseException | str,
) -> dict[str, Any]:
    public_error = _public_error(
        RuntimeError(error) if isinstance(error, str) else error,
        purpose="retained_parent_cleanup",
    )
    return {
        "completed": False,
        "actions": [],
        "blockers": [blocker],
        "details": {
            "config_path": (
                str(control.binding.config_path) if control is not None else None
            ),
            "artifacts_retained": [
                str(item.path) for item in owned_files.values() if item.owned
            ],
            "error": public_error,
        },
    }


class _EventSpParentOwnership:
    """Resource bookkeeping only; it contains no task or navigation state."""

    def __init__(self) -> None:
        self.owned_files: dict[str, ExclusiveFile] = {}
        self.control_root: Path | None = None
        self.activation_pipe: Any = None
        self.job: Any = None
        self.process: Any = None
        self.control: WorkerControl | None = None
        self.process_result: ProcessSupervisionResult | None = None
        self.parent_cleanup: dict[str, Any] | None = None
        self.activation_may_have_been_delivered = False
        self.run_id: str | None = None
        self.deadline_seconds: int | None = None
        self.started_at: str | None = None
        self.activation_token: bytes | None = None
        self.materialization_proof: dict[str, str] | None = None
        self.materialization_control: dict[str, Any] | None = None
        self.seed_file: ImmutableInputFile | None = None
        self.seed_source: SeedSource | None = None


def _supervise_event_sp_impl(
    args: argparse.Namespace,
    *,
    worker_argv: list[str] | None = None,
    popen_factory: Any = subprocess.Popen,
    forward_inventory: Any = adb_forward_inventory,
    verified_pid: Any = adb_verified_game_pid,
    remove_forward: Any = adb_remove_forward,
    supervise: Any = supervise_process,
    shutdown: Any = shutdown_worker,
    monotonic: Any = time.monotonic,
    temporary_directory: Any = tempfile.mkdtemp,
    job_factory: Any = WindowsWorkerJob,
    activation_factory: Any = create_activation_pipe,
    exclusive_file_factory: Any = exclusive_create,
    activation_sender: Any = send_activation,
    identity_getter: Any = process_identity,
    seed_input_factory: Any = open_immutable_input,
    _ownership: _EventSpParentOwnership,
) -> Mapping[str, Any]:
    deadline_seconds = _total_deadline(args)
    assert deadline_seconds is not None
    _event_sp_seed_name(args)
    execution_budgets = _execution_budgets(args)
    # This clock read is deliberately the first operation after strict argument
    # validation.  Path resolution, Job/pipe creation, ADB preflight, exclusive
    # file creation, launch, activation, and worker serialization all consume
    # the same total budget.
    absolute_deadline = monotonic() + deadline_seconds
    started_at = _utc_now()
    run_id = uuid.uuid4().hex
    _ownership.run_id = run_id
    _ownership.deadline_seconds = deadline_seconds
    _ownership.started_at = started_at
    owned_files = _ownership.owned_files
    control_root: Path | None = None
    activation_pipe = None
    job = None
    process = None
    control: WorkerControl | None = None
    activation_may_have_been_delivered = False
    process_result: ProcessSupervisionResult | None = None
    setup_error: BaseException | None = None
    setup_classification = "runner.setup_failed"
    try:
        remaining_seconds(absolute_deadline, monotonic)
        provided_root = args.alas_root
        if not isinstance(provided_root, Path) or not provided_root.is_absolute():
            raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_UNPROVEN)
        alas_root = provided_root.resolve(strict=True)
        if alas_root != provided_root:
            raise EventSpTemplateAdmissionError(EVENT_SP_TEMPLATE_UNPROVEN)
        materialization_proof = _materialized_alas_proof(alas_root)
        seed_file, seed_source, _seed_value = _admit_event_sp_template(
            alas_root, input_factory=seed_input_factory
        )
        _ownership.seed_file = seed_file
        _ownership.seed_source = seed_source
        remaining_seconds(absolute_deadline, monotonic)
        _ownership.materialization_proof = materialization_proof
        job = job_factory()
        _ownership.job = job
        starting_forwards = forward_inventory(
            args.adb,
            args.serial,
            timeout_seconds=remaining_seconds(absolute_deadline, monotonic),
        )
        game_pid = verified_pid(
            args.adb,
            args.serial,
            GAME_PACKAGE,
            timeout_seconds=remaining_seconds(absolute_deadline, monotonic),
        )
        activation_pipe = activation_factory()
        _ownership.activation_pipe = activation_pipe
        control_root = Path(
            temporary_directory(prefix="alas-eventsp-runner-", dir=None)
        )
        control_root = control_root.resolve()
        _ownership.control_root = control_root
        remaining_seconds(absolute_deadline, monotonic)
        paths = {
            "config": alas_root
            / "config"
            / ("_codex_event_live_eventsp_" + run_id + ".json"),
            "control": control_root / "worker-control.json",
            "result": control_root / "worker-result.json",
            "cleanup": control_root / "worker-cleanup.json",
            "lease": control_root / "forward-lease.json",
        }
        for label, path in paths.items():
            owned_files[label] = exclusive_file_factory(
                path, inheritable=label in ("config", "result", "cleanup", "lease")
            )
        child_handles = {
            "control": owned_files["control"].create_child_handle("read"),
            "config": owned_files["config"].create_child_handle("write"),
            "result": owned_files["result"].create_child_handle("write"),
            "cleanup": owned_files["cleanup"].create_child_handle("write"),
            "lease": owned_files["lease"].create_child_handle("write"),
            "seed": seed_file.create_child_handle(),
        }
        parent_pid = os.getpid()
        parent_identity = identity_getter(parent_pid)
        token = os.urandom(32)
        _ownership.activation_token = token
        materialization_control = _materialization_control_record(
            materialization_proof,
            run_id=run_id,
            task=args.task,
            stage=args.stage,
            event=args.event,
            deadline_seconds=deadline_seconds,
            parent_pid=parent_pid,
            alas_root=alas_root,
        )
        ensure_secret_free_payload(materialization_control, token)
        _ownership.materialization_control = materialization_control
        environment = dict(os.environ)
        environment.update(
            {
                WORKER_ROLE_ENV: "worker",
                WORKER_CONTROL_ENV: str(paths["control"]),
                WORKER_ACTIVATION_HANDLE_ENV: str(activation_pipe.read_handle),
                WORKER_CONTROL_HANDLE_ENV: str(child_handles["control"]),
                WORKER_CONFIG_HANDLE_ENV: str(child_handles["config"]),
                WORKER_RESULT_HANDLE_ENV: str(child_handles["result"]),
                WORKER_CLEANUP_HANDLE_ENV: str(child_handles["cleanup"]),
                WORKER_LEASE_HANDLE_ENV: str(child_handles["lease"]),
                WORKER_SEED_HANDLE_ENV: str(child_handles["seed"]),
                MATERIALIZED_ALAS_CONTROL_ENV: json.dumps(
                    materialization_control,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                    allow_nan=False,
                ),
            }
        )
        command = worker_argv or [
            sys.executable,
            str(Path(__file__).resolve()),
            *sys.argv[1:],
        ]
        if os.name != "nt":
            raise RuntimeError("EventSp worker supervision requires Windows")
        inherited_handles = [
            activation_pipe.read_handle,
            *child_handles.values(),
        ]
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.lpAttributeList = {"handle_list": inherited_handles}
        remaining_seconds(absolute_deadline, monotonic)
        process = popen_factory(
            command,
            cwd=str(ROOT),
            env=environment,
            stdin=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            startupinfo=startupinfo,
            close_fds=True,
        )
        _ownership.process = process
        # No later process may inherit these capabilities from the parent.
        for owned in owned_files.values():
            owned.close_child_handle()
        seed_file.close_child_handle()
        activation_pipe.close_parent_read()
        binding = RunBinding(
            run_id=run_id,
            token_digest=hashlib.sha256(token).hexdigest(),
            task=args.task,
            stage=args.stage,
            event=args.event,
            deadline_seconds=deadline_seconds,
            parent_pid=parent_pid,
            parent_identity=parent_identity,
            worker_pid=process.pid,
            config_path=paths["config"],
            control_path=paths["control"],
            result_path=paths["result"],
            cleanup_path=paths["cleanup"],
            lease_path=paths["lease"],
        )
        config_root = paths["config"].parent.resolve(strict=True)
        if config_root != paths["config"].parent:
            raise RuntimeError("ALAS config root is not the exact canonical path")
        config_ownership = build_config_ownership(
            binding,
            config_root=config_root,
            root_identity=file_identity_from_path(config_root),
            initial_identity=file_identity_from_fd(owned_files["config"].fd),
            control_identity=file_identity_from_fd(owned_files["control"].fd),
        )
        control = WorkerControl(
            binding=binding,
            config_ownership=config_ownership,
            seed_source=seed_source,
            serial=args.serial,
            verified_game_pid=game_pid,
            starting_forwards=tuple(starting_forwards),
            handles=WorkerHandles(
                control=child_handles["control"],
                config=child_handles["config"],
                result=child_handles["result"],
                cleanup=child_handles["cleanup"],
                lease=child_handles["lease"],
                seed=child_handles["seed"],
            ),
            materialization_control=materialization_control,
            execution_budgets=execution_budgets,
        )
        control.bind_activation_token(token, verified=False)
        _ownership.control = control
        # Containment and its independent membership check must both succeed
        # before the one-shot activation record can become visible.
        job.assign(process)
        ensure_secret_free_payload(control.to_mapping(), token)
        write_owned_file(
            owned_files["control"], canonical_json_bytes(control.to_mapping())
        )
        validate_control_lease(owned_files["control"], control)
        # The control HANDLE remains the immutable ownership lease.  The data
        # HANDLE must be gone before activation so ALAS can replace the exact
        # config path atomically on Windows.
        owned_files["config"].close_parent()
        if owned_files["config"].fd >= 0:
            raise RuntimeError("parent config data handle remained open")
        # A root directory pathname can drift independently of the immutable
        # template/config file handles.  Re-prove the same canonical directory
        # identity at the final pre-activation boundary.
        validate_worker_control_root(control)
        remaining_seconds(absolute_deadline, monotonic)
        activation_may_have_been_delivered = True
        _ownership.activation_may_have_been_delivered = True
        activation_sender(
            activation_pipe,
            control,
            paths["control"],
            absolute_deadline=absolute_deadline,
            monotonic=monotonic,
        )
        candidate_process_result = supervise(
            process,
            job,
            absolute_deadline=absolute_deadline,
            monotonic=monotonic,
        )
        if not isinstance(candidate_process_result, ProcessSupervisionResult):
            raise TypeError("supervisor returned an invalid process result")
        process_result = candidate_process_result
    except KeyboardInterrupt as exc:
        setup_error = exc
        setup_classification = "runner.interrupted"
        if process is not None:
            process_result = _shutdown_for_runner_failure(
                process,
                job,
                shutdown,
                reason="interrupted",
                original=exc,
            )
    except TimeoutError as exc:
        setup_error = exc
        setup_classification = "event_sp.runner_deadline_exceeded"
        if process is not None:
            process_result = _shutdown_for_runner_failure(
                process,
                job,
                shutdown,
                reason="deadline",
                original=exc,
            )
    except MaterializedAlasAdmissionError as exc:
        setup_error = exc
        setup_classification = exc.classification
        if process is not None:
            process_result = _shutdown_for_runner_failure(
                process,
                job,
                shutdown,
                reason="materialization_error",
                original=exc,
            )
    except EventSpTemplateAdmissionError as exc:
        setup_error = exc
        setup_classification = exc.classification
        if process is not None:
            process_result = _shutdown_for_runner_failure(
                process,
                job,
                shutdown,
                reason="template_seed_error",
                original=exc,
            )
    except BaseException as exc:
        setup_error = exc
        if process is not None:
            process_result = _shutdown_for_runner_failure(
                process,
                job,
                shutdown,
                reason="supervision_error",
                original=exc,
            )

    _ownership.process_result = process_result

    # A mocked or future supervisor may report a dead root while descendants
    # remain.  Re-check the Job before reading or deleting any run-owned file.
    if process_result is not None and process_result.termination_confirmed:
        try:
            root_returncode = process.poll()
            if root_returncode is None:
                process_result = _process_result_with_error(
                    process_result,
                    "worker_root_process_remained_alive",
                    termination_confirmed=False,
                )
            elif job.active_process_count() != 0:
                process_result = _process_result_with_error(
                    process_result,
                    "job_active_processes_remained",
                    termination_confirmed=False,
                )
        except BaseException as exc:
            process_result = _process_result_with_error(
                process_result,
                secret_free_exception_label(exc, "job_query"),
                termination_confirmed=False,
            )
    _ownership.process_result = process_result

    if process is None or control is None:
        cleanup_confirmed = process is None or (
            process_result is not None and process_result.termination_confirmed
        )
        parent_cleanup = _owned_artifact_cleanup(
            owned_files, control_root, termination_confirmed=cleanup_confirmed
        )
        result = _setup_failure_result(
            args,
            run_id=run_id,
            deadline_seconds=deadline_seconds,
            started_at=started_at,
            classification=setup_classification,
            error=setup_error or RuntimeError("worker setup did not start"),
            parent_cleanup=parent_cleanup,
            activation_may_have_been_delivered=activation_may_have_been_delivered,
            process_result=process_result,
        )
        _ownership.parent_cleanup = parent_cleanup
        return result

    assert process_result is not None
    assert control is not None
    termination_confirmed = process_result.termination_confirmed
    worker_cleanup_wrapper = None
    worker_cleanup = None
    worker_cleanup_error = None
    if termination_confirmed:
        worker_cleanup_wrapper, worker_cleanup_error = _optional_owned_json(
            owned_files.get("cleanup")
        )
        if worker_cleanup_error is None and worker_cleanup_wrapper is None:
            worker_cleanup_error = "runner.worker_cleanup_missing"
        elif worker_cleanup_error is None and worker_cleanup_wrapper is not None:
            try:
                worker_cleanup = _validate_worker_cleanup(
                    worker_cleanup_wrapper, control
                )
            except Exception as exc:
                worker_cleanup_error = secret_free_exception_label(
                    exc, "worker_cleanup_validation"
                )
    worker_result = None
    worker_result_error = None
    if termination_confirmed and process_result.reason == "completed":
        worker_result, worker_result_error = _optional_owned_json(
            owned_files.get("result")
        )
    try:
        parent_cleanup = _parent_fallback_cleanup(
            control,
            owned_files=owned_files,
            control_root=control_root,
            termination_confirmed=termination_confirmed,
            worker_activated=activation_may_have_been_delivered,
            worker_cleanup=worker_cleanup,
            cleanup_deadline=monotonic() + WORKER_CLEANUP_GRACE_SECONDS,
            monotonic=monotonic,
            adb=args.adb,
            forward_inventory=forward_inventory,
            remove_forward=remove_forward,
        )
    except KeyboardInterrupt:
        raise
    except BaseException as exc:
        parent_cleanup = _retained_parent_cleanup(
            owned_files,
            control,
            blocker="runner.cleanup.parent_cleanup_failed",
            error=exc,
        )
    _ownership.parent_cleanup = parent_cleanup
    if worker_cleanup_error is not None:
        parent_cleanup["completed"] = False
        parent_cleanup["blockers"] = list(
            dict.fromkeys(
                [
                    *parent_cleanup.get("blockers", ()),
                    "runner.cleanup.worker_status_malformed",
                ]
            )
        )
        parent_cleanup["details"]["worker_cleanup_error"] = worker_cleanup_error

    if process_result.reason != "completed" or not process_result.termination_confirmed:
        return _supervision_failure_result(
            args,
            control,
            process_result,
            parent_cleanup,
            worker_cleanup,
            activation_may_have_been_delivered=activation_may_have_been_delivered,
            started_at=started_at,
        )

    if (
        worker_result_error is not None
        or worker_result is None
        or worker_cleanup is None
    ):
        classification = "runner.worker_result_missing_or_malformed"
        execution = _execution_claim(
            activation_may_have_been_delivered=activation_may_have_been_delivered
        )
        result: dict[str, Any] = {
            "schema": SCHEMA,
            "passed": False,
            **execution,
            "capability_promotion": False,
            "task": args.task,
            "stage": args.stage,
            "event": args.event,
            "run_result": False,
            "run_error": {
                "type": "WorkerResultError",
                "message": classification,
                "classification": classification,
            },
            "validation_errors": [classification],
            "raw_input_fallback_used": False,
        }
        trusted_terminal_kind = None
    else:
        try:
            result = _validate_worker_result(
                worker_result,
                control,
                args,
                worker_cleanup,
                expected_materialization=materialization_proof,
            )
            trusted_terminal_kind = verify_bound_record(
                control, RECORD_RESULT, worker_result
            ).get("terminal_kind")
        except Exception as exc:
            classification = "runner.worker_result_identity_or_shape_mismatch"
            execution = _execution_claim(
                activation_may_have_been_delivered=(activation_may_have_been_delivered)
            )
            result = {
                "schema": SCHEMA,
                "passed": False,
                **execution,
                "capability_promotion": False,
                "task": args.task,
                "stage": args.stage,
                "event": args.event,
                "run_result": False,
                "run_error": _public_error(
                    exc,
                    purpose="worker_result_validation",
                    classification=classification,
                ),
                "validation_errors": [classification],
                "raw_input_fallback_used": False,
            }
            trusted_terminal_kind = None
        if trusted_terminal_kind == "stop_requested":
            expected_returncode = 124
        elif trusted_terminal_kind == "fatal":
            expected_returncode = 1
        elif trusted_terminal_kind == "completed":
            expected_returncode = 0 if result.get("passed") is True else 1
        else:
            expected_returncode = None
        if (
            expected_returncode is not None
            and process_result.returncode != expected_returncode
        ):
            result["passed"] = False
            result["capability_promotion"] = False
            result.setdefault("validation_errors", []).append(
                "runner.worker_returncode_mismatch"
            )

    cleanup_blockers = list(parent_cleanup.get("blockers", ()))
    if cleanup_blockers:
        result["passed"] = False
        result["capability_promotion"] = False
        result["validation_errors"] = list(
            dict.fromkeys([*result.get("validation_errors", ()), *cleanup_blockers])
        )
    result["supervision"] = {
        "binding": control.binding.to_mapping(),
        "run_id": control.binding.run_id,
        "total_deadline_seconds": control.binding.deadline_seconds,
        "deadline_triggered": False,
        "interrupted": False,
        "termination_mode": process_result.termination_mode,
        "worker_returncode": process_result.returncode,
        "cooperative_stop_requested": False,
        "forced_worker_terminate": False,
        "forced_worker_kill": False,
        "termination_confirmed": process_result.termination_confirmed,
        "lifecycle_errors": list(process_result.errors),
        "worker_cleanup": worker_cleanup,
        "parent_cleanup": parent_cleanup,
    }
    return result


def _supervise_event_sp(
    args: argparse.Namespace,
    *,
    worker_argv: list[str] | None = None,
    popen_factory: Any = subprocess.Popen,
    forward_inventory: Any = adb_forward_inventory,
    verified_pid: Any = adb_verified_game_pid,
    remove_forward: Any = adb_remove_forward,
    supervise: Any = supervise_process,
    shutdown: Any = shutdown_worker,
    monotonic: Any = time.monotonic,
    temporary_directory: Any = tempfile.mkdtemp,
    job_factory: Any = WindowsWorkerJob,
    activation_factory: Any = create_activation_pipe,
    exclusive_file_factory: Any = exclusive_create,
    activation_sender: Any = send_activation,
    identity_getter: Any = process_identity,
    seed_input_factory: Any = open_immutable_input,
) -> Mapping[str, Any]:
    # Preserve strict pre-side-effect rejection.  The implementation validates
    # again immediately before starting its absolute deadline.
    deadline_seconds = _total_deadline(args)
    assert deadline_seconds is not None
    _event_sp_seed_name(args)
    _execution_budgets(args)
    ownership = _EventSpParentOwnership()
    final_result: dict[str, Any] | None = None
    try:
        final_result = dict(
            _supervise_event_sp_impl(
                args,
                worker_argv=worker_argv,
                popen_factory=popen_factory,
                forward_inventory=forward_inventory,
                verified_pid=verified_pid,
                remove_forward=remove_forward,
                supervise=supervise,
                shutdown=shutdown,
                monotonic=monotonic,
                temporary_directory=temporary_directory,
                job_factory=job_factory,
                activation_factory=activation_factory,
                exclusive_file_factory=exclusive_file_factory,
                activation_sender=activation_sender,
                identity_getter=identity_getter,
                seed_input_factory=seed_input_factory,
                _ownership=ownership,
            )
        )
    except BaseException as exc:
        interrupted = isinstance(exc, KeyboardInterrupt)
        reason = "interrupted" if interrupted else "supervision_error"
        process_result = ownership.process_result
        if ownership.process is not None and (
            process_result is None or not process_result.termination_confirmed
        ):
            process_result = _shutdown_for_runner_failure(
                ownership.process,
                ownership.job,
                shutdown,
                reason=reason,
                original=exc,
            )
        elif process_result is not None:
            process_result = ProcessSupervisionResult(
                reason=reason,
                termination_mode=reason + "_post_supervision",
                returncode=process_result.returncode,
                termination_confirmed=process_result.termination_confirmed,
                cooperative_stop_requested=process_result.cooperative_stop_requested,
                forced_terminate=process_result.forced_terminate,
                forced_kill=process_result.forced_kill,
                errors=(
                    *process_result.errors,
                    secret_free_exception_label(exc, "post_supervision"),
                ),
            )
        ownership.process_result = process_result

        parent_cleanup = ownership.parent_cleanup
        if parent_cleanup is None:
            if ownership.process is None:
                try:
                    parent_cleanup = _owned_artifact_cleanup(
                        ownership.owned_files,
                        ownership.control_root,
                        termination_confirmed=True,
                    )
                except BaseException as cleanup_exc:
                    parent_cleanup = _retained_parent_cleanup(
                        ownership.owned_files,
                        ownership.control,
                        blocker="runner.cleanup.parent_cleanup_failed",
                        error=cleanup_exc,
                    )
            else:
                parent_cleanup = _retained_parent_cleanup(
                    ownership.owned_files,
                    ownership.control,
                    blocker=(
                        "runner.cleanup.post_supervision_interrupted"
                        if interrupted
                        else "runner.cleanup.post_supervision_failed"
                    ),
                    error=exc,
                )
        ownership.parent_cleanup = parent_cleanup

        started_at = ownership.started_at or _utc_now()
        run_id = ownership.run_id or uuid.uuid4().hex
        if ownership.control is not None and process_result is not None:
            final_result = _supervision_failure_result(
                args,
                ownership.control,
                process_result,
                parent_cleanup,
                None,
                activation_may_have_been_delivered=(
                    ownership.activation_may_have_been_delivered
                ),
                started_at=started_at,
            )
        else:
            final_result = _setup_failure_result(
                args,
                run_id=run_id,
                deadline_seconds=ownership.deadline_seconds or deadline_seconds,
                started_at=started_at,
                classification=(
                    "runner.interrupted" if interrupted else "runner.setup_failed"
                ),
                error=exc,
                parent_cleanup=parent_cleanup,
                activation_may_have_been_delivered=(
                    ownership.activation_may_have_been_delivered
                ),
                process_result=process_result,
            )
    finally:
        finalization_errors = _finalize_parent_resources(
            process=ownership.process,
            job=ownership.job,
            owned_files=ownership.owned_files,
            activation_pipe=ownership.activation_pipe,
            seed_file=ownership.seed_file,
        )
        _record_finalization_errors(final_result, finalization_errors)
    assert final_result is not None
    if ownership.materialization_proof is not None:
        existing_loaded = final_result.get("materialized_alas")
        if existing_loaded is not None:
            try:
                _validate_loaded_materialized_alas(
                    existing_loaded,
                    expected_proof=ownership.materialization_proof,
                )
            except MaterializedAlasAdmissionError:
                final_result.pop("materialized_alas", None)
                final_result["passed"] = False
                final_result["capability_promotion"] = False
                final_result["validation_errors"] = list(
                    dict.fromkeys(
                        [
                            *final_result.get("validation_errors", ()),
                            "runner.worker_result_identity_or_shape_mismatch",
                        ]
                    )
                )
        final_result["materialized_alas_admission"] = dict(
            ownership.materialization_proof
        )
    if ownership.materialization_control is not None:
        supervision = final_result.setdefault("supervision", {})
        if isinstance(supervision, dict):
            supervision["materialization_control"] = dict(
                ownership.materialization_control
            )
    if ownership.seed_source is not None:
        supervision = final_result.setdefault("supervision", {})
        if isinstance(supervision, dict):
            supervision["seed_source"] = dict(ownership.seed_source.to_mapping())
            supervision["seed_support_classification"] = (
                _event_sp_template_support_classification(
                    ownership.seed_source.sha256
                )
            )
    if ownership.activation_token is not None:
        final_result = redact_secret_representations(
            final_result, ownership.activation_token
        )
    return final_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--alas-root", required=True, type=Path)
    parser.add_argument(
        "--serial",
        help="exact online ADB serial; auto-discovered only when exactly one is online",
    )
    parser.add_argument("--driver-revision", required=True)
    parser.add_argument("--adb", default="adb")
    parser.add_argument("--seed-config", default=EVENT_SP_SEED_NAME)
    parser.add_argument("--task", required=True, choices=TASKS)
    parser.add_argument("--event", default="event_20260813_cn")
    parser.add_argument("--stage", required=True)
    parser.add_argument("--use-auto-search", action="store_true")
    parser.add_argument("--stage-entry-budget", type=int)
    parser.add_argument("--fleet-mutation-budget", type=int)
    parser.add_argument("--sortie-budget", type=int)
    parser.add_argument("--combat-budget", type=int)
    parser.add_argument("--viewport-swipe-budget", type=int)
    parser.add_argument("--camera-positioning-budget", type=int)
    parser.add_argument("--recovery-total", type=int)
    parser.add_argument("--total-deadline-seconds", type=int)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        _total_deadline(args)
        _event_sp_seed_name(args)
        _execution_budgets(args)
    except ValueError as exc:
        parser.error("runner arguments are invalid ({0})".format(type(exc).__name__))
    return args


def _traceback_digest(exc: BaseException) -> str | None:
    try:
        rendered = "".join(
            traceback.format_exception(type(exc), exc, exc.__traceback__)
        )
        return hashlib.sha256(rendered.encode("utf-8", errors="replace")).hexdigest()
    except BaseException:
        return None


def _terminal_wrapper(
    control: WorkerControl,
    status: _WorkerRunStatus,
    exc: BaseException,
    *,
    terminal_kind: str,
    classification: str,
) -> Mapping[str, Any]:
    cleanup = status.cleanup
    cleanup_status = "missing"
    cleanup_digest = None
    if isinstance(cleanup, Mapping):
        cleanup_status = "complete" if cleanup.get("completed") is True else "failed"
        cleanup_digest = hashlib.sha256(canonical_json_bytes(cleanup)).hexdigest()
    exception_type = safe_exception_type(exc)
    exit_code = (
        normalize_system_exit_code(exc.code) if isinstance(exc, SystemExit) else None
    )
    terminal = WorkerTerminal(
        terminal_kind=terminal_kind,
        phase=status.phase,
        execution_state=status.execution_state,
        classification=classification,
        passed=False,
        capability_promotion=False,
        exit_code=exit_code,
        exception_type=exception_type,
        message=classification,
        traceback_digest=_traceback_digest(exc),
        cleanup_status=cleanup_status,
        cleanup_digest=cleanup_digest,
    )
    return bind_record(
        control,
        RECORD_RESULT,
        {
            "schema": WORKER_RESULT_SCHEMA,
            "binding": control.binding.to_mapping(),
            "binding_digest": binding_digest(control.binding),
            "terminal_kind": terminal_kind,
            "terminal": terminal.to_bound_mapping(control),
        },
    )


def _write_terminal_best_effort(
    control: WorkerControl,
    status: _WorkerRunStatus,
    exc: BaseException,
    *,
    terminal_kind: str,
    classification: str,
) -> None:
    wrapper = _terminal_wrapper(
        control,
        status,
        exc,
        terminal_kind=terminal_kind,
        classification=classification,
    )
    write_bytes_handle(control.handles.result, _public_json_bytes(wrapper, control))


def _ensure_worker_terminal_cleanup(
    control: WorkerControl, status: _WorkerRunStatus
) -> None:
    """Close pre-init config authority and publish cleanup before a terminal."""

    if isinstance(status.cleanup, Mapping):
        return
    errors: list[dict[str, str]] = []
    terminal_errors: list[BaseException] = []
    if not status.seed_handle_consumed:
        try:
            close_inherited_handle(control.handles.seed)
            status.seed_handle_consumed = True
        except BaseException as exc:
            errors.append(
                {
                    "item": "inherited_seed_handle_close",
                    **_public_error(exc, purpose="inherited_seed_handle_close"),
                }
            )
            if not isinstance(exc, Exception):
                terminal_errors.append(exc)
    try:
        close_inherited_handle(control.handles.config)
    except BaseException as exc:
        errors.append(
            {
                "item": "inherited_config_handle_close",
                **_public_error(exc, purpose="inherited_config_handle_close"),
            }
        )
        if not isinstance(exc, Exception):
            terminal_errors.append(exc)
    cleanup = _failure_isolated_worker_cleanup(
        instance=None,
        prior_cwd=Path.cwd(),
        config_path=control.binding.config_path,
        prior_env={},
        remove_config=False,
        worker_control=control,
        terminal_errors=terminal_errors,
    )
    cleanup["errors"] = [*errors, *cleanup["errors"]]
    cleanup["completed"] = not cleanup["errors"]
    status.cleanup = cleanup
    try:
        cleanup_wrapper = bind_record(
            control,
            RECORD_CLEANUP,
            {
                "schema": WORKER_CLEANUP_SCHEMA,
                "binding": control.binding.to_mapping(),
                "binding_digest": binding_digest(control.binding),
                "cleanup": cleanup,
            },
        )
        _write_public_json_handle(
            control.handles.cleanup,
            cleanup_wrapper,
            control,
        )
    except BaseException as exc:
        cleanup["completed"] = False
        cleanup["errors"].append(
            {
                "item": "cleanup_status_write",
                **_public_error(exc, purpose="cleanup_status_write"),
            }
        )
        if not isinstance(exc, Exception):
            terminal_errors.append(exc)
    if terminal_errors:
        raise min(terminal_errors, key=_worker_terminal_priority)


def _finish_worker_terminal(
    control: WorkerControl, status: _WorkerRunStatus, active: BaseException
) -> int:
    """Publish one terminal using the strongest stop signal seen in cleanup."""

    try:
        _ensure_worker_terminal_cleanup(control, status)
    except BaseException as cleanup_exc:
        if _worker_terminal_priority(cleanup_exc) < _worker_terminal_priority(active):
            active = cleanup_exc
    if isinstance(active, RunnerStopRequested):
        terminal_kind = "stop_requested"
        classification = "runner.worker_stop_requested"
        returncode = 124
    elif isinstance(active, SystemExit):
        terminal_kind = "fatal"
        classification = "runner.worker_system_exit"
        returncode = 1
    elif isinstance(active, MaterializedAlasAdmissionError):
        terminal_kind = "fatal"
        classification = active.classification
        returncode = 1
    else:
        terminal_kind = "fatal"
        classification = (
            "runner.worker_keyboard_interrupt"
            if isinstance(active, KeyboardInterrupt)
            else "runner.worker_fatal"
        )
        returncode = 1
    try:
        _write_terminal_best_effort(
            control,
            status,
            active,
            terminal_kind=terminal_kind,
            classification=classification,
        )
    except BaseException:
        # Parent supervision still owns the process classification when the
        # bounded terminal handle cannot accept a complete run-bound frame.
        pass
    return returncode


def main() -> int:
    args = parse_args()
    # A public invocation has no internal role.  An alleged worker must consume
    # the inherited one-shot activation handle and validate its real parent
    # before run() can create config, import ALAS, or touch ADB/session state.
    control = worker_control_from_activation(os.environ)
    if control is not None:
        status = _WorkerRunStatus()

        def restore_signal() -> None:
            return None

        try:
            restore_signal = install_worker_stop_handler()
            result = dict(run(args, worker_control=control, _worker_status=status))
            result["executed"] = result.get("qualification_stop") is None
            result["capability_promotion"] = bool(result.get("passed"))
            status.phase = "result_serialize"
            wrapper = bind_record(
                control,
                RECORD_RESULT,
                {
                    "schema": WORKER_RESULT_SCHEMA,
                    "binding": control.binding.to_mapping(),
                    "binding_digest": binding_digest(control.binding),
                    "terminal_kind": "completed",
                    "result": result,
                },
            )
            write_bytes_handle(
                control.handles.result, _public_json_bytes(wrapper, control)
            )
            return 0 if result["passed"] else 1
        except RunnerStopRequested as exc:
            return _finish_worker_terminal(control, status, exc)
        except SystemExit as exc:
            return _finish_worker_terminal(control, status, exc)
        except BaseException as exc:
            return _finish_worker_terminal(control, status, exc)
        finally:
            restore_signal()
    args.serial = resolve_adb_serial(args.adb, args.serial)
    if args.task == "EventSp" and args.use_auto_search:
        result = _supervise_event_sp(args)
    else:
        result = run(args)
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    run_error = result.get("run_error")
    if (
        isinstance(run_error, Mapping)
        and run_error.get("classification") == "runner.interrupted"
    ):
        return 130
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
