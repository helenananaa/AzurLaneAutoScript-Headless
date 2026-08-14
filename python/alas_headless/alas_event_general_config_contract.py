"""Fail-closed contract for ALAS event limits and task balancing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from .semantic_oracle import SemanticGateClosed


TASK_BALANCER_CALLS = ("Main", "Main2", "Main3")
_PT_SEPARATORS = re.compile(r"[,.'\"，。]")
_EARLIEST_TIME = datetime(2000, 1, 1)
_LATEST_TIME = datetime(2100, 1, 1)
_MAX_LIMIT = 1_000_000_000_000


@dataclass(frozen=True)
class AlasEventGeneralConfigSnapshot:
    pt_limit: int
    time_limit: datetime
    task_balancer_enable: bool
    task_balancer_coin_limit: int
    task_balancer_task_call: str


def _pt_limit(value: object) -> int:
    if isinstance(value, bool):
        raise SemanticGateClosed("EventGeneral.PtLimit must be a non-negative integer")
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        raw = value.strip()
        if not raw or any(
            character not in "0123456789,.'\"，。" for character in raw
        ):
            raise SemanticGateClosed(
                "EventGeneral.PtLimit contains unsupported characters"
            )
        normalized = _PT_SEPARATORS.sub("", raw)
        if not normalized:
            raise SemanticGateClosed("EventGeneral.PtLimit contains no digits")
        parsed = int(normalized)
    else:
        raise SemanticGateClosed("EventGeneral.PtLimit must be integer text")
    if not 0 <= parsed <= _MAX_LIMIT:
        raise SemanticGateClosed("EventGeneral.PtLimit is outside safe bounds")
    return parsed


def _bounded_integer(name: str, value: object) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 0 <= value <= _MAX_LIMIT
    ):
        raise SemanticGateClosed(f"{name} must be a bounded non-negative integer")
    return value


def validate_alas_event_general_config(
    *,
    pt_limit: object,
    time_limit: object,
    task_balancer_enable: object,
    task_balancer_coin_limit: object,
    task_balancer_task_call: object,
) -> AlasEventGeneralConfigSnapshot:
    """Validate the complete EventGeneral and TaskBalancer surface."""

    if (
        not isinstance(time_limit, datetime)
        or time_limit.tzinfo is not None
        or not _EARLIEST_TIME <= time_limit <= _LATEST_TIME
    ):
        raise SemanticGateClosed(
            "EventGeneral.TimeLimit must be a bounded naive datetime"
        )
    if type(task_balancer_enable) is not bool:
        raise SemanticGateClosed("TaskBalancer.Enable must be a bool")
    if (
        not isinstance(task_balancer_task_call, str)
        or task_balancer_task_call not in TASK_BALANCER_CALLS
    ):
        raise SemanticGateClosed(
            "TaskBalancer.TaskCall is outside the pinned ALAS surface"
        )
    return AlasEventGeneralConfigSnapshot(
        pt_limit=_pt_limit(pt_limit),
        time_limit=time_limit,
        task_balancer_enable=task_balancer_enable,
        task_balancer_coin_limit=_bounded_integer(
            "TaskBalancer.CoinLimit", task_balancer_coin_limit
        ),
        task_balancer_task_call=task_balancer_task_call,
    )
