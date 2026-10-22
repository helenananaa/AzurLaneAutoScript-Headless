"""Deterministic replay of pinned ALAS hard-mode configuration decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_hard_config_contract import HARD_STAGES, validate_alas_hard_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.hard-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> dict[str, object]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panel = document.get("Hard")
    group = panel.get("Hard") if isinstance(panel, dict) else None
    if not isinstance(group, dict) or set(group) != {"HardStage", "HardFleet"}:
        raise AssertionError("Hard field surface drifted")
    if group["HardStage"].get("type") != "input" or group["HardStage"].get(
        "value"
    ) != "11-4":
        raise AssertionError("Hard.HardStage surface drifted")
    if (
        group["HardFleet"].get("type") != "select"
        or group["HardFleet"].get("option") != [1, 2]
        or group["HardFleet"].get("value") != 1
    ):
        raise AssertionError("Hard.HardFleet surface drifted")
    return {"HardStage": "11-4", "HardFleet": 1}


def _verify_catalog(alas_root: Path) -> list[str]:
    root = alas_root / "campaign" / "campaign_main"
    catalog = []
    for path in root.glob("campaign_*_*.py"):
        parts = path.stem.split("_")
        if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit():
            catalog.append(f"{int(parts[1])}-{int(parts[2])}")
    catalog.sort(key=lambda value: tuple(map(int, value.split("-"))))
    if tuple(catalog) != HARD_STAGES:
        raise AssertionError("pinned hard-stage module catalog drifted")
    return catalog


def _verify_consumers(path: Path) -> dict[str, list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    hard = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "CampaignHard"
    )
    methods = {
        node.name: node
        for node in hard.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    run = methods.get("run")
    run_hard = methods.get("_run_hard")
    if run is None or run_hard is None:
        raise AssertionError("CampaignHard runtime surface drifted")
    run_attributes = {
        node.attr for node in ast.walk(run) if isinstance(node, ast.Attribute)
    }
    if not {"Hard_HardStage", "Hard_HardFleet"}.issubset(run_attributes):
        raise AssertionError("Hard configuration consumers drifted")
    calls = {
        node.func.id
        for node in ast.walk(run)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    return {
        "Hard.HardStage": ["CampaignHard.run", "CampaignHard._run_hard"],
        "Hard.HardFleet": ["CampaignHard.run", "CampaignHard._run_hard"],
        "patched_guards": sorted(calls & {"validate_alas_hard_config"}),
    }


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        module = importlib.import_module("module.hard.hard")
        return module, module.CampaignHard
    finally:
        sys.path.remove(root)


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for stage in HARD_STAGES:
        snapshot = validate_alas_hard_config(hard_stage=stage, hard_fleet=1)
        if snapshot.hard_stage != stage:
            raise AssertionError("canonical Hard.HardStage drifted")
        accepted += 1
    for value in (" campaign_11_4 ", "11_4", "01-04"):
        validate_alas_hard_config(hard_stage=value, hard_fleet=1)
        accepted += 1
    validate_alas_hard_config(hard_stage="11-4", hard_fleet=2)
    accepted += 1
    for value in (
        "",
        "0-1",
        "1-0",
        "-1-1",
        "1-5",
        "1",
        "campaign_1_1junk",
        "A1",
        None,
        1,
    ):
        try:
            validate_alas_hard_config(hard_stage=value, hard_fleet=1)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Hard.HardStage was admitted")
    for value in (0, 3, -1, True, "1", 1.0, None):
        try:
            validate_alas_hard_config(hard_stage="11-4", hard_fleet=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Hard.HardFleet was admitted")
    return accepted, invalid


class ReplayConfig:
    def __init__(self, *, stage: object, fleet: object):
        self.Hard_HardStage = stage
        self.Hard_HardFleet = fleet
        self.events: list[tuple[Any, ...]] = []

    def override(self, **kwargs: object) -> None:
        self.events.append(("override", kwargs))
        for key, value in kwargs.items():
            setattr(self, key, value)

    def task_delay(self, **kwargs: object) -> None:
        self.events.append(("delay", kwargs))

    def task_call(self, name: str) -> None:
        self.events.append(("call", name))


def _run_case(
    module: Any,
    hard_type: type[Any],
    *,
    stage: object,
    fleet: object,
    remain: int,
) -> dict[str, Any]:
    host = object.__new__(hard_type)
    host.config = ReplayConfig(stage=stage, fleet=fleet)
    events: list[tuple[Any, ...]] = []
    host.device = SimpleNamespace(
        semantic_adapter=None,
        image="fixture-frame",
        screenshot=lambda: events.append(("screenshot",)),
    )
    campaign = SimpleNamespace(
        device=SimpleNamespace(image=None),
        MAP=None,
        ensure_campaign_ui=lambda **kwargs: events.append(("ensure_ui", kwargs)),
        run=lambda: events.append(("campaign_run",)),
        ensure_auto_search_exit=lambda: events.append(("auto_search_exit",)),
    )

    def load_campaign(name: str, *, folder: str) -> None:
        events.append(("load_campaign", name, folder))
        host.campaign = campaign

    host.load_campaign = load_campaign
    old_import = module.importlib.import_module
    old_ocr = module.OCR_HARD_REMAIN
    module.importlib.import_module = lambda name, package: (
        events.append(("import", name, package)) or SimpleNamespace(MAP="fixture-map")
    )
    module.OCR_HARD_REMAIN = SimpleNamespace(ocr=lambda image: remain)
    try:
        hard_type.run(host)
    finally:
        module.importlib.import_module = old_import
        module.OCR_HARD_REMAIN = old_ocr
    return {
        "events": events,
        "config_events": host.config.events,
        "campaign_runs": sum(event[0] == "campaign_run" for event in events),
        "campaign_map": campaign.MAP,
        "campaign_image": campaign.device.image,
    }


def _invalid_case(
    hard_type: type[Any], *, stage: object = "11-4", fleet: object = 1
) -> list[tuple[Any, ...]]:
    host = object.__new__(hard_type)
    host.config = ReplayConfig(stage=stage, fleet=fleet)
    events = []
    host.device = SimpleNamespace(
        semantic_adapter=None,
        image=None,
        screenshot=lambda: events.append(("screenshot",)),
    )
    host.load_campaign = lambda *args, **kwargs: events.append(("load",))
    try:
        hard_type.run(host)
    except SemanticGateClosed:
        pass
    else:
        raise AssertionError("invalid Hard configuration entered CampaignHard.run")
    if events or host.config.events:
        raise AssertionError("invalid Hard configuration caused a mutation")
    return events


def _verify_original(module: Any, hard_type: type[Any]) -> dict[str, Any]:
    fleet_one = _run_case(
        module, hard_type, stage=" campaign_11_4 ", fleet=1, remain=3
    )
    fleet_two = _run_case(module, hard_type, stage="16_4", fleet=2, remain=0)
    first_override = fleet_one["config_events"][0][1]
    second_override = fleet_two["config_events"][0][1]
    if first_override["Fleet_FleetOrder"] != "fleet1_all_fleet2_standby":
        raise AssertionError("Hard fleet-one order drifted")
    if second_override["Fleet_FleetOrder"] != "fleet1_standby_fleet2_all":
        raise AssertionError("Hard fleet-two order drifted")
    if fleet_one["campaign_runs"] != 3 or fleet_two["campaign_runs"] != 0:
        raise AssertionError("Hard remaining-run loop drifted")
    if ("import", ".campaign_11_4", "campaign.campaign_main") not in fleet_one[
        "events"
    ]:
        raise AssertionError("Hard stage module conversion drifted")
    if ("ensure_ui", {"name": "11-4", "mode": "hard"}) not in fleet_one["events"]:
        raise AssertionError("Hard canonical UI stage drifted")
    if fleet_one["campaign_map"] != "fixture-map" or fleet_one[
        "campaign_image"
    ] != "fixture-frame":
        raise AssertionError("Hard campaign initialization drifted")
    if fleet_one["config_events"][-2:] != [
        ("delay", {"server_update": True}),
        ("call", "Reward"),
    ]:
        raise AssertionError("Hard scheduler completion drifted")
    return {
        "fleet_one": fleet_one,
        "fleet_two": fleet_two,
        "invalid_stage_events": _invalid_case(hard_type, stage="-1-1"),
        "invalid_fleet_events": _invalid_case(hard_type, fleet=True),
    }


def verify_hard_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    defaults = _verify_args(alas_root)
    catalog = _verify_catalog(alas_root)
    source = alas_root / "module" / "hard" / "hard.py"
    consumers = _verify_consumers(source)
    module, hard_type = _load_original(alas_root)
    accepted, invalid = _verify_contract()
    original = _verify_original(module, hard_type)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "catalog_count": len(catalog),
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "defaults": defaults,
        "runtime_consumers": consumers,
        "original_decisions": original,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module" / "config" / "argument" / "args.json"),
            "hard": _sha256(source),
        },
    }
