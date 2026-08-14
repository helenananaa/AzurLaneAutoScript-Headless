"""Fail-closed contract for the pinned ALAS hard-mode task settings."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .semantic_oracle import SemanticGateClosed


HARD_STAGES = tuple(
    f"{chapter}-{stage}" for chapter in range(1, 17) for stage in range(1, 5)
)
_HARD_STAGE = re.compile(r"(?:campaign_)?([0-9]+)[_-]([0-9]+)", re.IGNORECASE)


@dataclass(frozen=True)
class AlasHardConfigSnapshot:
    hard_stage: str
    hard_fleet: int


def validate_alas_hard_config(
    *, hard_stage: object, hard_fleet: object
) -> AlasHardConfigSnapshot:
    """Return canonical hard-task values from the pinned 64-stage catalog."""

    if type(hard_stage) is not str:
        raise SemanticGateClosed("Hard.HardStage must be text")
    normalized = re.sub(r"[ \t\r\n]", "", hard_stage)
    match = _HARD_STAGE.fullmatch(normalized)
    if match is None:
        raise SemanticGateClosed("Hard.HardStage has an invalid format")
    canonical = f"{int(match.group(1))}-{int(match.group(2))}"
    if canonical not in HARD_STAGES:
        raise SemanticGateClosed("Hard.HardStage is outside the pinned map catalog")
    if type(hard_fleet) is not int or hard_fleet not in (1, 2):
        raise SemanticGateClosed("Hard.HardFleet must be integer 1 or 2")
    return AlasHardConfigSnapshot(hard_stage=canonical, hard_fleet=hard_fleet)
