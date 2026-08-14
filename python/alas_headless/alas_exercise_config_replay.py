"""Deterministic replay of pinned ALAS Exercise configuration decisions."""

from __future__ import annotations

import ast
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
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
REPRESENTATIVE_THRESHOLDS = (0.0, 0.01, 0.4, 1.0)
REPRESENTATIVE_REFRESH_VALUES = tuple(range(7))
REPRESENTATIVE_REFRESH_RECORDS = (
    datetime(2000, 1, 1),
    datetime(2026, 8, 15),
    datetime(2100, 1, 1),
)
INVALID_ENUM_VALUES = (None, True, 1, "", "unknown", [])
INVALID_TRIAL_VALUES = (0, -1, True, 1.0, "1", None, [])
INVALID_THRESHOLD_VALUES = (
    -0.01,
    1.01,
    True,
    float("nan"),
    float("inf"),
    "0.4",
    None,
    [],
)
INVALID_REFRESH_VALUES = (-1, 7, True, 1.0, "1", None, [])
INVALID_RECORD_VALUES = (
    datetime(1999, 12, 31),
    datetime(2100, 1, 2),
    datetime(2026, 8, 15, tzinfo=timezone.utc),
    "2026-08-15 00:00:00",
    None,
    [],
)


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
        "LowHpThreshold": ("input", 0.4, None),
        "LowHpConfirmWait": ("input", 0.1, None),
        "OpponentRefreshValue": ("input", 0, None),
        "OpponentRefreshRecord": (
            "datetime",
            "2020-01-01 00:00:00",
            None,
        ),
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


def _source_flags(exercise_path: Path, combat_path: Path, hp_path: Path):
    consumed_fields = (
        "Exercise_ExerciseStrategy",
        "Exercise_OpponentChooseMode",
        "Exercise_OpponentTrial",
        "Exercise_LowHpThreshold",
        "Exercise_OpponentRefreshValue",
        "Exercise_OpponentRefreshRecord",
        "Exercise_LowHpConfirmWait",
    )
    _, exercise_class, exercise_consumers = _method_consumers(
        exercise_path,
        "Exercise",
        consumed_fields,
    )
    _, _, combat_consumers = _method_consumers(
        combat_path,
        "ExerciseCombat",
        consumed_fields,
    )
    _, _, hp_consumers = _method_consumers(
        hp_path,
        "HpDaemon",
        consumed_fields,
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
        "Exercise_LowHpThreshold": ["_exercise_easiest_else_exp"],
        "Exercise_OpponentRefreshValue": ["_get_opponent_change_count"],
        "Exercise_OpponentRefreshRecord": ["_get_opponent_change_count"],
        "Exercise_LowHpConfirmWait": [],
    }
    if guard_present:
        for field in (
            "Exercise_LowHpThreshold",
            "Exercise_OpponentRefreshValue",
            "Exercise_OpponentRefreshRecord",
        ):
            expected[field].append("run")
    combined = {
        field: sorted(
            exercise_consumers[field]
            + combat_consumers[field]
            + hp_consumers[field]
        )
        for field in consumed_fields
    }
    expected["Exercise_OpponentTrial"] = sorted(
        expected["Exercise_OpponentTrial"] + ["_combat"]
    )
    expected["Exercise_LowHpThreshold"] = sorted(
        expected["Exercise_LowHpThreshold"] + ["_at_low_hp"]
    )
    if combined != expected:
        raise AssertionError(
            f"Exercise configuration consumer surface drifted: {combined!r} != {expected!r}"
        )
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
    def __init__(
        self,
        *,
        strategy: object,
        mode: object,
        trial: object,
        low_hp_threshold: object = 0.4,
        refresh_value: object = 0,
        refresh_record: object = datetime(2026, 8, 15),
    ):
        super().__init__(
            Exercise_ExerciseStrategy=strategy,
            Exercise_OpponentChooseMode=mode,
            Exercise_OpponentTrial=trial,
            Exercise_LowHpThreshold=low_hp_threshold,
            Exercise_OpponentRefreshValue=refresh_value,
            Exercise_OpponentRefreshRecord=refresh_record,
        )
        self.events = []

    def multi_set(self):
        return nullcontext()

    def set_record(self, **kwargs):
        self.events.append(["set_record", kwargs])
        for key, value in kwargs.items():
            setattr(self, key, value)

    def override(self, **kwargs):
        self.events.append(["override", kwargs])
        for key, value in kwargs.items():
            setattr(self, key, value)

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
    low_hp_threshold: object = 0.4,
    refresh_value: object = 0,
    refresh_record: object = datetime(2026, 8, 15),
) -> dict[str, Any]:
    events = []
    config = _Config(
        strategy=strategy,
        mode=mode,
        trial=trial,
        low_hp_threshold=low_hp_threshold,
        refresh_value=refresh_value,
        refresh_record=refresh_record,
    )
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


def _verify_refresh_state(exercise_module: Any) -> dict[str, Any]:
    update = datetime(2026, 8, 15)
    original_update = exercise_module.get_server_last_update
    exercise_module.get_server_last_update = lambda value: update
    same_day = {}
    try:
        for value in REPRESENTATIVE_REFRESH_VALUES:
            config = _Config(
                strategy="aggressive",
                mode="max_exp",
                trial=1,
                refresh_value=value,
                refresh_record=update,
            )
            host = object.__new__(exercise_module.Exercise)
            host.config = config
            result = exercise_module.Exercise._get_opponent_change_count(host)
            if result != value or config.events:
                raise AssertionError("Exercise same-day refresh restoration drifted")
            same_day[str(value)] = result

        resets = {}
        for label, record in (
            ("previous_day", update - timedelta(days=1)),
            ("future_day", update + timedelta(days=1)),
        ):
            config = _Config(
                strategy="aggressive",
                mode="max_exp",
                trial=1,
                refresh_value=6,
                refresh_record=record,
            )
            host = object.__new__(exercise_module.Exercise)
            host.config = config
            result = exercise_module.Exercise._get_opponent_change_count(host)
            if (
                result != 0
                or config.Exercise_OpponentRefreshValue != 0
                or config.events
                != [["set_record", {"Exercise_OpponentRefreshValue": 0}]]
            ):
                raise AssertionError("Exercise cross-day refresh reset drifted")
            resets[label] = config.events

        increments = {}
        for value in range(5):
            events = []
            config = _Config(
                strategy="aggressive",
                mode="max_exp",
                trial=1,
                refresh_value=value,
                refresh_record=update,
            )
            host = object.__new__(exercise_module.Exercise)
            host.config = config
            host.opponent_change_count = value
            host.appear_then_click = MethodType(
                lambda self, button: events.append("new_opponent"), host
            )
            host.ensure_no_info_bar = MethodType(
                lambda self, timeout: events.append(["info_bar", timeout]), host
            )
            exercise_module.Exercise._new_opponent(host)
            expected = value + 1
            if (
                host.opponent_change_count != expected
                or config.Exercise_OpponentRefreshValue != expected
                or events != ["new_opponent", ["info_bar", 3]]
            ):
                raise AssertionError("Exercise refresh increment drifted")
            increments[str(value)] = expected
    finally:
        exercise_module.get_server_last_update = original_update
    return {"same_day": same_day, "cross_day": resets, "increments": increments}


class _ConfirmTimer:
    def __init__(self, *, reached: bool, current: float):
        self._reached = reached
        self._current = current
        self.reset_count = 0

    def reached(self):
        return self._reached

    def current_time(self):
        return self._current

    def reset(self):
        self.reset_count += 1
        self._reached = False


def _verify_low_hp_threshold(combat_module: Any) -> dict[str, Any]:
    cases = {
        "confirmed_at_threshold": (0.4, 0.4, 0.5, True, 1.0, True),
        "confirmation_pending": (0.4, 0.4, 0.5, False, 0.5, False),
        "above_threshold": (0.4, 0.400001, 0.5, True, 1.0, False),
        "minimum_excluded": (1.0, 0.01, 0.5, True, 1.0, False),
        "zero_threshold": (0.0, 0.5, 0.5, True, 1.0, False),
        "full_threshold": (1.0, 1.0, 0.5, True, 1.0, True),
        "defender_bar_gone": (0.4, 0.4, 0.0, True, 1.0, False),
        "stale_confirmation": (0.4, 0.4, 0.5, True, 300.0, False),
    }
    result = {}
    for name, (threshold, attacker, defender, reached, current, expected) in cases.items():
        host = object.__new__(combat_module.ExerciseCombat)
        host.config = SimpleNamespace(Exercise_LowHpThreshold=threshold)
        timer = _ConfirmTimer(reached=reached, current=current)
        host.low_hp_confirm_timer = timer
        percentages = iter((attacker, defender))
        host._calculate_hp = MethodType(
            lambda self, image, **kwargs: next(percentages), host
        )
        host._show_hp = MethodType(lambda self, low_hp_time=0: None, host)
        decision = combat_module.HpDaemon._at_low_hp(
            host,
            image=object(),
            pause=combat_module.PAUSE,
        )
        if bool(decision) is not expected:
            raise AssertionError("Exercise low-HP threshold decision drifted")
        result[name] = {
            "decision": bool(decision),
            "timer_resets": timer.reset_count,
        }
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
    for strategy, mode, trial, threshold, refresh_value, refresh_record in itertools.product(
        EXERCISE_STRATEGIES,
        EXERCISE_OPPONENT_MODES,
        REPRESENTATIVE_TRIALS,
        REPRESENTATIVE_THRESHOLDS,
        REPRESENTATIVE_REFRESH_VALUES,
        REPRESENTATIVE_REFRESH_RECORDS,
    ):
        validate_alas_exercise_config(
            strategy=strategy,
            opponent_mode=mode,
            opponent_trial=trial,
            low_hp_threshold=threshold,
            opponent_refresh_value=refresh_value,
            opponent_refresh_record=refresh_record,
        )
    invalid_count = 0
    for field in ("strategy", "opponent_mode"):
        for value in INVALID_ENUM_VALUES:
            case = {
                "strategy": "aggressive",
                "opponent_mode": "max_exp",
                "opponent_trial": 1,
                "low_hp_threshold": 0.4,
                "opponent_refresh_value": 0,
                "opponent_refresh_record": datetime(2026, 8, 15),
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
                low_hp_threshold=0.4,
                opponent_refresh_value=0,
                opponent_refresh_record=datetime(2026, 8, 15),
            )
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid Exercise.OpponentTrial was admitted")
    invalid_surfaces = (
        ("low_hp_threshold", INVALID_THRESHOLD_VALUES),
        ("opponent_refresh_value", INVALID_REFRESH_VALUES),
        ("opponent_refresh_record", INVALID_RECORD_VALUES),
    )
    for field, values in invalid_surfaces:
        for value in values:
            case = {
                "strategy": "aggressive",
                "opponent_mode": "max_exp",
                "opponent_trial": 1,
                "low_hp_threshold": 0.4,
                "opponent_refresh_value": 0,
                "opponent_refresh_record": datetime(2026, 8, 15),
            }
            case[field] = value
            try:
                validate_alas_exercise_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid Exercise.{field} was admitted")
    return (
        len(EXERCISE_STRATEGIES)
        * len(EXERCISE_OPPONENT_MODES)
        * len(REPRESENTATIVE_TRIALS)
        * len(REPRESENTATIVE_THRESHOLDS)
        * len(REPRESENTATIVE_REFRESH_VALUES)
        * len(REPRESENTATIVE_REFRESH_RECORDS),
        invalid_count,
    )


def _verify_invalid_entry(module: Any, guard_present: bool):
    if not guard_present:
        return {}
    result = {}
    cases = {
        "Exercise_ExerciseStrategy": {"strategy": None},
        "Exercise_OpponentChooseMode": {"mode": None},
        "Exercise_OpponentTrial": {"trial": 0},
        "Exercise_LowHpThreshold": {"low_hp_threshold": -0.01},
        "Exercise_OpponentRefreshValue": {"refresh_value": 7},
        "Exercise_OpponentRefreshRecord": {
            "refresh_record": datetime(1999, 12, 31)
        },
    }
    for field, override in cases.items():
        arguments = {
            "strategy": "aggressive",
            "mode": "max_exp",
            "trial": 1,
            "period_hours": 60,
            "low_hp_threshold": 0.4,
            "refresh_value": 0,
            "refresh_record": datetime(2026, 8, 15),
        }
        arguments.update(override)
        try:
            _run_case(module, **arguments)
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
    hp_path = alas_root / "module/exercise/hp_daemon.py"
    consumers, guard_present = _source_flags(exercise_path, combat_path, hp_path)
    exercise_module, combat_module, opponent_module = _load_original(alas_root)
    strategy_windows = _verify_strategy_windows(exercise_module)
    opponent_modes = _verify_opponent_modes(exercise_module, opponent_module)
    trial_decisions = _verify_trials(combat_module)
    refresh_state = _verify_refresh_state(exercise_module)
    low_hp_threshold = _verify_low_hp_threshold(combat_module)
    mode_dispatch = _verify_mode_dispatch(exercise_module)
    accepted_count, invalid_count = _verify_contract()
    invalid_entry = _verify_invalid_entry(exercise_module, guard_present)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 6,
        "declared_unused_fields": ["Exercise_LowHpConfirmWait"],
        "accepted_case_count": accepted_count,
        "strategy_hour_case_count": len(EXERCISE_STRATEGIES) * 61,
        "invalid_case_count": invalid_count,
        "trial_domain": "positive_int",
        "runtime_consumers": consumers,
        "patched_guard_present": guard_present,
        "original_strategy_windows": strategy_windows,
        "original_opponent_modes": opponent_modes,
        "original_trial_decisions": trial_decisions,
        "original_refresh_state": refresh_state,
        "original_low_hp_threshold": low_hp_threshold,
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
            "hp_daemon": _sha256(hp_path),
            "opponent": _sha256(alas_root / "module/exercise/opponent.py"),
        },
    }
