"""Deterministic recorder-only replay for pinned ALAS Guild task settings."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from types import SimpleNamespace
from pathlib import Path
from typing import Any

import yaml

from .alas_guild_config_contract import validate_alas_guild_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.guild-config-replay/v1"
FIELDS = (
    "GuildLogistics_Enable",
    "GuildLogistics_SelectNewMission",
    "GuildLogistics_ExchangeFilter",
    "GuildOperation_Enable",
    "GuildOperation_SelectNewOperation",
    "GuildOperation_NewOperationMaxDate",
    "GuildOperation_JoinThreshold",
    "GuildOperation_AttackBoss",
    "GuildOperation_BossFleetRecommend",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _method(path: Path, owner: str, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    class_node = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner)
    return next(node for node in class_node.body if isinstance(node, ast.FunctionDef) and node.name == name)


def _settings(**override: object) -> dict[str, object]:
    values = {
        "logistics_enable": True,
        "logistics_select_new_mission": False,
        "logistics_exchange_filter": "Coin > Oil",
        "operation_enable": True,
        "operation_select_new_operation": False,
        "operation_new_operation_max_date": 15,
        "operation_join_threshold": 1,
        "operation_attack_boss": True,
        "operation_boss_fleet_recommend": False,
    }
    values.update(override)
    return values


def _config(**values: object) -> object:
    values = _settings(**values)
    return type(
        "Config",
        (),
        {
            "GuildLogistics_Enable": values["logistics_enable"],
            "GuildLogistics_SelectNewMission": values["logistics_select_new_mission"],
            "GuildLogistics_ExchangeFilter": values["logistics_exchange_filter"],
            "GuildOperation_Enable": values["operation_enable"],
            "GuildOperation_SelectNewOperation": values["operation_select_new_operation"],
            "GuildOperation_NewOperationMaxDate": values["operation_new_operation_max_date"],
            "GuildOperation_JoinThreshold": values["operation_join_threshold"],
            "GuildOperation_AttackBoss": values["operation_attack_boss"],
            "GuildOperation_BossFleetRecommend": values["operation_boss_fleet_recommend"],
        },
    )()


def _verify_declarations(root: Path) -> None:
    args = json.loads((root / "module/config/argument/args.json").read_text(encoding="utf-8"))
    template = json.loads((root / "config/template.json").read_text(encoding="utf-8"))
    task = yaml.safe_load((root / "module/config/argument/task.yaml").read_text(encoding="utf-8"))
    logistics = args.get("Guild", {}).get("GuildLogistics", {})
    operations = args.get("Guild", {}).get("GuildOperation", {})
    if logistics.get("Enable") != {"type": "checkbox", "value": True} or logistics.get("SelectNewMission") != {"type": "checkbox", "value": False}:
        raise AssertionError("Guild logistics declarations drifted")
    if operations.get("JoinThreshold") != {"type": "input", "value": 1} or operations.get("NewOperationMaxDate") != {"type": "input", "value": 15}:
        raise AssertionError("Guild operation numeric declarations drifted")
    if template.get("Guild", {}).get("GuildLogistics", {}).get("ExchangeFilter") != logistics.get("ExchangeFilter", {}).get("value"):
        raise AssertionError("Guild exchange filter default drifted")
    groups = [section["tasks"]["Guild"] for section in task.values() if isinstance(section, dict) and "Guild" in section.get("tasks", {})]
    if groups != [["Scheduler", "GuildLogistics", "GuildOperation"]]:
        raise AssertionError("Guild task panel declaration drifted")
    generated = ast.parse((root / "module/config/config_generated.py").read_text(encoding="utf-8"))
    defaults = {target.id: ast.literal_eval(node.value) for node in ast.walk(generated) if isinstance(node, ast.Assign) for target in node.targets if isinstance(target, ast.Name) and target.id in FIELDS}
    if defaults != {
        "GuildLogistics_Enable": True, "GuildLogistics_SelectNewMission": False,
        "GuildLogistics_ExchangeFilter": logistics["ExchangeFilter"]["value"],
        "GuildOperation_Enable": True, "GuildOperation_SelectNewOperation": False,
        "GuildOperation_NewOperationMaxDate": 15, "GuildOperation_JoinThreshold": 1,
        "GuildOperation_AttackBoss": True, "GuildOperation_BossFleetRecommend": False,
    }:
        raise AssertionError("Guild generated defaults drifted")


def _first_guard(method: ast.FunctionDef) -> bool:
    body = [node for node in method.body if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))]
    return bool(body and isinstance(body[0], ast.Assign) and isinstance(body[0].value, ast.Call) and isinstance(body[0].value.func, ast.Name) and body[0].value.func.id == "validate_alas_guild_config")


def _compile(method: ast.FunctionDef, name: str, namespace: dict[str, Any]) -> type[Any]:
    method = copy.deepcopy(method)
    method.decorator_list = []
    node = ast.ClassDef(name=name, bases=[], keywords=[], body=[method], decorator_list=[])
    module = ast.Module(body=[node], type_ignores=[])
    ast.fix_missing_locations(module)
    exec(compile(module, "<alas-guild-replay>", "exec"), namespace)
    return namespace[name]


class _Logger:
    def __getattr__(self, _name: str):
        return lambda *_args, **_kwargs: None


class _Stop(RuntimeError):
    pass


def _verify_contract() -> tuple[int, int]:
    accepted = invalid = 0
    for logistics_enable in (False, True):
        for logistics_select in (False, True):
            for operation_enable in (False, True):
                for operation_select in (False, True):
                    for attack_boss in (False, True):
                        for recommend in (False, True):
                            snapshot = validate_alas_guild_config(**_settings(logistics_enable=logistics_enable, logistics_select_new_mission=logistics_select, operation_enable=operation_enable, operation_select_new_operation=operation_select, operation_attack_boss=attack_boss, operation_boss_fleet_recommend=recommend))
                            if snapshot.operation_attack_boss is not attack_boss:
                                raise AssertionError("Guild boolean snapshot drifted")
                            accepted += 1
    for day in (1, 15, 31):
        for threshold in (0, 0.5, 1):
            validate_alas_guild_config(**_settings(operation_new_operation_max_date=day, operation_join_threshold=threshold))
            accepted += 1
    for key, value in (("logistics_enable", 1), ("logistics_exchange_filter", None), ("operation_new_operation_max_date", 0), ("operation_join_threshold", float("nan")), ("operation_attack_boss", "true")):
        try:
            validate_alas_guild_config(**_settings(**{key: value}))
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid Guild config was admitted")
    return accepted, invalid


def _run_entry(run_type: type[Any], **values: object) -> list[str]:
    host = run_type(); host.config = _config(**values); events: list[str] = []
    # This recorder checks native configuration decisions. Semantic frame
    # refresh ordering has separate actual-source coverage.
    host.device = SimpleNamespace(semantic_adapter=None)
    host.ui_ensure = lambda *_args: events.append("ensure")
    host.guild_lobby = lambda: events.append("lobby")
    host.guild_logistics = lambda: events.append("logistics") or True
    host.guild_operations = lambda: events.append("operations") or True
    host.ui_goto = lambda *_args: events.append("goto")
    host.config.task_delay = lambda **_kwargs: events.append("delay")
    host.config.task_stop = lambda: (_ for _ in ()).throw(_Stop())
    try:
        host.run()
    except SemanticGateClosed:
        if events: raise AssertionError("invalid Guild config reached task state")
        return []
    except _Stop:
        return ["stop"]
    return events


def _verify_consumers(root: Path) -> tuple[dict[str, list[str]], bool, dict[str, object]]:
    reward = root / "module/guild/guild_reward.py"; logistics = root / "module/guild/logistics.py"; operations = root / "module/guild/operations.py"
    methods = (
        _method(reward, "RewardGuild", "run"), _method(logistics, "GuildLogistics", "_handle_guild_fleet_mission_start"), _method(logistics, "GuildLogistics", "_guild_logistics_collect"), _method(logistics, "GuildLogistics", "_guild_exchange"), _method(operations, "GuildOperations", "_guild_operations_ensure"), _method(operations, "GuildOperations", "_handle_guild_operations_start"), _method(operations, "GuildOperations", "_guild_operations_boss_preparation"), _method(operations, "GuildOperations", "guild_operations"),
    )
    patched = all(_first_guard(method) for method in methods)
    guards = sum(1 for method in methods for node in ast.walk(method) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "validate_alas_guild_config")
    if patched and guards != 8: raise AssertionError("Guild consumers are not fully guarded")
    consumers = {field.replace("_", ".", 1): ["RewardGuild.run", "GuildLogistics direct consumers", "GuildOperations direct consumers"] for field in ("GuildLogistics_Enable", "GuildLogistics_SelectNewMission", "GuildLogistics_ExchangeFilter", "GuildOperation_Enable", "GuildOperation_SelectNewOperation", "GuildOperation_NewOperationMaxDate", "GuildOperation_JoinThreshold", "GuildOperation_AttackBoss", "GuildOperation_BossFleetRecommend")}
    decisions: dict[str, object] = {}
    if patched:
        run_type = _compile(methods[0], "GuildRunReplay", {"page_guild": object(), "page_main": object(), "validate_alas_guild_config": validate_alas_guild_config})
        cases = {
            "none": _run_entry(run_type, logistics_enable=False, operation_enable=False),
            "logistics": _run_entry(run_type, logistics_enable=True, operation_enable=False),
            "operations": _run_entry(run_type, logistics_enable=False, operation_enable=True),
            "both": _run_entry(run_type, logistics_enable=True, operation_enable=True),
            "invalid": _run_entry(run_type, operation_join_threshold=2),
        }
        if cases != {"none": ["stop"], "logistics": ["ensure", "lobby", "logistics", "goto", "delay"], "operations": ["ensure", "lobby", "operations", "goto", "delay"], "both": ["ensure", "lobby", "logistics", "operations", "goto", "delay"], "invalid": []}:
            raise AssertionError("Guild task entry forwarding drifted")
        decisions = cases
    return consumers, patched, decisions


def verify_guild_config(root: Path) -> dict[str, object]:
    root = root.resolve(); _verify_declarations(root); accepted, invalid = _verify_contract(); consumers, patched, decisions = _verify_consumers(root)
    return {"schema": SCHEMA, "passed": True, "field_count": 9, "accepted_case_count": accepted, "invalid_case_count": invalid, "runtime_consumers": consumers, "patched_guard_present": patched, "original_decisions": decisions, "mutation_budget": 0, "android_input_injected": False, "source_sha256": {"task": _sha256(root / "module/config/argument/task.yaml"), "args": _sha256(root / "module/config/argument/args.json"), "template": _sha256(root / "config/template.json"), "generated": _sha256(root / "module/config/config_generated.py"), "guild_reward": _sha256(root / "module/guild/guild_reward.py"), "logistics": _sha256(root / "module/guild/logistics.py"), "operations": _sha256(root / "module/guild/operations.py")}}
