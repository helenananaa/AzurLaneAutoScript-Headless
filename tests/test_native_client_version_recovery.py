import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui
from tests.test_alas_config_branch_compatibility import method


WARNING = '指挥官，当前客户端的游戏版本不是最新的，推荐您重新打开游戏进行更新'
ROOT = 'UICamera/Canvas/UIOrigin/Msgbox(Clone)/window/'


def warning_backend():
    backend = FakeBackend([make_button('custom_button_1(Clone)',
        ROOT + 'button_container/custom_button_1(Clone)', raycast_top=False)])
    backend.ui = make_ui([make_text(WARNING, ROOT + 'msg_panel/content'),
                          make_text('确 定', ROOT + 'button_container/custom_button_1(Clone)/pic')])
    return backend


@pytest.mark.parametrize('change,expected', [('baseline', True), ('extra_metadata', True),
    ('foreign_prompt', False), ('truncated', False), ('absent', False)])
def test_version_warning_is_passive_restart_classification_not_button_authority(change, expected):
    backend = warning_backend()
    if change == 'extra_metadata':
        backend.ui['future_metadata'] = {'anything': True}
    elif change == 'foreign_prompt':
        backend.ui['texts'][0]['text'] = '学习完成，是否继续学习？'
    elif change == 'truncated':
        backend.ui['texts'][0]['flags'] |= 0x10
    elif change == 'absent':
        backend = FakeBackend([])
    assert make_oracle(backend).client_version_update_required() is expected
    assert backend.taps == []


@pytest.mark.parametrize('change', ['ambiguous', 'stale', 'wrong_package', 'incoherent'])
def test_bad_version_warning_observation_cannot_request_restart(change):
    backend = warning_backend()
    if change == 'ambiguous':
        backend.ui['texts'].append(dict(backend.ui['texts'][0]))
        backend.ui['text_count'] += 1
    elif change == 'stale':
        backend.ui['age_ms'] = 10001
    elif change == 'wrong_package':
        backend.snapshot['package'] = 'other.package'
    else:
        backend.ui['generation'] = 13
    with pytest.raises(SemanticGateClosed):
        make_oracle(backend).client_version_update_required()
    assert backend.taps == []


@pytest.mark.parametrize('semantic,required', [(False, False), (True, False), (True, True)])
def test_native_ui_warning_enters_existing_game_bug_restart_branch(monkeypatch, semantic, required):
    class NativeGameBugError(Exception):
        pass
    monkeypatch.setitem(sys.modules, 'module.exception', SimpleNamespace(GameBugError=NativeGameBugError))
    check = method('module/ui/ui.py', 'UI', '_check_semantic_client_version')
    adapter = Mock() if semantic else None
    if adapter is not None:
        adapter.client_version_update_required.return_value = required
    device = SimpleNamespace(semantic_adapter=adapter, click=Mock())
    if semantic and required:
        with pytest.raises(NativeGameBugError, match='native Restart/update'):
            check(SimpleNamespace(device=device))
    else:
        check(SimpleNamespace(device=device))
    device.click.assert_not_called()


def test_version_warning_precedes_navigation_on_known_underlay(monkeypatch):
    class NativeGameBugError(Exception):
        pass
    monkeypatch.setitem(sys.modules, 'module.exception', SimpleNamespace(GameBugError=NativeGameBugError))
    adapter = SimpleNamespace(client_version_update_required=lambda: True)
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=adapter, screenshot=Mock(), click=Mock()),
                           interval_clear=Mock(), ui_page_appear=Mock(return_value=True))
    host._check_semantic_client_version = method(
        'module/ui/ui.py', 'UI', '_check_semantic_client_version').__get__(host)
    goto = method('module/ui/ui.py', 'UI', 'ui_goto',
                  Page=SimpleNamespace(init_connection=Mock(), iter_check_buttons=lambda: []),
                  GOTO_MAIN=SimpleNamespace(clear_offset=Mock()), logger=Mock())
    with pytest.raises(NativeGameBugError):
        goto(host, object())
    host.ui_page_appear.assert_not_called()
    host.device.click.assert_not_called()
