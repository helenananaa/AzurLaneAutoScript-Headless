"""Prove Main/Main2/Main3 shared configuration and dispatch equivalence."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping

from .alas_campaign_route_config_contract import MAIN_TASKS
from .alas_main_shared_config_contract import (
    MAIN_SHARED_GROUPS,
    STOP_CONDITION_MAP_ACHIEVEMENTS,
    validate_alas_main_stop_condition_config,
)
from .alas_scheduler_contract import validate_alas_scheduler_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.main-shared-config-equivalence/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AzurLaneAutoScript":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return item
    raise AssertionError("missing AzurLaneAutoScript." + name)


def _dispatch_signature(method: ast.FunctionDef) -> str:
    normalized = copy.deepcopy(method)
    normalized.name = "main_instance"
    return ast.dump(normalized, include_attributes=False)


def _execute_dispatch_methods(tree: ast.Module) -> Mapping[str, object]:
    calls: list[Mapping[str, object]] = []
    hosts: dict[str, object] = {}

    class FakeCampaignRun:
        def __init__(self, *, config: object, device: object) -> None:
            self.config = config
            self.device = device

        def run(self, **values: object) -> None:
            calls.append(
                {
                    "config": self.config,
                    "device": self.device,
                    **values,
                }
            )

    module_package = ModuleType("module")
    campaign_package = ModuleType("module.campaign")
    run_module = ModuleType("module.campaign.run")
    run_module.CampaignRun = FakeCampaignRun
    saved = {name: sys.modules.get(name) for name in (
        "module",
        "module.campaign",
        "module.campaign.run",
    )}
    sys.modules["module"] = module_package
    sys.modules["module.campaign"] = campaign_package
    sys.modules["module.campaign.run"] = run_module
    try:
        namespace: dict[str, object] = {}
        for task in MAIN_TASKS:
            node = copy.deepcopy(_method(tree, task.lower()))
            node.name = "dispatch"
            compiled = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
            exec(compile(compiled, "<alas-main-dispatch>", "exec"), namespace)
            host = SimpleNamespace(
                config=SimpleNamespace(
                    Campaign_Name=task + "-stage",
                    Campaign_Event="campaign_main",
                    Campaign_Mode="normal",
                ),
                device=object(),
            )
            hosts[task] = host
            namespace["dispatch"](host)
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    return {
        task: {
            "name": calls[index]["name"],
            "folder": calls[index]["folder"],
            "mode": calls[index]["mode"],
            "config_identity_preserved": (
                calls[index]["config"] is hosts[task].config
            ),
            "device_identity_preserved": (
                calls[index]["device"] is hosts[task].device
            ),
        }
        for index, task in enumerate(MAIN_TASKS)
    }


def _normalized_template(panel: Mapping[str, Any]) -> Mapping[str, Any]:
    value = copy.deepcopy(dict(panel))
    value["Scheduler"]["Command"] = "<main-instance>"
    return value


def _normalized_arguments(panel: Mapping[str, Any]) -> Mapping[str, Any]:
    value = copy.deepcopy(dict(panel))
    value["Scheduler"]["Command"]["value"] = "<main-instance>"
    return value


def _scheduler_surface(template: Mapping[str, Any]) -> Mapping[str, Any]:
    data: dict[str, Any] = {}
    for task in MAIN_TASKS:
        scheduler = copy.deepcopy(template[task]["Scheduler"])
        scheduler["NextRun"] = datetime.fromisoformat(scheduler["NextRun"])
        data[task] = {"Scheduler": scheduler}
    snapshots = validate_alas_scheduler_config(data)
    return {
        snapshot.panel: {
            "command": snapshot.command,
            "server_updates": snapshot.server_updates,
        }
        for snapshot in snapshots
    }


def _stop_condition_cases() -> tuple[int, int]:
    defaults: dict[str, object] = {
        "oil_limit": 1000,
        "run_count": 0,
        "map_achievement": "non_stop",
        "stage_increase": False,
        "get_new_ship": False,
        "reach_level": 0,
    }
    legal_rows: list[tuple[str, object]] = []
    legal_rows.extend(("oil_limit", value) for value in (0, 499, 1000, 999999))
    legal_rows.extend(("run_count", value) for value in (0, 1, 999999))
    legal_rows.extend(
        ("map_achievement", value) for value in STOP_CONDITION_MAP_ACHIEVEMENTS
    )
    legal_rows.extend(("stage_increase", value) for value in (False, True))
    legal_rows.extend(("get_new_ship", value) for value in (False, True))
    legal_rows.extend(("reach_level", value) for value in (0, 1, 125, 999999))
    invalid_rows = (
        ("oil_limit", -1),
        ("oil_limit", True),
        ("oil_limit", "1000"),
        ("run_count", -1),
        ("run_count", False),
        ("run_count", 1.0),
        ("map_achievement", "unknown"),
        ("map_achievement", None),
        ("stage_increase", 1),
        ("stage_increase", "false"),
        ("get_new_ship", 0),
        ("get_new_ship", None),
        ("reach_level", -1),
        ("reach_level", True),
        ("reach_level", "125"),
    )
    accepted = 0
    rejected = 0
    for task in MAIN_TASKS:
        for field, value in legal_rows:
            values = dict(defaults)
            values[field] = value
            snapshot = validate_alas_main_stop_condition_config(task=task, **values)
            if snapshot is None or snapshot.task != task:
                raise AssertionError("legal Main stop-condition row was not classified")
            accepted += 1
        for field, value in invalid_rows:
            values = dict(defaults)
            values[field] = value
            try:
                validate_alas_main_stop_condition_config(task=task, **values)
            except SemanticGateClosed:
                rejected += 1
            else:
                raise AssertionError("invalid Main stop-condition row was admitted")
    if validate_alas_main_stop_condition_config(
        task="Event",
        **defaults,
    ) is not None:
        raise AssertionError("non-Main stop conditions were unexpectedly constrained")
    return accepted, rejected


def verify_main_shared_config(alas_root: Path) -> Mapping[str, object]:
    alas_root = alas_root.resolve()
    args_path = alas_root / "module" / "config" / "argument" / "args.json"
    template_path = alas_root / "config" / "template.json"
    alas_path = alas_root / "alas.py"
    run_path = alas_root / "module" / "campaign" / "run.py"
    arguments = json.loads(args_path.read_text(encoding="utf-8"))
    template = json.loads(template_path.read_text(encoding="utf-8"))
    tree = ast.parse(alas_path.read_text(encoding="utf-8"), filename=str(alas_path))

    reference_args = arguments[MAIN_TASKS[0]]
    normalized_reference_args = _normalized_arguments(reference_args)
    reference_template = _normalized_template(template[MAIN_TASKS[0]])
    if tuple(reference_args) != MAIN_SHARED_GROUPS:
        raise AssertionError("Main shared group order drifted")
    field_count = sum(len(fields) for fields in reference_args.values())
    for task in MAIN_TASKS:
        if _normalized_arguments(arguments.get(task, {})) != normalized_reference_args:
            raise AssertionError(task + " argument declarations diverged from Main")
        if _normalized_template(template.get(task, {})) != reference_template:
            raise AssertionError(task + " template diverged beyond Scheduler.Command")
        if template[task]["Scheduler"]["Command"] != task:
            raise AssertionError(task + " Scheduler.Command is not independent")

    signatures = {
        task: _dispatch_signature(_method(tree, task.lower())) for task in MAIN_TASKS
    }
    if len(set(signatures.values())) != 1:
        raise AssertionError("Main dispatch wrappers are not structurally equivalent")
    dispatches = _execute_dispatch_methods(tree)
    for task, dispatch in dispatches.items():
        if dispatch["name"] != task + "-stage":
            raise AssertionError(task + " dispatch leaked another panel's stage")

    accepted, rejected = _stop_condition_cases()
    return {
        "schema": SCHEMA,
        "passed": True,
        "tasks": list(MAIN_TASKS),
        "group_count": len(MAIN_SHARED_GROUPS),
        "field_count": field_count,
        "panel_field_instance_count": field_count * len(MAIN_TASKS),
        "intentional_template_differences": ["Scheduler.Command"],
        "scheduler": _scheduler_surface(template),
        "dispatches": dispatches,
        "stop_condition_accepted_rows": accepted,
        "stop_condition_rejected_rows": rejected,
        "source_sha256": {
            "args": _sha256(args_path),
            "template": _sha256(template_path),
            "alas": _sha256(alas_path),
            "run": _sha256(run_path),
        },
        "mutation_budget": 0,
        "android_input_injected": False,
    }


__all__ = ("SCHEMA", "verify_main_shared_config")
