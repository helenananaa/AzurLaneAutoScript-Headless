from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticTargetMissing
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('present,enabled,generation,reuse', [
    (True, True, 11, True), (False, True, 11, False),
    (True, False, 11, False), (True, True, 10, False),
])
def test_tech_repeat_requires_observed_destination(present, enabled, generation, reuse):
    oracle = FakeOracle()
    oracle.observation_target_present = lambda target: target == 'research-menu/page/back' and present
    oracle.enabled = lambda target: target == 'research-menu/page/back' and enabled
    oracle.read_state = lambda: SimpleNamespace(generation=generation)
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    prior = SimpleNamespace(generation=10)
    adapter._main_tech_entry_receipt = prior
    receipt = adapter._click_mapped('MAIN_GOTO_RESHMENU', 'main/tech')
    assert (receipt is prior) == reuse
    assert oracle.click_calls == ([] if reuse else ['main/tech'])
    adapter.reset_task_state()
    assert adapter._main_tech_entry_receipt is None


@pytest.mark.parametrize('dispatched', [False, True])
def test_tech_transition_race_is_rechecked_only_before_input(dispatched):
    oracle = FakeOracle()
    observations = iter((False, True))
    oracle.observation_target_present = lambda target: next(observations)
    oracle.enabled = lambda target: True
    oracle.read_state = lambda: SimpleNamespace(generation=11)
    oracle.input_dispatch_count = 0
    def click(target):
        oracle.input_dispatch_count += int(dispatched)
        raise SemanticTargetMissing('source unmounted')
    oracle.click = click
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    prior = SimpleNamespace(generation=10)
    adapter._main_tech_entry_receipt = prior
    if dispatched:
        with pytest.raises(SemanticTargetMissing):
            adapter._click_mapped('MAIN_GOTO_RESHMENU', 'main/tech')
    else:
        assert adapter._click_mapped('MAIN_GOTO_RESHMENU', 'main/tech') is prior
