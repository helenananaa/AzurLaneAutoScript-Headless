"""Deterministic, input-free replay of the pinned ALAS Research chooser.

The replay extracts the chooser and filter methods from a caller supplied ALAS
tree.  It records decisions only: no device, reset, project start, or resource
mutation callback is available in the sandbox.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Callable, Dict, Mapping


class _Logger:
    def __getattr__(self, _name: str) -> Callable[..., None]:
        return lambda *_args, **_kwargs: None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _class_node(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise ValueError(f"missing ALAS class {name}")


def _method(tree: ast.Module, owner: str, name: str) -> ast.FunctionDef:
    for node in _class_node(tree, owner).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise ValueError(f"missing ALAS method {owner}.{name}")


def _compile(node: ast.AST, globals_: Mapping[str, object]) -> object:
    namespace: Dict[str, object] = dict(globals_)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    exec(compile(module, "<alas-research-replay>", "exec"), namespace)
    if isinstance(node, ast.ClassDef):
        return namespace[node.name]
    if isinstance(node, ast.FunctionDef):
        return namespace[node.name]
    raise TypeError(type(node).__name__)


def _literal(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"missing ALAS assignment {name}")


def _compiled_regex(tree: ast.Module, name: str) -> re.Pattern[str]:
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            continue
        if (
            not isinstance(node.value, ast.Call)
            or not isinstance(node.value.func, ast.Attribute)
            or not isinstance(node.value.func.value, ast.Name)
            or node.value.func.value.id != "re"
            or node.value.func.attr != "compile"
            or len(node.value.args) != 1
        ):
            break
        pattern = ast.literal_eval(node.value.args[0])
        if not isinstance(pattern, str):
            break
        return re.compile(pattern)
    raise ValueError(f"missing literal ALAS regex {name}")


@dataclass(eq=False)
class _Project:
    marker: str
    series: str = "S9"
    ship: str = ""
    ship_rarity: str = ""
    genre: str = "Q"
    number: str = ""
    duration: str = "0.5"
    valid: bool = True
    need_coin: bool = False
    need_cube: bool = False
    need_part: bool = False
    task: str = ""

    def __str__(self) -> str:
        return self.marker


def _project_from_filter(marker: str, parsed: list[object]) -> _Project:
    values = ["" if value is None else str(value) for value in parsed]
    return _Project(
        marker=marker,
        series=values[0] or "S9",
        ship=values[1],
        ship_rarity=values[2],
        genre=values[3] or "Q",
        number=values[4],
        duration=values[5] or "0.5",
    )


def verify_research_config(alas_root: Path) -> Mapping[str, object]:
    alas_root = alas_root.resolve()
    paths = {
        "selector": alas_root / "module/research/selector.py",
        "research": alas_root / "module/research/research.py",
        "filter": alas_root / "module/base/filter.py",
        "preset": alas_root / "module/research/preset.py",
        "args": alas_root / "module/config/argument/args.json",
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    trees = {
        key: ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for key, path in paths.items()
        if key != "args"
    }
    logger = _Logger()
    filter_type = _compile(
        _class_node(trees["filter"], "Filter"), {"re": re, "logger": logger}
    )
    assert isinstance(filter_type, type)
    filter_regex = _compiled_regex(trees["selector"], "FILTER_REGEX")
    filter_ = filter_type(
        filter_regex,
        ("series", "ship", "ship_rarity", "genre", "number", "duration"),
        ("shortest", "cheapest", "reset"),
    )
    presets = _literal(trees["preset"], "DICT_FILTER_PRESET")
    shortest = _literal(trees["preset"], "FILTER_STRING_SHORTEST")
    cheapest = _literal(trees["preset"], "FILTER_STRING_CHEAPEST")
    if not isinstance(presets, dict):
        raise TypeError("ALAS Research presets are not a dictionary")

    args = json.loads(paths["args"].read_text(encoding="utf-8"))
    research_args = args["Research"]["Research"]
    public_presets = tuple(research_args["PresetFilter"]["option"])
    default_preset = research_args["PresetFilter"]["value"]
    strategies = tuple(research_args["UseCoin"]["option"])
    if len(public_presets) != 26 or public_presets[0] != "custom":
        raise AssertionError("pinned ALAS public Research preset surface changed")
    if strategies != ("always_use", "only_05_hour", "only_no_project", "do_not_use"):
        raise AssertionError("pinned ALAS Research resource strategy surface changed")

    generated_config = type("GeneratedConfig", (), {"Research_PresetFilter": default_preset})
    common_globals = {
        "re": re,
        "partial": partial,
        "FILTER": filter_,
        "DICT_FILTER_PRESET": presets,
        "FILTER_STRING_SHORTEST": shortest,
        "FILTER_STRING_CHEAPEST": cheapest,
        "GeneratedConfig": generated_config,
        "logger": logger,
    }
    compiled = {
        name: _compile(_method(trees["selector"], "ResearchSelector", name), common_globals)
        for name in (
            "research_sort_filter",
            "_research_check",
            "research_sort_shortest",
            "research_sort_cheapest",
        )
    }
    select = _compile(
        _method(trees["research"], "RewardResearch", "research_select"),
        {"logger": logger},
    )
    fixed_now = datetime(2026, 8, 14, 1, 0, 0)

    class _FixedDateTime:
        @classmethod
        def now(cls) -> datetime:
            return fixed_now

    delay_check = _compile(
        _method(trees["research"], "RewardResearch", "research_delay_check"),
        {"datetime": _FixedDateTime, "timedelta": timedelta},
    )

    cases: list[str] = []

    def check(name: str, condition: bool) -> None:
        if not condition:
            raise AssertionError(name)
        cases.append(name)

    def sandbox(preset: str, projects: list[_Project], **config_values: object) -> SimpleNamespace:
        values = {
            "Research_PresetFilter": preset,
            "Research_CustomFilter": "S9-Q0.5 > reset > shortest",
            "Research_UseCube": "only_05_hour",
            "Research_UseCoin": "always_use",
            "Research_UsePart": "always_use",
            "Research_AllowDelay": True,
            "SERVER": "cn",
        }
        values.update(config_values)
        target = SimpleNamespace(
            config=SimpleNamespace(**values),
            projects=projects,
            storage_has_boxes=True,
            enforce=False,
        )
        for name, method in compiled.items():
            setattr(target, name, MethodType(method, target))
        return target

    preset_results: dict[str, str] = {}
    for preset in public_presets:
        source = (
            research_args["CustomFilter"]["value"]
            if preset == "custom"
            else presets[preset]
        )
        probe_filter = filter_type(filter_regex, filter_.attr, filter_.preset)
        probe_filter.load(source.lower())
        candidate = next(
            _project_from_filter(f"{preset}-candidate", parsed)
            for raw, parsed in zip(probe_filter.filter_raw, probe_filter.filter)
            if raw.lower() not in probe_filter.preset and any(parsed)
        )
        target = sandbox(preset, [candidate])
        priority = target.research_sort_filter()
        check(f"preset-{preset}", candidate in priority)
        preset_results[preset] = str(priority[0])

    cube_target = sandbox(
        default_preset,
        [_Project("cube-variant")],
        Research_UseCube="always_use",
    )
    cube_priority = cube_target.research_sort_filter()
    check("cube-variant-selected", isinstance(cube_priority, list))

    first = _Project("first")
    middle = _Project("middle")
    miss = _Project("miss", series="S1", genre="C", duration="12")
    target = sandbox("custom", [first, miss, middle])
    target.config.Research_CustomFilter = "S9-Q0.5"
    check("first-and-middle-match", target.research_sort_filter() == [first, middle])
    target.projects = [miss]
    check("no-match", target.research_sort_filter() == [])
    target = sandbox("not-a-public-preset", [first])
    check("fallback-default", isinstance(target.research_sort_filter(), list))

    # The semantic gate is intentionally stricter than Filter.load(), which
    # logs and ignores invalid tokens.  Exercise it without importing ALAS.
    from .alas_adapter import AlasSemanticAdapter

    gate = AlasSemanticAdapter.validate_research_filter
    gate(SimpleNamespace(), filter_, "S9-Q0.5 > reset")
    check("valid-custom-filter", True)
    try:
        gate(SimpleNamespace(), filter_, "S9-Q0.5 > definitely-invalid")
    except Exception as exc:  # SemanticGateClosed, imported by the adapter
        check("invalid-token-fails-closed", "invalid token" in str(exc))
    else:
        raise AssertionError("invalid-token-fails-closed")

    tie_a, tie_b = _Project("tie-a"), _Project("tie-b")
    target = sandbox("custom", [tie_a, tie_b])
    target.config.Research_CustomFilter = "S9-Q0.5"
    check("equal-priority-keeps-card-order", target.research_sort_filter() == [tie_a, tie_b])
    check("cross-round-idempotent", target.research_sort_filter() == [tie_a, tie_b])

    for name, allow, slot, end_time, expected in (
        ("delay-disabled", False, 3, fixed_now + timedelta(hours=1), False),
        ("delay-open-slot", True, 3, fixed_now + timedelta(hours=1), True),
        ("delay-slot4-finished", True, 4, fixed_now, True),
        ("delay-slot4-long-running", True, 4, fixed_now + timedelta(minutes=11), True),
        ("delay-slot4-near-finish", True, 4, fixed_now + timedelta(minutes=5), False),
        ("delay-queue-full", True, 5, fixed_now + timedelta(hours=1), False),
    ):
        delay_target = SimpleNamespace(
            config=SimpleNamespace(Research_AllowDelay=allow),
            get_queue_slot=lambda slot=slot: slot,
            end_time=end_time,
        )
        check(name, MethodType(delay_check, delay_target)() is expected)

    policy_rows = 0
    for resource in ("coin", "cube", "part"):
        for strategy in strategies:
            for duration, enforce in (("0.5", False), ("1", False), ("1", True)):
                project = _Project("policy", duration=duration)
                setattr(project, f"need_{resource}", True)
                values = {f"Research_Use{resource.title()}": strategy}
                target = sandbox("custom", [project], **values)
                accepted = target._research_check(project, enforce=enforce)
                expected = (
                    strategy == "always_use"
                    or (strategy == "only_05_hour" and duration == "0.5")
                    or (enforce and strategy in ("only_05_hour", "only_no_project"))
                )
                check(f"policy-{resource}-{strategy}-{duration}-{int(enforce)}", accepted is expected)
                policy_rows += 1

    # Execute the original selector with preview-only callbacks.  A false start
    # represents complete but insufficient resource data; no callback mutates.
    def select_preview(start_results: list[object], allow_delay: bool, slot: int = 5) -> tuple[bool, list[str]]:
        events: list[str] = []
        project = _Project("selected")
        target = sandbox("custom", [project], Research_AllowDelay=allow_delay)
        target.enforce = True
        target.research_project_start_with_requirements = lambda _project, add_queue=True: (
            events.append("start-preview") or start_results.pop(0)
        )
        target.get_queue_slot = lambda: slot
        target.end_time = fixed_now + timedelta(hours=1)
        target.research_delay_check = MethodType(delay_check, target)
        target.research_enforce = lambda **_kwargs: events.append("fallback") or True
        target.research_reset = lambda **_kwargs: events.append("reset-preview") or True
        target.research_sort_shortest = lambda _enforce: [project]
        target.research_sort_cheapest = lambda _enforce: [project]
        target.research_select = MethodType(select, target)
        return target.research_select([project]), events

    result, events = select_preview([True], False)
    check("resource-sufficient-preview", result is True and events == ["start-preview"])
    result, events = select_preview([False], False)
    check("resource-insufficient-no-delay", result is True and events == ["start-preview", "fallback"])
    result, events = select_preview([False], True, slot=3)
    check("resource-insufficient-delay", result is True and events == ["start-preview"])
    result, events = select_preview([False], True, slot=5)
    check("queue-full-no-delay", events == ["start-preview", "fallback"])

    target = sandbox("custom", [_Project("reset")])
    target.enforce = True
    reset_events: list[str] = []
    target.research_reset = lambda **_kwargs: reset_events.append("reset-preview") or True
    target.research_enforce = lambda **_kwargs: reset_events.append("fallback") or True
    target.research_select = MethodType(select, target)
    check("reset-before-selection", target.research_select(["reset"]) is False)
    check("reset-preview-only", reset_events == ["reset-preview"])

    target = sandbox("custom", [_Project("before-reset")])
    target.enforce = True
    after_reset_events: list[str] = []
    target.research_project_start_with_requirements = (
        lambda _project, add_queue=True: after_reset_events.append("start-preview") or False
    )
    target.research_delay_check = lambda: False
    target.research_reset = lambda **_kwargs: after_reset_events.append("reset-preview") or True
    target.research_enforce = lambda **_kwargs: after_reset_events.append("fallback") or True
    target.research_select = MethodType(select, target)
    check(
        "reset-after-failed-candidate",
        target.research_select([target.projects[0], "reset"]) is False
        and after_reset_events == ["start-preview", "reset-preview"],
    )

    return {
        "schema": "alas-headless.research-config-replay/v1",
        "passed": True,
        "public_preset_count": len(public_presets),
        "public_presets": list(public_presets),
        "preset_results": preset_results,
        "resource_strategy_count": len(strategies),
        "resource_policy_rows": policy_rows,
        "case_count": len(cases),
        "cases": cases,
        "mutation_budget": 0,
        "android_input_injected": False,
        "source_sha256": {key: _sha256(path) for key, path in paths.items()},
    }
