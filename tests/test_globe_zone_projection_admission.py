"""Only pre-input projection refusal uses existing task-local input admission."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.oracle.errors import SemanticTargetNotActionable
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_ui, make_button, make_buttons


def projection():
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    record = dict(plane_hit=True, ui_clear=True, plane_instance_id=42,
                  input_point=[500, 400], path='WorldMap3D/entity/Plane/PointerInfo/GetMapScreenPos')
    oracle._operation_siren_globe_map_projection_record = Mock(return_value=(SimpleNamespace(generation=10), record))
    oracle._sleep = lambda _: None
    return backend, oracle, record


@pytest.mark.parametrize('damage', ['missing-point', 'no-plane', 'covered', 'malformed-point'])
def test_unactionable_projection_is_classified_before_any_input(damage):
    backend, oracle, record = projection()
    if damage == 'missing-point': record['input_point'] = None
    elif damage == 'no-plane': record['plane_hit'] = False
    elif damage == 'covered': record['ui_clear'] = False
    else: record['input_point'] = [True, 400]
    with pytest.raises(SemanticTargetNotActionable) as caught:
        oracle.click_operation_siren_globe_map_zone('zone', (1, 2))
    assert caught.value.semantic_id == 'os/globe/zone/select'
    assert 'native zone projection is not actionable' in str(caught.value.__cause__)
    assert not backend.taps and oracle.input_dispatch_count == 0


def test_valid_projection_still_requires_named_postcondition():
    backend, oracle, _ = projection()
    backend.on_tap = lambda: setattr(backend, 'ui', make_ui([], generation=11))
    oracle._operation_siren_globe_zone_name_from_ui = lambda _: 'zone'
    receipt = oracle.click_operation_siren_globe_map_zone('zone', (1, 2))
    assert receipt.semantic_id == 'os/globe/zone/select' and backend.taps == [(500, 400)]


def test_wrong_post_input_zone_remains_uncertain_failure():
    backend, oracle, _ = projection()
    backend.on_tap = lambda: setattr(backend, 'ui', make_ui([], generation=11))
    oracle._operation_siren_globe_zone_name_from_ui = lambda _: 'different zone'
    with pytest.raises(SemanticGateClosed) as caught:
        oracle.click_operation_siren_globe_map_zone('zone', (1, 2))
    assert not isinstance(caught.value, SemanticTargetNotActionable)
    assert backend.taps == [(500, 400)]


@pytest.mark.parametrize('clears', [True, False])
def test_known_loading_projection_reuses_existing_bounded_read_window(clears):
    backend, oracle, record = projection()
    ready = dict(record)
    loading = dict(record, ui_clear=False, input_point=None,
                   ui_top_path='OverlayCamera/Overlay/UIOverlay/Loading(Clone)/bg')
    calls = []
    def read(_, **kwargs):
        assert kwargs == {'check_foreground_on_return': False}
        calls.append(True)
        waiting = len(calls) == 1 or not clears
        backend.buttons = make_buttons([make_button('Loading(Clone)',
            'OverlayCamera/Overlay/UIOverlay/Loading(Clone)')] if waiting else [])
        return SimpleNamespace(generation=10), loading if waiting else ready
    oracle._operation_siren_globe_map_projection_record = read
    backend.on_tap = lambda: setattr(backend, 'ui', make_ui([], generation=11))
    oracle._operation_siren_globe_zone_name_from_ui = lambda _: 'zone'
    if clears:
        oracle.click_operation_siren_globe_map_zone('zone', (1, 2))
        assert len(calls) == 2 and backend.taps == [(500, 400)]
    else:
        with pytest.raises(SemanticTargetNotActionable):
            oracle.click_operation_siren_globe_map_zone('zone', (1, 2))
        assert len(calls) == 4 and not backend.taps


def test_unknown_projection_obscurer_is_not_retried_as_loading():
    backend, oracle, record = projection()
    record.update(ui_clear=False, input_point=None, ui_top_path='UnknownOverlay/Loading(Clone)')
    with pytest.raises(SemanticTargetNotActionable):
        oracle.click_operation_siren_globe_map_zone('zone', (1, 2))
    assert oracle._operation_siren_globe_map_projection_record.call_count == 1
    assert not backend.taps
