"""Deterministic recorder-only replay for pinned ALAS Coalition settings."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .alas_coalition_config_contract import (
    COALITION_FLEETS,
    COALITION_MODES,
    validate_alas_coalition_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.coalition-config-replay/v1"


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
    args = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    template = json.loads((alas_root / "config/template.json").read_text(encoding="utf-8"))
    task = yaml.safe_load(
        (alas_root / "module/config/argument/task.yaml").read_text(encoding="utf-8")
    )
    expected = {
        "Mode": {
            "type": "select",
            "value": "hard",
            "option": ["easy", "normal", "hard", "sp"],
        },
        "Fleet": {"type": "select", "value": "single", "option": ["single", "multi"]},
    }
    if args.get("Coalition", {}).get("Coalition") != expected:
        raise AssertionError("Coalition argument declaration drifted")
    sp_expected = dict(expected)
    sp_expected["Mode"] = dict(expected["Mode"], value="sp", display="hide")
    if args.get("CoalitionSp", {}).get("Coalition") != sp_expected:
        raise AssertionError("CoalitionSp argument declaration drifted")
    if template.get("Coalition", {}).get("Coalition") != {
        "Mode": "hard",
        "Fleet": "single",
    } or template.get("CoalitionSp", {}).get("Coalition") != {
        "Mode": "sp",
        "Fleet": "single",
    }:
        raise AssertionError("Coalition template declaration drifted")
    panels = {
        name: section["tasks"][name]
        for section in task.values()
        if isinstance(section, dict)
        for name in ("Coalition", "CoalitionSp")
        if name in section.get("tasks", {})
    }
    expected_groups = ["Scheduler", "Campaign", "Coalition", "StopCondition", "Emotion"]
    if panels != {"Coalition": expected_groups, "CoalitionSp": expected_groups}:
        raise AssertionError("Coalition task group declarations drifted")
    tree = ast.parse(
        (alas_root / "module/config/config_generated.py").read_text(encoding="utf-8")
    )
    defaults = {
        target.id: ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and target.id in {"Coalition_Mode", "Coalition_Fleet"}
    }
    if defaults != {"Coalition_Mode": "hard", "Coalition_Fleet": "single"}:
        raise AssertionError("Coalition generated defaults drifted")


def _first_guard(method: ast.FunctionDef) -> bool:
    executable = [
        statement
        for statement in method.body
        if not (
            isinstance(statement, ast.Expr)
            and isinstance(statement.value, ast.Constant)
            and isinstance(statement.value.value, str)
        )
    ]
    first = executable[0] if executable else None
    return (
        isinstance(first, ast.Assign)
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "validate_alas_coalition_config"
    )


def _verify_consumers(alas_root: Path) -> tuple[dict[str, list[str]], bool]:
    coalition_path = alas_root / "module/coalition/coalition.py"
    combat_path = alas_root / "module/coalition/combat.py"
    execute = _method(coalition_path, "Coalition", "coalition_execute_once")
    run = _method(coalition_path, "Coalition", "run")
    combat = _method(combat_path, "CoalitionCombat", "coalition_combat")
    methods = (execute, run, combat)
    attributes = {
        node.attr
        for method in methods
        for node in ast.walk(method)
        if isinstance(node, ast.Attribute)
    }
    if not {"Coalition_Mode", "Coalition_Fleet"}.issubset(attributes):
        raise AssertionError("Coalition configuration consumer surface drifted")
    guards = sum(
        1
        for method in methods
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_coalition_config"
    )
    patched = all(_first_guard(method) for method in methods)
    if patched and guards != 3:
        raise AssertionError("Coalition direct configuration reads are not fully guarded")
    return {
        "Coalition.Mode": ["Coalition.run", "Coalition.coalition_execute_once", "CoalitionCombat.coalition_combat"],
        "Coalition.Fleet": ["Coalition.run", "Coalition.coalition_execute_once", "CoalitionCombat.coalition_combat"],
    }, patched


class _Logger:
    def info(self, *_args: object, **_kwargs: object) -> None:
        return None

    def warning(self, *_args: object, **_kwargs: object) -> None:
        return None

    def hr(self, *_args: object, **_kwargs: object) -> None:
        return None


class _Stop(RuntimeError):
    pass


class _CampaignEnd(RuntimeError):
    pass


def _compile(method: ast.FunctionDef, *, name: str, namespace: dict[str, Any]) -> type[Any]:
    class_node = ast.ClassDef(name=name, bases=[], keywords=[], body=[method], decorator_list=[])
    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<alas-coalition-replay>", "exec"), namespace)
    return namespace[name]


class _Config:
    def __init__(self, *, mode: object, fleet: object):
        self.Coalition_Mode = mode
        self.Coalition_Fleet = fleet
        self.Campaign_Event = "coalition_fixture"
        self.Emotion_Fleet1Control = "prevent_red_face"
        self.StopCondition_RunCount = 0
        self.events: list[tuple[str, object]] = []

    def override(self, **values: object) -> None:
        self.events.append(("override", values))
        for key, value in values.items():
            setattr(self, key, value)

    def task_stop(self) -> None:
        raise _Stop("task stop")


def _contract_cases() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for mode in sorted(COALITION_MODES):
        for fleet in sorted(COALITION_FLEETS):
            snapshot = validate_alas_coalition_config(mode=mode, fleet=fleet)
            if (snapshot.mode, snapshot.fleet) != (mode, fleet):
                raise AssertionError("Coalition snapshot drifted")
            accepted += 1
    for mode in ("HARD", " hard", None, True, 0, [], {}):
        try:
            validate_alas_coalition_config(mode=mode, fleet="single")
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Coalition.Mode was admitted")
    for fleet in ("SINGLE", "single ", None, True, 0, [], {}):
        try:
            validate_alas_coalition_config(mode="hard", fleet=fleet)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Coalition.Fleet was admitted")
    return accepted, invalid


def _run_case(replay_type: type[Any], *, mode: object, fleet: object) -> list[str]:
    host = replay_type()
    host.config = _Config(mode=mode, fleet=fleet)
    events: list[str] = []
    host.handle_stage_name = (
        lambda event, stage: events.append("stage_name") or (event, stage)
    )
    host.event_time_limit_triggered = lambda: events.append("event_time_limit") or True
    try:
        host.run(event="coalition_fixture", total=1)
    except SemanticGateClosed:
        if events:
            raise AssertionError("invalid Coalition configuration reached task state")
        return events
    except _Stop:
        pass
    else:
        raise AssertionError("Coalition task stop fixture did not stop")
    return events


def _execute_case(
    replay_type: type[Any], *, mode: object, fleet: object, stage: str
) -> dict[str, object]:
    host = replay_type()
    host.config = _Config(mode=mode, fleet=fleet)
    events: list[tuple[str, object]] = []
    host._coalition_has_oil_icon = True
    host.emotion = type(
        "Emotion",
        (),
        {"check_reduce": lambda _self, *, battle: events.append(("emotion", battle))},
    )()
    host.coalition_get_battles = lambda *_args: 3
    host.triggered_stop_condition = lambda **_kwargs: events.append(("stop", None)) or False
    host.enter_map = lambda **kwargs: events.append(("enter", kwargs))
    host.coalition_combat = lambda: events.append(("combat", None))
    try:
        host.coalition_execute_once("coalition_fixture", stage, fleet)
    except SemanticGateClosed:
        if events or host.config.events:
            raise AssertionError("invalid Coalition configuration crossed a stateful boundary")
        return {"events": [], "overrides": []}
    return {"events": events, "overrides": host.config.events}


def _combat_case(replay_type: type[Any], *, mode: object, fleet: object) -> list[tuple[str, object]]:
    host = replay_type()
    host.config = _Config(mode=mode, fleet=fleet)
    host.FUNCTION_NAME_BASE = "Coalition_"
    events: list[tuple[str, object]] = []
    host.combat_preparation = lambda **_kwargs: events.append(("preparation", None))
    host.coalition_combat_re_enter = lambda: events.append(("re_enter", None))

    def auto(**kwargs: object) -> None:
        events.append(("auto", kwargs["emotion_reduce"]))
        if host.battle_count == 1:
            raise _CampaignEnd()

    host.auto_search_combat_execute = auto
    try:
        host.coalition_combat()
    except SemanticGateClosed:
        if events:
            raise AssertionError("invalid Coalition config entered combat preparation")
        return events
    return events


def verify_coalition_config(alas_root: Path) -> dict[str, object]:
    """Verify exact Coalition choices without a device, account, or input."""

    alas_root = alas_root.resolve()
    _verify_declarations(alas_root)
    consumers, patched = _verify_consumers(alas_root)
    coalition_path = alas_root / "module/coalition/coalition.py"
    combat_path = alas_root / "module/coalition/combat.py"
    run = _method(coalition_path, "Coalition", "run")
    execute = _method(coalition_path, "Coalition", "coalition_execute_once")
    combat = _method(combat_path, "CoalitionCombat", "coalition_combat")
    accepted, invalid = _contract_cases()
    run_type = _compile(
        run,
        name="CoalitionRunReplay",
        namespace={
            "ScriptError": RuntimeError,
            "logger": _Logger(),
            "validate_alas_coalition_config": validate_alas_coalition_config,
        },
    )
    execute_type = _compile(
        execute,
        name="CoalitionExecuteReplay",
        namespace={
            "ScriptEnd": _Stop,
            "logger": _Logger(),
            "validate_alas_coalition_config": validate_alas_coalition_config,
        },
    )
    combat_type = _compile(
        combat,
        name="CoalitionCombatReplay",
        namespace={
            "CampaignEnd": _CampaignEnd,
            "logger": _Logger(),
            "validate_alas_coalition_config": validate_alas_coalition_config,
        },
    )
    decisions: dict[str, object] = {}
    if patched:
        decisions = {
            "run_valid": _run_case(run_type, mode="hard", fleet="single"),
            "run_invalid": _run_case(run_type, mode="HARD", fleet="single"),
            "single_hard": _execute_case(
                execute_type, mode="hard", fleet="single", stage="hard"
            ),
            "single_sp": _execute_case(
                execute_type, mode="sp", fleet="single", stage="sp"
            ),
            "multi_hard": _execute_case(
                execute_type, mode="hard", fleet="multi", stage="hard"
            ),
            "combat_single": _combat_case(
                combat_type, mode="hard", fleet="single"
            ),
            "combat_multi": _combat_case(
                combat_type, mode="hard", fleet="multi"
            ),
            "combat_invalid": _combat_case(
                combat_type, mode="hard", fleet="invalid"
            ),
        }
        if decisions["run_valid"] != ["stage_name", "event_time_limit"] or decisions["run_invalid"]:
            raise AssertionError("Coalition.run guard order drifted")
        if decisions["single_hard"]["overrides"][1] != (
            "override",
            {"Emotion_Fleet1Control": "prevent_yellow_face"},
        ):
            raise AssertionError("single Coalition emotion override drifted")
        if decisions["single_sp"]["overrides"][2] != (
            "override",
            {"Coalition_Fleet": "multi"},
        ):
            raise AssertionError("SP Coalition fleet override drifted")
        if len(decisions["multi_hard"]["overrides"]) != 1:
            raise AssertionError("multi Coalition override drifted")
        if decisions["combat_single"] != [
            ("preparation", None),
            ("auto", True),
            ("re_enter", None),
            ("auto", True),
        ] or decisions["combat_multi"] != [
            ("preparation", None),
            ("auto", True),
            ("re_enter", None),
            ("auto", False),
        ] or decisions["combat_invalid"]:
            raise AssertionError("Coalition combat fleet branch drifted")
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "patched_guard_present": patched,
        "original_decisions": decisions,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "task": _sha256(alas_root / "module/config/argument/task.yaml"),
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "template": _sha256(alas_root / "config/template.json"),
            "generated": _sha256(alas_root / "module/config/config_generated.py"),
            "coalition": _sha256(coalition_path),
            "combat": _sha256(combat_path),
        },
    }
