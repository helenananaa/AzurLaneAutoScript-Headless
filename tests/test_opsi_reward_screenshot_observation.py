"""Native combat map-event discovery must use its ALAS screenshot frame."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.test_alas_config_branch_compatibility import method


@pytest.mark.parametrize('case', ['absent', 'present', 'unknown'])
def test_original_map_event_reward_probe_uses_screenshot_and_retains_fresh_action_boundary(case):
    adapter, live, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    frame = SimpleNamespace(award_info_page_visible=Mock(return_value=case == 'present'))
    if case == 'unknown':
        frame.award_info_page_visible.side_effect = SemanticGateClosed('unknown reward owner')
    adapter._frame_observation_oracle = lambda: frame
    live.award_info_page_visible = Mock(side_effect=AssertionError('live reward read bypassed screenshot'))
    session = AlasSemanticSession('replay', '506b76f698b5089aaa29c4e7908b48edb8532a44')
    session.open = lambda: adapter
    session.refresh_frame = Mock()
    # A positive discovery can vanish before input; the existing atomic close
    # handles that fresh observation without producing a receipt or a tap.
    adapter.try_click_operation_siren_reward_close = Mock(return_value=None)
    native = method('module/os_handler/map_event.py', 'MapEventHandler',
                    'handle_map_get_items', logger=Mock())
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=session),
                           is_in_map=Mock(return_value=True))
    if case == 'unknown':
        with pytest.raises(SemanticGateClosed, match='unknown reward owner'):
            native(host)
    else:
        assert native(host) is (case == 'present')
    live.award_info_page_visible.assert_not_called()
    if case == 'present':
        session.refresh_frame.assert_called_once()
        adapter.try_click_operation_siren_reward_close.assert_called_once()
    else:
        session.refresh_frame.assert_not_called()
        adapter.try_click_operation_siren_reward_close.assert_not_called()


def test_direct_reward_probe_without_screenshot_preserves_live_contract():
    adapter, live, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._frame_observation_oracle = None
    live.award_info_page_visible = Mock(return_value=True)
    assert adapter.operation_siren_reward_visible()
    live.award_info_page_visible.assert_called_once()
