"""Replay all Main/Main2/Main3 routes through pinned ALAS stage handling."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

from .alas_campaign_route_config_contract import (
    MAIN_TASKS,
    validate_alas_main_campaign_route_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.main-campaign-route-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _main_catalog(alas_root: Path) -> tuple[str, ...]:
    root = alas_root / "campaign" / "campaign_main"
    key = lambda value: tuple(int(part) for part in value.split("-"))
    stages = tuple(sorted(
        (
            path.stem.removeprefix("campaign_").replace("_", "-")
            for path in root.glob("campaign_[0-9]*_[0-9].py")
        ),
        key=key,
    ))
    expected = tuple(
        f"{chapter}-{section}" for chapter in range(1, 17) for section in range(1, 5)
    )
    if stages != expected:
        raise AssertionError("pinned main campaign module catalog drifted")
    return stages


def _load_run_module(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.campaign.run")
    finally:
        sys.path.remove(root)


def _original_route(module: Any, stage: str) -> tuple[str, str]:
    host = object.__new__(module.CampaignRun)
    host.config = SimpleNamespace(
        task=SimpleNamespace(command="Main"),
        STAGE_ENTRANCE=(),
        STAGE_LOOP_ALIAS={},
        StopCondition_RunCount=1,
        StopCondition_MapAchievement="non_stop",
        StopCondition_StageIncrease=False,
    )
    name, folder = module.CampaignRun.handle_stage_name(
        host, stage, "campaign_main", mode="normal"
    )
    return str(name), str(folder)


def verify_main_campaign_routes(alas_root: Path) -> Mapping[str, object]:
    alas_root = alas_root.resolve()
    template_path = alas_root / "config" / "template.json"
    run_path = alas_root / "module" / "campaign" / "run.py"
    template = json.loads(template_path.read_text(encoding="utf-8"))
    stages = _main_catalog(alas_root)
    module = _load_run_module(alas_root)
    routes: dict[str, object] = {}
    for task in MAIN_TASKS:
        task_config = template.get(task)
        if not isinstance(task_config, dict):
            raise AssertionError(f"{task} template instance is missing")
        if task_config["Scheduler"].get("Command") != task:
            raise AssertionError(f"{task} scheduler command drifted")
        accepted = []
        for stage in stages:
            route = validate_alas_main_campaign_route_config(
                task=task, stage=stage, event="campaign_main", mode="normal"
            )
            if route is None:
                raise AssertionError(f"{task} route was not classified")
            original_name, original_folder = _original_route(module, stage)
            if original_name != route.module_name or original_folder != route.event:
                raise AssertionError(f"{task} {stage} original route drifted")
            accepted.append(stage)
        routes[task] = {
            "accepted_stage_count": len(accepted),
            "first_stage": accepted[0],
            "last_stage": accepted[-1],
            "scheduler_command": task,
        }

    invalid_values = (
        ("Main", "0-1", "campaign_main", "normal"),
        ("Main", "-1-1", "campaign_main", "normal"),
        ("Main2", "12-5", "campaign_main", "normal"),
        ("Main3", "campaign_12_4", "campaign_main", "normal"),
        ("Main", "12-4", "event_20260813_cn", "normal"),
        ("Main2", "12-4", "campaign_main", "hard"),
        ("Main3", "12-4", "campaign_main", None),
        (None, "12-4", "campaign_main", "normal"),
    )
    for task, stage, event, mode in invalid_values:
        try:
            validate_alas_main_campaign_route_config(
                task=task, stage=stage, event=event, mode=mode
            )
        except SemanticGateClosed:
            pass
        else:
            raise AssertionError("invalid main campaign route was admitted")
    if validate_alas_main_campaign_route_config(
        task="Event", stage="A1", event="event_20260813_cn", mode="normal"
    ) is not None:
        raise AssertionError("non-main campaign task was unexpectedly constrained")

    return {
        "schema": SCHEMA,
        "passed": True,
        "task_count": len(MAIN_TASKS),
        "stage_count": len(stages),
        "accepted_route_count": len(MAIN_TASKS) * len(stages),
        "invalid_case_count": len(invalid_values),
        "routes": routes,
        "source_sha256": {
            "template": _sha256(template_path),
            "run": _sha256(run_path),
        },
        "mutation_budget": 0,
        "android_input_injected": False,
    }


__all__ = ("SCHEMA", "verify_main_campaign_routes")
