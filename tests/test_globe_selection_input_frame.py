from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from tests.test_adapter_frame import make_clock


@pytest.mark.parametrize('invalidated', [False, True])
def test_globe_selection_reacquires_expired_or_invalidated_input_lease(invalidated):
    handle, monotonic, clock = make_clock()
    first = clock.acquire()
    if invalidated:
        clock.invalidate(first.identity.frame_id)
    else:
        monotonic.value += 10_000_000_000
    with pytest.raises(StaleFrameError):
        clock.borrow(require_fresh=True)
    # New frame acquisition must also observe an advancing generation.
    handle.snapshot['generation'] += 1
    handle.buttons['generation'] += 1
    handle.ui['generation'] += 1
    def select(name, position):
        clock.borrow(require_fresh=True)
        handle.tap(500, 400)
        return name, position
    adapter = SimpleNamespace(click_operation_siren_globe_map_zone=select)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    session.refresh_frame = clock.acquire
    assert session.click_operation_siren_globe_map_zone('zone85', (1, 2)) == ('zone85', (1, 2))
    assert handle.taps == [(500, 400)]


@pytest.mark.parametrize('failure', ['game activity is not top-resumed', 'observer endpoints are not generation-coherent'])
def test_failed_new_frame_cannot_reach_zone_input(failure):
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    select = Mock()
    session.open = lambda: SimpleNamespace(click_operation_siren_globe_map_zone=select)
    session.refresh_frame = Mock(side_effect=SemanticGateClosed(failure))
    with pytest.raises(SemanticGateClosed, match=failure):
        session.click_operation_siren_globe_map_zone('zone85', (1, 2))
    select.assert_not_called()
