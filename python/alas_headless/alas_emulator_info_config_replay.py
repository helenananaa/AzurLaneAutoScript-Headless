"""Deterministic replay for ALAS emulator instance text configuration."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from .alas_emulator_info_config_contract import validate_alas_emulator_info_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.emulator-info-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "PlatformBase"
    )
    return next(
        node for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == "emulator_info"
    )


def _generated_defaults(path: Path) -> dict[str, object]:
    expected = {
        "EmulatorInfo_Emulator": "auto",
        "EmulatorInfo_name": None,
        "EmulatorInfo_path": None,
    }
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    values: dict[str, object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id in expected:
                value = ast.literal_eval(node.value)
                if type(value) is not type(expected[target.id]) or value != expected[target.id]:
                    raise AssertionError(f"{target.id} generated default drifted")
                values[target.id] = value
    if values != expected:
        raise AssertionError("EmulatorInfo generated surface drifted")
    return values


def _verify_argument_schema(path: Path, defaults: dict[str, object]) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    group = document.get("EmulatorInfo") if isinstance(document, dict) else None
    if not isinstance(group, dict):
        raise AssertionError("EmulatorInfo argument schema is unavailable")
    for field in ("name", "path"):
        declaration = group.get(field)
        if not isinstance(declaration, dict):
            raise AssertionError(f"EmulatorInfo.{field} declaration is unavailable")
        if declaration.get("type") != "textarea" or declaration.get("value") is not None:
            raise AssertionError(f"EmulatorInfo.{field} declaration drifted")
        if defaults[f"EmulatorInfo_{field}"] is not None:
            raise AssertionError(f"EmulatorInfo.{field} default drifted")


def _compile(method: ast.FunctionDef):
    module = ast.Module(body=[method], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace: dict[str, Any] = {
        "cached_property": lambda method: method,
        "EmulatorInfo": lambda **values: SimpleNamespace(**values),
    }
    exec(compile(module, "<alas-emulator-info-replay>", "exec"), namespace)
    return namespace[method.name]


def _run_case(
    method,
    *,
    emulator: object = "auto",
    name: object = None,
    path: object = None,
) -> dict[str, object]:
    host = SimpleNamespace(
        config=SimpleNamespace(
            EmulatorInfo_Emulator=emulator,
            EmulatorInfo_name=name,
            EmulatorInfo_path=path,
        )
    )
    try:
        result = method(host)
    except SemanticGateClosed:
        return {"rejected": True, "result": None, "events": []}
    return {
        "rejected": False,
        "result": {"emulator": result.emulator, "name": result.name, "path": result.path},
        "events": [],
    }


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    valid_name = {
        None: "",
        "": "",
        " Nox\n": "Nox",
        " None ": "",
        "False": "",
    }
    for value, expected in valid_name.items():
        snapshot = validate_alas_emulator_info_config(name=value, path=None)
        if snapshot.name != expected or snapshot.path != "":
            raise AssertionError("EmulatorInfo.name normalization drifted")
        accepted += 1
    valid_path = {
        None: "",
        "": "",
        " C:\\Emulator\\player.exe ": "C:\\Emulator\\player.exe",
        "C:\\emu\nplayer.exe": "C:\\emuplayer.exe",
        "True": "",
    }
    for value, expected in valid_path.items():
        snapshot = validate_alas_emulator_info_config(name=None, path=value)
        if snapshot.name != "" or snapshot.path != expected:
            raise AssertionError("EmulatorInfo.path normalization drifted")
        accepted += 1
    for field in ("name", "path"):
        for value in (True, 0, [], {}):
            values = {"name": None, "path": None}
            values[field] = value
            try:
                validate_alas_emulator_info_config(**values)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid EmulatorInfo.{field} was admitted")
    return accepted, invalid


def _verify_property(method) -> dict[str, object]:
    defaults = _run_case(method)
    explicit = _run_case(
        method,
        emulator="BlueStacks5",
        name=" Nox\n",
        path=" C:\\Emulator\\player.exe ",
    )
    if defaults["result"] != {"emulator": "", "name": "", "path": ""}:
        raise AssertionError("EmulatorInfo default property drifted")
    if explicit["result"] != {
        "emulator": "BlueStacks5",
        "name": "Nox",
        "path": "C:\\Emulator\\player.exe",
    }:
        raise AssertionError("EmulatorInfo property normalization drifted")
    invalid = {
        field: _run_case(method, **{field: value})
        for field, value in (("name", True), ("path", []))
    }
    if any(not case["rejected"] or case["events"] for case in invalid.values()):
        raise AssertionError("invalid EmulatorInfo value reached platform discovery")
    return {"defaults": defaults, "explicit": explicit, "invalid_entries": invalid}


def verify_emulator_info_config(alas_root: Path) -> dict[str, object]:
    root = alas_root.resolve()
    platform_path = root / "module" / "device" / "platform" / "platform_base.py"
    config_path = root / "module" / "config" / "config_generated.py"
    argument_path = root / "module" / "config" / "argument" / "argument.yaml"
    if not all(path.is_file() for path in (platform_path, config_path, argument_path)):
        raise FileNotFoundError("ALAS EmulatorInfo source is incomplete")
    defaults = _generated_defaults(config_path)
    _verify_argument_schema(argument_path, defaults)
    property_method = _method(platform_path)
    calls = {
        node.func.id for node in ast.walk(property_method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    if "validate_alas_emulator_info_config" not in calls:
        raise AssertionError("EmulatorInfo validation guard is absent")
    accepted, invalid = _verify_contract()
    property_result = _verify_property(_compile(property_method))
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_defaults": defaults,
        "runtime_consumers": {
            "EmulatorInfo.name": "PlatformBase.emulator_info",
            "EmulatorInfo.path": "PlatformBase.emulator_info",
        },
        "original_decisions": {"emulator_info": property_result},
        "mutation_budget": 0,
        "filesystem_probed": False,
        "emulator_started": False,
        "android_input_injected": False,
        "source_sha256": {
            "platform_base": _sha256(platform_path),
            "config_generated": _sha256(config_path),
            "argument_schema": _sha256(argument_path),
        },
    }
