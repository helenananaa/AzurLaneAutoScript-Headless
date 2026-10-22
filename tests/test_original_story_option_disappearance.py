import ast
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import source


@pytest.mark.parametrize('outcome', ['success', 'absent', 'partial', 'dispatched'])
def test_original_story_option_only_recovers_proven_zero_input_disappearance(outcome):
    owner = next(node for node in ast.parse(source('module/handler/info_handler.py')).body
                 if isinstance(node, ast.ClassDef) and node.name == 'InfoHandler')
    node = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == 'story_skip')
    node.decorator_list = []
    namespace = dict(logger=Mock())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])),
                 '<original-story>', 'exec'), namespace)
    oracle = SimpleNamespace(event_story_skip_prompt_visible=lambda: False,
        event_story_dialogue_visible=lambda: True, event_story_option_count=lambda: 2,
        input_dispatch_count=10, event_story_surface_absent=Mock(return_value=True))
    if outcome == 'partial':
        oracle.event_story_surface_absent.side_effect = SemanticGateClosed('unknown mounted story')
    def choose(index):
        assert index == 0
        if outcome == 'success':
            return object()
        if outcome == 'dispatched':
            oracle.input_dispatch_count += 1
        raise SemanticGateClosed('dialogue identity absent')
    adapter = SimpleNamespace(open=lambda: SimpleNamespace(oracle=oracle,
                                  _frame_or_live_observation_oracle=lambda: oracle), refresh_frame=Mock(),
                              click_event_story_option=Mock(side_effect=choose))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
        config=SimpleNamespace(STORY_OPTION=0), story_popup_timeout=Mock())
    if outcome in ('success', 'absent'):
        assert namespace['story_skip'](host) is (outcome == 'success')
    else:
        with pytest.raises(SemanticGateClosed):
            namespace['story_skip'](host)
    adapter.click_event_story_option.assert_called_once_with(0)
    if outcome in ('success', 'dispatched'):
        oracle.event_story_surface_absent.assert_not_called()
    else:
        oracle.event_story_surface_absent.assert_called_once_with()
    assert host.story_popup_timeout.reset.call_count == (outcome == 'success')
