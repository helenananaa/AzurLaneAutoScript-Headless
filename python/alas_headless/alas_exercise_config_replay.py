"""Deterministic replay of pinned ALAS Exercise configuration decisions."""

from __future__ import annotations

import ast
from contextlib import nullcontext
from datetime import timedelta
import hashlib
import importlib
import itertools
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_exercise_config_contract import (
    EXERCISE_OPPONENT_MODES,
    EXERCISE_STRATEGIES,
    validate_alas_exercise_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.exercise-config-replay/v1"
REPRESENTATIVE_TRIALS = (1, 2, 10, 2**31)
INVALID_ENUM_VALUES = (None, True, 1, "", "unknown", [])
INVALID_TRIAL_VALUES = (0, -1, True, 1.0, "1", None, [])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    group = document.get("Exercise", {}).get("Exercise")
    if not isinstance(group, dict):
        raise AssertionError("Exercise field surface is missing")
    expected = {
        "OpponentChooseMode": ("select", "max_exp", EXERCISE_OPPONENT_MODES),
        "OpponentTrial": ("input", 1, None),
        "ExerciseStrategy": ("select", "aggressive", EXERCISE_STRATEGIES),
    }
    for field, (kind, default, options) in expected.items():
        declaration = group.get(field)
        if not isinstance(declaration, dict):
            raise AssertionError(f"Exercise.{field} declaration is missing")
        if declaration.get("type") != kind or declaration.get("value") != default:
            raise AssertionError(f"Exercise.{field} declaration drifted")
        if options is not None and tuple(declaration.get("option", ())) != options:
            raise AssertionError(f"Exercise.{field} options drifted")


def _method_consumers(path: Path, class_name: str, fields: tuple[str, ...]):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    result = {field: [] for field in fields}
    target = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            target = node
            break
    if target is None:
        raise AssertionError(f"{class_name} is missing")
    for child in target.body:
        if not isinstance(child, ast.FunctionDef):
            continue
        for field in fields:
            if any(
                isinstance(item, ast.Attribute)
                and isinstance(item.ctx, ast.Load)
                and item.attr == field
                for item in ast.walk(child)
            ):
                result[field].append(child.name)
    return tree, target, {field: sorted(methods) for field, methods in result.items()}


def _source_flags(exercise_path: Path, combat_path: Path):
    _, exercise_class, exercise_consumers = _method_consumers(
        exercise_path,
        "Exercise",
        ("Exercise_ExerciseStrategy", "Exercise_OpponentChooseMode", "Exercise_OpponentTrial"),
    )
    _, _, combat_consumers = _method_consumers(
        combat_path,
        "ExerciseCombat",
        ("Exercise_OpponentTrial",),
    )
    run = next(
        (node for node in exercise_class.body if isinstance(node, ast.FunctionDef) and node.name == "run"),
        None,
    )
    if run is None:
        raise AssertionError("Exercise.run is missing")
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_exercise_config"
        for node in ast.walk(run)
    )
    expected = {
        "Exercise_ExerciseStrategy": ["_get_exercise_strategy", "run"],
        "Exercise_OpponentChooseMode": [
            "_opponent_fleet_check_all",
            "_opponent_sort",
            "run",
        ],
        "Exercise_OpponentTrial": ["run"] if guard_present else [],
    }
    combined = dict(exercise_consumers)
    combined["Exercise_OpponentTrial"] = sorted(
        combined["Exercise_OpponentTrial"] + combat_consumers["Exercise_OpponentTrial"]
    )
    expected["Exercise_OpponentTrial"] = sorted(
        expected["Exercise_OpponentTrial"] + ["_combat"]
    )
    if combined != expected:
        raise AssertionError("Exercise configuration consumer surface drifted")
    if guard_present:
        executable = [
            statement
            for statement in run.body
            if not isinstance(statement, (ast.Import, ast.ImportFrom))
        ]
        first = executable[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == "validate_alas_exercise_config"
        ):
            raise AssertionError("Exercise configuration guard is not first in run")
    return combined, guard_present


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        exercise = importlib.import_module("module.exercise.exercise")
        combat = importlib.import_module("module.exercise.combat")
        opponent = importlib.import_module("module.exercise.opponent")
        return exercise, combat, opponent
    finally:
        sys.path.remove(root)


class _Config(SimpleNamespace):
    def __init__(self, *, strategy: object, mode: object, trial: object):
        super().__init__(
            Exercise_ExerciseStrategy=strategy,
            Exercise_OpponentChooseMode=mode,
            Exercise_OpponentTrial=trial,
        )
        self.events = []

    def multi_set(self):
        return nullcontext()

    def set_record(self, **kwargs):
        self.events.append(["set_record", kwargs])

    def task_delay(self, **kwargs):
        self.events.append(["task_delay", kwargs])


def _run_case(
    module: Any,
    *,
    strategy: object,
    mode: object,
    trial: object,
    period_hours: int,
    remaining: tuple[int, ...] = (0,),
) -> dict[str, Any]:
    events = []
    config = _Config(strategy=strategy, mode=mode, trial=trial)
    host = object.__new__(module.Exercise)
    host.config = config
    host.device = SimpleNamespace(image=object())
    host.ui_ensure = MethodType(lambda self, page: events.append("ui_ensure"), host)
    host._get_opponent_change_count = MethodType(lambda self: 0, host)
    host._exercise_once = MethodType(
        lambda self: events.append("exercise_once") or True, host
    )
    host._exercise_easiest_else_exp = MethodType(
        lambda self: events.append("easiest_else_exp") or True, host
    )
    remaining_values = iter(remaining)
    original_period = module.OCR_PERIOD_REMAIN
    original_remaining = module.OCR_EXERCISE_REMAIN
    module.OCR_PERIOD_REMAIN = SimpleNamespace(
        ocr=lambda image: timedelta(hours=period_hours)
    )
    module.OCR_EXERCISE_REMAIN = SimpleNamespace(
        ocr=lambda image: next(remaining_values)
    )
    try:
        module.Exercise.run(host)
    finally:
        module.OCR_PERIOD_REMAIN = original_period
        module.OCR_EXERCISE_REMAIN = original_remaining
    return {
        "preserve": host.preserve,
        "remain": host.remain,
        "events": events + config.events,
    }


def _expected_preserve(module: Any, strategy: str, hour: int) -> int:
    if strategy == "aggressive":
        return 0
    preserve = 5
    if hour == 0:
        return preserve
    start, end = module.ADMIRAL_TRIAL_HOUR_INTERVAL[strategy]
    if start > hour >= end:
        return 0
    if hour < 6:
        return 0
    return preserve


def _verify_strategy_windows(module: Any) -> dict[str, list[int]]:
    zero_preserve_hours = {}
    logger_methods = {name: getattr(module.logger, name) for name in ("info", "attr", "hr")}
    for name in logger_methods:
        setattr(module.logger, name, lambda *args, **kwargs: None)
    try:
        for strategy in EXERCISE_STRATEGIES:
            zero_hours = []
            for hour in range(61):
                case = _run_case(
                    module,
                    strategy=strategy,
                    mode="leftmost",
                    trial=1,
                    period_hours=hour,
                )
                expected = _expected_preserve(module, strategy, hour)
                if case["preserve"] != expected:
                    raise AssertionError("original Exercise strategy window drifted")
                if expected == 0:
                    zero_hours.append(hour)
            zero_preserve_hours[strategy] = zero_hours
    finally:
        for name, value in logger_methods.items():
            setattr(module.logger, name, value)
    return zero_preserve_hours


class _Opponent:
    def __init__(self, index: int):
        self.index = index

    def get_priority(self, method: str):
        if "easiest" in method:
            return (30, 10, 40, 20)[self.index]
        return (10, 40, 20, 30)[self.index]


def _verify_opponent_modes(exercise_module: Any, opponent_module: Any):
    sorting = {}
    fleet_checks = {}
    original_check = opponent_module.OpponentChoose._opponent_fleet_check_all
    check_events = []
    opponent_module.OpponentChoose._opponent_fleet_check_all = (
        lambda self: check_events.append("checked")
    )
    try:
        for mode in EXERCISE_OPPONENT_MODES:
            host = object.__new__(exercise_module.Exercise)
            host.config = SimpleNamespace(Exercise_OpponentChooseMode=mode)
            host.opponents = [_Opponent(index) for index in range(4)]
            order = [
                int(index)
                for index in exercise_module.Exercise._opponent_sort(host)
            ]
            expected = (
                [0, 1, 2, 3]
                if mode == "leftmost"
                else [2, 0, 3, 1]
                if "easiest" in mode
                else [1, 3, 2, 0]
            )
            if order != expected:
                raise AssertionError("original Exercise opponent sorting drifted")
            sorting[mode] = order
            check_events.clear()
            exercise_module.Exercise._opponent_fleet_check_all(host)
            expected_checks = [] if mode == "leftmost" else ["checked"]
            if check_events != expected_checks:
                raise AssertionError("Exercise opponent detail-check dispatch drifted")
            fleet_checks[mode] = list(check_events)
    finally:
        opponent_module.OpponentChoose._opponent_fleet_check_all = original_check
    return {"sorting": sorting, "fleet_checks": fleet_checks}


def _combat_case(combat_module: Any, *, trial: int, success_at: int | None):
    events = []
    host = object.__new__(combat_module.ExerciseCombat)
    host.config = SimpleNamespace(Exercise_OpponentTrial=trial)
    host._choose_opponent = MethodType(
        lambda self, opponent: events.append(["choose", opponent]), host
    )
    host._combat_preparation = MethodType(
        lambda self: events.append("prepare"), host
    )
    attempts = 0

    def execute(self):
        nonlocal attempts
        attempts += 1
        events.append("execute")
        return attempts == success_at

    host._combat_execute = MethodType(execute, host)
    host._preparation_quit = MethodType(lambda self: events.append("quit"), host)
    result = combat_module.ExerciseCombat._combat(host, 2)
    return {
        "result": bool(result),
        "attempts": attempts,
        "trial_after": host.config.Exercise_OpponentTrial,
        "events": events,
    }


def _verify_trials(combat_module: Any):
    result = {}
    for trial in (1, 2, 3):
        success_points = {1, trial, None}
        for success_at in success_points:
            case = _combat_case(
                combat_module,
                trial=trial,
                success_at=success_at,
            )
            expected_attempts = trial if success_at is None else success_at
            if case["attempts"] != expected_attempts:
                raise AssertionError("original Exercise trial count drifted")
            if case["result"] is not (success_at is not None):
                raise AssertionError("original Exercise trial result drifted")
            if ("quit" in case["events"]) is not (success_at is None):
                raise AssertionError("original Exercise trial quit drifted")
            result[f"{trial}:{success_at}"] = case
    revised = _combat_case(combat_module, trial=0, success_at=1)
    if revised["trial_after"] != 1 or revised["attempts"] != 1:
        raise AssertionError("original Exercise invalid-trial revision drifted")
    result["original_invalid_revision"] = revised
    return result


def _verify_mode_dispatch(module: Any):
    result = {}
    for mode in EXERCISE_OPPONENT_MODES:
        case = _run_case(
            module,
            strategy="aggressive",
            mode=mode,
            trial=1,
            period_hours=60,
            remaining=(1, 0),
        )
        expected_event = "easiest_else_exp" if mode == "easiest_else_exp" else "exercise_once"
        if case["events"].count(expected_event) != 1:
            raise AssertionError("original Exercise mode dispatch drifted")
        result[mode] = case["events"]
    return result


def _verify_contract() -> tuple[int, int]:
    for strategy, mode, trial in itertools.product(
        EXERCISE_STRATEGIES,
        EXERCISE_OPPONENT_MODES,
        REPRESENTATIVE_TRIALS,
    ):
        validate_alas_exercise_config(
            strategy=strategy,
            opponent_mode=mode,
            opponent_trial=trial,
        )
    invalid_count = 0
    for field in ("strategy", "opponent_mode"):
        for value in INVALID_ENUM_VALUES:
            case = {
                "strategy": "aggressive",
                "opponent_mode": "max_exp",
                "opponent_trial": 1,
            }
            case[field] = value
            try:
                validate_alas_exercise_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid Exercise.{field} was admitted")
    for value in INVALID_TRIAL_VALUES:
        try:
            validate_alas_exercise_config(
                strategy="aggressive",
                opponent_mode="max_exp",
                opponent_trial=value,
            )
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid Exercise.OpponentTrial was admitted")
    return (
        len(EXERCISE_STRATEGIES)
        * len(EXERCISE_OPPONENT_MODES)
        * len(REPRESENTATIVE_TRIALS),
        invalid_count,
    )


def _verify_invalid_entry(module: Any, guard_present: bool):
    if not guard_present:
        return {}
    result = {}
    cases = {
        "Exercise_ExerciseStrategy": (None, "max_exp", 1),
        "Exercise_OpponentChooseMode": ("aggressive", None, 1),
        "Exercise_OpponentTrial": ("aggressive", "max_exp", 0),
    }
    for field, (strategy, mode, trial) in cases.items():
        try:
            _run_case(
                module,
                strategy=strategy,
                mode=mode,
                trial=trial,
                period_hours=60,
            )
        except SemanticGateClosed:
            result[field] = []
        else:
            raise AssertionError(f"patched Exercise admitted invalid {field}")
    return result


def verify_exercise_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    exercise_path = alas_root / "module/exercise/exercise.py"
    combat_path = alas_root / "module/exercise/combat.py"
    consumers, guard_present = _source_flags(exercise_path, combat_path)
    exercise_module, combat_module, opponent_module = _load_original(alas_root)
    strategy_windows = _verify_strategy_windows(exercise_module)
    opponent_modes = _verify_opponent_modes(exercise_module, opponent_module)
    trial_decisions = _verify_trials(combat_module)
    mode_dispatch = _verify_mode_dispatch(exercise_module)
    accepted_count, invalid_count = _verify_contract()
    invalid_entry = _verify_invalid_entry(exercise_module, guard_present)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted_count,
        "strategy_hour_case_count": len(EXERCISE_STRATEGIES) * 61,
        "invalid_case_count": invalid_count,
        "trial_domain": "positive_int",
        "runtime_consumers": consumers,
        "patched_guard_present": guard_present,
        "original_strategy_windows": strategy_windows,
        "original_opponent_modes": opponent_modes,
        "original_trial_decisions": trial_decisions,
        "original_mode_dispatch": mode_dispatch,
        "invalid_entry_events": invalid_entry,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_exercise_attempt_consumed": False,
        "real_combat_started": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "exercise": _sha256(exercise_path),
            "combat": _sha256(combat_path),
            "opponent": _sha256(alas_root / "module/exercise/opponent.py"),
        },
    }
