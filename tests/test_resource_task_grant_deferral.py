"""Keep resource/selection errors separate from ordinary grant exhaustion."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import ActionLeaseError
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton


def case(kind):
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter()
    if kind == 'awaken':
        action = lambda: adapter.begin_awaken_task(False)
    elif kind == 'enhancement':
        action = lambda: adapter.begin_enhancement_task('all', 5, None)
    elif kind == 'retirement':
        action = lambda: adapter.retire_ships_one_click(True)
    elif kind == 'build':
        adapter.begin_build()
        adapter._build_context.coins_owned = 3000
        adapter._build_context.prep_opened = True
        oracle.enabled_values['build/warning/confirm'] = False
        oracle.build_submit_state = Mock(return_value=SimpleNamespace(
            count=1, cubes_owned=10, cubes_required=1, coins_required=1500))
        action = lambda: adapter.click(NamedButton('POPUP_CONFIRM_GACHA_ORDER'))
    else:
        oracle.dorm_furniture_shop_balance = Mock(return_value=SimpleNamespace(dorm_coins=1000))
        if kind == 'furniture':
            oracle.dorm_furniture_purchase_state = Mock(return_value=SimpleNamespace(gold_price=100, quantity=1))
            oracle.click_dorm_furniture_purchase = Mock()
            action = adapter.buy_dorm_furniture_with_gold
        else:
            oracle.dorm_furniture_theme_purchase_state = Mock(return_value=SimpleNamespace(gold_price=100))
            oracle.click_dorm_furniture_theme_purchase_gold = Mock()
            action = adapter.buy_dorm_furniture_theme_with_gold
    return adapter, oracle, action


@pytest.mark.parametrize('kind', ['awaken', 'enhancement', 'retirement', 'build', 'furniture', 'theme'])
def test_valid_resource_task_zero_grant_defers_before_mutation(kind):
    adapter, oracle, action = case(kind)
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, kind):
            action()
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert oracle.click_calls == []
    assert oracle.awaken_calls == []
    assert oracle.enhancement_calls == []
    if kind == 'furniture':
        oracle.click_dorm_furniture_purchase.assert_not_called()
    elif kind == 'theme':
        oracle.click_dorm_furniture_theme_purchase_gold.assert_not_called()


def test_closed_awaken_ledger_with_candidates_keeps_fatal_contract_error():
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter(awaken_budget=1)
    adapter.begin_awaken_task(False)
    oracle.awaken_dock_candidates = Mock(return_value=(object(),))
    adapter._action_ledger.close()
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(ActionLeaseError):
        with semantic_task_scope(session, 'awaken'):
            adapter.awaken_next(False)


@pytest.mark.parametrize('bad', ['count', 'cubes', 'coins', 'preparation'])
def test_bad_build_resources_remain_fatal_even_with_zero_grant(bad):
    adapter, oracle, action = case('build')
    submit = oracle.build_submit_state.return_value
    if bad == 'count':
        submit.count = 0
    elif bad == 'cubes':
        submit.cubes_owned = 0
    elif bad == 'coins':
        adapter._build_context.coins_owned = 0
    else:
        adapter._build_context.prep_opened = False
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session, 'build'):
            action()
    assert not isinstance(caught.value, AlasSemanticActionDeferred)
    assert oracle.click_calls == []


def test_insufficient_furniture_coins_do_not_become_a_grant_failure():
    adapter, oracle, action = case('furniture')
    oracle.dorm_furniture_shop_balance.return_value.dorm_coins = 0
    session = SimpleNamespace(discard_task_state=adapter.reset_task_state, trace=None)
    with pytest.raises(SemanticGateClosed, match='coins are insufficient'):
        with semantic_task_scope(session, 'buy_furniture'):
            action()
    oracle.click_dorm_furniture_purchase.assert_not_called()
