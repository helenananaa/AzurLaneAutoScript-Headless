from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle


@pytest.mark.parametrize('owned,newer,present,expired', [
    (True, True, False, False), (False, True, False, False),
    (True, False, False, False), (True, True, True, False),
    (True, True, False, True),
])
def test_native_back_reentry_only_acknowledges_accepted_departure(owned, newer, present, expired):
    adapter = AlasSemanticAdapter(make_oracle(FakeBackend([])), lambda: None)
    adapter.begin_commission()
    frame = Mock()
    frame.enabled.return_value = False
    frame.read_state.return_value = SimpleNamespace(generation=11 if newer else 10)
    frame.observation_target_present.return_value = present
    adapter._fresh_input_oracle = Mock(return_value=frame)
    previous = SimpleNamespace(semantic_id='tactical/page/back', generation=10)
    adapter._commission_context.navigation_back_receipt = previous if owned else None
    if expired:
        adapter._commission_context.passive_transition_until = 0
    if owned and newer and not present and not expired:
        assert adapter.click('BACK_ARROW') is previous
    else:
        with pytest.raises(SemanticGateClosed, match='contextual ALAS back'):
            adapter.click('BACK_ARROW')
    frame.click.assert_not_called()


@pytest.mark.parametrize('ready', [('tactical/page/back',), ('commission/page/back',),
                                 ('tactical/page/back', 'commission/page/back')])
def test_navigation_readiness_and_input_share_frame_and_preserve_ambiguity(ready):
    adapter = AlasSemanticAdapter(make_oracle(FakeBackend([])), lambda: None)
    adapter.begin_commission()
    frame = Mock()
    frame.enabled.side_effect = lambda target: target in ready
    frame.click.return_value = SimpleNamespace(semantic_id=ready[0], generation=10)
    adapter._fresh_input_oracle = Mock(return_value=frame)
    if len(ready) == 2:
        with pytest.raises(SemanticGateClosed, match='contextual ALAS back'):
            adapter.click('BACK_ARROW')
        frame.click.assert_not_called()
    else:
        assert adapter.click('BACK_ARROW') is frame.click.return_value
        frame.click.assert_called_once_with(ready[0])
        assert adapter._commission_context.navigation_back_receipt is frame.click.return_value
    adapter._fresh_input_oracle.assert_called_once()


@pytest.mark.parametrize('bad_frame', [False, True])
def test_tactical_timer_obeys_native_screenshot_frame_without_live_fallback(bad_frame):
    adapter = AlasSemanticAdapter(make_oracle(FakeBackend([])), lambda: None)
    adapter.begin_tactical()
    frame = Mock()
    frame.tactical_remaining_seconds.return_value = (120, 480)
    adapter._frame_or_live_observation_oracle = Mock(return_value=frame)
    adapter.oracle.tactical_remaining_seconds = Mock(side_effect=AssertionError('live fallback'))
    if bad_frame:
        adapter._frame_or_live_observation_oracle.side_effect = SemanticGateClosed('invalid frame')
        with pytest.raises(SemanticGateClosed, match='invalid frame'):
            adapter.tactical_remaining_seconds()
        frame.tactical_remaining_seconds.assert_not_called()
    else:
        assert adapter.tactical_remaining_seconds() == (120, 480)
    adapter.oracle.tactical_remaining_seconds.assert_not_called()
