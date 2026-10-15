"""Exercise native Research queue input through the real session/frame boundary."""

from unittest import mock

import pytest

from alas_headless import AlasSemanticSession, ResearchProjectStatus, SemanticGateClosed
from alas_headless.adapter import AdbRuntimeHandle, StaleFrameError
from alas_headless.semantic_oracle import AdbObserverBridge
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_text, make_ui,
)
from tests.test_adapter_session_runtime_handle import PACKAGE, REVISION, expected_fingerprint


def research_queue_session(*, confirmed_start=True, edge=False):
    selected = "UICamera/Canvas/UIMain/TechnologyUI(Clone)/main/base_page/selecte_panel"
    card = selected + "/technology_card/frame/"
    bounds = ({"left": 1200, "top": 559, "right": 1280, "bottom": 608} if edge
              else {"left": 514, "top": 559, "right": 681, "bottom": 608})
    point_x = 1279.75 if edge else 597
    backend = FakeBackend([
        make_button("selecte_panel", selected),
        make_button("stop_btn", card + "btns/stop_btn", x=407, y=583),
        make_button("join_btn", card + "btns/join_btn", x=point_x, y=583,
                    bounds=bounds, raycast_top=None),
    ])
    join_image = make_image(card + "btns/join_btn", "join_btn", bounds=bounds)
    join_image["raycast_target"] = True
    backend.ui = make_ui([make_text("D-332-MI", card + "name_bg/Text")], images=[
        make_image(card + "top/label/version", "version_9"), join_image,
    ])
    bridge = AdbObserverBridge("offline-research-queue", PACKAGE)
    bridge.pid = backend.snapshot["pid"]
    bridge.request = backend.request
    bridge.foreground_component = backend.foreground_component
    bridge.tap = backend.tap
    bridge.swipe = backend.swipe
    bridge.package_pid = mock.Mock(return_value=bridge.pid)
    handle = AdbRuntimeHandle(bridge, fingerprint_sha256=expected_fingerprint())
    # A confirmed, already-paid start needs no second start grant to queue.
    session = AlasSemanticSession(driver_revision=REVISION, runtime_handle=handle,
                                  research_start_budget=0 if confirmed_start else 1)
    adapter = session.open()
    adapter.begin_research()
    context = adapter._research_context
    context.selected_code = "D-332-MI"
    context.selected_series = 9
    context.selected_status = ResearchProjectStatus.RUNNING
    if confirmed_start:
        context.start_confirm_receipt = object()
    session.refresh_frame()
    return backend, bridge, session, adapter


def test_queue_add_returns_receipt_after_its_input_invalidates_the_proof_frame():
    backend, bridge, session, adapter = research_queue_session()
    invalidated_at_tap = []
    backend.on_tap = lambda *_: invalidated_at_tap.append(session._frame_clock.current_frame_id is None)

    receipt = session.click("RESEARCH_QUEUE_ADD")

    assert receipt.semantic_id == "research/detail/queue"
    assert adapter._research_context.queue_add_receipt == receipt
    assert backend.taps == [(597, 583)]
    assert invalidated_at_tap == [True]
    assert adapter.oracle.input_dispatch_count == 1
    assert adapter._action_ledger.remaining("research.start") == 0
    assert not adapter._research_context.queue_add_requires_start_grant
    bridge.package_pid.assert_called_once_with()
    with pytest.raises(StaleFrameError):
        session._frame_clock.borrow()


def test_existing_running_project_can_queue_without_another_start_input():
    backend, _, session, adapter = research_queue_session(confirmed_start=False)
    receipt = session.click("RESEARCH_QUEUE_ADD")
    assert receipt.semantic_id == "research/detail/queue"
    assert backend.taps == [(597, 583)]
    assert adapter._research_context.start_receipt is None
    assert adapter._research_context.start_confirm_receipt is None
    assert adapter._research_context.queue_add_requires_start_grant
    assert adapter._action_ledger.remaining("research.start") == 1


@pytest.mark.parametrize("changed", ["code", "series"])
def test_queue_add_rejects_changed_selected_identity_on_the_final_session_frame(changed):
    backend, _, session, adapter = research_queue_session()
    if changed == "code":
        backend.ui["texts"][0]["text"] = "D-347-MI"
    else:
        backend.ui["images"][0]["sprite"] = "version_10"
    # Keep the earlier live observation at the selected identity. The actual
    # freshly acquired immutable frame must independently reject the change.
    adapter.oracle.research_detail_identity = lambda: ("D-332-MI", 9)
    with pytest.raises(SemanticGateClosed, match="selected research project (identity|series) changed"):
        session.click("RESEARCH_QUEUE_ADD")
    assert backend.taps == []
    assert adapter.oracle.input_dispatch_count == 0
    assert adapter._research_context.queue_add_receipt is None


@pytest.mark.parametrize("changed", ["foreground", "pid", "freshness"])
def test_queue_add_keeps_the_real_final_input_preflight(changed):
    backend, bridge, session, adapter = research_queue_session()
    original = adapter._fresh_input_oracle

    def changed_after_frozen_proof_acquisition():
        oracle = original()
        if changed == "foreground":
            backend.foreground = "other.package/OtherActivity"
        elif changed == "pid":
            bridge.package_pid.return_value = bridge.pid + 1
        else:
            frame = session._frame_clock.borrow()
            session._frame_clock._monotonic_ns = lambda: frame.captured_monotonic_ns + 20_000_000_000
        return oracle

    adapter._fresh_input_oracle = changed_after_frozen_proof_acquisition
    with pytest.raises((SemanticGateClosed, StaleFrameError)):
        session.click("RESEARCH_QUEUE_ADD")
    assert backend.taps == []
    assert adapter.oracle.input_dispatch_count == 0
    assert adapter._research_context.queue_add_receipt is None


def test_queue_add_keeps_the_reviewed_delegated_image_proof():
    backend, _, session, adapter = research_queue_session()
    backend.ui["images"][1]["sprite"] = "unreviewed_join_image"
    with pytest.raises(SemanticGateClosed, match="queue-add input is not proven"):
        session.click("RESEARCH_QUEUE_ADD")
    assert backend.taps == []
    assert adapter.oracle.input_dispatch_count == 0


def test_queue_add_uses_common_integer_bounds_without_changing_typed_receipt():
    backend, _, session, _ = research_queue_session(edge=True)
    receipt = session.click("RESEARCH_QUEUE_ADD")
    assert backend.taps == [(1279, 583)]
    assert receipt.point.x == 1279.75
    assert receipt.bounds.right == 1280
