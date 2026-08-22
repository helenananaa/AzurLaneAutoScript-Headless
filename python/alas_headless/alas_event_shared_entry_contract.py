"""Fail-closed entry contract shared by the seven campaign-event panels."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .alas_event_daily_config_contract import EVENT_DAILY_COMMANDS
from .semantic_oracle import SemanticGateClosed


EVENT_DIRECT_COMMANDS = ("Event", "Event2")
EVENT_SP_COMMANDS = ("EventSp",)
EVENT_COMMANDS = EVENT_DIRECT_COMMANDS + EVENT_DAILY_COMMANDS + EVENT_SP_COMMANDS
EVENT_SHARED_GROUPS = (
    "Scheduler",
    "Campaign",
    "StopCondition",
    "Fleet",
    "Submarine",
    "Emotion",
    "HpControl",
    "EnemyPriority",
    "Storage",
)

_EVENT_FOLDER = re.compile(r"^event_[0-9]{8}_[a-z]{2}$")
_DIRECT_STAGE = re.compile(r"^[a-z0-9\u03bc][a-z0-9._\-\u03bc]{0,31}$")
_DAILY_STAGES = {
    "EventA": frozenset(("a1", "a2", "a3", "t1", "t2", "t3")),
    "EventB": frozenset(("b1", "b2", "b3", "t4", "t5", "t6")),
    "EventC": frozenset(("c1", "c2", "c3", "ht1", "ht2", "ht3")),
    "EventD": frozenset(("d1", "d2", "d3", "ht4", "ht5", "ht6")),
}


@dataclass(frozen=True)
class AlasEventSharedEntrySnapshot:
    task: str
    family: str
    stage: str
    event: str
    mode: str


def _text(field: str, value: object) -> str:
    if type(value) is not str or not value.strip():
        raise SemanticGateClosed(field + " must be nonempty text")
    return value.strip()


def validate_alas_event_shared_entry_config(
    *,
    task: object,
    stage: object,
    event: object,
    mode: object,
) -> Optional[AlasEventSharedEntrySnapshot]:
    """Classify an event entry without changing the original event runner.

    Non-event CampaignRun consumers pass through. Event folders must be exact
    repository-local event identifiers; task-specific stage aliases are kept
    compatible with the pinned ALAS A/B/C/D to T/HT conversion.
    """

    task_name = _text("campaign scheduler command", task)
    if task_name not in EVENT_COMMANDS:
        return None
    event_name = _text("Campaign.Event", event).lower()
    if _EVENT_FOLDER.fullmatch(event_name) is None:
        raise SemanticGateClosed(
            "Campaign.Event must be an exact event_YYYYMMDD_region folder"
        )
    mode_name = _text("Campaign.Mode", mode).lower()
    if mode_name not in {"normal", "hard"}:
        raise SemanticGateClosed("Campaign.Mode must be normal or hard")
    stage_name = _text("Campaign.Name", stage).lower()

    if task_name in EVENT_DIRECT_COMMANDS:
        family = "direct"
        if (
            stage_name == "dynamic"
            or ".." in stage_name
            or _DIRECT_STAGE.fullmatch(stage_name) is None
        ):
            raise SemanticGateClosed("direct Event stage is not a safe map name")
    elif task_name in EVENT_DAILY_COMMANDS:
        family = "daily"
        if mode_name != "normal":
            raise SemanticGateClosed("EventA-D entry mode must remain normal")
        if stage_name != "dynamic" and stage_name not in _DAILY_STAGES[task_name]:
            raise SemanticGateClosed(
                task_name + " stage is outside its A/B/C/D equivalence class"
            )
    else:
        family = "sp"
        if mode_name != "normal":
            raise SemanticGateClosed("EventSp entry mode must remain normal")
        if stage_name != "sp":
            raise SemanticGateClosed("EventSp Campaign.Name must be sp")

    return AlasEventSharedEntrySnapshot(
        task=task_name,
        family=family,
        stage=stage_name,
        event=event_name,
        mode=mode_name,
    )


__all__ = (
    "AlasEventSharedEntrySnapshot",
    "EVENT_COMMANDS",
    "EVENT_DIRECT_COMMANDS",
    "EVENT_SHARED_GROUPS",
    "EVENT_SP_COMMANDS",
    "validate_alas_event_shared_entry_config",
)
