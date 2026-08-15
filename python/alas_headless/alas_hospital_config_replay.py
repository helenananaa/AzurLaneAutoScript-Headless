"""Deterministic recorder-only replay for the pinned Hospital fleet setting."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .alas_hospital_config_contract import validate_alas_hospital_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.hospital-config-replay/v1"


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
    arguments = json.loads(args_path.read_text(encoding="utf-8"))
    template = json.loads(template_path.read_text(encoding="utf-8"))
    task = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    if arguments.get("Hospital", {}).get("Hospital") != {
        "UseRecommendFleet": {"type": "checkbox", "value": True}
    }:
        raise AssertionError("Hospital argument declaration drifted")
    if template.get("Hospital", {}).get("Hospital") != {"UseRecommendFleet": True}:
        raise AssertionError("Hospital template declaration drifted")
    task_groups = [
        item["tasks"]["Hospital"]
        for item in task.values()
        if isinstance(item, dict) and "Hospital" in item.get("tasks", {})
    ]
    if task_groups != [["Scheduler", "Hospital", "StopCondition", "Emotion"]]:
        raise AssertionError("Hospital task group declaration drifted")
    tree = ast.parse(generated_path.read_text(encoding="utf-8"), filename=str(generated_path))
    defaults = [
        ast.literal_eval(node.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "Hospital_UseRecommendFleet"
            for target in node.targets
        )
    ]
    if defaults != [True]:
        raise AssertionError("Hospital generated default drifted")


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
        isinstance(first, (ast.Assign, ast.Expr))
        and isinstance(first.value, ast.Call)
        and isinstance(first.value.func, ast.Name)
        and first.value.func.id == "validate_alas_hospital_config"
    )


def _verify_consumers(alas_root: Path) -> tuple[dict[str, list[str]], bool]:
    combat_path = alas_root / "module/event_hospital/combat.py"
    hospital_path = alas_root / "module/event_hospital/hospital.py"
    preparation = _method(combat_path, "HospitalCombat", "combat_preparation")
    run = _method(hospital_path, "Hospital", "run")
    reads = sum(
        1
        for method in (preparation, run)
        for node in ast.walk(method)
        if isinstance(node, ast.Attribute) and node.attr == "Hospital_UseRecommendFleet"
    )
    guards = sum(
        1
        for method in (preparation, run)
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_hospital_config"
    )
    patched = _first_guard(preparation) and _first_guard(run)
    if patched and (reads != 2 or guards != 2):
        raise AssertionError("Hospital direct configuration reads are not fully guarded")
    return {"Hospital_UseRecommendFleet": ["Hospital.run", "HospitalCombat.combat_preparation"]}, patched


class _Logger:
    def info(self, *_args: object, **_kwargs: object) -> None:
        return None

    def error(self, *_args: object, **_kwargs: object) -> None:
        return None

    def hr(self, *_args: object, **_kwargs: object) -> None:
        return None


def _compile_recommend(method: ast.FunctionDef):
    class_node = ast.ClassDef(
        name="HospitalRecommendReplay", bases=[], keywords=[], body=[method], decorator_list=[]
    )
    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)
    events: list[str] = []

    class _Takeover(Exception):
        pass

    def fleet_operator(**_kwargs: object):
        class _Fleet:
            def in_use(self) -> bool:
                return fleet_operator.in_use

            def recommend(self) -> None:
                events.append("recommend")

        return _Fleet()

    fleet_operator.in_use = False
    namespace: dict[str, Any] = {
        "FLEET_1_CHOOSE": object(),
        "FLEET_1_ADVICE": object(),
        "FLEET_1_BAR": object(),
        "FLEET_1_CLEAR": object(),
        "FLEET_1_IN_USE": object(),
        "FLEET_1_HARD_SATIESFIED": object(),
        "FleetOperator": fleet_operator,
        "RequestHumanTakeover": _Takeover,
        "logger": _Logger(),
    }
    exec(compile(module, "<alas-hospital-recommend>", "exec"), namespace)
    return namespace["HospitalRecommendReplay"], fleet_operator, _Takeover, events


def _compile_preparation(method: ast.FunctionDef):
    class_node = ast.ClassDef(
        name="HospitalPreparationReplay", bases=[], keywords=[], body=[method], decorator_list=[]
    )
    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)
    raid_preparation = object()
    namespace: dict[str, Any] = {
        "BATTLE_PREPARATION": object(),
        "RAID_FLEET_PREPARATION": raid_preparation,
        "HOSPITAL_BATTLE_PREPARE": object(),
        "OilExhausted": RuntimeError,
        "logger": _Logger(),
        "run_once": lambda function: function,
        "validate_alas_hospital_config": validate_alas_hospital_config,
    }
    exec(compile(module, "<alas-hospital-preparation>", "exec"), namespace)
    return namespace["HospitalPreparationReplay"], raid_preparation


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for value in (False, True):
        snapshot = validate_alas_hospital_config(use_recommend_fleet=value)
        if snapshot.use_recommend_fleet is not value:
            raise AssertionError("Hospital boolean snapshot drifted")
        accepted += 1
    for value in (None, 0, 1, "true", "false", [], {}):
        try:
            validate_alas_hospital_config(use_recommend_fleet=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Hospital.UseRecommendFleet was admitted")
    return accepted, invalid


def _verify_recommend(method: ast.FunctionDef) -> dict[str, object]:
    replay_type, factory, takeover, events = _compile_recommend(method)
    host = replay_type()
    factory.in_use = True
    if host.handle_fleet_recommend(recommend=True) is not False or events:
        raise AssertionError("in-use Hospital fleet path drifted")
    factory.in_use = False
    if host.handle_fleet_recommend(recommend=True) is not True or events != ["recommend"]:
        raise AssertionError("enabled Hospital recommendation path drifted")
    try:
        host.handle_fleet_recommend(recommend=False)
    except takeover:
        pass
    else:
        raise AssertionError("disabled Hospital recommendation did not stop")
    if events != ["recommend"]:
        raise AssertionError("disabled Hospital recommendation crossed final input boundary")
    return {"in_use": False, "enabled_recommend_calls": 1, "disabled_stopped": True}


def _preparation_case(
    replay_type: type[Any], raid_preparation: object, *, value: object
) -> list[object]:
    host = replay_type()
    events: list[object] = []
    host.config = type(
        "Config", (), {"Hospital_UseRecommendFleet": value, "StopCondition_OilLimit": 1000}
    )()
    host.loop = lambda: iter((None,))
    host.appear = lambda target, **_kwargs: target is raid_preparation
    host.appear_then_click = lambda *_args, **_kwargs: False
    host.handle_retirement = lambda: False
    host.handle_combat_low_emotion = lambda: False
    host.handle_combat_automation_set = lambda **_kwargs: False
    host.handle_combat_automation_confirm = lambda: False
    host.handle_story_skip = lambda: False
    host.handle_fleet_recommend = lambda *, recommend: events.append(("recommend", recommend)) or True
    host.interval_clear = lambda target: events.append(("interval_clear", target is raid_preparation))
    host.device = type("Device", (), {"click": lambda *_args: events.append("click")})()
    try:
        host.combat_preparation()
    except SemanticGateClosed:
        return events
    if type(value) is not bool:
        raise AssertionError("invalid Hospital config entered combat preparation")
    return events


def verify_hospital_config(alas_root: Path) -> dict[str, object]:
    """Verify the pinned Hospital setting without pixels, inputs, or mutations."""

    alas_root = alas_root.resolve()
    _verify_declarations(alas_root)
    consumers, patched = _verify_consumers(alas_root)
    combat_path = alas_root / "module/event_hospital/combat.py"
    preparation = _method(combat_path, "HospitalCombat", "combat_preparation")
    recommend = _method(combat_path, "HospitalCombat", "handle_fleet_recommend")
    accepted, invalid = _verify_contract()
    decisions = _verify_recommend(recommend)
    replay_type, raid_preparation = _compile_preparation(preparation)
    entry_events: dict[str, list[object]] = {}
    if patched:
        entry_events = {
            "enabled": _preparation_case(replay_type, raid_preparation, value=True),
            "disabled": _preparation_case(replay_type, raid_preparation, value=False),
            "invalid": _preparation_case(replay_type, raid_preparation, value=0),
        }
        if entry_events["enabled"] != [("recommend", True), ("interval_clear", True)]:
            raise AssertionError("enabled Hospital dispatcher drifted")
        if entry_events["disabled"] != [("recommend", False), ("interval_clear", True)]:
            raise AssertionError("disabled Hospital dispatcher drifted")
        if entry_events["invalid"]:
            raise AssertionError("invalid Hospital config crossed combat preparation")
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "runtime_consumers": consumers,
        "patched_guard_present": patched,
        "original_decisions": decisions,
        "entry_events": entry_events,
        "mutation_budget": 0,
        "fleet_recommend_actions": 0,
        "android_input_injected": False,
        "source_sha256": {
            "task": _sha256(alas_root / "module/config/argument/task.yaml"),
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "template": _sha256(alas_root / "config/template.json"),
            "generated": _sha256(alas_root / "module/config/config_generated.py"),
            "combat": _sha256(combat_path),
            "hospital": _sha256(alas_root / "module/event_hospital/hospital.py"),
        },
    }
