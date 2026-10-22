"""Task outcomes release old authority without granting new action budgets."""

import pytest

from alas_headless import AlasSemanticSession, AlasSemanticUnmapped, SemanticGateClosed
from alas_headless.adapter import ActionLeaseError, StaleFrameError, UnknownObservationError, UnsupportedPixelRead
from alas_headless.adapter.task_lifecycle import TaskCapabilityUnavailable, semantic_task_scope
from alas_headless.adapter.semantic.contracts import AlasSemanticActionDeferred
from alas_headless.oracle.errors import (SemanticGlobeSelectionMissed, SemanticGlobeDragPathUnavailable,
    SemanticStrongholdEntryLocked, SemanticInputBlocked, SemanticTargetNotActionable,
    SemanticTargetMissing, ObserverTransportError)
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
    SemanticTargetMissing('accepted result is absent'), ObserverTransportError('malformed observer'),
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


@pytest.mark.parametrize('error', [SemanticInputBlocked('main/battle', 10, ('bulletin',)),
    SemanticTargetNotActionable('dorm/feed', 10)])
def test_classified_no_input_refusal_is_local_and_preserves_grants_and_next_task(error):
    session, adapter, oracle, frame = session_with_task()
    remaining = adapter._action_ledger.remaining('campaign.grid_click')
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'research'):
            raise error
    assert caught.value.cause is error
    assert 'semantic input deferred' in str(caught.value)
    assert session.last_task_outcome == {'task': 'research', 'outcome': 'input-unavailable'}
    expected_error = {'type': type(error).__name__, 'message': str(error),
                      'semantic_id': error.semantic_id, 'generation': error.generation}
    if isinstance(error, SemanticInputBlocked):
        expected_error['blockers'] = list(error.blockers)
    assert session.last_task_error == expected_error
    assert oracle.click_calls == []
    assert adapter._action_ledger.remaining('campaign.grid_click') == remaining
    with pytest.raises(StaleFrameError):
        session._frame_clock.borrow(frame.frame_id)
    with semantic_task_scope(session, 'reward'):
        session._frame_clock.acquire()
        oracle.exists_values['task/page/back'] = True
        assert session.appear(NamedButton('MISSION_CHECK'))
    assert session.last_task_outcome == {'task': 'reward', 'outcome': 'returned'}
    assert adapter._action_ledger.remaining('campaign.grid_click') == remaining


def test_real_blocked_input_stays_closed_until_fresh_overlay_unmount():
    from alas_headless import AlasSemanticAdapter
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    buttons = [make_button('battle', 'UICamera/Canvas/UIMain/MainUI/frame/right/1/battle'),
        make_button('close', 'OverlayCamera/Overlay/UIMain/NewBulletinBoardUI(Clone)/close')]
    backend = FakeBackend(buttons)
    oracle = make_oracle(backend)
    session = AlasSemanticSession('offline-test', DRIVER_REVISION)
    session.adapter = AlasSemanticAdapter(oracle, lambda: None)
    for task in ('research', 'reward'):
        with pytest.raises(TaskCapabilityUnavailable) as caught:
            with semantic_task_scope(session, task):
                oracle.click('main/battle')
        assert isinstance(caught.value.cause, SemanticInputBlocked)
        assert backend.taps == []
    backend.buttons['buttons'].pop()
    backend.buttons['button_count'] = 1
    for snapshot in (backend.snapshot, backend.buttons, backend.ui):
        snapshot['generation'] += 1
    with semantic_task_scope(session, 'reward'):
        receipt = oracle.click('main/battle')
    assert receipt.generation == 11
    assert backend.taps == [(640, 360)]
    assert session.last_task_outcome['outcome'] == 'returned'


def test_real_accepted_input_failure_keeps_original_failure_and_never_retries():
    from alas_headless import AlasSemanticAdapter
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    backend = FakeBackend([make_button('battle', 'UICamera/Canvas/UIMain/MainUI/frame/right/1/battle')])
    oracle = make_oracle(backend)
    session = AlasSemanticSession('offline-test', DRIVER_REVISION)
    session.adapter = AlasSemanticAdapter(oracle, lambda: None)
    error = SemanticGateClosed('input result uncertain')
    def uncertain():
        raise error
    backend.on_tap = uncertain
    with pytest.raises(SemanticGateClosed) as caught:
        with semantic_task_scope(session, 'reward'):
            oracle.click('main/battle')
    assert caught.value is error
    assert backend.taps == [(640, 360)]
    assert session.last_task_outcome == {'task': 'reward', 'outcome': 'raised'}


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



def test_real_stale_observation_defers_task_and_reenters_only_with_fresh_state():
    from alas_headless import AlasSemanticAdapter
    from alas_headless.oracle.errors import SemanticSnapshotStale
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    backend = FakeBackend([make_button('battle', 'UICamera/Canvas/UIMain/MainUI/frame/right/1/battle')])
    oracle = make_oracle(backend)
    session = AlasSemanticSession('offline-test', DRIVER_REVISION)
    session.adapter = AlasSemanticAdapter(oracle, lambda: None)
    backend.snapshot['age_ms'] = 10001
    with pytest.raises(TaskCapabilityUnavailable) as caught:
        with semantic_task_scope(session, 'shop_once'):
            oracle.read_state()
    assert isinstance(caught.value.cause, SemanticSnapshotStale)
    assert caught.value.cause.age_ms == 10001
    assert session.last_task_error['age_ms'] == 10001
    assert session.last_task_error['max_age_ms'] == oracle.fingerprint.max_age_ms
    assert session.last_task_error['input_outcome_uncertain'] is False
    assert any(frame['function'] == 'read_state' for frame in session.last_task_error['read_stack'])
    assert session.last_task_outcome == {'task': 'shop_once', 'outcome': 'observation-not-ready'}
    assert backend.taps == []
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(session, 'reward'):
            oracle.click('main/battle')
    assert backend.taps == []
    backend.snapshot['age_ms'] = 0
    for snapshot in (backend.snapshot, backend.buttons, backend.ui):
        snapshot['generation'] += 1
    with semantic_task_scope(session, 'reward'):
        assert oracle.read_state().generation == 11
        assert oracle.click('main/battle').generation == 11
    assert backend.taps == [(640, 360)]
    assert session.last_task_outcome['outcome'] == 'returned'


@pytest.mark.parametrize('stage', ['backend', 'postcondition'])
def test_stale_failure_during_dispatched_action_keeps_original_uncertainty(stage):
    from alas_headless import AlasSemanticAdapter
    from alas_headless.oracle.errors import SemanticSnapshotStale
    from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle
    backend = FakeBackend([make_button('battle', 'UICamera/Canvas/UIMain/MainUI/frame/right/1/battle')])
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None, campaign_combat_budget=2)
    session = AlasSemanticSession('offline-test', DRIVER_REVISION)
    session.adapter = adapter
    error = SemanticSnapshotStale(12000)
    if stage == 'backend':
        def uncertain():
            raise error
        backend.on_tap = uncertain
        operation = lambda: oracle.click('main/battle')
    else:
        def operation():
            oracle.click('main/battle')
            raise error
    remaining = adapter._action_ledger.remaining('campaign.grid_click')
    with pytest.raises(SemanticSnapshotStale) as caught:
        with semantic_task_scope(session, 'reward'):
            adapter._dispatch_mutation('campaign.grid_click', operation)
    assert caught.value is error and error.input_outcome_uncertain
    assert backend.taps == [(640, 360)]
    assert session.last_task_outcome == {'task': 'reward', 'outcome': 'raised'}
    assert adapter._action_ledger.remaining('campaign.grid_click') == remaining - 1
