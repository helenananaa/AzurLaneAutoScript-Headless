"""A queued lesson prompt must yield the old Home edge to native popup handling."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticUnmapped, SemanticGateClosed
from tests.test_alas_config_branch_compatibility import method
from tests.test_frame_post_input_foreground import session_for_meta
from tests.test_game_tips_loading_presence import host


FIXTURE = 'tactical-continue-home-failure-20261029.json'


def install(backend, packets):
    generation = max(p['generation'] for p in
                     (backend.snapshot, backend.buttons, backend.ui)) + 1
    for name, value in packets.items():
        previous = getattr(backend, name)
        packet = deepcopy(value)
        packet.update({key: previous[key] for key in ('package', 'pid', 'driver_revision')})
        packet['generation'] = generation
        setattr(backend, name, packet)


def uncover(packets):
    value = deepcopy(packets)
    for name, records in [('buttons', 'buttons'), ('ui', 'texts'), ('ui', 'images')]:
        packet = value[name]
        packet[records] = [item for item in packet[records]
                           if '/Msgbox(Clone)/' not in item['path']]
        packet[{'buttons': 'button_count', 'texts': 'text_count',
                'images': 'image_count'}[records]] = len(packet[records])
    for button in value['buttons']['buttons']:
        if button['name'] == 'btnBack':
            button['raycast_top'] = True
    return value


@pytest.mark.parametrize('drift', [False, True])
def test_actual_session_yields_late_home_then_original_ui_and_info_handler_own_cancel(drift):
    backend, session, _ = session_for_meta(FIXTURE)
    if drift:
        backend.buttons['buttons'].reverse()
        backend.buttons['new_optional_metadata'] = {'additive': True}
    prompt = {name: deepcopy(getattr(backend, name)) for name in ('snapshot', 'buttons', 'ui')}
    source = uncover(prompt)
    install(backend, source)
    session.refresh_frame()
    assert session.appear('TACTICAL_CHECK') is True
    home = SimpleNamespace(name='GOTO_MAIN', clear_offset=Mock())
    confirm = SimpleNamespace(name='POPUP_CONFIRM')
    cancel = SimpleNamespace(name='POPUP_CANCEL')
    white = SimpleNamespace(name='POPUP_CONFIRM_WHITE')
    destination = object()
    page = SimpleNamespace(parent=destination, check_button=SimpleNamespace(name='TACTICAL_CHECK'),
                           links={destination: home})
    mounted, receipts, checks = [], [], []
    def appear(button, **_):
        result = session.appear(button.name)
        if button.name == 'TACTICAL_CHECK' and result and not mounted:
            # Native source classification succeeds, then Unity queues its
            # completed-lesson modal before Session acquires the input frame.
            install(backend, prompt)
            mounted.append(True)
        return result
    def click(button):
        receipt = session.click(button.name)
        receipts.append(None if receipt is None else receipt.semantic_id)
        if receipt is None:
            assert not backend.taps
            assert not session.open().oracle.main_page_visible()
        return receipt
    main = json.loads((Path(__file__).parent / 'fixtures/guild-notice-expired-main-r386.json').read_bytes())
    def tapped():
        install(backend, source if len(backend.taps) == 1 else main)
    backend.on_tap = tapped
    def reached(**_):
        value = session.open()._require_frame_observation_oracle().main_page_visible()
        checks.append(value)
        return value
    handler = method('module/handler/info_handler.py', 'InfoHandler', 'handle_popup_confirm',
                     POPUP_CANCEL=cancel, POPUP_CONFIRM=confirm, POPUP_CONFIRM_WHITE=white)
    runner = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session,
        screenshot=session.refresh_frame, click=click), _popup_offset=(30, 30),
        interval_clear=Mock(), ui_button_interval_reset=Mock(),
        _check_semantic_client_version=Mock(), _handle_semantic_orphan_result=lambda: False,
        ui_page_appear=reached, appear=appear)
    runner.handle_popup_confirm = lambda name: handler(runner, name)
    runner.ui_page_os_popups = lambda: False
    additional = method('module/ui/ui.py', 'UI', 'ui_additional')
    runner.ui_additional = lambda **kwargs: additional(runner, **kwargs)
    native = method('module/ui/ui.py', 'UI', 'ui_goto', GOTO_MAIN=home, logger=Mock(),
                    Page=SimpleNamespace(init_connection=Mock(), iter_check_buttons=lambda: [],
                                         iter_pages=lambda: [page], clear_connection=Mock()))
    try:
        native(runner, destination)
        assert receipts == [None, 'tactical/continue/cancel', 'tactical/page/back']
        assert len(backend.taps) == 2 and checks == [False, False, False, True]
        assert session.action_ledger.remaining('tactical.reward') == 0
        assert session.action_ledger.remaining('tactical.assign') == 0
    finally:
        session.close()


@pytest.mark.parametrize('fault', ['other_text', 'duplicate_cancel', 'covered', 'stale'])
def test_unknown_or_unsafe_late_modal_does_not_gain_home_input(fault):
    backend, oracle, adapter = host(fixture=FIXTURE)
    if fault == 'other_text':
        next(t for t in backend.ui['texts'] if t['path'].endswith('/window/msg_panel/content'))['text'] = '是否购买资源？'
    elif fault == 'duplicate_cancel':
        backend.buttons['buttons'].append(deepcopy(next(b for b in backend.buttons['buttons']
            if b['path'].endswith('/custom_button_2(Clone)'))))
        backend.buttons['button_count'] += 1
    elif fault == 'covered':
        next(b for b in backend.buttons['buttons'] if b['path'].endswith('/custom_button_2(Clone)'))['raycast_top'] = False
    else:
        backend.snapshot['age_ms'] = backend.buttons['age_ms'] = 1000000
    with pytest.raises((AlasSemanticUnmapped, SemanticGateClosed)):
        adapter.click('GOTO_MAIN')
    assert not backend.taps
