from types import SimpleNamespace
from unittest.mock import Mock
import time
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('confirm', [True, False])
def test_build_navigation_delegates_owned_os_exit(confirm):
    oracle = FakeOracle()
    oracle.observation_prompt_kind_value = 'opsi-exit'
    oracle.operation_siren_exit_prompt_visible = lambda: True
    oracle.build_queue_finish_prompt_cost = Mock(side_effect=SemanticGateClosed('foreign prompt'))
    prior = SimpleNamespace(semantic_id='os/exit/confirm', generation=10)
    oracle.click_operation_siren_exit = Mock(return_value=prior)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_build()
    name = 'POPUP_CONFIRM' if confirm else 'POPUP_CANCEL'
    assert adapter._appear_build(name) is UNHANDLED
    assert adapter._click_build(name) is UNHANDLED
    assert adapter._click_confirmation(name) is prior
    oracle.click_operation_siren_exit.assert_called_once_with(confirm=confirm)
    oracle.build_queue_finish_prompt_cost.assert_not_called()
    assert adapter._build_context.submit_receipt is None


@pytest.mark.parametrize('kind, visible', [('opsi-exit', False), (None, True), ('build-finish', True)])
def test_unproven_foreign_prompt_keeps_construction_guard(kind, visible):
    oracle = FakeOracle()
    oracle.observation_prompt_kind_value = kind
    oracle.operation_siren_exit_prompt_visible = lambda: visible
    oracle.build_queue_finish_prompt_cost = Mock(side_effect=SemanticGateClosed('not actionable'))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_build()
    with pytest.raises(SemanticGateClosed, match='not actionable'):
        adapter._click_build('POPUP_CONFIRM')
    assert oracle.click_calls == []


def test_build_repeated_os_exit_uses_fresh_destination_and_existing_receipt():
    oracle = FakeOracle()
    oracle.main_page_visible = lambda: True
    oracle.observation_surface_present = lambda _: False
    oracle.read_state = lambda: SimpleNamespace(generation=11)
    oracle.build_queue_finish_prompt_cost = Mock(side_effect=AssertionError('wrong owner'))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    adapter.begin_build()
    prior = SimpleNamespace(generation=10, semantic_id='os/exit/confirm')
    adapter._operation_siren_exit_receipt = prior
    adapter._operation_siren_entry_transition_until = time.monotonic() + 20
    assert adapter.click(SimpleNamespace(name='POPUP_CONFIRM')) is prior
    assert oracle.click_calls == []
    oracle.build_queue_finish_prompt_cost.assert_not_called()
