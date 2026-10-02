import time
from types import SimpleNamespace
from unittest.mock import Mock
from itertools import chain, repeat, count

import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('destination_visible', [True, False])
@pytest.mark.parametrize('elapsed', [1, 30])
def test_menu_mount_between_probe_and_input_needs_fresh_destination(destination_visible, elapsed, monkeypatch):
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    receipt = SimpleNamespace(generation=10)
    host._main_battle_transition_receipt = receipt
    host._main_battle_transition_until = time.monotonic() + 20 - elapsed
    probes = chain([False, False], repeat(destination_visible))
    host._main_battle_destination_visible = Mock(side_effect=lambda: next(probes))
    ticks = count(0, 3)
    monkeypatch.setattr('alas_headless.adapter.semantic.dispatch_actions.time.monotonic', lambda: next(ticks))
    monkeypatch.setattr('alas_headless.adapter.semantic.dispatch_actions.time.sleep', lambda _: None)
    oracle.input_dispatch_count = 0

    def rejected(target):
        oracle.click_calls.append(target)
        raise SemanticGateClosed('semantic target is not actionable')

    oracle.click = rejected
    if destination_visible:
        assert host._click_mapped('MAIN_GOTO_CAMPAIGN_WHITE', 'main/battle') is receipt
    else:
        with pytest.raises(SemanticGateClosed, match='not actionable'):
            host._click_mapped('MAIN_GOTO_CAMPAIGN_WHITE', 'main/battle')
    assert oracle.click_calls == ['main/battle']
    assert oracle.input_dispatch_count == 0


@pytest.mark.parametrize('change', [None, 'no_receipt', 'old_generation', 'unknown_destination'])
def test_battle_receipt_needs_own_input_new_generation_and_known_destination(change):
    oracle = FakeOracle()
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    if change != 'no_receipt':
        host._main_battle_transition_receipt = SimpleNamespace(generation=10)
    oracle.read_state = lambda: SimpleNamespace(generation=10 if change == 'old_generation' else 11)
    oracle.campaign_menu_is_entry = lambda: change != 'unknown_destination'
    oracle.campaign_page_is_normal = lambda: False
    oracle.campaign_is_in_map = lambda: False
    assert host._main_battle_destination_visible() is (change is None)
