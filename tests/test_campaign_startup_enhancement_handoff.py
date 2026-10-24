"""Startup must register the retained map before enabling its auto search."""
import ast
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def native_source(name):
    root = os.environ.get("ALAS_TEST_ROOT")
    if not root:
        pytest.skip("ALAS_TEST_ROOT is required for native recovery replay")
    return ast.parse(Path(root, "module/campaign", name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("resume", [True, False])
def test_native_recovery_enables_auto_only_after_its_owner_is_ready(resume):
    node = next(n for n in ast.walk(native_source("campaign_base.py"))
                if isinstance(n, ast.FunctionDef) and n.name == "_semantic_campaign_retirement_recovery")
    namespace = {}
    exec(compile(ast.Module(body=[node], type_ignores=[]), "<native recovery>", "exec"), namespace)
    actor = SimpleNamespace(device=SimpleNamespace(screenshot=Mock()),
                            handle_retirement=Mock(return_value=True),
                            is_in_map=Mock(return_value=True),
                            handle_auto_search_map_option=Mock(return_value=True))
    assert namespace[node.name](actor, resume_auto_search=resume) is True
    actor.handle_retirement.assert_called_once_with()
    assert actor.handle_auto_search_map_option.call_count == int(resume)


def test_native_startup_requests_paused_handoff():
    calls = [n for n in ast.walk(native_source("run.py")) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "_semantic_campaign_retirement_recovery"]
    assert len(calls) == 1
    assert any(k.arg == "resume_auto_search" and isinstance(k.value, ast.Constant)
               and k.value.value is False for k in calls[0].keywords)
