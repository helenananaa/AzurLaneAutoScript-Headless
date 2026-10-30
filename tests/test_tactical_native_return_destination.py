"""An accepted classroom Back must not finish the native task before arrival."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_alas_config_branch_compatibility import method
from tests.test_frame_post_input_foreground import session_for_meta
from tests.test_tactical_late_continue_home import install


@pytest.mark.parametrize('fading', [False, True])
def test_native_receive_owns_next_screenshot_after_accepted_back(monkeypatch, fading):
    backend, session, _ = session_for_meta('tactical-return-fading-source-20261029.json')
    if fading:
        backend.buttons['buttons'].reverse()
        backend.ui['additive_metadata'] = {'compatible': True}
    source = {k: deepcopy(getattr(backend, k)) for k in ('snapshot', 'buttons', 'ui')}
    destination = json.loads((Path(__file__).parent / 'fixtures' /
        'tactical-return-reward-destination-20261029.json').read_bytes())
    screenshots = []
    def screenshot():
        screenshots.append(True)
        assert len(screenshots) <= 2
        value = deepcopy(source) if fading and len(screenshots) == 1 else destination
        if value is not destination:
            next(b for b in value['buttons']['buttons'] if b['name'] == 'btnBack')['raycast_top'] = False
        install(backend, value)
        session.refresh_frame()
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: session)
    resources = {name: name for name in (
        'TACTICAL_CHECK', 'TACTICAL_CLASS_START', 'REWARD_2', 'REWARD_2_WHITE',
        'REWARD_GOTO_TACTICAL', 'REWARD_GOTO_TACTICAL_WHITE', 'BOOK_EMPTY_POPUP',
        'MISSION_POPUP_GO', 'DOCK_CHECK', 'SKILL_CONFIRM', 'TACTICAL_META',
        'POPUP_CONFIRM', 'POPUP_CANCEL', 'GET_MISSION', 'ADD_NEW_STUDENT')}
    receive = method('module/tactical/tactical_class.py', 'RewardTacticalClass',
        'tactical_class_receive', Timer=lambda *a, **k: Mock(), page_reward=object(), **resources)
    back = method('module/tactical/tactical_class.py', 'RewardTacticalClass',
        '_return_from_tactical_page', BACK_ARROW='back')
    host = SimpleNamespace(config=SimpleNamespace(AddNewStudent_Enable=False),
        device=SimpleNamespace(screenshot=screenshot), _validate_tactical_config=Mock(),
        _tactical_get_finish=Mock(return_value=[1]), interval_clear=Mock(), interval_reset=Mock(),
        appear=lambda resource, **kwargs: resource == 'TACTICAL_CHECK' and not screenshots,
        appear_then_click=lambda *a, **k: False, handle_rapid_training=lambda: False,
        ui_main_appear_then_click=lambda *a, **k: False, handle_popup_confirm=lambda *a: False,
        handle_urgent_commission=lambda: False, ui_page_main_popups=lambda: False,
        handle_game_tips=lambda: False, _popup_offset=(30, 30))
    host._return_from_tactical_page = lambda: back(host)
    try:
        session.begin_tactical()
        session.refresh_frame()
        assert receive(host) is True
        assert len(screenshots) == (2 if fading else 1)
        assert len(backend.taps) == 1
        assert session.open()._require_frame_observation_oracle().observation_target_present('reward/page/back')
        assert not session.open()._require_frame_observation_oracle().observation_target_present('tactical/page/back')
        assert session.action_ledger.remaining('tactical.reward') == 0
        assert session.action_ledger.remaining('tactical.assign') == 0
    finally:
        session.close()
