"""Deterministic replay of pinned ALAS enemy-priority decisions."""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from .alas_enemy_priority_config_contract import (
    ENEMY_PRIORITY_MODES,
    validate_alas_enemy_priority_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.enemy-priority-config-replay/v1"
EXPECTED_CONSUMERS = {
    "clear_chosen_enemy",
    "clear_enemy",
    "clear_roadblocks",
    "clear_potential_roadblocks",
    "clear_filter_enemy",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> tuple[str, ...]:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    panels = []
    for panel, groups in document.items():
        if "EnemyPriority" not in groups:
            continue
        panels.append(panel)
        field = groups["EnemyPriority"].get("EnemyScaleBalanceWeight")
        if field is None or tuple(field.get("option", ())) != ENEMY_PRIORITY_MODES:
            raise AssertionError("EnemyPriority option surface drifted")
        if field.get("value") != "default_mode":
            raise AssertionError("EnemyPriority default drifted")
    if len(panels) != 11:
        raise AssertionError("EnemyPriority shared panel surface drifted")
    return tuple(panels)


def _verify_consumers(map_path: Path) -> tuple[str, ...]:
    tree = ast.parse(map_path.read_text(encoding="utf-8"), filename=str(map_path))
    consumers = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Attribute)
                and child.attr == "EnemyPriority_EnemyScaleBalanceWeight"
                and isinstance(child.ctx, ast.Load)
            ):
                consumers.add(node.name)
    if consumers != EXPECTED_CONSUMERS:
        raise AssertionError("EnemyPriority runtime consumer surface drifted")
    return tuple(sorted(consumers))


def _load_originals(alas_root: Path) -> tuple[type[Any], type[Any], type[Any]]:
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        map_module = importlib.import_module("module.map.map")
        grids_module = importlib.import_module("module.map.map_grids")
        grid_module = importlib.import_module("module.map_detection.grid_info")
        return map_module.Map, grids_module.SelectedGrids, grid_module.GridInfo
    finally:
        sys.path.remove(root)


def _grid(
    grid_type: type[Any],
    location: tuple[int, int],
    scale: int,
    genre: str,
    *,
    weight: int,
    cost: int,
) -> Any:
    grid = grid_type()
    grid.location = location
    grid.is_enemy = True
    grid.is_boss = False
    grid.enemy_scale = scale
    grid.enemy_genre = genre
    grid.weight = weight
    grid.cost = cost
    return grid


def _host(map_type: type[Any], selected_type: type[Any], grids: list[Any], mode: str):
    chosen = []

    def select(**values: object):
        return selected_type(grids).select(**values)

    host = SimpleNamespace(
        config=SimpleNamespace(
            EnemyPriority_EnemyScaleBalanceWeight=mode,
            MAP_CLEAR_ALL_THIS_TIME=False,
            MAP_HAS_MOVABLE_NORMAL_ENEMY=False,
        ),
        map=SimpleNamespace(select=select),
        select_grids=map_type.select_grids,
        show_select_grids=lambda *args, **kwargs: None,
        clear_chosen_enemy=lambda grid, expected="": chosen.append(str(grid)),
        clear_any_enemy=lambda **kwargs: False,
    )
    return host, chosen


def _verify_original_decisions(
    map_type: type[Any], selected_type: type[Any], grid_type: type[Any]
) -> dict[str, Any]:
    fixture = [
        _grid(grid_type, (0, 0), 3, "Enemy", weight=30, cost=4),
        _grid(grid_type, (1, 0), 1, "Light", weight=20, cost=2),
        _grid(grid_type, (2, 0), 2, "Main", weight=10, cost=1),
    ]
    clear_enemy = {}
    for mode, expected in (
        ("default_mode", "C1"),
        ("S1_enemy_first", "B1"),
        ("S3_enemy_first", "A1"),
    ):
        host, chosen = _host(map_type, selected_type, fixture, mode)
        if map_type.clear_enemy(host) is not True or chosen != [expected]:
            raise AssertionError("original clear_enemy priority drifted")
        clear_enemy[mode] = chosen[0]

    tie_fixture = [
        _grid(grid_type, (3, 0), 3, "Light", weight=20, cost=1),
        _grid(grid_type, (4, 0), 3, "Main", weight=10, cost=3),
        _grid(grid_type, (5, 0), 1, "Enemy", weight=1, cost=1),
    ]
    host, chosen = _host(map_type, selected_type, tie_fixture, "S3_enemy_first")
    if map_type.clear_enemy(host) is not True or chosen != ["E1"]:
        raise AssertionError("original same-scale tie ordering drifted")
    tie_choice = chosen[0]

    host, chosen = _host(map_type, selected_type, [], "S1_enemy_first")
    if map_type.clear_enemy(host) is not False or chosen:
        raise AssertionError("original empty-enemy behavior drifted")

    filter_enemy = {}
    for mode, filter_text, expected in (
        ("default_mode", "2M > 1L > 3E", "C1"),
        ("S1_enemy_first", "3E > 2M > 1L", "B1"),
        ("S3_enemy_first", "1L > 2M > 3E", "A1"),
    ):
        host, chosen = _host(map_type, selected_type, fixture, mode)
        if map_type.clear_filter_enemy(host, filter_text) is not True:
            raise AssertionError("original clear_filter_enemy returned no target")
        if chosen != [expected]:
            raise AssertionError("original filter priority override drifted")
        filter_enemy[mode] = chosen[0]

    return {
        "clear_enemy": clear_enemy,
        "clear_filter_enemy": filter_enemy,
        "same_scale_tie": tie_choice,
        "empty_enemy_returns_false": True,
        "final_input_boundaries_captured": 7,
    }


def verify_enemy_priority_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    panels = _verify_args(alas_root)
    map_path = alas_root / "module" / "map" / "map.py"
    consumers = _verify_consumers(map_path)
    map_type, selected_type, grid_type = _load_originals(alas_root)
    decisions = _verify_original_decisions(map_type, selected_type, grid_type)

    for mode in ENEMY_PRIORITY_MODES:
        snapshot = validate_alas_enemy_priority_config(
            enemy_scale_balance_weight=mode
        )
        if snapshot.enemy_scale_balance_weight != mode:
            raise AssertionError("EnemyPriority contract changed a valid value")
    invalid_count = 0
    for value in ("", "unknown", "s1_enemy_first", None, 1, True):
        try:
            validate_alas_enemy_priority_config(enemy_scale_balance_weight=value)
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid EnemyPriority value was admitted")

    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "panel_count": len(panels),
        "panels": list(panels),
        "accepted_modes": list(ENEMY_PRIORITY_MODES),
        "invalid_case_count": invalid_count,
        "runtime_consumers": list(consumers),
        "original_decisions": decisions,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "map": _sha256(map_path),
        },
    }
