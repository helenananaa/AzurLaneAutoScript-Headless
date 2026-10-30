"""Daily detail does not satisfy the original native overview check."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_game_tips_loading_presence import host
from tests.semantic_support.observer_fixtures import make_button
from tests.test_daily_automation_info_underlay import method


@pytest.mark.parametrize('drift', [False, True])
@pytest.mark.parametrize('detail', [False, True])
def test_real_daily_entry_shortcut_distinguishes_detail(drift, detail):
    backend, oracle, adapter = host(drift, 'daily-renamed-back-r181.json')
    if detail:
        backend.buttons['buttons'].append(make_button('info',
            'UICamera/Canvas/UIMain/DailyLevelUI(Clone)/desc_panel/main_mask/'
            'main/scrollview/content/stagetpl(Clone)/info'))
        backend.buttons['button_count'] += 1
    assert oracle.daily_page_visible()
    assert oracle.daily_detail_visible() is detail
    assert oracle.daily_navigation_visible()
    assert oracle.daily_entry_visible() is (not detail)
    assert adapter.appear('DAILY_CHECK') is (not detail)
    assert not backend.taps


def test_native_inherited_detail_uses_original_ui_click_until_overview():
    class ReachedOverviewLoop(Exception):
        pass
    adapter = SimpleNamespace(open=lambda: SimpleNamespace(oracle=SimpleNamespace(
        daily_battle_result_visible=lambda: False)), daily_precombat_visible=lambda: False,
        daily_detail_visible=lambda: True)
    runner = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
        ui_ensure=Mock())
    def ui_click(click_button, check_button):
        assert click_button == 'BACK_ARROW'
        assert check_button == 'DAILY_CHECK'
        raise ReachedOverviewLoop
    runner.ui_click = ui_click
    recovery = method('module/daily/daily.py', 'Daily', 'daily_run_one',
        logger=Mock(), BACK_ARROW='BACK_ARROW', DAILY_CHECK='DAILY_CHECK')
    with pytest.raises(ReachedOverviewLoop):
        recovery(runner)
    runner.ui_ensure.assert_not_called()
