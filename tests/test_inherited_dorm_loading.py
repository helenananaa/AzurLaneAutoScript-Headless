from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from alas_headless.adapter.semantic.dispatch_result import UNHANDLED
from tests.semantic_support.fake_oracle import FakeOracle


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GET_ITEMS_2', 'GET_ITEMS_3',
                                'GOTO_MAIN_WHITE', 'RPG_HOME', 'FLEET_CHECK'])
@pytest.mark.parametrize('underlay', [None, 'commission-page', 'tactical-page', 'dorm-page'])
def test_exact_loading_with_known_business_underlay_yields_passive_probes(name, underlay):
    oracle = FakeOracle()
    blockers = ['loading'] + ([underlay] if underlay else [])
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=key) for key in blockers]
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert adapter._appear_priority(name) is False
    assert oracle.click_calls == []


@pytest.mark.parametrize('name', ['GET_ITEMS_1', 'GOTO_MAIN_WHITE', 'FLEET_CHECK'])
def test_foreign_overlay_is_not_loading_owned_absence(name):
    oracle = FakeOracle()
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=key)
                                       for key in ['loading', 'dorm-page', 'unknown-overlay']]
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert adapter._appear_priority(name) is UNHANDLED
    assert oracle.click_calls == []


@pytest.mark.parametrize('name', ['WITHDRAW', 'CAMPAIGN_WITHDRAW_CONFIRM', 'DOCK_CHECK'])
@pytest.mark.parametrize('foreign', [False, True])
def test_exact_inherited_dorm_proves_only_unobscured_withdraw_absence(name, foreign):
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'dorm/page/manage'
    oracle._blocking_rules = lambda *_: [SimpleNamespace(blocker_id=key) for key in
                                       (['dorm-page', 'unknown-overlay'] if foreign else ['dorm-page'])]
    def complete_dorm_summary():
        # Model the existing typed Dorm reader used by the inherited passive
        # path. Real-oracle blocker and incomplete-summary cases have separate
        # coverage in test_inherited_dorm_passive_probes.
        if foreign:
            raise SemanticGateClosed('dorm page identity is not proven')
        return oracle.dorm_state_value
    oracle._dorm_state_once = complete_dorm_summary
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    assert (adapter._appear_priority(name) is False) == (not foreign)
    assert oracle.click_calls == []
