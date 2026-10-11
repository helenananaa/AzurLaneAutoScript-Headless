"""Native ui_goto reuses native unknown-page recovery after page handoffs."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('semantic,reviewed_home', [(True, True), (True, False), (False, True)])
def test_native_goto_uses_existing_recovery_only_for_reviewed_semantic_home(semantic, reviewed_home):
    page = SimpleNamespace(init_connection=Mock(), iter_check_buttons=lambda: [],
                           iter_pages=lambda: [], clear_connection=Mock())
    goto = method('module/ui/ui.py', 'UI', 'ui_goto', Page=page,
                  GOTO_MAIN=SimpleNamespace(clear_offset=Mock()), logger=Mock())
    adapter = SimpleNamespace(mail_reward_active=lambda: False) if semantic else None
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter, screenshot=Mock(), click=Mock()),
        interval_clear=Mock(), _check_semantic_client_version=Mock(),
        ui_page_appear=Mock(side_effect=[False, True]), appear=Mock(return_value=reviewed_home),
        ui_get_current_page=Mock(), ui_additional=Mock(return_value=False))
    goto(host, object())
    if semantic and reviewed_home:
        host.ui_get_current_page.assert_called_once_with()
        host.ui_additional.assert_not_called()
    else:
        host.ui_get_current_page.assert_not_called()
        host.ui_additional.assert_called_once_with(get_ship=True)
    host.device.click.assert_not_called()
    page.clear_connection.assert_called_once_with()
