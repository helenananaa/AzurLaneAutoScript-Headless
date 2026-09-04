"""Exercise the live experiment's input bound without constructing a device."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize("already_dispatched", [11, 12])
def test_live_experiment_stops_before_an_excess_navigation_input(already_dispatched):
    path = Path(__file__).resolve().parents[1] / "scripts/python/run_alas_task_isolation_live_validation.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    # Execute the actual callback in isolation; running main would open ADB.
    callback = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "bounded_tap")
    backend = Mock(return_value="dispatched")
    namespace = {"oracle": SimpleNamespace(input_dispatch_count=already_dispatched), "original_tap": backend}
    exec(compile(ast.Module(body=[callback], type_ignores=[]), str(path), "exec"), namespace)
    tap = namespace["bounded_tap"]
    if already_dispatched < 12:
        assert tap(10, 20) == "dispatched"
        backend.assert_called_once_with(10, 20)
    else:
        with pytest.raises(RuntimeError, match="12 navigation inputs"):
            tap(10, 20)
        backend.assert_not_called()
