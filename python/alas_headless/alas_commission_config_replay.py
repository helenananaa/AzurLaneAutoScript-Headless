"""Deterministic replay of pinned ALAS Commission configuration decisions."""

from __future__ import annotations

import ast
from datetime import datetime
import hashlib
import importlib
import itertools
import json
import sys
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any

from .alas_commission_config_contract import (
    COMMISSION_PRESETS,
    parse_alas_commission_custom_filter,
    validate_alas_commission_config,
)
from .semantic_oracle import SemanticGateClosed


SCHEMA = "alas-headless.commission-config-replay/v1"
INVALID_PRESET_VALUES = (None, True, 1, "", "unknown", [])
INVALID_BOOL_VALUES = (0, 1, None, "true", [], {})
INVALID_CUSTOM_FILTERS = (
    None,
    True,
    1,
    "",
    ">",
    "unknown",
    "Cube-",
    "100:00",
    "ExtraCube-0:3",
    "Gem-8x",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _verify_args(alas_root: Path) -> str:
    document = json.loads(
        (alas_root / "module/config/argument/args.json").read_text(encoding="utf-8")
    )
    group = document.get("Commission", {}).get("Commission")
    if not isinstance(group, dict) or set(group) != {
        "PresetFilter",
        "CustomFilter",
        "DoMajorCommission",
    }:
        raise AssertionError("Commission field surface drifted")
    preset = group["PresetFilter"]
    if (
        preset.get("type") != "select"
        or preset.get("value") != "cube"
        or tuple(preset.get("option", ())) != COMMISSION_PRESETS
    ):
        raise AssertionError("Commission.PresetFilter declaration drifted")
    custom = group["CustomFilter"]
    if custom.get("type") != "textarea" or type(custom.get("value")) is not str:
        raise AssertionError("Commission.CustomFilter declaration drifted")
    major = group["DoMajorCommission"]
    if major.get("type") != "checkbox" or major.get("value") is not False:
        raise AssertionError("Commission.DoMajorCommission declaration drifted")
    return custom["value"]


def _source_flags(path: Path) -> tuple[dict[str, list[str]], bool]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    expected = {
        "Commission_PresetFilter": {"_commission_choose"},
        "Commission_CustomFilter": {"_commission_choose"},
        "Commission_DoMajorCommission": {"_commission_check"},
    }
    consumers: dict[str, list[str]] = {}
    run = None
    for node in tree.body:
        if not isinstance(node, ast.ClassDef) or node.name != "RewardCommission":
            continue
        for child in node.body:
            if not isinstance(child, ast.FunctionDef):
                continue
            if child.name == "run":
                run = child
            for field in expected:
                if any(
                    isinstance(item, ast.Attribute)
                    and isinstance(item.ctx, ast.Load)
                    and item.attr == field
                    for item in ast.walk(child)
                ):
                    consumers.setdefault(field, []).append(child.name)
    if run is None:
        raise AssertionError("RewardCommission.run is missing")
    guard_present = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "validate_alas_commission_config"
        for node in ast.walk(run)
    )
    expected_consumers = {
        field: methods | ({"run"} if guard_present else set())
        for field, methods in expected.items()
    }
    normalized = {field: sorted(consumers.get(field, [])) for field in expected}
    if normalized != {
        field: sorted(methods) for field, methods in expected_consumers.items()
    }:
        raise AssertionError("Commission configuration consumer surface drifted")
    if guard_present:
        statements = list(run.body)
        if (
            statements
            and isinstance(statements[0], ast.Expr)
            and isinstance(statements[0].value, ast.Constant)
            and isinstance(statements[0].value.value, str)
        ):
            statements.pop(0)
        executable = [
            statement
            for statement in statements
            if not isinstance(statement, (ast.Import, ast.ImportFrom))
        ]
        first = executable[0]
        if not (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Call)
            and isinstance(first.value.func, ast.Name)
            and first.value.func.id == "validate_alas_commission_config"
        ):
            raise AssertionError("Commission configuration guard is not first in run")
    return normalized, guard_present


def _load_original(alas_root: Path):
    root = str(alas_root.resolve())
    sys.path.insert(0, root)
    try:
        for name in tuple(sys.modules):
            if name == "module" or name.startswith("module."):
                del sys.modules[name]
        return importlib.import_module("module.commission.commission")
    finally:
        sys.path.remove(root)


class _RecordingFilter:
    def __init__(self):
        self.loaded: list[str] = []

    def load(self, value: str):
        self.loaded.append(value)

    def apply(self, objects, func=None):
        return []


def _preset_case(
    module: Any, *, preset: str, custom_filter: str, period: str
) -> str:
    recorder = _RecordingFilter()
    original_filter = module.COMMISSION_FILTER
    original_last_update = module.get_server_last_update
    if period == "day":
        times = {
            "02:00": datetime(2026, 1, 2, 2),
            "21:00": datetime(2026, 1, 1, 21),
        }
    elif period == "night":
        times = {
            "02:00": datetime(2026, 1, 1, 2),
            "21:00": datetime(2026, 1, 2, 21),
        }
    else:
        raise AssertionError("unknown Commission replay period")
    module.COMMISSION_FILTER = recorder
    module.get_server_last_update = lambda trigger: times[trigger]
    host = object.__new__(module.RewardCommission)
    host.config = SimpleNamespace(
        Commission_PresetFilter=preset,
        Commission_CustomFilter=custom_filter,
        Commission_DoMajorCommission=False,
    )
    empty = module.SelectedGrids([])
    try:
        daily, urgent = module.RewardCommission._commission_choose(host, empty, empty)
    finally:
        module.COMMISSION_FILTER = original_filter
        module.get_server_last_update = original_last_update
    if daily.count or urgent.count or len(recorder.loaded) != 1:
        raise AssertionError("Commission empty selection replay drifted")
    loaded = recorder.loaded[0]
    if loaded == custom_filter:
        return "custom"
    for name, value in module.DICT_FILTER_PRESET.items():
        if loaded == value:
            return name
    raise AssertionError("Commission resolved an unknown filter source")


def _verify_preset_resolution(module: Any, custom_filter: str) -> dict[str, str]:
    expected_keys = {
        "chip",
        "chip_night",
        "chip_24h",
        "cube",
        "cube_night",
        "cube_24h",
        "oil",
        "oil_night",
    }
    if set(module.DICT_FILTER_PRESET) != expected_keys:
        raise AssertionError("Commission built-in preset surface drifted")
    result = {}
    for preset, period in itertools.product(COMMISSION_PRESETS, ("day", "night")):
        resolved = _preset_case(
            module,
            preset=preset,
            custom_filter=custom_filter,
            period=period,
        )
        night_name = f"{preset}_night"
        expected = (
            "custom"
            if preset == "custom"
            else night_name
            if period == "night" and night_name in module.DICT_FILTER_PRESET
            else preset
        )
        if resolved != expected:
            raise AssertionError("original Commission preset resolution drifted")
        result[f"{preset}:{period}"] = resolved
    fallback = _preset_case(
        module,
        preset="unknown",
        custom_filter=custom_filter,
        period="day",
    )
    if fallback != "cube":
        raise AssertionError("original Commission invalid-preset fallback drifted")
    result["original_invalid_fallback"] = fallback
    return result


def _verify_custom_filters(module: Any, custom_filter: str) -> dict[str, Any]:
    sources = {"args_custom": custom_filter, **module.DICT_FILTER_PRESET}
    unique_tokens = set()
    for name, value in sources.items():
        tokens = parse_alas_commission_custom_filter(value)
        if not tokens:
            raise AssertionError(f"Commission filter source {name} is empty")
        unique_tokens.update(tokens)
        module.COMMISSION_FILTER.load(value)
        if any(parts and parts[0] == "1nVa1d" for parts in module.COMMISSION_FILTER.filter):
            raise AssertionError(f"Commission filter source {name} contains invalid tokens")

    def candidate(label, category, genre, duration_hm, duration_hour):
        return SimpleNamespace(
            label=label,
            category_str=category,
            genre_str=genre,
            duration_hm=duration_hm,
            duration_hour=duration_hour,
        )

    major = candidate("major", "major", "unknown", "12:00", "12")
    gem = candidate("gem", "urgent", "gem", "8:00", "8")
    cube = candidate("cube", "extra", "cube", "0:30", "0.5")
    drill = candidate("drill", "extra", "drill", "1:30", "1.5")
    objects = [drill, cube, gem, major]
    expression = "Major > Gem-8 > ExtraCube-0:30 > 1.5 > shortest"
    module.COMMISSION_FILTER.load(expression)
    selected = module.COMMISSION_FILTER.apply(objects)
    labels = [item if isinstance(item, str) else item.label for item in selected]
    if labels != ["major", "gem", "cube", "drill", "shortest"]:
        raise AssertionError("original Commission custom-filter priority drifted")
    unicode_expression = "Major ＞ Gem－8 ❯ shortest"
    if parse_alas_commission_custom_filter(unicode_expression) != (
        "major",
        "gem-8",
        "shortest",
    ):
        raise AssertionError("Commission custom-filter normalization drifted")
    module.COMMISSION_FILTER.load(unicode_expression)
    selected = module.COMMISSION_FILTER.apply(objects)
    labels = [item if isinstance(item, str) else item.label for item in selected]
    if labels != ["major", "gem", "shortest"]:
        raise AssertionError("original Commission unicode-filter priority drifted")
    return {
        "source_count": len(sources),
        "unique_token_count": len(unique_tokens),
        "representative_priority": ["major", "gem", "cube", "drill", "shortest"],
    }


def _verify_major_filter(module: Any) -> dict[str, bool]:
    result = {}
    for do_major, category, valid, status in itertools.product(
        (False, True),
        ("major", "extra"),
        (False, True),
        ("pending", "running"),
    ):
        host = object.__new__(module.RewardCommission)
        host.config = SimpleNamespace(Commission_DoMajorCommission=do_major)
        commission = SimpleNamespace(
            valid=valid,
            status=status,
            category_str=category,
        )
        admitted = bool(module.RewardCommission._commission_check(host, commission))
        expected = valid and status == "pending" and (
            do_major or category != "major"
        )
        if admitted is not expected:
            raise AssertionError("original Commission major-filter decision drifted")
        key = f"{int(do_major)}:{category}:{int(valid)}:{status}"
        result[key] = admitted
    return result


def _verify_contract(custom_filter: str) -> tuple[int, int]:
    for preset, do_major in itertools.product(COMMISSION_PRESETS, (False, True)):
        validate_alas_commission_config(
            preset_filter=preset,
            custom_filter=custom_filter,
            do_major_commission=do_major,
        )
    invalid_count = 0
    invalid_values = {
        "preset_filter": INVALID_PRESET_VALUES,
        "do_major_commission": INVALID_BOOL_VALUES,
    }
    for field, values in invalid_values.items():
        for value in values:
            case = {
                "preset_filter": "cube",
                "custom_filter": custom_filter,
                "do_major_commission": False,
            }
            case[field] = value
            try:
                validate_alas_commission_config(**case)
            except SemanticGateClosed:
                invalid_count += 1
            else:
                raise AssertionError(f"invalid Commission.{field} was admitted")
    for value in INVALID_CUSTOM_FILTERS:
        try:
            validate_alas_commission_config(
                preset_filter="cube",
                custom_filter=value,
                do_major_commission=False,
            )
        except SemanticGateClosed:
            invalid_count += 1
        else:
            raise AssertionError("invalid Commission.CustomFilter was admitted")
    return len(COMMISSION_PRESETS) * 2, invalid_count


class _Config(SimpleNamespace):
    def __init__(
        self, *, preset_filter: object, custom_filter: object, do_major: object
    ):
        super().__init__(
            Commission_PresetFilter=preset_filter,
            Commission_CustomFilter=custom_filter,
            Commission_DoMajorCommission=do_major,
        )
        self.events = []

    def task_delay(self, **kwargs):
        self.events.append(["task_delay", kwargs])

    def cross_get(self, **kwargs):
        self.events.append(["cross_get", kwargs])
        return False


def _entry_case(
    module: Any,
    *,
    preset_filter: object,
    custom_filter: object,
    do_major: object,
    semantic: bool = True,
) -> list[Any]:
    events = []
    session = SimpleNamespace(
        begin_commission=lambda: events.append("begin_commission"),
        end_commission=lambda: events.append("end_commission"),
        commission_reward_pending=lambda: False,
        commission_reward_claimed=lambda: False,
    )
    host = object.__new__(module.RewardCommission)
    host.config = _Config(
        preset_filter=preset_filter,
        custom_filter=custom_filter,
        do_major=do_major,
    )
    host.device = SimpleNamespace(semantic_adapter=session if semantic else None)
    host.ui_ensure = MethodType(lambda self, page: events.append("ui_ensure"), host)
    host.commission_receive = MethodType(
        lambda self: events.append("commission_receive"), host
    )
    host.handle_info_bar = MethodType(
        lambda self: events.append("handle_info_bar"), host
    )
    empty = module.SelectedGrids([])
    host.daily = empty
    host.urgent = empty

    def commission_start(self):
        events.append("commission_start")
        self.comm_choose = module.SelectedGrids([])

    host.commission_start = MethodType(commission_start, host)
    module.RewardCommission.run(host)
    events.extend(host.config.events)
    return events


def _verify_entry(module: Any, guard_present: bool, custom_filter: str):
    if not guard_present:
        return {"valid": {}, "normal": [], "invalid": {}}
    expected = [
        "begin_commission",
        "ui_ensure",
        "commission_receive",
        "handle_info_bar",
        "commission_start",
        "end_commission",
        ["task_delay", {"success": False}],
        [
            "cross_get",
            {"keys": "GemsFarming.GemsFarming.CommissionLimit", "default": False},
        ],
    ]
    valid = {}
    for preset, do_major in itertools.product(COMMISSION_PRESETS, (False, True)):
        events = _entry_case(
            module,
            preset_filter=preset,
            custom_filter=custom_filter,
            do_major=do_major,
        )
        if events != expected:
            raise AssertionError("valid Commission entry dispatch drifted")
        valid[f"{preset}:{int(do_major)}"] = events
    normal = _entry_case(
        module,
        preset_filter="cube",
        custom_filter=custom_filter,
        do_major=False,
        semantic=False,
    )
    expected_normal = [
        "ui_ensure",
        "commission_receive",
        "handle_info_bar",
        "commission_start",
        ["task_delay", {"success": False}],
        [
            "cross_get",
            {"keys": "GemsFarming.GemsFarming.CommissionLimit", "default": False},
        ],
    ]
    if normal != expected_normal:
        raise AssertionError("normal Commission entry dispatch drifted")
    invalid = {}
    cases = {
        "Commission_PresetFilter": (None, custom_filter, False),
        "Commission_CustomFilter": ("cube", "unknown", False),
        "Commission_DoMajorCommission": ("cube", custom_filter, None),
    }
    for field, (preset, custom, do_major) in cases.items():
        try:
            _entry_case(
                module,
                preset_filter=preset,
                custom_filter=custom,
                do_major=do_major,
            )
        except SemanticGateClosed:
            invalid[field] = []
        else:
            raise AssertionError(f"patched Commission admitted invalid {field}")
    return {"valid": valid, "normal": normal, "invalid": invalid}


def verify_commission_config(alas_root: Path) -> dict[str, Any]:
    alas_root = alas_root.resolve()
    custom_filter = _verify_args(alas_root)
    source = alas_root / "module/commission/commission.py"
    consumers, guard_present = _source_flags(source)
    module = _load_original(alas_root)
    preset_decisions = _verify_preset_resolution(module, custom_filter)
    custom_decisions = _verify_custom_filters(module, custom_filter)
    major_decisions = _verify_major_filter(module)
    accepted_count, invalid_count = _verify_contract(custom_filter)
    entry_decisions = _verify_entry(module, guard_present, custom_filter)
    return {
        "schema": SCHEMA,
        "passed": True,
        "field_count": 3,
        "accepted_case_count": accepted_count,
        "preset_resolution_case_count": len(COMMISSION_PRESETS) * 2,
        "invalid_case_count": invalid_count,
        "runtime_consumers": consumers,
        "patched_guard_present": guard_present,
        "original_preset_decisions": preset_decisions,
        "custom_filter_decisions": custom_decisions,
        "major_filter_decisions": major_decisions,
        "entry_decisions": entry_decisions,
        "temporary_config_only": True,
        "mutation_budget": 0,
        "real_reward_claimed": False,
        "real_commission_started": False,
        "android_input_injected": False,
        "source_sha256": {
            "args": _sha256(alas_root / "module/config/argument/args.json"),
            "commission": _sha256(source),
            "preset": _sha256(alas_root / "module/commission/preset.py"),
        },
    }
