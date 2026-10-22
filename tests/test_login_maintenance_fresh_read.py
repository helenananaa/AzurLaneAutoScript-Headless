from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle


def test_maintenance_probe_waits_for_a_fresh_complete_read_without_input():
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    fresh = oracle.read_state()
    oracle.read_state = Mock(side_effect=[SemanticGateClosed('observer snapshot is stale'), fresh])
    assert oracle.server_maintenance_visible() is False
    assert oracle.read_state.call_count == 2
    assert backend.taps == backend.swipes == []


def test_maintenance_probe_preserves_persistent_read_failure_without_input():
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    oracle.read_state = Mock(side_effect=SemanticGateClosed('observer snapshot is stale'))
    with pytest.raises(SemanticGateClosed, match='snapshot is stale'):
        oracle.server_maintenance_visible()
    assert oracle.read_state.call_count == 12
    assert backend.taps == backend.swipes == []
