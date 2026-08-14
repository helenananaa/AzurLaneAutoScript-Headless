"""Execute ALAS stop-condition methods in an isolated, deterministic sandbox.

The verifier extracts the methods from a caller-supplied ALAS tree instead of
copying their decisions into the adapter.  This keeps the evidence tied to the
exact pinned/patched source while avoiding a campaign run or device input.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from types import MethodType, SimpleNamespace
from typing import Any, Callable, Dict, Iterable, Mapping, MutableMapping


SOURCE_METHODS = {
    "module/campaign/run.py": (
        "CampaignRun",
        ("triggered_stop_condition", "run", "_run"),
    ),
    "module/handler/fast_forward.py": (
        "FastForwardHandler",
        ("campaign_name_increase", "triggered_map_stop", "handle_map_stop"),
    ),
    "module/combat/level.py": ("Level", ("lv_triggered",)),
}


class _Logger:
    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def __getattr__(self, name: str) -> Callable[..., None]:
        def record(message: object = "", *_args: object, **_kwargs: object) -> None:
            self.events.append((name, str(message)))

        return record


class _Config(SimpleNamespace):
    def __init__(self, **values: Any) -> None:
        defaults = {
            "StopCondition_RunCount": 0,
            "StopCondition_ReachLevel": 0,
            "StopCondition_OilLimit": 0,
            "StopCondition_GetNewShip": False,
            "StopCondition_MapAchievement": "non_stop",
            "StopCondition_StageIncrease": False,
            "Scheduler_Enable": True,
            "TaskBalancer_Enable": False,
            "Error_OnePushConfig": "",
            "Campaign_Name": "12-4",
            "Campaign_Event": "campaign_main",
            "STAGE_INCREASE_AB": True,
            "STAGE_INCREASE_CUSTOM": "",
            "LV_TRIGGERED": False,
            "GET_SHIP_TRIGGERED": False,
            "config_name": "stop-condition-replay",
        }
        defaults.update(values)
        super().__init__(**defaults)
        self.delays: list[object] = []

    def task_delay(self, **kwargs: object) -> None:
        self.delays.append(kwargs)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _class_node(tree: ast.Module, class_name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    raise ValueError(f"missing ALAS class {class_name}")


def _method_node(tree: ast.Module, class_name: str, method_name: str) -> ast.FunctionDef:
    class_node = _class_node(tree, class_name)
    for node in class_node.body:
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    raise ValueError(f"missing ALAS method {class_name}.{method_name}")


def _literal_class_assignment(tree: ast.Module, class_name: str, name: str) -> Any:
    for node in _class_node(tree, class_name).body:
        if not isinstance(node, ast.Assign):
            continue
        if any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError(f"missing ALAS class assignment {class_name}.{name}")


def _compile_method(
    tree: ast.Module,
    class_name: str,
    method_name: str,
    globals_: Mapping[str, object],
) -> Callable[..., Any]:
    node = _method_node(tree, class_name, method_name)
    module = ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[]))
    namespace: Dict[str, object] = dict(globals_)
    exec(compile(module, f"<alas:{class_name}.{method_name}>", "exec"), namespace)
    method = namespace[method_name]
    if not callable(method):
        raise TypeError(f"compiled ALAS method is not callable: {class_name}.{method_name}")
    return method


def _assert_run_decrement_order(tree: ast.Module) -> Mapping[str, object]:
    try:
        run = _method_node(tree, "CampaignRun", "_run")
    except ValueError:
        # Compatibility with the pinned upstream before the semantic wrapper
        # split ``run`` into a wrapper plus the original ``_run`` body.
        run = _method_node(tree, "CampaignRun", "run")
    calls: list[tuple[int, str]] = []
    decrement_lines: list[int] = []
    decrement_guarded = False
    for node in ast.walk(run):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            parts: list[str] = []
            current: ast.expr = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            calls.append((node.lineno, ".".join(reversed(parts))))
        if (
            isinstance(node, ast.AugAssign)
            and isinstance(node.op, ast.Sub)
            and isinstance(node.target, ast.Attribute)
            and node.target.attr == "StopCondition_RunCount"
        ):
            decrement_lines.append(node.lineno)
            parent_guard = next(
                (
                    candidate
                    for candidate in ast.walk(run)
                    if isinstance(candidate, ast.If)
                    and node in tuple(ast.walk(candidate))
                    and isinstance(candidate.test, ast.Attribute)
                    and candidate.test.attr == "StopCondition_RunCount"
                ),
                None,
            )
            decrement_guarded = parent_guard is not None

    campaign_run_lines = [line for line, name in calls if name == "self.campaign.run"]
    after_stop_lines = [
        line
        for line, name in calls
        if name == "self.triggered_stop_condition"
        and any(
            keyword.arg == "oil_check"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is False
            for call in ast.walk(run)
            if isinstance(call, ast.Call) and call.lineno == line
            for keyword in call.keywords
        )
    ]
    if len(campaign_run_lines) != 1 or len(decrement_lines) != 1 or len(after_stop_lines) != 1:
        raise AssertionError("ALAS run-count post-success structure is ambiguous")
    if not campaign_run_lines[0] < decrement_lines[0] < after_stop_lines[0]:
        raise AssertionError("run count is not decremented only after a successful campaign run")
    if not decrement_guarded:
        raise AssertionError("unlimited run count would be decremented")
    return {
        "campaign_run_line": campaign_run_lines[0],
        "decrement_line": decrement_lines[0],
        "post_run_stop_check_line": after_stop_lines[0],
        "unlimited_count_guarded": True,
    }


def _base_campaign() -> SimpleNamespace:
    config = _Config()
    return SimpleNamespace(
        config=config,
        auto_search_oil_limit_triggered=False,
        auto_search_coin_limit_triggered=False,
        event_pt_limit_triggered=lambda: False,
    )


def _stop_sandbox(method: Callable[..., Any], **overrides: object) -> SimpleNamespace:
    config_values = dict(overrides.pop("config", {}))
    campaign = _base_campaign()
    for key, value in dict(overrides.pop("campaign_config", {})).items():
        setattr(campaign.config, key, value)
    for key, value in dict(overrides.pop("campaign", {})).items():
        setattr(campaign, key, value)
    oil = int(overrides.pop("oil", 99999))
    sandbox = SimpleNamespace(
        config=_Config(**config_values),
        campaign=campaign,
        run_limit=int(overrides.pop("run_limit", 0)),
        run_count=int(overrides.pop("run_count", 0)),
        name="12-4",
        get_oil=lambda: oil,
        handle_task_balancer=lambda: None,
        triggered_task_balancer=lambda: False,
    )
    if overrides:
        raise TypeError(f"unknown stop sandbox overrides: {sorted(overrides)}")
    sandbox.triggered_stop_condition = MethodType(method, sandbox)
    return sandbox


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def verify_stop_conditions(alas_root: Path) -> Mapping[str, object]:
    """Run deterministic cases against methods extracted from ``alas_root``."""

    alas_root = alas_root.resolve()
    trees: MutableMapping[str, ast.Module] = {}
    hashes: Dict[str, str] = {}
    for relative in SOURCE_METHODS:
        path = alas_root / relative
        if not path.is_file():
            raise FileNotFoundError(path)
        trees[relative] = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        hashes[relative] = _sha256(path)

    logger = _Logger()
    notifications: list[Mapping[str, object]] = []

    def handle_notify(config: object, **kwargs: object) -> None:
        notifications.append({"config": config, **kwargs})

    stop_method = _compile_method(
        trees["module/campaign/run.py"],
        "CampaignRun",
        "triggered_stop_condition",
        {"logger": logger, "handle_notify": handle_notify},
    )
    map_method = _compile_method(
        trees["module/handler/fast_forward.py"],
        "FastForwardHandler",
        "triggered_map_stop",
        {"logger": logger},
    )
    handle_map_method = _compile_method(
        trees["module/handler/fast_forward.py"],
        "FastForwardHandler",
        "handle_map_stop",
        {"logger": logger, "to_map_input_name": lambda value: str(value).upper()},
    )
    to_map_input_name = _compile_method(
        trees["module/handler/fast_forward.py"],
        "FastForwardHandler",
        "campaign_name_increase",
        {
            "logger": logger,
            "to_map_input_name": lambda value: re.sub(r"[ \t\n]", "", str(value)).upper()
            .replace("CAMPAIGN_", "")
            .replace("_", "-"),
            "map_files": lambda _event: ["a1", "a2", "a3", "b1", "b2", "b3", "d1", "d2", "d3"],
        },
    )
    level_method = _compile_method(
        trees["module/combat/level.py"], "Level", "lv_triggered", {"logger": logger}
    )

    case_names: list[str] = []

    def case(name: str, condition: bool) -> None:
        _expect(condition, name)
        case_names.append(name)

    # OilLimit uses a strict lower-than check and a hard 500 floor.
    for oil, limit, expected in (
        (499, 0, True),
        (500, 0, False),
        (999, 1000, True),
        (1000, 1000, False),
        (1001, 1000, False),
    ):
        sandbox = _stop_sandbox(stop_method, oil=oil, config={"StopCondition_OilLimit": limit})
        case(f"oil-{oil}-limit-{limit}", sandbox.triggered_stop_condition() is expected)

    # RunCount 0 is unlimited; a positive initial limit stops at zero and clamps negatives.
    for run_limit, remaining, expected in ((0, 0, False), (3, 1, False), (3, 0, True), (3, -1, True)):
        sandbox = _stop_sandbox(
            stop_method,
            run_limit=run_limit,
            config={"StopCondition_RunCount": remaining},
        )
        result = sandbox.triggered_stop_condition(oil_check=False)
        case(f"run-count-{run_limit}-{remaining}", result is expected)
        if expected:
            case(f"run-count-clamped-{remaining}", sandbox.config.StopCondition_RunCount == 0)
            case(f"run-count-disabled-{remaining}", sandbox.config.Scheduler_Enable is False)

    run_order = _assert_run_decrement_order(trees["module/campaign/run.py"])
    case("run-count-post-success-order", True)

    # MapAchievement covers every supported value across its three observations.
    achievement_options = (
        "non_stop",
        "100_percent_clear",
        "map_3_stars",
        "threat_safe_without_3_stars",
        "threat_safe",
    )
    achievement_rows = 0
    for option in achievement_options:
        for clear in (False, True):
            for stars in (False, True):
                for threat in (False, True):
                    expected = {
                        "non_stop": False,
                        "100_percent_clear": clear,
                        "map_3_stars": clear and stars,
                        "threat_safe_without_3_stars": clear and threat,
                        "threat_safe": clear and stars and threat,
                    }[option]
                    sandbox = SimpleNamespace(
                        config=_Config(StopCondition_MapAchievement=option),
                        map_is_100_percent_clear=clear,
                        map_is_3_stars=stars,
                        map_is_threat_safe=threat,
                    )
                    result = MethodType(map_method, sandbox)()
                    case(f"achievement-{option}-{int(clear)}{int(stars)}{int(threat)}", result is expected)
                    achievement_rows += 1

    # StageIncrease: main progression, custom/event progression, A/B, end, and disabled.
    stage_increase = _literal_class_assignment(
        trees["module/handler/fast_forward.py"], "FastForwardHandler", "STAGE_INCREASE"
    )

    def stage_sandbox(**values: object) -> SimpleNamespace:
        config = _Config(**values)
        sandbox = SimpleNamespace(config=config, STAGE_INCREASE=stage_increase)
        sandbox.campaign_name_increase = MethodType(to_map_input_name, sandbox)
        sandbox.handle_map_stop = MethodType(handle_map_method, sandbox)
        return sandbox

    sandbox = stage_sandbox(Campaign_Name="12-3", StopCondition_StageIncrease=True)
    sandbox.handle_map_stop()
    case("stage-main-next", sandbox.config.Campaign_Name == "12-4")
    sandbox = stage_sandbox(Campaign_Name="16-4", StopCondition_StageIncrease=True)
    sandbox.handle_map_stop()
    case("stage-main-end-disables", sandbox.config.Scheduler_Enable is False)
    sandbox = stage_sandbox(
        Campaign_Name="D1",
        Campaign_Event="event_test",
        STAGE_INCREASE_CUSTOM="D1 > D2 > D3",
        STAGE_INCREASE_AB=False,
        StopCondition_StageIncrease=True,
    )
    sandbox.handle_map_stop()
    case("stage-custom-next", sandbox.config.Campaign_Name == "D2")
    sandbox = stage_sandbox(
        Campaign_Name="A3",
        Campaign_Event="event_test",
        STAGE_INCREASE_AB=True,
        StopCondition_StageIncrease=True,
    )
    sandbox.handle_map_stop()
    case("stage-ab-next", sandbox.config.Campaign_Name == "B1")
    sandbox = stage_sandbox(Campaign_Name="12-3", StopCondition_StageIncrease=False)
    sandbox.handle_map_stop()
    case("stage-disabled-stops", sandbox.config.Scheduler_Enable is False)

    # ReachLevel accepts exact/low-level crossings and rejects equal, unknown, and implausible gaps.
    for name, before, after, limit, expected in (
        ("exact", 119, 120, 120, True),
        ("equal", 120, 120, 120, False),
        ("large-gap", 118, 120, 120, False),
        ("low-level-crossing", 8, 10, 10, True),
        ("unknown-before", -1, 120, 120, False),
        ("below", 118, 119, 120, False),
    ):
        config = _Config(StopCondition_ReachLevel=limit)
        sandbox = SimpleNamespace(
            config=config,
            _lv_before_battle=[before, -1, -1, -1, -1, -1],
            lv=[after, -1, -1, -1, -1, -1],
        )
        result = MethodType(level_method, sandbox)()
        case(f"reach-level-{name}", result is expected)
        case(f"reach-level-flag-{name}", bool(config.LV_TRIGGERED) is expected)

    # The original method order is the concurrent-condition precedence contract.
    logger.events.clear()
    sandbox = _stop_sandbox(
        stop_method,
        run_limit=2,
        oil=0,
        config={
            "StopCondition_RunCount": 0,
            "StopCondition_ReachLevel": 120,
            "StopCondition_GetNewShip": True,
        },
        campaign_config={"LV_TRIGGERED": True, "GET_SHIP_TRIGGERED": True},
        campaign={"auto_search_oil_limit_triggered": True},
    )
    case("precedence-run-count-result", sandbox.triggered_stop_condition() is True)
    case("precedence-run-count-first", logger.events[-1][1].endswith("Run count"))
    logger.events.clear()
    sandbox = _stop_sandbox(
        stop_method,
        oil=0,
        config={"StopCondition_ReachLevel": 120, "StopCondition_GetNewShip": True},
        campaign_config={"LV_TRIGGERED": True, "GET_SHIP_TRIGGERED": True},
        campaign={"auto_search_oil_limit_triggered": True},
    )
    case("precedence-reach-level-result", sandbox.triggered_stop_condition() is True)
    case("precedence-reach-level-first", "Reach level" in logger.events[-1][1])
    logger.events.clear()
    sandbox = _stop_sandbox(
        stop_method,
        oil=499,
        config={"StopCondition_GetNewShip": True},
        campaign_config={"GET_SHIP_TRIGGERED": True},
        campaign={"auto_search_oil_limit_triggered": True},
    )
    case("precedence-oil-result", sandbox.triggered_stop_condition() is True)
    case("precedence-oil-first", logger.events[-1][1].endswith("Oil limit"))

    return {
        "schema": "alas-headless.stop-condition-replay/v1",
        "passed": True,
        "alas_root": str(alas_root),
        "source_sha256": hashes,
        "case_count": len(case_names),
        "cases": case_names,
        "map_achievement_truth_table_rows": achievement_rows,
        "run_count_post_success": run_order,
        "new_ship_live_test": "skipped-nondeterministic-first-acquisition",
        "input_injected": False,
    }
