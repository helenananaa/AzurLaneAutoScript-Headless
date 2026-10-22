"""Execute the original patched ALAS preparation decisions in isolation."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def preparation_decisions():
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/map/map_operation.py'
    if not source.exists():
        pytest.skip('materialized patched ALAS tree unavailable')
    tree = ast.parse(source.read_text(encoding='utf-8'))
    mode = next(node for node in ast.walk(tree) if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'observed_mode' for t in node.targets))
    progress = next(node for node in ast.walk(tree) if isinstance(node, ast.If)
                    and 'self.config.MAP_IS_ONE_TIME_STAGE' in ast.unparse(node.test)
                    and "self.config.Campaign_Name.lower() == 'sp'" in ast.unparse(node.test))
    return compile(ast.fix_missing_locations(ast.Module(body=[mode, progress], type_ignores=[])), str(source), 'exec')


@pytest.mark.parametrize('selected', [True, False])
def test_sp_uses_original_automation_decision_without_inventing_progress(selected):
    oracle = SimpleNamespace(campaign_map_preparation_mode_state=Mock(side_effect=AssertionError('SP has no switch')),
        campaign_map_clear_percentage=Mock(side_effect=AssertionError('SP has no progress')),
        campaign_auto_search_selected=Mock(return_value=selected), campaign_clear_mode_available=Mock(return_value=True))
    host = SimpleNamespace(config=SimpleNamespace(MAP_HAS_MODE_SWITCH=False, Campaign_Mode='normal',
        MAP_IS_ONE_TIME_STAGE=True, Campaign_Name='sp'), map_clear_percentage=0, map_is_100_percent_clear=False)
    namespace = {'self': host, 'semantic_adapter': oracle}
    exec(preparation_decisions(), namespace)
    assert namespace['observed_mode'] == 'normal'
    assert host.map_has_clear_mode is selected
    assert host.map_clear_percentage == 0 and host.map_is_100_percent_clear is False


@pytest.mark.parametrize('percentage', [0.5, 1.0])
def test_shared_d3_keeps_difficulty_and_progress_contract(percentage):
    oracle = SimpleNamespace(campaign_map_preparation_mode_state=Mock(return_value='hard'),
        campaign_map_clear_percentage=Mock(return_value=percentage),
        campaign_auto_search_selected=Mock(side_effect=AssertionError('not the SP branch')),
        campaign_clear_mode_available=Mock(return_value=True))
    host = SimpleNamespace(config=SimpleNamespace(MAP_HAS_MODE_SWITCH=True, Campaign_Mode='hard',
        MAP_IS_ONE_TIME_STAGE=False, Campaign_Name='d3'))
    namespace = {'self': host, 'semantic_adapter': oracle}
    exec(preparation_decisions(), namespace)
    assert namespace['observed_mode'] == 'hard'
    assert host.map_has_clear_mode is (percentage > 0.95)
    oracle.campaign_map_preparation_mode_state.assert_called_once()
    oracle.campaign_map_clear_percentage.assert_called_once()


@pytest.mark.parametrize('one_time, name, remaining, delayed', [
    (True, 'sp', 0, True), (True, 'sp', 1, False),
    (True, 'sp', None, False), (False, 'd3', 0, False),
    (False, 'sp', 0, True),
])
def test_original_run_delays_only_proven_exhausted_sp(one_time, name, remaining, delayed):
    source = Path(__file__).resolve().parents[1] / 'artifacts/campaign-preparation/upstream/module/campaign/run.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    branch = next(n for n in ast.walk(tree) if isinstance(n, ast.If)
                  and 'campaign_remaining_attempts' in ast.unparse(n.test))
    loop = ast.For(target=ast.Name(id='_', ctx=ast.Store()),
                   iter=ast.List(elts=[ast.Constant(0)], ctx=ast.Load()),
                   body=[branch], orelse=[])
    host = SimpleNamespace(campaign=SimpleNamespace(config=SimpleNamespace(MAP_IS_ONE_TIME_STAGE=one_time)),
                           config=SimpleNamespace(Campaign_Name=name, task_delay=Mock()))
    adapter = SimpleNamespace(campaign_remaining_attempts=Mock(return_value=remaining))
    code = compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])), str(source), 'exec')
    exec(code, {'self': host, 'semantic_adapter': adapter, 'logger': Mock()})
    assert host.config.task_delay.called is delayed
    if delayed:
        host.config.task_delay.assert_called_once_with(server_update=True)
    if name != 'sp':
        adapter.campaign_remaining_attempts.assert_not_called()
