"""Deterministic replay for ALAS equipment-code configuration parsing."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

import yaml

from .alas_equipment_code_config_contract import validate_alas_equipment_code_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.equipment-code-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _methods(path: Path) -> tuple[ast.FunctionDef, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "EquipmentCodeHandler"
    )
    methods = {
        node.name: node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name in {"get_code", "set_code"}
    }
    if set(methods) != {"get_code", "set_code"}:
        raise AssertionError("EquipmentCode configuration methods are unavailable")
    return methods["get_code"], methods["set_code"]


def _generated_default(path: Path) -> object:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "EquipmentCode_Config"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if value is not None:
                raise AssertionError("EquipmentCode generated default drifted")
            return value
    raise AssertionError("EquipmentCode generated default is unavailable")


def _verify_argument_schema(path: Path, default: object) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    group = document.get("EquipmentCode") if isinstance(document, dict) else None
    declaration = group.get("Config") if isinstance(group, dict) else None
    if not isinstance(declaration, dict):
        raise AssertionError("EquipmentCode argument schema is unavailable")
    if (
        declaration.get("type") != "textarea"
        or declaration.get("mode") != "yaml"
        or declaration.get("value") != ""
        or default is not None
    ):
        raise AssertionError("EquipmentCode argument schema drifted")


def _compile(get_method: ast.FunctionDef, set_method: ast.FunctionDef):
    module = ast.Module(body=[get_method, set_method], type_ignores=[])
    ast.fix_missing_locations(module)
    events: list[dict[str, object]] = []

    class _Logger:
        def error(self, *_args, **_kwargs) -> None:
            return None

    namespace: dict[str, Any] = {
        "logger": _Logger(),
        "yaml": yaml,
        "validate_alas_equipment_code_config": validate_alas_equipment_code_config,
    }
    exec(compile(module, "<alas-equipment-code-replay>", "exec"), namespace)
    return namespace["get_code"], namespace["set_code"], events


class _Config:
    def __init__(self, value: object, events: list[dict[str, object]]) -> None:
        object.__setattr__(self, "EquipmentCode_Config", value)
        object.__setattr__(self, "_events", events)

    def __setattr__(self, name: str, value: object) -> None:
        if name == "EquipmentCode_Config":
            self._events.append({"kind": "in_memory_config_update", "value": value})
        object.__setattr__(self, name, value)


def _host(value: object, events: list[dict[str, object]]):
    return type("EquipmentCodeReplayHost", (), {"config": _Config(value, events)})()


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    valid_cases = (
        ("bogue: code-a", {"bogue": "code-a"}),
        ("{}", {}),
        ("", {}),
        ("---\nbogue: old\n---\nbogue: new\nDD: code-dd", {"bogue": "new", "DD": "code-dd"}),
        ("bogue: null", {"bogue": None}),
    )
    for value, expected in valid_cases:
        if validate_alas_equipment_code_config(value) != expected:
            raise AssertionError("EquipmentCode configuration normalization drifted")
        accepted += 1
    for value in (None, True, 0, [], "[", "- item", "plain", "7: value"):
        try:
            validate_alas_equipment_code_config(value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid EquipmentCode configuration was admitted")
    return accepted, invalid


def _verify_runtime(get_method: ast.FunctionDef, set_method: ast.FunctionDef) -> dict[str, object]:
    get_code, set_code, events = _compile(get_method, set_method)
    host = _host("bogue: code-a\nDD: code-dd", events)
    result = get_code(host, "bogue")
    if result != "code-a" or events:
        raise AssertionError("EquipmentCode lookup changed the configuration")

    missing = get_code(host, "ranger")
    invalid_get = get_code(_host("[", events), "bogue")
    if missing is not None or invalid_get is not None or events:
        raise AssertionError("EquipmentCode invalid lookup reached an action boundary")

    valid_set_host = _host("bogue: code-a", events)
    set_code(valid_set_host, "DD", "code-dd")
    valid_set_events = list(events)
    if len(valid_set_events) != 1 or valid_set_events[0]["kind"] != "in_memory_config_update":
        raise AssertionError("EquipmentCode writeback intent drifted")
    if yaml.safe_load(valid_set_host.config.EquipmentCode_Config) != {
        "DD": "code-dd",
        "bogue": "code-a",
    }:
        raise AssertionError("EquipmentCode writeback value drifted")

    del events[:]
    invalid_set_host = _host("[", events)
    set_code(invalid_set_host, "DD", "code-dd")
    if events:
        raise AssertionError("invalid EquipmentCode config reached writeback")
    return {
        "lookup": {"result": result, "events": []},
        "missing": missing,
        "invalid_lookup": invalid_get,
        "valid_set": {"in_memory_updates": valid_set_events},
        "invalid_set": {"in_memory_updates": []},
    }


def verify_equipment_code_config(alas_root: Path) -> dict[str, object]:
    root = alas_root.resolve()
    source_path = root / "module" / "equipment" / "equipment_code.py"
    config_path = root / "module" / "config" / "config_generated.py"
    argument_path = root / "module" / "config" / "argument" / "argument.yaml"
    if not all(path.is_file() for path in (source_path, config_path, argument_path)):
        raise FileNotFoundError("ALAS EquipmentCode source is incomplete")
    default = _generated_default(config_path)
    _verify_argument_schema(argument_path, default)
    get_method, set_method = _methods(source_path)
    guard_calls = [
        node
        for method in (get_method, set_method)
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_equipment_code_config"
    ]
    if len(guard_calls) != 2:
        raise AssertionError("EquipmentCode validation guards are incomplete")
    accepted, invalid = _verify_contract()
    runtime = _verify_runtime(get_method, set_method)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_default": default,
        "runtime_consumers": [
            "EquipmentCodeHandler.get_code",
            "EquipmentCodeHandler.set_code",
        ],
        "original_decisions": runtime,
        "mutation_budget": 0,
        "config_writebacks": 0,
        "device_navigation": 0,
        "equipment_imports": 0,
        "android_input_injected": False,
        "source_sha256": {
            "equipment_code": _sha256(source_path),
            "config_generated": _sha256(config_path),
            "argument_schema": _sha256(argument_path),
        },
    }
