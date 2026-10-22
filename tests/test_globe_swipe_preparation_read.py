from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.test_semantic_oracle_opsi_port_geometry import fixture


def prepare(adapter):
    return adapter.begin_operation_siren_globe_swipe_vector(
        (-300, -300), box=(20, 220, 980, 620), random_range=(0, 0, 0, 0),
        padding=15, duration=(0.1, 0.2), whitelist_area=None,
        blacklist_area=None, name='GLOBE_SWIPE_-300_-300', distance_check=True)


def test_transient_loading_read_can_settle_before_arming_without_input():
    backend, oracle = fixture()
    oracle._sleep = Mock()
    original = oracle._require_operation_siren_globe_visible
    oracle._require_operation_siren_globe_visible = Mock(side_effect=[
        SemanticGateClosed('globe is obscured: loading'), original()])
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    intent = prepare(adapter)
    assert intent.pixel_vector == (-300, -300)
    assert oracle._require_operation_siren_globe_visible.call_count == 2
    oracle._sleep.assert_called_once_with(.25)
    assert backend.swipes == backend.taps == []
    adapter.end_operation_siren_globe_swipe_vector(intent)


@pytest.mark.parametrize('error', [
    'game activity is not top-resumed', 'observer generation moved backwards',
    'button snapshot is truncated', 'globe is obscured: msgbox'])
def test_persistent_read_error_remains_classified_and_unarmed(error):
    backend, oracle = fixture()
    oracle._sleep = Mock()
    oracle.read_state = Mock(side_effect=SemanticGateClosed(error))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    with pytest.raises(SemanticGateClosed, match=error):
        prepare(adapter)
    assert oracle.read_state.call_count == 4
    assert adapter._operation_siren_globe_swipe_intent is None
    assert backend.swipes == backend.taps == []


def test_ready_baseline_arms_immediately_without_observation_wait_or_input():
    backend, oracle = fixture()
    oracle._sleep = Mock()
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    intent = prepare(adapter)
    oracle._sleep.assert_not_called()
    assert backend.swipes == backend.taps == []
    adapter.end_operation_siren_globe_swipe_vector(intent)
