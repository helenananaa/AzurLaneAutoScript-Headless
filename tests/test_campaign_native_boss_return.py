"""Original ALAS owns stage settling, late settlement and CampaignEnd."""
import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from tests.alas_test_source import patched_alas_root


@pytest.mark.parametrize('final_page', ['stage', 'unknown'])
def test_native_boss_result_keeps_grade_statistics_rewards_and_late_total_handlers(final_page):
    root = patched_alas_root()
    status_tree = ast.parse(Path(root, 'module/combat/combat.py').read_text(encoding='utf-8'))
    status = next(n for n in ast.walk(status_tree) if isinstance(n, ast.FunctionDef)
        and n.name == 'combat_status')
    tree = ast.parse(Path(root, 'module/handler/enemy_searching.py').read_text(encoding='utf-8'))
    stage = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'handle_in_stage')
    class CampaignEnd(Exception): pass
    class Host(SimpleNamespace):
        def __getattr__(self, name):
            if name.startswith('handle_'):
                method = Mock(return_value=False)
                setattr(self, name, method)
                return method
            raise AttributeError(name)
    frame, actions = [None], []
    def loop():
        for name in ('grade', 'statistics', 'reward', 'stage-peek', 'total', final_page):
            frame[0] = name
            yield
    def handle(*names):
        def invoke(*args, **kwargs):
            if frame[0] in names:
                actions.append(frame[0])
                return True
            return False
        return Mock(side_effect=invoke)
    adapter = SimpleNamespace(campaign_combat_committed=lambda: True,
        operation_siren_combat_committed=lambda: False)
    session = SimpleNamespace(open=lambda: adapter,
        close_campaign_battle_fail_tip_if_present=lambda: False,
        campaign_is_in_map_after_combat=Mock(side_effect=AssertionError('boss must use native result loop')))
    host = Host(device=SimpleNamespace(semantic_adapter=session, screenshot_interval_set=Mock(),
        stuck_record_clear=Mock(), click_record_clear=Mock()), loop=loop,
        is_in_stage=lambda: frame[0] in ('stage-peek', 'stage'), appear=lambda *a, **kw: False,
        in_stage_timer=SimpleNamespace(reached=lambda: frame[0] == 'stage', reset=Mock()),
        ensure_no_info_bar=Mock(), handle_battle_status=handle('grade', 'statistics'),
        handle_get_items=handle('reward'), handle_exp_info=Mock(return_value=False),
        handle_auto_search_exit=handle('total'))
    scope = dict(logger=Mock(), CampaignEnd=CampaignEnd,
        MAP_PREPARATION=object(), FLEET_PREPARATION=object())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[status, stage], type_ignores=[])),
        '<native complete result loop>', 'exec'), scope)
    host.handle_in_stage = lambda: scope['handle_in_stage'](host)
    if final_page == 'stage':
        with pytest.raises(CampaignEnd): scope['combat_status'](host, expected_end='in_stage')
        host.ensure_no_info_bar.assert_called_once_with(timeout=1.2)
    else:
        scope['combat_status'](host, expected_end='in_stage')
        host.ensure_no_info_bar.assert_not_called()
    assert actions == ['grade', 'statistics', 'reward', 'total']
    assert host.handle_exp_info.call_count >= 1
    session.campaign_is_in_map_after_combat.assert_not_called()


@pytest.mark.parametrize('automatic', [False, True])
def test_native_campaign_end_keeps_original_exit_and_then_records_manual_completion(automatic):
    root = patched_alas_root()
    tree = ast.parse(Path(root, 'module/campaign/campaign_base.py').read_text(encoding='utf-8'))
    handler = next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)
        and isinstance(n.type, ast.Name) and n.type.id == 'CampaignEnd')
    function = ast.FunctionDef(name='finish', args=ast.arguments(posonlyargs=[], args=[],
        kwonlyargs=[], kw_defaults=[], defaults=[]), body=handler.body, decorator_list=[])
    order = []
    host = SimpleNamespace(map_is_auto_search=automatic,
        ensure_auto_search_exit=lambda: order.append('native-exit'))
    adapter = SimpleNamespace(campaign_boss_returned_to_stage=lambda: order.append('manual-proof'),
        campaign_auto_search_result_visible=lambda: order.append('automatic-proof'))
    ns = dict(self=host, semantic_adapter=adapter, logger=Mock())
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), '<native end>', 'exec'), ns)
    assert ns['finish']() is True
    assert order == (['automatic-proof'] if automatic else ['native-exit', 'manual-proof'])
