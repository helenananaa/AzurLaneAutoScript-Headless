from types import SimpleNamespace
from unittest.mock import Mock
import json
import pytest
from alas_headless.adapter.task_lifecycle import semantic_task_scope,TaskCapabilityUnavailable
from alas_headless.oracle.errors import SemanticInputBlocked,SemanticTargetNotActionable

@pytest.mark.parametrize('error',[SemanticInputBlocked('os/order/repair',3848,('loading',)),SemanticTargetNotActionable('os/order/back',3849)])
def test_refusal_receipt_retains_exact_action_and_generation_without_new_policy(error):
    s=SimpleNamespace(discard_task_state=Mock(),trace=None)
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(s,'opsi_stronghold'):raise error
    encoded=json.loads(json.dumps(s.last_task_error))
    assert encoded['semantic_id']==error.semantic_id and encoded['generation']==error.generation
    if isinstance(error,SemanticInputBlocked):assert encoded['blockers']==['loading']
    assert s.last_task_outcome['outcome']=='input-unavailable'
    s.discard_task_state.assert_called_once()
