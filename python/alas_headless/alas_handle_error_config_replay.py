"""Deterministic replay for ALAS error-recovery configuration."""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

import yaml

from .alas_handle_error_config_contract import validate_alas_handle_error_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.handle-error-config-replay/v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _methods(path: Path, owner_name: str, names: set[str]) -> dict[str, ast.FunctionDef]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owner = next(
        node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == owner_name
    )
    methods = {
        node.name: node
        for node in owner.body
        if isinstance(node, ast.FunctionDef) and node.name in names
    }
    if set(methods) != names:
        raise AssertionError(f"{owner_name} HandleError methods are unavailable")
    return methods


def _generated_default(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if any(
            isinstance(target, ast.Name) and target.id == "Error_HandleError"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if type(value) is not bool or value is not True:
                raise AssertionError("HandleError generated default drifted")
            return value
    raise AssertionError("HandleError generated default is unavailable")


def _verify_argument_schema(path: Path, default: bool) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    group = document.get("Error") if isinstance(document, dict) else None
    if not isinstance(group, dict) or group.get("HandleError") is not default:
        raise AssertionError("HandleError argument schema drifted")


def _compile_device(methods: dict[str, ast.FunctionDef]):
    class_node = ast.ClassDef(
        name="DeviceReplay",
        bases=[ast.Name(id="Parent", ctx=ast.Load())],
        keywords=[],
        body=[methods["app_start"], methods["app_stop"]],
        decorator_list=[],
    )
    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)
    events: list[str] = []

    class _Logger:
        def critical(self, *_args, **_kwargs) -> None:
            return None

    class _RequestHumanTakeover(Exception):
        pass

    class _Parent:
        def app_start(self) -> None:
            events.append("parent_app_start")

        def app_stop(self) -> None:
            events.append("parent_app_stop")

    namespace: dict[str, Any] = {
        "Parent": _Parent,
        "RequestHumanTakeover": _RequestHumanTakeover,
        "logger": _Logger(),
        "validate_alas_handle_error_config": validate_alas_handle_error_config,
    }
    exec(compile(module, "<alas-handle-error-device>", "exec"), namespace)
    return namespace["DeviceReplay"], _RequestHumanTakeover, events


def _compile_campaign(method: ast.FunctionDef):
    class_node = ast.ClassDef(
        name="CampaignReplay",
        bases=[],
        keywords=[],
        body=[method],
        decorator_list=[],
    )
    module = ast.Module(body=[class_node], type_ignores=[])
    ast.fix_missing_locations(module)
    events: list[str] = []

    class _Logger:
        def hr(self, *_args, **_kwargs) -> None:
            return None

        def warning(self, *_args, **_kwargs) -> None:
            return None

    class _MapEnemyMoved(Exception):
        pass

    class _ScriptError(Exception):
        pass

    namespace: dict[str, Any] = {
        "MapEnemyMoved": _MapEnemyMoved,
        "ScriptError": _ScriptError,
        "logger": _Logger(),
        "validate_alas_handle_error_config": validate_alas_handle_error_config,
    }
    exec(compile(module, "<alas-handle-error-campaign>", "exec"), namespace)
    return namespace["CampaignReplay"], _ScriptError, events


def _verify_contract() -> tuple[int, int]:
    accepted = 0
    invalid = 0
    for value in (True, False):
        if validate_alas_handle_error_config(value) is not value:
            raise AssertionError("HandleError boolean decision drifted")
        accepted += 1
    for value in (None, 0, 1, "", "true", [], {}):
        try:
            validate_alas_handle_error_config(value)
        except SemanticGateClosed:
            invalid += 1
        else:
            raise AssertionError("invalid HandleError value was admitted")
    return accepted, invalid


def _verify_device(methods: dict[str, ast.FunctionDef]) -> dict[str, object]:
    device_type, takeover, events = _compile_device(methods)
    results: dict[str, object] = {}
    for method_name in ("app_start", "app_stop"):
        for label, value in (("enabled", True), ("disabled", False), ("invalid", "true")):
            del events[:]
            device = device_type()
            device.config = type("Config", (), {"Error_HandleError": value})()
            device.stuck_record_clear = lambda: events.append("stuck_record_clear")
            device.click_record_clear = lambda: events.append("click_record_clear")
            try:
                getattr(device, method_name)()
            except (takeover, SemanticGateClosed) as exc:
                results[f"{method_name}_{label}"] = {
                    "exception": type(exc).__name__,
                    "events": list(events),
                }
            else:
                results[f"{method_name}_{label}"] = {"exception": None, "events": list(events)}
    for method_name in ("app_start", "app_stop"):
        enabled = results[f"{method_name}_enabled"]
        disabled = results[f"{method_name}_disabled"]
        invalid = results[f"{method_name}_invalid"]
        if enabled["events"][:1] != [f"parent_{method_name}"]:
            raise AssertionError(f"{method_name} enabled path did not reach parent boundary")
        if disabled["events"] or invalid["events"]:
            raise AssertionError(f"{method_name} disabled or invalid path reached app action")
    return results


def _verify_campaign(method: ast.FunctionDef) -> dict[str, object]:
    campaign_type, script_error, events = _compile_campaign(method)
    results: dict[str, object] = {}
    for label, value in (("enabled", True), ("disabled", False), ("invalid", "true")):
        del events[:]
        campaign = campaign_type()
        campaign.config = type("Config", (), {"Error_HandleError": value})()
        campaign.FUNCTION_NAME_BASE = "battle_"
        campaign.battle_count = 0
        campaign.semantic_prepare_a_battle = lambda: events.append("prepare")
        campaign.battle_function = lambda: False
        campaign.withdraw = lambda: events.append("withdraw")
        try:
            result = campaign.execute_a_battle()
        except (script_error, SemanticGateClosed) as exc:
            results[label] = {"result": None, "exception": type(exc).__name__, "events": list(events)}
        else:
            results[label] = {"result": result, "exception": None, "events": list(events)}
    if results["enabled"]["events"][-1:] != ["withdraw"]:
        raise AssertionError("enabled HandleError did not reach the withdrawal intent")
    if "withdraw" in results["disabled"]["events"] or "withdraw" in results["invalid"]["events"]:
        raise AssertionError("disabled or invalid HandleError reached withdrawal")
    return results


def _direct_handle_error_reads(methods: dict[str, ast.FunctionDef]) -> int:
    return sum(
        1
        for method in methods.values()
        for node in ast.walk(method)
        if isinstance(node, ast.Attribute) and node.attr == "Error_HandleError"
    )


def verify_handle_error_config(alas_root: Path) -> dict[str, object]:
    root = alas_root.resolve()
    device_path = root / "module" / "device" / "device.py"
    campaign_path = root / "module" / "campaign" / "campaign_base.py"
    config_path = root / "module" / "config" / "config_generated.py"
    argument_path = root / "module" / "config" / "argument" / "argument.yaml"
    if not all(path.is_file() for path in (device_path, campaign_path, config_path, argument_path)):
        raise FileNotFoundError("ALAS HandleError source is incomplete")
    default = _generated_default(config_path)
    _verify_argument_schema(argument_path, default)
    device_methods = _methods(device_path, "Device", {"app_start", "app_stop"})
    campaign_methods = _methods(campaign_path, "CampaignBase", {"execute_a_battle", "run"})
    all_methods = {**device_methods, **{f"campaign_{name}": value for name, value in campaign_methods.items()}}
    guard_calls = [
        node
        for method in all_methods.values()
        for node in ast.walk(method)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_handle_error_config"
    ]
    if len(guard_calls) != 4 or _direct_handle_error_reads(all_methods) != 4:
        raise AssertionError("HandleError guards do not cover every direct read")
    accepted, invalid = _verify_contract()
    device = _verify_device(device_methods)
    campaign = _verify_campaign(campaign_methods["execute_a_battle"])
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 1,
        "accepted_case_count": accepted,
        "invalid_case_count": invalid,
        "generated_default": default,
        "runtime_consumers": {
            "restart": ["Device.app_start", "Device.app_stop"],
            "withdrawal": ["CampaignBase.execute_a_battle", "CampaignBase.run"],
        },
        "original_decisions": {"device": device, "campaign": campaign},
        "mutation_budget": 0,
        "app_restart_requests": 0,
        "withdrawal_requests": 0,
        "android_input_injected": False,
        "source_sha256": {
            "device": _sha256(device_path),
            "campaign_base": _sha256(campaign_path),
            "config_generated": _sha256(config_path),
            "argument_schema": _sha256(argument_path),
        },
    }
