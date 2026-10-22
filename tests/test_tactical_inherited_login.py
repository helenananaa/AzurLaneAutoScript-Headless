import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_buttons, make_oracle
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport

LOGIN = 'UICamera/Canvas/UIMain/LoginUI2(Clone)'


def adapter_for_login():
    backend = FakeBackend([make_button('LoginUI2(Clone)', LOGIN)])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None, allow_tactical_rewards=True,
                                  frame_identity_provider=AlasSemanticAdapterTestsSupport.frame_identity)
    adapter._frame_observation_oracle = lambda: adapter._live_oracle
    adapter.begin_tactical()
    return backend, adapter


def test_original_ui_additional_can_observe_and_click_inherited_login_without_nested_flow():
    backend, adapter = adapter_for_login()
    assert not adapter._login_flow.active
    assert adapter.appear('LOGIN_CHECK')
    assert backend.taps == []
    receipt = adapter.click('LOGIN_CHECK')
    assert receipt.semantic_id == 'login/enter'
    assert backend.taps == [(640, 360)]
    assert not adapter._login_flow.active
    assert adapter._commission_context.flow_kind == 'tactical'
    assert adapter._commission_context.tactical_reward_receipt is None
    assert adapter._action_ledger.allowed('tactical.reward')


@pytest.mark.parametrize('case', ['covered', 'foreign', 'stale', 'duplicate'])
def test_inherited_login_keeps_original_input_boundary(case):
    backend, adapter = adapter_for_login()
    if case == 'covered': backend.buttons['buttons'][0]['raycast_top'] = False
    elif case == 'foreign': backend.snapshot['package'] = 'unrelated.package'
    elif case == 'stale': backend.snapshot['age_ms'] = 100000
    elif case == 'duplicate':
        backend.buttons['buttons'].append(dict(backend.buttons['buttons'][0]))
        backend.buttons['button_count'] = 2
    with pytest.raises(SemanticGateClosed): adapter.click('LOGIN_CHECK')
    assert backend.taps == []


def test_login_probe_absent_keeps_unrelated_tactical_observation_usable():
    backend, adapter = adapter_for_login()
    backend.buttons = make_buttons([])
    assert not adapter.appear('LOGIN_CHECK')
    assert not adapter.appear('REWARD_2')
    assert backend.taps == []
