"""Execute the actual patched ALAS walk owner with controlled semantic frames."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed


class Timer:
    def __init__(self, *args, **kwargs):
        self.resets = 0

    def start(self):
        return self

    def reset(self):
        self.resets += 1

    def reached(self):
        return True


def walk_function():
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/os/fleet.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    owner = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'OSFleet')
    function = next(node for node in owner.body if isinstance(node, ast.FunctionDef) and node.name == 'wait_until_walk_stable')
    namespace = {'Timer': Timer, 'logger': Mock()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), str(source), 'exec'), namespace)
    return namespace['wait_until_walk_stable']


def host(events):
    semantic = SimpleNamespace(operation_siren_low_resolve_prompt_visible=Mock(return_value=False),
                               operation_siren_map_visible=Mock(return_value=True))
    return SimpleNamespace(device=SimpleNamespace(semantic_adapter=semantic,
        screenshot_interval_set=Mock(), stuck_record_clear=Mock(), click_record_clear=Mock()),
        loop=lambda **kwargs: iter(range(8)), handle_map_event=Mock(side_effect=events),
        handle_popup_confirm=Mock(return_value=False), combat_appear=Mock(return_value=False))


@pytest.mark.parametrize('events, cleared', [
    (['story_skip', 'map_get_items', ''], True),
    (['map_confirmation', 'map_get_items', ''], False),
    (['story_skip', 'ash_popup', 'map_get_items', ''], False),
    ([''], False),
])
def test_walk_preserves_original_event_owner_and_reward_history(events, cleared):
    caller = host(events)
    drop = object()
    result = walk_function()(caller, drop=drop)
    assert result == ('event' if len(events) > 1 else '')
    assert caller.device.click_record_clear.call_count == int(cleared)
    assert all(call.kwargs == {'drop': drop} for call in caller.handle_map_event.call_args_list)
    assert caller.device.semantic_adapter.operation_siren_map_visible.call_count == 1
    assert caller.combat_appear.call_count == 1


def test_walk_calls_original_confirmation_owner_before_map_stability():
    caller = host(['', ''])
    caller.handle_popup_confirm.side_effect = [True, False]
    assert walk_function()(caller) == ''
    assert caller.handle_popup_confirm.call_args_list[0].args == ('WALK_UNTIL_STABLE',)
    assert caller.device.semantic_adapter.operation_siren_map_visible.call_count == 1


def test_walk_does_not_ignore_unknown_or_obscured_event_failure():
    caller = host([])
    caller.handle_map_event.side_effect = SemanticGateClosed('story option is ambiguous')
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        walk_function()(caller)
    caller.handle_popup_confirm.assert_not_called()
    caller.device.semantic_adapter.operation_siren_map_visible.assert_not_called()
