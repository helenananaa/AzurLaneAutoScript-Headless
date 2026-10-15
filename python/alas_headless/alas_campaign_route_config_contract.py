"""Fail-closed route contract for the three normal Main task instances."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .semantic_oracle import SemanticGateClosed


MAIN_TASKS = ("Main", "Main2", "Main3")
MAIN_CAMPAIGN_EVENT = "campaign_main"
MAIN_CAMPAIGN_MODES = ("normal",)
_MODULE_PATTERN = re.compile(r"campaign_([1-9][0-9]*)_([1-4])")


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
    if not isinstance(stage, str):
        raise SemanticGateClosed("main campaign stage must be text")
    # Accept the spellings handled by ALAS's to_map_file_name. This only
    # classifies the route; ALAS still normalizes and loads the actual module.
    module_name = re.sub(r"[ \t\n]", "", stage).lower()
    if module_name and module_name[0].isdigit():
        module_name = "campaign_" + module_name.replace("-", "_")
    match = _MODULE_PATTERN.fullmatch(module_name)
    if match is None:
        raise SemanticGateClosed("main campaign stage must be chapter-section with section 1 to 4")
    if event != MAIN_CAMPAIGN_EVENT:
        raise SemanticGateClosed("main task cannot route to a non-main campaign")
    if mode not in MAIN_CAMPAIGN_MODES:
        raise SemanticGateClosed("main task mode is not supported by Headless")
    chapter, section = match.groups()
    return AlasMainCampaignRouteConfig(
        task=task,
        stage=f"{chapter}-{section}",
        event=event,
        mode=mode,
        module_name=module_name,
    )


__all__ = (
    "AlasMainCampaignRouteConfig",
    "MAIN_CAMPAIGN_EVENT",
    "MAIN_CAMPAIGN_MODES",
    "MAIN_TASKS",
    "validate_alas_main_campaign_route_config",
)
