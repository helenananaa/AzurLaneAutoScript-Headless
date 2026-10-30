"""Inherited Daily selection must not be renamed to native carousel index1."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from alas_headless import SemanticGateClosed

from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('inherited', [0, 3])
def test_first_native_daily_pass_resets_inherited_position_before_assigning_index(inherited):
    position = [inherited]
    pages = []
    class BeforeResource(Exception):
        pass
    adapter = SimpleNamespace(open=lambda: SimpleNamespace(oracle=SimpleNamespace(
        daily_battle_result_visible=lambda: False)), daily_precombat_visible=lambda: False,
        daily_detail_visible=lambda: False)
    def ensure(page):
        pages.append(('ensure', page))
        if position[0] is None:
            position[0] = 0
    def goto(page):
        pages.append(('goto', page))
        position[0] = None
    def first_stage():
        assert position[0] == 0, 'inherited Daily4 must not become native Daily1'
        raise BeforeResource
    runner = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter, sleep=Mock(), screenshot=Mock()),
        daily_checked=[0], ui_ensure=ensure, ui_goto=goto, appear=lambda *a, **k: False,
        get_daily_stage_and_fleet=first_stage)
    run = method('module/daily/daily.py', 'Daily', 'daily_run_one',
        page_daily='daily', page_campaign_menu='campaign',
        ENTRANCE_EMERGENCY_MODULE_DEVELOPMENT='emergency', logger=Mock(),
        SemanticGateClosed=SemanticGateClosed)
    with pytest.raises(BeforeResource):
        run(runner)
    assert position[0] == 0
    assert runner.daily_current == 1 and runner.daily_checked == [0]
