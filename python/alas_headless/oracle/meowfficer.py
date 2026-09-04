"""Meowfficer for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, List, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    MeowfficerAcquisitionState,
    MeowfficerCatState,
    MeowfficerDockState,
    MeowfficerEnhanceState,
    MeowfficerFeedState,
    MeowfficerPurchaseState,
    MeowfficerQueueState,
    MeowfficerTrainingState,
    Point,
    UiState,
)
from .errors import SemanticGateClosed


class MeowfficerOracle:
    """Meowfficer operations sharing the oracle frame and input boundary."""

    def meowfficer_dock_state(self) -> MeowfficerDockState:
        """Read the Commander Cat dock counters without entering a sub-page."""

        button_state = self.read_state()
        controls = {
            semantic_id: self._matches(button_state, semantic_id)
            for semantic_id in (
                "meowfficer/fort/enter",
                "meowfficer/buy/enter",
                "meowfficer/train/enter",
            )
        }
        if any(len(matches) != 1 for matches in controls.values()):
            raise SemanticGateClosed("meowfficer dock identity is not proven")
        for semantic_id, matches in controls.items():
            control = matches[0]
            if (
                self._blocking_rules(button_state, semantic_id)
                or not control.active_in_hierarchy
                or not control.active_and_enabled
                or not control.interactable
                or control.raycast_top is not None
                or control.point is None
                or control.bounds is None
                or not control.bounds.contains(control.point)
            ):
                raise SemanticGateClosed("meowfficer dock control is not proven")

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.snapshot.get("text_truncated") is not False
        ):
            raise SemanticGateClosed("meowfficer dock snapshots are not coherent")
        root = "CommanderCatUI(Clone)/blur_panel/"
        suffixes = {
            "fort": root + "pages/CommanderCatDockUI(Clone)/box/home/Text",
            "training": root + "pages/CommanderCatDockUI(Clone)/box/boxes_btn/Text",
            "purchase": root + "pages/CommanderCatDockUI(Clone)/box/reserve_btn/Text",
            "capacity": root + "pages/CommanderCatDockUI(Clone)/box/capcity/Text",
            "coins": root + "top/res/gold/Text",
            "box_1": root + "top/res/1/Text",
            "box_2": root + "top/res/2/Text",
            "box_3": root + "top/res/3/Text",
        }
        values: Dict[str, str] = {}
        for key, suffix in suffixes.items():
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer counter is absent: " + key)
            values[key] = matches[0].text.strip()

        pairs: Dict[str, Tuple[int, int]] = {}
        for key in ("fort", "training", "purchase", "capacity"):
            match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", values[key])
            if match is None:
                raise SemanticGateClosed("meowfficer counter is malformed: " + key)
            pairs[key] = tuple(map(int, match.groups()))
            if pairs[key][0] > pairs[key][1]:
                raise SemanticGateClosed("meowfficer counter is inconsistent: " + key)
        scalars: Dict[str, int] = {}
        for key in ("coins", "box_1", "box_2", "box_3"):
            if re.fullmatch(r"[0-9]+", values[key]) is None:
                raise SemanticGateClosed("meowfficer resource is malformed: " + key)
            scalars[key] = int(values[key])
        return MeowfficerDockState(
            purchased=pairs["purchase"][0],
            purchase_total=pairs["purchase"][1],
            coins=scalars["coins"],
            capacity_used=pairs["capacity"][0],
            capacity_total=pairs["capacity"][1],
            fort_current=pairs["fort"][0],
            fort_total=pairs["fort"][1],
            training_finished=pairs["training"][0],
            training_total=pairs["training"][1],
            box_counts=(scalars["box_1"], scalars["box_2"], scalars["box_3"]),
        )

    def meowfficer_purchase_state(self) -> MeowfficerPurchaseState:
        """Read the exact reserve count and total coin price."""

        button_state = self.read_state()
        for semantic_id in (
            "meowfficer/buy/min",
            "meowfficer/buy/add",
            "meowfficer/buy/max",
            "meowfficer/buy/submit",
        ):
            matches = self._matches(button_state, semantic_id)
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer purchase identity is not proven")
            control = matches[0]
            if (
                self._blocking_rules(button_state, semantic_id)
                or not control.active_in_hierarchy
                or not control.active_and_enabled
                or not control.interactable
                or control.raycast_top is not None
                or control.point is None
                or control.bounds is None
                or not control.bounds.contains(control.point)
            ):
                raise SemanticGateClosed("meowfficer purchase control is not proven")

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.snapshot.get("text_truncated") is not False
        ):
            raise SemanticGateClosed("meowfficer purchase snapshots are not coherent")
        root = "CommanderReserveUI(Clone)/frame/bg1/"

        def exact_number(suffix: str) -> int:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(root + suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer purchase number is ambiguous")
            return int(matches[0].text.strip())

        count = exact_number("count/Text")
        total_price = exact_number("price_all/Text")
        if not 1 <= count <= 15 or total_price > 15 * 1500:
            raise SemanticGateClosed("meowfficer purchase values are inconsistent")
        return MeowfficerPurchaseState(
            generation=button_state.generation,
            count=count,
            total_price=total_price,
        )

    def _meowfficer_purchase_prompt_proven(
        self, button_state: ObserverState
    ) -> bool:
        controls = tuple(
            self._matches(button_state, semantic_id)
            for semantic_id in (
                "meowfficer/buy/cancel",
                "meowfficer/buy/confirm",
            )
        )
        if any(len(matches) != 1 for matches in controls):
            return False
        return all(
            not self._blocking_rules(button_state, semantic_id)
            and control.active_in_hierarchy
            and control.active_and_enabled
            and control.interactable
            and control.raycast_top is None
            and control.point is not None
            and control.bounds is not None
            and control.bounds.contains(control.point)
            for semantic_id, matches in zip(
                ("meowfficer/buy/cancel", "meowfficer/buy/confirm"), controls
            )
            for control in matches
        )

    def _meowfficer_purchase_skip_proven(
        self, button_state: ObserverState
    ) -> bool:
        matches = self._matches(button_state, "meowfficer/buy/skip")
        if len(matches) != 1:
            return False
        target = matches[0]
        return bool(
            not self._blocking_rules(button_state, "meowfficer/buy/skip")
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        )

    def _meowfficer_enhance_prompt_proven(
        self, button_state: ObserverState
    ) -> bool:
        """Prove the prompt nested under the reviewed enhancement surface."""

        semantic_ids = (
            "meowfficer/enhance/cancel",
            "meowfficer/enhance/confirm",
        )
        controls = tuple(self._matches(button_state, item) for item in semantic_ids)
        if any(len(matches) != 1 for matches in controls):
            return False
        return all(
            not self._blocking_rules(button_state, semantic_id)
            and control.active_in_hierarchy
            and control.active_and_enabled
            and control.interactable
            and control.raycast_top is None
            and control.point is not None
            and control.bounds is not None
            and control.bounds.contains(control.point)
            for semantic_id, matches in zip(semantic_ids, controls)
            for control in matches
        )

    def _meowfficer_reviewed_control_proven(
        self, button_state: ObserverState, semantic_id: str
    ) -> bool:
        matches = self._matches(button_state, semantic_id)
        if len(matches) != 1:
            return False
        target = matches[0]
        return bool(
            not self._blocking_rules(button_state, semantic_id)
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        )

    def _meowfficer_cat_states(
        self, button_state: ObserverState, ui_state: UiState
    ) -> Tuple[MeowfficerCatState, ...]:
        icon_pattern = re.compile(
            r"CommanderCatDockUI\(Clone\)/frame/content/(?:"
            r"[0-9]+/info|ComanderCatTpl(?:\(Clone\))?/info/icon)$"
        )
        level_pattern = re.compile(
            r"CommanderCatDockUI\(Clone\)/frame/content/(?:"
            r"[0-9]+/info/level_bg/Text|"
            r"ComanderCatTpl(?:\(Clone\))?/info/level_bg/Text)$"
        )
        selected_pattern = re.compile(
            r"CommanderCatDockUI\(Clone\)/frame/content/(?:"
            r"[0-9]+|ComanderCatTpl(?:\(Clone\))?)/up$"
        )
        icons = tuple(
            button
            for button in button_state.buttons
            if button.name in ("icon", "info")
            and icon_pattern.search(button.path)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        levels = tuple(
            item
            for item in ui_state.texts
            if level_pattern.search(item.path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and re.fullmatch(r"(?:LV\.)?([1-9][0-9]?)", item.text.strip())
        )
        selected = tuple(
            item
            for item in ui_state.images
            if selected_pattern.search(item.path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if not icons or len(icons) > 16 or len(levels) != len(icons):
            raise SemanticGateClosed("meowfficer cat grid is ambiguous")
        results: List[MeowfficerCatState] = []
        used_levels: Set[int] = set()
        for icon in icons:
            assert icon.bounds is not None and icon.point is not None
            matches = tuple(
                (index, item)
                for index, item in enumerate(levels)
                if index not in used_levels
                and item.bounds is not None
                and self._bounds_overlap(icon.bounds, item.bounds) > 0
            )
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer cat level mapping is ambiguous")
            level_index, level_item = matches[0]
            used_levels.add(level_index)
            level_match = re.fullmatch(
                r"(?:LV\.)?([1-9][0-9]?)", level_item.text.strip()
            )
            assert level_match is not None
            selected_matches = tuple(
                item
                for item in selected
                if item.bounds is not None
                and self._bounds_overlap(icon.bounds, item.bounds) > 0
            )
            if len(selected_matches) > 1:
                raise SemanticGateClosed("meowfficer selected marker is ambiguous")
            results.append(
                MeowfficerCatState(
                    path=icon.path,
                    level=int(level_match.group(1)),
                    selected=len(selected_matches) == 1,
                    point=icon.point,
                    bounds=icon.bounds,
                )
            )
        ordered = tuple(
            sorted(results, key=lambda item: (item.bounds.top, item.bounds.left))
        )
        if len({(item.bounds.left, item.bounds.top) for item in ordered}) != len(ordered):
            raise SemanticGateClosed("meowfficer cat positions are ambiguous")
        return ordered

    def meowfficer_dock_cats(self) -> Tuple[MeowfficerCatState, ...]:
        self.meowfficer_dock_state()
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            not button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
            or ui_state.snapshot.get("text_truncated") is not False
            or ui_state.snapshot.get("image_truncated") is not False
        ):
            raise SemanticGateClosed("meowfficer cat snapshots are not coherent")
        return self._meowfficer_cat_states(button_state, ui_state)

    def meowfficer_feed_state(self) -> MeowfficerFeedState:
        button_state = self.read_state()
        for semantic_id in ("meowfficer/feed/cancel", "meowfficer/feed/confirm"):
            matches = self._matches(button_state, semantic_id)
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer feed identity is not proven")
            target = matches[0]
            if (
                self._blocking_rules(button_state, semantic_id)
                or not target.active_in_hierarchy
                or not target.active_and_enabled
                or not target.interactable
                or target.raycast_top is not None
                or target.point is None
                or target.bounds is None
                or not target.bounds.contains(target.point)
            ):
                raise SemanticGateClosed("meowfficer feed control is not proven")
        ui_state = self.read_ui_state()
        if (
            not button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
            or ui_state.snapshot.get("text_truncated") is not False
            or ui_state.snapshot.get("image_truncated") is not False
        ):
            raise SemanticGateClosed("meowfficer feed snapshots are not coherent")
        counters = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith("CommanderCatDockUI(Clone)/bottom/value/Text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", item.text.strip())
        )
        if len(counters) != 1:
            raise SemanticGateClosed("meowfficer feed counter is ambiguous")
        match = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", counters[0].text.strip())
        assert match is not None
        selected, capacity = map(int, match.groups())
        if selected > capacity or capacity > 10:
            raise SemanticGateClosed("meowfficer feed counter is inconsistent")
        return MeowfficerFeedState(
            generation=button_state.generation,
            selected=selected,
            capacity=capacity,
            candidates=self._meowfficer_cat_states(button_state, ui_state),
        )

    def meowfficer_enhance_state(self) -> MeowfficerEnhanceState:
        button_state = self.read_state()
        for semantic_id in (
            "meowfficer/enhance/back",
            "meowfficer/feed/open",
        ):
            if not self._meowfficer_reviewed_control_proven(
                button_state, semantic_id
            ):
                raise SemanticGateClosed("meowfficer enhance control is not proven")
        ui_state = self.read_ui_state()
        if (
            not button_state.generation
            <= ui_state.generation
            <= button_state.generation + 2
            or ui_state.snapshot.get("text_truncated") is not False
        ):
            raise SemanticGateClosed("meowfficer enhance snapshots are not coherent")

        def exact_number(suffix: str, pattern: str) -> int:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and re.fullmatch(pattern, item.text.strip())
            )
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer enhance number is ambiguous")
            value = re.fullmatch(pattern, matches[0].text.strip())
            assert value is not None
            return int(value.group(1))

        level = exact_number(
            "CommanderCatPlayUI(Clone)/select_panel/exp_bg/level_bg/Text",
            r"(?:LV\.)?([1-9][0-9]?)",
        )
        coins = exact_number(
            "CommanderCatUI(Clone)/blur_panel/top/res/gold/Text", r"([0-9]+)"
        )
        if level > 30:
            raise SemanticGateClosed("meowfficer enhance level is inconsistent")
        return MeowfficerEnhanceState(
            generation=button_state.generation,
            level=level,
            coins=coins,
        )

    def click_meowfficer_cat(self, expected: MeowfficerCatState) -> ActionReceipt:
        if not isinstance(expected, MeowfficerCatState):
            raise TypeError("expected meowfficer cat state")
        try:
            candidates = self.meowfficer_feed_state().candidates
        except SemanticGateClosed:
            candidates = self.meowfficer_dock_cats()
        current = tuple(
            item
            for item in candidates
            if item.path == expected.path
            and item.bounds == expected.bounds
            and item.point == expected.point
        )
        if len(current) != 1:
            raise SemanticGateClosed("meowfficer cat identity changed before input")
        state = self.read_state()
        matches = tuple(
            button
            for button in state.buttons
            if button.path == expected.path
            and button.bounds == expected.bounds
            and button.point == expected.point
            and button.name in ("icon", "info")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
        )
        if len(matches) != 1:
            raise SemanticGateClosed("meowfficer cat target is no longer unique")
        if self._blocking_rules(state, "meowfficer/cat/select"):
            raise SemanticGateClosed("meowfficer cat input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before meowfficer cat input")
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="meowfficer/cat/select",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def meowfficer_training_state(self) -> MeowfficerTrainingState:
        """Read the exact training queue without image matching or OCR."""

        button_state = self.read_state()
        control_ids = (
            "meowfficer/train/close",
            "meowfficer/train/finish-all",
            "meowfficer/train/start",
        )
        for semantic_id in control_ids:
            matches = self._matches(button_state, semantic_id)
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer training identity is not proven")
            control = matches[0]
            if (
                self._blocking_rules(button_state, semantic_id)
                or not control.active_in_hierarchy
                or not control.active_and_enabled
                or not control.interactable
                or control.raycast_top is not None
                or control.point is None
                or control.bounds is None
                or not control.bounds.contains(control.point)
            ):
                raise SemanticGateClosed("meowfficer training control is not proven")

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.snapshot.get("text_truncated") is not False
        ):
            raise SemanticGateClosed("meowfficer training snapshots are not coherent")
        root = "CommanderBoxesUI(Clone)/frame/boxes/"

        def exact_text(suffix: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer training counter is ambiguous")
            return matches[0].text.strip()

        active_match = re.fullmatch(
            r"([0-9]+)/([1-9][0-9]*)",
            exact_text(root + "statistics/traning"),
        )
        waiting_match = re.fullmatch(
            r"([0-9]+)/([1-9][0-9]*)",
            exact_text(root + "statistics/wait"),
        )
        if active_match is None or waiting_match is None:
            raise SemanticGateClosed("meowfficer training counter is malformed")
        active, active_capacity = map(int, active_match.groups())
        waiting, waiting_capacity = map(int, waiting_match.groups())
        if active > active_capacity or waiting > waiting_capacity:
            raise SemanticGateClosed("meowfficer training counter is inconsistent")
        completed = sum(
            1
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and re.search(
                r"/CommanderBoxesUI\(Clone\)/frame/boxes/mask/content/"
                r"frame(?:\(Clone\))?/ongoing/time/Text$",
                item.path,
            )
            and item.text.strip() == "COMPLETE"
        )
        complete_buttons = self._matches(
            button_state, "meowfficer/train/complete/first"
        )
        if completed > 0 and len(complete_buttons) != 1:
            raise SemanticGateClosed("meowfficer completed training identity is inconsistent")
        return MeowfficerTrainingState(
            active_training=active,
            active_capacity=active_capacity,
            waiting=waiting,
            waiting_capacity=waiting_capacity,
            completed=completed,
        )

    def _meowfficer_get_continue_proven(self, button_state: ObserverState) -> bool:
        matches = self._matches(button_state, "meowfficer/get/continue")
        if len(matches) != 1:
            return False
        target = matches[0]
        if (
            self._blocking_rules(button_state, "meowfficer/get/continue")
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top is not None
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
            or ui_state.snapshot.get("text_truncated") is not False
            or ui_state.snapshot.get("image_truncated") is not False
        ):
            return False
        titles = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith("GetCommanderUI(Clone)/main/bg/Image")
            and item.text.strip() == "COMMAND MEOW"
        )
        rarities = tuple(
            item
            for item in ui_state.images
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith(
                "GetCommanderUI(Clone)/main/info/content/rarity/value"
            )
            and item.sprite in ("R", "SR", "SSR")
        )
        return len(titles) == 1 and len(rarities) == 1

    def _meowfficer_lock_toggle_proven(
        self, button_state: ObserverState, semantic_id: str
    ) -> bool:
        """Prove one exact lock-state toggle on the current acquisition card."""

        if semantic_id not in (
            "meowfficer/get/lock",
            "meowfficer/get/unlock",
        ):
            raise ValueError("unknown meowfficer lock toggle")
        if not self._meowfficer_get_continue_proven(button_state):
            return False
        actionable: Dict[str, Tuple[ButtonState, ...]] = {}
        for candidate in (
            "meowfficer/get/lock",
            "meowfficer/get/unlock",
        ):
            actionable[candidate] = tuple(
                target
                for target in self._matches(button_state, candidate)
                if not self._blocking_rules(button_state, candidate)
                and target.active_in_hierarchy
                and target.active_and_enabled
                and target.interactable
                and target.raycast_top is None
                and target.point is not None
                and target.bounds is not None
                and target.bounds.contains(target.point)
            )
        return bool(
            len(actionable[semantic_id]) == 1
            and sum(len(matches) for matches in actionable.values()) == 1
        )

    def meowfficer_acquisition_state(self) -> MeowfficerAcquisitionState:
        """Read rarity and talent tiers from the exact acquisition card."""

        button_state = self.read_state()
        if not self._meowfficer_get_continue_proven(button_state):
            raise SemanticGateClosed("meowfficer acquisition identity is not proven")
        ui_state = self.read_ui_state()
        root = "GetCommanderUI(Clone)/main/info/content/"

        def exact_text(suffix: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.path.endswith(root + suffix)
            )
            if len(matches) != 1 or not matches[0].text.strip():
                raise SemanticGateClosed("meowfficer acquisition text is ambiguous")
            return matches[0].text.strip()

        rarity_matches = tuple(
            item
            for item in ui_state.images
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith(root + "rarity/value")
            and item.sprite in ("R", "SR", "SSR")
        )
        talent_matches = tuple(
            item
            for item in ui_state.images
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and re.search(
                r"GetCommanderUI\(Clone\)/main/info/content/talents/"
                r"talent(?:\(Clone\))?/icon$",
                item.path,
            )
            and bool(item.sprite)
        )
        if len(rarity_matches) != 1 or not 1 <= len(talent_matches) <= 3:
            raise SemanticGateClosed("meowfficer acquisition fields are ambiguous")
        sprites = tuple(item.sprite for item in talent_matches)
        # Upstream defines a special talent as tierless or rainbow.  Ordinary
        # talent sprites have a reviewed numeric tier suffix.  Unknown/tierless
        # sprites are conservatively classified as special so retention cannot
        # be skipped silently.
        has_special = any(
            re.fullmatch(r"[A-Za-z0-9_]+_[123]", sprite) is None
            for sprite in sprites
        )
        return MeowfficerAcquisitionState(
            generation=button_state.generation,
            identity=exact_text("copyright/Text"),
            rarity=rarity_matches[0].sprite,
            talent_sprites=sprites,
            has_special_talent=has_special,
        )

    def _meowfficer_lock_prompt_proven(self, button_state: ObserverState) -> bool:
        controls = tuple(
            self._matches(button_state, semantic_id)
            for semantic_id in (
                "meowfficer/get/lock-cancel",
                "meowfficer/get/lock-confirm",
            )
        )
        if any(len(matches) != 1 for matches in controls):
            return False
        if any(
            self._blocking_rules(button_state, semantic_id)
            for semantic_id in (
                "meowfficer/get/lock-cancel",
                "meowfficer/get/lock-confirm",
            )
        ):
            return False
        if any(
            not control.active_in_hierarchy
            or not control.active_and_enabled
            or not control.interactable
            or control.raycast_top is not None
            or control.point is None
            or control.bounds is None
            or not control.bounds.contains(control.point)
            for matches in controls
            for control in matches
        ):
            return False
        ui_state = self.read_ui_state()
        prompts = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith(
                "GetCommanderUI(Clone)/CommanderMsgBoxUI(Clone)/frame/bg/content/Text"
            )
            and item.text.startswith("<color=#847D7B>")
            and "<color=#92fc63>" in item.text
        )
        return len(prompts) == 1

    def _meowfficer_get_result_proven(self, button_state: ObserverState) -> bool:
        matches = self._matches(button_state, "meowfficer/get/result/close")
        if len(matches) != 1:
            return False
        target = matches[0]
        if (
            self._blocking_rules(button_state, "meowfficer/get/result/close")
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top is not None
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False
        ui_state = self.read_ui_state()
        result_rows = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith(
                "GetCommanderResultUI(Clone)/frame/list1/tpl(Clone)/info/Text"
            )
            and bool(item.text.strip())
        )
        instructions = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith("GetCommanderResultUI(Clone)/frame/Text")
            and bool(item.text.strip())
        )
        return len(result_rows) >= 1 and len(instructions) == 1

    def meowfficer_queue_state(self) -> MeowfficerQueueState:
        button_state = self.read_state()
        for semantic_id in (
            "meowfficer/queue/auto",
            "meowfficer/queue/start",
            "meowfficer/queue/close",
        ):
            matches = self._matches(button_state, semantic_id)
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer queue identity is not proven")
            control = matches[0]
            if (
                self._blocking_rules(button_state, semantic_id)
                or not control.active_in_hierarchy
                or not control.active_and_enabled
                or not control.interactable
                or control.raycast_top is not None
                or control.point is None
                or control.bounds is None
                or not control.bounds.contains(control.point)
            ):
                raise SemanticGateClosed("meowfficer queue control is not proven")
        ui_state = self.read_ui_state()

        def exact_text(suffix: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.path.endswith(suffix)
            )
            if len(matches) != 1:
                raise SemanticGateClosed("meowfficer queue text is ambiguous")
            return matches[0].text.strip()

        root = "CommanderBuildPoolUI(Clone)/"
        counter = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", exact_text(root + "statistics/Text"))
        if counter is None:
            raise SemanticGateClosed("meowfficer queue counter is malformed")
        selected, capacity = map(int, counter.groups())
        if selected > capacity:
            raise SemanticGateClosed("meowfficer queue counter is inconsistent")
        counts = tuple(
            int(exact_text(root + "frame/bg/content/list/{0}/Text".format(index)))
            for index in (1, 2, 3)
        )
        return MeowfficerQueueState(
            selected=selected,
            capacity=capacity,
            box_counts=counts,
        )

    def _meowfficer_fort_close_proven(self, button_state: ObserverState) -> bool:
        matches = self._matches(button_state, "meowfficer/fort/close")
        if len(matches) != 1:
            return False
        target = matches[0]
        if (
            self._blocking_rules(button_state, "meowfficer/fort/close")
            or not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.raycast_top is not None
            or target.point is None
            or target.bounds is None
            or not target.bounds.contains(target.point)
        ):
            return False
        ui_state = self.read_ui_state()
        counters = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith("CommanderHomeUI(Clone)/bg/frame/cnt/Text")
            and re.fullmatch(r"[0-9]+/[1-9][0-9]*", item.text.strip())
        )
        levels = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith("CommanderHomeUI(Clone)/bg/frame/title/Text")
            and re.fullmatch(r"LV\.[1-9][0-9]*", item.text.strip())
        )
        return len(counters) == 1 and len(levels) == 1

    def meowfficer_fort_chore_paths(self) -> Tuple[str, ...]:
        """Return exact actionable Fort chore buttons in stable path order."""

        button_state = self.read_state()
        if not self._meowfficer_fort_close_proven(button_state):
            raise SemanticGateClosed("meowfficer Fort identity is not proven")
        pattern = re.compile(
            r"CommanderHomeUI\(Clone\)/bg/frame/scrollrect/content/"
            r"tpl(?:\(Clone\))?/unlock/bubble/(play|feed|clean)$"
        )
        chores = tuple(
            sorted(
                button.path
                for button in button_state.buttons
                if pattern.search(button.path)
                and button.name in ("play", "feed", "clean")
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.raycast_top is None
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            )
        )
        if len(chores) != len(set(chores)) or len(chores) > 8:
            raise SemanticGateClosed("meowfficer Fort chores are ambiguous")
        return chores

    def click_meowfficer_fort_chore(self, expected_path: str) -> ActionReceipt:
        """Click one still-actionable Fort chore selected from the typed state."""

        if not isinstance(expected_path, str) or not expected_path:
            raise ValueError("meowfficer Fort chore path must be text")
        state = self.read_state()
        if not self._meowfficer_fort_close_proven(state):
            raise SemanticGateClosed("meowfficer Fort identity is not proven")
        matches = tuple(
            button
            for button in state.buttons
            if button.path == expected_path
            and button.name in ("play", "feed", "clean")
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("meowfficer Fort chore is no longer actionable")
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before meowfficer Fort chore")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="meowfficer/fort/chore/" + target.name,
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _meowfficer_queue_prompt_proven(self, button_state: ObserverState) -> bool:
        controls = tuple(
            self._matches(button_state, semantic_id)
            for semantic_id in (
                "meowfficer/queue/cancel",
                "meowfficer/queue/confirm",
            )
        )
        if any(len(matches) != 1 for matches in controls):
            return False
        if any(
            not control.active_in_hierarchy
            or not control.active_and_enabled
            or not control.interactable
            or control.raycast_top is not None
            or control.point is None
            or control.bounds is None
            or not control.bounds.contains(control.point)
            for matches in controls
            for control in matches
        ):
            return False
        ui_state = self.read_ui_state()
        queue_counts = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith("CommanderBuildPoolUI(Clone)/statistics/Text")
            and re.fullmatch(r"([1-9][0-9]*)/\1", item.text.strip())
        )
        if len(queue_counts) != 1:
            return False
        selected = int(queue_counts[0].text.strip().split("/", 1)[0])
        prompts = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.path.endswith("CommanderMsgBoxUI(Clone)/frame/bg/content/Text")
            and item.text.startswith("<color=#847D7B>")
            and item.text.endswith("</color>")
            and re.findall(r"[0-9]+", re.sub(r"<[^>]+>", "", item.text))
            == [str(selected)]
        )
        selected_boxes = tuple(
            item
            for item in ui_state.images
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and "CommanderBuildPoolUI(Clone)/frame/bg/content/queue/" in item.path
            and item.path.endswith("/icon")
            and item.sprite in ("R1", "sr1", "ssr1")
        )
        return len(prompts) == 1 and len(selected_boxes) == selected
