"""Opsi state for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Sequence, Tuple
from .contracts import ActionReceipt, ButtonState, OperationSirenState, Point, UiState
from .errors import SemanticGateClosed


class OpsiStateOracle:
    """Opsi state operations sharing the oracle frame and input boundary."""

    def _operation_siren_energy_submission_prompt(self):
        state = self.read_state()
        root = 'OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/'
        choices = [b for b in state.buttons if b.path.startswith(root+'button_container/')]
        if not choices:
            return None
        owners = self._matches(state, 'os/page/back')
        if not owners:
            # The same generic item dialog on a different task has no OpSi
            # authority. Leave that task's classifier in charge.
            return None
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('OpSi item submission snapshots are incoherent')
        def text(suffix):
            values = [t.text.strip() for t in ui.texts if t.path == root+suffix
                      and t.active_in_hierarchy and t.active_and_enabled and not t.truncated]
            if len(values) > 1:
                raise SemanticGateClosed('OpSi item submission text is ambiguous')
            return values[0] if values else None
        if text('item_panel/Text') != '是否提交以下物品?':
            return None
        paths = [root+'button_container/custom_button_'+str(i)+'(Clone)' for i in (1, 2)]
        if len(choices) != 2 or {b.path for b in choices} != set(paths):
            raise SemanticGateClosed('OpSi item submission choices are ambiguous')
        if (''.join((text('button_container/custom_button_1(Clone)/pic') or '').split()) != '确定'
                or ''.join((text('button_container/custom_button_2(Clone)/pic') or '').split()) != '取消'):
            raise SemanticGateClosed('OpSi item submission choice labels are unsupported')
        back = self._unique(state, 'os/page/back')
        if not back.active_in_hierarchy or not back.active_and_enabled:
            raise SemanticGateClosed('OpSi item submission map owner is absent')
        prefix = root+'item_panel/scrollview/list/'
        icons = [i for i in ui.images if i.path.startswith(prefix) and i.path.endswith('/IconTpl/icon_bg/icon')
                 and i.active_in_hierarchy and i.active_and_enabled]
        if (ui.image_truncated or len(icons) != 1 or icons[0].truncated
                or icons[0].sprite != 'jingtidianchi'):
            raise SemanticGateClosed('OpSi item submission energy item is unproven')
        count_suffix = icons[0].path[len(root):-len('icon')]+'count'
        if text(count_suffix) != '1':
            raise SemanticGateClosed('OpSi item submission quantity is unsupported')
        blockers = [b for b in self._blocking_rules(state, 'os/page/back')
                    if b.path_fragment != '/Msgbox(Clone)/']
        if blockers:
            raise SemanticGateClosed('OpSi item submission has another blocker')
        return state, choices, paths

    def operation_siren_energy_submission_prompt_visible(self) -> bool:
        return self._operation_siren_energy_submission_prompt() is not None

    def click_operation_siren_energy_submission(self, *, confirm: bool) -> ActionReceipt:
        prompt = self._operation_siren_energy_submission_prompt()
        if prompt is None:
            raise SemanticGateClosed('OpSi item submission prompt is absent')
        state, choices, paths = prompt
        target = next(b for b in choices if b.path == paths[0 if confirm else 1])
        if (not target.actionable or target.point is None or target.bounds is None
                or not target.bounds.contains(target.point)
                or not 0 <= round(target.point.x) < self.fingerprint.width
                or not 0 <= round(target.point.y) < self.fingerprint.height):
            raise SemanticGateClosed('OpSi item submission confirm is not actionable')
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('foreground changed before OpSi item submission')
        self._tap(round(target.point.x), round(target.point.y))
        receipt = ActionReceipt('os/map/energy-submit/'+('confirm' if confirm else 'cancel'), state.generation,
                                target.point, target.bounds, target.path)
        def completed():
            after = self.read_state()
            if (after.generation <= state.generation or any(
                    b.active_in_hierarchy and '/Msgbox(Clone)/' in b.path for b in after.buttons)):
                raise SemanticGateClosed('OpSi item submission did not dismiss; do not retry')
            back = self._unique(after, 'os/page/back')
            if not back.active_in_hierarchy or not back.active_and_enabled:
                raise SemanticGateClosed('OpSi item submission map did not return')
            return True
        self._retry_transition_read(completed, attempts=20, interval_seconds=0.25)
        return receipt

    def operation_siren_state(self) -> OperationSirenState:
        """Read the stable local-map header without mutating Operation Siren."""

        button_state = self.read_state()
        back = self._unique(button_state, "os/page/back")
        if not (
            back.active_in_hierarchy
            and back.active_and_enabled
            and back.bounds is not None
        ):
            raise SemanticGateClosed("operation siren page identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("operation siren snapshots are not coherent")

        root = "top/adapt/top_stage/"

        def exact_text(path: str) -> str:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(path)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "operation siren text is absent or ambiguous: " + path
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        zone_name = exact_text(root + "title/name")
        coins = exact_text(root + "resources/WorldResPanel(Clone)/res/Whuobi/value")
        action_points = exact_text(
            root + "resources/WorldResPanel(Clone)/res/stamina/value"
        )
        action_capacity = exact_text(
            root + "resources/WorldResPanel(Clone)/res/stamina/max_value"
        )
        beacon = exact_text(
            root + "resources/WorldResPanel(Clone)/res/boss_progress/value"
        )
        daily = exact_text(
            root + "resources/WorldResPanel(Clone)/res/boss_progress/max_value"
        )
        beacon_match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", beacon)
        daily_match = re.fullmatch(r"DAILY:([0-9]+)/([1-9][0-9]*)", daily)
        capacity_match = re.fullmatch(r"MAX:([1-9][0-9]*)", action_capacity)
        if (
            not zone_name
            or re.fullmatch(r"[0-9]+", coins) is None
            or re.fullmatch(r"[0-9]+", action_points) is None
            or capacity_match is None
            or beacon_match is None
            or daily_match is None
        ):
            raise SemanticGateClosed("operation siren resource summary is malformed")

        fleet_prefix = "/top/adapt/left_stage/bg/fleet/"
        levels = tuple(
            int(text.text.strip())
            for text in ui_state.texts
            if fleet_prefix in text.path
            and text.path.endswith("/icon_bg/lv/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]{1,3}", text.text.strip())
        )
        if len(levels) not in range(1, 7):
            raise SemanticGateClosed("operation siren fleet summary is malformed")
        beacon_points, beacon_capacity = map(int, beacon_match.groups())
        daily_points, daily_capacity = map(int, daily_match.groups())
        action_value = int(action_points)
        action_limit = int(capacity_match.group(1))
        # ``MAX`` is the natural-regeneration ceiling, not a hard inventory
        # ceiling: boxes and the weekly oil purchase may legitimately take AP
        # above 200.  Keep the same defensive upper bound as legacy ALAS.
        if (
            action_value > 600
            or beacon_points > beacon_capacity
            or daily_points > daily_capacity
        ):
            raise SemanticGateClosed("operation siren summary is inconsistent")
        return OperationSirenState(
            zone_name=zone_name,
            coins=int(coins),
            action_points=action_value,
            action_point_capacity=action_limit,
            beacon_points=beacon_points,
            beacon_capacity=beacon_capacity,
            daily_beacon_points=daily_points,
            daily_beacon_capacity=daily_capacity,
            fleet_levels=levels,
        )

    def operation_siren_page_visible(self) -> bool:
        """Recognize the typed Operation Siren page shell without side panels."""

        state = self.read_state()
        backs = tuple(
            button
            for button in self._matches(state, "os/page/back")
            if button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        return len(backs) == 1

    def operation_siren_stronghold_percentage(self) -> int:
        """Read the exact Stronghold suppression percentage from WorldMap."""

        button_state = self.read_state()
        back = self._unique(button_state, "os/page/back")
        progress_path = (
            "top/adapt/top_stage/features/status_field/poison_rate"
        )
        progress_buttons = tuple(
            button
            for button in button_state.buttons
            if button.name == "poison_rate"
            and button.path.endswith(progress_path)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if (
            not back.active_in_hierarchy
            or not back.active_and_enabled
            or back.bounds is None
            or len(progress_buttons) != 1
        ):
            raise SemanticGateClosed("operation siren stronghold identity is absent")
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "operation siren stronghold snapshots are not coherent"
            )
        title = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("top/adapt/top_stage/title/name")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r".+-塞壬要塞海域", text.text.strip())
        )
        percentage = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(progress_path + "/bg/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"(?:100|[1-9]?[0-9])%", text.text.strip())
        )
        if len(title) != 1 or len(percentage) != 1:
            raise SemanticGateClosed(
                "operation siren stronghold percentage is absent or ambiguous"
            )
        return int(percentage[0].text.strip().rstrip("%"))

    def operation_siren_local_map_visible(self) -> bool:
        """Recognize the mounted local-map shell without requiring its texts."""

        state = self.read_state()
        order_backs = tuple(
            button
            for button in self._matches(state, "os/order/back")
            if button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if order_backs:
            # The local map remains mounted under SVOrderPanel.  Do not let
            # ALAS accept that background shell as the postcondition of
            # order_quit(), or its next fleet-bar click lands behind the
            # still-blocking order overlay.
            return False
        backs = self._matches(state, "os/page/back")
        fleet_bars = tuple(
            button
            for button in state.buttons
            if button.name == "fleet_bar"
            and button.path.endswith(
                "top/adapt/left_stage/other/fleet_bar"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        return len(backs) == 1 and len(fleet_bars) == 1

    def operation_siren_boss_preparation_visible(self) -> bool:
        """Recognize the exact in-map Siren boss challenge panel."""

        button_state = self.read_state()
        targets = self._matches(button_state, "os/boss/start")
        if len(targets) != 1:
            return False
        target = targets[0]
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "operation siren boss-preparation snapshots are not coherent"
            )
        boss_icons = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(
                "OverlayCamera/Overlay/UIMain/fixed/bossname/name/banner/Type/Icon"
            )
            and image.sprite.startswith("battle_")
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        return len(boss_icons) == 1

    def operation_siren_precombat_visible(self) -> bool:
        """Recognize the exact WorldPreCombatUI used by Siren bosses."""

        button_state = self.read_state()
        starts = self._matches(button_state, "os/precombat/start")
        backs = tuple(
            button
            for button in button_state.buttons
            if button.name == "back_btn"
            and button.path.endswith(
                "WorldPreCombatUI(Clone)/adapt/top/back_btn"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if len(starts) != 1 or len(backs) != 1:
            return False
        start = starts[0]
        if not (
            start.active_in_hierarchy
            and start.active_and_enabled
            and start.interactable
            and start.raycast_top is None
            and start.point is not None
            and start.bounds is not None
            and start.bounds.contains(start.point)
        ):
            return False
        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "operation siren precombat snapshots are not coherent"
            )
        start_images = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(
                "WorldPreCombatUI(Clone)/adapt/right/start"
            )
            and image.sprite == "battle"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        fleet_levels = tuple(
            text
            for text in ui_state.texts
            if "/WorldPreCombatUI(Clone)/adapt/middle/fleet/" in text.path
            and text.path.endswith("/icon_bg/lv/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]{1,3}", text.text.strip())
        )
        return len(start_images) == 1 and 1 <= len(fleet_levels) <= 6

    def operation_siren_precombat_info_visible(self) -> bool:
        """Recognize the one-button first-entry information prompt."""

        if not self.operation_siren_precombat_visible():
            return False
        button_state = self.read_state()
        confirms = self._matches(button_state, "os/precombat/info/confirm")
        cancels = tuple(
            button
            for button in button_state.buttons
            if button.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_2(Clone)"
            )
            and button.active_in_hierarchy
        )
        if len(confirms) != 1 or cancels:
            return False
        confirm = confirms[0]
        if not confirm.actionable:
            return False
        ui_state = self.read_ui_state()
        help_rows = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(
                "Msgbox(Clone)/window/help_panel/list/help_tpl"
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and bool(text.text.strip())
        )
        return len(help_rows) == 1

    def click_operation_siren_precombat_info(self) -> ActionReceipt:
        if not self.operation_siren_precombat_info_visible():
            raise SemanticGateClosed(
                "operation siren precombat information prompt is absent"
            )
        return self.click("os/precombat/info/confirm")

    def click_operation_siren_precombat_start(self) -> ActionReceipt:
        if not self.operation_siren_precombat_visible():
            raise SemanticGateClosed("operation siren precombat is absent")
        if self.operation_siren_precombat_info_visible():
            raise SemanticGateClosed(
                "operation siren precombat information prompt is blocking"
            )
        state = self.read_state()
        target = self._unique(state, "os/precombat/start")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and self._foreground_component() == self.fingerprint.component
        ):
            raise SemanticGateClosed(
                "operation siren precombat start is not actionable"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/precombat/start",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def operation_siren_low_resolve_prompt_visible(self) -> bool:
        """Recognize the exact one-button prompt that forbids another fight."""

        state = self.read_state()
        suffix = (
            "Msgbox(Clone)/window/button_container/custom_button_2(Clone)"
        )
        cancels = tuple(
            button
            for button in state.buttons
            if button.name == "custom_button_2(Clone)"
            and button.path.endswith(suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(cancels) != 1:
            return False
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed(
                "operation siren low-resolve prompt snapshots are not coherent"
            )
        messages = tuple(
            item.text.strip()
            for item in ui_state.texts
            if item.path.endswith("Msgbox(Clone)/window/msg_panel/content")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        return bool(
            len(messages) == 1
            and "舰队士气过低" in messages[0]
            and "无法与强敌战斗" in messages[0]
            and "取得任意战斗胜利均可恢复舰队的士气" in messages[0]
        )

    def click_operation_siren_low_resolve_cancel(self) -> ActionReceipt:
        if not self.operation_siren_low_resolve_prompt_visible():
            raise SemanticGateClosed(
                "operation siren low-resolve prompt is absent"
            )
        state = self.read_state()
        suffix = (
            "Msgbox(Clone)/window/button_container/custom_button_2(Clone)"
        )
        matches = tuple(
            button
            for button in state.buttons
            if button.name == "custom_button_2(Clone)"
            and button.path.endswith(suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "operation siren low-resolve cancel is ambiguous"
            )
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "foreground changed before low-resolve cancellation"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/combat/low-resolve/cancel",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    @staticmethod
    def _operation_siren_current_fleet_from_ui_state(state: UiState) -> int:
        path = (
            "top/adapt/left_stage/other/fleet_bar/text_selected/x"
        )
        matches = tuple(
            item
            for item in state.images
            if item.name == "x"
            and item.path.endswith(path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) != 1 or matches[0].sprite not in {"1", "2", "3", "4"}:
            raise SemanticGateClosed(
                "operation siren current fleet is absent or ambiguous"
            )
        return int(matches[0].sprite)

    def operation_siren_current_fleet(self) -> int:
        """Read the selected Operation Siren fleet from its exact sprite."""

        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        return self._operation_siren_current_fleet_from_ui_state(
            self.read_ui_state()
        )

    def operation_siren_current_fleet_defeated(self) -> bool:
        """Return whether the selected fleet already lost its Month Boss attempt.

        Original ALAS ``FLEET_LOW_RESOLVE`` is a left HUD color check, not a
        map-chibi classifier.  The map ``marks/damage/1`` icon is only a
        post-combat remainder on that fleet's own model; stacked fleets in a
        locked room can show another fleet's mark while walking, so callers
        must not use a one-frame map sample to skip a fresh fleet.
        """

        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        state = self.read_ui_state()
        fleet = self._operation_siren_current_fleet_from_ui_state(state)
        fleet_root = (
            f"/LevelGrid/DragLayer/plane/cells/fleet_{fleet}"
        )
        markers = tuple(
            image
            for image in state.images
            if image.path.endswith(fleet_root + "/marks/damage/1")
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(markers) > 1:
            raise SemanticGateClosed(
                "operation siren selected-fleet low-resolve marker is ambiguous"
            )
        if markers:
            marker = markers[0]
            if marker.name != "1" or marker.sprite != "200":
                raise SemanticGateClosed(
                    "operation siren selected-fleet low-resolve marker is not reviewed"
                )
            return True

        anchors = tuple(
            image
            for image in state.images
            if image.name == "shadow"
            and image.path.endswith(fleet_root + "/shadow")
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(anchors) != 1:
            raise SemanticGateClosed(
                "operation siren selected-fleet map anchor is absent or ambiguous"
            )
        return False

    def operation_siren_current_fleet_needs_repair(self) -> bool:
        """Return whether the selected fleet has a sunk ship in the left panel."""

        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        state = self.read_state()
        pattern = re.compile(
            r".+/top/adapt/left_stage/bg/fleet/(?:main|vanguard)/"
            r"shiptpl\(Clone\)/agony$"
        )
        markers = tuple(
            button
            for button in state.buttons
            if button.name == "agony"
            and pattern.fullmatch(button.path)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(markers) > 6:
            raise SemanticGateClosed(
                "operation siren repair markers are ambiguous"
            )
        signatures = {
            (
                round(marker.bounds.left, 3),
                round(marker.bounds.top, 3),
                round(marker.bounds.right, 3),
                round(marker.bounds.bottom, 3),
            )
            for marker in markers
            if marker.bounds is not None
        }
        if len(signatures) != len(markers):
            raise SemanticGateClosed("operation siren repair markers overlap")
        return bool(markers)

    def operation_siren_auto_search_state(self) -> str:
        """Return the exact local-map auto-search switch state.

        The visible ``off`` control is not proof that auto-search is locked:
        the same Unity button is used for an unlocked switch that the player
        has simply turned off.  Callers may attempt that reviewed button once
        and must use the subsequent state transition, rather than the initial
        appearance, to decide whether the account can start auto-search.
        """

        self.operation_siren_state()
        state = self.read_state()

        def actionable(semantic_id: str) -> bool:
            matches = tuple(
                target
                for target in self._matches(state, semantic_id)
                if target.active_in_hierarchy
                and target.active_and_enabled
                and target.interactable
                and target.point is not None
                and target.bounds is not None
                and target.bounds.contains(target.point)
            )
            if len(matches) > 1:
                raise SemanticGateClosed(
                    "operation siren auto-search state is ambiguous"
                )
            return len(matches) == 1

        enabled = actionable("os/map/auto-search/on")
        disabled = actionable("os/map/auto-search/off")
        if enabled == disabled:
            raise SemanticGateClosed(
                "operation siren auto-search state is absent or inconsistent"
            )
        return "on" if enabled else "off"

    def operation_siren_strategic_search_state(self) -> str:
        """Return ``off``, ``configuring``, or ``on`` from exact Unity controls."""

        state = self.read_state()

        def present(semantic_id: str) -> bool:
            matches = tuple(
                target
                for target in self._matches(state, semantic_id)
                if target.active_in_hierarchy
                and target.active_and_enabled
                and target.interactable
                and target.point is not None
                and target.bounds is not None
                and target.bounds.contains(target.point)
            )
            if len(matches) > 1:
                raise SemanticGateClosed(
                    "operation siren strategic-search state is ambiguous"
                )
            return len(matches) == 1

        confirm = present("os/strategic-search/confirm")
        cancel = present("os/strategic-search/cancel")
        if confirm or cancel:
            if not (confirm and cancel):
                raise SemanticGateClosed(
                    "operation siren strategic-search popup is incomplete"
                )
            return "configuring"

        self.operation_siren_state()
        enabled = present("os/map/strategic-search/on")
        disabled = present("os/map/strategic-search/off")
        if enabled == disabled:
            raise SemanticGateClosed(
                "operation siren strategic-search state is absent or inconsistent"
            )
        return "on" if enabled else "off"

    def operation_siren_strategic_search_scroll_to_bottom(
        self, timeout_seconds: float = 5.0
    ) -> ActionReceipt:
        """Expose the lower strategic-search options through the exact scrollbar."""

        if self._swipe is None:
            raise SemanticGateClosed(
                "operation siren strategic-search swipe backend is absent"
            )
        if self.operation_siren_strategic_search_state() != "configuring":
            raise SemanticGateClosed(
                "operation siren strategic-search popup is absent"
            )
        before = self.read_ui_state()
        handle_suffix = (
            "WorldSwitchPlanningUI(Clone)/window/content/scrollbar/"
            "Sliding Area/Handle"
        )
        handles = tuple(
            image
            for image in before.images
            if image.name == "Handle"
            and image.path.endswith(handle_suffix)
            and image.sprite == "scroll_bar"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and not image.truncated
            and image.bounds is not None
        )
        if len(handles) != 1:
            raise SemanticGateClosed(
                "operation siren strategic-search scrollbar is absent or ambiguous"
            )
        bounds = handles[0].bounds
        assert bounds is not None
        if not (
            898 <= bounds.left < bounds.right <= 915
            and 210 <= bounds.top < bounds.bottom <= 475
        ):
            raise SemanticGateClosed(
                "operation siren strategic-search scrollbar geometry changed"
            )
        start = Point(
            (bounds.left + bounds.right) / 2.0,
            (bounds.top + bounds.bottom) / 2.0,
        )
        end = Point(start.x, 430.0)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "game activity changed before strategic-search scroll"
            )
        self._swipe(
            int(round(start.x)),
            int(round(start.y)),
            int(round(end.x)),
            int(round(end.y)),
            450,
        )
        deadline = self._monotonic() + timeout_seconds
        while self._monotonic() < deadline:
            self._sleep(0.25)
            after = self.read_ui_state()
            matches = self._toggle_matches(
                after, "os/strategic-search/auto-submit/on"
            )
            if len(matches) > 1:
                raise SemanticGateClosed(
                    "operation siren strategic-search auto-submit is ambiguous"
                )
            if len(matches) == 1:
                toggle = matches[0]
                if (
                    after.generation > before.generation
                    and toggle.point is not None
                    and toggle.bounds is not None
                    and toggle.bounds.contains(toggle.point)
                    and 0 <= toggle.point.x < self.fingerprint.width
                    and 0 <= toggle.point.y < self.fingerprint.height
                ):
                    return ActionReceipt(
                        semantic_id="os/strategic-search/scroll/bottom",
                        generation=after.generation,
                        point=end,
                        bounds=toggle.bounds,
                        path=toggle.path,
                    )
        raise SemanticGateClosed(
            "operation siren strategic-search scroll was not proven"
        )

    def operation_siren_auto_search_info_count(self) -> int:
        """Count the exact paired auto-search notifications on the OS map."""

        state = self.read_ui_state()
        path = (
            "OverlayCamera/Overlay/UIOverlay/TipPanel(Clone)/Grid/"
            "toolTip(Clone)/Text"
        )
        reviewed = {
            "<color=white>当前所选舰队开始自律寻敌</color>",
            "<color=white>当前所选舰队视野内无可自律事件，无法继续自律寻敌</color>",
        }
        matches = tuple(
            item
            for item in state.texts
            if item.path.endswith(path)
            and item.text.strip() in reviewed
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        # Repeated start toasts are not the paired no-event notification.
        # ALAS uses count >= 2 to end search, so count distinct reviewed
        # messages rather than pooled duplicate Unity tooltip instances.
        return len({item.text.strip() for item in matches})

    def operation_siren_fleet_lock_state(self) -> str:
        """Read the exact image-only fleet-lock switch state."""

        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        state = self.read_ui_state()
        root = (
            "LevelCamera/Canvas/LevelOrigin/top/adapt/right_stage/btn_list/"
            "auto_switch/"
        )
        matches = tuple(
            item
            for item in state.images
            if item.path in {root + "on", root + "off"}
            and item.name in {"on", "off"}
            and item.sprite in {"auto_switch_on", "auto_switch_off"}
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "operation siren fleet-lock state is absent or ambiguous"
            )
        return matches[0].name

    def click_operation_siren_fleet_lock(self, expected_state: str) -> ActionReceipt:
        """Toggle the image-only fleet lock after proving its exact state."""

        if expected_state not in {"on", "off"}:
            raise SemanticGateClosed("operation siren fleet-lock state is malformed")
        if self.operation_siren_fleet_lock_state() != expected_state:
            raise SemanticGateClosed("operation siren fleet-lock state changed")
        state = self.read_ui_state()
        path = (
            "LevelCamera/Canvas/LevelOrigin/top/adapt/right_stage/btn_list/"
            f"auto_switch/{expected_state}"
        )
        matches = tuple(
            item
            for item in state.images
            if item.path == path
            and item.name == expected_state
            and item.bounds is not None
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(matches) != 1:
            raise SemanticGateClosed("operation siren fleet-lock target changed")
        target = matches[0]
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before fleet-lock input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=f"os/map/fleet-lock/{expected_state}",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_fleet_bar(self) -> ActionReceipt:
        """Open the exact fleet bar whose Unity button has no raycast-top bit."""

        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        last_error: Optional[SemanticGateClosed] = None
        for attempt in range(5):
            state = self.read_state()
            matches = tuple(
                button
                for button in state.buttons
                if button.name == "fleet_bar"
                and button.path.endswith(
                    "top/adapt/left_stage/other/fleet_bar"
                )
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "operation siren fleet bar is absent or ambiguous"
                )
            target = matches[0]
            assert target.point is not None and target.bounds is not None
            ui_state = self.read_ui_state()
            if not state.generation <= ui_state.generation <= state.generation + 2:
                last_error = SemanticGateClosed(
                    "operation siren fleet-bar snapshots are not coherent"
                )
                if attempt < 4:
                    self._sleep(0.3)
                    continue
                raise last_error
            controls = tuple(
                image
                for image in ui_state.images
                if image.name == "fleet_bar"
                and image.path == target.path
                and image.sprite == "btn_switch"
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds == target.bounds
            )
            if len(controls) != 1:
                raise SemanticGateClosed(
                    "operation siren fleet-bar control is absent or ambiguous"
                )
            # Use the exact Unity Button's own event point.  The stronghold layout
            # consumes the whole fleet_bar component even though the legacy CN
            # screenshot asset highlighted only its right-hand decoration.
            point = target.point
            if self._foreground_component() != self.fingerprint.component:
                raise SemanticGateClosed(
                    "foreground changed before fleet-bar input"
                )
            self._tap(int(round(point.x)), int(round(point.y)))
            return ActionReceipt(
                semantic_id="os/map/fleet-selector/open",
                generation=state.generation,
                point=point,
                bounds=target.bounds,
                path=target.path,
            )
        assert last_error is not None
        raise last_error

    def operation_siren_fleet_selector_open(self) -> bool:
        """Return whether the exact four-row fleet selector is mounted."""

        state = self.read_state()
        root = "top/adapt/left_stage/mask/list/"
        expected = {"item", *(f"item ({index})" for index in range(1, 4))}
        matches = {
            button.name
            for button in state.buttons
            if button.name in expected
            and button.path.endswith(root + button.name)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        }
        if matches and matches != expected:
            raise SemanticGateClosed("operation siren fleet selector is incomplete")
        return matches == expected

    def click_operation_siren_fleet_selector(self, fleet_index: int) -> ActionReceipt:
        """Select fleet 1..4 from the exact expanded selector row."""

        if type(fleet_index) is not int or fleet_index not in range(1, 5):
            raise SemanticGateClosed("operation siren fleet index is malformed")
        if not self.operation_siren_fleet_selector_open():
            raise SemanticGateClosed("operation siren fleet selector is closed")
        state = self.read_state()
        suffix = "item" if fleet_index == 1 else f"item ({fleet_index - 1})"
        path = "top/adapt/left_stage/mask/list/" + suffix
        matches = tuple(
            button
            for button in state.buttons
            if button.path.endswith(path)
            and button.name == suffix
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("operation siren fleet selector row changed")
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before fleet selection")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=f"os/map/fleet-selector/{fleet_index}",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_back(self) -> ActionReceipt:
        """Leave the proven local Operation Siren map through its top back."""

        # The original page graph can recognize the map beneath its inventory.
        # Close that exact overlay before the next native page-graph iteration
        # attempts the map edge; never click its covered underlying back.
        if self.operation_siren_storage_visible():
            return self.click_operation_siren_storage_back()
        self.operation_siren_state()
        state = self.read_state()
        target = self._unique(state, "os/page/back")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and not self._blocking_rules(state, "os/page/back")
        ):
            raise SemanticGateClosed("operation siren back is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before operation siren back")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/page/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def operation_siren_reset_fleet_visible(self) -> bool:
        from ..opsi_monthstart import reset_fleet
        return reset_fleet(self) is not None

    def operation_siren_reset_ticket_visible(self) -> bool:
        from ..opsi_monthstart import reset_ticket
        return reset_ticket(self) is not None

    def click_operation_siren_reset_ticket(self) -> ActionReceipt:
        from ..opsi_monthstart import click_reset_ticket
        return click_reset_ticket(self)

    def operation_siren_reset_fleet_ready(self) -> bool:
        from ..opsi_monthstart import reset_fleet_ready
        return reset_fleet_ready(self)

    def click_operation_siren_reset_fleet(self) -> ActionReceipt:
        from ..opsi_monthstart import click_reset_fleet
        return click_reset_fleet(self)

    def operation_siren_map_overlay_present(self) -> bool:
        return bool(self._blocking_rules(self.read_state(), 'os/map/order'))

    @staticmethod
    def _operation_siren_actionable_rows(
        rows: Sequence[ButtonState], width: int, height: int
    ) -> Tuple[ButtonState, ...]:
        return tuple(
            row
            for row in rows
            if row.active_in_hierarchy
            and row.active_and_enabled
            and row.interactable
            and row.raycast_top is None
            and row.point is not None
            and row.bounds is not None
            and row.bounds.contains(row.point)
            and row.bounds.bottom > 0
            and row.bounds.top < height
            and 0 <= row.point.x < width
            and 0 <= row.point.y < height
        )

    def operation_siren_fleet_hp(self) -> Tuple[float, ...]:
        """Read the six visible Operation Siren HP bars in ALAS slot order.

        Operation Siren reuses the campaign HP balancer, but mounts its fleet
        panel below ``left_stage/bg/fleet`` instead of the normal campaign
        hierarchy.  A sunk ship removes its HP fill and mounts the exact
        portrait ``agony`` Button; require exactly one of those two states in
        each of the six ordered portrait slots.
        """

        self.operation_siren_state()
        button_state = self.read_state()
        state = self.read_ui_state()
        suffix = "/left_stage/bg/fleet/"
        portraits = tuple(
            item
            for item in state.images
            if suffix in item.path
            and item.path.endswith("/icon_bg/icon")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        bars = tuple(
            item
            for item in state.images
            if suffix in item.path
            and item.path.endswith("/blood/fillarea/green")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        agony_pattern = re.compile(
            r".+/top/adapt/left_stage/bg/fleet/(?:main|vanguard)/"
            r"shiptpl\(Clone\)/agony$"
        )
        agony = tuple(
            item
            for item in button_state.buttons
            if item.name == "agony"
            and agony_pattern.fullmatch(item.path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.point is not None
            and item.bounds is not None
            and item.bounds.contains(item.point)
        )
        if len(portraits) != 6:
            raise SemanticGateClosed(
                "Operation Siren fleet portraits are absent or incomplete"
            )
        ordered = tuple(sorted(portraits, key=lambda item: item.bounds.top))
        top_values = tuple(item.bounds.top for item in ordered)
        if any(
            not 95.0 <= later - earlier <= 105.0
            for earlier, later in zip(top_values, top_values[1:])
        ):
            raise SemanticGateClosed("Operation Siren fleet HP slot order is invalid")
        full_width = 66.333
        values = []
        for portrait in ordered:
            assert portrait.bounds is not None
            slot_bars = tuple(
                item
                for item in bars
                if item.bounds is not None
                and abs(item.bounds.top - (portrait.bounds.top + 79.8)) <= 5.0
            )
            slot_agony = tuple(
                item
                for item in agony
                if item.bounds is not None
                and abs(item.bounds.top - (portrait.bounds.top - 3.334)) <= 5.0
            )
            if bool(slot_bars) == bool(slot_agony) or len(slot_bars) > 1 or len(slot_agony) > 1:
                raise SemanticGateClosed(
                    "Operation Siren fleet HP slot state is absent or ambiguous"
                )
            if slot_agony:
                values.append(0.0)
            else:
                bar = slot_bars[0]
                assert bar.bounds is not None
                values.append(
                    max(
                        0.0,
                        min(1.0, (bar.bounds.right - bar.bounds.left) / full_width),
                    )
                )
        return tuple(values)

    def operation_siren_need_repair(self) -> Tuple[bool, ...]:
        """Return exact repair requirements for the six visible ships."""

        return tuple(value == 0.0 for value in self.operation_siren_fleet_hp())

    def operation_siren_low_resolve_visible(self) -> bool:
        """Read the exact low-resolve marker beside the selected map fleet."""

        return self.operation_siren_current_fleet_defeated()
