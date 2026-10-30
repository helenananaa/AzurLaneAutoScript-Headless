"""Typed observation and one-input ports; original ALAS owns selection."""

import time
from .contracts import ActionReceipt, Point
from .errors import SemanticGateClosed
from .old_retirement_contracts import OldRetirementCard, OldRetirementSelectionReceipt


def read_old_retirement_cards(oracle, *, card_limit=None):
    """Read exactly the retirement selector through existing typed Dock parsers."""
    selection = oracle.retirement_selection_state()
    state, ui = oracle._retirement_records()
    if not state.generation <= selection.generation <= ui.generation:
        raise SemanticGateClosed("old retirement selector frame changed")
    base = oracle.enhancement_dock_candidates()
    if card_limit is not None:
        if type(card_limit) is not int or card_limit <= 0:
            raise SemanticGateClosed("old retirement native card count is invalid")
        # Native ALAS supplies its logical scan size. Count disabled typed slot
        # positions too, so they cannot pull extra third-row candidates in.
        prefix = "UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/ships/"
        slots = sorted(
            (button for button in state.buttons
             if button.path.startswith(prefix)
             and "/" not in button.path[len(prefix):]
             and button.active_in_hierarchy
             and button.bounds is not None and button.bounds.top >= 0
             and button.bounds.left >= 0
             and button.bounds.right <= oracle.fingerprint.width
             and button.bounds.bottom <= oracle.fingerprint.height + 20),
            key=lambda button: (button.bounds.top, button.bounds.left),
        )
        positions = {button.bounds for button in slots[:card_limit]}
        base = tuple(item for item in base
                     if item.button.bounds in positions)
    frames = {"1": "N", "2": "R", "3": "SR", "4": "SSR", "4_0": "SSR"}
    result = []
    seen_instances = set()
    for item in base:
        target = item.button
        instance = target.raw.get("instance_id")
        if type(instance) is not int or instance == 0 or instance in seen_instances:
            raise SemanticGateClosed("old retirement card instance is ambiguous")
        seen_instances.add(instance)
        assert target.bounds is not None and target.point is not None
        if not (
            0 <= target.point.x < oracle.fingerprint.width
            and 0 <= target.point.y < oracle.fingerprint.height
        ):
            continue

        def belongs(image):
            bounds = image.bounds
            return bounds is not None and target.bounds.contains(
                Point(
                    (bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2
                )
            )

        rarity = [
            image
            for image in ui.images
            if image.path == target.path + "/content/front/frame"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and belongs(image)
        ]
        if len(rarity) != 1:
            raise SemanticGateClosed("old retirement card rarity is incomplete")
        # Unknown/PR/META rarity is unselectable, like the original unknown
        # color branch, without rejecting unrelated known card observations.
        result.append(
            OldRetirementCard(
                item.ship_id,
                instance,
                item.ship_name,
                item.level,
                frames.get(rarity[0].sprite),
                target,
            )
        )
    return selection, state, tuple(result)


def resolve_old_retirement_target(oracle, expected, target_rarity, selected_count, *, card_limit=None):
    """Prepare one native select click; no tap or confirmation occurs here."""
    selection, state, cards = read_old_retirement_cards(oracle, card_limit=card_limit)
    if selection.selected_count != selected_count:
        raise SemanticGateClosed("old retirement selection changed")
    matches = [
        card
        for card in cards
        if card.instance_id == expected.instance_id
        and card.template_id == expected.template_id
        and card.name == expected.name
        and card.level == expected.level
        and card.rarity == expected.rarity
    ]
    if len(matches) != 1 or matches[0].rarity not in target_rarity:
        raise SemanticGateClosed(
            "old retirement target changed or is outside native rarity"
        )
    if oracle._blocking_rules(state, "retirement/ships/select"):
        raise SemanticGateClosed("old retirement selection is blocked")
    if oracle._foreground_component() != oracle.fingerprint.component:
        raise SemanticGateClosed("foreground changed before retirement selection")
    return matches[0].button


class OldRetirementSelectionUncertain(SemanticGateClosed):
    """A tap was attempted; never select again to recover an unknown result."""

    def __init__(self, action_intent, message):
        super().__init__(message)
        self.action_intent = action_intent
        self.input_outcome_uncertain = True
        self.dispatch_attempted = True


def select_one_old_retirement_card(
    fresh_oracle,
    expected,
    target_rarity,
    selected_count,
    *,
    require_retirement_grant,
    card_limit=None,
    timeout_seconds=10.0,
    monotonic=time.monotonic,
    sleep=time.sleep,
):
    """Exact observation/input boundary for ONE native-selected card only."""
    oracle = fresh_oracle()
    before, state, _ = read_old_retirement_cards(oracle, card_limit=card_limit)
    target = resolve_old_retirement_target(
        oracle, expected, target_rarity, selected_count, card_limit=card_limit
    )
    # Selection must not be started when the following retirement submission
    # has no grant. No grant is consumed here: no ship was retired by a select.
    require_retirement_grant()
    point, bounds = target.point, target.bounds
    if (
        not target.actionable
        or point is None
        or bounds is None
        or not bounds.contains(point)
        or not (
            0 <= point.x < oracle.fingerprint.width
            and 0 <= point.y < oracle.fingerprint.height
        )
    ):
        raise SemanticGateClosed("old retirement card is not actionable")
    if oracle._foreground_component() != oracle.fingerprint.component:
        raise SemanticGateClosed("foreground changed before old retirement input")
    intent = ActionReceipt(
        semantic_id="retirement/card/select/" + str(expected.instance_id),
        generation=state.generation,
        point=point,
        bounds=bounds,
        path=target.path,
    )
    dispatched_before = oracle.input_dispatch_count
    try:
        oracle._tap(int(round(point.x)), int(round(point.y)))
        if oracle._foreground_component() != oracle.fingerprint.component:
            raise SemanticGateClosed("foreground changed after old retirement input")
        deadline = monotonic() + timeout_seconds
        while monotonic() < deadline:
            after_oracle = fresh_oracle()
            after = after_oracle.retirement_selection_state()
            after_state = after_oracle.read_state()
            if after_state.snapshot["pid"] != state.snapshot["pid"]:
                raise SemanticGateClosed(
                    "runtime changed after old retirement selection"
                )
            if (after.capacity_used, after.capacity_total) != (
                before.capacity_used,
                before.capacity_total,
            ):
                raise SemanticGateClosed(
                    "dock usage changed while only selecting retirement card"
                )
            if after.generation > intent.generation:
                if after.selected_count == selected_count + 1:
                    return OldRetirementSelectionReceipt(
                        action=intent,
                        pid=state.snapshot["pid"],
                        template_id=expected.template_id,
                        instance_id=expected.instance_id,
                        count_before=selected_count,
                        count_after=after.selected_count,
                        capacity_used=after.capacity_used,
                        observed_generation=after.generation,
                    )
                if after.selected_count != selected_count:
                    raise SemanticGateClosed(
                        "retirement selection delta is not exactly one"
                    )
            sleep(0.05)
        raise SemanticGateClosed(
            "old retirement selection postcondition did not advance"
        )
    except BaseException as exc:
        if oracle.input_dispatch_count == dispatched_before:
            # Preflight/lease refusal happened before transport. Preserve its
            # explicit zero-input classification instead of manufacturing an
            # unknown dispatch or requiring unnecessary selection recovery.
            raise
        # The candidate has no retry-input path, including transport errors.
        # A retained intent records uncertainty, not a confirmed accepted tap.
        raise OldRetirementSelectionUncertain(intent, str(exc)) from exc
