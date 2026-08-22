"""Deterministic replay of EventA-D stage rotation configuration."""

from __future__ import annotations

import ast
import hashlib
import importlib
import itertools
import json
import sys
from contextlib import nullcontext
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_event_daily_config_contract import (
    EVENT_DAILY_COMMANDS,
    validate_alas_event_daily_last_stage,
    validate_alas_event_daily_stage_filter,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.event-daily-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> dict[str, str]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    defaults: dict[str, str] = {}
    for command in EVENT_DAILY_COMMANDS:
        panel = document.get(command)
        group = panel.get("EventDaily") if isinstance(panel, dict) else None
        if not isinstance(group, dict) or set(group) != {"StageFilter", "LastStage"}:
            raise AssertionError(f"{command} EventDaily surface drifted")
        stage_filter = group["StageFilter"]
        last_stage = group["LastStage"]
        if stage_filter.get("type") != "textarea" or last_stage.get("type") != "input":
            raise AssertionError(f"{command} EventDaily field type drifted")
        expected = " > ".join(f"{command[-1]}{number}" for number in range(1, 4))
        if stage_filter.get("value") != expected or last_stage.get("value") != 0:
            raise AssertionError(f"{command} EventDaily defaults drifted")
        defaults[command] = expected
    return defaults


def _verify_consumers(path: Path) -> dict[str, list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    campaign = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CampaignABCD"
    )
    run = next(
        node for node in campaign.body if isinstance(node, ast.FunctionDef) and node.name == "run"
    )
    attributes = {
        node.attr for node in ast.walk(run) if isinstance(node, ast.Attribute)
    }
    if "EventDaily_StageFilter" not in attributes or "EventDaily_LastStage" not in attributes:
        raise AssertionError("EventDaily runtime consumer surface drifted")
    calls = {
        node.func.id
        for node in ast.walk(run)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return {
        "EventDaily.StageFilter": ["CampaignABCD.run"],
        "EventDaily.LastStage": ["CampaignABCD.run"],
        "patched_guards": sorted(
            calls
            & {
                "validate_alas_event_daily_stage_filter",
                "validate_alas_event_daily_last_stage",
            }
        ),
    }


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.event.campaign_abcd")
        base = importlib.import_module("module.event.base")
        return module, base, module.CampaignABCD
    finally:
        sys.path.remove(root)


class ReplayStop(Exception):
    pass


class ReplayConfig:
    def __init__(
        self,
        *,
        command: str,
        stage_filter: object,
        last_stage: object,
        next_run: datetime,
    ):
        self.Campaign_Name = "dynamic"
        self.Campaign_Event = "event_20260813_cn"
        self.Campaign_Mode = "normal"
        self.EventDaily_StageFilter = stage_filter
        self.EventDaily_LastStage = last_stage
        self.Scheduler_Command = command
        self.Scheduler_Enable = True
        self.Scheduler_NextRun = next_run
        self.Scheduler_ServerUpdate = "00:00"
        self.task = SimpleNamespace(command=command)
        self.events: list[tuple[object, ...]] = []

    def task_delay(self, **kwargs: object) -> None:
        self.events.append(("delay", tuple(sorted(kwargs.items()))))

    def task_stop(self) -> None:
        self.events.append(("stop",))
        raise ReplayStop

    @staticmethod
    def task_switched() -> bool:
        return False

    @staticmethod
    def multi_set():
        return nullcontext()


def _run_case(
    module: Any,
    base: Any,
    campaign_type: type[Any],
    *,
    command: str,
    stage_filter: object,
    last_stage: object = 0,
    files: tuple[str, ...] | None = None,
    outdated: bool = False,
    run_outcome: str = "success",
) -> dict[str, Any]:
    prefix = command[-1].lower()
    if files is None:
        files = tuple(f"{prefix}{number}.py" for number in range(1, 4))
    last_update = datetime(2026, 8, 15, 0, 0, 0)
    next_run = datetime(2026, 8, 14 if outdated else 16, 12, 0, 0)
    config = ReplayConfig(
        command=command,
        stage_filter=stage_filter,
        last_stage=last_stage,
        next_run=next_run,
    )
    host = object.__new__(campaign_type)
    host.config = config
    host.run_count = 1
    host.handle_stage_name = lambda name, folder: (str(name).lower(), "normal")
    runs: list[str] = []

    old_listdir = module.os.listdir
    old_last_update = module.get_server_last_update
    old_run = base.EventBase.run

    def run_stage(self: object, *, name: str, folder: str, total: int) -> None:
        runs.append(name)
        if run_outcome == "task_end":
            raise module.TaskEnd
        if run_outcome == "campaign_name_error":
            raise module.ScriptEnd("Campaign name error")

    module.os.listdir = lambda path: list(files)
    module.get_server_last_update = lambda server_update: last_update
    base.EventBase.run = run_stage
    outcome = "returned"
    try:
        campaign_type.run(host)
    except ReplayStop:
        outcome = "stopped"
    except module.RequestHumanTakeover:
        outcome = "human_takeover"
    finally:
        module.os.listdir = old_listdir
        module.get_server_last_update = old_last_update
        base.EventBase.run = old_run
    return {
        "outcome": outcome,
        "runs": runs,
        "last_stage": config.EventDaily_LastStage,
        "scheduler_enabled": config.Scheduler_Enable,
        "events": config.events,
    }


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for command in EVENT_DAILY_COMMANDS:
        prefix = command[-1]
        stages = tuple(f"{prefix}{number}" for number in range(1, 4))
        for length in range(1, 4):
            for tokens in itertools.permutations(stages, length):
                validate_alas_event_daily_stage_filter(
                    " > ".join(tokens), task_command=command
                )
                accepted += 1
        validate_alas_event_daily_stage_filter(
            f"{prefix}1 ＞ {prefix}2", task_command=command
        )
        accepted += 1
        for value in (0, f"{prefix}1", f" {prefix.lower()}3 "):
            validate_alas_event_daily_last_stage(value, task_command=command)
            accepted += 1
        wrong = "B" if prefix != "B" else "A"
        for value in (
            "",
            f"{prefix}1 >> {prefix}2",
            f"{prefix}1 > {prefix}1",
            f"{prefix}4",
            f"{wrong}1",
            f"{prefix}1junk",
            None,
        ):
            try:
                validate_alas_event_daily_stage_filter(value, task_command=command)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError("invalid EventDaily.StageFilter was admitted")
        for value in (1, "0", f"{prefix}4", f"{wrong}1", None):
            try:
                validate_alas_event_daily_last_stage(value, task_command=command)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError("invalid EventDaily.LastStage was admitted")
    return accepted, invalid


def _verify_original(module: Any, base: Any, campaign_type: type[Any]) -> dict[str, Any]:
    cases: dict[str, Any] = {}
    for command in EVENT_DAILY_COMMANDS:
        prefix = command[-1]
        cases[f"{command}_priority"] = _run_case(
            module,
            base,
            campaign_type,
            command=command,
            stage_filter=f"{prefix}2 > {prefix}1 > {prefix}3",
        )
        if cases[f"{command}_priority"]["runs"] != [
            f"{prefix.lower()}2",
            f"{prefix.lower()}1",
            f"{prefix.lower()}3",
        ]:
            raise AssertionError("EventDaily priority order drifted")
    cases["resume"] = _run_case(
        module,
        base,
        campaign_type,
        command="EventA",
        stage_filter="A2 > A1 > A3",
        last_stage="A1",
    )
    if cases["resume"]["runs"] != ["a3"]:
        raise AssertionError("EventDaily LastStage resume drifted")
    cases["filtered_cursor"] = _run_case(
        module,
        base,
        campaign_type,
        command="EventA",
        stage_filter="A1 > A3",
        last_stage="A2",
    )
    if cases["filtered_cursor"]["runs"] != ["a1", "a3"]:
        raise AssertionError("filtered LastStage restart drifted")
    cases["outdated_invalid_cursor"] = _run_case(
        module,
        base,
        campaign_type,
        command="EventA",
        stage_filter="A1 > A2",
        last_stage="B9",
        outdated=True,
    )
    if cases["outdated_invalid_cursor"]["runs"] != ["a1", "a2"]:
        raise AssertionError("outdated LastStage reset drifted")
    cases["missing_script"] = _run_case(
        module,
        base,
        campaign_type,
        command="EventA",
        stage_filter="A1 > A2 > A3",
        files=("a1.py", "a3.py"),
    )
    if cases["missing_script"]["runs"] != ["a1", "a3"]:
        raise AssertionError("missing EventDaily script filter drifted")
    cases["no_match"] = _run_case(
        module,
        base,
        campaign_type,
        command="EventA",
        stage_filter="A1 > A2",
        files=("sp.py",),
    )
    if cases["no_match"]["outcome"] != "stopped" or cases["no_match"][
        "scheduler_enabled"
    ]:
        raise AssertionError("no-match EventDaily stop drifted")
    cases["task_switch"] = _run_case(
        module,
        base,
        campaign_type,
        command="EventA",
        stage_filter="A1",
        run_outcome="task_end",
    )
    if cases["task_switch"]["runs"] != ["a1"]:
        raise AssertionError("EventDaily TaskEnd catch drifted")
    cases["locked_stage"] = _run_case(
        module,
        base,
        campaign_type,
        command="EventA",
        stage_filter="A1",
        run_outcome="campaign_name_error",
    )
    if cases["locked_stage"]["outcome"] != "human_takeover":
        raise AssertionError("locked EventDaily stage did not request takeover")

    source = Path(module.__file__).read_text(encoding="utf-8")
    patched = "validate_alas_event_daily_stage_filter" in source
    if patched:
        for field, value in (
            ("EventDaily_StageFilter", "A1junk"),
            ("EventDaily_LastStage", "B1"),
        ):
            kwargs = {
                "command": "EventA",
                "stage_filter": "A1",
                "last_stage": 0,
            }
            if field == "EventDaily_StageFilter":
                kwargs["stage_filter"] = value
            else:
                kwargs["last_stage"] = value
            try:
                _run_case(module, base, campaign_type, **kwargs)
            except SemanticGateClosed:
                pass
            else:
                raise AssertionError(f"patched {field} guard admitted invalid value")
    return {"cases": cases, "patched_guard_present": patched}


def verify_event_daily_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    defaults = _verify_args(alas_root)
    source = alas_root / "module" / "event" / "campaign_abcd.py"
    consumers = _verify_consumers(source)
    module, base, campaign_type = _load_original(alas_root)
    accepted, invalid = _verify_contract()
    original = _verify_original(module, base, campaign_type)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "panel_count": 4,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "defaults": defaults,
        "runtime_consumers": consumers,
        "original_decisions": original,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "campaign_abcd": _sha256(source),
        },
    }
