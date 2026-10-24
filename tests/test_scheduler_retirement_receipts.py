"""Native retirement transactions remain attributable across scheduled tasks."""
from dataclasses import dataclass
import json
from types import MappingProxyType

import pytest

from tests.test_scheduler_failure_screenshot import load_runner


@dataclass(frozen=True)
class Receipt:
    generation: int
    evidence: object


@pytest.mark.parametrize('native_failure', [False, True])
def test_each_new_transaction_retained_even_if_native_call_later_raises(monkeypatch, native_failure):
    runner = load_runner(monkeypatch)
    cached = Receipt(1, MappingProxyType({'old': True}))
    current = {}
    actual_calls = []

    def native(*, keep_limit_break):
        nonlocal cached
        actual_calls.append(keep_limit_break)
        cached = Receipt(cached.generation + 1, MappingProxyType({'equipment_retained': True}))
        if native_failure:
            raise ValueError('native follow-up failed')
        return 3

    wrapped = runner.recorded_retirement(native, lambda: cached, lambda: current)
    for _ in range(2):
        if native_failure:
            with pytest.raises(ValueError, match='native follow-up failed'):
                wrapped(keep_limit_break=True)
        else:
            assert wrapped(keep_limit_break=True) == 3
    assert actual_calls == [True, True]
    encoded = json.loads(json.dumps(current))
    assert [r['generation'] for r in encoded['retirement_receipts']] == [2, 3]
    assert encoded['retirement_receipts'][0]['evidence']['equipment_retained'] is True


def test_previous_task_receipt_is_not_repeated_when_no_transaction_occurs(monkeypatch):
    runner = load_runner(monkeypatch)
    previous = Receipt(1, {})
    current = {}
    wrapped = runner.recorded_retirement(lambda: 0, lambda: previous, lambda: current)
    assert wrapped() == 0
    assert 'retirement_receipts' not in current


def test_recording_failure_does_not_change_native_return_or_exception(monkeypatch):
    runner = load_runner(monkeypatch)
    current = {}
    def broken_reader():
        raise RuntimeError('receipt unavailable')
    assert runner.recorded_retirement(lambda: 7, broken_reader, lambda: current)() == 7
    def native_failure():
        raise ValueError('original failure')
    with pytest.raises(ValueError, match='original failure'):
        runner.recorded_retirement(native_failure, broken_reader, lambda: current)()
    assert len(current['retirement_recording_errors']) == 4


def test_unknown_baseline_does_not_promote_a_cached_receipt(monkeypatch):
    runner = load_runner(monkeypatch)
    current = {}
    reads = 0
    def reader():
        nonlocal reads
        reads += 1
        if reads == 1:
            raise RuntimeError('initial diagnostic failed')
        return Receipt(1, {'old': True})
    assert runner.recorded_retirement(lambda: 0, reader, lambda: current)() == 0
    assert 'retirement_receipts' not in current
    assert current['retirement_recording_errors'] == ['initial diagnostic failed']
