from dataclasses import replace
import pytest
from alas_headless import SemanticGateClosed
from alas_headless.oracle.contracts import RetirementEquipmentState
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle


@pytest.mark.parametrize('outcome', ['delayed', 'stale', 'unchanged', 'inventory_changed'])
def test_deselection_waits_for_fresh_empty_selection_without_repeating_input(outcome):
    backend = FakeBackend([])
    oracle = make_oracle(backend)
    before = RetirementEquipmentState(generation=10, item_quantities=((0, 2),),
                                      selected_slots=(0,), all_checked=True)
    clear = replace(before, generation=12, selected_slots=(), all_checked=False)
    ticks = [0.0]
    oracle._monotonic = lambda: ticks[0]
    oracle._sleep = lambda delay: ticks.__setitem__(0, ticks[0] + delay)
    def state():
        if outcome == 'inventory_changed':
            return replace(clear, item_quantities=((0, 1),))
        if outcome == 'stale':
            return replace(clear, generation=10)
        if outcome == 'unchanged' or ticks[0] < 0.4:
            return before
        return clear
    oracle._retirement_equipment_state = state
    if outcome == 'delayed':
        oracle._wait_retirement_equipment_clear(before, 10, 1.0)
        assert ticks[0] >= 0.4
    else:
        with pytest.raises(SemanticGateClosed):
            oracle._wait_retirement_equipment_clear(before, 10, 1.0)
    assert backend.taps == []
