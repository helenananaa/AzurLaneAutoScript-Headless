"""Academy shop admission and dispatch share one immutable fresh input frame."""
from unittest.mock import Mock
import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from alas_headless.adapter.frame import _FrameBoundSemanticOracle
from tests.test_academy_page_probe_isolation import fixture
from tests.semantic_support.observer_fixtures import make_button


@pytest.mark.parametrize('drift', [False, True])
def test_academy_munitions_does_not_split_final_input_across_live_reads(drift):
    backend, live, adapter = fixture()
    if drift:
        backend.buttons['buttons'].reverse()
        backend.ui['optional_metadata'] = {'compatible': True}
    frame = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        live._tap, live.fingerprint, frame_guard=lambda: None,
        input_dispatch_counter=lambda: live.input_dispatch_count)
    def fresh():
        backend.requests.clear()
        return frame
    adapter._fresh_input_oracle = Mock(side_effect=fresh)
    live.click = Mock(side_effect=AssertionError('split live input'))
    receipt = adapter.click('ACADEMY_GOTO_MUNITIONS')
    assert receipt.semantic_id == 'academy/munitions'
    assert len(backend.taps) == 1
    assert backend.requests == ['GET /v1/state\n', 'GET /v1/ui\n']
    adapter._fresh_input_oracle.assert_called_once()
    live.click.assert_not_called()


@pytest.mark.parametrize('case', ['stale-lease', 'foreign-modal', 'ambiguous-entry'])
def test_fresh_academy_entry_keeps_existing_refusals(case):
    backend, live, adapter = fixture()
    if case == 'foreign-modal':
        backend.buttons['buttons'].append(make_button('custom_button_1(Clone)',
            'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
        backend.buttons['button_count'] += 1
    elif case == 'ambiguous-entry':
        target = next(b for b in backend.buttons['buttons'] if b['name'] == 'supplyShop')
        backend.buttons['buttons'].append(dict(target))
        backend.buttons['button_count'] += 1
    frame = _FrameBoundSemanticOracle(backend.request, backend.foreground_component,
        live._tap, live.fingerprint, frame_guard=lambda: None)
    adapter._fresh_input_oracle = Mock(return_value=frame)
    if case == 'stale-lease':
        adapter._fresh_input_oracle.side_effect = StaleFrameError()
    with pytest.raises((SemanticGateClosed, StaleFrameError)):
        adapter.click('ACADEMY_GOTO_MUNITIONS')
    assert not backend.taps
