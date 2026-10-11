from types import SimpleNamespace
from contextlib import nullcontext
from unittest.mock import Mock

import pytest

from alas_headless.adapter.semantic.session_opsi import SessionOpsiPorts
from alas_headless.oracle.errors import SemanticGateClosed


@pytest.mark.parametrize('panel,local,globe,allowed', [
    (False, False, True, True),  # A ready globe need not have a selected pin.
    (False, True, False, True),
    (True, False, True, False),
    (False, False, False, False),  # Unknown/covered return surface stays closed.
])
def test_action_point_close_requires_panel_absence_and_known_return(
    monkeypatch, panel, local, globe, allowed
):
    monkeypatch.setattr('alas_headless.adapter.semantic.session_opsi.time.sleep', lambda _: None)
    receipt = object()
    oracle = SimpleNamespace(
        operation_siren_local_map_visible=Mock(return_value=local),
        operation_siren_globe_visible=Mock(return_value=globe),
    )
    adapter = SimpleNamespace(
        oracle=oracle,
        click_operation_siren_action_point_control=Mock(return_value=receipt),
        operation_siren_action_point_visible=Mock(return_value=panel),
        prepared_input_frame=lambda provider:nullcontext(),
        _require_frame_observation_oracle=lambda:oracle,
    )
    session = SimpleNamespace(refresh_frame=Mock(), open=lambda: adapter)
    if allowed:
        assert SessionOpsiPorts.click_operation_siren_action_point_control(session, False) is receipt
    else:
        with pytest.raises(SemanticGateClosed, match='panel did not close'):
            SessionOpsiPorts.click_operation_siren_action_point_control(session, False)
    adapter.click_operation_siren_action_point_control.assert_called_once_with(False)
