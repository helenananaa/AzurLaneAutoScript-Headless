"""ALAS' skipped first screenshot still needs a frame after input invalidation."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from tests.semantic_support.adapter_fixtures import NamedButton


def fixture():
    adapter = SimpleNamespace(_login_flow=SimpleNamespace(active=False),
                              _mail_context=object(), appear=Mock(return_value=True))
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    session._frame_clock = Mock()
    session.refresh_frame = Mock()
    return session, adapter


def test_valid_screenshot_frame_stays_frozen_across_page_candidates():
    session, adapter = fixture()
    assert session.appear(NamedButton('MAIN_GOTO_CAMPAIGN_WHITE'))
    assert session.appear(NamedButton('REWARD_CHECK'))
    session.refresh_frame.assert_not_called()
    assert adapter.appear.call_count == 2


def test_invalidated_navigation_frame_is_captured_once_before_page_sweep():
    session, adapter = fixture()
    session._frame_clock.borrow.side_effect = [StaleFrameError(), object()]
    assert session.appear(NamedButton('MAIN_GOTO_CAMPAIGN_WHITE'))
    assert session.appear(NamedButton('REWARD_CHECK'))
    session.refresh_frame.assert_called_once_with()
    assert adapter.appear.call_count == 2


@pytest.mark.parametrize('failure', ['game activity is not top-resumed', 'Msgbox snapshots are not coherent'])
def test_failed_new_frame_never_falls_back_to_live_page_classification(failure):
    session, adapter = fixture()
    session._frame_clock.borrow.side_effect = StaleFrameError()
    session.refresh_frame.side_effect = SemanticGateClosed(failure)
    with pytest.raises(SemanticGateClosed, match=failure):
        session.appear(NamedButton('MAIN_GOTO_CAMPAIGN_WHITE'))
    adapter.appear.assert_not_called()
