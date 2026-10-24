"""Fail-closed contracts for EventA-D daily stage rotation settings."""

from __future__ import annotations

import re

from .semantic_oracle import SemanticGateClosed


EVENT_DAILY_COMMANDS = ("EventA", "EventB", "EventC", "EventD")
_FILTER_SEPARATOR_TRANSLATION = str.maketrans("＞﹥›˃ᐳ❯", ">>>>>>")


def _event_prefix(task_command: object) -> str:
    if type(task_command) is not str or task_command not in EVENT_DAILY_COMMANDS:
        raise SemanticGateClosed("EventDaily requires EventA, EventB, EventC, or EventD")
    return task_command[-1].lower()


def validate_alas_event_daily_stage_filter(
    stage_filter: object, *, task_command: object
) -> str:
    """Return the canonical filter while rejecting cross-panel or partial tokens."""

    prefix = _event_prefix(task_command)
    if type(stage_filter) is not str:
        raise SemanticGateClosed("EventDaily.StageFilter must be text")
    normalized = re.sub(r"[ \t\r\n]", "", stage_filter)
    normalized = normalized.translate(_FILTER_SEPARATOR_TRANSLATION)
    tokens = normalized.lower().split(">")
    if not tokens or any(not token for token in tokens):
        raise SemanticGateClosed("EventDaily.StageFilter contains an empty token")
    if len(tokens) != len(set(tokens)):
        raise SemanticGateClosed("EventDaily.StageFilter contains duplicate stages")
    allowed = {f"{prefix}{number}" for number in range(1, 4)}
    invalid = [token for token in tokens if token not in allowed]
    if invalid:
        raise SemanticGateClosed(
            "EventDaily.StageFilter contains stages outside the current panel: "
            + ", ".join(invalid)
        )
    return " > ".join(token.upper() for token in tokens)


def validate_alas_event_daily_last_stage(
    last_stage: object, *, task_command: object
) -> int | str:
    """Validate a non-stale rotation cursor for the current A-D panel."""

    prefix = _event_prefix(task_command)
    if type(last_stage) is int and last_stage == 0:
        return 0
    if type(last_stage) is not str:
        raise SemanticGateClosed("EventDaily.LastStage must be 0 or a stage name")
    normalized = last_stage.strip().lower()
    allowed = {f"{prefix}{number}" for number in range(1, 4)}
    # CampaignABCD persists the physical name returned by native convert_stages,
    # not necessarily the user's A/B/C/D filter spelling. Keep that cursor so
    # native rotation can skip the completed stage on the next invocation.
    numbers = range(1, 4) if prefix in ('a', 'c') else range(4, 7)
    aliases = ('t',) if prefix in ('a', 'b') else ('ht', 'th')
    allowed.update(f'{alias}{number}' for alias in aliases for number in numbers)
    if normalized not in allowed:
        raise SemanticGateClosed(
            "EventDaily.LastStage does not belong to the current panel"
        )
    return normalized
