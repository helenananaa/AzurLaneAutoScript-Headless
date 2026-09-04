"""Task outcomes release old authority without granting new action budgets."""

import pytest

from alas_headless import AlasSemanticSession, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter import ActionLeaseError, StaleFrameError, UnknownObservationError, UnsupportedPixelRead
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from tests.semantic_support.adapter_cases import AlasSemanticAdapterTestsSupport
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import DRIVER_REVISION
from tests.test_adapter_frame import make_clock


def session_with_task():
    session = AlasSemanticSession(serial="offline-test", driver_revision=DRIVER_REVISION)
    adapter, oracle, _ = AlasSemanticAdapterTestsSupport().make_adapter(campaign_combat_budget=2)
    session.adapter = adapter
    oracle.enabled_values["reward/award-info/close"] = False
    adapter.begin_research()
    adapter._daily_pending_receipt = object()
    adapter._operation_siren_pending_order = "radar"
    adapter._operation_siren_combat_active = True
    adapter._campaign_evidence_sequence = 3
    session._combat_result_observation = ("BATTLE_STATUS_S", 100.0)
    session._meta_beacon_active = True
    session._opsi_sample_use = object()
    _, _, session._frame_clock = make_clock()
    frame = session._frame_clock.acquire()
    return session, adapter, oracle, frame


@pytest.mark.parametrize("error", [AlasSemanticUnmapped("optional"), UnknownObservationError(), UnsupportedPixelRead()])
def test_unsupported_task_releases_context_and_frame_then_next_task_runs(error):
    session, adapter, oracle, frame = session_with_task()
    ledger = adapter._action_ledger
    ledger.dispatch("campaign.grid_click", lambda: None)
    receipt = object()
    adapter._daily_execution_receipts.append(receipt)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, "research"):
            raise error
    assert caught.value.cause is error
    assert session.last_task_outcome == {"task": "research", "outcome": "capability-unavailable"}
    assert adapter._research_context is None
    assert adapter._daily_pending_receipt is None
    assert adapter._operation_siren_pending_order is None
    assert not adapter._operation_siren_combat_active
    assert not session._meta_beacon_active
    assert session._opsi_sample_use is None
    assert session._combat_result_observation is None
    assert ledger is adapter._action_ledger
    assert ledger.remaining("campaign.grid_click") == 1
    assert adapter._campaign_evidence_sequence == 3
    assert adapter.daily_execution_receipts() == (receipt,)
    with pytest.raises(StaleFrameError):
        session._frame_clock.borrow(frame.frame_id)
    with semantic_task_scope(session, "reward"):
        session._frame_clock.acquire()
        oracle.exists_values["task/page/back"] = True
        assert session.appear(NamedButton("MISSION_CHECK"))
    assert session.last_task_outcome["outcome"] == "returned"
    assert ledger.remaining("campaign.grid_click") == 1


@pytest.mark.parametrize("error", [SemanticGateClosed("package identity failed"),
    SemanticGateClosed("target ambiguous"), SemanticGateClosed("input result uncertain"),
    StaleFrameError(), ActionLeaseError(), RuntimeError("bug")])
def test_runtime_and_input_errors_keep_original_failure(error):
    session, adapter, _, _ = session_with_task()
    with pytest.raises(type(error)) as caught:
        with semantic_task_scope(session, "research"):
            raise error
    assert caught.value is error
    assert adapter._research_context is None
    assert session.last_task_outcome["outcome"] == "raised"


def test_task_release_does_not_clear_input_generation_invalidation():
    _, _, clock = make_clock()
    frame = clock.acquire()
    clock.invalidate(frame.frame_id)
    clock.release_frame()
    with pytest.raises(StaleFrameError):
        clock.acquire()


def test_no_semantic_session_leaves_native_exception_unchanged():
    error = UnsupportedPixelRead()
    with pytest.raises(UnsupportedPixelRead) as caught:
        with semantic_task_scope(None, "native"):
            raise error
    assert caught.value is error


def test_task_end_is_propagated_after_cleanup():
    class TaskEnd(Exception):
        pass
    session, adapter, _, _ = session_with_task()
    with pytest.raises(TaskEnd):
        with semantic_task_scope(session, "reward"):
            raise TaskEnd()
    assert adapter._research_context is None
