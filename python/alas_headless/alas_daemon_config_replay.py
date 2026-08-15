"""Deterministic replay of pinned ALAS daemon configuration branches."""

from __future__ import annotations

import ast
import hashlib
import importlib
import itertools
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_daemon_config_contract import (
    validate_alas_daemon_config,
    validate_alas_opsi_daemon_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.daemon-config-replay/v1"
INVALID_BOOLEANS = (0, 1, "true", "false", None, [], {})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    expected = {
        ("Daemon", "Daemon", "EnterMap"): True,
        ("OpsiDaemon", "OpsiDaemon", "RepairShip"): True,
        ("OpsiDaemon", "OpsiDaemon", "SelectEnemy"): True,
    }
    for (panel, group, field), default in expected.items():
        declaration = document.get(panel, {}).get(group, {}).get(field)
        if (
            not isinstance(declaration, dict)
            or declaration.get("type") != "checkbox"
            or declaration.get("value") is not default
        ):
            raise AssertionError(f"{group}.{field} declaration drifted")


def _run_once_ast(
    path: Path, field_names: tuple[str, ...], guard_name: str
) -> tuple[dict[str, list[str]], bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    target = next(
        (
            node
            for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "AzurLaneDaemon"
        ),
        None,
    )
    if target is None:
        raise AssertionError(f"AzurLaneDaemon is missing from {path.name}")
    run_once = next(
        (
            node
            for node in target.body
            if isinstance(node, ast.FunctionDef) and node.name == "run_once"
        ),
        None,
    )
    if run_once is None:
        raise AssertionError(f"run_once is missing from {path.name}")
    consumers = {field: [] for field in field_names}
    for field in consumers:
        if any(
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == field
            for node in ast.walk(run_once)
        ):
            consumers[field].append("run_once")
    if consumers != {field: ["run_once"] for field in consumers}:
        raise AssertionError(f"daemon consumer surface drifted in {path.name}")
    guard = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == guard_name
        for node in ast.walk(run_once)
    )
    if guard:
        executable = [
            statement
            for statement in run_once.body
            if not isinstance(statement, (ast.Import, ast.ImportFrom))
            and not (
                isinstance(statement, ast.Expr)
                and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            )
        ]
        first = executable[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == guard_name
        ):
            raise AssertionError(f"daemon guard is not first in {path.name}")
    return consumers, guard


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        daemon = importlib.import_module("module.daemon.daemon")
        opsi = importlib.import_module("module.daemon.os_daemon")
        return daemon, opsi
    finally:
        sys.path.remove(root)


class _Config(SimpleNamespace):
    def __init__(self, *, enter_map: object, repair_ship: object, select_enemy: object, events: list[Any]):
        super().__init__(
            Daemon_EnterMap=enter_map,
            OpsiDaemon_RepairShip=repair_ship,
            OpsiDaemon_SelectEnemy=select_enemy,
        )
        self.events = events

    def merge(self, value):
        self.events.append("config_merge")

    def override(self, **kwargs):
        self.events.append(["config_override", kwargs])


def _base_host(module: Any, *, enter_map: object, repair_ship: object, select_enemy: object):
    events: list[Any] = []
    host = object.__new__(module.AzurLaneDaemon)
    host.config = _Config(
        enter_map=enter_map,
        repair_ship=repair_ship,
        select_enemy=select_enemy,
        events=events,
    )
    host.device = SimpleNamespace(
        semantic_adapter=None,
        screenshot=lambda: events.append("screenshot"),
        sleep=lambda value: events.append(["sleep", value]),
    )
    false_methods = (
        "is_in_main",
        "is_combat_executing",
        "combat_appear",
        "handle_battle_status",
        "handle_mystery_items",
        "handle_retirement",
        "handle_urgent_commission",
        "handle_guild_popup_cancel",
        "handle_vote_popup",
        "story_skip",
        "handle_map_event",
    )
    for name in false_methods:
        if hasattr(module.AzurLaneDaemon, name):
            setattr(host, name, MethodType(lambda self: False, host))
    return host, events


def _run_daemon_case(daemon_module: Any, *, enter_map: object, target: str | None = None):
    host, events = _base_host(
        daemon_module,
        enter_map=enter_map,
        repair_ship=False,
        select_enemy=False,
    )
    host.appear_then_click = MethodType(
        lambda self, button, **kwargs: events.append(
            [
                "appear_then_click",
                "map" if button is daemon_module.MAP_PREPARATION else
                "fleet" if button is daemon_module.FLEET_PREPARATION else "other",
            ]
        )
        or (
            (target == "map" and button is daemon_module.MAP_PREPARATION)
            or (target == "fleet" and button is daemon_module.FLEET_PREPARATION)
        ),
        host,
    )
    result = daemon_module.AzurLaneDaemon.run_once(host)
    return {"result": result, "events": events}


def _run_opsi_case(
    opsi_module: Any,
    *,
    repair_ship: object,
    select_enemy: object,
    port_visible: bool = False,
    enemy_visible: bool = False,
):
    host, events = _base_host(
        opsi_module,
        enter_map=False,
        repair_ship=repair_ship,
        select_enemy=select_enemy,
    )
    host.appear_then_click = MethodType(lambda self, button, **kwargs: False, host)
    host.appear = MethodType(
        lambda self, button, **kwargs: events.append("port_probe")
        or (port_visible and button is opsi_module.PORT_ENTER),
        host,
    )
    for name in ("port_enter", "port_dock_repair", "port_quit"):
        setattr(
            host,
            name,
            MethodType(lambda self, _name=name: events.append(_name), host),
        )
    host.interval_reset = MethodType(
        lambda self, button: events.append("port_interval_reset"), host
    )
    host.click_nearest_object = MethodType(
        lambda self: events.append("enemy_probe") or enemy_visible, host
    )
    result = opsi_module.AzurLaneDaemon.run_once(host)
    return {"result": result, "events": events}


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    for enter_map in (False, True):
        validate_alas_daemon_config(enter_map=enter_map)
        accepted += 1
    for repair_ship, select_enemy in itertools.product((False, True), repeat=2):
        validate_alas_opsi_daemon_config(
            repair_ship=repair_ship, select_enemy=select_enemy
        )
        accepted += 1
    invalid = 0
    for value in INVALID_BOOLEANS:
        try:
            validate_alas_daemon_config(enter_map=value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Daemon.EnterMap was admitted")
    for field in ("repair_ship", "select_enemy"):
        for value in INVALID_BOOLEANS:
            case = {"repair_ship": True, "select_enemy": True}
            case[field] = value
            try:
                validate_alas_opsi_daemon_config(**case)
            except SemanticGateClosed:
                invalid += 1
            else:
                raise AssertionError(f"invalid OpsiDaemon {field} was admitted")
    return accepted, invalid


def _verify_invalid_entry(daemon_module: Any, opsi_module: Any, guards: tuple[bool, bool]):
    if not all(guards):
        return {}
    result = {}
    for name, callback in {
        "Daemon_EnterMap": lambda: _run_daemon_case(daemon_module, enter_map=1),
        "OpsiDaemon_RepairShip": lambda: _run_opsi_case(
            opsi_module, repair_ship=1, select_enemy=True
        ),
        "OpsiDaemon_SelectEnemy": lambda: _run_opsi_case(
            opsi_module, repair_ship=True, select_enemy="true"
        ),
    }.items():
        try:
            callback()
        except SemanticGateClosed:
            result[name] = []
        else:
            raise AssertionError(f"patched daemon admitted invalid {name}")
    return result


def verify_daemon_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    daemon_path = alas_root / "module/daemon/daemon.py"
    opsi_path = alas_root / "module/daemon/os_daemon.py"
    daemon_consumers, daemon_guard = _run_once_ast(
        daemon_path, ("Daemon_EnterMap",), "validate_alas_daemon_config"
    )
    opsi_consumers, opsi_guard = _run_once_ast(
        opsi_path,
        ("OpsiDaemon_RepairShip", "OpsiDaemon_SelectEnemy"),
        "validate_alas_opsi_daemon_config",
    )
    daemon_module, opsi_module = _load_original(alas_root)
    daemon_cases = {
        "disabled": _run_daemon_case(daemon_module, enter_map=False),
        "enabled_absent": _run_daemon_case(daemon_module, enter_map=True),
        "map": _run_daemon_case(daemon_module, enter_map=True, target="map"),
        "fleet": _run_daemon_case(daemon_module, enter_map=True, target="fleet"),
    }
    opsi_cases = {
        "disabled": _run_opsi_case(
            opsi_module, repair_ship=False, select_enemy=False
        ),
        "repair_absent_select_absent": _run_opsi_case(
            opsi_module, repair_ship=True, select_enemy=True
        ),
        "repair": _run_opsi_case(
            opsi_module,
            repair_ship=True,
            select_enemy=True,
            port_visible=True,
        ),
        "select": _run_opsi_case(
            opsi_module,
            repair_ship=False,
            select_enemy=True,
            enemy_visible=True,
        ),
    }
    disabled_targets = tuple(
        event[1]
        for event in daemon_cases["disabled"]["events"]
        if isinstance(event, list)
        and event[:1] == ["appear_then_click"]
        and event[1] in ("map", "fleet")
    )
    if disabled_targets:
        raise AssertionError("disabled Daemon.EnterMap touched map input")
    enabled_targets = tuple(
        event[1]
        for event in daemon_cases["enabled_absent"]["events"]
        if isinstance(event, list)
        and event[:1] == ["appear_then_click"]
        and event[1] in ("map", "fleet")
    )
    if enabled_targets != ("map", "fleet"):
        raise AssertionError("enabled Daemon.EnterMap probe order drifted")
    if daemon_cases["map"]["result"] != "map_preparation":
        raise AssertionError("Daemon map-preparation dispatch drifted")
    if daemon_cases["fleet"]["result"] != "fleet_preparation":
        raise AssertionError("Daemon fleet-preparation dispatch drifted")
    if opsi_cases["repair"]["result"] != "port_repair":
        raise AssertionError("OpsiDaemon repair dispatch drifted")
    if opsi_cases["select"]["result"] != "nearest_object":
        raise AssertionError("OpsiDaemon selection dispatch drifted")
    if any(
        event in ("port_probe", "enemy_probe")
        for event in opsi_cases["disabled"]["events"]
    ):
        raise AssertionError("disabled OpsiDaemon switches touched final boundaries")
    accepted, invalid = _verify_contract()
    invalid_entry = _verify_invalid_entry(
        daemon_module, opsi_module, (daemon_guard, opsi_guard)
    )
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "daemon_cases": daemon_cases,
        "opsi_cases": opsi_cases,
        "runtime_consumers": {**daemon_consumers, **opsi_consumers},
        "patched_guards_present": daemon_guard and opsi_guard,
        "invalid_entry_events": invalid_entry,
        "mutation_budget": 0,
        "real_map_input_performed": False,
        "real_port_repair_performed": False,
        "real_enemy_selected": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "daemon": _sha256(daemon_path),
            "opsi_daemon": _sha256(opsi_path),
        },
    }
