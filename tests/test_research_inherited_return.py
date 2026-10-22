from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('change', [None, 'no_receipt', 'source_present', 'unknown_destination', 'old_generation'])
def test_research_old_return_needs_own_receipt_and_fresh_destination(change):
    o = FakeOracle()
    o.award_info_page_visible = lambda: False
    o.observation_target_present = lambda target: target == 'research/page/back' and change == 'source_present'
    o.enabled = lambda target: target == 'research-menu/page/back' and change != 'unknown_destination'
    o.main_page_visible = lambda: False
    o.read_state = lambda: SimpleNamespace(generation=10 if change == 'old_generation' else 11)
    o.click = Mock(side_effect=SemanticGateClosed('source is absent'))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._goto_main_target = lambda: 'research/page/back'
    prior = SimpleNamespace(generation=10, semantic_id='research/page/back')
    if change != 'no_receipt': a._research_back_receipt = prior
    if change is None:
        assert a.click(SimpleNamespace(name='GOTO_MAIN')) is prior
        o.click.assert_not_called()
        assert a._research_back_receipt is None
    else:
        with pytest.raises(SemanticGateClosed, match='source is absent'):
            a.click(SimpleNamespace(name='GOTO_MAIN'))
        o.click.assert_called_once()


def test_research_return_receipt_is_recorded_and_reset():
    o = FakeOracle()
    o.award_info_page_visible = lambda: False
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a._goto_main_target = lambda: 'research/page/back'
    receipt = a.click(SimpleNamespace(name='GOTO_MAIN'))
    assert a._research_back_receipt is receipt
    a.reset_task_state()
    assert a._research_back_receipt is None


@pytest.mark.parametrize('confirm', [True, False])
def test_research_handoff_delegates_exact_os_exit_to_existing_port(confirm):
    o = FakeOracle()
    o.observation_prompt_kind_value = 'opsi-exit'
    o.operation_siren_exit_prompt_visible = lambda: True
    o.click_operation_siren_exit = Mock(return_value=SimpleNamespace(
        semantic_id='os/exit/confirm' if confirm else 'os/exit/cancel', generation=10))
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_research()
    if confirm:
        receipt = a.click(SimpleNamespace(name='POPUP_CONFIRM'))
    else:
        # The fake login flow lacks a leased frame for its cancellation probe.
        # Check delegation and the existing confirmation port directly.
        from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
        assert a._click_research('POPUP_CANCEL') is UNHANDLED
        receipt = a._click_confirmation('POPUP_CANCEL')
    assert receipt.semantic_id == ('os/exit/confirm' if confirm else 'os/exit/cancel')
    o.click_operation_siren_exit.assert_called_once_with(confirm=confirm)
    assert a._research_context.start_receipt is None


@pytest.mark.parametrize('kind, visible', [('opsi-exit', False), ('research-start', True),
                                          (None, True)])
def test_research_handoff_does_not_bypass_unproven_start(kind, visible):
    o = FakeOracle()
    o.observation_prompt_kind_value = kind
    o.operation_siren_exit_prompt_visible = lambda: visible
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_research()
    with pytest.raises(SemanticGateClosed, match='budgeted project'):
        a.click(SimpleNamespace(name='POPUP_CONFIRM'))
    assert o.click_calls == []


@pytest.mark.parametrize('name', ['GOTO_MAIN', 'GOTO_MAIN_WHITE', 'RPG_HOME'])
def test_retained_os_exit_hides_covered_home_probe(name):
    o = FakeOracle()
    o.observation_prompt_kind_value = 'opsi-exit'
    o.operation_siren_exit_prompt_visible = lambda: True
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_research()
    assert a._appear_priority(name) is False
    assert o.click_calls == []


def test_research_repeated_os_exit_confirmation_reuses_proven_receipt():
    import time
    o = FakeOracle()
    o.observation_prompt_kind_value = None
    o.main_page_visible = lambda: True
    o.observation_surface_present = lambda _: False
    o.read_state = lambda: SimpleNamespace(generation=11)
    a = AlasSemanticAdapter(o, package_gate=lambda: None)
    a.begin_research()
    prior = SimpleNamespace(generation=10, semantic_id='os/exit/confirm')
    a._operation_siren_exit_receipt = prior
    a._operation_siren_entry_transition_until = time.monotonic() + 20
    assert a.click(SimpleNamespace(name='POPUP_CONFIRM')) is prior
    assert a._operation_siren_exit_receipt is None
    assert o.click_calls == []
