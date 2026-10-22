from types import SimpleNamespace
import pytest
from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import FakeOracle


@pytest.mark.parametrize('destination, generation, dispatched', [
    (True, 11, False), (False, 11, False),
    (True, 10, False), (True, 11, True),
])
def test_live_area_race_requires_fresh_destination_without_additional_input(
        monkeypatch, destination, generation, dispatched):
    from alas_headless.adapter.semantic import dispatch_actions
    clock = [0.0]
    monkeypatch.setattr(dispatch_actions.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(dispatch_actions.time, 'sleep',
                        lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    oracle = FakeOracle()
    oracle.input_dispatch_count = 0
    oracle.observation_target_present = lambda target: (
        target == 'dorm-menu/dorm' and destination and clock[0] >= 0.4)
    oracle.enabled = oracle.observation_target_present
    oracle.read_state = lambda: SimpleNamespace(generation=generation)
    calls = []
    def click(target):
        calls.append(target)
        oracle.input_dispatch_count += int(dispatched)
        raise SemanticGateClosed('semantic target is not actionable')
    oracle.click = click
    adapter = AlasSemanticAdapter(oracle, package_gate=lambda: None)
    prior = SimpleNamespace(generation=10)
    adapter._main_live_entry_receipt = prior
    if destination and generation > 10 and not dispatched:
        assert adapter._click_mapped('MAIN_GOTO_DORMMENU', 'main/live') is prior
    else:
        with pytest.raises(SemanticGateClosed):
            adapter._click_mapped('MAIN_GOTO_DORMMENU', 'main/live')
    assert calls == ['main/live']
    assert oracle.input_dispatch_count == int(dispatched)
