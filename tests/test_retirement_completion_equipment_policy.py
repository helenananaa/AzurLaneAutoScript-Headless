"""Interrupted retirement must retain the configured equipment disposition."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.dock import DockAdapterPorts


_spec = importlib.util.spec_from_file_location(
    'retirement_live_completion',
    Path(__file__).resolve().parents[1]
    / 'scripts/python/verify_authorized_retirement_live.py',
)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


@pytest.mark.parametrize('policy,options', [
    (None, {}), ('preserve', {}), ('disassemble', {'preserve_equipment': False}),
])
def test_pending_completion_uses_adapter_policy_without_new_submission(monkeypatch, policy, options):
    if policy is None:
        monkeypatch.delenv('ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY', raising=False)
    else:
        monkeypatch.setenv('ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY', policy)
    calls = []
    result = object()

    def finish(*args, **kwargs):
        calls.append((args, kwargs))
        return result

    adapter = DockAdapterPorts()
    # No selection/submission port is provided: completion cannot retire again.
    adapter.oracle = SimpleNamespace(_finish_retirement_transaction=finish)
    before, settings, actions = object(), object(), [object()]
    assert _module.complete_pending_retirement(
        adapter, before, {'retired_count': 9}, settings, actions) is result
    assert calls == [((before, 9, settings, actions, 60), options)]


def test_invalid_policy_rejected_before_pending_dialog_input(monkeypatch):
    monkeypatch.setenv('ALAS_SEMANTIC_DOCK_EQUIPMENT_POLICY', 'unknown')
    calls = []
    adapter = DockAdapterPorts()
    adapter.oracle = SimpleNamespace(
        _finish_retirement_transaction=lambda *args, **kwargs: calls.append(args))
    with pytest.raises(SemanticGateClosed, match='unknown dock equipment policy'):
        _module.complete_pending_retirement(adapter, object(), {'retired_count': 9}, object(), [])
    assert calls == []
