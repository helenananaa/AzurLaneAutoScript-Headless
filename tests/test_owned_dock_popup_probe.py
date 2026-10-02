import time
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('owned, expired, generation, blocker', [
    (True, False, 11, None), (True, False, 11, 'loading'),
    (False, False, 11, None), (True, True, 11, None),
    (True, False, 10, None), (True, False, 11, 'msgbox'),
])
def test_partial_dock_popup_probe_yields_only_after_owned_entry(
        owned, expired, generation, blocker):
    oracle = FakeOracle()
    oracle.meta_character_menu_visible = lambda: False
    oracle.meta_character_sync_page_visible = lambda: False
    oracle.read_state = lambda: SimpleNamespace(generation=generation, buttons=[SimpleNamespace(
        active_in_hierarchy=True, active_and_enabled=True,
        path='OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button')])
    oracle._blocking_rules = lambda *_: ([] if blocker is None else [SimpleNamespace(blocker_id=blocker)])
    oracle._enhancement_dock_records = Mock(side_effect=SemanticGateClosed('partial Dock'))
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if owned:
        host._main_dock_transition_receipt = SimpleNamespace(generation=10)
    host._main_dock_transition_until = time.monotonic() + (-1 if expired else 12)
    if owned and not expired and generation > 10 and blocker in (None, 'loading'):
        assert host._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM') is False
    else:
        with pytest.raises(SemanticGateClosed):
            host._appear_priority('CAMPAIGN_WITHDRAW_CONFIRM')
    assert oracle.click_calls == []
