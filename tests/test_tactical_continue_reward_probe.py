"""Queued learning prompts own sidebar absence before native cancellation."""
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle
from alas_headless.oracle.errors import SemanticTargetNotActionable, SemanticInputBlocked


@pytest.mark.parametrize('name,target', [
    ('REWARD_2', 'reward/tactical/finish'),
    ('REWARD_2_WHITE', 'reward/tactical/finish'),
    ('REWARD_GOTO_TACTICAL', 'reward/tactical/go'),
    ('REWARD_GOTO_TACTICAL_WHITE', 'reward/tactical/go'),
])
def test_continue_prompt_precedes_offscreen_reward_shortcut(name, target):
    oracle = FakeOracle()
    oracle.reward_sidebar_control_offscreen = Mock(return_value=True)
    adapter = AlasSemanticAdapter(oracle, lambda: None, allow_tactical_rewards=True)
    adapter.begin_tactical()
    assert adapter._appear_tactical(name, target) is True
    oracle.tactical_prompt_text = 'already proven tactical continuation'
    oracle.reward_sidebar_control_offscreen.reset_mock()
    assert adapter._appear_tactical(name, target) is False
    oracle.reward_sidebar_control_offscreen.assert_not_called()
    assert oracle.click_calls == []


def test_ambiguous_prompt_remains_closed():
    oracle = FakeOracle()
    oracle.tactical_continue_prompt_text = Mock(side_effect=SemanticGateClosed('ambiguous prompt'))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_tactical()
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        adapter._appear_tactical('REWARD_2', 'reward/tactical/finish')
    assert oracle.click_calls == []


def test_cancel_presence_reuses_the_native_screenshot_without_a_live_request():
    oracle = FakeOracle()
    oracle.tactical_continue_prompt_text = Mock(side_effect=AssertionError('redundant live prompt read'))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_tactical()
    frame = Mock()
    frame.tactical_continue_prompt_text.return_value = None
    adapter._frame_observation_oracle = lambda: frame
    assert adapter.cancel_tactical_continue_if_present() is False
    oracle.tactical_continue_prompt_text.assert_not_called()
    assert not oracle.click_calls


def test_departed_continue_prompt_is_rechecked_before_any_input():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_tactical()
    old, current = Mock(), Mock()
    old.tactical_continue_prompt_text.return_value = 'previous prompt'
    current.tactical_continue_prompt_text.return_value = None
    adapter._frame_observation_oracle = lambda: old
    adapter._fresh_input_oracle = Mock(return_value=current)
    assert adapter.cancel_tactical_continue_if_present() is False
    current.click.assert_not_called()
    assert not oracle.click_calls


def test_accepted_reward_handoff_does_not_probe_or_repeat_departing_sidebar():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None, allow_tactical_rewards=True)
    adapter.begin_tactical()
    prior = oracle.click_receipt('reward/tactical/finish')
    adapter._commission_context.tactical_reward_receipt = prior
    oracle.reward_sidebar_control_offscreen = Mock(side_effect=AssertionError('departing sidebar probe'))
    assert adapter._click_tactical('REWARD_2') is prior
    oracle.reward_sidebar_control_offscreen.assert_not_called()
    assert not oracle.click_calls


def test_positive_empty_slot_can_yield_undispatched_transition_to_next_native_frame():
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None, tactical_assign_budget=1)
    adapter.begin_tactical()
    oracle.click_tactical_first_empty_slot = Mock(side_effect=
        SemanticTargetNotActionable('tactical/slot/first-empty', 10))
    assert adapter._click_tactical('ADD_NEW_STUDENT') is None
    assert adapter._commission_context.tactical_empty_slot_receipt is None
    assert adapter._action_ledger.remaining('tactical.assign') == 1
    assert oracle.click_calls == []
    receipt = oracle.click_receipt('tactical/slot/first-empty')
    oracle.click_tactical_first_empty_slot = Mock(return_value=receipt)
    assert adapter._click_tactical('ADD_NEW_STUDENT') is receipt


@pytest.mark.parametrize('error', [
    SemanticTargetNotActionable('unrelated/target', 10),
    SemanticInputBlocked('tactical/slot/first-empty', 10, ['unknown-popup']),
    SemanticGateClosed('uncertain dispatched input'),
])
def test_empty_slot_yield_does_not_swallow_other_input_failures(error):
    oracle = FakeOracle()
    adapter = AlasSemanticAdapter(oracle, lambda: None, tactical_assign_budget=1)
    adapter.begin_tactical()
    oracle.click_tactical_first_empty_slot = Mock(side_effect=error)
    with pytest.raises(type(error)):
        adapter._click_tactical('ADD_NEW_STUDENT')
    assert oracle.click_calls == []
