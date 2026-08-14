"""Deterministic replay of pinned ALAS submarine configuration decisions."""

from __future__ import annotations

import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_submarine_config_contract import (
    SUBMARINE_AUTO_SEARCH_MODES,
    SUBMARINE_BOSS_DISTANCES,
    SUBMARINE_MODES,
    validate_alas_submarine_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.submarine-config-replay/v1"
FIELD_NAMES = ("Fleet", "Mode", "AutoSearchMode", "DistanceToBoss")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> tuple[str, ...]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panels = []
    for panel, groups in document.items():
        if "Submarine" not in groups:
            continue
        panels.append(panel)
        group = groups["Submarine"]
        if tuple(group) != FIELD_NAMES:
            raise AssertionError("Submarine field set or order drifted")
        if tuple(group["Fleet"].get("option", ())) != (0, 1, 2):
            raise AssertionError("Submarine fleet surface drifted")
        expected_modes = (
            ("do_not_use", "hunt_only")
            if panel == "GemsFarming"
            else SUBMARINE_MODES
        )
        if tuple(group["Mode"].get("option", ())) != expected_modes:
            raise AssertionError("Submarine mode surface drifted")
        if (
            tuple(group["AutoSearchMode"].get("option", ()))
            != SUBMARINE_AUTO_SEARCH_MODES
        ):
            raise AssertionError("Submarine auto-search surface drifted")
        if (
            tuple(group["DistanceToBoss"].get("option", ()))
            != SUBMARINE_BOSS_DISTANCES
        ):
            raise AssertionError("Submarine distance surface drifted")
    if len(panels) != 12:
        raise AssertionError("Submarine shared panel surface drifted")
    return tuple(panels)


def _load_originals(alas_root: Path) -> dict[str, Any]:
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return {
            "call": importlib.import_module("module.combat.submarine").SubmarineCall,
            "fleet": importlib.import_module("module.map.fleet").Fleet,
            "fast": importlib.import_module(
                "module.handler.fast_forward"
            ).FastForwardHandler,
            "selected": importlib.import_module("module.map.map_grids").SelectedGrids,
            "grid": importlib.import_module("module.map_detection.grid_info").GridInfo,
        }
    finally:
        sys.path.remove(root)


class _Timer:
    def __init__(self, reached: bool):
        self.value = reached
        self.resets = 0

    def reached(self) -> bool:
        return self.value

    def reset(self) -> None:
        self.resets += 1


def _call_decision(call_type: type[Any], mode: str) -> tuple[object, int]:
    clicks = []
    host = SimpleNamespace(
        submarine_call_flag=False,
        submarine_call_timer=_Timer(False),
        submarine_call_click_timer=_Timer(True),
        appear=lambda target: "CALLED" not in str(target),
        appear_then_click=lambda target: clicks.append(str(target)) or True,
        device=SimpleNamespace(click=lambda target: clicks.append(str(target))),
        map=SimpleNamespace(spawn_data=[]),
        battle_count=0,
    )
    result = call_type.handle_submarine_call(host, mode)
    return result, len(clicks)


def _grid(grid_type: type[Any], location: tuple[int, int], cost: int) -> Any:
    grid = grid_type()
    grid.location = location
    grid.cost = cost
    grid.is_land = False
    grid.is_submarine_spawn_point = False
    return grid


def _distance_decisions(
    fleet_type: type[Any], selected_type: type[Any], grid_type: type[Any]
) -> dict[str, object]:
    spawn = _grid(grid_type, (0, 1), 0)
    spawn.is_submarine_spawn_point = True
    sea = [
        _grid(grid_type, (5, 5), 3),
        _grid(grid_type, (4, 5), 2),
        _grid(grid_type, (3, 5), 1),
    ]
    decisions = {}
    for distance in SUBMARINE_BOSS_DISTANCES:
        moved = []

        def select(**values: object):
            if values == {"is_submarine_spawn_point": True}:
                return selected_type([spawn])
            if values == {"is_land": False}:
                return selected_type(sea)
            raise AssertionError("unexpected original submarine map query")

        host = SimpleNamespace(
            is_call_submarine_at_boss=True,
            config=SimpleNamespace(Submarine_DistanceToBoss=distance),
            map=SimpleNamespace(
                select=select,
                find_path_initial=lambda *args, **kwargs: None,
                show_cost=lambda: None,
            ),
            fleet_submarine_location=(0, 0),
            find_path_initial=lambda: None,
            submarine_goto=lambda location: moved.append(tuple(location)) or True,
        )
        result = fleet_type.submarine_move_near_boss(host, (5, 5))
        decisions[distance] = {
            "result": bool(result),
            "target": list(moved[0]) if moved else None,
        }
    expected = {
        "to_boss_position": [5, 5],
        "1_grid_to_boss": [4, 5],
        "2_grid_to_boss": [3, 5],
        "use_open_ocean_support": None,
    }
    if {key: value["target"] for key, value in decisions.items()} != expected:
        raise AssertionError("original submarine distance decision drifted")
    return decisions


def _verify_original(originals: dict[str, Any]) -> dict[str, Any]:
    call_modes = {}
    final_boundaries = 0
    for mode in SUBMARINE_MODES:
        result, clicks = _call_decision(originals["call"], mode)
        call_modes[mode] = result
        final_boundaries += clicks
        if mode in ("boss_only", "every_combat"):
            if result is not True or clicks != 1:
                raise AssertionError("original submarine call decision drifted")
        elif result is not False or clicks:
            raise AssertionError("inactive original submarine call drifted")

    boss_modes = {}
    for active in (False, True):
        for expected in ("combat", "combat_boss"):
            host = SimpleNamespace(is_call_submarine_at_boss=active)
            result = originals["fleet"]._submarine_mode(host, expected)
            boss_modes[f"{active}:{expected}"] = result

    auto_modes = {}
    for mode in SUBMARINE_AUTO_SEARCH_MODES:
        calls = []
        host = SimpleNamespace(
            map_is_auto_search=True,
            config=SimpleNamespace(
                SUBMARINE=True,
                Fleet_FleetOrder="fleet1_mob_fleet2_boss",
                Submarine_AutoSearchMode=mode,
            ),
            fleet_preparation_sidebar_ensure=lambda value: calls.append(
                "sidebar:" + str(value)
            ),
            auto_search_setting_ensure=lambda value: calls.append(value),
        )
        if originals["fast"].handle_auto_search_setting(host) is not True:
            raise AssertionError("original submarine auto-search setting drifted")
        if calls[-1] != mode:
            raise AssertionError("original submarine auto-search value drifted")
        auto_modes[mode] = calls

    return {
        "combat_call_modes": call_modes,
        "boss_mode_mapping": boss_modes,
        "auto_search_modes": auto_modes,
        "distance_decisions": _distance_decisions(
            originals["fleet"], originals["selected"], originals["grid"]
        ),
        "unqualified_final_input_boundaries": final_boundaries,
    }


def verify_submarine_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    panels = _verify_args(alas_root)
    originals = _load_originals(alas_root)
    decisions = _verify_original(originals)

    accepted_count = 0
    for mode in SUBMARINE_MODES:
        for auto in SUBMARINE_AUTO_SEARCH_MODES:
            for distance in SUBMARINE_BOSS_DISTANCES:
                validate_alas_submarine_config(
                    fleet=0,
                    mode=mode,
                    auto_search_mode=auto,
                    distance_to_boss=distance,
                )
                accepted_count += 1
    refused_active_count = 0
    for fleet in (1, 2):
        for mode in SUBMARINE_MODES:
            try:
                validate_alas_submarine_config(
                    fleet=fleet,
                    mode=mode,
                    auto_search_mode="sub_standby",
                    distance_to_boss="2_grid_to_boss",
                )
            except SemanticGateClosed:
                refused_active_count += 1
            else:
                raise AssertionError("active submarine fleet was admitted")
    invalid_count = 0
    for field, value in (
        ("fleet", -1),
        ("fleet", 3),
        ("fleet", True),
        ("mode", "unknown"),
        ("auto_search_mode", "unknown"),
        ("distance_to_boss", "unknown"),
    ):
        values = {
            "fleet": 0,
            "mode": "do_not_use",
            "auto_search_mode": "sub_standby",
            "distance_to_boss": "2_grid_to_boss",
        }
        values[field] = value
        try:
            validate_alas_submarine_config(**values)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid submarine value was admitted")

    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": len(FIELD_NAMES),
        "panel_count": len(panels),
        "panels": list(panels),
        "accepted_inactive_count": accepted_count,
        "refused_active_count": refused_active_count,
        "invalid_case_count": invalid_count,
        "original_decisions": decisions,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            name: _sha256(alas_root / relative)
            for name, relative in {
                "args": "module/config/argument/args.json",
                "call": "module/combat/submarine.py",
                "fleet": "module/map/fleet.py",
                "fast": "module/handler/fast_forward.py",
            }.items()
        },
    }
