"""Rewards for the typed ALAS boundary."""

from __future__ import annotations

import math
import re
from typing import Optional, Tuple
from .contracts import ActionReceipt, ButtonState, OracleState
from .errors import SemanticGateClosed


class RewardsOracle:
    """Rewards operations sharing the oracle frame and input boundary."""

    def reward_summary_count(self, section: str, counter: str) -> int:
        """Read one exact non-negative counter from the reward side panel."""

        return self._retry_transition_read(
            lambda: self._reward_summary_count_once(section, counter)
        )

    def reward_resource_amount(self, resource: str) -> int:
        """Read the exact positive collectible amount for one reward resource."""

        amount, _, _ = self._retry_transition_read(
            lambda: self._reward_resource_state_once(resource)
        )
        return amount

    def reward_resource_available(self, resource: str) -> bool:
        """Return true only when the exact resource bubble carries an amount."""

        return self.reward_resource_amount(resource) > 0

    def _reward_resource_state_once(
        self, resource: str
    ) -> Tuple[int, Optional[ButtonState], OracleState]:
        resources = {
            "oil": (
                "reward/resource/oil",
                "canteen",
                "icon_oil",
            ),
            "coin": (
                "reward/resource/coin",
                "merchant",
                "icon_gold",
            ),
            "exp": (
                "reward/resource/exp",
                "class",
                "icon_class",
            ),
        }
        try:
            semantic_id, root_name, root_sprite = resources[resource]
        except KeyError as exc:
            raise SemanticGateClosed("reward resource is not mapped") from exc

        button_state = self.read_state()
        page = self._unique(button_state, "reward/page/back")
        if not page.actionable or self._blocking_rules(
            button_state, "reward/page/back"
        ):
            raise SemanticGateClosed("reward resource page identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.image_truncated
            or ui_state.method_mask & 0x8 == 0
        ):
            raise SemanticGateClosed("reward resource snapshots are incomplete")

        target_matches = self._matches(button_state, semantic_id)
        if len(target_matches) > 1:
            raise SemanticGateClosed("reward resource bubble is ambiguous")
        bubble_root = (
            "CommissionInfoUI4Mellow(Clone)/frame/resources/"
            + root_name
            + "/bubble"
        )
        text_matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(bubble_root + "/Text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(text_matches) > 1:
            raise SemanticGateClosed("reward resource amount is ambiguous")
        if target_matches:
            target = target_matches[0]
            if not target.actionable or self._blocking_rules(button_state, semantic_id):
                raise SemanticGateClosed("reward resource bubble is not actionable")
            if len(text_matches) != 1:
                raise SemanticGateClosed("reward resource amount is absent")
            value = text_matches[0].text.strip()
            if re.fullmatch(r"[1-9][0-9]*", value) is None:
                raise SemanticGateClosed("reward resource amount is malformed")
            return int(value), target, button_state

        # A resource with no accumulated amount omits both its bubble Button
        # and text.  Admit that zero only when the exact resource card remains
        # present in a complete typed Image snapshot.
        if text_matches:
            raise SemanticGateClosed("reward resource has text without its bubble")
        root_path = (
            "CommissionInfoUI4Mellow(Clone)/frame/resources/" + root_name
        )
        roots = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(root_path)
            and image.name == root_name
            and image.sprite == root_sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(roots) != 1:
            raise SemanticGateClosed("reward resource zero state is not proven")
        return 0, None, button_state

    def click_reward_resource(self, resource: str) -> ActionReceipt:
        """Claim one non-zero resource bubble after re-proving its amount."""

        amount, target, state = self._retry_transition_read(
            lambda: self._reward_resource_state_once(resource)
        )
        if amount <= 0 or target is None:
            raise SemanticGateClosed("reward resource has no collectible amount")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before reward resource input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id={
                "oil": "reward/resource/oil",
                "coin": "reward/resource/coin",
                "exp": "reward/resource/exp",
            }[resource],
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _reward_summary_count_once(self, section: str, counter: str) -> int:
        """Read one exact reward-summary generation."""

        section_names = {
            "commission": "event",
            "tactical": "class",
            "research": "technology",
        }
        if section not in section_names:
            raise SemanticGateClosed("reward summary section is not mapped")
        if counter not in ("finished", "ongoing", "leisure"):
            raise SemanticGateClosed("reward summary counter is not mapped")

        button_state = self.read_state()
        page = self._unique(button_state, "reward/page/back")
        if not page.actionable or self._blocking_rules(
            button_state, "reward/page/back"
        ):
            raise SemanticGateClosed("reward summary page identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("reward summary snapshots are not coherent")
        suffix = (
            "CommissionInfoUI4Mellow(Clone)/frame/main/content/"
            + section_names[section]
            + "/frame/counter/"
            + counter
            + "/Text"
        )
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) > 1:
            raise SemanticGateClosed("reward summary counter is ambiguous")
        if matches:
            if re.fullmatch(r"[0-9]+", matches[0].text) is None:
                raise SemanticGateClosed("reward summary counter is malformed")
            return int(matches[0].text)

        # The pinned page omits both the label Image and Text for zero-valued
        # counters.  Treat that closed-world omission as zero only after the
        # exact section frame and a complete Image snapshot are proven.
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed reward Image snapshot is incomplete")
        section_path = (
            "CommissionInfoUI4Mellow(Clone)/frame/main/content/"
            + section_names[section]
            + "/frame"
        )
        frame_sprites = {
            "commission": "frame_event",
            "tactical": "frame_class",
            "research": "frame_tech",
        }
        frames = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(section_path)
            and image.sprite == frame_sprites[section]
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        label_sprites = {
            "finished": "label_finish",
            "ongoing": "label_ongoing",
            "leisure": "label_freedom",
        }
        labels = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(suffix[: -len("/Text")])
            and image.sprite == label_sprites[counter]
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(frames) != 1 or labels:
            raise SemanticGateClosed("reward summary zero counter is not proven")
        return 0

    def battle_pass_reward_available(self) -> bool:
        """Read the exact active Battle Pass notice on the reward summary."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("Battle Pass reward snapshots are not coherent")
        page = self._matches(state, "reward/page/back")
        entrance = self._matches(state, "reward/battle-pass/enter")
        if len(page) != 1 or len(entrance) != 1:
            return False
        target = entrance[0]
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "reward/battle-pass/enter")
        ):
            return False
        tip_path = target.path + "/tip"
        tips = tuple(
            image
            for image in ui_state.images
            if image.path == tip_path
            and image.name == "tip"
            and image.sprite == "exclamation_mark"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(tips) > 1:
            raise SemanticGateClosed("Battle Pass reward notice is ambiguous")
        return len(tips) == 1

    def click_battle_pass_entrance(self) -> ActionReceipt:
        """Open Battle Pass through its exact delegated reward-summary card."""

        if not self.battle_pass_reward_available():
            raise SemanticGateClosed("Battle Pass reward is not available")
        state = self.read_state()
        target = self._unique(state, "reward/battle-pass/enter")
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="reward/battle-pass/enter",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def battle_pass_page_visible(self) -> bool:
        """Require the exact current World Cruise award page."""

        state = self.read_state()
        award_tabs = tuple(
            button
            for button in state.buttons
            if button.path.endswith("WorldCruiseUI(Clone)/frame/toggles/award")
            and button.name == "award"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(award_tabs) > 1:
            raise SemanticGateClosed("Battle Pass page identity is ambiguous")
        if not award_tabs:
            # This predicate is also used to classify unrelated ALAS page
            # probes.  Avoid reading a second, independently advancing UI
            # endpoint unless the exact World Cruise award control makes this
            # a Battle Pass candidate.  High-churn combat/result surfaces may
            # otherwise produce harmless generation skew here.
            return False

        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("Battle Pass page snapshots are not coherent")
        roots = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("/WorldCruiseUI(Clone)")
            and image.name == "WorldCruiseUI(Clone)"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        selected = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(
                "WorldCruiseUI(Clone)/frame/toggles/award/selected"
            )
            and image.sprite == "toggle_bg"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        titles = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("WorldCruiseUI(Clone)/top/title/Text/en")
            and text.text.strip() == "W O R L D  C R U I S E"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        if (
            len(roots) > 1
            or len(selected) > 1
            or len(titles) > 1
        ):
            raise SemanticGateClosed("Battle Pass page identity is ambiguous")
        return len(roots) == len(award_tabs) == len(selected) == len(titles) == 1

    def battle_pass_claim_all_available(self) -> bool:
        """Admit only the ordinary claim-all button with its active notice."""

        if not self.battle_pass_page_visible():
            return False
        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("Battle Pass claim snapshots are not coherent")
        matches = self._matches(state, "battle-pass/claim-all")
        if len(matches) != 1:
            return False
        target = matches[0]
        tips = tuple(
            image
            for image in ui_state.images
            if image.path == target.path + "/Image"
            and image.name == "Image"
            and image.sprite == "tip"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(tips) > 1:
            raise SemanticGateClosed("Battle Pass claim notice is ambiguous")
        return bool(
            len(tips) == 1
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "battle-pass/claim-all")
        )

    def click_battle_pass_claim_all(self) -> ActionReceipt:
        """Claim currently unlocked rewards without touching the paid-pass control."""

        if not self.battle_pass_claim_all_available():
            raise SemanticGateClosed("Battle Pass claim-all reward is unavailable")
        state = self.read_state()
        target = self._unique(state, "battle-pass/claim-all")
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="battle-pass/claim-all",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_battle_pass_home(self) -> ActionReceipt:
        """Leave World Cruise through its exact top-right home control."""

        if not self.battle_pass_page_visible():
            raise SemanticGateClosed("Battle Pass page identity is absent")
        state = self.read_state()
        target = self._unique(state, "battle-pass/home")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "battle-pass/home")
        ):
            raise SemanticGateClosed("Battle Pass home is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="battle-pass/home",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _new_ship_reward_visible_in_state(self, state: OracleState) -> bool:
        """Prove the typed, topmost NewShipUI acquisition page."""

        matches = self._matches(state, "reward/new-ship/continue")
        if len(matches) > 1:
            raise SemanticGateClosed("new-ship continue target is ambiguous")
        if not matches:
            return False
        target = matches[0]
        bounds = target.bounds
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or bounds is None
            or target.point is None
            or not math.isclose(bounds.left, 0.0, abs_tol=0.01)
            or not math.isclose(bounds.top, 0.0, abs_tol=0.01)
            or not math.isclose(
                bounds.right, float(self.fingerprint.width), abs_tol=0.01
            )
            or not math.isclose(
                bounds.bottom, float(self.fingerprint.height), abs_tol=0.01
            )
            or self._blocking_rules(state, "reward/new-ship/continue")
        ):
            return False

        ui_state = self.read_ui_state()
        # A full NewShipUI tree is substantially larger than its companion
        # Button snapshot.  On the observed client, the sequential observer
        # reads can span four monotonically increasing generations while both
        # still prove this exact same click layer and typed identity.
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 4
        ):
            raise SemanticGateClosed("new-ship snapshots are not coherent")

        dialogue_background = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("NewShipUI(Clone)/shake_panel/dialogue/bg")
            and image.sprite == "liaotian04"
            and image.active_in_hierarchy
            and image.active_and_enabled
        )
        # On the current CN client, the observer can associate an unrelated
        # child Image sprite with the full-screen ``click`` Button while the
        # Button itself remains the exact actionable target.  Use the unique
        # same-page dialogue background as the companion visual identity
        # instead of trusting that lossy Image association.  The exact Button
        # path, its full-screen bounds, and the typed name/type/dialogue proof
        # below remain mandatory.
        if target.raycast_top is not True and len(dialogue_background) != 1:
            return False
        if len(dialogue_background) > 1:
            raise SemanticGateClosed("new-ship dialogue background is ambiguous")

        root = "NewShipUI(Clone)/shake_panel/"

        def exact_text(suffix: str) -> Optional[str]:
            candidates = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(root + suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(candidates) > 1:
                raise SemanticGateClosed("new-ship text identity is ambiguous")
            if not candidates:
                return None
            value = candidates[0].text.strip()
            return value or None

        display_name = exact_text("ship_type/name_bg/mask/Text")
        dialogue_name = exact_text("dialogue/bg/name")
        ship_type = exact_text("dialogue/bg/type")
        dialogue = exact_text("dialogue/Text")
        return bool(
            display_name
            and dialogue_name
            and display_name == dialogue_name
            and ship_type
            and dialogue
        )

    def _new_ship_reward_action_state(self) -> OracleState:
        """Read a settled, actionable NewShipUI state immediately before input.

        The client can publish the full-screen click Button one observer frame
        before the companion typed UI tree.  Preserve every identity check, but
        retry the complete read-only proof while that transition settles so an
        already-proven construction result does not abort before its sole
        acknowledgement input.
        """

        def reader() -> OracleState:
            state = self.read_state()
            if not self._new_ship_reward_visible_in_state(state):
                raise SemanticGateClosed("new-ship reward identity is not proven")
            return state

        return self._retry_transition_read(reader)

    def new_ship_reward_visible(self) -> bool:
        """Return whether a safely actionable ship-acquisition page is present."""

        return self._retry_transition_read(
            lambda: self._new_ship_reward_visible_in_state(self.read_state())
        )

    def new_ship_reward_page_visible(self) -> bool:
        """Return whether an active typed NewShipUI page owns the foreground.

        This is deliberately weaker than :meth:`new_ship_reward_visible`: it
        exists only for negative queue probes while the client is publishing a
        new-ship result.  It never authorizes the full-screen acknowledgement
        input, which continues to require the complete name/type/dialogue
        proof above.
        """

        def reader() -> bool:
            state = self.read_state()
            roots = tuple(
                button
                for button in state.buttons
                if button.active_in_hierarchy
                and button.active_and_enabled
                and "/NewShipUI(Clone)/shake_panel/" in button.path
            )
            page_roots = {
                button.path.split("/NewShipUI(Clone)/", 1)[0]
                + "/NewShipUI(Clone)"
                for button in roots
            }
            if len(page_roots) > 1 or len({button.path for button in roots}) > 32:
                raise SemanticGateClosed("new-ship result page identity is ambiguous")
            return bool(roots)

        return self._retry_transition_read(reader)

    def award_info_page_visible(self) -> bool:
        """Return whether the typed AwardInfo result hierarchy owns the page.

        This intentionally proves only page ownership, not its close action:
        the close Button can appear one observer turn after the result canvas.
        """

        def reader() -> bool:
            state = self.read_state()
            roots = tuple(
                button
                for button in state.buttons
                if button.active_in_hierarchy
                and button.active_and_enabled
                and "/AwardInfoUI(Clone)/" in button.path
            )
            if len({button.path for button in roots}) > 32:
                raise SemanticGateClosed("award-info page identity is ambiguous")
            return bool(roots)

        return self._retry_transition_read(reader)
