"""Combat observations share ALAS' screenshot lease and retain live checks."""

from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticSession
from alas_headless.adapter import SemanticFrameReader
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.test_adapter_frame import COMPONENT, REVISION, make_clock
from tests.test_alas_combat_observer import frame, qualified_manifest


def host():
    handle, _, clock = make_clock()
    payload = frame(10, ("BATTLE_STATUS_S",))
    for endpoint in ("snapshot", "buttons", "ui"):
        payload[endpoint]["driver_revision"] = REVISION
        setattr(handle, endpoint, payload[endpoint])
    session = AlasSemanticSession("offline", REVISION)
    adapter = SimpleNamespace(
        campaign_combat_committed=lambda: True,
        operation_siren_combat_committed=lambda: False,
    )
    session.open = lambda: adapter
    session._combat_manifest = replace(qualified_manifest(), driver_revision=REVISION)
    return handle, clock, adapter, session


def test_repeated_combat_probes_use_frozen_frame_without_new_endpoint_requests():
    handle, clock, adapter, session = host()
    clock.acquire(include_ui=True)
    adapter._frame_or_live_observation_oracle = SemanticFrameReader(clock, clock._oracle).oracle
    requests = list(handle.requests)
    foreground_calls = handle.foreground_calls
    # The live runtime has already advanced; this ALAS screenshot still owns 10.
    handle.ui["generation"] = 30
    assert session._live_combat_snapshot().generation == 10
    assert session._live_combat_snapshot().generation == 10
    assert handle.requests == requests
    assert handle.foreground_calls == foreground_calls
    assert handle.taps == []


def test_live_fallback_retries_entire_pair_without_relaxing_generation_checks():
    handle, clock, adapter, session = host()
    adapter._frame_or_live_observation_oracle = lambda: clock._oracle
    handle.ui["generation"] = 30
    def advance(_):
        handle.snapshot["generation"] = handle.buttons["generation"] = 30
    clock._oracle._sleep = Mock(side_effect=advance)
    assert session._live_combat_snapshot().generation == 30
    assert handle.requests.count("GET /v1/state\n") == 2
    assert handle.requests.count("GET /v1/ui\n") == 2
    assert handle.taps == []


@pytest.mark.parametrize("failure", ["generation", "activity", "stale"])
def test_live_combat_rejects_persistent_incoherence_or_identity_failure(failure):
    handle, clock, adapter, session = host()
    adapter._frame_or_live_observation_oracle = lambda: clock._oracle
    clock._oracle._sleep = lambda _: None
    if failure == "generation":
        handle.ui["generation"] = 30
    elif failure == "activity":
        handle.component = COMPONENT + ".Other"
    else:
        handle.snapshot["age_ms"] = 9000
    with pytest.raises(SemanticGateClosed):
        session._live_combat_snapshot()
    assert handle.taps == []
