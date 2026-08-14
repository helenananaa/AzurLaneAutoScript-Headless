"""Deterministic replay of pinned ALAS Game Manager restart decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_game_manager_config_contract import validate_alas_game_manager_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.game-manager-config-replay/v1"
INVALID_VALUES = (0, 1, None, "true", [], {})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    field = document.get("GameManager", {}).get("GameManager", {}).get("AutoRestart")
    if not isinstance(field, dict):
        raise AssertionError("GameManager.AutoRestart declaration is missing")
    if field.get("type") != "checkbox" or field.get("value") is not True:
        raise AssertionError("GameManager.AutoRestart declaration drifted")


def _source_flags(path: Path) -> tuple[bool, bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    run = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "GameManager":
            run = next(
                (
                    child
                    for child in node.body
                    if isinstance(child, ast.FunctionDef) and child.name == "run"
                ),
                None,
            )
    if run is None:
        raise AssertionError("GameManager.run is missing")
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_game_manager_config"
        for node in ast.walk(run)
    )
    semantic_path_present = any(
        isinstance(node, ast.Attribute)
        and node.attr == "restart_game_for_manager"
        for node in ast.walk(run)
    )
    if guard_present:
        executable = [
            statement
            for statement in run.body
            if not isinstance(statement, (ast.Import, ast.ImportFrom))
        ]
        first_statement = executable[0]
        if not (
            isinstance(first_statement, ast.Assign)
            and isinstance(first_statement.value, ast.Call)
            and isinstance(first_statement.value.func, ast.Name)
            and first_statement.value.func.id == "validate_alas_game_manager_config"
        ):
            raise AssertionError("GameManager guard is not first in run")
    return guard_present, semantic_path_present


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.daemon.game_manager")
        return module, module.GameManager
    finally:
        sys.path.remove(root)


def _run_case(
    manager_type: type[Any],
    *,
    auto_restart: object,
    semantic_backend: bool,
) -> list[str]:
    events = []
    adapter = None
    if semantic_backend:
        adapter = SimpleNamespace(
            restart_game_for_manager=lambda: events.append("semantic_restart")
        )
    device = SimpleNamespace(
        semantic_adapter=adapter,
        app_stop=lambda: events.append("app_stop"),
        app_start=lambda: events.append("app_start"),
    )
    host = object.__new__(manager_type)
    host.config = SimpleNamespace(GameManager_AutoRestart=auto_restart)
    host.device = device
    host.handle_app_login = MethodType(lambda self: events.append("login"), host)
    manager_type.run(host)
    return events


def _verify_original(
    manager_type: type[Any], *, semantic_path_present: bool
) -> dict[str, list[str]]:
    cases = {}
    for auto_restart in (False, True):
        for semantic_backend in (False, True):
            key = f"restart_{int(auto_restart)}_semantic_{int(semantic_backend)}"
            events = _run_case(
                manager_type,
                auto_restart=auto_restart,
                semantic_backend=semantic_backend,
            )
            if semantic_path_present and semantic_backend and auto_restart:
                expected = ["semantic_restart", "login"]
            elif auto_restart:
                expected = ["app_stop", "app_start", "login"]
            else:
                expected = ["app_stop"]
            if events != expected:
                raise AssertionError("original GameManager lifecycle decision drifted")
            cases[key] = events
    return cases


def _verify_contract() -> int:
    for value in (False, True):
        validate_alas_game_manager_config(auto_restart=value)
    invalid_count = 0
    for value in INVALID_VALUES:
        try:
            validate_alas_game_manager_config(auto_restart=value)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid GameManager.AutoRestart was admitted")
    return invalid_count


def _verify_invalid_entry(manager_type: type[Any], *, guard_present: bool) -> list[Any]:
    if not guard_present:
        return []
    try:
        _run_case(manager_type, auto_restart=None, semantic_backend=True)
    except SemanticGateClosed:
        return []
    raise AssertionError("patched GameManager admitted invalid AutoRestart")


def verify_game_manager_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    source = alas_root / "module" / "daemon" / "game_manager.py"
    guard_present, semantic_path_present = _source_flags(source)
    module, manager_type = _load_original(alas_root)
    decisions = _verify_original(
        manager_type,
        semantic_path_present=semantic_path_present,
    )
    invalid_count = _verify_contract()
    invalid_events = _verify_invalid_entry(
        manager_type,
        guard_present=guard_present,
    )
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "accepted_case_count": 2,
        "invalid_case_count": invalid_count,
        "patched_guard_present": guard_present,
        "semantic_restart_path_present": semantic_path_present,
        "original_decisions": decisions,
        "invalid_entry_events": invalid_events,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_app_lifecycle_called": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "game_manager": _sha256(source),
        },
    }
