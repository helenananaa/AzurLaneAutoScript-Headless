from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.capabilities import DEFAULT_CAPABILITY_INVENTORY, compatibility_profile
from alas_headless.adapter.ledger import ActionLedger, compatibility_policy_sha256
from alas_headless.adapter.policy import RecoveryPolicy
from alas_headless.adapter.task_lifecycle import semantic_task_scope, TaskCapabilityUnavailable
from tests.semantic_support.adapter_fixtures import FakeOracle

def make_adapter(grant):
    grants={'operation_siren.action_point_use':grant}
    profile=compatibility_profile('ap-iteration',grants)
    ledger=ActionLedger(profile=profile,inventory=DEFAULT_CAPABILITY_INVENTORY,grants=grants,
        recovery_policy=RecoveryPolicy.QUALIFICATION_STOP,policy_sha256=compatibility_policy_sha256(profile.profile_id,grants))
    o=FakeOracle();o.click_operation_siren_action_point_control=Mock(return_value=o.click_receipt('os/ap/use'))
    a=AlasSemanticAdapter(o,lambda:None,action_ledger=ledger)
    s=SimpleNamespace(discard_task_state=Mock(),trace=None)
    return a,o,s

def test_exhausted_ap_budget_is_task_local_and_dispatches_nothing():
    a,o,s=make_adapter(0)
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(s,'opsi_stronghold'):
            a.click_operation_siren_action_point_control(True)
    o.click_operation_siren_action_point_control.assert_not_called()
    assert s.last_task_outcome['outcome']=='action-deferred'
    # An independent task can still enter the same native scope.
    with semantic_task_scope(s,'commission'):pass
    assert s.last_task_outcome['outcome']=='returned'

def test_one_ap_grant_is_consumed_once_then_deferred():
    a,o,s=make_adapter(1)
    assert a.click_operation_siren_action_point_control(True).semantic_id=='os/ap/use'
    assert a._action_ledger.remaining('operation_siren.action_point_use')==0
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(s,'opsi_stronghold'):
            a.click_operation_siren_action_point_control(True)
    assert o.click_operation_siren_action_point_control.call_count==1

def test_unknown_ap_action_failure_remains_fatal():
    a,o,s=make_adapter(1);o.click_operation_siren_action_point_control.side_effect=SemanticGateClosed('ambiguous AP target')
    with pytest.raises(SemanticGateClosed,match='ambiguous AP target'):
        with semantic_task_scope(s,'opsi_stronghold'):
            a.click_operation_siren_action_point_control(True)
    assert s.last_task_outcome['outcome']=='raised'
