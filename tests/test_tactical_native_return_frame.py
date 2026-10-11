from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('semantic,pending,ready', [(False, False, False), (True, True, True), (True, False, False), (True, False, True)])
def test_native_tactical_return_waits_for_owned_navigation_and_uses_one_input_frame(monkeypatch, semantic, pending, ready):
    returned = method('module/tactical/tactical_class.py', 'RewardTacticalClass', '_return_from_tactical_page', BACK_ARROW='back')
    frame = Mock()
    frame.enabled.return_value = ready
    adapter = Mock(_commission_context=SimpleNamespace(tactical_empty_slot_receipt=object() if pending else None))
    adapter._fresh_input_oracle.return_value = frame
    session = SimpleNamespace(open=lambda: adapter) if semantic else None
    monkeypatch.setattr('alas_headless.current_semantic_session', lambda: session)
    device = Mock()
    host = SimpleNamespace(device=device)
    assert returned(host) is (semantic and not pending and ready)
    if not semantic:
        device.click.assert_called_once_with('back')
        adapter._fresh_input_oracle.assert_not_called()
    elif pending:
        adapter._fresh_input_oracle.assert_not_called()
        frame.click.assert_not_called()
    else:
        adapter._fresh_input_oracle.assert_called_once()
        frame.enabled.assert_called_once_with('tactical/page/back')
        if ready:
            frame.click.assert_called_once_with('tactical/page/back')
            adapter._record_mission_transition.assert_called_once_with(frame.click.return_value)
        else:
            frame.click.assert_not_called()
