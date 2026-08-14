"""Deterministic replay of pinned ALAS Data Key configuration decisions."""

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

from .alas_data_key_config_contract import validate_alas_data_key_config
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.data-key-config-replay/v1"
INVALID_VALUES = (0, 1, None, "true", [], {})


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> None:
    path = alas_root / "module" / "config" / "argument" / "args.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    data_key = document.get("Freebies", {}).get("DataKey")
    if not isinstance(data_key, dict) or set(data_key) != {"Collect", "ForceCollect"}:
        raise AssertionError("DataKey field surface drifted")
    expected = {"Collect": True, "ForceCollect": False}
    for field, default in expected.items():
        declaration = data_key[field]
        if declaration.get("type") != "checkbox" or declaration.get("value") is not default:
            raise AssertionError(f"DataKey.{field} declaration drifted")


def _verify_consumers(freebies_path: Path, data_key_path: Path) -> dict[str, list[str]]:
    expected = {
        "DataKey_Collect": (freebies_path, "Freebies", {"run"}),
        "DataKey_ForceCollect": (data_key_path, "DataKey", {"data_key_collect"}),
    }
    result = {}
    for field, (path, class_name, methods_expected) in expected.items():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        methods = set()
        for node in tree.body:
            if not isinstance(node, ast.ClassDef) or node.name != class_name:
                continue
            for child in node.body:
                if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if any(
                    isinstance(item, ast.Attribute)
                    and isinstance(item.ctx, ast.Load)
                    and item.attr == field
                    for item in ast.walk(child)
                ):
                    methods.add(child.name)
        if methods != methods_expected:
            raise AssertionError(f"{field} consumer surface drifted")
        result[field] = sorted(methods)
    return result


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        freebies_module = importlib.import_module("module.freebies.freebies")
        data_key_module = importlib.import_module("module.freebies.data_key")
        return freebies_module, data_key_module
    finally:
        sys.path.remove(root)


class _Config(SimpleNamespace):
    def __init__(self, *, collect: object, force_collect: object):
        super().__init__(
            BattlePass_Collect=False,
            DataKey_Collect=collect,
            DataKey_ForceCollect=force_collect,
            SupplyPack_Collect=False,
            SupplyPack_DayOfWeek=0,
        )
        self.events = []

    def task_delay(self, **kwargs):
        self.events.append(["delay", kwargs])


def _freebies_case(module: Any, *, collect: object, force_collect: object) -> dict[str, Any]:
    config = _Config(collect=collect, force_collect=force_collect)
    device = object()
    host = object.__new__(module.Freebies)
    host.config = config
    host.device = device
    events = []

    def factory(name: str):
        def create(actual_config, actual_device):
            if actual_config is not config or actual_device is not device:
                raise AssertionError("Freebies child constructor forwarding drifted")
            return SimpleNamespace(run=lambda: events.append(name))
        return create

    originals = {
        name: getattr(module, name)
        for name in ("BattlePass", "DataKey", "MailWhite", "SupplyPack_250814")
    }
    module.BattlePass = factory("battle_pass")
    module.DataKey = factory("data_key")
    module.MailWhite = factory("mail")
    module.SupplyPack_250814 = factory("supply_pack")
    try:
        module.Freebies.run(host)
    finally:
        for name, value in originals.items():
            setattr(module, name, value)
    return {"events": events, "config_events": config.events}


def _data_key_case(
    module: Any,
    *,
    force_collect: bool,
    already_collected: bool,
    remain: int,
) -> dict[str, Any]:
    host = object.__new__(module.DataKey)
    host.config = SimpleNamespace(DataKey_ForceCollect=force_collect)
    host.device = SimpleNamespace(image=object())
    events = []
    host.appear = MethodType(lambda self, *args, **kwargs: already_collected, host)
    host._data_key_collect = MethodType(lambda self: events.append("collect"), host)
    original = module.DATA_KEY
    module.DATA_KEY = SimpleNamespace(ocr=lambda image: (30 - remain, remain, 30))
    try:
        result = module.DataKey.data_key_collect(host)
    finally:
        module.DATA_KEY = original
    return {"result": bool(result), "events": events}


def _verify_original(freebies_module: Any, data_key_module: Any) -> dict[str, Any]:
    combos = {}
    for collect, force_collect in itertools.product((False, True), repeat=2):
        key = f"{int(collect)}{int(force_collect)}"
        case = _freebies_case(
            freebies_module,
            collect=collect,
            force_collect=force_collect,
        )
        expected_events = ["data_key", "mail"] if collect else ["mail"]
        if case != {
            "events": expected_events,
            "config_events": [["delay", {"server_update": True}]],
        }:
            raise AssertionError("original Freebies DataKey dispatch drifted")
        combos[key] = case
    boundaries = {
        "already_collected": _data_key_case(
            data_key_module,
            force_collect=True,
            already_collected=True,
            remain=0,
        ),
        "full_not_forced": _data_key_case(
            data_key_module,
            force_collect=False,
            already_collected=False,
            remain=0,
        ),
        "full_forced": _data_key_case(
            data_key_module,
            force_collect=True,
            already_collected=False,
            remain=0,
        ),
        "room_not_forced": _data_key_case(
            data_key_module,
            force_collect=False,
            already_collected=False,
            remain=1,
        ),
    }
    expected = {
        "already_collected": {"result": False, "events": []},
        "full_not_forced": {"result": False, "events": []},
        "full_forced": {"result": True, "events": ["collect"]},
        "room_not_forced": {"result": True, "events": ["collect"]},
    }
    if boundaries != expected:
        raise AssertionError("original DataKey capacity decision drifted")
    return {"combinations": combos, "capacity_boundaries": boundaries}


def _verify_contract() -> int:
    for collect, force_collect in itertools.product((False, True), repeat=2):
        validate_alas_data_key_config(
            collect=collect,
            force_collect=force_collect,
        )
    invalid_count = 0
    for field in ("collect", "force_collect"):
        for value in INVALID_VALUES:
            case = {"collect": True, "force_collect": False}
            case[field] = value
            try:
                validate_alas_data_key_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid DataKey.{field} was admitted")
    return invalid_count


def _verify_invalid_entry(module: Any) -> dict[str, list[Any]]:
    source = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_data_key_config"
        for node in ast.walk(source)
    )
    if not guard_present:
        return {}
    result = {}
    for field in ("collect", "force_collect"):
        values = {"collect": True, "force_collect": False}
        values[field] = None
        try:
            _freebies_case(module, **values)
        except SemanticGateClosed:
            result[field] = []
        else:
            raise AssertionError(f"patched Freebies admitted invalid {field}")
    return result


def verify_data_key_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    _verify_args(alas_root)
    freebies_path = alas_root / "module" / "freebies" / "freebies.py"
    data_key_path = alas_root / "module" / "freebies" / "data_key.py"
    consumers = _verify_consumers(freebies_path, data_key_path)
    freebies_module, data_key_module = _load_original(alas_root)
    original = _verify_original(freebies_module, data_key_module)
    invalid_count = _verify_contract()
    invalid_entry_events = _verify_invalid_entry(freebies_module)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 2,
        "accepted_case_count": 4,
        "invalid_case_count": invalid_count,
        "runtime_consumers": consumers,
        "original_decisions": original,
        "invalid_entry_events": invalid_entry_events,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_collect_method_called": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(
                alas_root / "module" / "config" / "argument" / "args.json"
            ),
            "freebies": _sha256(freebies_path),
            "data_key": _sha256(data_key_path),
        },
    }
