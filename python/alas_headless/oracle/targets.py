"""Targets for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Any, Optional, Tuple
from .contracts import (
    ActionReceipt,
    BlockerRule,
    Bounds,
    ButtonState,
    ImageState,
    OracleState,
    Point,
    SemanticImageTarget,
    SemanticTarget,
    SemanticToggleTarget,
    ToggleState,
    UiState,
)
from .errors import SemanticGateClosed, SemanticTargetMissing


class TargetsOracle:
    """Targets operations sharing the oracle frame and input boundary."""

    def _mapping(self, semantic_id: str) -> SemanticTarget:
        try:
            return self._targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic target is not mapped: {0}".format(semantic_id)
            ) from exc

    def _image_mapping(self, semantic_id: str) -> SemanticImageTarget:
        try:
            return self._image_targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic image target is not mapped: {0}".format(semantic_id)
            ) from exc

    def _toggle_mapping(self, semantic_id: str) -> SemanticToggleTarget:
        try:
            return self._toggle_targets[semantic_id]
        except KeyError as exc:
            raise SemanticGateClosed(
                "semantic toggle target is not mapped: {0}".format(semantic_id)
            ) from exc

    def _toggle_matches(
        self, state: UiState, semantic_id: str
    ) -> Tuple[ToggleState, ...]:
        target = self._toggle_mapping(semantic_id)
        suffixes = (
            target.path_suffix
            if isinstance(target.path_suffix, tuple)
            else (target.path_suffix,)
        )
        candidates = tuple(
            toggle
            for toggle in state.toggles
            if toggle.name == target.name
            and toggle.path.endswith(suffixes)
        )
        if target.expected_child_sprite is None:
            return candidates

        matching = []
        for toggle in candidates:
            if toggle.bounds is None:
                continue
            child_images = tuple(
                image
                for image in state.images
                if not image.truncated
                and image.active_in_hierarchy
                and image.active_and_enabled
                and image.bounds is not None
                and image.sprite == target.expected_child_sprite
                and image.path.startswith(toggle.path + "/")
                and toggle.bounds.contains(
                    Point(
                        (image.bounds.left + image.bounds.right) / 2.0,
                        (image.bounds.top + image.bounds.bottom) / 2.0,
                    )
                )
            )
            if len(child_images) == 1:
                matching.append(toggle)
            elif len(child_images) > 1:
                raise SemanticGateClosed(
                    "semantic toggle child sprite is ambiguous: {0}".format(semantic_id)
                )
        return tuple(matching)

    def toggle_state(self, semantic_id: str) -> ToggleState:
        state = self.read_ui_state()
        if state.method_mask & 0x1 == 0:
            raise SemanticGateClosed("typed Unity Toggle snapshot is incomplete")
        matches = self._toggle_matches(state, semantic_id)
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic toggle target is absent or ambiguous: {0}".format(semantic_id)
            )
        return matches[0]

    def toggle_selected(self, semantic_id: str) -> bool:
        return self.toggle_state(semantic_id).checked

    def toggle_present(self, semantic_id: str) -> bool:
        """Return whether one exact typed Toggle exists on the current UI."""

        state = self.read_ui_state()
        matches = self._toggle_matches(state, semantic_id)
        if len(matches) > 1:
            raise SemanticGateClosed(
                "semantic toggle target is ambiguous: {0}".format(semantic_id)
            )
        return bool(matches)

    def click_toggle(self, semantic_id: str) -> ActionReceipt:
        button_state: Optional[OracleState] = None
        ui_state: Optional[UiState] = None
        for attempt in range(8):
            candidate_buttons = self.read_state()
            candidate_ui = self.read_ui_state()
            if candidate_ui.method_mask & 0x1 == 0:
                raise SemanticGateClosed("typed Unity Toggle snapshot is incomplete")
            if (
                candidate_ui.generation >= candidate_buttons.generation
                and candidate_ui.generation <= candidate_buttons.generation + 2
            ):
                button_state = candidate_buttons
                ui_state = candidate_ui
                break
            if attempt < 7:
                self._sleep(0.05)
        if button_state is None or ui_state is None:
            raise SemanticGateClosed("button and toggle snapshots are not coherent")
        matches = self._toggle_matches(ui_state, semantic_id)
        delegated_build_pool = self._build_pool_delegated_raycast_proven(
            button_state, ui_state, semantic_id
        )
        delegated_guild_nav = self._guild_nav_delegated_raycast_proven(
            button_state,
            ui_state,
            semantic_id,
            matches,
        )
        delegated_campaign_auto = False
        delegated_campaign_event_auto = False
        if semantic_id == "campaign/map-preparation/auto-search" and len(matches) == 1:
            toggle = matches[0]
            standard_toggle_suffix = (
                "LevelStageInfoView(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle"
            )
            delegated_campaign_auto = any(
                button.name == "Toggle"
                and button.path.endswith(standard_toggle_suffix)
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.bounds is not None
                and button.bounds.contains(toggle.point)
                for button in button_state.buttons
            )
            delegated_campaign_event_auto = (
                self._campaign_event_auto_delegated_raycast_proven(
                    button_state,
                    ui_state,
                    toggle,
                )
            )
        strategic_toggle_ids = {
            "os/strategic-search/tab/secured",
            "os/strategic-search/zone-mode/repeat",
            "os/strategic-search/merchant/stop",
            "os/strategic-search/device/stop",
            "os/strategic-search/auto-submit/on",
        }
        strategic_page_buttons = tuple(
            button
            for button in button_state.buttons
            if button.path.endswith(
                (
                "OverlayCamera/Overlay/UIMain/WorldSwitchPlanningUI(Clone)/"
                "window/button_container/custom_button_1",
                "OverlayCamera/Overlay/UIMain/WorldSwitchPlanningUI(Clone)/"
                "window/button_container/custom_button_2",
                )
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        delegated_operation_siren_strategic = bool(
            semantic_id in strategic_toggle_ids
            and len(matches) == 1
            and len(strategic_page_buttons) == 2
            and matches[0].active_in_hierarchy
            and matches[0].active_and_enabled
            and matches[0].interactable
            and matches[0].raycast_top is None
            and matches[0].point is not None
            and matches[0].bounds is not None
            and matches[0].bounds.contains(matches[0].point)
        )
        delegated_shop_nav = False
        if semantic_id == "shop/gift-pack" and len(matches) == 1:
            toggle = matches[0]
            delegated_shop_nav = bool(
                self._recommendation_shop_visible_from_states(
                    button_state, ui_state
                )
                and not toggle.checked
                and toggle.active_in_hierarchy
                and toggle.active_and_enabled
                and toggle.interactable
                and toggle.raycast_top is None
                and toggle.point is not None
                and toggle.bounds is not None
                and toggle.bounds.contains(toggle.point)
            )
        if len(matches) != 1 or (
            not matches[0].actionable
            and not delegated_build_pool
            and not delegated_campaign_auto
            and not delegated_campaign_event_auto
            and not delegated_operation_siren_strategic
            and not delegated_shop_nav
            and not delegated_guild_nav
        ):
            raise SemanticGateClosed("semantic toggle target is not actionable")
        toggle = matches[0]
        if self._blocking_rules(button_state, semantic_id):
            raise SemanticGateClosed("semantic toggle action is blocked")
        assert toggle.point is not None
        assert toggle.bounds is not None
        input_point = toggle.point
        if delegated_campaign_auto:
            controls = tuple(
                button
                for button in button_state.buttons
                if button.name == "Toggle"
                and button.path.endswith(
                    "LevelStageInfoView(Clone)/panel/BottomExtra/LoopGroup/Loop/Toggle"
                )
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.bounds is not None
                and button.bounds.contains(toggle.point)
            )
            if len(controls) != 1:
                raise SemanticGateClosed("campaign auto-search control is ambiguous")
            bounds = controls[0].bounds
            assert bounds is not None
            input_point = Point(
                x=(bounds.left + bounds.right) / 2.0,
                y=(bounds.top + bounds.bottom) / 2.0,
            )
        if not (
            0 <= input_point.x < self.fingerprint.width
            and 0 <= input_point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("semantic toggle target point is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before toggle input")
        self._tap(int(round(input_point.x)), int(round(input_point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after toggle input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=ui_state.generation,
            point=input_point,
            bounds=toggle.bounds,
            path=toggle.path,
        )

    def _image_matches(
        self,
        state: UiState,
        semantic_id: str,
    ) -> Tuple[ImageState, ...]:
        target = self._image_mapping(semantic_id)
        direct_suffix = target.path_parent_suffix + "/Image"
        selected_suffix = target.path_parent_suffix + "/selected/Image"
        allowed_sprites = (target.selected_sprite, target.inactive_sprite)
        return tuple(
            image
            for image in state.images
            if image.name == "Image"
            and (
                image.path.endswith(direct_suffix)
                or image.path.endswith(selected_suffix)
            )
            and image.sprite in allowed_sprites
        )

    def image_state(self, semantic_id: str) -> ImageState:
        return self._retry_transition_read(lambda: self._image_state_once(semantic_id))

    def _image_state_once(self, semantic_id: str) -> ImageState:
        state = self.read_ui_state()
        if state.image_truncated or state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed Unity Image snapshot is incomplete")
        matches = self._image_matches(state, semantic_id)
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic image target is absent or ambiguous: {0}".format(semantic_id)
            )
        if matches[0].truncated:
            raise SemanticGateClosed("semantic image target identity is truncated")
        return matches[0]

    def image_selected(self, semantic_id: str) -> bool:
        target = self._image_mapping(semantic_id)
        image = self.image_state(semantic_id)
        if image.sprite == target.selected_sprite:
            return True
        if image.sprite == target.inactive_sprite:
            return False
        raise SemanticGateClosed("semantic image target sprite is unexpected")

    def click_image(self, semantic_id: str) -> ActionReceipt:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed Unity Image snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("button and image snapshots are not coherent")
        matches = self._image_matches(ui_state, semantic_id)
        if len(matches) != 1:
            raise SemanticGateClosed("semantic image target is absent or ambiguous")
        image = matches[0]
        if (
            image.truncated
            or not image.active_in_hierarchy
            or not image.active_and_enabled
            or not image.raycast_target
            or image.raycast_top is not True
            or image.bounds is None
        ):
            raise SemanticGateClosed("semantic image target is not actionable")
        if semantic_id.startswith("task/nav/"):
            page_semantic_id = "task/page/back"
            page_name = "mission"
        elif semantic_id.startswith("commission/nav/"):
            page_semantic_id = "commission/page/back"
            page_name = "commission"
        else:
            raise SemanticGateClosed("semantic image action has no page identity")
        page_back = self._unique(button_state, page_semantic_id)
        if not page_back.actionable or self._blocking_rules(button_state, semantic_id):
            raise SemanticGateClosed(page_name + " page image action is blocked")
        point = Point(
            (image.bounds.left + image.bounds.right) / 2.0,
            (image.bounds.top + image.bounds.bottom) / 2.0,
        )
        if not image.bounds.contains(point) or not (
            0 <= point.x < self.fingerprint.width
            and 0 <= point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("semantic image target center is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before image input")
        self._tap(int(round(point.x)), int(round(point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after image input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=ui_state.generation,
            point=point,
            bounds=image.bounds,
            path=image.path,
        )

    def _matches(self, state: OracleState, semantic_id: str) -> Tuple[ButtonState, ...]:
        target = self._mapping(semantic_id)
        suffixes = (
            target.path_suffix
            if isinstance(target.path_suffix, tuple)
            else (target.path_suffix,)
        )
        return tuple(
            button
            for button in state.buttons
            if button.name == target.name and button.path.endswith(suffixes)
        )

    def _unique(self, state: OracleState, semantic_id: str) -> ButtonState:
        matches = self._matches(state, semantic_id)
        if not matches:
            raise SemanticTargetMissing(
                "semantic target is absent: {0}".format(semantic_id)
            )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "semantic target mapping is ambiguous: {0}".format(semantic_id)
            )
        return matches[0]

    def _blocking_rules(
        self, state: OracleState, semantic_id: str
    ) -> Tuple[BlockerRule, ...]:
        if semantic_id in (
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
            "overlay/login-data-expired/confirm",
        ):
            # A proven topmost NetworkDown Msgbox intentionally crosses page
            # ownership. Its exact text/labels and top raycast are still
            # required before either button can be considered actionable.
            return ()
        return tuple(
            rule
            for rule in self._blockers
            if semantic_id not in rule.allowed_target_ids
            and not (
                rule.blocker_id == "tactical-dock"
                and (
                    semantic_id.startswith("enhancement/dock/")
                    or semantic_id.startswith("awaken/")
                    or semantic_id.startswith("os/port/dock/")
                    or semantic_id.startswith("gems-farming/dock/")
                    or semantic_id.startswith("retirement/")
                    or semantic_id == "dock/page/back"
                )
            )
            and not (
                rule.blocker_id == "tactical-page"
                and semantic_id.startswith("enhancement/dock/favourite/")
            )
            and not (
                rule.blocker_id == "archive-page"
                and (
                    semantic_id.startswith("archive/category/")
                    or semantic_id.startswith("archive/campaign/")
                )
            )
            and not (
                rule.blocker_id == "campaign-menu"
                and (
                    semantic_id.startswith("archive/category/")
                    or semantic_id.startswith("archive/campaign/")
                )
            )
            and any(
                rule.path_fragment in button.path
                or (
                    # Root-only publication during a remount still blocks its
                    # underlay; a trailing slash must not require a child.
                    rule.path_fragment.endswith("/")
                    and button.active_in_hierarchy
                    and button.active_and_enabled
                    and button.path.endswith(rule.path_fragment[:-1])
                )
                for button in state.buttons
            )
        )

    def _msgbox_prompt_parts(
        self, state: OracleState
    ) -> Optional[Tuple[str, str, str]]:
        ui_state = self._stable_msgbox_ui_state(state)

        def exact_text(suffix: str) -> Optional[str]:
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed("Msgbox text is ambiguous")
            return matches[0].text if matches else None

        content = exact_text("Msgbox(Clone)/window/msg_panel/content")
        cancel = exact_text(
            "Msgbox(Clone)/window/button_container/custom_button_2(Clone)/pic"
        )
        confirm = exact_text(
            "Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic"
        )
        if content is None or cancel is None or confirm is None:
            return None
        return (
            re.sub(r"<[^>]*>", "", content).strip(),
            "".join(cancel.split()),
            "".join(confirm.split()),
        )

    @staticmethod
    def _msgbox_button_signature(state: OracleState) -> Tuple[Any, ...]:
        def point(value: Optional[Point]) -> Optional[Tuple[float, float]]:
            return None if value is None else (value.x, value.y)

        def bounds(
            value: Optional[Bounds],
        ) -> Optional[Tuple[float, float, float, float]]:
            return (
                None
                if value is None
                else (value.left, value.top, value.right, value.bottom)
            )

        return tuple(
            sorted(
                (
                    (
                        button.name,
                        button.path,
                        button.active_in_hierarchy,
                        button.active_and_enabled,
                        button.interactable,
                        button.raycast_top,
                        point(button.point),
                        bounds(button.bounds),
                    )
                    for button in state.buttons
                    if "/Msgbox(Clone)/" in button.path
                ),
                key=repr,
            )
        )

    def _stable_msgbox_ui_state(self, before: OracleState) -> UiState:
        """Sandwich Msgbox text between two identical Button snapshots."""

        before_signature = self._msgbox_button_signature(before)

        def reader() -> UiState:
            ui_state = self.read_ui_state()
            after = self.read_state()
            if not (
                before.generation <= ui_state.generation <= after.generation
                and before.scene_handle == after.scene_handle
                and before_signature == self._msgbox_button_signature(after)
            ):
                raise SemanticGateClosed("Msgbox snapshots are not coherent")
            return ui_state

        # Unity can publish the text slice one observer turn after the modal
        # Button tree during its opening transition.  Repeat only this
        # read-only sandwich; every accepted attempt still has to bind the
        # original exact modal Button signature to its typed text and closing
        # Button snapshot.
        return self._retry_transition_read(reader)

    def _network_reconnect_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        return bool(
            re.fullmatch(
                r"服务器连接失败，是否重新连接？\s*"
                r"\[(?:NetworkDown|HostNotFound|ConnectionReset)\]",
                plain,
            )
            and cancel == "取消"
            and confirm == "确定"
        )

    def _dock_full_prompt_matches(self, state: OracleState) -> bool:
        ui_state = self._stable_msgbox_ui_state(state)
        content = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("Msgbox(Clone)/window/msg_panel/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        labels = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic"
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        buttons = self._matches(state, "overlay/network-reconnect/confirm")
        return bool(
            len(content) == 1
            and content[0].text.strip() == "船坞已满，请前往整理或扩展"
            and len(buttons) == 3
            and sorted("".join(label.text.split()) for label in labels)
            == sorted(("整理", "拓展", "强化"))
        )

    def dock_full_prompt_active(self) -> bool:
        return self._retry_transition_read(
            lambda: self._dock_full_prompt_matches(self.read_state())
        )

    def exists(self, semantic_id: str) -> bool:
        return self._retry_transition_read(lambda: self._exists_once(semantic_id))

    def _exists_once(self, semantic_id: str) -> bool:
        state = self.read_state()
        matches = self._matches(state, semantic_id)
        if semantic_id == "tactical/continue/cancel":
            return bool(matches and self._tactical_continue_prompt_matches(state))
        if semantic_id in (
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
        ):
            return bool(matches and self._network_reconnect_prompt_matches(state))
        if semantic_id == "overlay/login-data-expired/confirm":
            return bool(matches and self._login_data_expired_prompt_matches(state))
        if semantic_id in ("build/warning/cancel", "build/warning/confirm"):
            return bool(matches and self._build_warning_prompt_matches(state))
        if semantic_id in (
            "build/queue/finish-cancel",
            "build/queue/finish-confirm",
        ):
            return bool(matches and self._build_queue_finish_prompt_cost(state) is not None)
        if semantic_id in ("tactical/course/cancel", "tactical/course/confirm"):
            return bool(matches and self._tactical_course_prompt_matches(state))
        if semantic_id in ("research/start/cancel", "research/start/confirm"):
            return bool(matches and self._research_start_prompt_cost(state) is not None)
        if semantic_id in ("research/queue/cancel", "research/queue/confirm"):
            return bool(matches and self._research_queue_prompt_matches(state))
        if semantic_id in ("guild/dispatch/cancel", "guild/dispatch/confirm"):
            return bool(matches and self._guild_dispatch_prompt_matches(state))
        if semantic_id in ("guild/exchange/cancel", "guild/exchange/confirm"):
            return bool(matches and self._guild_exchange_prompt_matches(state))
        return bool(matches)

    def enabled(self, semantic_id: str) -> bool:
        return self._retry_transition_read(lambda: self._enabled_once(semantic_id))

    def _enabled_once(self, semantic_id: str) -> bool:
        state = self.read_state()
        if semantic_id in ("os/order/back", "os/order/scan", "os/order/submarine"):
            if self._operation_siren_order_prompt_mounted(state):
                return False
        if semantic_id == "main/raid":
            return bool(
                self._main_raid_entry_proven(state)
                and not self._blocking_rules(state, semantic_id)
            )
        if semantic_id == "os/boss/start":
            return self.operation_siren_boss_preparation_visible()
        if semantic_id == "reward/new-ship/continue":
            return self._new_ship_reward_visible_in_state(state)
        if semantic_id in (
            "meowfficer/buy/min",
            "meowfficer/buy/add",
            "meowfficer/buy/max",
            "meowfficer/buy/submit",
        ):
            try:
                self.meowfficer_purchase_state()
            except SemanticGateClosed:
                return False
            matches = self._matches(state, semantic_id)
            return bool(
                len(matches) == 1
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].raycast_top is None
                and matches[0].point is not None
                and matches[0].bounds is not None
                and matches[0].bounds.contains(matches[0].point)
            )
        if semantic_id == "meowfficer/buy/skip":
            return self._meowfficer_purchase_skip_proven(state)
        if semantic_id in (
            "meowfficer/buy/cancel",
            "meowfficer/buy/confirm",
        ):
            return self._meowfficer_purchase_prompt_proven(state)
        if semantic_id == "meowfficer/enhance/open":
            try:
                self.meowfficer_dock_state()
            except SemanticGateClosed:
                return False
            return self._meowfficer_reviewed_control_proven(state, semantic_id)
        if semantic_id in (
            "meowfficer/enhance/back",
            "meowfficer/feed/open",
            "meowfficer/enhance/submit",
        ):
            try:
                self.meowfficer_enhance_state()
            except SemanticGateClosed:
                return False
            return self._meowfficer_reviewed_control_proven(state, semantic_id)
        if semantic_id in (
            "meowfficer/feed/cancel",
            "meowfficer/feed/confirm",
        ):
            try:
                self.meowfficer_feed_state()
            except SemanticGateClosed:
                return False
            return self._meowfficer_reviewed_control_proven(state, semantic_id)
        if semantic_id in (
            "meowfficer/enhance/cancel",
            "meowfficer/enhance/confirm",
        ):
            return self._meowfficer_enhance_prompt_proven(state)
        if semantic_id == "meowfficer/get/continue":
            return self._meowfficer_get_continue_proven(state)
        if semantic_id in (
            "meowfficer/get/lock",
            "meowfficer/get/unlock",
        ):
            return self._meowfficer_lock_toggle_proven(state, semantic_id)
        if semantic_id in (
            "meowfficer/get/lock-cancel",
            "meowfficer/get/lock-confirm",
        ):
            return self._meowfficer_lock_prompt_proven(state)
        if semantic_id == "meowfficer/get/result/close":
            return self._meowfficer_get_result_proven(state)
        if semantic_id == "meowfficer/fort/close":
            return self._meowfficer_fort_close_proven(state)
        if semantic_id in (
            "meowfficer/queue/auto",
            "meowfficer/queue/start",
            "meowfficer/queue/close",
        ):
            try:
                self.meowfficer_queue_state()
            except SemanticGateClosed:
                return False
            matches = self._matches(state, semantic_id)
            return bool(
                len(matches) == 1
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].raycast_top is None
                and matches[0].point is not None
                and matches[0].bounds is not None
                and matches[0].bounds.contains(matches[0].point)
            )
        if semantic_id in (
            "meowfficer/queue/cancel",
            "meowfficer/queue/confirm",
        ):
            return self._meowfficer_queue_prompt_proven(state)
        if semantic_id == "academy/munitions":
            return self.academy_munitions_available()
        if semantic_id == "shipyard/series/open":
            matches = self._matches(state, semantic_id)
            return bool(
                self.shipyard_page_visible()
                and len(matches) == 1
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].point is not None
                and matches[0].bounds is not None
            )
        if semantic_id.startswith("shipyard/series/"):
            matches = self._matches(state, semantic_id)
            return bool(
                len(matches) == 1
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].point is not None
                and matches[0].bounds is not None
            )
        if semantic_id == "login/update/download":
            return self._login_update_download_prompt_matches(state)
        if semantic_id == "mail/manage/back":
            return self._mail_manager_back_delegated_raycast_proven(state)
        if semantic_id == "exercise/opponent/start":
            return self.exercise_opponent_detail_visible()
        matches = self._matches(state, semantic_id)
        if semantic_id in (
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
        ) and not matches:
            # Dock pages can legitimately exceed the observer toggle budget.
            # Do not demand an unrelated full Msgbox/UI snapshot when the
            # colliding NetworkDown button target is absent in typed state.
            return False
        if semantic_id in (
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
        ) and self._dock_full_prompt_matches(state):
            return False
        if (
            semantic_id == "overlay/login-data-expired/confirm"
            and not self._login_data_expired_prompt_matches(state)
        ):
            return False
        if len(matches) > 1:
            raise SemanticGateClosed("semantic target mapping is ambiguous")
        if semantic_id.startswith("guild/") and semantic_id in (
            "guild/lobby/report",
            "guild/logistics/supply",
            "guild/logistics/mission",
            "guild/operations/formation",
            "guild/operations/report",
            "guild/operations/dispatch/open",
        ):
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("guild control snapshots are not coherent")
            return bool(
                len(matches) == 1
                and self._guild_delegated_button_proven(
                    state, ui_state, semantic_id, matches[0]
                )
                and not self._blocking_rules(state, semantic_id)
            )
        if semantic_id in (
            "guild/dispatch-detail/close",
            "guild/dispatch-detail/formation",
        ):
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("guild dispatch snapshots are not coherent")
            return bool(
                len(matches) == 1
                and self._guild_dispatch_detail_control_proven(
                    state, ui_state, semantic_id, matches[0]
                )
                and not self._blocking_rules(state, semantic_id)
            )
        if semantic_id in (
            "guild/report/close",
            "guild/report/claim-all",
        ):
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("guild report snapshots are not coherent")
            return bool(
                len(matches) == 1
                and self._guild_report_control_proven(
                    state, ui_state, semantic_id, matches[0]
                )
                and not self._blocking_rules(state, semantic_id)
            )
        if semantic_id in (
            "guild/formation/close",
            "guild/formation/recommend",
            "guild/formation/go",
        ):
            ui_state = self.read_ui_state()
            if (
                ui_state.generation < state.generation
                or ui_state.generation > state.generation + 2
            ):
                raise SemanticGateClosed("guild formation snapshots are not coherent")
            return bool(
                len(matches) == 1
                and self._guild_formation_control_proven(
                    state, ui_state, semantic_id, matches[0]
                )
                and not self._blocking_rules(state, semantic_id)
            )
        if semantic_id == "main/guild":
            return bool(
                self.main_page_visible()
                and matches
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].raycast_top is None
                and matches[0].point is not None
                and matches[0].bounds is not None
                and matches[0].bounds.contains(matches[0].point)
                and not self._blocking_rules(state, semantic_id)
            )
        if semantic_id == "dorm/empty-food/cancel":
            return self._dorm_empty_food_cancel_proven(state)
        if semantic_id in ("dorm/feed", "dorm/collect"):
            return self._dorm_page_control_proven(state, semantic_id)
        if semantic_id in (
            "meowfficer/page/back",
            "meowfficer/fort/enter",
            "meowfficer/buy/enter",
            "meowfficer/train/enter",
        ):
            try:
                self.meowfficer_dock_state()
            except SemanticGateClosed:
                return False
            return bool(
                matches
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].raycast_top is None
                and matches[0].point is not None
                and matches[0].bounds is not None
                and matches[0].bounds.contains(matches[0].point)
            )
        if semantic_id in (
            "meowfficer/train/close",
            "meowfficer/train/complete/first",
            "meowfficer/train/finish-all",
            "meowfficer/train/start",
        ):
            try:
                training = self.meowfficer_training_state()
            except SemanticGateClosed:
                return False
            return bool(
                matches
                and (
                    semantic_id != "meowfficer/train/complete/first"
                    or training.completed > 0
                )
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].raycast_top is None
                and matches[0].point is not None
                and matches[0].bounds is not None
                and matches[0].bounds.contains(matches[0].point)
            )
        if (
            semantic_id == "tactical/continue/cancel"
            and not self._tactical_continue_prompt_matches(state)
        ):
            return False
        if semantic_id in (
            "overlay/network-reconnect/cancel",
            "overlay/network-reconnect/confirm",
        ) and not self._network_reconnect_prompt_matches(state):
            return False
        if semantic_id in (
            "build/warning/cancel",
            "build/warning/confirm",
        ) and not self._build_warning_prompt_matches(state):
            return False
        if semantic_id in (
            "build/queue/finish-cancel",
            "build/queue/finish-confirm",
        ) and self._build_queue_finish_prompt_cost(state) is None:
            return False
        if semantic_id in (
            "tactical/course/cancel",
            "tactical/course/confirm",
        ) and not self._tactical_course_prompt_matches(state):
            return False
        if (
            semantic_id in ("research/start/cancel", "research/start/confirm")
            and self._research_start_prompt_cost(state) is None
        ):
            return False
        if semantic_id in (
            "research/queue/cancel",
            "research/queue/confirm",
        ) and not self._research_queue_prompt_matches(state):
            return False
        if semantic_id in (
            "guild/dispatch/cancel",
            "guild/dispatch/confirm",
        ) and not self._guild_dispatch_prompt_matches(state):
            return False
        if semantic_id in (
            "guild/exchange/cancel",
            "guild/exchange/confirm",
        ) and not self._guild_exchange_prompt_matches(state):
            return False
        if semantic_id in (
            "os/map/auto-search/off",
            "os/map/auto-search/on",
            "os/map/mission-list",
            "os/map/storage",
            "os/map/order",
            "os/order/back",
            "os/order/scan",
            "os/order/submarine",
            "os/port/enter",
            "os/port/supply",
            "os/port/dock",
            "os/port/dock/back",
            "os/port/dock/repair-all",
            "os/port/back",
            "os/shop/back",
            "os/globe/voucher",
            "os/globe/mission-overview",
            "os/mission-list/close",
            "os/voucher/back",
            "os/storage/back",
        ):
            return bool(
                matches
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].raycast_top is None
                and matches[0].point is not None
                and matches[0].bounds is not None
                and matches[0].bounds.contains(matches[0].point)
                and not self._blocking_rules(state, semantic_id)
            )
        if semantic_id == "os/help/close":
            return bool(
                matches
                and matches[0].active_in_hierarchy
                and matches[0].active_and_enabled
                and matches[0].interactable
                and matches[0].raycast_top is None
                and matches[0].point is not None
                and matches[0].bounds is not None
                and matches[0].bounds.contains(matches[0].point)
                and not self._blocking_rules(state, semantic_id)
            )
        return bool(
            matches
            and matches[0].actionable
            and not self._blocking_rules(state, semantic_id)
        )

    def bounds(self, semantic_id: str) -> Bounds:
        target = self._unique(self.read_state(), semantic_id)
        if target.bounds is None:
            raise SemanticGateClosed("semantic target has no screen bounds")
        return target.bounds

    def current_scene(self) -> int:
        return self.read_state().scene_handle
