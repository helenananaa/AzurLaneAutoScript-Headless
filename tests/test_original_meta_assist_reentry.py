from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.test_alas_config_branch_compatibility import method

@pytest.mark.parametrize('page', ['main', 'dossier', 'precombat', 'assist'])
def test_original_meta_assist_run_keeps_navigation_and_combat_owners(page):
    adapter = SimpleNamespace(begin_meta_assist=Mock(), end_meta_assist=Mock(),
                              meta_page_visible=lambda: page == 'dossier',
                              meta_precombat_visible=lambda: page == 'precombat')
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
                           config=SimpleNamespace(task_delay=Mock()),
                           _in_meta_assist_page=lambda: page == 'assist',
                           ui_ensure=Mock(), _make_an_attack=Mock(),
                           _begin_meta_assist=Mock(return_value=False))
    run = method('module/os_ash/meta.py', 'AshBeaconAssist', 'run', page_reward=object(), MetaReward=Mock())
    run(host)
    assert host.ui_ensure.call_count == (1 if page == 'main' else 0)
    assert host._make_an_attack.call_count == (1 if page == 'precombat' else 0)
    host._begin_meta_assist.assert_called_once()
    adapter.end_meta_assist.assert_called_once()
    host.config.task_delay.assert_called_once_with(minute=(10, 20))


def test_original_completed_assist_releases_combat_before_meta_reward():
    calls = []
    adapter = SimpleNamespace(begin_meta_assist=Mock(), end_meta_assist=Mock(),
                              meta_page_visible=lambda: True, meta_precombat_visible=lambda: False,
                              complete_meta_assist_combat=lambda: calls.append('release'))
    reward = SimpleNamespace(run=lambda: calls.append('reward'))
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter),
                           config=SimpleNamespace(task_delay=Mock()),
                           _in_meta_assist_page=lambda: True,
                           ui_ensure=Mock(), _make_an_attack=Mock(),
                           _begin_meta_assist=Mock(return_value=True))
    run = method('module/os_ash/meta.py', 'AshBeaconAssist', 'run', page_reward=object(),
                 MetaReward=lambda *args: reward)
    run(host)
    assert calls == ['release', 'reward']
    host.config.task_delay.assert_called_once_with(server_update=True)
