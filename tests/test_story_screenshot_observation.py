"""Original story discovery consumes its ALAS screenshot, not a second live read."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('kind', ['idle', 'combat', 'result'])
def test_outer_native_story_handler_uses_the_same_screenshot_for_daily_exclusion(kind):
    observation=SimpleNamespace(daily_combat_visible=lambda:kind=='combat',
                                daily_battle_result_visible=lambda:kind=='result')
    live=Mock()
    live.daily_combat_visible.side_effect=AssertionError('outer story probe used live state')
    live.daily_battle_result_visible.side_effect=AssertionError('outer story probe used live state')
    session=SimpleNamespace(campaign_combat_active=lambda:False,
        open=lambda:SimpleNamespace(oracle=live,_frame_or_live_observation_oracle=lambda:observation))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),map_is_threat_safe=False,
                         story_skip=Mock(return_value=True))
    handle=method('module/handler/info_handler.py','InfoHandler','handle_story_skip')
    assert handle(host) is (kind=='idle')
    assert host.story_skip.call_count==(1 if kind=='idle' else 0)


@pytest.mark.parametrize('case', ['idle', 'unknown', 'skip-prompt', 'options', 'dialogue-no-skip'])
def test_original_story_discovery_uses_frame_and_keeps_native_action_branch(case):
    observation=Mock()
    observation.event_story_skip_prompt_visible.return_value=case=='skip-prompt'
    observation.event_story_dialogue_visible.return_value=case in ('options','dialogue-no-skip')
    observation.event_story_option_count.return_value=2 if case=='options' else 0
    observation.event_story_surface_absent.return_value=True
    if case=='unknown':observation.event_story_surface_absent.side_effect=SemanticGateClosed('unsupported story')
    live=Mock(input_dispatch_count=0)
    for name in ('event_story_skip_prompt_visible','event_story_dialogue_visible','event_story_option_count','event_story_surface_absent'):
        getattr(live,name).side_effect=AssertionError('passive story discovery used live observation')
    session=Mock()
    session.open.return_value=SimpleNamespace(oracle=live,_frame_or_live_observation_oracle=lambda:observation)
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),story_popup_timeout=Mock(),
                         config=SimpleNamespace(STORY_ALLOW_SKIP=False,STORY_OPTION=1))
    story_skip=method('module/handler/info_handler.py','InfoHandler','story_skip',Timer=Mock())
    if case=='unknown':
        with pytest.raises(SemanticGateClosed,match='unsupported story'):story_skip(host)
    else:
        assert story_skip(host) is (case in ('skip-prompt','options'))
    if case in ('skip-prompt','options'):
        session.refresh_frame.assert_called_once()
        (session.click_event_story_skip_confirm if case=='skip-prompt' else session.click_event_story_option).assert_called_once()
    else:session.refresh_frame.assert_not_called()
