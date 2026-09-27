import copy
import importlib.util
from pathlib import Path


def test_continuity_uses_completed_transaction_not_later_card_state():
    path = Path(__file__).resolve().parents[1] / 'scripts/python/run_alas_daily_quick_live_validation.py'
    spec = importlib.util.spec_from_file_location('daily_live', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = dict(task_result=True, receipts=[dict(semantic_id='daily/execute/fierce_assault/stage/1/quick/all')],
                  transactions=[dict(before=3, after=0)], grant_remaining=0,
                  completion_checks=[dict(complete=True, reward_closed=True, remaining=0)],
                  reward_closed=False, award_absent_after_task=True, daily_page_after_task=True)
    assert module.continuity_passed(result)
    for key, value in [('completion_checks', []), ('award_absent_after_task', False),
                       ('task_result', False), ('grant_remaining', 1)]:
        invalid = copy.deepcopy(result)
        invalid[key] = value
        assert not module.continuity_passed(invalid)
