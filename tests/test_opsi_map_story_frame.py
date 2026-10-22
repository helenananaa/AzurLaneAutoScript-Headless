from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('covered, transition, visible', [
    (True, False, False), (False, True, False), (False, False, True),
])
def test_map_visibility_uses_screenshot_owner_and_story_handoff(covered, transition, visible, monkeypatch):
    oracle = FakeOracle()
    oracle.operation_siren_state = Mock(return_value=SimpleNamespace())
    oracle.operation_siren_map_overlay_present = Mock(return_value=False)
    frame = SimpleNamespace(operation_siren_state=Mock(return_value=SimpleNamespace()),
                            operation_siren_map_overlay_present=Mock(return_value=covered))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._frame_or_live_observation_oracle = lambda: frame
    adapter._event_story_transition_until = 101 if transition else 99
    monkeypatch.setattr('alas_headless.adapter.semantic.opsi.time.monotonic', lambda: 100)
    assert adapter.operation_siren_map_visible() is visible
    frame.operation_siren_state.assert_called_once()
    oracle.operation_siren_state.assert_not_called()
    oracle.operation_siren_map_overlay_present.assert_not_called()
    assert oracle.click_calls == []
