"""Evidence retention for the original multi-run Hard task."""

from types import SimpleNamespace
from unittest.mock import Mock

from alas_headless import SemanticGateClosed
from alas_headless.adapter.semantic.contracts import CampaignAutoSearchCompletionProof
from scripts.python.run_alas_hard_live_validation import _completion_value, _observe_counters


def test_each_completion_keeps_its_own_generation_and_fleet_roles():
    values = [
        _completion_value(CampaignAutoSearchCompletionProof(
            stage_code="11-4", result_generation=generation,
            result_path="reward/total", fleet1_role="standby", fleet2_role="all",
            waited_seconds=25.0, combat_auto_generation=generation - 10,
            result_exit_receipt=None,
        ))
        for generation in (100, 200, 300)
    ]
    assert [value["result_generation"] for value in values] == [100, 200, 300]
    assert all(value["fleet2_role"] == "all" for value in values)
    assert all(value["combat_auto_proven"] for value in values)


def test_optional_counter_failure_is_retained_without_stopping_original_task():
    oracle = SimpleNamespace(
        campaign_hard_remain=Mock(side_effect=SemanticGateClosed("transition")),
        campaign_oil=Mock(return_value=1000),
        read_state=Mock(return_value=SimpleNamespace(generation=10)),
    )
    before = _observe_counters(oracle, "before_runs", remain=3)
    assert before["remain"] == 3
    oracle.campaign_hard_remain.assert_not_called()
    after = _observe_counters(oracle, "after_run", run=1)
    assert "remain" not in after
    assert after["remain_error"] == "SemanticGateClosed: transition"
    assert after["oil"] == 1000
    assert after["generation"] == 10
