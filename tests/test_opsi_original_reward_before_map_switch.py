import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

class CampaignEnd(Exception): pass

def method():
    source=Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream/module/os_handler/map_event.py'
    node=next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
              if isinstance(n,ast.FunctionDef) and n.name=='handle_os_auto_search_map_option')
    scope={'logger':Mock(),'CampaignEnd':CampaignEnd}
    for name in ('AUTO_SEARCH_REWARD','AUTO_SEARCH_OS_MAP_OPTION_OFF',
                 'AUTO_SEARCH_OS_MAP_OPTION_OFF_DISABLED','AUTO_SEARCH_OS_MAP_OPTION_ON'):
        scope[name]=name
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
    return scope['handle_os_auto_search_map_option']

@pytest.mark.parametrize('cleared',[False,True])
def test_foreground_reward_reaches_existing_quit_branch_before_map_reader(cleared):
    semantic=SimpleNamespace(operation_siren_map_visible=Mock(side_effect=AssertionError('covered map')))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=semantic,screenshot_interval_set=Mock()),
        appear=lambda button,**kwargs:button=='AUTO_SEARCH_REWARD',
        match_template_color=Mock(return_value=False),os_auto_search_quit=Mock(return_value=cleared))
    if cleared:
        with pytest.raises(CampaignEnd): method()(host)
    else:
        assert method()(host) is True
    host.os_auto_search_quit.assert_called_once_with(drop=None)
    semantic.operation_siren_map_visible.assert_not_called()

def test_unproven_reward_and_hidden_map_remain_passive():
    semantic=SimpleNamespace(operation_siren_map_visible=Mock(return_value=False))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=semantic),appear=Mock(return_value=False),
        match_template_color=Mock(side_effect=AssertionError('covered switch')),os_auto_search_quit=Mock())
    assert method()(host) is False
    semantic.operation_siren_map_visible.assert_called_once_with()
    host.os_auto_search_quit.assert_not_called()

def test_uncovered_map_keeps_existing_switch_path(monkeypatch):
    import alas_headless
    monkeypatch.setattr(alas_headless,'current_semantic_session',lambda:None)
    semantic=SimpleNamespace(operation_siren_map_visible=Mock(return_value=True))
    host=SimpleNamespace(device=SimpleNamespace(semantic_adapter=semantic),appear=Mock(return_value=False),
        match_template_color=Mock(return_value=False),os_auto_search_quit=Mock())
    assert method()(host,enable=None) is False
    semantic.operation_siren_map_visible.assert_called_once_with()
    host.os_auto_search_quit.assert_not_called()
