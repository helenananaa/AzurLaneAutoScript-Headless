"""Native page enumeration probes Dock while leaving the reviewed sign page."""
import pytest
from tests.test_game_tips_loading_presence import host


@pytest.mark.parametrize('drift', [False, True])
def test_actual_sign_return_proves_passive_dock_absence(drift):
    b, o, a = host(drift, 'month-sign-return-r138.json')
    # This page identity uses only the actual frozen snapshot/buttons.
    assert o.read_state().generation == 16920
    assert o.enabled('event-list/page/back')
    assert a.appear('DOCK_CHECK') is False
    assert b.taps == []
