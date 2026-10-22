from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from alas_headless import SemanticGateClosed
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport


@pytest.mark.parametrize('name', ['BUILD_QUEUE_EMPTY', 'BUILD_FINISH_ORDERS', 'POPUP_CONFIRM', 'POPUP_CANCEL'])
def test_dock_modal_precedes_queue_read_in_original_gacha_loop(name):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_build()
    oracle.campaign_dock_full_visible = Mock(return_value=True)
    oracle.build_queue_empty = Mock(side_effect=AssertionError('covered queue'))
    assert adapter._appear_build(name) is False
    assert adapter.dock_full_recovery_owned()
    oracle.campaign_dock_full_visible.assert_called_once_with('')
    oracle.build_queue_empty.assert_not_called()
    adapter.end_build()
    assert not adapter.dock_full_recovery_owned()


def test_unknown_dock_modal_does_not_become_safe_queue_absence():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_build()
    oracle.campaign_dock_full_visible = Mock(side_effect=SemanticGateClosed('ambiguous choices'))
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        adapter._appear_build('BUILD_QUEUE_EMPTY')
    assert oracle.click_calls == []


def test_inherited_selected_queue_loading_needs_no_new_navigation_receipt():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter.begin_build()
    oracle._blocking_rules = Mock(return_value=[SimpleNamespace(blocker_id='loading')])
    oracle.campaign_dock_full_visible = Mock(side_effect=AssertionError('covered modal'))
    oracle.build_queue_empty = Mock(side_effect=AssertionError('covered queue'))
    assert adapter._build_context.queue_entry_receipt is None
    assert adapter._appear_build('BUILD_QUEUE_EMPTY') is False
    assert adapter._appear_build('BUILD_FINISH_ORDERS') is False
    assert oracle.click_calls == []
