import sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('state',['present','disappeared','unsafe'])
def test_native_map_event_uses_existing_presence_driven_input(monkeypatch,state):
    target=SimpleNamespace(name='POPUP_CONFIRM')
    monkeypatch.setitem(sys.modules,'module.handler.assets',SimpleNamespace(POPUP_CONFIRM=target))
    error=SemanticGateClosed('unknown actual prompt')
    adapter=SimpleNamespace(click_if_present=Mock(return_value=(object() if state=='present' else None),
        side_effect=error if state=='unsafe' else None))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,click=Mock(side_effect=AssertionError('unconditional click forbidden'))),
        ensure_button=lambda button:button,appear=Mock(return_value=True))
    for name in ('handle_map_get_items','handle_os_game_tips','handle_map_archives',
        'handle_guild_popup_cancel','handle_ash_popup','handle_urgent_commission','handle_story_skip'):
        setattr(host,name,Mock(return_value=False))
    native_click=method('module/base/base.py','ModuleBase','appear_then_click')
    host.appear_then_click=lambda button:native_click(host,button)
    event=method('module/os_handler/map_event.py','MapEventHandler','handle_map_event')
    if state=='unsafe':
        with pytest.raises(SemanticGateClosed) as caught:event(host)
        assert caught.value is error
    else:
        assert event(host)==('map_confirmation' if state=='present' else '')
    adapter.click_if_present.assert_called_once_with(target)
    host.device.click.assert_not_called()
