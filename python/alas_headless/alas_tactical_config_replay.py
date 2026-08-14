"""Deterministic replay of pinned ALAS tactical configuration decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_tactical_config_contract import validate_alas_tactical_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.tactical-config-replay/v1"
EXPECTED_CONSUMERS = {
    "ControlExpOverflow": {"_tactical_books_filter_exp"},
    "AddNewStudent.Enable": {"tactical_class_receive"},
    "AddNewStudent.Favorite": {"select_suitable_ship"},
    "AddNewStudent.MinLevel": {"select_suitable_ship"},
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _defaults() -> dict[str, object]:
    return {
        "control_exp_overflow_enable": True,
        "t1_allow": 200,
        "t2_allow": 200,
        "t3_allow": 100,
        "t4_allow": 100,
        "add_new_student_enable": False,
        "add_new_student_favorite": False,
        "add_new_student_min_level": 50,
    }


def _config(**overrides: object) -> SimpleNamespace:
    values = {
        "ControlExpOverflow_Enable": True,
        "ControlExpOverflow_T1Allow": 200,
        "ControlExpOverflow_T2Allow": 200,
        "ControlExpOverflow_T3Allow": 100,
        "ControlExpOverflow_T4Allow": 100,
        "AddNewStudent_Enable": False,
        "AddNewStudent_Favorite": False,
        "AddNewStudent_MinLevel": 50,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _verify_args(alas_root: Path) -> None:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panel = document.get("Tactical")
    if not isinstance(panel, dict):
        raise AssertionError("Tactical panel is absent")
    overflow = panel.get("ControlExpOverflow")
    student = panel.get("AddNewStudent")
    if not isinstance(overflow, dict) or set(overflow) != {
        "Enable",
        "T1Allow",
        "T2Allow",
        "T3Allow",
        "T4Allow",
    }:
        raise AssertionError("ControlExpOverflow field surface drifted")
    if not isinstance(student, dict) or set(student) != {
        "Enable",
        "Favorite",
        "MinLevel",
    }:
        raise AssertionError("AddNewStudent field surface drifted")
    if overflow["Enable"].get("type") != "checkbox":
        raise AssertionError("ControlExpOverflow.Enable type drifted")
    if student["Enable"].get("type") != "checkbox" or student["Favorite"].get(
        "type"
    ) != "checkbox":
        raise AssertionError("AddNewStudent boolean surface drifted")


def _verify_consumers(path: Path) -> dict[str, list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = {name: set() for name in EXPECTED_CONSUMERS}
    tactical_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "RewardTacticalClass"
    )
    for node in tactical_class.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if node.name == "_validate_tactical_config":
            continue
        attributes = {
            child.attr
            for child in ast.walk(node)
            if isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Load)
        }
        if (
            "ControlExpOverflow_Enable" in attributes
            or "control_exp_overflow_enable" in attributes
            or any(
                isinstance(child, ast.JoinedStr)
                and "ControlExpOverflow_T" in ast.unparse(child)
                for child in ast.walk(node)
            )
        ):
            found["ControlExpOverflow"].add(node.name)
        for suffix, snapshot_name in (
            ("Enable", "add_new_student_enable"),
            ("Favorite", "add_new_student_favorite"),
            ("MinLevel", "add_new_student_min_level"),
        ):
            if f"AddNewStudent_{suffix}" in attributes or snapshot_name in attributes:
                found[f"AddNewStudent.{suffix}"].add(node.name)
    if found != EXPECTED_CONSUMERS:
        raise AssertionError("Tactical runtime consumer surface drifted")
    return {name: sorted(values) for name, values in found.items()}


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.tactical.tactical_class")
        return module, module.RewardTacticalClass
    finally:
        sys.path.remove(root)


def _book_filter_case(
    module: Any,
    tactical_type: type[Any],
    *,
    enabled: bool,
    total: int = 5_800,
) -> list[str]:
    allowances = {1: 200, 2: 200, 3: 100, 4: 100}
    books = [SimpleNamespace(identifier="special", tier=1, exp_value=100)]
    for tier, allowance in allowances.items():
        books.append(
            SimpleNamespace(
                identifier=f"t{tier}-boundary",
                tier=tier,
                exp_value=100 + allowance,
            )
        )
        books.append(
            SimpleNamespace(
                identifier=f"t{tier}-over",
                tier=tier,
                exp_value=101 + allowance,
            )
        )
    host = object.__new__(tactical_type)
    host.config = _config(ControlExpOverflow_Enable=enabled)
    host.device = SimpleNamespace(image=None)
    host.books = module.SelectedGrids(books)
    old_skill_exp = module.SKILL_EXP
    module.SKILL_EXP = SimpleNamespace(
        ocr=lambda image: (5_700, max(total - 5_700, 0), total)
    )
    try:
        tactical_type._tactical_books_filter_exp(host)
    finally:
        module.SKILL_EXP = old_skill_exp
    return [book.identifier for book in host.books]


def _semantic_student_case(module: Any, tactical_type: type[Any]) -> dict[str, Any]:
    calls = []

    class Session:
        def tactical_select_suitable_ship(self, *values: object) -> bool:
            calls.append(tuple(values))
            return True

    host = object.__new__(tactical_type)
    host.config = _config(
        AddNewStudent_Enable=True,
        AddNewStudent_Favorite=True,
        AddNewStudent_MinLevel="50",
    )
    host.dock_select_index = 2
    package = importlib.import_module("alas_headless")
    old_current = package.current_semantic_session
    package.current_semantic_session = lambda: Session()
    try:
        result = tactical_type.select_suitable_ship(host)
    finally:
        package.current_semantic_session = old_current
    if result is not True or len(calls) != 1:
        raise AssertionError("original tactical student selection drifted")
    guard_present = hasattr(tactical_type, "_validate_tactical_config")
    expected = (True, 50, 2) if guard_present else (50, 2)
    if calls[0] != expected:
        raise AssertionError("tactical favorite/min-level forwarding drifted")
    return {
        "call": calls[0],
        "favorite_forwarded": guard_present,
        "min_level": 50,
        "start_index": 2,
    }


def _verify_original(module: Any, tactical_type: type[Any]) -> dict[str, Any]:
    disabled = _book_filter_case(module, tactical_type, enabled=False)
    enabled = _book_filter_case(module, tactical_type, enabled=True)
    not_max = _book_filter_case(module, tactical_type, enabled=False, total=4_000)
    if disabled != ["special"]:
        raise AssertionError("disabled tactical overflow decision drifted")
    expected_enabled = ["special"] + [
        f"t{tier}-boundary" for tier in range(1, 5)
    ]
    if enabled != expected_enabled:
        raise AssertionError("enabled tactical overflow boundaries drifted")
    if len(not_max) != 9:
        raise AssertionError("non-max tactical book list was filtered")

    student = _semantic_student_case(module, tactical_type)
    guard_present = hasattr(tactical_type, "_validate_tactical_config")
    if guard_present:
        host = object.__new__(tactical_type)
        host.config = _config(AddNewStudent_Enable=1)
        try:
            tactical_type.tactical_class_receive(host)
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError("patched tactical receive admitted invalid config")
    return {
        "overflow_disabled": disabled,
        "overflow_enabled": enabled,
        "non_max_count": len(not_max),
        "student": student,
        "patched_guard_present": guard_present,
    }


def verify_tactical_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    source = alas_root / "module" / "tactical" / "tactical_class.py"
    consumers = _verify_consumers(source)
    module, tactical_type = _load_original(alas_root)
    decisions = _verify_original(module, tactical_type)

    accepted = 0
    for overflow in (False, True):
        for add_student in (False, True):
            for favorite in (False, True):
                for min_level in (1, 50, 125):
                    values = _defaults()
                    values.update(
                        control_exp_overflow_enable=overflow,
                        add_new_student_enable=add_student,
                        add_new_student_favorite=favorite,
                        add_new_student_min_level=min_level,
                    )
                    validate_alas_tactical_config(**values)
                    accepted += 1
    for field in ("t1_allow", "t2_allow", "t3_allow", "t4_allow"):
        for value in (0, 5_800):
            values = _defaults()
            values[field] = value
            validate_alas_tactical_config(**values)
            accepted += 1
    for value in ("1", "125"):
        values = _defaults()
        values["add_new_student_min_level"] = value
        validate_alas_tactical_config(**values)
        accepted += 1

    invalid_count = 0
    invalids = (
        ("control_exp_overflow_enable", 1),
        ("t1_allow", -1),
        ("t2_allow", 5_801),
        ("t3_allow", True),
        ("t4_allow", "100"),
        ("add_new_student_enable", 0),
        ("add_new_student_favorite", 1),
        ("add_new_student_min_level", 0),
        ("add_new_student_min_level", 126),
        ("add_new_student_min_level", True),
        ("add_new_student_min_level", "1e2"),
        ("add_new_student_min_level", None),
    )
    for field, value in invalids:
        values = _defaults()
        values[field] = value
        try:
            validate_alas_tactical_config(**values)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid tactical configuration was admitted")

    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 8,
        "panel_count": 1,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid_count,
        "runtime_consumers": consumers,
        "original_decisions": decisions,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "tactical_class": _sha256(source),
        },
    }
