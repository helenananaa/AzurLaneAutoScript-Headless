"""Native refocus resolves both inputs from the final immutable fresh frame."""

from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from alas_headless.adapter.semantic.opsi import OpsiAdapterPorts
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_ui,
)


def fixture(port):
    root = 'root/OverlayCamera/Overlay/UIMain/top/adapt/'
    if port == 'bar':
        target = make_button('fleet_bar', root + 'left_stage/other/fleet_bar')
        buttons = [make_button('back_button', root + 'top_stage/back_button'), target]
        images = [make_image(target['path'], 'btn_switch', target['adb_bounds'])]
    else:
        buttons = [make_button('item' if i == 0 else f'item ({i})',
                    root + 'left_stage/mask/list/' + ('item' if i == 0 else f'item ({i})'))
                   for i in range(4)]
        target = buttons[-1]
        images = []
    backend = FakeBackend(buttons)
    backend.ui = make_ui([], images=images)
    live = make_oracle(backend)
    ctx = OpsiAdapterPorts()
    ctx._package_gate = Mock()
    ctx.oracle = Mock()
    ctx.oracle.click_operation_siren_fleet_bar.side_effect = AssertionError('cached live input')
    ctx.oracle.click_operation_siren_fleet_selector.side_effect = AssertionError('cached live input')
    guard = Mock()
    frame = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        live._tap, live.fingerprint, frame_guard=guard,
        input_dispatch_counter=lambda: live.input_dispatch_count)
    ctx._fresh_input_oracle = Mock(return_value=frame)
    return backend, ctx, guard, target


def click(ctx, port):
    return ctx.click_operation_siren_fleet_bar() if port == 'bar' else ctx.click_operation_siren_fleet_selector(4)


@pytest.mark.parametrize('port', ['bar', 'selector'])
@pytest.mark.parametrize('drift', [False, True])
def test_refocus_uses_final_fresh_frame_with_compatible_metadata(port, drift):
    backend, ctx, _, target = fixture(port)
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['optional_metadata'] = {'compatible': True}
    receipt = click(ctx, port)
    assert receipt.path == target['path']
    assert len(backend.taps) == 1
    assert len(backend.requests) <= 2  # Repeated reads share one immutable frame.
    ctx._fresh_input_oracle.assert_called_once()
    ctx._package_gate.assert_called_once()
    ctx.oracle.click_operation_siren_fleet_bar.assert_not_called()
    ctx.oracle.click_operation_siren_fleet_selector.assert_not_called()


@pytest.mark.parametrize('port', ['bar', 'selector'])
@pytest.mark.parametrize('case', ['stale', 'ambiguous', 'foreign'])
def test_refocus_keeps_final_freshness_identity_and_uniqueness_refusals(port, case):
    backend, ctx, guard, target = fixture(port)
    if case == 'stale':
        guard.side_effect = StaleFrameError()
    elif case == 'ambiguous':
        backend.buttons['buttons'].append(dict(target))
        backend.buttons['button_count'] += 1
    else:
        backend.foreground = 'other.package/other.Activity'
    with pytest.raises((SemanticGateClosed, StaleFrameError)):
        click(ctx, port)
    assert not backend.taps
