import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_one_claim_waits_for_original_popup_transition_without_second_claim():
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/reward/reward.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8')))
                if isinstance(n, ast.FunctionDef) and n.name == '_reward_mission_claim_click')
    interval = SimpleNamespace(reached=lambda:True, reset=Mock())
    namespace = {'Timer':lambda *a,**k:interval, 'logger':Mock(), 'page_mission':object(),
                 'MISSION_MULTI':object(), 'MISSION_SINGLE':object(), 'MISSION_UNFINISH':object()}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), str(source), 'exec'), namespace)
    adapter = SimpleNamespace(mission_claim_allowed=Mock(return_value=False))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter), loop=lambda:iter(range(4)),
                           ui_page_appear=Mock(side_effect=[True,True,False]),
                           appear_then_click=Mock(return_value=True))
    assert namespace['_reward_mission_claim_click'](host) is True
    assert host.ui_page_appear.call_count == 3
    host.appear_then_click.assert_called_once()
    assert adapter.mission_claim_allowed.call_count == 2
