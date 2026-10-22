"""Official auto-search uses native ALAS combat loops without a manual cell tap."""

from types import SimpleNamespace
from unittest import mock

import pytest

from alas_headless import AlasSemanticAdapter, AlasSemanticSession
from alas_headless.adapter.semantic import session_combat
from alas_headless.semantic_oracle import SemanticGateClosed
from tests.semantic_support.observer_fixtures import (
    FakeBackend, make_button, make_image, make_oracle, make_text, make_ui,
)


PAUSE_PATH = "UICamera/Canvas/UIMain/CombatUIStandard(Clone)/PauseBtn"


def host(buttons=(), texts=(), images=()):
    backend = FakeBackend(list(buttons))
    backend.ui = make_ui(list(texts), images=list(images))
    oracle = make_oracle(backend)
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_campaign_pre_sortie("12-4", mode="normal")
    context = adapter._campaign_context
    context.sortie_receipt = SimpleNamespace(generation=1)
    context.sortie_proof = SimpleNamespace(map_generation=2)
    context.auto_search_role_state = SimpleNamespace(fleet1_role="mob", fleet2_role="boss")
    session = AlasSemanticSession("offline", oracle.fingerprint.driver_revision)
    session.adapter = adapter
    return backend, oracle, adapter, session


@pytest.mark.parametrize("missing", [None, "sortie_receipt", "sortie_proof", "auto_search_role_state"])
def test_official_sortie_owns_combat_ports_only_after_complete_proof(missing):
    _, _, adapter, _ = host()
    if missing is not None:
        setattr(adapter._campaign_context, missing, None)
    assert adapter.campaign_combat_committed() is (missing is None)
    # Official ownership must not manufacture manual movement/combat state.
    assert adapter.campaign_combat_active() is False
    assert adapter._campaign_context.combat_receipt is None
    assert adapter._campaign_context.combat_admission is None


@pytest.mark.parametrize("surface,loading,executing", [
    ("combat", True, True), ("map", False, False), ("precombat", True, False),
    ("loader", True, False), ("result", False, False),
    ("total-result", False, False), ("reconnect", False, False),
    ("reward", False, False),
])
def test_official_native_state_ports_follow_current_owner(surface, loading, executing):
    buttons, texts, images = [], [], []
    if surface in {"combat", "result", "total-result", "reconnect", "reward"}:
        # Retained CombatUI must not win over a topmost reward or prompt.
        buttons.append(make_button("PauseBtn", PAUSE_PATH))
    if surface == "map":
        buttons.append(make_button("map", "LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane"))
    elif surface == "precombat":
        path = "UICamera/Canvas/UIMain/ChapterPreCombatUI(Clone)/right/start"
        buttons.append(make_button("start", path))
        images.append(make_image(path, "start"))
    elif surface == "loader":
        path = "UICamera/Canvas/UIMain/CombatLoadUI(Clone)/loading/loading_label"
        texts.extend((make_text("NOW LOADING...", path), make_text("44.28%", path + "/percent")))
    elif surface == "result":
        buttons.append(make_button("confirmBtn", "OverlayCamera/Overlay/UIMain/"
                                   "NewBattleResultEmptyUI(Clone)/NewBattleResultStatisticsPage(Clone)/bottom/confirmBtn"))
    elif surface == "total-result":
        buttons.append(make_button("ButtonExit", "OverlayCamera/Overlay/UIMain/"
                                   "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit"))
    elif surface == "reconnect":
        buttons.append(make_button("confirm", "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/button_container/confirm"))
    elif surface == "reward":
        buttons.append(make_button("close", "OverlayCamera/Overlay/UIMain/AwardInfoUI(Clone)/items/close"))
    backend, oracle, _, session = host(buttons, texts, images)
    oracle.campaign_is_in_map = mock.Mock(side_effect=AssertionError("combat port must not parse map underlay"))
    session._live_combat_snapshot = mock.Mock(side_effect=AssertionError("current frame owns classification"))
    assert session.combat_is_loading() is loading
    assert session.combat_is_executing() is executing
    if not loading and not executing:
        assert session._live_combat_visible() == ()
    assert backend.taps == []
    oracle.campaign_is_in_map.assert_not_called()
    session._live_combat_snapshot.assert_not_called()


def test_official_combat_ports_use_one_leased_observation_instead_of_live_underlay():
    _, _, adapter, session = host()
    reader = mock.Mock()
    reader.read_state.return_value = object()
    reader._blocking_rules.return_value = ()
    reader.observation_target_present.return_value = False
    reader.observation_surface_present.return_value = False
    reader.daily_combat_visible.return_value = True
    adapter._frame_observation_oracle = lambda: reader
    adapter.oracle.read_state = mock.Mock(side_effect=AssertionError("live observation split the ALAS frame"))
    assert session.combat_is_loading()
    assert session.combat_is_executing()
    adapter.oracle.read_state.assert_not_called()


@pytest.mark.parametrize("proved", [True, False])
def test_live_combat_input_keeps_existing_commit_boundary_for_official_sortie(proved):
    _, _, adapter, session = host()
    if not proved:
        adapter._campaign_context.sortie_proof = None
    receipt = object()
    commit = SimpleNamespace(commit_generation=11, action_name="COMBAT_AUTO_SWITCH", receipt=receipt)
    session._runtime_handle = SimpleNamespace(pid=4242)
    session._live_combat_manifest = mock.Mock(return_value=object())
    with mock.patch.object(session_combat, "commit_alas_combat_resource_action_for_evidence",
                           return_value=commit) as dispatch:
        if proved:
            assert session._live_combat_click("COMBAT_AUTO") is receipt
            assert dispatch.call_count == 1
            assert dispatch.call_args.kwargs["expected_pid"] == 4242
            assert dispatch.call_args.kwargs["action_budget"] == 1
        else:
            with pytest.raises(SemanticGateClosed, match="committed ALAS combat entry"):
                session._live_combat_click("COMBAT_AUTO")
            dispatch.assert_not_called()


def test_stale_official_frame_is_not_hidden_as_a_noncombat_phase():
    backend, _, _, session = host()
    backend.snapshot["age_ms"] = 1_000_000
    with pytest.raises(SemanticGateClosed, match="observer snapshot is stale"):
        session.combat_is_loading()


@pytest.mark.parametrize("retained_combat", [False, True])
def test_native_popup_probes_before_total_menu_do_not_parse_combat_underlay(retained_combat):
    buttons = [make_button("ButtonExit", "OverlayCamera/Overlay/UIMain/"
                           "LevelStageTotalRewardPanel(Clone)/Window/Fixed/ButtonExit")]
    if retained_combat:
        buttons.append(make_button("PauseBtn", PAUSE_PATH))
    backend, _, _, session = host(buttons)
    session._live_combat_snapshot = mock.Mock(side_effect=AssertionError("total reward is not a combat frame"))
    assert session.appear("POPUP_CANCEL") is False
    assert session.appear("POPUP_CONFIRM") is False
    assert backend.taps == []
    session._live_combat_snapshot.assert_not_called()
