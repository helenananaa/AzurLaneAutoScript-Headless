import textwrap
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from alas_headless import SemanticGateClosed, AlasSemanticAdapter
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_image, make_oracle, make_ui, make_text
from tests.semantic_support.adapter_fixtures import FakeOracle, NamedButton


LOCK = "OverlayCamera/Overlay/UIMain/top/LevelStageView(Clone)/right_stage/event/collapse/lock_fleet"


def test_typed_ambush_notices_do_not_guess_unknown_or_conflicting_results():
    path = "OverlayCamera/Overlay/UIOverlay/TipPanel(Clone)/Grid/toolTip(Clone)/Text"
    backend = FakeBackend([])
    for text, expected in (("<color=white>规避成功</color>", "success"), ("规避失败", "failed"), ("其他通知", "unknown")):
        backend.ui = make_ui([make_text(text, path)])
        assert make_oracle(backend).campaign_ambush_notice() == expected
    backend.ui = make_ui([make_text("规避成功", path), make_text("规避失败", path)])
    with pytest.raises(SemanticGateClosed, match="conflict"):
        make_oracle(backend).campaign_ambush_notice()


@pytest.mark.parametrize("selected", [True, False])
def test_fleet_lock_uses_exact_live_sprite_and_top_target(selected):
    backend = FakeBackend([make_button("lock_fleet", LOCK)])
    backend.ui = make_ui([], images=[make_image(LOCK, "auto_battle_on" if selected else "auto_battle_off")])
    oracle = make_oracle(backend)
    assert oracle.campaign_fleet_lock_selected() is selected
    oracle.click_campaign_fleet_lock(selected)
    assert len(backend.taps) == 1
    with pytest.raises(SemanticGateClosed, match="changed"):
        oracle.click_campaign_fleet_lock(not selected)
    backend.buttons["buttons"][0]["raycast_top"] = None
    with pytest.raises(SemanticGateClosed, match="actionable"):
        oracle.click_campaign_fleet_lock(selected)
    assert len(backend.taps) == 1


def test_ambush_refuses_orphan_target_from_a_different_root():
    root = "root/LevelAmbushView(Clone)"
    backend = FakeBackend([make_button("LevelAmbushView(Clone)", root),
                           make_button("fight_button", "another/LevelAmbushView(Clone)/window/fight_button")])
    with pytest.raises(SemanticGateClosed, match="ambiguous"):
        make_oracle(backend).click_campaign_ambush(evade=False)
    assert not backend.taps

    # A Canvas root need not itself carry a Button component.
    backend = FakeBackend([make_button("fight_button", root + "/window/fight_button")])
    oracle = make_oracle(backend)
    assert oracle.campaign_ambush_present()
    oracle.click_campaign_ambush(evade=False)
    assert len(backend.taps) == 1


def test_ambush_requires_postcondition_before_reusing_remaining_budget():
    oracle = FakeOracle()
    oracle.campaign_ambush_visible = lambda **kw: True
    oracle.click_campaign_ambush = lambda **kw: oracle.click_receipt("campaign/ambush/evade")
    adapter = AlasSemanticAdapter(oracle, lambda: None, campaign_combat_budget=2)
    adapter.begin_campaign_pre_sortie("1-1")
    assert not adapter.campaign_combat_committed()
    adapter.handle_campaign_ambush(evade=True)
    assert adapter.campaign_combat_committed()
    assert adapter._campaign_context.combat_receipt is None
    with pytest.raises(SemanticGateClosed, match="postcondition"):
        adapter.handle_campaign_ambush(evade=True)
    assert adapter._action_ledger.remaining("campaign.grid_click") == 1
    oracle.campaign_ambush_present = lambda: False
    generation = adapter._campaign_context.ambush_receipt.generation + 1
    oracle.read_state = lambda: SimpleNamespace(generation=generation)
    adapter.finish_campaign_ambush()
    assert not adapter.campaign_combat_committed()
    adapter.handle_campaign_ambush(evade=False)
    assert adapter._action_ledger.remaining("campaign.grid_click") == 0


def test_fleet_lock_refuses_unchanged_toggle_but_allows_proven_reverse_change():
    oracle = FakeOracle()
    oracle.click_campaign_fleet_lock = lambda expected: oracle.click_receipt("campaign/fleet-lock/" + ("on" if expected else "off"))
    adapter = AlasSemanticAdapter(oracle, lambda: None)
    adapter.begin_campaign_pre_sortie("12-4")
    receipt = adapter.click(NamedButton("FLEET_LOCKED"))
    with pytest.raises(SemanticGateClosed, match="state did not advance"):
        adapter.click(NamedButton("FLEET_LOCKED"))
    oracle.read_state = lambda: SimpleNamespace(generation=receipt.generation + 1)
    assert adapter.click(NamedButton("FLEET_UNLOCKED")).semantic_id.endswith("/off")


def test_ambush_input_bypasses_legacy_defensive_resource_action_mapping():
    from alas_headless.adapter.semantic.session_dispatch import SessionDispatchPorts
    adapter = SimpleNamespace(click=Mock(return_value="typed-receipt"))
    session = SimpleNamespace(refresh_frame=Mock(), open=lambda: adapter)
    button = NamedButton("MAP_AMBUSH_EVADE")
    assert SessionDispatchPorts.click(session, button) == "typed-receipt"
    session.refresh_frame.assert_called_once()
    adapter.click.assert_called_once_with(button)


@pytest.mark.parametrize("outcome", ["success", "failed", "unknown"])
def test_original_evade_loop_owns_result_and_combat_without_pixels(outcome):
    patch = (Path(__file__).resolve().parents[1] / "integration/alas/series/0530-campaign-ambush-flow.patch").read_text(encoding="utf-8")
    section = patch.split("+    def _handle_ambush_evade(self):", 1)[1].split("@@", 1)[0]
    source = "    def _handle_ambush_evade(self):\n" + "\n".join(line[1:] for line in section.splitlines() if line.startswith("+"))
    namespace = {"logger": Mock(), "MAP_AMBUSH_EVADE": object()}
    exec(textwrap.dedent(source), namespace)
    clicks = []
    semantic = SimpleNamespace(campaign_ambush_outcome=lambda: outcome if clicks else None)
    host = SimpleNamespace(device=SimpleNamespace(semantic_adapter=semantic, screenshot=Mock()),
        wait_until_appear=Mock(), handle_info_bar=Mock(),
        appear_then_click=lambda *args, **kw: clicks.append("evade") or True,
        combat_appear=lambda: bool(clicks) and outcome == "unknown",
        combat=Mock(), ensure_no_info_bar=Mock(), fleet_show_index=2,
        image_crop=Mock(side_effect=AssertionError("unexpected pixel access")))
    namespace["_handle_ambush_evade"](host)
    assert clicks == ["evade"]
    assert host.device.screenshot.call_count == 1
    if outcome == "success":
        host.combat.assert_not_called()
    elif outcome == "failed":
        host.combat.assert_called_once_with(expected_end="no_searching", fleet_index=2)
    else:
        host.combat.assert_called_once_with(fleet_index=2)
