"""Deterministic, recorder-only replay of the pinned ALAS Awaken dispatcher."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from .alas_awaken_config_contract import (
    AWAKEN_LEVEL_CAPS,
    validate_alas_awaken_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.awaken-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_declarations(alas_root: Path) -> None:
    args_path = alas_root / "module/config/argument/args.json"
    template_path = alas_root / "config/template.json"
    task_path = alas_root / "module/config/argument/task.yaml"
    generated_path = alas_root / "module/config/config_generated.py"
    arguments = json.loads(args_path.read_text(encoding="utf-8"))
    template = json.loads(template_path.read_text(encoding="utf-8"))
    task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    awaken = arguments.get("Awaken", {}).get("Awaken")
    if not isinstance(awaken, dict) or set(awaken) != {"LevelCap", "Favourite"}:
        raise AssertionError("Awaken field surface drifted")
    if awaken["LevelCap"] != {
        "type": "select",
        "value": "level120",
        "option": ["level120", "level125"],
    } or awaken["Favourite"] != {"type": "checkbox", "value": False}:
        raise AssertionError("Awaken argument declaration drifted")
    if template.get("Awaken", {}).get("Awaken") != {
        "LevelCap": "level120",
        "Favourite": False,
    }:
        raise AssertionError("Awaken template declaration drifted")
    task_groups = [
        item["tasks"]["Awaken"]
        for item in task.values()
        if isinstance(item, dict) and "Awaken" in item.get("tasks", {})
    ]
    if task_groups != [["Scheduler", "Awaken"]]:
        raise AssertionError("Awaken task group declaration drifted")
    tree = ast.parse(generated_path.read_text(encoding="utf-8"), filename=str(generated_path))
    values = {
        target.id: ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id in {"Awaken_LevelCap", "Awaken_Favourite"}
    }
    if values != {"Awaken_LevelCap": "level120", "Awaken_Favourite": False}:
        raise AssertionError("Awaken generated defaults drifted")


def _verify_consumer(path: Path) -> tuple[dict[str, list[str]], bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    awaken = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Awaken"
    )
    run = next(
        node for node in awaken.body if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    reads = {
        name: ["Awaken.run"]
        for name in ("Awaken_LevelCap", "Awaken_Favourite")
        if any(
            isinstance(node, ast.Attribute) and node.attr == name
            for node in ast.walk(run)
        )
    }
    if set(reads) != {"Awaken_LevelCap", "Awaken_Favourite"}:
        raise AssertionError("Awaken runtime consumers drifted")
    executable = [
        statement
        for statement in run.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    first = executable[0] if executable else None
    guard = (
        isinstance(first, ast.Assign)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "validate_alas_awaken_config"
        and {keyword.arg for keyword in first.value.keywords} == {"level_cap", "favourite"}
    )
    return reads, guard


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.awaken.awaken")
    finally:
        sys.path.remove(root)


class _Config:
    def __init__(self, *, level_cap: object, favourite: object):
        self.Awaken_LevelCap = level_cap
        self.Awaken_Favourite = favourite
        self.events: list[tuple[str, dict[str, object]]] = []

    def task_delay(self, **kwargs: object) -> None:
        self.events.append(("task_delay", kwargs))


def _run_case(
    module: Any,
    *,
    level_cap: object,
    favourite: object,
    first_result: str = "success",
) -> dict[str, object]:
    host = object.__new__(module.Awaken)
    config = _Config(level_cap=level_cap, favourite=favourite)
    host.config = config
    events: list[tuple[str, object]] = []
    results = iter((first_result, "success"))

    def awaken_run(*, use_array: bool = False, favourite: bool = False) -> str:
        events.append(("awaken_run", (use_array, favourite)))
        return next(results)

    host.awaken_run = awaken_run
    host.dock_favourite_set = lambda **kwargs: events.append(("favourite_reset", kwargs))
    host.dock_filter_set = lambda **kwargs: events.append(("filter_reset", kwargs))
    module.Awaken.run(host)
    return {"events": events, "config_events": config.events}


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for level_cap in sorted(AWAKEN_LEVEL_CAPS):
        for favourite in (False, True):
            snapshot = validate_alas_awaken_config(
                level_cap=level_cap, favourite=favourite
            )
            if snapshot.level_cap != level_cap or snapshot.favourite is not favourite:
                raise AssertionError("Awaken snapshot drifted")
            accepted += 1
    invalid_cases = (
        ("level_120", False),
        ("LEVEL120", False),
        ("level125 ", False),
        (None, False),
        (True, False),
        (120, False),
        ("level120", None),
        ("level120", 0),
        ("level120", 1),
        ("level120", "false"),
        ("level120", []),
        ("level120", {}),
    )
    for level_cap, favourite in invalid_cases:
        try:
            validate_alas_awaken_config(level_cap=level_cap, favourite=favourite)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Awaken configuration was admitted")
    return accepted, invalid


def _verify_decisions(module: Any) -> dict[str, dict[str, object]]:
    decisions = {
        "level120_not_favourite": _run_case(
            module, level_cap="level120", favourite=False
        ),
        "level120_favourite": _run_case(module, level_cap="level120", favourite=True),
        "level125_timeout": _run_case(
            module, level_cap="level125", favourite=False, first_result="timeout"
        ),
        "level125_continue": _run_case(
            module, level_cap="level125", favourite=True, first_result="success"
        ),
    }
    expected = {
        "level120_not_favourite": {
            "events": [
                ("awaken_run", (False, False)),
                ("filter_reset", {"wait_loading": False}),
            ],
            "config_events": [("task_delay", {"server_update": True})],
        },
        "level120_favourite": {
            "events": [
                ("awaken_run", (False, True)),
                ("favourite_reset", {"wait_loading": False}),
                ("filter_reset", {"wait_loading": False}),
            ],
            "config_events": [("task_delay", {"server_update": True})],
        },
        "level125_timeout": {
            "events": [
                ("awaken_run", (True, False)),
                ("filter_reset", {"wait_loading": False}),
            ],
            "config_events": [("task_delay", {"server_update": True})],
        },
        "level125_continue": {
            "events": [
                ("awaken_run", (True, True)),
                ("awaken_run", (False, True)),
                ("favourite_reset", {"wait_loading": False}),
                ("filter_reset", {"wait_loading": False}),
            ],
            "config_events": [("task_delay", {"server_update": True})],
        },
    }
    if decisions != expected:
        raise AssertionError("original Awaken dispatcher decisions drifted")
    return decisions


def _verify_invalid_entry(module: Any, *, level_cap: object, favourite: object) -> list[object]:
    host = object.__new__(module.Awaken)
    host.config = _Config(level_cap=level_cap, favourite=favourite)
    events: list[object] = []
    host.awaken_run = lambda **kwargs: events.append(("awaken_run", kwargs))
    host.dock_favourite_set = lambda **kwargs: events.append(("favourite_reset", kwargs))
    host.dock_filter_set = lambda **kwargs: events.append(("filter_reset", kwargs))
    try:
        module.Awaken.run(host)
    except SemanticGateClosed:
        return events
    raise AssertionError("patched Awaken entry admitted invalid configuration")


def verify_awaken_config(alas_root: Path) -> dict[str, object]:
    """Verify pinned configuration, dispatch semantics, and early patched gate."""

    alas_root = alas_root.resolve()
    _verify_declarations(alas_root)
    source_path = alas_root / "module/awaken/awaken.py"
    consumers, guard = _verify_consumer(source_path)
    module = _load_original(alas_root)
    accepted, invalid = _verify_contract()
    decisions = _verify_decisions(module)
    invalid_entry_events: dict[str, list[object]] = {}
    if guard:
        invalid_entry_events = {
            "Awaken.LevelCap": _verify_invalid_entry(
                module, level_cap="level_120", favourite=False
            ),
            "Awaken.Favourite": _verify_invalid_entry(
                module, level_cap="level120", favourite=0
            ),
        }
        if any(invalid_entry_events.values()):
            raise AssertionError("invalid Awaken config crossed the dispatcher boundary")
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "patched_guard_present": guard,
        "original_decisions": decisions,
        "invalid_entry_events": invalid_entry_events,
        "mutation_budget": 0,
        "real_awaken_run_called": False,
        "android_input_injected": False,
        "source_sha256": {
            "task": _sha256(alas_root / "module/config/argument/task.yaml"),
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "template": _sha256(alas_root / "config/template.json"),
            "generated": _sha256(alas_root / "module/config/config_generated.py"),
            "awaken": _sha256(source_path),
        },
    }
