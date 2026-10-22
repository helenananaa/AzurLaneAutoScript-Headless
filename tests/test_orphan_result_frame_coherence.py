from unittest.mock import Mock
import pytest
from tests.test_frame_post_input_foreground import session_for_meta

@pytest.mark.parametrize('result',[False,True])
def test_orphan_result_probe_uses_one_current_frame_instead_of_two_live_reads(result):
    backend,s,frame=session_for_meta()
    live=s.open()._live_oracle
    live.daily_battle_result_visible=Mock(side_effect=AssertionError('redundant live result read'))
    live.campaign_battle_reward_visible=Mock(side_effect=AssertionError('cross-frame reward read'))
    frame.daily_battle_result_visible=Mock(return_value=False)
    frame.campaign_battle_reward_visible=Mock(return_value=result)
    assert s.orphan_combat_result_visible() is result
    assert not backend.taps
    assert frame.daily_battle_result_visible.call_count==1
    assert frame.campaign_battle_reward_visible.call_count==1
