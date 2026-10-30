"""Real immutable-frame and task-scope boundaries; controlled transport only."""

from dataclasses import replace

import pytest

from alas_headless import SemanticGateClosed
from alas_headless.adapter import StaleFrameError
from alas_headless.adapter.task_lifecycle import (
    TaskCapabilityUnavailable,
    current_semantic_task,
    semantic_task_scope,
)
from alas_headless.oracle.old_retirement import OldRetirementSelectionUncertain
from tests.semantic_support.old_retirement import build_old_frame_rig


def target(rig):
    cards, rarity = rig.delegate.old_retirement_card_vectors(target_rarity={"N", "R"}, card_limit=14)
    assert len(cards) == len(rarity)
    return next(card for card in cards if card.rarity == "N")


def test_one_selection_invalidates_lease_and_does_not_consume_commit_grant():
    rig = build_old_frame_rig()
    card = target(rig)
    action = rig.delegate.old_retirement_select_card(card)
    assert action.semantic_id.endswith(str(card.instance_id))
    assert len(rig.handle.taps) == 1
    assert rig.invalidated == [True]
    assert rig.delegate.old_retirement_confirmation_pending()
    assert rig.adapter._action_ledger.remaining("retirement.execute") == 1
    assert rig.delegate.match_template_color("SHIP_CONFIRM")
    with pytest.raises(SemanticGateClosed, match="already selected"):
        rig.delegate.old_retirement_select_card(card)
    with pytest.raises(SemanticGateClosed, match="reselect"):
        target(rig)
    assert len(rig.handle.taps) == 1


def test_foreign_card_from_other_observation_cannot_be_selected():
    rig = build_old_frame_rig()
    card = target(rig)
    with pytest.raises(SemanticGateClosed, match="native observation"):
        rig.delegate.old_retirement_select_card(
            replace(card, instance_id=card.instance_id - 1)
        )
    assert not rig.handle.taps


def test_expired_real_frame_refuses_before_dispatch_without_false_uncertainty():
    rig = build_old_frame_rig()
    card = target(rig)
    require = rig.adapter._require_action_grant

    def expire(capability):
        require(capability)
        rig.timer.value += 3_000_000_000

    rig.adapter._require_action_grant = expire
    with pytest.raises(StaleFrameError) as captured:
        rig.delegate.old_retirement_select_card(card)
    assert not isinstance(captured.value, OldRetirementSelectionUncertain)
    assert not rig.handle.taps
    assert rig.oracle.input_dispatch_count == 0
    assert rig.adapter._action_ledger.remaining("retirement.execute") == 1
    rig.delegate.discard_task_state()
    assert rig.delegate.old_retirement_pending_evidence() is None


def test_unknown_selection_is_not_replayed_or_cleared_by_later_empty_frame():
    rig = build_old_frame_rig(transport_unknown=True)
    card = target(rig)
    with pytest.raises(OldRetirementSelectionUncertain):
        rig.delegate.old_retirement_select_card(card)
    assert len(rig.handle.taps) == rig.oracle.input_dispatch_count == 1
    rig.delegate.discard_task_state()
    assert rig.delegate.old_retirement_pending_evidence()["uncertain_selection"]
    for value in (rig.handle.snapshot, rig.handle.buttons, rig.handle.ui):
        value["generation"] += 1
    with pytest.raises(SemanticGateClosed, match="unresolved"):
        rig.delegate._check_old_reentry()
    with semantic_task_scope(rig.delegate, "commission"):
        assert (
            rig.delegate.unrelated_capability_probe()
            == "unrelated capability remains available"
        )
    assert len(rig.handle.taps) == 1


def test_known_cancelled_unsubmitted_selection_can_reenter_from_exact_empty_page():
    rig = build_old_frame_rig()
    card = target(rig)
    rig.delegate.old_retirement_select_card(card)
    rig.delegate.discard_task_state()
    assert rig.delegate.old_retirement_pending_evidence()["selections"]
    with pytest.raises(SemanticGateClosed, match="unresolved"):
        rig.delegate._check_old_reentry()
    # Represents original ALAS cancelling the known accepted selection. This
    # observation change is not an adapter input or a transport replay.
    for value in (rig.handle.snapshot, rig.handle.buttons, rig.handle.ui):
        value["generation"] += 1
    for text in rig.handle.ui["texts"]:
        if text["path"].endswith("/bottom_info/bg_input/count"):
            text["text"] = "0"
    rig.delegate._check_old_reentry()
    assert rig.delegate.old_retirement_pending_evidence() is None
    assert len(rig.handle.taps) == 1


@pytest.mark.parametrize("generation_delta", [0, -1])
def test_empty_selector_must_postdate_the_known_selection(generation_delta):
    rig = build_old_frame_rig()
    rig.delegate.old_retirement_select_card(target(rig))
    rig.delegate.discard_task_state()
    last = rig.delegate.old_retirement_pending_evidence()["selections"][-1].observed_generation
    for value in (rig.handle.snapshot, rig.handle.buttons, rig.handle.ui):
        value["generation"] = last + generation_delta
    for text in rig.handle.ui["texts"]:
        if text["path"].endswith("/bottom_info/bg_input/count"):
            text["text"] = "0"
    with pytest.raises(SemanticGateClosed, match="unresolved" if generation_delta == 0 else "moved backwards"):
        rig.delegate._check_old_reentry()
    assert len(rig.handle.taps) == 1


def test_task_cleanup_retains_plain_selection_evidence_without_input_authority():
    rig = build_old_frame_rig()
    with pytest.raises(SemanticGateClosed):
        with semantic_task_scope(rig.delegate, "main"):
            rig.delegate.old_retirement_select_card(target(rig))
            raise SemanticGateClosed("controlled failure before submission")
    assert current_semantic_task() is None
    assert rig.delegate.last_task_outcome == dict(task="main", outcome="raised")
    assert rig.delegate._old_retirement_batch is None
    assert rig.delegate._old_retirement_dialog is None
    assert rig.clock.current_frame_id is None
    assert rig.delegate.old_retirement_pending_evidence()["selections"]
    with semantic_task_scope(rig.delegate, "research"):
        rig.delegate.refresh_frame()
    assert rig.delegate.last_task_outcome == dict(task="research", outcome="returned")
    assert rig.delegate.last_task_error is None
    assert len(rig.handle.taps) == 1
    assert rig.adapter._action_ledger.remaining("retirement.execute") == 1


def test_zero_grant_refusal_is_task_local_and_never_renews_budget():
    rig = build_old_frame_rig(budget=0)
    with pytest.raises(TaskCapabilityUnavailable):
        with semantic_task_scope(rig.delegate, "main"):
            rig.delegate.old_retirement_select_card(target(rig))
    assert rig.delegate.last_task_outcome == dict(
        task="main", outcome="action-deferred"
    )
    assert rig.delegate.old_retirement_pending_evidence() is None
    with semantic_task_scope(rig.delegate, "commission"):
        assert (
            rig.delegate.unrelated_capability_probe()
            == "unrelated capability remains available"
        )
    assert not rig.handle.taps
    assert rig.adapter._action_ledger.remaining("retirement.execute") == 0


def test_unrelated_additive_records_and_unknown_other_rarity_remain_usable():
    rig = build_old_frame_rig()
    known = target(rig)
    for image in rig.handle.ui["images"]:
        if image["path"].endswith("/content/front/frame") and image["sprite"] in (
            "4",
            "4_0",
        ):
            image["sprite"] = "future-unrelated-rarity"
    for value in (rig.handle.snapshot, rig.handle.buttons, rig.handle.ui):
        value["future_field"] = {"ignored": True}
        value["generation"] += 1
    rig.delegate.old_retirement_select_card(known)
    assert len(rig.handle.taps) == 1
