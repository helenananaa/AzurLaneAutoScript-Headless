"""Task outcomes release old authority without granting new action budgets."""

import pytest

from alas_headless import AlasSemanticSession, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter import ActionLeaseError, StaleFrameError, UnknownObservationError, UnsupportedPixelRead
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.oracle.errors import SemanticGlobeSelectionMissed, SemanticGlobeDragPathUnavailable, SemanticStrongholdEntryLocked
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


@pytest.mark.parametrize("error", [AlasSemanticUnmapped("optional"), UnknownObservationError(), UnsupportedPixelRead(),
    SemanticGlobeSelectionMissed("native port input produced no pin after original focus retries"),
    SemanticGlobeDragPathUnavailable("original ALAS sampler found no owned globe drag path")])
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
    assert session.last_task_error == {'type': type(error).__name__, 'message': str(error)}
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
    assert session.last_task_error is None
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
    assert session.last_task_error == {'type': type(error).__name__, 'message': str(error)}


def test_native_stronghold_lock_defers_only_that_task_without_releasing_input_budget():
    session, adapter, oracle, frame = session_with_task()
    remaining = adapter._action_ledger.remaining('campaign.grid_click')
    error = SemanticStrongholdEntryLocked(51)
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'opsi_stronghold'):
            raise error
    assert caught.value.cause is error
    assert 'game prerequisite pending' in str(caught.value)
    assert session.last_task_outcome['outcome'] == 'prerequisite-pending'
    assert oracle.click_calls == []
    assert adapter._action_ledger.remaining('campaign.grid_click') == remaining
    with semantic_task_scope(session, 'reward'):
        session._frame_clock.acquire()
        oracle.exists_values['task/page/back'] = True
        assert session.appear(NamedButton('MISSION_CHECK'))
    assert session.last_task_error is None


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


@pytest.mark.parametrize('refresh', [False, True])
def test_ungranted_shop_action_defers_without_input_and_keeps_other_tasks_available(refresh):
    session, adapter, oracle, frame = session_with_task()
    ledger = adapter._action_ledger
    assert ledger.remaining('shop.purchase') == 0
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'shop_once'):
            if refresh:
                adapter.refresh_shop_once()
            else:
                adapter.purchase_shop_item_once(5, 'BookRedT3', 'Coins', 2400)
    assert isinstance(caught.value.cause, AlasSemanticActionDeferred)
    assert 'semantic action deferred' in str(caught.value)
    assert session.last_task_outcome == {'task': 'shop_once', 'outcome': 'action-deferred'}
    assert oracle.click_calls == []
    assert ledger.remaining('shop.purchase') == 0
    assert ledger.remaining('campaign.grid_click') == 2
    with pytest.raises(StaleFrameError):
        session._frame_clock.borrow(frame.frame_id)
    with semantic_task_scope(session, 'reward'):
        session._frame_clock.acquire()
        oracle.exists_values['task/page/back'] = True
        assert session.appear(NamedButton('MISSION_CHECK'))
    assert session.last_task_outcome['outcome'] == 'returned'
