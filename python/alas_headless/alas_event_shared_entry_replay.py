"""Prove the seven campaign-event panels share one guarded entry model."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Mapping

from .alas_event_daily_config_contract import EVENT_DAILY_COMMANDS
from .alas_event_shared_entry_contract import (
    EVENT_COMMANDS,
    EVENT_DIRECT_COMMANDS,
    EVENT_SHARED_GROUPS,
    validate_alas_event_shared_entry_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.event-shared-entry-equivalence/v1"
_CLASSIC_STAGES = tuple(
    f"{prefix}{number}" for prefix in "abcd" for number in range(1, 4)
) + ("sp",)
_T_STAGES = ("t1", "t2", "t3", "t4", "t5", "t6", "ht1", "ht2", "ht3", "ht4", "ht5", "ht6", "sp")
_INTENTIONAL_DISPLAY_DIFFERENCES = (
    ("Campaign", "Name"),
    ("Campaign", "Use2xBook"),
    ("StopCondition", "GetNewShip"),
    ("StopCondition", "MapAchievement"),
    ("StopCondition", "ReachLevel"),
    ("StopCondition", "RunCount"),
    ("StopCondition", "StageIncrease"),
    ("Submarine", "AutoSearchMode"),
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AzurLaneAutoScript":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == name:
                    return item
    raise AssertionError("missing AzurLaneAutoScript." + name)


def _normalized_method(method: ast.FunctionDef) -> str:
    value = copy.deepcopy(method)
    value.name = "event_instance"
    return ast.dump(value, include_attributes=False)


def _normalized_panel(panel: Mapping[str, Any]) -> Mapping[str, Any]:
    value = copy.deepcopy(dict(panel))
    value.pop("EventDaily", None)
    value["Scheduler"]["Command"]["value"] = "<event-instance>"
    value["Scheduler"]["FailureInterval"]["value"] = "<event-schedule>"
    value["Scheduler"]["SuccessInterval"]["value"] = "<event-schedule>"
    value["Campaign"]["Name"]["value"] = "<event-entry>"
    for group, field in _INTENTIONAL_DISPLAY_DIFFERENCES:
        value[group][field].pop("display", None)
    return value


def _normalized_template(panel: Mapping[str, Any]) -> Mapping[str, Any]:
    value = copy.deepcopy(dict(panel))
    value.pop("EventDaily", None)
    value["Scheduler"]["Command"] = "<event-instance>"
    value["Scheduler"]["FailureInterval"] = "<event-schedule>"
    value["Scheduler"]["SuccessInterval"] = "<event-schedule>"
    value["Campaign"]["Name"] = "<event-entry>"
    return value


def _execute_wrappers(tree: ast.Module) -> Mapping[str, object]:
    calls: list[Mapping[str, object]] = []
    hosts: dict[str, object] = {}

    class FakeRunner:
        runner = "unknown"

        def __init__(self, *, config: object, device: object) -> None:
            self.config = config
            self.device = device

        def run(self, **values: object) -> None:
            calls.append(
                {
                    "runner": self.runner,
                    "config": self.config,
                    "device": self.device,
                    **values,
                }
            )

    class FakeCampaignRun(FakeRunner):
        runner = "CampaignRun"

    class FakeCampaignABCD(FakeRunner):
        runner = "CampaignABCD"

    class FakeCampaignSP(FakeRunner):
        runner = "CampaignSP"

    modules = {
        "module": ModuleType("module"),
        "module.campaign": ModuleType("module.campaign"),
        "module.campaign.run": ModuleType("module.campaign.run"),
        "module.event": ModuleType("module.event"),
        "module.event.campaign_abcd": ModuleType("module.event.campaign_abcd"),
        "module.event.campaign_sp": ModuleType("module.event.campaign_sp"),
    }
    modules["module.campaign.run"].CampaignRun = FakeCampaignRun
    modules["module.event.campaign_abcd"].CampaignABCD = FakeCampaignABCD
    modules["module.event.campaign_sp"].CampaignSP = FakeCampaignSP
    saved = {name: sys.modules.get(name) for name in modules}
    sys.modules.update(modules)
    try:
        namespace: dict[str, object] = {}
        for task in EVENT_COMMANDS:
            method_name = task.lower() if task in EVENT_DIRECT_COMMANDS else task.replace("Event", "event_").lower()
            node = copy.deepcopy(_method(tree, method_name))
            node.name = "dispatch"
            compiled = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
            exec(compile(compiled, "<alas-event-dispatch>", "exec"), namespace)
            name = "D3" if task in EVENT_DIRECT_COMMANDS else ("sp" if task == "EventSp" else "dynamic")
            host = SimpleNamespace(
                config=SimpleNamespace(
                    Campaign_Name=name,
                    Campaign_Event="event_20260813_cn",
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
            "runner": calls[index]["runner"],
            "arguments": {
                key: value
                for key, value in calls[index].items()
                if key not in {"runner", "config", "device"}
            },
            "config_identity_preserved": calls[index]["config"] is hosts[task].config,
            "device_identity_preserved": calls[index]["device"] is hosts[task].device,
        }
        for index, task in enumerate(EVENT_COMMANDS)
    }


def _contract_cases() -> tuple[int, int]:
    accepted = 0
    rejected = 0
    event = "event_20260813_cn"
    for task in EVENT_DIRECT_COMMANDS:
        for stage in _CLASSIC_STAGES:
            for mode in ("normal", "hard"):
                validate_alas_event_shared_entry_config(
                    task=task, stage=stage, event=event, mode=mode
                )
                accepted += 1
    aliases = {
        "EventA": ("dynamic", "a1", "a2", "a3", "t1", "t2", "t3"),
        "EventB": ("dynamic", "b1", "b2", "b3", "t4", "t5", "t6"),
        "EventC": ("dynamic", "c1", "c2", "c3", "ht1", "ht2", "ht3"),
        "EventD": ("dynamic", "d1", "d2", "d3", "ht4", "ht5", "ht6"),
    }
    for task, stages in aliases.items():
        for stage in stages:
            validate_alas_event_shared_entry_config(
                task=task, stage=stage, event=event, mode="normal"
            )
            accepted += 1
    validate_alas_event_shared_entry_config(
        task="EventSp", stage="sp", event=event, mode="normal"
    )
    accepted += 1

    invalid: list[Mapping[str, object]] = []
    for task in EVENT_COMMANDS:
        stage = "D3" if task in EVENT_DIRECT_COMMANDS else ("sp" if task == "EventSp" else "dynamic")
        for bad_event in ("campaign_main", "../event", "", None):
            invalid.append({"task": task, "stage": stage, "event": bad_event, "mode": "normal"})
        for bad_mode in (None, "auto"):
            invalid.append({"task": task, "stage": stage, "event": event, "mode": bad_mode})
    for task in EVENT_DAILY_COMMANDS + ("EventSp",):
        stage = "sp" if task == "EventSp" else "dynamic"
        invalid.append({"task": task, "stage": stage, "event": event, "mode": "hard"})
    for task in EVENT_DIRECT_COMMANDS:
        for stage in ("dynamic", "../a1", "", None):
            invalid.append({"task": task, "stage": stage, "event": event, "mode": "normal"})
    for task in EVENT_DAILY_COMMANDS:
        wrong = "b1" if task != "EventB" else "a1"
        for stage in (wrong, "sp", task[-1].lower() + "4", "../a1", None):
            invalid.append({"task": task, "stage": stage, "event": event, "mode": "normal"})
    for stage in ("a1", "dynamic", "../sp", None):
        invalid.append({"task": "EventSp", "stage": stage, "event": event, "mode": "normal"})
    invalid.append({"task": None, "stage": "a1", "event": event, "mode": "normal"})
    for values in invalid:
        try:
            validate_alas_event_shared_entry_config(**values)
        except SemanticGateClosed:
            rejected += 1
        else:
            raise AssertionError("invalid event entry row was admitted: " + repr(values))
    if validate_alas_event_shared_entry_config(
        task="Main", stage="12-4", event="campaign_main", mode="normal"
    ) is not None:
        raise AssertionError("non-event CampaignRun task was unexpectedly constrained")
    return accepted, rejected


def _event_inventory(alas_root: Path) -> Mapping[str, object]:
    campaign = alas_root / "campaign"
    for folder in sorted(campaign.glob("event_*"), reverse=True):
        if not folder.is_dir():
            continue
        stages = {path.stem.lower() for path in folder.glob("*.py")}
        if set(_CLASSIC_STAGES).issubset(stages):
            family = "A-D"
            selected = _CLASSIC_STAGES
        elif set(_T_STAGES).issubset(stages):
            family = "T-HT"
            selected = _T_STAGES
        else:
            continue
        return {
            "folder": folder.name,
            "script_family": family,
            "script_count": len(selected),
            "scripts": list(selected),
        }
    raise AssertionError("no complete A-D/SP event script family is available")


def _guard_order(alas_root: Path) -> Mapping[str, object]:
    run = (alas_root / "module" / "campaign" / "run.py").read_text(encoding="utf-8")
    abcd = (alas_root / "module" / "event" / "campaign_abcd.py").read_text(encoding="utf-8")
    sp = (alas_root / "module" / "event" / "campaign_sp.py").read_text(encoding="utf-8")
    present = "_validate_event_shared_entry_config" in run
    if present:
        run_section = run[run.index("    def run(self, name") :]
        if not (
            run_section.index("self._validate_main_stop_condition_config()")
            < run_section.index("self._validate_event_shared_entry_config(name, folder, mode)")
            < run_section.index("self._validate_campaign_switch_config()")
            < run_section.index("semantic_adapter = getattr")
        ):
            raise AssertionError("CampaignRun event-entry guard ordering drifted")
        if not (
            abcd.index("validate_alas_event_shared_entry_config")
            < abcd.index("os.listdir")
        ):
            raise AssertionError("CampaignABCD guard must precede directory enumeration")
        if not (
            sp.index("validate_alas_event_shared_entry_config")
            < sp.index("os.path.exists")
        ):
            raise AssertionError("CampaignSP guard must precede path probing")
    return {
        "runtime_guard_present": present,
        "before_semantic_scope": present,
        "before_daily_directory_enumeration": present,
        "before_sp_path_probe": present,
    }


def verify_event_shared_entry(alas_root: Path) -> Mapping[str, object]:
    alas_root = alas_root.resolve()
    args_path = alas_root / "module" / "config" / "argument" / "args.json"
    template_path = alas_root / "config" / "template.json"
    alas_path = alas_root / "alas.py"
    arguments = json.loads(args_path.read_text(encoding="utf-8"))
    template = json.loads(template_path.read_text(encoding="utf-8"))
    tree = ast.parse(alas_path.read_text(encoding="utf-8"), filename=str(alas_path))

    reference_args = _normalized_panel(arguments["Event"])
    reference_template = _normalized_template(template["Event"])
    panels: dict[str, Mapping[str, object]] = {}
    for task in EVENT_COMMANDS:
        groups = tuple(arguments[task])
        expected_groups = (
            EVENT_SHARED_GROUPS[:1] + ("EventDaily",) + EVENT_SHARED_GROUPS[1:]
            if task in EVENT_DAILY_COMMANDS
            else EVENT_SHARED_GROUPS
        )
        if groups != expected_groups:
            raise AssertionError(task + " group order drifted")
        if _normalized_panel(arguments[task]) != reference_args:
            raise AssertionError(task + " base argument surface diverged")
        if _normalized_template(template[task]) != reference_template:
            raise AssertionError(task + " base template surface diverged")
        field_count = sum(len(group) for group in arguments[task].values())
        panels[task] = {"group_count": len(groups), "field_count": field_count}

    if len({_normalized_method(_method(tree, name)) for name in ("event", "event2")}) != 1:
        raise AssertionError("Event/Event2 dispatch wrappers diverged")
    if len({_normalized_method(_method(tree, name)) for name in ("event_a", "event_b", "event_c", "event_d")}) != 1:
        raise AssertionError("EventA-D dispatch wrappers diverged")
    dispatches = _execute_wrappers(tree)
    accepted, rejected = _contract_cases()
    return {
        "schema": SCHEMA,
        "passed": True,
        "tasks": list(EVENT_COMMANDS),
        "shared_group_count": len(EVENT_SHARED_GROUPS),
        "shared_field_count": 54,
        "panel_field_instance_count": sum(item["field_count"] for item in panels.values()),
        "panels": panels,
        "intentional_differences": [
            "Scheduler.Command",
            "Scheduler.SuccessInterval and FailureInterval",
            "Campaign.Name value and display",
            "Campaign.Use2xBook display",
            "five StopCondition display flags",
            "EventSp Submarine.AutoSearchMode display",
            "EventDaily presence and A-D defaults",
        ],
        "dispatches": dispatches,
        "accepted_entry_rows": accepted,
        "rejected_entry_rows": rejected,
        "event_inventory": _event_inventory(alas_root),
        "guard_order": _guard_order(alas_root),
        "source_sha256": {
            "args": _sha256(args_path),
            "template": _sha256(template_path),
            "alas": _sha256(alas_path),
            "run": _sha256(alas_root / "module" / "campaign" / "run.py"),
            "campaign_abcd": _sha256(alas_root / "module" / "event" / "campaign_abcd.py"),
            "campaign_sp": _sha256(alas_root / "module" / "event" / "campaign_sp.py"),
        },
        "mutation_budget": 0,
        "android_input_injected": False,
    }


__all__ = ("SCHEMA", "verify_event_shared_entry")
