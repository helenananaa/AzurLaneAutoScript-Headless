from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless.oracle.errors import SemanticGateClosed, SemanticInputBlocked
from tests.test_alas_config_branch_compatibility import method
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


def test_blocked_input_retains_typed_reason_and_never_sends_navigation():
    backend = FakeBackend([
        make_button('settings', 'root/frame/top/btns/settings', 1221, 36),
        make_button('close_btn', 'Overlay/UIMain/NewBulletinBoardUI(Clone)/bg/close_btn', 1204, 83),
    ])
    oracle = make_oracle(backend)
    with pytest.raises(SemanticInputBlocked) as rejected:
        oracle.click('main/settings')
    assert rejected.value.semantic_id == 'main/settings'
    assert rejected.value.blockers == ('bulletin',)
    assert backend.taps == []
    oracle.click('overlay/bulletin/close')
    assert backend.taps == [(1204, 83)]


@pytest.mark.parametrize('error', [
    SemanticInputBlocked('main/guild', 11, ['bulletin']),
    SemanticInputBlocked('os/page/back', 11, ['opsi-exit']),
    SemanticInputBlocked('main/guild', 11, ['opsi-exit']),
    SemanticInputBlocked('os/page/back', 11, ['opsi-exit', 'msgbox']),
    SemanticInputBlocked('main/guild', 11, ['msgbox']),
    SemanticInputBlocked('main/guild', 11, ['bulletin', 'msgbox']),
    SemanticGateClosed('foreground changed immediately before input'),
    None,
])
def test_native_navigation_consumes_only_known_preinput_overlay_races(error):
    destination = object()
    button = object()
    page = SimpleNamespace(parent=destination, check_button=object(), links={destination: button})
    pages = SimpleNamespace(init_connection=Mock(), clear_connection=Mock(),
                            iter_check_buttons=lambda: [], iter_pages=lambda: [page])
    events = []
    done = False
    def click(target):
        nonlocal done
        events.append('navigation')
        if error is not None:
            raise error
        done = True
    def additional(**kw):
        nonlocal done
        events.append('native-additional')
        done = True
        return True
    host = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=SimpleNamespace(mail_reward_active=lambda: False,
            client_version_update_required=lambda: False),
            screenshot=lambda: events.append('screenshot'), click=click),
        interval_clear=Mock(), ui_button_interval_reset=Mock(),
        _handle_semantic_orphan_result=Mock(return_value=False),
        ui_page_appear=lambda **kw: done,
        appear=lambda target, *a, **kw: target is page.check_button,
        ui_additional=additional)
    original = method('module/ui/ui.py', 'UI', 'ui_goto', Page=pages,
                      GOTO_MAIN=SimpleNamespace(clear_offset=Mock()), logger=Mock())
    host._check_semantic_client_version = method(
        'module/ui/ui.py', 'UI', '_check_semantic_client_version').__get__(host)
    if error is not None and not (isinstance(error, SemanticInputBlocked) and
            (error.blockers == ('bulletin',) or
             (error.semantic_id == 'os/page/back' and error.blockers == ('opsi-exit',)))):
        with pytest.raises(type(error)):
            original(host, destination, skip_first_screenshot=True)
        assert events == ['navigation']
    else:
        original(host, destination, skip_first_screenshot=True)
        assert events == (['navigation', 'screenshot', 'native-additional', 'screenshot']
                          if error else ['navigation', 'screenshot'])
        pages.clear_connection.assert_called_once()


@pytest.mark.parametrize('covered', [True, False])
def test_bulletin_raycast_loss_retains_native_reentry_reason(covered):
    backend = FakeBackend([
        make_button('extend', 'root/NewMainMellowTheme(Clone)/frame/left/extend', 40, 230,
                    raycast_top=not covered),
        make_button('close_btn', 'Overlay/UIMain/NewBulletinBoardUI(Clone)/bg/close_btn', 1204, 83),
    ])
    with pytest.raises(SemanticInputBlocked) as rejected:
        make_oracle(backend).click('main/more')
    assert rejected.value.blockers == ('bulletin',)
    assert backend.taps == []


def test_unexplained_raycast_loss_still_fails_without_navigation():
    backend = FakeBackend([make_button('extend',
        'root/NewMainMellowTheme(Clone)/frame/left/extend', 40, 230, raycast_top=False)])
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        make_oracle(backend).click('main/more')
    assert backend.taps == []


def test_actual_r117_frozen_bulletin_frame_retains_blocker_reason():
    import json
    from pathlib import Path
    from alas_headless.adapter.frame import _FrameBoundSemanticOracle
    from alas_headless.semantic_oracle import OracleFingerprint
    path = Path(__file__).resolve().parents[1] / 'artifacts/continuity-20261004/goal-scheduler-r117.json'
    if not path.exists():
        pytest.skip('retained live failure unavailable')
    frame = json.loads(path.read_text(encoding='utf-8-sig'))['tasks'][0]['failure_leased_frame']
    backend = FakeBackend([])
    backend.snapshot, backend.buttons = frame['snapshot'], frame['buttons_snapshot']
    fp = OracleFingerprint(package=backend.snapshot['package'], component=backend.foreground,
        driver_revision=backend.snapshot['driver_revision'], expected_pid=backend.snapshot['pid'])
    oracle = _FrameBoundSemanticOracle(backend.request,backend.foreground_component,backend.tap,fp,
                                     frame_guard=lambda:None)
    with pytest.raises(SemanticInputBlocked) as rejected:
        oracle.click('main/more')
    assert rejected.value.generation == frame['generation'] == 2755
    assert rejected.value.blockers == ('bulletin',)
    assert backend.taps == []



def test_loading_raycast_loss_keeps_existing_main_readiness_wait():
    from alas_headless import AlasSemanticAdapter
    from unittest.mock import patch
    backend = FakeBackend([
        make_button('extend', 'root/NewMainMellowTheme(Clone)/frame/left/extend', 40, 230,
                    raycast_top=False),
        make_button('curtain', 'root/UIOverlay/Loading(Clone)/curtain'),
    ])
    oracle = make_oracle(backend)
    # This test exercises action readiness; the page identity was already read.
    oracle.main_page_visible = lambda: True
    with pytest.raises(SemanticGateClosed, match='semantic target is not actionable'):
        oracle.click('main/more')
    assert backend.taps == []
    def finish_loading(_):
        backend.snapshot['generation'] += 1
        backend.buttons['generation'] = backend.snapshot['generation']
        backend.buttons['buttons'] = [dict(backend.buttons['buttons'][0], raycast_top=True)]
        backend.buttons['button_count'] = 1
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.sleep', side_effect=finish_loading):
        receipt = host._click_main_ready('main/more')
    assert receipt.semantic_id == 'main/more'
    assert backend.taps == [(40, 230)]


def test_nonactionable_bulletin_with_foreign_modal_retains_both_blockers():
    backend = FakeBackend([
        make_button('extend', 'root/NewMainMellowTheme(Clone)/frame/left/extend', 40, 230,
                    raycast_top=False),
        make_button('close_btn', 'Overlay/UIMain/NewBulletinBoardUI(Clone)/bg/close_btn', 1204, 83),
        make_button('button', 'root/Msgbox(Clone)/window/button'),
    ])
    with pytest.raises(SemanticInputBlocked) as rejected:
        make_oracle(backend).click('main/more')
    # The existing generic Msgbox blocker is named tactical-continue.
    assert set(rejected.value.blockers) == {'bulletin', 'tactical-continue'}
    assert backend.taps == []
