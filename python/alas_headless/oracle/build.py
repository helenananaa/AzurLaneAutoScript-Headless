"""Build for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, Optional, Tuple
from .contracts import (
    ActionReceipt,
    BuildCostState,
    BuildPool,
    BuildSubmitState,
    OracleState,
    UiState,
)
from .errors import SemanticGateClosed


class BuildOracle:
    """Build operations sharing the oracle frame and input boundary."""

    def _build_origin_queue_shell(self, buttons: OracleState, ui: UiState) -> bool:
        """Prove the queue's reviewed UIOrigin canvas without a raycast report."""
        backs = self._matches(buttons, "build/page/back")
        if len(backs) != 1:
            return False
        back = backs[0]
        if not (
            back.path.endswith("UIOrigin/blur_panel/adapt/top/back_btn")
            and back.active_in_hierarchy and back.active_and_enabled
            and back.interactable and back.raycast_top is None
            and back.point is not None and back.bounds is not None
            and back.bounds.contains(back.point)
        ):
            return False
        tabs = self._toggle_matches(ui, "build/nav/queue")
        if not (len(tabs) == 1 and tabs[0].checked
                and tabs[0].active_in_hierarchy and tabs[0].active_and_enabled
                and tabs[0].path.endswith(
                    "UIOrigin/blur_panel/adapt/left_length/frame/tagRoot/queue_btn")):
            return False
        capacities = tuple(t for t in ui.texts
            if t.path.endswith("BuildShipDetailUI1(Clone)/title/value")
            and t.active_in_hierarchy and t.active_and_enabled
            and not t.truncated and t.bounds is not None)
        images = tuple(i for i in ui.images
            if i.path == back.path + "/mask/Image" and i.sprite == "back_btn"
            and i.active_in_hierarchy and i.active_and_enabled
            and i.raycast_target and i.raycast_top is None
            and not i.truncated and i.bounds is not None
            and i.bounds.contains(back.point))
        return bool(len(capacities) == 1
                    and re.fullmatch(r"[1-9][0-9]*", capacities[0].text.strip())
                    and len(images) == 1 and not ui.image_truncated)

    def _build_origin_pool_navigation_proven(self, buttons, ui, semantic_id, matches):
        if (semantic_id != "build/nav/pools" or len(matches) != 1
                or not self._build_origin_queue_shell(buttons, ui)):
            return False
        toggle = matches[0]
        if not (toggle.path.endswith(
                    "UIOrigin/blur_panel/adapt/left_length/frame/tagRoot/build_btn")
                and not toggle.checked and toggle.active_in_hierarchy
                and toggle.active_and_enabled and toggle.interactable
                and toggle.raycast_top is None and toggle.point is not None
                and toggle.bounds is not None and toggle.bounds.contains(toggle.point)):
            return False
        images = tuple(i for i in ui.images
            if i.path == toggle.path and i.sprite == "build_unsel"
            and i.active_in_hierarchy and i.active_and_enabled
            and i.raycast_target and i.raycast_top is None
            and not i.truncated and i.bounds is not None
            and i.bounds.contains(toggle.point))
        return len(images) == 1

    def build_selected_pool(self) -> BuildPool:
        """Return the selected construction pool from exact Unity Toggles."""

        return self._retry_transition_read(self._build_selected_pool_once)

    def _build_selected_pool_once(self) -> BuildPool:
        button_state = self.read_state()
        page_markers = tuple(
            button
            for button in button_state.buttons
            if button.name == "start_btn"
            and button.path.endswith(
                "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/start_btn"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        if len(page_markers) != 1:
            raise SemanticGateClosed("construction page identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("construction snapshots are not coherent")
        selected = []
        for pool in BuildPool:
            matches = self._toggle_matches(ui_state, "build/pool/" + pool.value)
            if pool is BuildPool.EVENT and not matches:
                continue
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "construction pool Toggle is absent or ambiguous: " + pool.value
                )
            if matches[0].checked:
                selected.append(pool)
        if len(selected) != 1:
            raise SemanticGateClosed("construction pool selection is inconsistent")
        return selected[0]

    def build_costs(self) -> BuildCostState:
        """Read owned cubes and per-build costs without enabling construction."""

        self.build_selected_pool()
        state = self.read_ui_state()
        base = "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/"
        suffixes = {
            "owned": base + "res_items/item/Text",
            "cubes": base + "item_bg/item/Text",
            "coins": base + "item_bg/gold/Text",
        }
        values: Dict[str, int] = {}
        for key, suffix in suffixes.items():
            matches = tuple(
                item
                for item in state.texts
                if item.path.endswith(suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
                and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "construction resource text is absent or ambiguous: " + key
                )
            values[key] = int(matches[0].text.strip())
        if values["cubes"] <= 0 or values["coins"] <= 0:
            raise SemanticGateClosed("construction cost is invalid")
        return BuildCostState(
            cubes_owned=values["owned"],
            cubes_per_build=values["cubes"],
            coins_per_build=values["coins"],
        )

    def build_coins_owned(self) -> int:
        """Read the exact global coin counter while the pool page is proven."""

        self.build_selected_pool()
        state = self.read_ui_state()
        suffix = "Overlay/UIMain/ResPanel(Clone)/frame/gold/gold_value"
        matches = tuple(
            item
            for item in state.texts
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("construction coin counter is absent or ambiguous")
        return int(matches[0].text.strip())

    def build_submit_state(self) -> BuildSubmitState:
        """Read and cross-check the open construction confirmation dialog."""

        return self._retry_transition_read(self._build_submit_state_once)

    def _build_submit_state_once(self) -> BuildSubmitState:
        button_state = self.read_state()
        confirm = self._unique(button_state, "build/prep/confirm")
        cancel = self._unique(button_state, "build/prep/cancel")
        if (
            not confirm.actionable
            or not cancel.actionable
            or self._blocking_rules(button_state, "build/prep/confirm")
        ):
            raise SemanticGateClosed("construction confirmation identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "construction confirmation snapshots are not coherent"
            )

        def exact_text(path: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(path)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "construction confirmation text is absent or ambiguous"
                )
            return re.sub(r"<[^>]*>", "", matches[0].text).strip()

        count_text = exact_text(
            "BuildShipMsgBoxUI(Clone)/window/content/calc_panel/Text"
        )
        message = exact_text("BuildShipMsgBoxUI(Clone)/window/content/Text")
        count_match = re.fullmatch(r"([1-9][0-9]?)", count_text)
        cost_match = re.fullmatch(
            r"建造「([1-9][0-9]?)艘」.+需要消耗:\s*"
            r"「([1-9][0-9]*)物资」和「([1-9][0-9]*)个心智魔方」",
            message,
        )
        if count_match is None or cost_match is None:
            raise SemanticGateClosed("construction confirmation cost is malformed")
        count = int(count_match.group(1))
        message_count, coins, cubes = map(int, cost_match.groups())
        if message_count != count:
            raise SemanticGateClosed("construction confirmation count is inconsistent")

        costs = self.build_costs()
        if (
            cubes != costs.cubes_per_build * count
            or coins != costs.coins_per_build * count
        ):
            raise SemanticGateClosed(
                "construction confirmation cost changed unexpectedly"
            )
        return BuildSubmitState(
            count=count,
            cubes_owned=costs.cubes_owned,
            cubes_required=cubes,
            coins_required=coins,
            confirm=confirm,
        )

    def build_queue_timers(self) -> Tuple[str, ...]:
        """Read every instantiated slot in the complete typed queue."""

        return self._retry_transition_read(self._build_queue_timers_once)

    def _build_queue_timers_once(self) -> Tuple[str, ...]:
        button_state = self.read_state()
        back = self._unique(button_state, "build/page/back")
        if self._blocking_rules(button_state, "build/nav/queue"):
            raise SemanticGateClosed("construction queue page identity is not proven")
        ui_state = self.read_ui_state()
        # On the pinned CN client, a read of the unchanged queue Button tree
        # followed by its much larger typed UI tree can span up to four
        # monotonically increasing observer generations.  Keep the queue-tab,
        # capacity, and timer-shape proofs below exact; this only admits the
        # observed read skew while those immutable page identities settle.
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 4
        ):
            raise SemanticGateClosed("construction queue snapshots are not coherent")
        if not back.actionable and not self._build_origin_queue_shell(button_state, ui_state):
            raise SemanticGateClosed("construction queue page identity is not proven")
        selected_tabs = self._toggle_matches(ui_state, "build/nav/queue")
        if len(selected_tabs) != 1 or not selected_tabs[0].checked:
            raise SemanticGateClosed("construction queue tab is not selected")
        capacity = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith("BuildShipDetailUI1(Clone)/title/value")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(capacity) != 1 or re.fullmatch(r"[1-9][0-9]*", capacity[0].text.strip()) is None:
            raise SemanticGateClosed("construction queue capacity is unexpected")
        # The title's concurrency/capacity value is not the number of rendered
        # queue rows (the baseline itself has value 2 with four queue rows).
        # Enumerate all active row identities across the complete endpoint so
        # a new slot cannot disappear from either timers or the empty proof.
        row_pattern = re.compile(
            r"BuildShipDetailUI1\(Clone\)/list_(single|mult)_line/"
            r"content/project_([1-9][0-9]*)(?:/|$)"
        )
        rows = set()
        for item in (*button_state.buttons, *ui_state.texts, *ui_state.images, *ui_state.toggles):
            if not item.active_in_hierarchy or not item.active_and_enabled:
                continue
            if re.search(r"BuildShipDetailUI1\(Clone\)/list_(?:single|mult)_line/content/project_", item.path):
                match = row_pattern.search(item.path)
                if match is None:
                    raise SemanticGateClosed("construction queue row identity is unsupported")
                rows.add(("single" if match.group(1) == "single" else "multi", int(match.group(2))))
        timer_patterns = {
            "single": re.compile(
                r"BuildShipDetailUI1\(Clone\)/list_single_line/content/"
                r"project_([1-9][0-9]*)/frame/buiding/timer/Text$"
            ),
            "multi": re.compile(
                r"BuildShipDetailUI1\(Clone\)/list_mult_line/content/"
                r"project_([1-9][0-9]*)/frame/buiding/timer/Text$"
            ),
        }
        timers_by_layout: Dict[str, Dict[int, str]] = {
            "single": {},
            "multi": {},
        }
        for item in ui_state.texts:
            layout_match = next(
                (
                    (layout, pattern.search(item.path))
                    for layout, pattern in timer_patterns.items()
                    if pattern.search(item.path) is not None
                ),
                None,
            )
            if layout_match is None:
                continue
            layout, match = layout_match
            assert match is not None
            if (
                not item.active_in_hierarchy
                or not item.active_and_enabled
                or item.truncated
                or item.bounds is None
            ):
                continue
            index = int(match.group(1))
            timers = timers_by_layout[layout]
            if index in timers:
                raise SemanticGateClosed("construction queue timer is ambiguous")
            value = item.text.strip()
            if (
                value != "99:99:99"
                and re.fullmatch(r"[0-9]{2}:[0-5][0-9]:[0-5][0-9]", value) is None
            ):
                raise SemanticGateClosed("construction queue timer is malformed")
            timers[index] = value
        observed = tuple(
            (layout, timers) for layout, timers in timers_by_layout.items() if timers
        )
        if not observed:
            quick_counts = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith("BuildShipDetailUI1(Clone)/quick_count/value")
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
                and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
            )
            if rows or len(quick_counts) != 1:
                raise SemanticGateClosed("construction queue timers are incomplete")
            return ()
        if len(observed) != 1:
            raise SemanticGateClosed("construction queue timers are incomplete")
        layout, timers = observed[0]
        expected = tuple(range(1, len(timers) + 1))
        if tuple(sorted(timers)) != expected or rows != {(layout, index) for index in expected}:
            raise SemanticGateClosed("construction queue timers are incomplete")
        return tuple(timers[index] for index in expected)

    def build_queue_empty(self) -> bool:
        timers = self.build_queue_timers()
        state = self.read_state()
        finished = tuple(
            button
            for button in state.buttons
            if button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.bounds is not None
            and re.search(
                r"BuildShipDetailUI1\(Clone\)/list_(?:single|mult)_line/content/"
                r"project_([1-9][0-9]*)/frame/finished/launched_btn$",
                button.path,
            )
            is not None
        )
        if finished:
            # A finished slot retains the sentinel timer on the pinned CN
            # client until the exact batch-launch action is taken.  Its active
            # ``launched_btn`` is authoritative nonempty queue state; otherwise
            # a four-slot completed batch would be mistaken for an empty queue.
            paths = {button.path for button in finished}
            if len(paths) != len(finished):
                raise SemanticGateClosed("construction finished slots are ambiguous")
            return False
        return all(value == "99:99:99" for value in timers)

    def build_queue_finish_prompt_cost(self) -> Optional[Tuple[int, int]]:
        """Return the exact quick-finish cost and owned count for one queue prompt."""

        state = self.read_state()
        confirm = self._matches(state, "build/queue/finish-confirm")
        cancel = self._matches(state, "build/queue/finish-cancel")
        if not confirm and not cancel:
            return None
        if len(confirm) != 1 or len(cancel) != 1:
            raise SemanticGateClosed("construction quick-finish prompt is ambiguous")
        if (
            not confirm[0].actionable
            or not cancel[0].actionable
            or self._blocking_rules(state, "build/queue/finish-confirm")
            or self._blocking_rules(state, "build/queue/finish-cancel")
        ):
            raise SemanticGateClosed("construction quick-finish prompt is not actionable")
        return self._build_queue_finish_prompt_cost(state)

    def build_queue_all_launch_available(self, *, allow_empty: bool = False) -> bool:
        """Prove the exact batch-finish control on a nonempty build queue."""

        if self.build_queue_empty() != allow_empty:
            return False
        state = self.read_state()
        control = self._unique(state, "build/queue/all-launch")
        if (
            not control.active_in_hierarchy
            or not control.active_and_enabled
            or not control.interactable
            or control.raycast_top is not None
            or control.point is None
            or control.bounds is None
            or not control.bounds.contains(control.point)
            or self._blocking_rules(state, "build/queue/all-launch")
        ):
            return False
        ui_state = self.read_ui_state()
        images = tuple(
            image
            for image in ui_state.images
            if image.path == control.path
            and image.name == "all_launch"
            and image.sprite == "btn_batch"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and image.raycast_top is None
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(control.point)
        )
        if len(images) > 1:
            raise SemanticGateClosed("construction batch-finish Image is ambiguous")
        return len(images) == 1

    def build_queue_all_launch_visible(self) -> bool:
        """Observe the batch button also when an empty queue disables its input."""
        self.build_queue_timers()
        state = self.read_state()
        controls = self._matches(state, "build/queue/all-launch")
        if len(controls) != 1:
            raise SemanticGateClosed("construction batch-finish control is absent or ambiguous")
        control = controls[0]
        if (not control.active_in_hierarchy or not control.active_and_enabled
                or control.point is None or control.bounds is None
                or not control.bounds.contains(control.point)
                or self._blocking_rules(state, "build/queue/all-launch")):
            return False
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 4:
            raise SemanticGateClosed("construction queue snapshots are not coherent")
        images = tuple(i for i in ui.images
            if i.path == control.path and i.name == "all_launch" and i.sprite == "btn_batch"
            and i.active_in_hierarchy and i.active_and_enabled and not i.truncated
            and i.bounds is not None and i.bounds.contains(control.point))
        if len(images) > 1:
            raise SemanticGateClosed("construction batch-finish Image is ambiguous")
        return len(images) == 1

    def click_build_empty_queue_return(self) -> ActionReceipt:
        """Use the native empty batch-button edge to return to construction."""
        if not self.build_queue_empty():
            raise SemanticGateClosed("construction empty-queue return requires an empty queue")
        return self.click_build_queue_all_launch(allow_empty=True)

    def click_build_queue_all_launch(self, *, allow_empty: bool = False) -> ActionReceipt:
        """Click the proven queue batch-finish control without pixel fallback."""

        if not self.build_queue_all_launch_available(allow_empty=allow_empty):
            raise SemanticGateClosed("construction batch-finish control is not proven")
        state = self.read_state()
        control = self._unique(state, "build/queue/all-launch")
        assert control.point is not None
        assert control.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before construction finish input")
        self._tap(int(round(control.point.x)), int(round(control.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after construction finish input")
        return ActionReceipt(
            semantic_id="build/queue/all-launch",
            generation=state.generation,
            point=control.point,
            bounds=control.bounds,
            path=control.path,
        )

    def _build_pool_delegated_raycast_proven(
        self,
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
    ) -> bool:
        expected_sprites = {
            "build/pool/event": "activity_unsel",
            "build/pool/light": "light_unsel",
            "build/pool/heavy": "heavy_unsel",
            "build/pool/special": "spec_unsel",
        }
        expected_sprite = expected_sprites.get(semantic_id)
        if expected_sprite is None:
            return False
        matches = self._toggle_matches(ui_state, semantic_id)
        if len(matches) > 1:
            raise SemanticGateClosed("construction pool Toggle is ambiguous")
        if not matches:
            return False
        toggle = matches[0]
        if (
            toggle.checked
            or toggle.raycast_top is not None
            or not toggle.active_in_hierarchy
            or not toggle.active_and_enabled
            or not toggle.interactable
            or toggle.point is None
            or toggle.bounds is None
            or not toggle.bounds.contains(toggle.point)
            or self._blocking_rules(button_state, semantic_id)
        ):
            return False

        # The live 9.7.10 construction-pool Toggle delegates its raycast to
        # the same-path Image.  The observer consequently reports no top
        # result on either component.  Admit only an unchecked, exact pool
        # Toggle with its exact unselected sprite while the pool start Button
        # proves the surrounding page.
        page_markers = tuple(
            button
            for button in button_state.buttons
            if button.name == "start_btn"
            and button.path.endswith(
                "BuildShipUI(Clone)/BuildShipPoolsPageUI(Clone)/gallery/start_btn"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        if len(page_markers) != 1:
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == toggle.path
            and image.name == "frame"
            and image.sprite == expected_sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and image.raycast_top is None
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(toggle.point)
        )
        if len(images) > 1:
            raise SemanticGateClosed("construction pool Image is ambiguous")
        return len(images) == 1

    def _build_warning_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        return bool(
            plain
            == "常驻UR兑换点数已达上限，未兑换UR角色前继续建造不能获得点数，是否继续建造？"
            and cancel == "取消"
            and confirm == "确定"
        )

    def _build_queue_finish_prompt_cost(
        self, state: OracleState
    ) -> Optional[Tuple[int, int]]:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return None
        plain, cancel, confirm = parts
        match = re.fullmatch(
            r"快速完成需要消耗([1-9][0-9]*)个快速完成工具\s*"
            r"剩余加速道具:\s*([0-9]+)个",
            plain,
        )
        if match is None or cancel != "取消" or confirm != "确定":
            return None
        required, owned = (int(match.group(1)), int(match.group(2)))
        if owned < required:
            raise SemanticGateClosed(
                "construction quick-finish resources are insufficient"
            )
        return required, owned
