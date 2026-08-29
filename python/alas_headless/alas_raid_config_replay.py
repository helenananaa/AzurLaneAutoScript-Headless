"""Deterministic recorder-only replay of pinned Raid configuration decisions."""

from __future__ import annotations

import ast
import hashlib
import itertools
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

from .alas_raid_config_contract import (
    RAID_DAILY_STAGES,
    RAID_MODES,
    validate_alas_raid_daily_stage_filter,
    validate_alas_raid_mode,
    validate_alas_raid_use_ticket,
)
from .alas_reward_config_contract import validate_alas_reward_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.raid-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path, owner_name: str, method_name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner_name
    )
    return next(
        node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name == method_name
    )


def _verify_declarations(alas_root: Path) -> None:
    args_path = alas_root / "module/config/argument/args.json"
    template_path = alas_root / "config/template.json"
    task_path = alas_root / "module/config/argument/task.yaml"
    generated_path = alas_root / "module/config/config_generated.py"
    args = json.loads(args_path.read_text(encoding="utf-8"))
    template = json.loads(template_path.read_text(encoding="utf-8"))
    task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    if args.get("Raid", {}).get("Raid") != {
        "Mode": {"type": "select", "value": "hard", "option": ["easy", "normal", "hard", "ex"]},
        "UseTicket": {"type": "checkbox", "value": False},
    }:
        raise AssertionError("Raid argument declaration drifted")
    if args.get("RaidDaily", {}).get("RaidDaily") != {
        "StageFilter": {"type": "textarea", "value": "hard > normal > easy"}
    }:
        raise AssertionError("RaidDaily argument declaration drifted")
    if template.get("Raid", {}).get("Raid") != {"Mode": "hard", "UseTicket": False}:
        raise AssertionError("Raid template declaration drifted")
    if template.get("RaidDaily", {}).get("RaidDaily") != {"StageFilter": "hard > normal > easy"}:
        raise AssertionError("RaidDaily template declaration drifted")
    groups = {
        name: item["tasks"][name]
        for item in task.values()
        if isinstance(item, dict)
        for name in ("Raid", "RaidDaily")
        if name in item.get("tasks", {})
    }
    if groups != {
        "Raid": ["Scheduler", "Raid", "Campaign", "StopCondition", "Emotion"],
        "RaidDaily": ["Scheduler", "RaidDaily", "Campaign", "StopCondition", "Emotion"],
    }:
        raise AssertionError("Raid task group declarations drifted")
    tree = ast.parse(generated_path.read_text(encoding="utf-8"), filename=str(generated_path))
    defaults = {
        target.id: ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id in {"Raid_Mode", "Raid_UseTicket", "RaidDaily_StageFilter"}
    }
    if defaults != {
        "Raid_Mode": "hard",
        "Raid_UseTicket": False,
        "RaidDaily_StageFilter": "hard > normal > easy",
    }:
        raise AssertionError("Raid generated defaults drifted")


def _first_guard(method: ast.FunctionDef, name: str) -> bool:
    executable = [
        statement
        for statement in method.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    return any(
        isinstance(statement, (ast.Assign, ast.Expr))
        and isinstance(statement.value, ast.Call)
        and isinstance(statement.value.func, ast.Name)
        and statement.value.func.id == name
        for statement in executable[:2]
    )


def _verify_consumers(alas_root: Path) -> tuple[dict[str, list[str]], bool]:
    run = _method(alas_root / "module/raid/run.py", "RaidRun", "run")
    ticket = _method(alas_root / "module/raid/raid.py", "Raid", "handle_raid_ticket_use")
    daily = _method(alas_root / "module/raid/daily.py", "RaidDaily", "run")
    attributes = {
        node.attr
        for method in (run, ticket, daily)
        for node in ast.walk(method)
        if isinstance(node, ast.Attribute)
    }
    expected = {"Raid_Mode", "Raid_UseTicket", "RaidDaily_StageFilter"}
    if not expected.issubset(attributes):
        raise AssertionError("Raid configuration consumer surface drifted")
    calls = {
        node.func.id
        for method in (run, ticket, daily)
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    patched = {
        "validate_alas_raid_mode",
        "validate_alas_raid_use_ticket",
        "validate_alas_raid_daily_stage_filter",
    }.issubset(calls)
    if patched and not (
        _first_guard(run, "validate_alas_raid_mode")
        and _first_guard(ticket, "validate_alas_raid_use_ticket")
        and _first_guard(daily, "validate_alas_raid_daily_stage_filter")
    ):
        raise AssertionError("Raid guards are not before their stateful entries")
    return {
        "Raid.Mode": ["RaidRun.run"],
        "Raid.UseTicket": ["RaidRun.run", "Raid.handle_raid_ticket_use"],
        "RaidDaily.StageFilter": ["RaidDaily.run"],
    }, patched


class _Logger:
    def info(self, *_args: object, **_kwargs: object) -> None:
        return None

    def hr(self, *_args: object, **_kwargs: object) -> None:
        return None


def _compile_ticket(method: ast.FunctionDef):
    class_node = ast.ClassDef(name="RaidTicketReplay", bases=[], keywords=[], body=[method], decorator_list=[])
    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)
    confirm, cancel = object(), object()
    namespace: dict[str, Any] = {
        "TICKET_USE_CONFIRM": confirm,
        "TICKET_USE_CANCEL": cancel,
        "validate_alas_raid_use_ticket": validate_alas_raid_use_ticket,
    }
    exec(compile(module, "<alas-raid-ticket>", "exec"), namespace)
    return namespace["RaidTicketReplay"], confirm, cancel


def _compile_daily(method: ast.FunctionDef):
    class _Parent:
        def run(self, **kwargs: object) -> None:
            self.events.append(("raid_run", kwargs))

    class_node = ast.ClassDef(
        name="RaidDailyReplay",
        bases=[ast.Name(id="Parent", ctx=ast.Load())],
        keywords=[],
        body=[method],
        decorator_list=[],
    )
    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)

    class _Stage:
        def __init__(self, name: str):
            self.name = name

    namespace: dict[str, Any] = {
        "Parent": _Parent,
        "RaidStage": _Stage,
        "STAGES": ["easy", "normal", "hard"],
        "page_raid": object(),
        "logger": _Logger(),
        "validate_alas_raid_daily_stage_filter": validate_alas_raid_daily_stage_filter,
        "validate_alas_reward_config": validate_alas_reward_config,
    }
    exec(compile(module, "<alas-raid-daily>", "exec"), namespace)
    return namespace["RaidDailyReplay"], _Stage, namespace


class _DailyConfig:
    def __init__(self, stage_filter: object):
        self.RaidDaily_StageFilter = stage_filter
        self.Campaign_Event = "raid_fixture"
        self.Raid_Mode = "hard"
        self.Raid_UseTicket = False
        self.Reward_CollectOil = True
        self.Reward_CollectCoin = True
        self.Reward_CollectExp = True
        self.Reward_CollectMission = True
        self.Reward_CollectWeeklyMission = True
        self.events: list[tuple[str, dict[str, object]]] = []

    def task_delay(self, **kwargs: object) -> None:
        self.events.append(("task_delay", kwargs))

    def task_stop(self) -> None:
        self.events.append(("task_stop", {}))


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for mode in sorted(RAID_MODES):
        if validate_alas_raid_mode(mode) != mode:
            raise AssertionError("Raid.Mode snapshot drifted")
        accepted += 1
    for value in (False, True):
        if validate_alas_raid_use_ticket(value) is not value:
            raise AssertionError("Raid.UseTicket snapshot drifted")
        accepted += 1
    permutations = []
    for size in range(1, len(RAID_DAILY_STAGES) + 1):
        permutations.extend(itertools.permutations(sorted(RAID_DAILY_STAGES), size))
    for tokens in permutations:
        canonical = validate_alas_raid_daily_stage_filter(" > ".join(tokens))
        if canonical != " > ".join(tokens):
            raise AssertionError("RaidDaily stage ordering drifted")
        accepted += 1
    for value in ("", "hard >> easy", "hard > hard", "impossible", "hard > impossible", None, True, 0):
        try:
            validate_alas_raid_daily_stage_filter(value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid RaidDaily.StageFilter was admitted")
    for value in ("HARD", "hard ", None, True, 0, [], {}):
        try:
            validate_alas_raid_mode(value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Raid.Mode was admitted")
    for value in (None, 0, 1, "true", [], {}):
        try:
            validate_alas_raid_use_ticket(value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Raid.UseTicket was admitted")
    return accepted, invalid


def _ticket_case(ticket_type: type[Any], confirm: object, cancel: object, *, use_ticket: object) -> list[str]:
    host = ticket_type()
    events: list[str] = []
    host.config = SimpleNamespace(Raid_UseTicket=use_ticket)
    host.appear = lambda target, **_kwargs: events.append("appear") or target is confirm
    host.device = SimpleNamespace(
        click=lambda target: events.append("confirm" if target is confirm else "cancel")
    )
    try:
        handled = host.handle_raid_ticket_use()
    except SemanticGateClosed:
        if events:
            raise AssertionError("invalid ticket setting reached observation or input")
        return events
    if handled is not True:
        raise AssertionError("ticket confirmation fixture was not handled")
    expected = ["appear", "confirm" if use_ticket else "cancel"]
    if events != expected:
        raise AssertionError("original ticket branch drifted")
    return events


def _daily_case(
    daily_type: type[Any], stage_type: type[Any], namespace: dict[str, Any], *, stage_filter: object
) -> dict[str, object]:
    host = daily_type()
    host.config = _DailyConfig(stage_filter)
    host.events: list[tuple[str, object]] = []
    host.device = object()
    host.is_raid_rpg = lambda: host.events.append(("is_raid_rpg", None)) or False
    host.ui_ensure = lambda _page: host.events.append(("ui_ensure", None))
    host._ensure_raid_page = lambda name: host.events.append(("ensure_raid_page", name))
    host.get_remain = lambda mode: 2 if mode == "ex" else 0
    host.ui_goto_main = lambda: host.events.append(("goto_main", None))

    class _Filter:
        def load(self, value: str) -> None:
            host.events.append(("filter", value))

        def apply(self, stages: list[object]) -> list[object]:
            return stages

    class _Reward:
        def __init__(self, *_args: object):
            return None

        def reward_mission(self, **kwargs: object) -> None:
            host.events.append(("reward_mission", kwargs))

    original_filter = namespace.get("STAGE_FILTER")
    original_reward = namespace.get("Reward")
    namespace["STAGE_FILTER"] = _Filter()
    namespace["Reward"] = _Reward
    try:
        daily_type.run(host)
    except SemanticGateClosed:
        if host.events or host.config.events:
            raise AssertionError("invalid daily filter reached a RaidDaily stateful boundary")
        return {"events": [], "config_events": []}
    finally:
        if original_filter is not None:
            namespace["STAGE_FILTER"] = original_filter
        if original_reward is not None:
            namespace["Reward"] = original_reward
    return {"events": host.events, "config_events": host.config.events}


def verify_raid_config(alas_root: Path) -> dict[str, object]:
    """Verify source declarations and original branches without a real device."""

    alas_root = alas_root.resolve()
    _verify_declarations(alas_root)
    consumers, patched = _verify_consumers(alas_root)
    ticket_method = _method(alas_root / "module/raid/raid.py", "Raid", "handle_raid_ticket_use")
    daily_method = _method(alas_root / "module/raid/daily.py", "RaidDaily", "run")
    accepted, invalid = _verify_contract()
    ticket_type, confirm, cancel = _compile_ticket(ticket_method)
    ticket_decisions = {
        "enabled": _ticket_case(ticket_type, confirm, cancel, use_ticket=True),
        "disabled": _ticket_case(ticket_type, confirm, cancel, use_ticket=False),
    }
    daily_type, stage_type, namespace = _compile_daily(daily_method)
    daily_decisions: dict[str, object] = {}
    if patched:
        daily_decisions = {
            "normal": _daily_case(daily_type, stage_type, namespace, stage_filter="hard > easy"),
            "with_ex": _daily_case(daily_type, stage_type, namespace, stage_filter="hard > ex > easy"),
            "invalid": _daily_case(daily_type, stage_type, namespace, stage_filter="hard > impossible"),
        }
        if daily_decisions["normal"]["events"][:2] != [
            ("is_raid_rpg", None),
            ("filter", "hard > easy"),
        ]:
            raise AssertionError("RaidDaily normal filter forwarding drifted")
        if ("reward_mission", {"daily": True, "weekly": False}) not in daily_decisions["with_ex"]["events"]:
            raise AssertionError("RaidDaily EX reward routing drifted")
        if daily_decisions["invalid"] != {"events": [], "config_events": []}:
            raise AssertionError("invalid RaidDaily filter crossed a boundary")
        if _ticket_case(ticket_type, confirm, cancel, use_ticket=0):
            raise AssertionError("invalid Raid ticket crossed a boundary")
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "patched_guard_present": patched,
        "original_decisions": {"ticket": ticket_decisions, "daily": daily_decisions},
        "mutation_budget": 0,
        "ticket_final_input_boundaries": 2,
        "android_input_injected": False,
        "source_sha256": {
            "task": _sha256(alas_root / "module/config/argument/task.yaml"),
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "template": _sha256(alas_root / "config/template.json"),
            "generated": _sha256(alas_root / "module/config/config_generated.py"),
            "raid": _sha256(alas_root / "module/raid/raid.py"),
            "run": _sha256(alas_root / "module/raid/run.py"),
            "daily": _sha256(alas_root / "module/raid/daily.py"),
        },
    }
