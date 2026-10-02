from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle, make_text, make_ui

ROOT = 'UICamera/Canvas/UIMain/GameHallUI(Clone)/ad/'

def fixture(amount=26, blocked=False, duplicate=False):
    free = make_button('free', ROOT+'container/content/top/free', raycast_top=None)
    buttons = [make_button('btnPlay', ROOT+'btnPlay'), make_button('btnBack', ROOT+'topPanel/btnBack'), free]
    if duplicate: buttons.append(dict(free))
    if blocked: buttons.append(make_button('custom_button_1(Clone)', 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/custom_button_1(Clone)'))
    backend = FakeBackend(buttons)
    backend.ui = make_ui([make_text(str(amount), ROOT+'topPanel/coin/text')])
    return backend, make_oracle(backend)

def test_free_coin_delegation_uses_exact_native_button():
    backend, oracle = fixture()
    receipt = oracle.click('game-room/free-coins')
    assert receipt.path == ROOT+'container/content/top/free'
    assert len(backend.taps) == 1

@pytest.mark.parametrize('kwargs', [{'amount':40}, {'blocked':True}, {'duplicate':True}])
def test_free_coin_unsafe_state_has_no_input(kwargs):
    backend, oracle = fixture(**kwargs)
    with pytest.raises(SemanticGateClosed): oracle.click('game-room/free-coins')
    assert not backend.taps

def test_native_coin_resource_is_routed_to_game_room_only_in_its_context():
    oracle = FakeOracle()
    oracle.game_room_page_visible = lambda: True
    oracle.game_room_list_visible = lambda: False
    oracle.observation_target_present = lambda target: target == 'game-room/free-coins'
    oracle.reward_resource_available = Mock(side_effect=AssertionError('wrong reward owner'))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_minigame()
    assert adapter.appear(NamedButton('COIN'))
    oracle.reward_resource_available.assert_not_called()

@pytest.mark.parametrize('blocker,success', [('award-info',True), ('msgbox',False)])
def test_free_claim_waits_for_inventory_and_allows_only_its_reward(blocker, success, monkeypatch):
    from types import SimpleNamespace
    import alas_headless.adapter.semantic.dispatch_actions as actions
    oracle = FakeOracle()
    amount = [26]
    oracle.minigame_coin_amount = lambda: amount[0]
    oracle.game_room_page_visible = lambda: True
    oracle.observation_target_present = lambda _: False
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=blocker)]
    original = oracle.click
    def claim(target):
        receipt = original(target)
        oracle.state_generation = receipt.generation + 1
        amount[0] = 36
        return receipt
    oracle.click = claim
    ticks = iter((0,0,0,9))
    monkeypatch.setattr(actions.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(actions.time, 'sleep', lambda _: None)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_minigame()
    if success:
        assert adapter.click(NamedButton('COIN')).semantic_id == 'game-room/free-coins'
    else:
        with pytest.raises(SemanticGateClosed,match='claim was not proven'):
            adapter.click(NamedButton('COIN'))
    assert oracle.click_calls == ['game-room/free-coins']
