"""The native campaign gate must defer exhausted grants, preserving map resume."""
import ast
from types import SimpleNamespace

import pytest

from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.alas_test_source import patched_alas_root
from tests.test_adapter_task_lifecycle import session_with_task


def native_entry_gate():
    path = patched_alas_root() / 'module/campaign/run.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    guards = [node for node in ast.walk(tree) if isinstance(node, ast.If) and
              any(isinstance(child, ast.Attribute) and
                  child.attr == 'campaign_stage_entry_allowed'
                  for child in ast.walk(node.test))]
    assert len(guards) == 1
    guard = guards[0]
    # Execute the original guard within its original ScriptEnd handler. This
    # reproduces the historical silent break without duplicating a task loop.
    module = ast.parse('''
def invoke(semantic_adapter, semantic_map_resume=False, run=lambda: 'ran'):
    try:
        pass
        return run()
    except ScriptEnd:
        return 'script-ended'
''')
    module.body[0].body[0].body[0] = guard
    namespace = {'ScriptEnd': type('ScriptEnd', (Exception,), {})}
    exec(compile(ast.fix_missing_locations(module), str(path), 'exec'), namespace)
    return namespace['invoke'], namespace['ScriptEnd']


def test_exhausted_campaign_entry_grant_is_deferred_instead_of_script_success():
    invoke, _ = native_entry_gate()
    calls = []
    with pytest.raises(AlasSemanticActionDeferred, match='campaign.stage_entry'):
        invoke(SimpleNamespace(campaign_stage_entry_allowed=lambda: False),
               run=lambda: calls.append('run'))
    assert calls == []


def test_exhaustion_reaches_existing_task_local_failure_interval_boundary():
    invoke, _ = native_entry_gate()
    session, adapter, oracle, _ = session_with_task()
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'event_sp'):
            invoke(SimpleNamespace(campaign_stage_entry_allowed=lambda: False))
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert session.last_task_outcome == {'task': 'event_sp', 'outcome': 'action-deferred'}
    assert oracle.click_calls == []
    assert adapter._action_ledger.remaining('campaign.grid_click') == 2
    with semantic_task_scope(session, 'reward'):
        pass
    assert session.last_task_outcome == {'task': 'reward', 'outcome': 'returned'}


@pytest.mark.parametrize('adapter,resume', [
    (None, False),
    (SimpleNamespace(campaign_stage_entry_allowed=lambda: True), False),
    (SimpleNamespace(campaign_stage_entry_allowed=lambda: False), True),
])
def test_native_mode_funded_entry_and_existing_map_resume_remain_allowed(adapter, resume):
    invoke, _ = native_entry_gate()
    assert invoke(adapter, resume) == 'ran'


def test_original_campaign_script_end_behavior_is_unchanged():
    invoke, script_end = native_entry_gate()
    def run():
        raise script_end('native completion')
    assert invoke(None, run=run) == 'script-ended'
