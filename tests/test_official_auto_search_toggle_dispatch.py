"""Native ALAS owns auto correction; the semantic shortcut reads its real Toggle."""

import ast
import os
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest import mock

import pytest

from alas_headless.adapter import SemanticFrameClock, SemanticFrameReader
from tests.test_adapter_frame import FakeRuntimeHandle
from tests.test_campaign_official_combat_ports import host, PAUSE_PATH
from tests.semantic_support.observer_fixtures import make_button, make_text, make_toggle


AUTO_PATH = "UICamera/Canvas/UIMain/CombatUIStandard(Clone)/AutoBtn"
AUTO_RESOURCES = ("AUTOMATION_ON", "AUTOMATION_OFF", "COMBAT_AUTO", "COMBAT_AUTO_133", "COMBAT_AUTO_150")


def combat_host(enabled):
    backend, oracle, adapter, session = host([make_button("PauseBtn", PAUSE_PATH)])
    backend.ui["toggles"] = [make_toggle(AUTO_PATH, checked=enabled)]
    backend.ui["toggle_count"] = 1
    return backend, oracle, adapter, session


@pytest.mark.parametrize("enabled", [False, True])
def test_official_combat_shortcut_observes_actual_toggle(enabled):
    backend, _, _, session = combat_host(enabled)
    assert session.appear("AUTOMATION_ON") is enabled
    for name in AUTO_RESOURCES[1:]:
        assert session.appear(name) is (not enabled)
    assert backend.taps == []


def test_official_toggle_uses_frozen_current_alas_frame():
    backend, oracle, adapter, session = combat_host(False)
    handle = FakeRuntimeHandle()
    handle.pid = backend.snapshot["pid"]
    handle.observer_request = backend.request
    handle.foreground_component = backend.foreground_component
    clock = SemanticFrameClock(handle, oracle)
    reader = SemanticFrameReader(clock, oracle)
    clock.acquire(include_ui=True)
    adapter._frame_observation_oracle = reader.oracle
    session._frame_clock = clock
    backend.ui["toggles"][0]["checked"] = True
    assert session.appear("COMBAT_AUTO") is True
    assert session.appear("AUTOMATION_ON") is False
    clock.acquire(include_ui=True)
    assert session.appear("COMBAT_AUTO") is False
    assert session.appear("AUTOMATION_ON") is True
    assert backend.taps == []


def test_nonofficial_combat_keeps_existing_shortcut_behavior():
    backend, _, adapter, session = combat_host(False)
    adapter._campaign_context.sortie_proof = None
    assert session.appear("AUTOMATION_ON") is True
    assert session.appear("AUTOMATION_OFF") is False
    assert session.appear("COMBAT_AUTO") is False
    assert backend.taps == []


@pytest.mark.parametrize("surface", ["total-result", "battle-result", "reconnect"])
@pytest.mark.parametrize("enabled", [False, True])
def test_topmost_result_or_reconnect_hides_retained_combat_toggle(surface, enabled):
    backend, _, _, session = combat_host(enabled)
    if surface == "total-result":
        backend.buttons["buttons"].append(make_button("ButtonExit", "OverlayCamera/Overlay/UIMain/"
            "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"))
    elif surface == "battle-result":
        backend.buttons["buttons"].append(make_button("confirmBtn", "OverlayCamera/Overlay/UIMain/"
            "NewBattleResultEmptyUI(Clone)/NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn"))
    else:
        popup = "root/Overlay/UIMain/Msgbox(Clone)/window/"
        backend.buttons["buttons"].extend(make_button(name, popup + "button_container/" + name)
            for name in ("custom_button_1(Clone)", "custom_button_2(Clone)"))
        backend.ui["texts"] = [
            make_text("服务器连接失败，是否重新连接？\n[NetworkDown]", popup + "msg_panel/content"),
            make_text("取 消", popup + "button_container/custom_button_2(Clone)/pic"),
            make_text("确 定", popup + "button_container/custom_button_1(Clone)/pic"),
        ]
        backend.ui["text_count"] = 3
    backend.buttons["button_count"] = len(backend.buttons["buttons"])
    for name in AUTO_RESOURCES:
        assert session.appear(name) is False
    assert backend.taps == []


def native_auto_runner(session):
    default = Path(__file__).resolve().parents[1] / (
        "artifacts/continuity-20261004/alas-runtime/module/combat/combat_auto.py")
    source = Path(os.environ.get("ALAS_TEST_COMBAT_AUTO_SOURCE", str(default)))
    if not source.exists():
        pytest.skip("retained original ALAS CombatAuto source unavailable")
    tree = ast.parse(source.read_text(encoding="utf8"))
    methods = [node for cls in tree.body if isinstance(cls, ast.ClassDef)
               and cls.name == "CombatAuto" for node in cls.body
               if isinstance(node, ast.FunctionDef)
               and node.name in ("combat_joystick_appear", "handle_combat_auto")]
    resources = ("COMBAT_AUTO", "COMBAT_AUTO_133", "COMBAT_AUTO_150", "COMBAT_AUTO_SWITCH")
    namespace = {name: name for name in resources}
    namespace["logger"] = SimpleNamespace(info=lambda *_: None)
    exec(compile(ast.Module(body=methods, type_ignores=[]), str(source), "exec"), namespace)
    timer = SimpleNamespace(reached=lambda: True, reset=lambda: None)
    runner = SimpleNamespace(
        device=SimpleNamespace(semantic_adapter=session, click=session.click),
        appear=lambda button, **_: session.appear(button), auto_mode_checked=False,
        auto_mode_switched=False, auto_mode_click_timer=SimpleNamespace(reached=lambda: False),
        auto_skip_timer=timer, auto_click_interval_timer=timer,
    )
    for name in ("combat_joystick_appear", "handle_combat_auto"):
        setattr(runner, name, MethodType(namespace[name], runner))
    return runner


@pytest.mark.parametrize("enabled", [False, True])
def test_original_auto_handler_corrects_typed_off_once_and_preserves_on(enabled):
    backend, _, _, session = combat_host(enabled)
    session._live_combat_click = mock.Mock(return_value=object())
    runner = native_auto_runner(session)
    assert runner.handle_combat_auto("combat_auto") is (not enabled)
    if enabled:
        session._live_combat_click.assert_not_called()
    else:
        session._live_combat_click.assert_called_once_with("COMBAT_AUTO")
        # The actual game reports ON in the next typed frame. Native ALAS
        # sees no joystick and submits no second toggle.
        backend.ui["toggles"][0]["checked"] = True
        assert runner.handle_combat_auto("combat_auto") is False
        assert session._live_combat_click.call_count == 1
    assert backend.taps == []


def test_native_menu_probes_record_corrected_auto_before_result_proof():
    backend, _, adapter, session = combat_host(False)
    session._live_combat_click = mock.Mock(return_value=object())
    runner = native_auto_runner(session)
    assert adapter.campaign_auto_search_result_visible() is False
    assert adapter._campaign_context.auto_search_combat_generation is None
    assert runner.handle_combat_auto("combat_auto") is True
    backend.ui["toggles"][0]["checked"] = True
    for projection in (backend.snapshot, backend.buttons, backend.ui):
        projection["generation"] = 11
    assert adapter.campaign_auto_search_result_visible() is False
    assert adapter._campaign_context.auto_search_combat_generation == 11
    backend.buttons["buttons"] = [make_button("ButtonExit", "OverlayCamera/Overlay/UIMain/"
        "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit")]
    backend.buttons["button_count"] = 1
    backend.ui["toggles"] = []
    backend.ui["toggle_count"] = 0
    for projection in (backend.snapshot, backend.buttons, backend.ui):
        projection["generation"] = 12
    assert adapter.campaign_auto_search_result_visible() is True
    proof = adapter._campaign_context.auto_search_completion
    assert proof.combat_auto_generation == 11
    assert proof.result_generation == 12
    assert proof.result_exit_receipt is None
    assert backend.taps == []
