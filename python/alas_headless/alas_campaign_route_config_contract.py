"""Fail-closed route contract for the three normal Main task instances."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .semantic_oracle import SemanticGateClosed


MAIN_TASKS = ("Main", "Main2", "Main3")
MAIN_CAMPAIGN_EVENT = "campaign_main"
MAIN_CAMPAIGN_MODES = ("normal",)
_STAGE_PATTERN = re.compile(r"^([1-9][0-9]*)-([1-4])$")


@dataclass(frozen=True)
class AlasMainCampaignRouteConfig:
    task: str
    stage: str
    event: str
    mode: str
    module_name: str


def validate_alas_main_campaign_route_config(
    *, task: object, stage: object, event: object, mode: object
) -> Optional[AlasMainCampaignRouteConfig]:
    """Validate Main routes; leave other campaign task families unchanged."""

    if not isinstance(task, str) or not task:
        raise SemanticGateClosed("campaign scheduler command is missing")
    if task not in MAIN_TASKS:
        return None
    if not isinstance(stage, str) or _STAGE_PATTERN.fullmatch(stage) is None:
        raise SemanticGateClosed("main campaign stage must be chapter-section with section 1 to 4")
    if event != MAIN_CAMPAIGN_EVENT:
        raise SemanticGateClosed("main task cannot route to a non-main campaign")
    if mode not in MAIN_CAMPAIGN_MODES:
        raise SemanticGateClosed("main task mode is not supported by Headless")
    chapter, section = stage.split("-", 1)
    return AlasMainCampaignRouteConfig(
        task=task,
        stage=stage,
        event=event,
        mode=mode,
        module_name=f"campaign_{chapter}_{section}",
    )


__all__ = (
    "AlasMainCampaignRouteConfig",
    "MAIN_CAMPAIGN_EVENT",
    "MAIN_CAMPAIGN_MODES",
    "MAIN_TASKS",
    "validate_alas_main_campaign_route_config",
)
