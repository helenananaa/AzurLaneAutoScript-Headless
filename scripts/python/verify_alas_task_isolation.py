#!/usr/bin/env python3
"""Execute the installed ALAS run/loop bodies with device-free fault injection."""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter import StaleFrameError, UnsupportedPixelRead
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope

ROOT = Path(__file__).resolve().parents[2]


def verify_source(source: str) -> dict:
    tree = ast.parse(source)
    controller = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AzurLaneAutoScript")
    methods = [n for n in controller.body if isinstance(n, ast.FunctionDef) and n.name in ("run", "loop")]
    if {n.name for n in methods} != {"run", "loop"}:
        raise ValueError("ALAS run/loop boundary is absent")
    namespace = {
        "logger": Mock(), "handle_notify": Mock(),
        "semantic_task_scope": semantic_task_scope,
        "TaskCapabilityUnavailable": TaskCapabilityUnavailable,
        "inflection": SimpleNamespace(underscore=lambda name: name.lower()),
        "del_cached_property": Mock(),
        "deep_get": lambda value, keys, default: value.get(keys, default),
    }
    # ALAS uses the first argument positionally and value= for the new value.
    def set_value(mapping, keys, value):
        mapping[keys] = value
    namespace["deep_set"] = set_value
    for name in ("TaskEnd", "GameNotRunningError", "GameStuckError", "GameTooManyClickError",
                 "GameBugError", "GamePageUnknownError", "ScriptError", "RequestHumanTakeover"):
        namespace[name] = type(name, (Exception,), {})
    exec(compile(ast.Module(body=methods, type_ignores=[]), "<installed-alas-run-loop>", "exec"), namespace)
    cls = type("InstalledAlasController", (), {name: namespace[name] for name in ("run", "loop")})

    def make_controller(semantic=True):
        instance = cls()
        session = SimpleNamespace(trace=None, context=None, cleanups=0)
        def discard():
            session.context = None
            session.cleanups += 1
        session.discard_task_state = discard
        instance.device = SimpleNamespace(
            semantic_adapter=session if semantic else None, screenshot=Mock(),
            stuck_record_clear=Mock(), click_record_clear=Mock(), sleep=Mock(), package="typed-test",
        )
        instance.config = SimpleNamespace(task_delay=Mock(), task_call=Mock(),
                                          Error_HandleError=True, Error_OnePushConfig={})
        instance.checker = SimpleNamespace(wait_until_available=Mock(), is_recovered=lambda: False,
                                           check_now=Mock(), is_available=lambda: True)
        instance.save_error_log = Mock()
        instance.config_name = "task-isolation-offline"
        instance.failure_record = {}
        instance.is_first_task = False
        return instance, session

    scenarios = []
    # Three repeated optional failures must not trip ALAS' three-crash takeover.
    instance, session = make_controller()
    queue = ["Optional", "Optional", "Optional", "Reward"]
    executions = []
    instance.stop_event = SimpleNamespace(is_set=lambda: not queue)
    instance.get_next_task = lambda: queue.pop(0)
    def optional():
        session.context = "failed-feature"
        executions.append("optional")
        raise AlasSemanticUnmapped("changed optional upstream resource")
    def reward():
        assert session.context is None
        executions.append("reward")
        raise namespace["TaskEnd"]()
    instance.optional, instance.reward = optional, reward
    instance.loop()
    assert executions == ["optional"] * 3 + ["reward"]
    assert instance.config.task_delay.call_count == 3
    assert all(call.kwargs == {"success": False} for call in instance.config.task_delay.call_args_list)
    assert instance.failure_record == {"Reward": 0}
    assert session.cleanups == 4
    instance.config.task_call.assert_not_called()
    scenarios.append("repeated-unsupported-task-then-independent-task")

    for error in (SemanticGateClosed("wrong package"), StaleFrameError(), RuntimeError("implementation bug")):
        instance, session = make_controller()
        def fail():
            session.context = "pending"
            raise error
        instance.task = fail
        try:
            instance.run("task")
        except SystemExit as exc:
            assert exc.code == 1
        else:
            raise AssertionError("runtime failure did not preserve fatal ALAS outcome")
        assert session.context is None and session.cleanups == 1
        instance.config.task_delay.assert_not_called()
    scenarios.append("runtime-identity-freshness-and-code-errors-still-stop")

    instance, session = make_controller()
    def stopped_game():
        raise namespace["GameNotRunningError"]()
    instance.task = stopped_game
    assert instance.run("task") is False
    instance.config.task_call.assert_called_once_with("Restart")
    assert session.cleanups == 1
    scenarios.append("original-alas-restart-recovery-preserved")

    instance, session = make_controller(semantic=False)
    def native_pixels():
        raise UnsupportedPixelRead()
    instance.task = native_pixels
    try:
        instance.run("task")
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("native task exception was incorrectly deferred")
    assert session.cleanups == 0
    instance.config.task_delay.assert_not_called()
    instance.task = lambda: None
    instance.device.screenshot.reset_mock()
    assert instance.run("task", skip_first_screenshot=True) is True
    instance.device.screenshot.assert_not_called()
    scenarios.append("native-mode-and-restart-screenshot-semantics-preserved")
    return {"scenarios": scenarios, "passed": True}


def verify(patched_upstream: Path) -> dict:
    source_path = patched_upstream / "alas.py"
    source = source_path.read_text(encoding="utf-8")
    baseline = verify_source(source)
    # Additive methods and harmless metadata must not change task admission.
    drift_tree = ast.parse(source)
    controller = next(n for n in drift_tree.body if isinstance(n, ast.ClassDef) and n.name == "AzurLaneAutoScript")
    controller.body.extend(ast.parse("""
upstream_metadata = {'new_optional_feature': 'available'}
def unrelated_optional_task(self):
    return 'new upstream task'
""").body)
    drift = verify_source(ast.unparse(drift_tree))
    identities = {}
    for relative in (
        "integration/alas/0001-semantic-oracle-hooks.patch", "integration/alas/series/series.json",
        "python/alas_headless/adapter/task_lifecycle.py", "python/alas_headless/adapter/frame.py",
        "python/alas_headless/adapter/semantic/core.py", "python/alas_headless/adapter/semantic/session.py",
        "scripts/python/verify_alas_task_isolation.py",
    ):
        identities[relative] = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
    return {
        "schema": "alas-headless.task-isolation-replay/v1",
        "alas_py_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "source_sha256": identities, "baseline": baseline, "additive_drift": drift,
        "android_input_injected": False, "live_qualified": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--patched-upstream", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = json.dumps(verify(args.patched_upstream), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            output.write(result)
    print(result, end="")
