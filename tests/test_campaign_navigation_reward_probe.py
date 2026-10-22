"""Generic ALAS navigation can observe absent rewards on the chapter page."""

from unittest.mock import Mock

import pytest

from alas_headless import AlasSemanticAdapter, SemanticGateClosed
from tests.semantic_support.adapter_fixtures import NamedButton
from tests.semantic_support.observer_fixtures import FakeBackend, make_button, make_oracle


ROOT = "UICamera/Canvas/UIMain/LevelMainScene(Clone)"


def chapter_adapter(extra=()):
    backend = FakeBackend([
        make_button("back_button", ROOT + "/top/top_chapter/back_button"),
        *extra,
    ])
    oracle = make_oracle(backend)
    return AlasSemanticAdapter(oracle, lambda: None), oracle, backend


@pytest.mark.parametrize("resource", ["GET_ITEMS_1", "GET_ITEMS_2", "GET_ITEMS_3"])
def test_chapter_navigation_reward_probe_needs_no_mission_or_stage_parser(resource):
    adapter, oracle, backend = chapter_adapter()
    oracle.campaign_page_state = Mock(side_effect=AssertionError("not a stage read"))
    assert adapter.appear(NamedButton(resource)) is False
    with pytest.raises(SemanticGateClosed):
        adapter.click(NamedButton(resource))
    oracle.campaign_page_state.assert_not_called()
    assert backend.taps == []


@pytest.mark.parametrize("covered", [False, True])
def test_unknown_or_covered_page_does_not_prove_reward_absence(covered):
    adapter, _, backend = chapter_adapter([
        make_button("cancel", "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/cancel")
    ] if covered else [])
    if not covered:
        backend.buttons["buttons"] = []
        backend.buttons["button_count"] = 0
    with pytest.raises(SemanticGateClosed):
        adapter.appear(NamedButton("GET_ITEMS_1"))
    assert backend.taps == []


def test_actual_award_overlay_keeps_existing_shared_observation():
    adapter, oracle, backend = chapter_adapter()
    target = oracle._targets["reward/award-info/close"]
    backend.buttons["buttons"].append(make_button(target.name, "root/" + target.path_suffix))
    backend.buttons["button_count"] += 1
    assert adapter.appear(NamedButton("GET_ITEMS_1")) is True
    assert adapter.appear(NamedButton("GET_ITEMS_2")) is False
    assert backend.taps == []


def test_reward_probe_propagates_invalid_shared_button_state():
    adapter, _, backend = chapter_adapter()
    backend.buttons["truncated"] = True
    with pytest.raises(SemanticGateClosed):
        adapter.appear(NamedButton("GET_ITEMS_1"))
    assert backend.taps == []
