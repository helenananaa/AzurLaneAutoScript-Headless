from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)


def dock_records():
    root = 'OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/'
    backend = FakeBackend([make_button('index_button', root + 'index_button')])
    backend.ui = make_ui([
        make_text('884/930', root + 'capacity/Text'),
        make_text('船坞容量:', root + 'capacity/label'),
    ], images=[make_image(root + 'index_button', 'shaixuan_off',
                         {'left': 620, 'top': 340, 'right': 660, 'bottom': 380})])
    oracle = make_oracle(backend)
    complete = oracle._retirement_records()
    backend.ui = make_ui(backend.ui['texts'])
    incomplete = make_oracle(backend)._retirement_records()
    return backend, oracle, complete, incomplete


def test_immutable_partial_dock_reads_once_and_keeps_input_closed():
    backend, oracle, complete, incomplete = dock_records()
    frame = _FrameBoundSemanticOracle(
        backend.request, backend.foreground_component, backend.tap,
        oracle.fingerprint, frame_guard=lambda: None, sleep=Mock(),
    )
    frame._retirement_records = Mock(side_effect=[incomplete, complete])
    with pytest.raises(SemanticGateClosed, match='identity is incomplete'):
        frame._enhancement_dock_records()
    assert frame._retirement_records.call_count == 1
    frame._sleep.assert_not_called()
    assert backend.taps == []


def test_live_dock_can_settle_without_relaxing_identity():
    backend, oracle, complete, incomplete = dock_records()
    oracle._retirement_records = Mock(side_effect=[incomplete, complete])
    assert oracle._enhancement_dock_records() == complete
    assert oracle._retirement_records.call_count == 2
    assert backend.taps == []


def test_live_dock_missing_sprite_remains_rejected_after_bounded_reads():
    backend, oracle, complete, incomplete = dock_records()
    oracle._retirement_records = Mock(return_value=incomplete)
    with pytest.raises(SemanticGateClosed, match='identity is incomplete'):
        oracle._enhancement_dock_records()
    assert oracle._retirement_records.call_count == 8
    assert backend.taps == []
