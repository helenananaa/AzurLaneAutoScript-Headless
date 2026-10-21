"""The native Hard caller reaches the existing budgeted Continue action."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticSession
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.test_campaign_task_grant_deferral import campaign_port


@pytest.mark.parametrize('budget', [0, 1])
def test_session_exposes_original_hard_continue_without_bypassing_action_ledger(budget):
    adapter, oracle, _, capability = campaign_port('hard_continue', budget=budget)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    session.refresh_frame = Mock(return_value=SimpleNamespace(frame_id='fresh'))
    if budget:
        receipt = session.continue_campaign_hard_auto_search()
        assert receipt.semantic_id == 'reward/campaign-total/continue'
        assert oracle.click_calls == ['reward/campaign-total/continue']
        assert adapter._action_ledger.remaining(capability) == 0
        assert adapter._campaign_context.sortie_receipt is receipt
        assert adapter._campaign_context.auto_search_completion is None
    else:
        with pytest.raises(AlasSemanticActionDeferred): session.continue_campaign_hard_auto_search()
        assert not oracle.click_calls
    session.refresh_frame.assert_called_once()


@pytest.mark.parametrize('budget', [0, 1])
def test_hard_accepts_reviewed_again_route_using_same_budget_and_completion(budget):
    adapter, oracle, call, capability = campaign_port('hard_continue', budget=budget)
    oracle.campaign_auto_search_reentry_available = Mock(return_value=True)
    if not budget:
        with pytest.raises(AlasSemanticActionDeferred): call()
        assert not oracle.click_calls
        oracle.campaign_auto_search_reentry_available.assert_not_called()
    else:
        receipt = call()
        assert receipt.semantic_id == 'reward/campaign-total/go'
        assert oracle.click_calls == ['reward/campaign-total/go']
        assert adapter._action_ledger.remaining(capability) == 0
        assert adapter._campaign_context.auto_search_completion is None


def test_hard_reentry_rechecks_typed_target_and_does_not_fallback_after_input_failure():
    from alas_headless import SemanticGateClosed
    adapter, oracle, call, _ = campaign_port('hard_continue', budget=1)
    oracle.campaign_auto_search_reentry_available = Mock(return_value=True)
    oracle.click_campaign_auto_search_reentry = Mock(side_effect=SemanticGateClosed('target changed'))
    with pytest.raises(SemanticGateClosed, match='target changed'): call()
    assert not oracle.click_calls
    assert adapter._campaign_context.auto_search_completion is not None


def test_hard_reentry_still_requires_prior_completion():
    from alas_headless import SemanticGateClosed
    adapter, oracle, call, _ = campaign_port('hard_continue', budget=1)
    adapter._campaign_context.auto_search_completion = None
    oracle.campaign_auto_search_reentry_available = Mock(return_value=True)
    with pytest.raises(SemanticGateClosed, match='proven result'): call()
    oracle.campaign_auto_search_reentry_available.assert_not_called()
    assert not oracle.click_calls


@pytest.mark.parametrize('route', ['reward/campaign-total/continue', 'reward/campaign-total/go'])
def test_accepted_continue_hides_closing_source_until_new_sortie_proof(route):
    from tests.test_alas_config_branch_compatibility import method
    adapter, oracle, call, capability = campaign_port('hard_continue', budget=2)
    oracle.campaign_auto_search_reentry_available = Mock(return_value=route.endswith('/go'))
    oracle.enabled_values['reward/campaign-total/exit'] = True
    receipt = call()
    assert receipt.semantic_id == route
    native_probe = method('module/handler/auto_search.py', 'AutoSearchHandler', 'is_in_auto_search_menu')
    native_host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter))
    assert native_probe(native_host) is False
    assert len(oracle.click_calls) == 1
    assert adapter._action_ledger.remaining(capability) == 1
    # The real action gate still refuses a second direct request without a
    # new completed sortie. Only passive old-menu visibility changed.
    from alas_headless import SemanticGateClosed
    with pytest.raises(SemanticGateClosed, match='proven result'):
        call()
    context = adapter._campaign_context
    context.sortie_proof = object()
    context.auto_search_role_state = object()
    context.auto_search_completion = object()
    assert native_probe(native_host)
    assert len(oracle.click_calls) == 1


def test_inherited_result_is_not_hidden_without_an_accepted_continue():
    adapter, oracle, _, _ = campaign_port('hard_continue', budget=1)
    oracle.enabled_values['reward/campaign-total/exit'] = True
    adapter._campaign_context.sortie_receipt = None
    adapter._campaign_context.auto_search_completion = None
    assert adapter.campaign_auto_search_result_visible()


@pytest.mark.parametrize('drift', [False, True])
def test_actual_hard_total_reward_again_button_is_budgeted_reentry(drift):
    from tests.test_game_tips_loading_presence import host
    backend, real_oracle, _ = host(drift, 'hard-total-reward-again-r30.json')
    adapter, _, call, capability = campaign_port('hard_continue', budget=1)
    # Replay retains the observed state/UI generations (6480/6481). Use the
    # production immutable reader so repeated target checks share that state,
    # rather than simulating a live endpoint moving backwards to 6480.
    from alas_headless.adapter.frame import _FrameBoundSemanticOracle
    adapter._live_oracle = _FrameBoundSemanticOracle(
        backend.request, backend.foreground_component, backend.tap,
        real_oracle.fingerprint, frame_guard=lambda: None)
    assert not real_oracle.exists('reward/campaign-total/continue')
    receipt = call()
    assert receipt.semantic_id == 'reward/campaign-total/go'
    assert receipt.path.endswith('/ButtonGO')
    assert len(backend.taps) == 1
    assert adapter._action_ledger.remaining(capability) == 0


def test_actual_hard_total_reward_unreviewed_again_label_rejects_input():
    from alas_headless import SemanticGateClosed
    from tests.test_game_tips_loading_presence import host
    backend, real_oracle, _ = host(fixture='hard-total-reward-again-r30.json')
    next(t for t in backend.ui['texts'] if t['path'].endswith('/ButtonGO/pic'))['text'] = 'unknown action'
    adapter, _, call, _ = campaign_port('hard_continue', budget=1)
    # Replay retains the observed state/UI generations (6480/6481). Use the
    # production immutable reader so repeated target checks share that state,
    # rather than simulating a live endpoint moving backwards to 6480.
    from alas_headless.adapter.frame import _FrameBoundSemanticOracle
    adapter._live_oracle = _FrameBoundSemanticOracle(
        backend.request, backend.foreground_component, backend.tap,
        real_oracle.fingerprint, frame_guard=lambda: None)
    with pytest.raises(SemanticGateClosed): call()
    assert not backend.taps
