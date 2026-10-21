"""A transient old publication is an observation wait, independently of task."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from alas_headless.oracle.errors import SemanticSnapshotStale
from tests.test_adapter_session_runtime_handle import FakeRuntimeHandle, REVISION


@pytest.mark.parametrize('case', ['fresh-after-gap', 'never-fresh', 'foreign'])
def test_screenshot_waits_for_fresh_publication_without_task_specific_owner(case):
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=FakeRuntimeHandle())
    session.adapter = SimpleNamespace(
        _login_flow=SimpleNamespace(snapshot=lambda: SimpleNamespace(active=False, passive_transition_until=0)),
        oracle=SimpleNamespace(stale_login_update_in_progress=lambda: False),
        _campaign_context=None, _operation_siren_entry_transition_until=0,
        _operation_siren_auto_search_transition_until=0)
    clock = [0.0]
    frame = Mock(generation=12, frame_id='fresh-publication')
    error = (SemanticGateClosed('observer package mismatch') if case == 'foreign'
             else SemanticSnapshotStale(19068, 10000))
    acquire = Mock(side_effect=[error]*121+[frame] if case == 'fresh-after-gap' else error)
    session._frame_clock = SimpleNamespace(current_frame_id='old', acquire=acquire)
    with patch('alas_headless.alas_adapter.time.monotonic', lambda: clock[0]), \
            patch('alas_headless.alas_adapter.time.sleep', lambda seconds: clock.__setitem__(0, clock[0]+seconds)):
        if case == 'fresh-after-gap':
            assert session.refresh_frame() is frame
            assert acquire.call_count == 122
            assert 18 <= clock[0] < 19
        else:
            with pytest.raises(SemanticGateClosed):
                session.refresh_frame()
            if case == 'foreign':
                assert acquire.call_count == 1
            else:
                assert 30 <= clock[0] < 30.2
