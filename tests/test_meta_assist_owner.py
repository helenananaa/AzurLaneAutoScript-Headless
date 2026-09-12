import pytest
from alas_headless import AlasSemanticAdapter, AlasSemanticSession, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


def test_assist_counter_retries_only_incoherent_observation():
    oracle = FakeOracle()
    calls = []
    def read():
        calls.append(1)
        if len(calls) == 1:
            raise SemanticGateClosed('META assist snapshots are not coherent')
        return 'coherent-state'
    oracle.meta_assist_state = read
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    assert adapter.meta_assist_state() == 'coherent-state'
    assert len(calls) == 2
    def malformed():
        raise SemanticGateClosed('META selected assist candidate is ambiguous')
    oracle.meta_assist_state = malformed
    with pytest.raises(SemanticGateClosed, match='ambiguous'):
        adapter.meta_assist_state()
    assert oracle.click_calls == []


def test_assist_start_consumes_once_and_pending_transition_never_reclicks():
    oracle = FakeOracle()
    calls = []
    oracle.meta_precombat_fleet_ready = lambda: True
    oracle.click_daily_precombat_start = lambda: (calls.append('start') or oracle.click_receipt('daily/precombat/start'))
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None, meta_assist_budget=1)
    adapter.begin_meta_assist()
    receipt = adapter.click_meta_precombat_start()
    assert adapter._action_ledger.remaining('meta.assist') == 0
    assert adapter.click_meta_precombat_start() is receipt
    assert calls == ['start']
    oracle.observation_prompt_kind = lambda: 'meta-sortie'
    oracle.meta_assist_sortie_prompt_visible = lambda: True
    oracle.click_meta_assist_sortie = lambda confirm: (calls.append('confirm') or oracle.click_receipt('meta/assist/sortie/confirm'))
    adapter._click_confirmation('POPUP_CONFIRM')
    assert calls == ['start', 'confirm']
    assert adapter._action_ledger.remaining('meta.assist') == 0
    adapter._meta_precombat_start_until = 0
    with pytest.raises(SemanticGateClosed, match='remaining sortie budget'):
        adapter.click_meta_precombat_start()
    adapter.end_meta_assist()
    assert adapter._meta_precombat_start_receipt is None


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
