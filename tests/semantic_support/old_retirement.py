"""Actual Session/adapter/frame clock over an OFFLINE retained typed fixture."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace as N

from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from alas_headless.adapter import (
    SemanticFrameClock,
    SemanticFrameReader,
    StaleFrameError,
)
from alas_headless.semantic_oracle import SemanticOracle, OracleFingerprint
from tests.test_adapter_frame import FakeRuntimeHandle, MutableClock, COMPONENT


def build_old_frame_rig(*, budget=1, transport_unknown=False):
    folder = Path(__file__).resolve().parents[1] / "fixtures"
    retained = json.loads(
        (folder / "old-retirement-selection-20261026.json").read_text(encoding="utf-8")
    )
    handle = FakeRuntimeHandle()
    handle.snapshot = copy.deepcopy(retained["selection_state"]["snapshot"])
    handle.buttons = copy.deepcopy(retained["selection_state"]["buttons_snapshot"])
    handle.ui = copy.deepcopy(retained["selection_ui"]["snapshot"])
    handle.pid = handle.snapshot["pid"]
    handle.component = COMPONENT
    timer = MutableClock()
    preflight_calls = []
    holder = {}

    def preflight():
        clock = holder["clock"]
        if clock.current_frame_id is not None:
            clock.borrow(require_fresh=True)
            clock.invalidate(clock.current_frame_id)
        preflight_calls.append("validated before actual dispatch")

    oracle = SemanticOracle(
        handle.observer_request,
        handle.foreground_component,
        handle.tap,
        OracleFingerprint(
            package=handle.snapshot["package"],
            component=COMPONENT,
            driver_revision=handle.snapshot["driver_revision"],
            expected_pid=handle.pid,
            max_age_ms=2500,
        ),
        input_preflight=preflight,
        sleep=lambda _: None,
    )
    clock = SemanticFrameClock(handle, oracle, monotonic_ns=timer)
    holder["clock"] = clock
    reader = SemanticFrameReader(clock, oracle)
    delegate = AlasSemanticSession(
        serial="offline-old-retire-frame",
        driver_revision=handle.snapshot["driver_revision"],
        retirement_budget=budget,
        observer_max_age_ms=2500,
    )
    gates = []
    adapter = AlasSemanticAdapter(
        oracle,
        lambda: gates.append("package gate"),
        action_ledger=delegate.action_ledger,
        frame_observation_oracle=reader.oracle,
        frame_identity_provider=reader.identity,
        input_frame_refresher=delegate.refresh_frame,
    )
    delegate.adapter = adapter
    delegate._runtime_handle = handle
    delegate._frame_clock = clock
    delegate._frame_reader = reader
    delegate.unrelated_capability_probe = (
        lambda: "unrelated capability remains available"
    )
    invalidated = []

    def tap(x, y):
        try:
            clock.borrow()
        except StaleFrameError:
            invalidated.append(True)
        else:
            raise AssertionError("old source frame survived actual input dispatch")
        handle.taps.append((x, y))
        if transport_unknown:
            raise OSError("controlled transport result unknown")
        for value in (handle.snapshot, handle.buttons, handle.ui):
            value["generation"] += 1
        for text in handle.ui["texts"]:
            if text["path"].endswith("/bottom_info/bg_input/count"):
                text["text"] = str(int(text["text"]) + 1)

    # Keep the real SemanticOracle dispatch wrapper/counter/preflight. Only
    # its final runtime backend is controlled, exactly as the existing tests.
    oracle._tap_backend = tap
    facade = delegate
    return N(
        handle=handle,
        oracle=oracle,
        clock=clock,
        reader=reader,
        timer=timer,
        delegate=delegate,
        adapter=adapter,
        facade=facade,
        gates=gates,
        preflight_calls=preflight_calls,
        invalidated=invalidated,
    )
