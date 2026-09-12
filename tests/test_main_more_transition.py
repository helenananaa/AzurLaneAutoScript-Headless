from types import SimpleNamespace

import pytest

from alas_headless import AlasSemanticAdapter
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('present,enabled,generation,reuse', [
    (True, True, 11, True),
    (False, True, 11, False),
    (True, False, 11, False),
    (True, True, 10, False),
])
def test_more_reuses_receipt_only_after_observed_sidebar_transition(present, enabled, generation, reuse):
    receipt = SimpleNamespace(generation=10)
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'reward/page/back' and present
    oracle.enabled = lambda target: target == 'reward/page/back' and enabled
    oracle.read_state = lambda: SimpleNamespace(generation=generation)
    host = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    host._main_more_entry_receipt = receipt
    result = host._click_mapped('GOTO_MAIN_MORE', 'main/more')
    assert (result is receipt) == reuse
    assert oracle.click_calls == ([] if reuse else ['main/more'])
