"""Fail-closed contracts for the pinned ALAS Raid and RaidDaily settings."""

from __future__ import annotations

import re

from .semantic_oracle import SemanticGateClosed


RAID_MODES = frozenset(("easy", "normal", "hard", "ex"))
RAID_DAILY_STAGES = frozenset(("easy", "normal", "hard", "ex"))
_FILTER_SEPARATOR_TRANSLATION = str.maketrans("＞﹥›˃ᐳ❯", ">>>>>>")


def validate_alas_raid_mode(value: object) -> str:
    """Return one exact declared Raid mode before any RaidRun work starts."""

    if type(value) is not str or value not in RAID_MODES:
        raise SemanticGateClosed("Raid.Mode is outside the pinned enum")
    return value


def validate_alas_raid_use_ticket(value: object) -> bool:
    """Return an exact ticket boolean before either ticket button can be chosen."""

    if type(value) is not bool:
        raise SemanticGateClosed("Raid.UseTicket must be a boolean")
    return value


def validate_alas_raid_daily_stage_filter(value: object) -> str:
    """Canonicalize the source Filter separators and reject ambiguous stage tokens."""

    if type(value) is not str:
        raise SemanticGateClosed("RaidDaily.StageFilter must be text")
    normalized = re.sub(r"[ \t\r\n]", "", value).translate(_FILTER_SEPARATOR_TRANSLATION)
    tokens = normalized.lower().split(">")
    if not tokens or any(not token for token in tokens):
        raise SemanticGateClosed("RaidDaily.StageFilter contains an empty token")
    if len(tokens) != len(set(tokens)):
        raise SemanticGateClosed("RaidDaily.StageFilter contains duplicate stages")
    invalid = [token for token in tokens if token not in RAID_DAILY_STAGES]
    if invalid:
        raise SemanticGateClosed(
            "RaidDaily.StageFilter contains stages outside the pinned enum: "
            + ", ".join(invalid)
        )
    return " > ".join(tokens)
