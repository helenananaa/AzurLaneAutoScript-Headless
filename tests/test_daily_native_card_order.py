import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed

@pytest.mark.parametrize('semantic,expected', [(True,[4]), (False,[])])
def test_original_daily_loop_keeps_pixel_placeholder_and_handles_reordered_typed_card(semantic,expected):
    source = Path(__file__).resolve().parents[1]/'artifacts/campaign-preparation/upstream/module/daily/daily.py'
    node = next(n for n in ast.walk(ast.parse(source.read_text(encoding='utf-8'))) if isinstance(n,ast.FunctionDef) and n.name=='daily_run_one')
    env = {'logger':Mock(),'page_daily':'daily','page_campaign_menu':'campaign','ENTRANCE_EMERGENCY_MODULE_DEVELOPMENT':'emergency','SemanticGateClosed':SemanticGateClosed,'OCR_REMAIN':SimpleNamespace(ocr=lambda _:3)}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),str(source),'exec'),env)
    adapter = SimpleNamespace(daily_current_remain=lambda:3,daily_detail_visible=lambda:False,daily_precombat_visible=lambda:False,open=lambda:SimpleNamespace(oracle=SimpleNamespace(daily_battle_result_visible=lambda:False))) if semantic else None
    calls = []
    owner = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter,sleep=Mock(),screenshot=Mock(),image=None),daily_checked=[0,1,2,3],empty_index=4,supply_line_disruption_index=2,config=SimpleNamespace(Daily_UseDailySkip=True),daily_semantic_kind='escort_mission',ui_ensure=Mock(),ui_goto=Mock(),appear=lambda *a,**k:False)
    owner.next = lambda: setattr(owner,'daily_current',owner.daily_current+1)
    owner.daily_check = lambda: owner.daily_checked.append(owner.daily_current)
    owner.get_daily_stage_and_fleet = lambda:(1,1)
    owner.is_active = lambda: owner.daily_current==4
    owner.daily_execute = lambda **kwargs:calls.append(owner.daily_current)
    env['daily_run_one'](owner)
    assert calls==expected
