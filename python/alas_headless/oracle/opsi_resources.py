"""Opsi resources for the typed ALAS boundary."""

from __future__ import annotations

import math
import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    ImageState,
    OperationSirenActionPointState,
    OracleState,
    Point,
)
from .errors import SemanticGateClosed, SemanticTargetMissing


class OpsiResourcesOracle:
    """Opsi resources operations sharing the oracle frame and input boundary."""

    def _operation_siren_order_prompt_mounted(self, state: OracleState) -> bool:
        # This client uses Msgbox/window, without the generic Msgbox(Clone)
        # owner. Bind its blocking effect to the retained SVOrderPanel only.
        return bool(
            any(v.active_in_hierarchy for v in self._matches(state, "os/order/back"))
            and any(v.active_in_hierarchy and v.active_and_enabled
                    for key in ("os/order/confirm", "os/order/cancel")
                    for v in self._matches(state, key))
        )

    def click_operation_siren_order(self, order_kind: str) -> ActionReceipt:
        """Execute one exact enabled navigation order from SVOrderPanel."""

        if order_kind not in ("scan", "submarine"):
            raise ValueError("operation siren order kind is unsupported")
        semantic_id = "os/order/" + order_kind
        state = self.read_state()
        if self._operation_siren_order_prompt_mounted(state):
            raise SemanticGateClosed("operation siren order is covered by its prompt")
        back = self._unique(state, "os/order/back")
        target = self._unique(state, semantic_id)
        if not all(
            item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.raycast_top is not False
            and item.bounds is not None
            for item in (back, target)
        ):
            raise SemanticGateClosed("operation siren order panel is incomplete")
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed(
                "operation siren order snapshots are not coherent"
            )
        root = (
            "SVOrderPanel(Clone)/adapt/order_list/"
            + ("fov" if order_kind == "scan" else "submarine")
            + "/type_enable/"
        )
        cost = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(root + "cost/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]{1,3}", text.text.strip())
        )
        sprite = "fov_icon" if order_kind == "scan" else "submarine_icon"
        icon = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(root + "light/icon")
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(cost) != 1 or len(icon) != 1:
            raise SemanticGateClosed(
                "operation siren enabled order identity is incomplete"
            )
        assert target.bounds is not None and icon[0].bounds is not None
        point = Point(
            (icon[0].bounds.left + icon[0].bounds.right) / 2.0,
            (icon[0].bounds.top + icon[0].bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point):
            raise SemanticGateClosed("operation siren order point left its button")
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("operation siren order is obscured")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before operation siren order")
        self._tap(int(round(point.x)), int(round(point.y)))
        # Do not let ALAS repeatedly submit an input that never opened its
        # confirmation. The original order loop still owns confirming it.
        for _ in range(12):
            self._sleep(0.25)
            if self.operation_siren_order_confirmation_visible(order_kind):
                break
        else:
            raise SemanticGateClosed("operation siren order input was not confirmed")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_order_back(self) -> ActionReceipt:
        """Close SVOrderPanel through its exact visible back image."""

        state = self.read_state()
        if self._operation_siren_order_prompt_mounted(state):
            raise SemanticGateClosed("operation siren order back is covered by its prompt")
        target = self._unique(state, "os/order/back")
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed(
                "operation siren order-back snapshots are not coherent"
            )
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.name == "back"
            and image.sprite == "btn_back"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(images) != 1:
            raise SemanticGateClosed(
                "operation siren order back is absent or ambiguous"
            )
        bounds = images[0].bounds
        assert bounds is not None
        point = Point(
            (bounds.left + bounds.right) / 2.0,
            (bounds.top + bounds.bottom) / 2.0,
        )
        if target.bounds is None or not target.bounds.contains(point):
            raise SemanticGateClosed("operation siren order-back point changed")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "foreground changed before operation siren order back"
            )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/order/back",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=target.path,
        )

    def operation_siren_order_confirmation_visible(
        self, order_kind: str
    ) -> bool:
        """Prove the AP confirmation mounted by one exact navigation order."""

        if order_kind not in ("scan", "submarine"):
            raise ValueError("operation siren order kind is unsupported")
        state = self.read_state()
        background = {
            semantic_id: tuple(
                button
                for button in self._matches(state, semantic_id)
                if button.active_in_hierarchy
                and button.bounds is not None
            )
            for semantic_id in (
                "os/order/back",
                "os/order/" + order_kind,
            )
        }
        actions = {
            semantic_id: tuple(
                button
                for button in self._matches(state, semantic_id)
                if button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            )
            for semantic_id in (
                "os/order/confirm",
                "os/order/cancel",
            )
        }
        required = {**background, **actions}
        if not any(actions.values()):
            return False
        if any(len(matches) != 1 for matches in required.values()):
            raise SemanticGateClosed(
                "operation siren order confirmation is incomplete"
            )

        text_state = self.read_text_state()
        if not state.generation <= text_state.generation <= state.generation + 2:
            raise SemanticGateClosed(
                "operation siren order confirmation snapshots are not coherent"
            )
        order_root = (
            "SVOrderPanel(Clone)/adapt/order_list/"
            + ("fov" if order_kind == "scan" else "submarine")
            + "/type_enable/cost/Text"
        )
        costs = tuple(
            text
            for text in text_state.texts
            if text.path.endswith(order_root)
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]{1,3}", text.text.strip())
        )
        prompts = tuple(
            text
            for text in text_state.texts
            if text.path.endswith("Msgbox/window/msg_panel/base/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(costs) != 1 or len(prompts) != 1:
            raise SemanticGateClosed(
                "operation siren order confirmation text is incomplete"
            )
        prompt_suffix = (
            "侦查当前海域的全部区域？"
            if order_kind == "scan"
            else "向当前海域派遣潜艇舰队？"
        )
        prompt_match = re.fullmatch(
            r"是否消耗<color=#92FC63FF>([0-9]{1,3})</color>行动力，\n"
            + re.escape(prompt_suffix),
            prompts[0].text.strip(),
        )
        if (
            prompt_match is None
            or int(prompt_match.group(1)) > int(costs[0].text.strip())
        ):
            raise SemanticGateClosed(
                "operation siren order confirmation cost changed"
            )
        return True

    def click_operation_siren_order_confirmation(
        self, order_kind: str, *, confirm: bool
    ) -> ActionReceipt:
        """Confirm or cancel the proven AP prompt for one navigation order."""

        if not self.operation_siren_order_confirmation_visible(order_kind):
            raise SemanticGateClosed(
                "operation siren order confirmation is absent"
            )
        state = self.read_state()
        semantic_id = "os/order/" + ("confirm" if confirm else "cancel")
        target = self._unique(state, semantic_id)
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            and self._foreground_component() == self.fingerprint.component
        ):
            raise SemanticGateClosed(
                "operation siren order confirmation is not actionable"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_map_exit(self) -> ActionReceipt:
        """Leave a locked special-zone room through its exact exit control."""

        if not self.operation_siren_local_map_visible():
            # A prior accepted exit can unmount this owner between ALAS'
            # presence probe and the final target re-read.  Classify that
            # atomic transition as a missing target so idempotent callers do
            # not issue a duplicate tap on the ordinary map.
            raise SemanticTargetMissing(
                "operation siren local-map identity is absent"
            )
        state = self.read_state()
        target = self._unique(state, "os/map/exit")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("operation siren map exit is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before map exit input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/map/exit",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _operation_siren_action_point_read(
        self,
    ) -> Tuple[
        OracleState,
        OperationSirenActionPointState,
        Tuple[ImageState, ...],
    ]:
        button_state = self.read_state()
        use = self._unique(button_state, "os/action-point/use")
        cancel = self._unique(button_state, "os/action-point/cancel")
        if not all(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
            for target in (use, cancel)
        ):
            raise SemanticGateClosed(
                "operation siren action point controls are incomplete"
            )

        ui_state = self.read_ui_state()
        if not (
            button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "operation siren action point snapshots are not coherent"
            )
        root = (
            "WorldStaminaRecoverUI(Clone)/window/world_stamina_panel/content/"
        )
        current_text = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(root + "tip_bg/stamina/value")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]{1,3}", text.text.strip())
        )
        if len(current_text) != 1:
            raise SemanticGateClosed(
                "operation siren current action points are absent or ambiguous"
            )

        item_suffix = "item(Clone)/IconTpl/icon_bg/icon"
        expected_sprites = (
            "oil",
            "Wxingdonglihuifu1",
            "Wxingdonglihuifu2",
            "Wxingdonglihuifu3",
        )
        icons = tuple(
            sorted(
                (
                    image
                    for image in ui_state.images
                    if image.path.endswith(root + "item_list/" + item_suffix)
                    and image.sprite in expected_sprites
                    and image.active_in_hierarchy
                    and image.active_and_enabled
                    and not image.truncated
                    and image.bounds is not None
                ),
                key=lambda image: image.bounds.left if image.bounds else math.inf,
            )
        )
        if (
            len(icons) != 4
            or tuple(image.sprite for image in icons) != expected_sprites
        ):
            raise SemanticGateClosed(
                "operation siren action point item icons are incomplete"
            )
        count_texts = tuple(
            sorted(
                (
                    text
                    for text in ui_state.texts
                    if text.path.endswith(
                        root + "item_list/item(Clone)/IconTpl/icon_bg/count"
                    )
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                    and text.bounds is not None
                    and re.fullmatch(r"[0-9]+", text.text.strip())
                ),
                key=lambda text: text.bounds.left if text.bounds else math.inf,
            )
        )
        if len(count_texts) != 4:
            raise SemanticGateClosed(
                "operation siren action point item counts are incomplete"
            )
        for icon, count in zip(icons, count_texts):
            assert icon.bounds is not None and count.bounds is not None
            if abs(
                (icon.bounds.left + icon.bounds.right) / 2.0
                - (count.bounds.left + count.bounds.right) / 2.0
            ) > 60.0:
                raise SemanticGateClosed(
                    "operation siren action point item pairing changed"
                )

        selected = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(root + "item_list/item(Clone)/select")
            and image.sprite == "selected"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(selected) != 1:
            raise SemanticGateClosed(
                "operation siren selected action point item is ambiguous"
            )
        assert selected[0].bounds is not None
        selected_center = (
            selected[0].bounds.left + selected[0].bounds.right
        ) / 2.0
        icon_centers = tuple(
            (image.bounds.left + image.bounds.right) / 2.0
            for image in icons
            if image.bounds is not None
        )
        selected_index = min(
            range(4), key=lambda index: abs(icon_centers[index] - selected_center)
        )
        if abs(icon_centers[selected_index] - selected_center) > 25.0:
            raise SemanticGateClosed(
                "operation siren selected action point item is unbound"
            )

        purchase_cost: Optional[int] = None
        purchase_points: Optional[int] = None
        purchase_remaining: Optional[int] = None
        purchase_limit: Optional[int] = None
        purchase_texts = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(root + "Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if selected_index == 0:
            if len(purchase_texts) != 1:
                raise SemanticGateClosed(
                    "operation siren oil purchase terms are absent or ambiguous"
                )
            purchase_plain = re.sub(
                r"</?color(?:=#[0-9A-Fa-f]{6})?>",
                "",
                purchase_texts[0].text,
            )
            purchase_values = tuple(
                int(value) for value in re.findall(r"[0-9]+", purchase_plain)
            )
            if (
                len(purchase_values) != 4
                or "<" in purchase_plain
                or ">" in purchase_plain
            ):
                raise SemanticGateClosed(
                    "operation siren oil purchase terms are malformed"
                )
            (
                purchase_cost,
                purchase_points,
                purchase_remaining,
                purchase_limit,
            ) = purchase_values
            if (
                purchase_cost <= 0
                or purchase_points not in range(1, 601)
                or purchase_limit != 5
                or purchase_remaining not in range(6)
            ):
                raise SemanticGateClosed(
                    "operation siren oil purchase terms changed"
                )
        return (
            button_state,
            OperationSirenActionPointState(
                generation=ui_state.generation,
                current=int(current_text[0].text.strip()),
                item_counts=tuple(
                    int(text.text.strip()) for text in count_texts
                ),
                selected_index=selected_index,
                oil_purchase_cost=purchase_cost,
                oil_purchase_points=purchase_points,
                oil_purchase_remaining=purchase_remaining,
                oil_purchase_limit=purchase_limit,
            ),
            icons,
        )

    def operation_siren_action_point_state(
        self,
    ) -> OperationSirenActionPointState:
        return self._retry_transition_read(
            lambda: self._operation_siren_action_point_read()[1]
        )

    def operation_siren_action_point_visible(self) -> bool:
        state = self.read_state()
        try:
            use = self._unique(state, "os/action-point/use")
            cancel = self._unique(state, "os/action-point/cancel")
        except SemanticTargetMissing:
            return False
        return all(
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            for target in (use, cancel)
        )

    def click_operation_siren_action_point_open(self) -> ActionReceipt:
        """Open the AP panel from the exact WorldMap stamina resource."""

        # Require the complete local-map resource header, not merely a button
        # with the same short Unity name.
        self.operation_siren_state()
        button_state = self.read_state()
        target = self._unique(button_state, "os/action-point/open")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed(
                "operation siren action point entry is not actionable"
            )
        ui_state = self.read_ui_state()
        value_texts = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(
                "top/adapt/top_stage/resources/WorldResPanel(Clone)/res/"
                "stamina/value"
            )
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"[0-9]+", text.text.strip()) is not None
        )
        if (
            len(value_texts) != 1
            or not button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "operation siren action point value is absent or ambiguous"
            )
        value = value_texts[0]
        assert value.bounds is not None
        point = Point(
            (value.bounds.left + value.bounds.right) / 2.0,
            (value.bounds.top + value.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point):
            raise SemanticGateClosed(
                "operation siren action point value left its resource control"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before action point input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/action-point/open",
            generation=button_state.generation,
            point=point,
            bounds=value.bounds,
            path=value.path,
        )

    def click_operation_siren_action_point_item(
        self, item_index: int
    ) -> ActionReceipt:
        if item_index not in range(4):
            raise ValueError("operation siren action point item must be 0 through 3")
        button_state, before, icons = self._operation_siren_action_point_read()
        if before.selected_index == item_index:
            raise SemanticGateClosed(
                "operation siren action point item is already selected"
            )
        target = icons[item_index]
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before action point input")
        self._tap(int(round(point.x)), int(round(point.y)))
        for _ in range(12):
            self._sleep(0.25)
            after = self.operation_siren_action_point_state()
            if (
                after.selected_index == item_index
                and after.current == before.current
                and after.item_counts == before.item_counts
            ):
                break
        else:
            raise SemanticGateClosed(
                "operation siren action point selection was not proven"
            )
        return ActionReceipt(
            semantic_id=f"os/action-point/item/{item_index}",
            generation=button_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_action_point_control(
        self, use: bool
    ) -> ActionReceipt:
        button_state, _, _ = self._operation_siren_action_point_read()
        semantic_id = "os/action-point/use" if use else "os/action-point/cancel"
        target = self._unique(button_state, semantic_id)
        if target.point is None or target.bounds is None:
            raise SemanticGateClosed(
                "operation siren action point control is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before action point input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _operation_siren_port_repair_cost_in_state(
        self, state: OracleState
    ) -> Optional[int]:
        """Bind the dock-wide repair prompt to its exact typed cost."""

        confirm = self._matches(state, "os/port/dock/repair-confirm")
        cancel = self._matches(state, "os/port/dock/repair-cancel")
        if len(confirm) > 1 or len(cancel) > 1:
            raise SemanticGateClosed("operation siren repair prompt is ambiguous")
        if not confirm and not cancel:
            return None
        if (
            len(confirm) != 1
            or len(cancel) != 1
            or not confirm[0].actionable
            or not cancel[0].actionable
        ):
            raise SemanticGateClosed("operation siren repair prompt is incomplete")

        before_signature = self._msgbox_button_signature(state)
        text_state = self.read_text_state()
        after = self.read_state()
        if not (
            state.generation <= text_state.generation <= after.generation
            and state.scene_handle == after.scene_handle
            and before_signature == self._msgbox_button_signature(after)
        ):
            raise SemanticGateClosed(
                "operation siren repair prompt snapshots are not coherent"
            )

        def exact_text(suffix: str) -> Optional[str]:
            matches = tuple(
                text
                for text in text_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed(
                    "operation siren repair prompt text is ambiguous"
                )
            return matches[0].text if matches else None

        content = exact_text("Msgbox(Clone)/window/msg_panel/content")
        cancel_text = exact_text(
            "Msgbox(Clone)/window/button_container/custom_button_2(Clone)/pic"
        )
        confirm_text = exact_text(
            "Msgbox(Clone)/window/button_container/custom_button_1(Clone)/pic"
        )
        if content is None or cancel_text is None or confirm_text is None:
            raise SemanticGateClosed("operation siren repair prompt text is incomplete")
        plain = re.sub(r"<[^>]*>", "", content).strip()
        match = re.fullmatch(r"修复所有舰船需要：\s*\*([1-9][0-9]*)", plain)
        if (
            match is None
            or "".join(cancel_text.split()) != "取消"
            or "".join(confirm_text.split()) != "确定"
        ):
            raise SemanticGateClosed("operation siren repair prompt is unknown")
        return int(match.group(1))

    def operation_siren_port_repair_cost(self) -> Optional[int]:
        return self._retry_transition_read(
            lambda: self._operation_siren_port_repair_cost_in_state(
                self.read_state()
            )
        )

    def click_operation_siren_port_repair(
        self, confirm: bool
    ) -> ActionReceipt:
        state = self.read_state()
        if self._operation_siren_port_repair_cost_in_state(state) is None:
            raise SemanticGateClosed("operation siren repair prompt is absent")
        semantic_id = (
            "os/port/dock/repair-confirm"
            if confirm
            else "os/port/dock/repair-cancel"
        )
        target = self._unique(state, semantic_id)
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed(
                "operation siren repair choice is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before repair input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _operation_siren_exit_prompt_state(self) -> Optional[OracleState]:
        """Return one button snapshot only when its exact exit text is coherent."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        zone_titles = tuple(
            text.text.strip()
            for text in ui_state.texts
            if text.path.endswith("/top_stage/title/name")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip()
        )
        retained_progress_prompts = {
            f"是否确定从{title}中离开？\n"
            "（离开后当前作战进度将会保留，本月内再次进入可继续挑战）"
            for title in zone_titles
        }
        reset_progress_prompts = {
            f"是否确定从{title}中离开？\n"
            "（离开后当前作战进度将会重置，已获得的奖励无法重复领取）"
            for title in zone_titles
        }
        prompt = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("Msgbox(Clone)/window/msg_panel/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and (
                text.text.strip()
                in {
                    "需要暂时离开大型作战么？",
                    "当前海域无法通过边界区域离开。是否继续？",
                    "离开当前海域后，潜艇舰队会自动返回我方港口待命，是否离开？",
                    "是否确定从该处隐秘海域离开？\n"
                    "（离开后将无法再次返回）",
                    "是否确定从深渊海域离开？\n"
                    "（警告：离开后将无法再次返回挑战强敌！）",
                }
                or text.text.strip() in retained_progress_prompts
                or text.text.strip() in reset_progress_prompts
            )
        )
        return state if (
            len(prompt) == 1
            and len(self._matches(state, "os/exit/confirm")) == 1
            and len(self._matches(state, "os/exit/cancel")) == 1
        ) else None

    def operation_siren_exit_prompt_visible(self) -> bool:
        return self._operation_siren_exit_prompt_state() is not None

    def operation_siren_abyssal_entry_prompt_visible(self) -> bool:
        """Recognize the one-way abyssal entry warning exactly."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        prompts = tuple(
            text.text.strip()
            for text in ui_state.texts
            if text.path.endswith("Msgbox(Clone)/window/msg_panel/content")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        return bool(
            prompts
            == (
                "深渊海域作战难度较高且不可重复进入，\n"
                "请确认舰队战备后前往作战",
            )
            and len(self._matches(state, "os/exit/confirm")) == 1
            and len(self._matches(state, "os/exit/cancel")) == 1
        )

    def operation_siren_abyssal_exit_available(self) -> bool:
        """Return whether the nearest abyssal passage has been unlocked.

        The client replaces ``taban_jinzhi(Clone)`` with ``taban(Clone)``
        after the boss settlement. Both models can remain in the scene graph
        outside the viewport, so compare the event model nearest the viewport
        centre instead of accepting any unlocked floor model in the map.
        """

        ui_state = self.read_ui_state()
        titles = tuple(
            text.text.strip()
            for text in ui_state.texts
            if text.path.endswith("/top_stage/title/name")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.strip().endswith("-深渊海域")
        )
        if len(titles) != 1:
            return False

        models = []
        for image in ui_state.images:
            if not image.active_in_hierarchy or image.bounds is None:
                continue
            if "/attachments/event_" not in image.path:
                continue
            if not image.path.endswith("/taban"):
                continue
            if "/icon/model/taban(Clone)/" in image.path:
                unlocked = True
            elif "/icon/model/taban_jinzhi(Clone)/" in image.path:
                unlocked = False
            else:
                continue
            center_x = (image.bounds.left + image.bounds.right) / 2.0
            center_y = (image.bounds.top + image.bounds.bottom) / 2.0
            distance = math.hypot(
                center_x - self.fingerprint.width / 2.0,
                center_y - self.fingerprint.height / 2.0,
            )
            models.append((distance, unlocked))

        if not models:
            return False
        models.sort(key=lambda item: item[0])
        nearest_distance, nearest_unlocked = models[0]
        return nearest_distance <= self.fingerprint.height and nearest_unlocked

    def click_operation_siren_abyssal_exit(self) -> ActionReceipt:
        """Move onto the nearest exact unlocked abyssal passage model."""

        if not self.operation_siren_abyssal_exit_available():
            raise SemanticGateClosed("unlocked abyssal passage is absent")
        state = self.read_ui_state()
        candidates = []
        for image in state.images:
            if (
                image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and "/attachments/event_" in image.path
                and image.path.endswith(
                    "/icon/model/taban(Clone)/taban"
                )
                and image.name == "taban"
                and image.sprite == "taban01"
            ):
                center_x = (image.bounds.left + image.bounds.right) / 2.0
                center_y = (image.bounds.top + image.bounds.bottom) / 2.0
                candidates.append(
                    (
                        math.hypot(
                            center_x - self.fingerprint.width / 2.0,
                            center_y - self.fingerprint.height / 2.0,
                        ),
                        image,
                        Point(center_x, center_y),
                    )
                )
        candidates.sort(key=lambda item: item[0])
        if not candidates:
            raise SemanticGateClosed("unlocked abyssal passage is absent")
        _, target, point = candidates[0]
        assert target.bounds is not None
        if (
            not target.bounds.contains(point)
            or not 80.0 <= point.x <= 960.0
            or not 100.0 <= point.y <= 620.0
            or self._foreground_component() != self.fingerprint.component
        ):
            raise SemanticGateClosed("unlocked abyssal passage is not safely visible")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/abyssal/exit",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def operation_siren_world_overview_visible(self) -> bool:
        """Recognize the post-special-zone overview dismissal exactly."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        tips = tuple(
            text
            for text in ui_state.texts
            if text.text.strip() == "点击任意位置返回"
            and text.path.endswith("WorldOverviewUI(Clone)/tip/Text")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        backgrounds = tuple(
            button
            for button in state.buttons
            if button.name == "bg"
            and button.path.endswith("WorldOverviewUI(Clone)/bg")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        return len(tips) == 1 and len(backgrounds) == 1

    def click_operation_siren_world_overview(self) -> ActionReceipt:
        if not self.operation_siren_world_overview_visible():
            raise SemanticGateClosed("operation siren world overview is absent")
        state = self.read_state()
        target = next(
            button
            for button in state.buttons
            if button.name == "bg"
            and button.path.endswith("WorldOverviewUI(Clone)/bg")
            and button.active_in_hierarchy
        )
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before overview dismissal")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/world-overview/close",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_abyssal_entry(self, confirm: bool) -> ActionReceipt:
        if not self.operation_siren_abyssal_entry_prompt_visible():
            raise SemanticGateClosed("operation siren abyssal entry prompt is absent")
        state = self.read_state()
        semantic_id = "os/exit/confirm" if confirm else "os/exit/cancel"
        target = self._unique(state, semantic_id)
        if not (
            target.actionable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed(
                "operation siren abyssal entry choice is not actionable"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=(
                "os/abyssal/entry/confirm"
                if confirm
                else "os/abyssal/entry/cancel"
            ),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_exit(self, confirm: bool) -> ActionReceipt:
        state = self._operation_siren_exit_prompt_state()
        if state is None:
            raise SemanticGateClosed("operation siren exit prompt is absent")
        semantic_id = "os/exit/confirm" if confirm else "os/exit/cancel"
        target = self._unique(state, semantic_id)
        if not (
            target.actionable
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            raise SemanticGateClosed("operation siren exit choice is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
