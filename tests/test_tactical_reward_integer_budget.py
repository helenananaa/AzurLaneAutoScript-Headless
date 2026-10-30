"""Optional integer tactical grants preserve Boolean compatibility and bounds."""
from unittest.mock import Mock, patch
import pytest
from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import translate_legacy_semantic_environment
from alas_headless.adapter.errors import ActionLeaseError
from tests.test_adapter_legacy_environment import BASE_ENVIRONMENT, explicit_policy

KEY = 'ALAS_SEMANTIC_TACTICAL_REWARD_BUDGET'


@pytest.mark.parametrize('legacy,budget,expected', [(False,None,0), (True,None,1),
    (True,'0',1), (False,'3',3), (True,'3',3)])
def test_integer_is_an_initial_total_not_an_additive_or_refilled_grant(legacy,budget,expected):
    env = dict(BASE_ENVIRONMENT, ALAS_SEMANTIC_ALLOW_TACTICAL_REWARDS=str(int(legacy)))
    if budget is not None:
        env[KEY] = budget
    translated = translate_legacy_semantic_environment(env)
    assert translated.grant('tactical.reward') == expected
    assert translated.session_arguments['allow_tactical_rewards'] is (expected > 0)


@pytest.mark.parametrize('value', ['-1', '+1', '01', '1.5', 'true', ' 3', '3 '])
def test_malformed_integer_never_creates_authority(value):
    with pytest.raises(SemanticGateClosed, match='canonical'):
        translate_legacy_semantic_environment(dict(BASE_ENVIRONMENT, **{KEY:value}))


def test_actual_session_ledger_consumes_three_once_then_rejects_without_operation():
    with patch.dict('os.environ', dict(BASE_ENVIRONMENT, **{KEY:'3'}), clear=True):
        session = AlasSemanticSession.from_environment('not-opened')
    operation = Mock()
    try:
        assert session.policy_grants['tactical.reward'] == 3
        for remaining in (2,1,0):
            receipt = session.action_ledger.dispatch('tactical.reward', operation)
            assert receipt.remaining_after_dispatch == remaining
        with pytest.raises(ActionLeaseError):
            session.action_ledger.dispatch('tactical.reward', operation)
        assert operation.call_count == 3
        assert session.action_ledger.remaining('tactical.reward') == 0
    finally:
        session.close()


def test_explicit_policy_and_nondefault_integer_still_conflict():
    with pytest.raises(SemanticGateClosed, match='conflicts'):
        translate_legacy_semantic_environment(dict(BASE_ENVIRONMENT, **{KEY:'3'}),
            explicit_policy=explicit_policy({'tactical.reward':3}))
