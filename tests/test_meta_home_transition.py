from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('change', [None, 'no_receipt', 'old_generation', 'home_present', 'unknown_main'])
def test_old_meta_home_edge_needs_own_receipt_and_fresh_destination(change):
    oracle = FakeOracle()
    oracle.award_info_page_visible = lambda: False
    oracle.observation_target_present = lambda target: target == 'meta/home' and change == 'home_present'
    oracle.main_page_visible = lambda: change != 'unknown_main'
    oracle.read_state = lambda: SimpleNamespace(generation=10 if change == 'old_generation' else 11)
    oracle.click_meta_home = Mock(side_effect=SemanticGateClosed('source is absent'))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._goto_main_target = lambda: 'meta/home'  # ALAS' immutable old frame.
    previous = SimpleNamespace(generation=10, semantic_id='meta/home')
    if change != 'no_receipt': adapter._meta_home_receipt = previous
    if change is None:
        assert adapter.click(SimpleNamespace(name='GOTO_MAIN')) is previous
        oracle.click_meta_home.assert_not_called()
        assert adapter._meta_home_receipt is None
    else:
        with pytest.raises(SemanticGateClosed, match='source is absent'):
            adapter.click(SimpleNamespace(name='GOTO_MAIN'))
        oracle.click_meta_home.assert_called_once()


def test_real_meta_home_return_is_recorded_and_cleared_with_task_state():
    oracle = FakeOracle()
    oracle.award_info_page_visible = lambda: False
    receipt = SimpleNamespace(generation=10, semantic_id='meta/home')
    oracle.click_meta_home = Mock(return_value=receipt)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter._goto_main_target = lambda: 'meta/home'
    assert adapter.click(SimpleNamespace(name='GOTO_MAIN')) is receipt
    assert adapter._meta_home_receipt is receipt
    adapter.reset_task_state()
    assert adapter._meta_home_receipt is None


@pytest.mark.parametrize('name', ['GOTO_MAIN_WHITE', 'RPG_HOME'])
def test_owned_meta_landing_hides_other_home_aliases(name):
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'meta/current/open'
    oracle.meta_page_visible = lambda: True
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert adapter.appear(SimpleNamespace(name=name)) is False
    assert oracle.click_calls == []
