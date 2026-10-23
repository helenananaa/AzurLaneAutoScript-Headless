"""Typed oil rejection reaches native ALAS instead of another finish input."""
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from tests.test_game_tips_loading_presence import host
from tests.test_alas_config_branch_compatibility import method


def retained(drift=False):
    backend, oracle, adapter = host(drift, 'commission-oil-maxed-r182.json')
    # Retain the original immutable pair; no repeated old transport responses.
    state, ui = oracle.read_state(), oracle.read_ui_state()
    oracle.read_state = lambda: state
    oracle.read_ui_state = lambda **_kwargs: ui
    adapter.begin_commission()
    return backend, oracle, adapter


@pytest.mark.parametrize('drift', [False, True])
def test_actual_client_oil_rejection_yields_to_native_oil_maxed_handler(drift):
    backend, oracle, adapter = retained(drift)
    assert oracle.commission_reward_oil_maxed()
    assert adapter.appear('OIL_MAXED') is True
    assert adapter.appear('REWARD_1') is False
    assert adapter.appear('REWARD_1_WHITE') is False
    before = adapter._action_ledger.remaining('commission.reward')
    with pytest.raises(AlasSemanticActionDeferred, match='client oil capacity'):
        adapter.click('REWARD_1')
    assert adapter._action_ledger.remaining('commission.reward') == before
    assert not backend.taps


def test_original_receive_loop_raises_original_oil_maxed_without_a_new_claim():
    backend, _, adapter = retained()
    class OilMaxed(Exception): pass
    stat = Mock()
    stat.new.return_value.__enter__ = Mock(return_value=None)
    stat.new.return_value.__exit__ = Mock(return_value=False)
    owner = SimpleNamespace(stat=stat, config=SimpleNamespace(DropRecord_CommissionRecord='none', SERVER='cn'),
        device=SimpleNamespace(screenshot=Mock()), ui_page_appear=lambda *a, **kw: False,
        interval_reset=Mock(), ui_main_appear_then_click=lambda *a, **kw: False,
        appear=lambda name, **kw: adapter.appear(name) if name == 'OIL_MAXED' else False,
        appear_then_click=lambda name, **kw: adapter.appear(name) if name in ('REWARD_1', 'REWARD_1_WHITE') else False)
    receive = method('module/commission/commission.py', 'RewardCommission', '_commission_receive',
        Timer=Mock(), OilMaxed=OilMaxed, page_commission='page_commission', page_reward='page_reward',
        EXP_INFO_S_REWARD='EXP', GET_ITEMS_1='AWARD1', GET_ITEMS_2='AWARD2', GET_ITEMS_3='AWARD3',
        REWARD_1='REWARD_1', REWARD_1_WHITE='REWARD_1_WHITE',
        REWARD_GOTO_COMMISSION='GO', REWARD_GOTO_COMMISSION_WHITE='GO_WHITE', OIL_MAXED='OIL_MAXED')
    with pytest.raises(OilMaxed): receive(owner)
    assert not backend.taps


@pytest.mark.parametrize('change', ['unrelated-message', 'missing-owner', 'foreign-package', 'incoherent', 'truncated'])
def test_unknown_tip_is_not_promoted_to_oil_recovery(change):
    backend, oracle, _ = host(fixture='commission-oil-maxed-r182.json')
    tip = next(t for t in backend.ui['texts'] if '/toolTip(Clone)/Text' in t['path'])
    if change == 'unrelated-message': tip['text'] = '其他通知'
    elif change == 'missing-owner':
        backend.buttons['buttons'] = [b for b in backend.buttons['buttons'] if not b['path'].endswith('/event/frame/finish_btn')]
        backend.buttons['button_count'] = len(backend.buttons['buttons'])
    elif change == 'foreign-package': backend.snapshot['package'] = 'unrelated.package'
    elif change == 'incoherent': backend.ui['generation'] += 10
    else: tip['flags'] |= 0x10
    if change in ('unrelated-message', 'missing-owner'):
        assert not oracle.commission_reward_oil_maxed()
    else:
        with pytest.raises(SemanticGateClosed): oracle.commission_reward_oil_maxed()
    assert not backend.taps
