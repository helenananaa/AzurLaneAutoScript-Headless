"""Fail-closed validation for ALAS' shared six-field Scheduler surface."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Mapping, Tuple

from .semantic_oracle import SemanticGateClosed


SCHEDULER_FIELDS = (
    "Enable",
    "NextRun",
    "Command",
    "SuccessInterval",
    "FailureInterval",
    "ServerUpdate",
)
_CLOCK = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")
_RANGE = re.compile(r"([0-9]+)(?:\s*[-,]\s*([0-9]+))?")


@dataclass(frozen=True)
class AlasSchedulerTaskSnapshot:
    panel: str
    enable: bool
    next_run: datetime
    command: str
    success_interval: Any
    failure_interval: Any
    server_updates: Tuple[str, ...]


@dataclass(frozen=True)
class AlasTaskHoardingSnapshot:
    minutes: int
    duration: timedelta


def validate_alas_task_hoarding_config(
    data: Mapping[str, Any],
) -> AlasTaskHoardingSnapshot:
    """Bound the global queue-hoarding offset before ALAS applies it."""

    try:
        value = data["Alas"]["Optimization"]["TaskHoardingDuration"]
    except (KeyError, TypeError) as exc:
        raise SemanticGateClosed(
            "Alas.Optimization.TaskHoardingDuration is missing"
        ) from exc
    if isinstance(value, bool) or not isinstance(value, int):
        raise SemanticGateClosed("TaskHoardingDuration must be whole minutes")
    if not 0 <= value <= 1440:
        raise SemanticGateClosed(
            "TaskHoardingDuration must be between zero and 1440 minutes"
        )
    return AlasTaskHoardingSnapshot(
        minutes=value,
        duration=timedelta(minutes=value),
    )


def _validate_interval(value: Any, *, field: str) -> None:
    if isinstance(value, bool):
        raise SemanticGateClosed(field + " must be a non-negative minute interval")
    if isinstance(value, (int, float)):
        if value < 0:
            raise SemanticGateClosed(field + " must be non-negative")
        return
    if isinstance(value, (tuple, list)) and len(value) == 2:
        low, high = value
        if (
            any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value)
            or low < 0
            or high < low
        ):
            raise SemanticGateClosed(field + " range is malformed")
        return
    if isinstance(value, str):
        match = _RANGE.fullmatch(value.strip())
        if match is not None:
            low = int(match.group(1))
            high = int(match.group(2) or match.group(1))
            if high >= low:
                return
    raise SemanticGateClosed(field + " interval is malformed")


def _validate_server_updates(value: Any, *, field: str) -> Tuple[str, ...]:
    if isinstance(value, str):
        values = tuple(part.strip() for part in value.split(","))
    elif isinstance(value, (tuple, list)):
        values = tuple(value)
    else:
        values = ()
    if not values or any(not isinstance(item, str) or _CLOCK.fullmatch(item) is None for item in values):
        raise SemanticGateClosed(field + " server update schedule is malformed")
    if len(values) != len(set(values)):
        raise SemanticGateClosed(field + " server update schedule is ambiguous")
    return values


def validate_alas_scheduler_config(
    data: Mapping[str, Any],
) -> Tuple[AlasSchedulerTaskSnapshot, ...]:
    """Validate every task using the shared ALAS Scheduler before dispatch."""

    if not isinstance(data, Mapping):
        raise SemanticGateClosed("ALAS scheduler configuration root is malformed")
    snapshots = []
    commands = set()
    for panel, panel_data in data.items():
        if not isinstance(panel_data, Mapping) or "Scheduler" not in panel_data:
            continue
        scheduler = panel_data["Scheduler"]
        prefix = str(panel) + ".Scheduler"
        if not isinstance(scheduler, Mapping) or set(scheduler) != set(SCHEDULER_FIELDS):
            raise SemanticGateClosed(prefix + " six-field contract is incomplete")
        enable = scheduler["Enable"]
        next_run = scheduler["NextRun"]
        command = scheduler["Command"]
        if not isinstance(enable, bool):
            raise SemanticGateClosed(prefix + ".Enable must be boolean")
        if not isinstance(next_run, datetime):
            raise SemanticGateClosed(prefix + ".NextRun must be a datetime")
        if not isinstance(command, str) or not command or command != panel:
            raise SemanticGateClosed(prefix + ".Command does not identify its panel")
        if command in commands:
            raise SemanticGateClosed("ALAS scheduler command is duplicated: " + command)
        commands.add(command)
        _validate_interval(scheduler["SuccessInterval"], field=prefix + ".SuccessInterval")
        _validate_interval(scheduler["FailureInterval"], field=prefix + ".FailureInterval")
        server_updates = _validate_server_updates(
            scheduler["ServerUpdate"], field=prefix + ".ServerUpdate"
        )
        snapshots.append(
            AlasSchedulerTaskSnapshot(
                panel=str(panel),
                enable=enable,
                next_run=next_run,
                command=command,
                success_interval=scheduler["SuccessInterval"],
                failure_interval=scheduler["FailureInterval"],
                server_updates=server_updates,
            )
        )
    if not snapshots:
        raise SemanticGateClosed("ALAS scheduler has no task surfaces")
    return tuple(snapshots)
