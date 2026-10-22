"""Terminal diagnostics preserve accepted camera input without another device read."""
import importlib.util
from pathlib import Path
import sys
from types import MappingProxyType, SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts/python'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('scheduler_swipe_receipts', SCRIPTS / 'run_alas_configured_scheduler_live.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


@pytest.mark.parametrize('proven', [False, True])
def test_current_task_attempt_copied_without_historical_repetition_or_live_reads(proven):
    record = dict(dispatched=True, postcondition_proven=proven,
                  pre_generation=10, proof_generation=11,
                  start=(838, 304), end=(838, 501),
                  metadata=MappingProxyType({'handler': 123}))
    oracle = SimpleNamespace(_operation_siren_map_swipe_attempts=[{'older': True}, record])
    result = runner.map_swipe_attempts(oracle, 1)
    assert len(result) == 1
    assert result[0]['dispatched'] is True
    assert result[0]['postcondition_proven'] is proven
    assert result[0]['start'] == [838, 304]
    assert result[0]['metadata'] == {'handler': 123}
    record['postcondition_proven'] = not proven
    assert result[0]['postcondition_proven'] is proven


def test_no_bound_oracle_or_camera_history_is_an_empty_diagnostic():
    assert runner.map_swipe_attempts(None) == []
    assert runner.map_swipe_attempts(SimpleNamespace()) == []
