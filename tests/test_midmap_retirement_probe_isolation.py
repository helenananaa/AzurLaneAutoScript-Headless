"""Retained dock snapshot catches probes from the real combat call chain."""
from types import SimpleNamespace

import pytest

from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.midmap_replay import ReplayRuntime, retained_payload
from tests.semantic_support.campaign_fixtures import make_normal_fleet_preparation_backend
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_text, make_ui


def dock_runtime():
    return ReplayRuntime(retained_payload(
        'integration/alas/campaign-midmap-continuous-20260913/blocked-r2.json'))


@pytest.mark.parametrize('committed', [False, True])
def test_retained_dock_all_observed_unrelated_probes_are_absent(committed):
    runtime = dock_runtime()
    session = runtime.session()
    try:
        if committed:
            session.open()._campaign_context.combat_receipt = SimpleNamespace(generation=99)
        oracle = session.open().oracle
        assert runtime.payload['ui']['toggle_truncated'] is True
        assert oracle.retirement_selection_visible()
        assert oracle.campaign_preparation_state('10-2') is None
        assert not oracle.daily_battle_result_visible()
        assert not oracle.login_update_download_available()
        assert not oracle.login_update_restart_prompt_available()
        assert not oracle.login_update_in_progress()
        assert not oracle.enabled('overlay/login-data-expired/confirm')
        for name in ('GAME_TIPS', 'GAME_TIPS3', 'GAME_TIPS4'):
            assert session.appear(SimpleNamespace(name=name)) is False
        assert session.appear(SimpleNamespace(name='IN_RETIREMENT_CHECK'))
        with pytest.raises(SemanticGateClosed):
            oracle.read_ui_state()
        assert runtime.actions == []
    finally:
        session.close()


@pytest.mark.parametrize('damage', ['text', 'back', 'foreground'])
def test_dock_absence_proof_does_not_hide_missing_required_evidence(damage):
    runtime = dock_runtime()
    if damage == 'text':
        runtime.payload['ui']['text_truncated'] = True
    elif damage == 'back':
        for button in runtime.payload['state']['buttons']['buttons']:
            if button['path'].endswith('/adapt/top/back'):
                button['raycast_top'] = False
    else:
        runtime.foreground = 'unrelated.package/.Activity'
    session = None
    try:
        with pytest.raises(SemanticGateClosed):
            from alas_headless import AlasSemanticSession
            from tests.semantic_support.midmap_replay import REVISION
            session = AlasSemanticSession(runtime_handle=runtime, driver_revision=REVISION)
            session.open().oracle.retirement_page_back_available()
        assert runtime.actions == []
    finally:
        if session:
            session.close()


def test_present_preparation_still_requires_complete_toggles():
    backend = make_normal_fleet_preparation_backend('10-2')
    oracle = make_oracle(backend)
    assert oracle.campaign_preparation_state('10-2') is not None
    backend.ui['toggle_truncated'] = True
    with pytest.raises(SemanticGateClosed, match='toggle'):
        oracle.campaign_preparation_state('10-2')


def test_login_text_capability_tolerates_other_arrays_but_not_text_loss():
    backend = FakeBackend([])
    backend.ui = make_ui([make_text('正在下载更新:进度103.2MB/796.8MB  总共982个  '
        '已完成426个  失败0个  速度3.63MB/S', 'root/Overlay/UIMain/UpdatePanel/progressInfo')])
    backend.ui.update(toggle_truncated=True, image_truncated=True)
    oracle = make_oracle(backend)
    assert oracle.login_update_in_progress()
    backend.ui['text_truncated'] = True
    with pytest.raises(SemanticGateClosed):
        oracle.login_update_in_progress()
