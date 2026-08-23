"""Input-free replay and source audit for the pinned ALAS Fleet surface."""

from __future__ import annotations

import ast
import hashlib
import json
import warnings
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Mapping

from .alas_fleet_config_contract import (
    FLEET_FORMATIONS,
    FLEET_MODES,
    FLEET_ORDERS,
    FLEET_STEPS,
    validate_alas_fleet_config,
)
from .semantic_oracle import SemanticGateClosed


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse(path: Path) -> ast.Module:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", SyntaxWarning)
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _method(path: Path, owner: str, name: str) -> object:
    tree = _parse(path)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != owner:
            continue
        for child in node.body:
            if isinstance(child, ast.FunctionDef) and child.name == name:
                namespace: dict[str, object] = {}
                module = ast.fix_missing_locations(
                    ast.Module(body=[child], type_ignores=[])
                )
                exec(
                    compile(module, "<alas-fleet-config-replay>", "exec"),
                    namespace,
                )
                compiled = namespace[name]
                return compiled.fget if isinstance(compiled, property) else compiled
    raise ValueError(f"missing ALAS method {owner}.{name}")


def _runtime_attribute_reads(
    module_root: Path,
    attribute: str,
    *,
    excluded: tuple[str, ...] = (),
) -> list[str]:
    matches: list[str] = []
    for path in sorted(module_root.rglob("*.py")):
        relative = path.relative_to(module_root.parent).as_posix()
        if path.name == "config_generated.py" or relative in excluded:
            continue
        tree = _parse(path)
        count = sum(
            1
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == attribute
        )
        matches.extend([relative] * count)
    return matches


def verify_fleet_config(alas_root: Path) -> Mapping[str, object]:
    alas_root = alas_root.resolve()
    paths = {
        "args": alas_root / "module/config/argument/args.json",
        "config": alas_root / "module/config/config.py",
        "fleet": alas_root / "module/map/fleet.py",
        "combat_auto": alas_root / "module/combat/combat_auto.py",
        "combat_manual": alas_root / "module/combat/combat_manual.py",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    args = json.loads(paths["args"].read_text(encoding="utf-8"))["Main"]["Fleet"]
    expected = {
        "Fleet1": tuple(range(1, 7)),
        "Fleet1Formation": FLEET_FORMATIONS,
        "Fleet1Mode": FLEET_MODES,
        "Fleet1Step": FLEET_STEPS,
        "Fleet2": tuple(range(0, 7)),
        "Fleet2Formation": FLEET_FORMATIONS,
        "Fleet2Mode": FLEET_MODES,
        "Fleet2Step": FLEET_STEPS,
        "FleetOrder": FLEET_ORDERS,
    }
    for field, values in expected.items():
        if tuple(args[field]["option"]) != values:
            raise AssertionError(f"pinned ALAS Fleet surface changed at {field}")

    defaults: dict[str, Any] = {
        "fleet1": 1,
        "fleet1_formation": "double_line",
        "fleet1_mode": "combat_auto",
        "fleet1_step": 3,
        "fleet2": 2,
        "fleet2_formation": "double_line",
        "fleet2_mode": "combat_auto",
        "fleet2_step": 2,
        "fleet_order": "fleet1_mob_fleet2_boss",
    }
    cases: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            raise AssertionError(name)
        cases.append(name)

    def classify(field: str, value: object) -> bool:
        values = dict(defaults)
        values[field] = value
        try:
            validate_alas_fleet_config(**values)
        except SemanticGateClosed:
            return False
        return True

    for value in expected["Fleet1"]:
        check(f"fleet1-{value}", classify("fleet1", value))
    for value in expected["Fleet2"]:
        check(f"fleet2-{value}", classify("fleet2", value))
    for side in ("fleet1", "fleet2"):
        for value in FLEET_FORMATIONS:
            check(
                f"{side}-formation-{value}",
                classify(f"{side}_formation", value)
                is (value == "double_line"),
            )
        for value in FLEET_MODES:
            check(
                f"{side}-mode-{value}",
                classify(f"{side}_mode", value) is (value == "combat_auto"),
            )
        for value in FLEET_STEPS:
            check(f"{side}-step-{value}", classify(f"{side}_step", value))
    for value in FLEET_ORDERS:
        check(
            f"fleet-order-{value}",
            classify("fleet_order", value)
            is (
                value
                in (
                    "fleet1_mob_fleet2_boss",
                    "fleet1_standby_fleet2_all",
                )
            ),
        )
    for field, value in (
        ("fleet1", 0),
        ("fleet1", True),
        ("fleet2", 7),
        ("fleet1_step", 1),
        ("fleet2_step", 6),
        ("fleet1_mode", "unknown"),
        ("fleet_order", "unknown"),
    ):
        check(f"invalid-{field}-{value}", not classify(field, value))

    fleet_step = _method(paths["fleet"], "Fleet", "fleet_step")
    for current in (1, 2):
        for reversed_ in (False, True):
            target = SimpleNamespace(
                config=SimpleNamespace(
                    MAP_HAS_FLEET_STEP=True,
                    Fleet_Fleet1Step=3,
                    Fleet_Fleet2Step=5,
                ),
                fleet_current_index=current,
                fleets_reversed=reversed_,
            )
            expected_step = 3 if (current == 1) != reversed_ else 5
            check(
                f"step-routing-{current}-{int(reversed_)}",
                MethodType(fleet_step, target)() == expected_step,
            )

    fleet_boss = _method(paths["config"], "AzurLaneConfig", "FLEET_BOSS")
    boss_results: dict[str, int] = {}
    for fleet2 in (0, 2):
        for order in FLEET_ORDERS:
            target = SimpleNamespace(
                _fleet_boss=0,
                Fleet_Fleet2=fleet2,
                Fleet_FleetOrder=order,
            )
            value = MethodType(fleet_boss, target)()
            expected_boss = 2 if fleet2 and order in FLEET_ORDERS[:2] else 1
            check(f"boss-routing-{fleet2}-{order}", value == expected_boss)
            boss_results[f"{fleet2}:{order}"] = value

    formation_reads = {
        field: _runtime_attribute_reads(
            alas_root / "module",
            field,
            excluded=("module/campaign/run.py",),
        )
        for field in ("Fleet_Fleet1Formation", "Fleet_Fleet2Formation")
    }
    formation_gate_reads = {
        field: _runtime_attribute_reads(alas_root / "module", field).count(
            "module/campaign/run.py"
        )
        for field in ("Fleet_Fleet1Formation", "Fleet_Fleet2Formation")
    }
    check(
        "formation1-is-runtime-noop",
        not formation_reads["Fleet_Fleet1Formation"],
    )
    check(
        "formation2-is-runtime-noop",
        not formation_reads["Fleet_Fleet2Formation"],
    )
    check(
        "formation-gate-read-is-bounded",
        all(value in (0, 1) for value in formation_gate_reads.values()),
    )

    auto_source = paths["combat_auto"].read_text(encoding="utf-8")
    manual_source = paths["combat_manual"].read_text(encoding="utf-8")
    for mode in FLEET_MODES:
        check(f"mode-source-{mode}", mode in auto_source or mode in manual_source)

    return {
        "schema": "alas-headless.fleet-config-replay/v1",
        "passed": True,
        "field_count": len(expected),
        "case_count": len(cases),
        "cases": cases,
        "accepted_semantic_modes": ["combat_auto"],
        "accepted_semantic_order": "fleet1_mob_fleet2_boss",
        "formation_runtime_reads": formation_reads,
        "formation_gate_reads": formation_gate_reads,
        "boss_results": boss_results,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {key: _sha256(path) for key, path in paths.items()},
    }
