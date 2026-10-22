from unittest.mock import patch
import pytest
from alas_headless import AlasSemanticUnmapped
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


def test_owned_build_back_waits_only_for_passive_reward_probes():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    adapter._goto_main_target = lambda: 'build/page/back'
    with patch('alas_headless.adapter.semantic.dispatch_actions.time.monotonic', return_value=10):
        receipt = adapter._click_main('GOTO_MAIN', None)
        assert receipt.semantic_id == 'build/page/back'
        assert adapter.appear(NamedButton('GET_SHIP')) is False
        assert adapter.appear(NamedButton('GET_ITEMS_1')) is False
    assert oracle.click_calls == ['build/page/back']
    with patch('alas_headless.adapter.semantic.dispatch_observation.time.monotonic', return_value=23):
        with pytest.raises(AlasSemanticUnmapped):
            adapter.appear(NamedButton('GET_SHIP'))
    assert oracle.click_calls == ['build/page/back']
