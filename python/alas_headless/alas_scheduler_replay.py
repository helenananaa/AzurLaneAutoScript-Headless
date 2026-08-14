"""Input-free replay of the pinned ALAS shared scheduler implementation."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import operator
import random
import re
from datetime import datetime, timedelta
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Callable, Dict, Mapping, MutableMapping, Sequence

from .alas_scheduler_contract import SCHEDULER_FIELDS, validate_alas_scheduler_config


class _Logger:
    def __getattr__(self, _name: str) -> Callable[..., None]:
        return lambda *_args, **_kwargs: None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise ValueError(f"missing ALAS class {name}")


def _method(tree: ast.Module, owner: str, name: str) -> ast.FunctionDef:
    for node in _class(tree, owner).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"missing ALAS method {owner}.{name}")


def _function(tree: ast.Module, name: str) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"missing ALAS function {name}")


def _compile(nodes: Sequence[ast.AST], globals_: Mapping[str, object]) -> Dict[str, object]:
    namespace: Dict[str, object] = dict(globals_)
    module = ast.fix_missing_locations(ast.Module(body=list(nodes), type_ignores=[]))
    exec(compile(module, "<alas-scheduler-replay>", "exec"), namespace)
    return namespace


def _scheduler_data(
    command: str,
    *,
    enable: bool = True,
    next_run: datetime,
    success: object = 30,
    failure: object = 60,
    server_update: object = "00:00",
) -> MutableMapping[str, object]:
    return {
        command: {
            "Scheduler": {
                "Enable": enable,
                "NextRun": next_run,
                "Command": command,
                "SuccessInterval": success,
                "FailureInterval": failure,
                "ServerUpdate": server_update,
            }
        }
    }


def _source_structure(config_tree: ast.Module) -> Mapping[str, object]:
    bind = _method(config_tree, "AzurLaneConfig", "bind")
    override = _method(config_tree, "AzurLaneConfig", "override")
    delay = _method(config_tree, "AzurLaneConfig", "task_delay")
    scheduler = _method(config_tree, "AzurLaneConfig", "get_next_task")

    override_store = [
        node.lineno
        for node in ast.walk(override)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == "overridden"
            for target in node.targets
        )
    ]
    bind_override = [
        node.lineno
        for node in ast.walk(bind)
        if isinstance(node, ast.For)
        and isinstance(node.iter, ast.Call)
        and isinstance(node.iter.func, ast.Attribute)
        and node.iter.func.attr == "items"
        and isinstance(node.iter.func.value, ast.Attribute)
        and node.iter.func.value.attr == "overridden"
    ]
    bind_value_loops = [
        node.lineno
        for node in ast.walk(bind)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "func"
    ]
    next_run_writes = [
        node.lineno
        for node in ast.walk(delay)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Attribute)
            and target.value.attr == "modified"
            for target in node.targets
        )
    ]
    scheduler_writes = [
        node.lineno
        for node in ast.walk(scheduler)
        if isinstance(node, (ast.Assign, ast.AugAssign))
        and any(
            isinstance(candidate, ast.Attribute) and candidate.attr == "NextRun"
            for candidate in ast.walk(node)
        )
    ]
    if (
        len(override_store) != 1
        or len(bind_override) != 1
        or not bind_value_loops
        or bind_override[0] <= min(bind_value_loops)
    ):
        raise AssertionError("ALAS scheduler override preservation structure is ambiguous")
    if len(next_run_writes) != 1 or scheduler_writes:
        raise AssertionError("ALAS scheduler NextRun ownership structure changed")
    return {
        "override_store_line": override_store[0],
        "bind_override_line": bind_override[0],
        "bind_override_applied_after_values": True,
        "task_delay_next_run_write_line": next_run_writes[0],
        "get_next_task_writes_next_run": False,
    }


def verify_scheduler_contract(alas_root: Path) -> Mapping[str, object]:
    alas_root = alas_root.resolve()
    paths = {
        "config": alas_root / "module/config/config.py",
        "utils": alas_root / "module/config/utils.py",
        "deep": alas_root / "module/config/deep.py",
        "filter": alas_root / "module/base/filter.py",
        "args": alas_root / "module/config/argument/args.json",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    trees = {
        key: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for key, path in paths.items()
        if key != "args"
    }
    logger = _Logger()
    deep = _compile(
        [_function(trees["deep"], "deep_get"), _function(trees["deep"], "deep_set")],
        {},
    )
    deep_get = deep["deep_get"]
    deep_set = deep["deep_set"]
    filter_type = _compile([_class(trees["filter"], "Filter")], {"re": re, "logger": logger})[
        "Filter"
    ]
    function_type = _compile(
        [_class(trees["config"], "Function")],
        {"deep_get": deep_get, "DEFAULT_TIME": datetime(2020, 1, 1)},
    )["Function"]

    fixed_now = datetime(2026, 8, 14, 23, 50, 0)

    class _FixedDateTimeMeta(type):
        def __instancecheck__(cls, instance: object) -> bool:
            return isinstance(instance, datetime)

    class _FixedDateTime(datetime, metaclass=_FixedDateTimeMeta):
        @classmethod
        def now(cls, _tz=None) -> datetime:
            return fixed_now

    class _MidpointRandom:
        @staticmethod
        def randint(low: int, high: int) -> int:
            return (low + high) // 2

    server_offset = [timedelta(0)]
    helpers = _compile(
        [
            _function(trees["utils"], "random_normal_distribution_int"),
            _function(trees["utils"], "ensure_time"),
            _function(trees["utils"], "dict_to_kv"),
            _function(trees["utils"], "get_server_next_update"),
            _function(trees["utils"], "nearest_future"),
        ],
        {
            "random": _MidpointRandom,
            "datetime": _FixedDateTime,
            "timedelta": timedelta,
            "server_time_offset": lambda: server_offset[0],
        },
    )
    marker_config = type("AzurLaneConfig", (), {"is_hoarding_task": True})
    get_next_task = _compile(
        [_method(trees["config"], "AzurLaneConfig", "get_next_task")],
        {
            "AzurLaneConfig": marker_config,
            "Function": function_type,
            "Filter": filter_type,
            "datetime": _FixedDateTime,
            "operator": operator,
            "logger": logger,
        },
    )["get_next_task"]

    class _ScriptError(RuntimeError):
        pass

    task_delay = _compile(
        [_method(trees["config"], "AzurLaneConfig", "task_delay")],
        {
            "datetime": _FixedDateTime,
            "timedelta": timedelta,
            "ensure_time": helpers["ensure_time"],
            "get_server_next_update": helpers["get_server_next_update"],
            "nearest_future": helpers["nearest_future"],
            "dict_to_kv": helpers["dict_to_kv"],
            "logger": logger,
            "ScriptError": _ScriptError,
        },
    )["task_delay"]

    args = json.loads(paths["args"].read_text(encoding="utf-8"))
    panels = []
    classes: Dict[str, list[str]] = {}
    runtime_data: MutableMapping[str, object] = {}
    for panel, panel_data in args.items():
        if "Scheduler" not in panel_data:
            continue
        scheduler = panel_data["Scheduler"]
        if set(scheduler) != set(SCHEDULER_FIELDS):
            raise AssertionError(f"{panel}.Scheduler is not the shared six-field surface")
        values = {field: scheduler[field]["value"] for field in SCHEDULER_FIELDS}
        if values["Command"] != panel:
            raise AssertionError(f"{panel}.Scheduler.Command is not self-identifying")
        signature = json.dumps(
            {
                field: values[field]
                for field in (
                    "Enable",
                    "SuccessInterval",
                    "FailureInterval",
                    "ServerUpdate",
                )
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        classes.setdefault(signature, []).append(panel)
        runtime_data[panel] = {
            "Scheduler": {
                **values,
                "NextRun": datetime.fromisoformat(values["NextRun"]),
            }
        }
        panels.append(panel)
    snapshots = validate_alas_scheduler_config(runtime_data)
    if len(panels) != 50 or len(classes) != 15 or len(snapshots) != 50:
        raise AssertionError("pinned ALAS Scheduler equivalence surface changed")

    cases: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            raise AssertionError(name)
        cases.append(name)

    def queue(data: MutableMapping[str, object], priority: str) -> SimpleNamespace:
        target = SimpleNamespace(
            data=data,
            hoarding=timedelta(0),
            SCHEDULER_PRIORITY=priority,
            pending_task=[],
            waiting_task=[],
        )
        MethodType(get_next_task, target)()
        return target

    data = {}
    data.update(_scheduler_data("Disabled", enable=False, next_run=fixed_now - timedelta(hours=1)))
    data.update(_scheduler_data("DueSecond", next_run=fixed_now - timedelta(minutes=1)))
    data.update(_scheduler_data("DueFirst", next_run=fixed_now - timedelta(minutes=2)))
    data.update(_scheduler_data("Future", next_run=fixed_now + timedelta(minutes=10)))
    queued = queue(data, "DueFirst > DueSecond > Future")
    check("disabled-not-dispatched", all(item.command != "Disabled" for item in queued.pending_task))
    pending_commands = [item.command for item in queued.pending_task]
    check("priority-orders-due", pending_commands == ["DueFirst", "DueSecond"])
    check("future-waits", [item.command for item in queued.waiting_task] == ["Future"])

    invalid = _scheduler_data("Invalid", next_run=fixed_now)
    invalid["Invalid"]["Scheduler"]["NextRun"] = "not-a-datetime"  # type: ignore[index]
    try:
        validate_alas_scheduler_config(invalid)
    except Exception as exc:
        check("invalid-datetime-fails-before-queue", "datetime" in str(exc))
    else:
        raise AssertionError("invalid-datetime-fails-before-queue")

    def delay_sandbox(
        *, success_interval: object = 30, failure_interval: object = 60, server_update: object = "00:00"
    ) -> SimpleNamespace:
        data = _scheduler_data(
            "Task",
            next_run=fixed_now - timedelta(minutes=1),
            success=success_interval,
            failure=failure_interval,
            server_update=server_update,
        )
        target = SimpleNamespace(
            data=data,
            modified={},
            task=SimpleNamespace(command="Task"),
            Scheduler_SuccessInterval=success_interval,
            Scheduler_FailureInterval=failure_interval,
            Scheduler_ServerUpdate=server_update,
            update_calls=0,
        )

        def update() -> None:
            target.update_calls += 1
            for key, value in tuple(target.modified.items()):
                deep_set(target.data, key, value)
            target.modified.clear()

        target.update = update
        target.task_delay = MethodType(task_delay, target)
        return target

    target = delay_sandbox()
    target.task_delay(success=True)
    check("success-fixed-interval", deep_get(target.data, "Task.Scheduler.NextRun") == fixed_now + timedelta(minutes=30))
    check("single-durable-update", target.update_calls == 1 and target.modified == {})

    target = delay_sandbox()
    target.task_delay(success=False)
    check("failure-fixed-interval", deep_get(target.data, "Task.Scheduler.NextRun") == fixed_now + timedelta(minutes=60))

    target = delay_sandbox(success_interval="30-60", failure_interval="120-240")
    target.task_delay(success=True)
    check("success-range-midpoint", deep_get(target.data, "Task.Scheduler.NextRun") == fixed_now + timedelta(minutes=45))
    target = delay_sandbox(success_interval="30-60", failure_interval="120-240")
    target.task_delay(success=False)
    check("failure-range-midpoint", deep_get(target.data, "Task.Scheduler.NextRun") == fixed_now + timedelta(minutes=180))

    target = delay_sandbox(server_update="00:00, 12:00")
    target.task_delay(server_update=True)
    check("cross-day-server-update", deep_get(target.data, "Task.Scheduler.NextRun") == datetime(2026, 8, 15, 0, 0))
    server_offset[0] = timedelta(hours=1)
    target = delay_sandbox(server_update="00:00")
    target.task_delay(server_update=True)
    check("cross-server-positive-offset", deep_get(target.data, "Task.Scheduler.NextRun") == datetime(2026, 8, 15, 1, 0))
    server_offset[0] = timedelta(hours=-1)
    target = delay_sandbox(server_update="00:00")
    target.task_delay(server_update=True)
    check("cross-server-negative-offset", deep_get(target.data, "Task.Scheduler.NextRun") == datetime(2026, 8, 15, 23, 0))
    server_offset[0] = timedelta(0)
    target = delay_sandbox(server_update="00:00, 12:00")
    target.task_delay(success=False, server_update=True)
    check("nearest-candidate-wins", deep_get(target.data, "Task.Scheduler.NextRun") == datetime(2026, 8, 15, 0, 0))

    target = delay_sandbox()
    target.data.update(_scheduler_data("Other", next_run=fixed_now - timedelta(minutes=1)))
    target.task_delay(minute=15, task="Other")
    check("cross-task-next-run", deep_get(target.data, "Other.Scheduler.NextRun") == fixed_now + timedelta(minutes=15))

    # Process interruption after the durable update: a fresh scheduler sees the
    # committed future NextRun and cannot dispatch the same task again.
    durable = copy.deepcopy(target.data)
    validate_alas_scheduler_config(durable)
    recovered = queue(durable, "Other > Task")
    check("recovery-preserves-next-run", deep_get(durable, "Other.Scheduler.NextRun") == fixed_now + timedelta(minutes=15))
    check("recovery-no-duplicate-dispatch", all(item.command != "Other" for item in recovered.pending_task))
    recovered_again = queue(copy.deepcopy(durable), "Other > Task")
    check(
        "repeated-recovery-is-idempotent",
        [item.command for item in recovered.waiting_task]
        == [item.command for item in recovered_again.waiting_task],
    )

    structure = _source_structure(trees["config"])
    check("override-is-preserved-after-bind", structure["bind_override_applied_after_values"] is True)
    check("get-next-has-no-next-run-write", structure["get_next_task_writes_next_run"] is False)

    class_rows = [
        {"signature": json.loads(signature), "panels": members}
        for signature, members in sorted(classes.items())
    ]
    return {
        "schema": "alas-headless.scheduler-contract-replay/v1",
        "passed": True,
        "scheduler_panel_count": len(panels),
        "scheduler_panels": panels,
        "equivalence_class_count": len(class_rows),
        "equivalence_classes": class_rows,
        "case_count": len(cases),
        "cases": cases,
        "source_structure": structure,
        "temporary_config_only": True,
        "offline_clock": fixed_now.isoformat(sep=" "),
        "android_input_injected": False,
        "source_sha256": {key: _sha256(path) for key, path in paths.items()},
    }
