import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


def test_assist_scope_does_not_grant_beacon_bypass_or_leak_combat_owner():
    oracle = FakeOracle()
    oracle.observation_prompt_kind = lambda: 'meta-sortie'
    oracle.meta_assist_sortie_prompt_visible = lambda: True
    calls = []
    oracle.click_meta_assist_sortie = lambda confirm: (calls.append(confirm) or oracle.click_receipt('meta/assist/sortie/confirm'))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None, meta_assist_budget=1)
    adapter.begin_meta_assist()
    assert not adapter.meta_beacon_active()
    assert adapter._operation_siren_allows_passive_probe()
    adapter._click_confirmation('POPUP_CONFIRM')
    assert adapter._action_ledger.remaining('meta.assist') == 0
    assert adapter._operation_siren_combat_active
    with pytest.raises(SemanticGateClosed):
        adapter._click_confirmation('POPUP_CONFIRM')
    assert calls == [True]
    adapter.end_meta_assist()
    assert not adapter._meta_assist_active
    assert not adapter._operation_siren_combat_active


def test_session_rebind_restores_assist_scope_and_enforces_budget_before_start():
    adapter = AlasSemanticAdapter(FakeOracle(), package_gate=lambda: None)
    session = AlasSemanticSession.__new__(AlasSemanticSession)
    session.open = lambda: adapter
    session.refresh_tactical_input_frame = lambda: None
    session._meta_assist_active = True
    with pytest.raises(SemanticGateClosed, match='remaining sortie budget'):
        session.click_daily_precombat_start()
    assert adapter._meta_assist_active
    assert adapter.oracle.click_calls == []
    adapter.reset_task_state()
    assert not adapter._meta_assist_active


def test_exhausted_assist_remains_observable_without_enabling_input():
    from tests.semantic_support.oracle_cases import OperationSirenSemanticOracleTestsSupport
    from tests.semantic_support.observer_fixtures import make_oracle
    backend = OperationSirenSemanticOracleTestsSupport._meta_assist_backend()
    backend.ui['texts'][0]['text'] = '0/3'
    backend.buttons['buttons'][0]['interactable'] = False
    oracle = make_oracle(backend)
    assert oracle.meta_assist_state().remaining_attempts == 0
    from types import SimpleNamespace
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert adapter.appear(SimpleNamespace(name='BEACON_MY'))
    with pytest.raises(SemanticGateClosed, match='exhausted'):
        oracle.click_meta_assist_start()
    assert backend.taps == []
