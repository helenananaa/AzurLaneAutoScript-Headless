"""A requested Hospital destination cannot loop through another event family."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from alas_headless import AlasSemanticAdapter
from alas_headless.adapter.task_lifecycle import (
    TaskCapabilityUnavailable, current_semantic_task, semantic_task_scope,
)
from tests.semantic_support.observer_fixtures import FakeBackend, make_oracle, make_ui


def retained_event():
    path = Path(__file__).resolve().parents[1] / "artifacts/full-feature-live-20261025/hospital-r3-post-stop-observation.json"
    if not path.exists():
        pytest.skip("private current Hospital boundary observation unavailable")
    raw = json.loads(path.read_text(encoding="utf-8"))["raw"]
    backend = FakeBackend(raw["buttons"]["buttons"])
    ui = raw["ui"]
    backend.ui = make_ui(ui["texts"], images=ui["images"], toggles=ui["toggles"])
    return backend, AlasSemanticAdapter(make_oracle(backend), lambda: None)


def session():
    return SimpleNamespace(discard_task_state=Mock(), trace=None)


def test_native_task_identity_is_restored_on_nested_scope_and_failure():
    outer, inner = session(), session()
    assert current_semantic_task() is None
    with semantic_task_scope(outer, "commission"):
        assert current_semantic_task() == "commission"
        with pytest.raises(ValueError), semantic_task_scope(inner, "hospital"):
            assert current_semantic_task() == "hospital"
            raise ValueError("failed native call")
        assert current_semantic_task() == "commission"
    assert current_semantic_task() is None
    outer.discard_task_state.assert_called_once()
    inner.discard_task_state.assert_called_once()


def test_hospital_rejects_proven_other_event_before_return_or_reentry_input():
    backend, adapter = retained_event()
    native = session()
    with pytest.raises(TaskCapabilityUnavailable, match="ordinary event battle selector"), semantic_task_scope(native, "hospital"):
        adapter.appear("HOSIPITAL_CHECK")
    assert native.last_task_outcome == dict(task="hospital", outcome="capability-unavailable")
    assert not backend.taps and not backend.swipes
    assert current_semantic_task() is None


@pytest.mark.parametrize("task", [None, "commission", "event_story", "main"])
def test_other_tasks_can_enumerate_hospital_on_the_same_event(task):
    backend, adapter = retained_event()
    if task is None:
        assert not adapter.appear("HOSIPITAL_CHECK")
    else:
        with semantic_task_scope(session(), task):
            assert not adapter.appear("HOSIPITAL_CHECK")
    assert not backend.taps and not backend.swipes


def test_hospital_probe_on_known_main_is_a_normal_navigation_absence():
    from tests.semantic_support.observer_fixtures import make_button
    backend = FakeBackend([
        make_button("battle", "UICamera/Canvas/UIMain/MainUI/frame/right/1/battle"),
        make_button("formation", "UICamera/Canvas/UIMain/MainUI/frame/right/1/formation"),
    ])
    adapter = AlasSemanticAdapter(make_oracle(backend), lambda: None)
    with semantic_task_scope(session(), "hospital"):
        assert not adapter.appear("HOSIPITAL_CHECK")
    assert not backend.taps


def test_incomplete_event_does_not_become_a_proven_wrong_activity():
    from alas_headless import SemanticGateClosed
    backend, adapter = retained_event()
    stage = next(b for b in backend.buttons["buttons"] if "/Chapter_" in b["path"] and b["name"] == "main")
    backend.buttons["buttons"].append(dict(stage))
    backend.buttons["button_count"] += 1
    with pytest.raises(SemanticGateClosed), semantic_task_scope(session(), "hospital"):
        adapter.appear("HOSIPITAL_CHECK")
    assert not backend.taps and not backend.swipes
