"""Raid for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    OracleState,
    Point,
    RaidMultipleSortieState,
    RaidRemainState,
    UiState,
)
from .errors import SemanticGateClosed


class RaidOracle:
    """Raid operations sharing the oracle frame and input boundary."""

    def _main_raid_entry_proven(self, state: OracleState) -> bool:
        """Prove the current main-page raid shortcut with its typed icon.

        The activity shortcuts live on the overlay canvas where the observer
        cannot always resolve a top raycast.  Keep that uncertainty local to
        the exact generic raid button and require the matching visible
        ``event_boss`` image to cover the same actionable rectangle.
        """

        target = self._matches(state, "main/raid")
        battle = self._matches(state, "main/battle")
        formation = self._matches(state, "main/formation")
        if not (
            len(target) == 1
            and len(battle) == 1
            and len(formation) == 1
            and battle[0].active_in_hierarchy
            and formation[0].active_in_hierarchy
        ):
            return False
        button = target[0]
        if not (
            button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is None
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        ):
            return False

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed("main raid entry snapshots are not coherent")
        images = tuple(
            image
            for image in ui_state.images
            if image.path == button.path + "/Image"
            and image.sprite == "event_boss"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and image.raycast_top is None
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
            and image.bounds.contains(button.point)
        )
        if len(images) != 1:
            return False
        button_area = (button.bounds.right - button.bounds.left) * (
            button.bounds.bottom - button.bounds.top
        )
        return self._bounds_overlap(button.bounds, images[0].bounds) >= button_area * 0.99

    def raid_remain_state(self, event: str, mode: str) -> RaidRemainState:
        """Read one reviewed RaidDaily counter from typed Unity state."""

        if event == "raid_20260827":
            if mode not in ("easy", "normal", "hard", "ex"):
                raise SemanticGateClosed("Raid remaining counter mode is unsupported")
            return self._retry_transition_read(
                lambda: self._amatsukaze_raid_remain_state(mode),
                attempts=8,
            )
        if event != "raid_20260212":
            raise SemanticGateClosed("Raid remaining counter event is unsupported")
        node_ids = {"easy": 5001, "normal": 5002, "hard": 5003, "ex": 5004}
        try:
            node_id = node_ids[mode]
        except KeyError as exc:
            raise SemanticGateClosed("Raid remaining counter mode is unsupported") from exc

        button_state = self.read_state()
        ui_state = self.read_text_state()
        if not (
            button_state.generation <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("Raid button and text generations are incoherent")

        root_suffix = "/BossRushVerSardiniaSPUI(Clone)"
        node_pattern = re.compile(
            r"(?P<root>.+/BossRushVerSardiniaSPUI\(Clone\))"
            r"/Battle/Nodes/(?P<node>500[1-5])(?:/.*)?$"
        )
        family_buttons = tuple(
            button
            for button in button_state.buttons
            if "/BossRush" in button.path
            and "/Battle/Nodes/" in button.path
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        parsed_buttons = []
        for button in family_buttons:
            match = node_pattern.fullmatch(button.path)
            if match is None or not match.group("root").endswith(root_suffix):
                raise SemanticGateClosed("Raid stage button root is not reviewed")
            parsed_buttons.append((match.group("root"), int(match.group("node")), button))
        roots = {root for root, _node, _button in parsed_buttons}
        if len(roots) != 1:
            raise SemanticGateClosed("Raid stage root is absent or ambiguous")
        root = next(iter(roots))

        stage_buttons = tuple(
            button
            for candidate_root, candidate_node, button in parsed_buttons
            if candidate_root == root
            and candidate_node == node_id
            and button.path == f"{root}/Battle/Nodes/{node_id}"
        )
        if len(stage_buttons) != 1 or stage_buttons[0].bounds is None:
            raise SemanticGateClosed("Raid stage identity is absent or ambiguous")

        prefix = f"{root}/Battle/Nodes/{node_id}/"
        texts = tuple(
            item
            for item in ui_state.texts
            if item.path.startswith(prefix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if mode == "ex":
            expected_path = prefix + "times/Text"
            counters = tuple(
                item
                for item in texts
                if item.path == expected_path
                and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
            )
            capacity = None
        else:
            counters = tuple(
                item
                for item in texts
                if re.fullmatch(r"[0-9]+\s*/\s*15", item.text.strip()) is not None
            )
            capacity = 15
        if len(counters) != 1:
            raise SemanticGateClosed("Raid remaining counter is absent or ambiguous")
        counter = counters[0]
        if mode == "ex":
            remaining = int(counter.text.strip())
        else:
            remaining = int(counter.text.split("/", 1)[0].strip())
            if remaining > 15:
                raise SemanticGateClosed("Raid remaining counter exceeds capacity")
        return RaidRemainState(
            generation=ui_state.generation,
            event=event,
            mode=mode,
            remaining=remaining,
            capacity=capacity,
            root=root,
            node_id=node_id,
        )

    def _amatsukaze_raid_page_state(
        self,
    ) -> Tuple[OracleState, UiState, str, Dict[str, ButtonState]]:
        """Prove the 2026-08-27 Raid page and its five distinct stage slots.

        The first four slots belong to the existing ALAS Raid state machine.
        Slot five is the update's separate advanced challenge and is proven only
        so it cannot be confused with EX; it is deliberately not actionable.
        """

        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if not (
            button_state.generation <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("current Raid button and UI snapshots are incoherent")

        fleet_root = "OverlayCamera/Overlay/UIMain/ActivityBossFleetSelectView(Clone)"
        if any(
            button.path.startswith(fleet_root + "/")
            and button.active_in_hierarchy
            and button.active_and_enabled
            for button in button_state.buttons
        ):
            raise SemanticGateClosed("current Raid page is obscured by fleet selection")
        precombat_roots = (
            "UICamera/Canvas/UIOrigin/ActivityBossPrecombatUI(Clone)",
            "OverlayCamera/Overlay/UIMain/ActivityBossPrecombatUI(Clone)",
        )
        if any(
            any(button.path.startswith(root + "/") for root in precombat_roots)
            and button.active_in_hierarchy
            and button.active_and_enabled
            for button in button_state.buttons
        ):
            raise SemanticGateClosed("current Raid page is obscured by precombat")

        story_roots = tuple(
            button
            for button in button_state.buttons
            if button.path.endswith("Overlay/UIOverlay/NewStoryUI(Clone)")
            and button.name == "NewStoryUI(Clone)"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if story_roots:
            story_skips = self._matches(button_state, "story/skip")
            if (
                len(story_roots) == 1
                and len(story_skips) == 1
            ):
                # Hide the underlay from Page.iter_pages() so the original
                # ALAS ui_additional()->handle_story_skip() loop owns this
                # event-story transition.
                raise SemanticGateClosed(
                    "current Raid page is obscured by event story"
                )
            raise SemanticGateClosed("current Raid event story overlay is malformed")

        root = "UICamera/Canvas/UIMain/ActivityBossAmatsukazeUI(Clone)"
        title_path = root + "/adapt/top/TopPage/top/deco/Text/Text_1"
        titles = tuple(
            item
            for item in ui_state.texts
            if item.path == title_path
            and item.text.strip() == "JOINT OPERATION"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if not titles:
            raise SemanticGateClosed("current Raid page is absent")
        if len(titles) != 1:
            raise SemanticGateClosed("current Raid page title is ambiguous")

        modes = ("easy", "normal", "hard", "ex", "advanced")
        buttons: Dict[str, ButtonState] = {}
        for index, candidate_mode in enumerate(modes, start=1):
            path = f"{root}/adapt/right/{index}"
            matches = tuple(
                button
                for button in button_state.buttons
                if button.name == str(index)
                and button.path == path
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.raycast_top in (True, None)
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "current Raid stage identity is absent or ambiguous"
                )
            buttons[candidate_mode] = matches[0]

        expected_images = {
            root + "/adapt/right/1": "btn_lv_bg",
            root + "/adapt/right/1/lv": "btn_lv_easy",
            root + "/adapt/right/2": "btn_lv_bg",
            root + "/adapt/right/2/lv": "btn_lv_normal",
            root + "/adapt/right/3": "btn_lv_bg",
            root + "/adapt/right/3/lv": "btn_lv_hard",
            root + "/adapt/right/4": "btn_lv_ex",
            root + "/adapt/right/5": "btn_lv_sp",
        }
        images = tuple(
            image
            for image in ui_state.images
            if image.path in expected_images
            and image.sprite == expected_images[image.path]
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if (
            len(images) != len(expected_images)
            or {image.path for image in images} != set(expected_images)
        ):
            raise SemanticGateClosed("current Raid stage sprites are absent or ambiguous")

        image_by_path = {image.path: image for image in images}
        for index, candidate_mode in enumerate(modes, start=1):
            button = buttons[candidate_mode]
            assert button.bounds is not None
            image = image_by_path[f"{root}/adapt/right/{index}"]
            assert image.bounds is not None
            button_area = (button.bounds.right - button.bounds.left) * (
                button.bounds.bottom - button.bounds.top
            )
            if self._bounds_overlap(button.bounds, image.bounds) < button_area * 0.99:
                raise SemanticGateClosed("current Raid stage sprite does not cover its button")
        return button_state, ui_state, root, buttons

    def _amatsukaze_raid_remain_state(self, mode: str) -> RaidRemainState:
        node_ids = {"easy": 1, "normal": 2, "hard": 3, "ex": 4}
        try:
            node_id = node_ids[mode]
        except KeyError as exc:
            raise SemanticGateClosed("Raid remaining counter mode is unsupported") from exc

        _button_state, ui_state, root, _buttons = self._amatsukaze_raid_page_state()
        if mode == "ex":
            counter_path = root + "/adapt/top/ticket/Text"
            ticket_image_path = root + "/adapt/top/ticket"
            ticket_label_path = ticket_image_path + "/Desc"
            ticket_images = tuple(
                image
                for image in ui_state.images
                if image.path == ticket_image_path
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
            )
            ticket_labels = tuple(
                item
                for item in ui_state.texts
                if item.path == ticket_label_path
                and item.text.strip() == "特别挑战券"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            pattern = r"[0-9]{1,3}"
            capacity = None
        else:
            counter_path = f"{root}/adapt/right/{node_id}/Text"
            ticket_images = (True,)
            ticket_labels = (True,)
            pattern = r"([0-9]|1[0-5])\s*/\s*15"
            capacity = 15
        counters = tuple(
            item
            for item in ui_state.texts
            if item.path == counter_path
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and re.fullmatch(pattern, item.text.strip()) is not None
        )
        if mode != "ex" and not counters:
            def hidden_zero_signature(candidate: UiState) -> Tuple[Optional[str], ...]:
                ticket_path = root + "/adapt/top/ticket"
                health_images = tuple(
                    image
                    for image in candidate.images
                    if image.path == ticket_path
                    and image.active_in_hierarchy
                    and image.active_and_enabled
                    and not image.truncated
                    and image.bounds is not None
                )
                health_texts = {
                    ticket_path + "/Text": r"[0-9]{1,3}",
                    ticket_path + "/Desc": r"特别挑战券",
                    root + "/adapt/right/ptaward/Text": r"[0-9]+",
                }
                for path, health_pattern in health_texts.items():
                    matches = tuple(
                        item
                        for item in candidate.texts
                        if item.path == path
                        and item.active_in_hierarchy
                        and item.active_and_enabled
                        and not item.truncated
                        and item.bounds is not None
                        and re.fullmatch(health_pattern, item.text.strip()) is not None
                    )
                    if len(matches) != 1:
                        raise SemanticGateClosed(
                            "current Raid hidden-zero text health is not proven"
                        )
                if len(health_images) != 1:
                    raise SemanticGateClosed(
                        "current Raid hidden-zero image health is not proven"
                    )

                values: List[Optional[str]] = []
                for ordinary_node in (1, 2, 3):
                    ordinary_path = f"{root}/adapt/right/{ordinary_node}/Text"
                    items = tuple(
                        item
                        for item in candidate.texts
                        if item.path == ordinary_path
                        and item.active_in_hierarchy
                        and item.active_and_enabled
                        and not item.truncated
                        and item.bounds is not None
                    )
                    if len(items) > 1:
                        raise SemanticGateClosed(
                            "current Raid ordinary counter is ambiguous"
                        )
                    if not items:
                        values.append(None)
                        continue
                    value = items[0].text.strip()
                    if re.fullmatch(r"([0-9]|1[0-5])\s*/\s*15", value) is None:
                        raise SemanticGateClosed(
                            "current Raid ordinary counter is malformed"
                        )
                    values.append(re.sub(r"\s+", "", value))
                return tuple(values)

            first_signature = hidden_zero_signature(ui_state)
            if first_signature[node_id - 1] is not None:
                raise SemanticGateClosed(
                    "current Raid remaining counter is absent or ambiguous"
                )
            self._sleep(0.25)
            _second_buttons, second_ui, second_root, _second_stage_buttons = (
                self._amatsukaze_raid_page_state()
            )
            second_signature = hidden_zero_signature(second_ui)
            if not (
                second_root == root
                and second_ui.generation > ui_state.generation
                and second_signature == first_signature
                and second_signature[node_id - 1] is None
            ):
                raise SemanticGateClosed(
                    "current Raid hidden-zero state is not stable"
                )
            return RaidRemainState(
                generation=second_ui.generation,
                event="raid_20260827",
                mode=mode,
                remaining=0,
                capacity=capacity,
                root=root,
                node_id=node_id,
            )
        if (
            len(ticket_images) != 1
            or len(ticket_labels) != 1
            or len(counters) != 1
        ):
            raise SemanticGateClosed("current Raid remaining counter is absent or ambiguous")
        value = counters[0].text.strip()
        remaining = int(value if mode == "ex" else value.split("/", 1)[0].strip())
        return RaidRemainState(
            generation=ui_state.generation,
            event="raid_20260827",
            mode=mode,
            remaining=remaining,
            capacity=capacity,
            root=root,
            node_id=node_id,
        )

    def raid_page_visible(self, event: str) -> bool:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid page event is unsupported")
        try:
            self._amatsukaze_raid_page_state()
        except SemanticGateClosed as exc:
            if str(exc) in (
                "current Raid page is absent",
                "current Raid page is obscured by fleet selection",
                "current Raid page is obscured by precombat",
                "current Raid page is obscured by event story",
            ):
                return False
            raise
        return True

    def click_raid_stage(self, event: str, mode: str) -> ActionReceipt:
        """Click one current Raid slot after exact page and mode proof."""

        if event != "raid_20260827":
            raise SemanticGateClosed("Raid stage event is unsupported")
        button_state, _ui_state, _root, buttons = self._amatsukaze_raid_page_state()
        if mode not in ("easy", "normal", "hard", "ex"):
            raise SemanticGateClosed("Raid stage mode is unsupported")
        target = buttons[mode]
        if self._blocking_rules(button_state, f"raid/stage/{mode}"):
            raise SemanticGateClosed("Raid stage input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.point is not None
        assert target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=f"raid/stage/{mode}",
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_raid_advanced_challenge(self, event: str) -> ActionReceipt:
        """Open the separate fifth current-Raid slot without treating it as EX."""

        if event != "raid_20260827":
            raise SemanticGateClosed("Raid advanced-challenge event is unsupported")
        button_state, _ui_state, _root, buttons = self._amatsukaze_raid_page_state()
        target = buttons["advanced"]
        if self._blocking_rules(button_state, "raid/advanced/entry"):
            raise SemanticGateClosed("Raid advanced-challenge input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.point is not None
        assert target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="raid/advanced/entry",
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_raid_home(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid page event is unsupported")
        button_state, ui_state, root, _buttons = self._amatsukaze_raid_page_state()
        path = root + "/adapt/top/TopPage/top/btn_home"
        targets = tuple(
            button
            for button in button_state.buttons
            if button.path == path
            and button.name == "btn_home"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top in (True, None)
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        images = tuple(
            image
            for image in ui_state.images
            if image.path == path
            and image.sprite == "btn_home"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if len(targets) != 1 or len(images) != 1:
            raise SemanticGateClosed("Raid home control is absent or ambiguous")
        target = targets[0]
        assert target.bounds is not None
        assert images[0].bounds is not None
        button_area = (target.bounds.right - target.bounds.left) * (
            target.bounds.bottom - target.bounds.top
        )
        if self._bounds_overlap(target.bounds, images[0].bounds) < button_area * 0.99:
            raise SemanticGateClosed("Raid home image does not cover its control")
        if self._blocking_rules(button_state, "raid/page/home"):
            raise SemanticGateClosed("Raid home input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="raid/page/home",
            generation=button_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _amatsukaze_raid_fleet_selection_state(
        self,
    ) -> Tuple[OracleState, UiState, Dict[str, ButtonState]]:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if not (
            button_state.generation <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("Raid fleet-selection snapshots are incoherent")
        root = "OverlayCamera/Overlay/UIMain/ActivityBossFleetSelectView(Clone)/panel"
        paths = {
            "back": root + "/btnBack",
            "start": root + "/start_button",
        }
        buttons: Dict[str, ButtonState] = {}
        for key, path in paths.items():
            matches = tuple(
                button
                for button in button_state.buttons
                if button.path == path
                and button.name == path.rsplit("/", 1)[-1]
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.raycast_top in (True, None)
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "Raid fleet-selection control is absent or ambiguous"
                )
            buttons[key] = matches[0]
        titles = tuple(
            item
            for item in ui_state.texts
            if item.path == root + "/title/Image/text/text (1)"
            and item.text.strip() == "FLEET SELECT"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        expected_images = {
            paths["back"]: "x_butten",
            paths["start"]: "qianwang_button",
        }
        images = tuple(
            image
            for image in ui_state.images
            if image.path in expected_images
            and image.sprite == expected_images[image.path]
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if (
            len(titles) != 1
            or len(images) != len(expected_images)
            or {image.path for image in images} != set(expected_images)
        ):
            raise SemanticGateClosed("Raid fleet-selection identity is incomplete")
        image_by_path = {image.path: image for image in images}
        for key, button in buttons.items():
            assert button.bounds is not None
            image = image_by_path[paths[key]]
            assert image.bounds is not None
            button_area = (button.bounds.right - button.bounds.left) * (
                button.bounds.bottom - button.bounds.top
            )
            if self._bounds_overlap(button.bounds, image.bounds) < button_area * 0.99:
                raise SemanticGateClosed(
                    "Raid fleet-selection image does not cover its control"
                )
        return button_state, ui_state, buttons

    def raid_fleet_selection_visible(self, event: str) -> bool:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid fleet-selection event is unsupported")
        try:
            self._amatsukaze_raid_fleet_selection_state()
        except SemanticGateClosed as exc:
            if str(exc) == "Raid fleet-selection control is absent or ambiguous":
                return False
            raise
        return True

    def raid_fleet_ready(self, event: str) -> bool:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid fleet-selection event is unsupported")
        button_state, _ui_state, _buttons = (
            self._amatsukaze_raid_fleet_selection_state()
        )
        root = (
            "OverlayCamera/Overlay/UIMain/ActivityBossFleetSelectView(Clone)/"
            "panel/fleet/1"
        )
        for group in ("main", "vanguard"):
            prefix = root + "/" + group + "/"
            slots = tuple(
                button
                for button in button_state.buttons
                if button.path.startswith(prefix)
                and button.name in ("shiptpl(Clone)", "emptytpl(Clone)")
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.interactable
                and button.raycast_top in (True, None)
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            )
            if len(slots) != 3:
                raise SemanticGateClosed(
                    "Raid fleet-selection slot identity is incomplete"
                )
            if not any(button.name == "shiptpl(Clone)" for button in slots):
                return False
        return True

    def click_raid_fleet_back(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid fleet-selection event is unsupported")
        button_state, _ui_state, buttons = self._amatsukaze_raid_fleet_selection_state()
        target = buttons["back"]
        if self._blocking_rules(button_state, "raid/fleet/back"):
            raise SemanticGateClosed("Raid fleet-selection back input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.point is not None
        assert target.bounds is not None
        # ActivityBossFleetSelectView anchors btnBack at its top-right edge;
        # Unity ignores that boundary point even though it belongs to the
        # RectTransform.  Its exact image and rectangle were proven above.
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="raid/fleet/back",
            generation=button_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_raid_fleet_start(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid fleet-selection event is unsupported")
        button_state, _ui_state, buttons = self._amatsukaze_raid_fleet_selection_state()
        target = buttons["start"]
        if self._blocking_rules(button_state, "raid/fleet/start"):
            raise SemanticGateClosed("Raid fleet-selection start input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="raid/fleet/start",
            generation=button_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_raid_fleet_recommend(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid fleet-selection event is unsupported")
        button_state, ui_state, _buttons = (
            self._amatsukaze_raid_fleet_selection_state()
        )
        path = (
            "OverlayCamera/Overlay/UIMain/ActivityBossFleetSelectView(Clone)/"
            "panel/fleet/1/btn_recom"
        )
        targets = tuple(
            button
            for button in button_state.buttons
            if button.path == path
            and button.name == "btn_recom"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top in (True, None)
            and button.bounds is not None
            and button.point is not None
            and button.bounds.contains(button.point)
        )
        images = tuple(
            image
            for image in ui_state.images
            if image.path == path
            and image.sprite == "tuijian_butten"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if len(targets) != 1 or len(images) != 1:
            raise SemanticGateClosed(
                "Raid fleet-selection recommend control is absent or ambiguous"
            )
        target = targets[0]
        assert target.bounds is not None
        assert images[0].bounds is not None
        button_area = (target.bounds.right - target.bounds.left) * (
            target.bounds.bottom - target.bounds.top
        )
        if self._bounds_overlap(target.bounds, images[0].bounds) < button_area * 0.99:
            raise SemanticGateClosed(
                "Raid fleet-selection recommend image does not cover its control"
            )
        if self._blocking_rules(button_state, "raid/fleet/recommend"):
            raise SemanticGateClosed("Raid fleet-selection recommend input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="raid/fleet/recommend",
            generation=button_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _amatsukaze_raid_precombat_state(
        self,
    ) -> Tuple[OracleState, UiState, ButtonState]:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if not (
            button_state.generation <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("Raid precombat snapshots are incoherent")
        roots = (
            "UICamera/Canvas/UIOrigin/ActivityBossPrecombatUI(Clone)",
            "OverlayCamera/Overlay/UIMain/ActivityBossPrecombatUI(Clone)",
        )
        starts = tuple(
            (root, button)
            for root in roots
            for button in button_state.buttons
            if button.path == root + "/adapt/right/start"
            and button.name == "start"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top in (True, None)
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if not starts:
            raise SemanticGateClosed("Raid precombat page is absent")
        if len(starts) != 1:
            raise SemanticGateClosed("Raid precombat start control is ambiguous")
        root, target = starts[0]
        start_path = root + "/adapt/right/start"
        exact_texts = {
            start_path + "/text_en": "WEIGH ANCHOR",
            start_path + "/text": "出击",
            start_path + "/cost_container/title": "消耗：",
            root + "/adapt/middle/gear_score/main/line/Image/Text2": "MAIN",
            root + "/adapt/middle/gear_score/vanguard/line/Image/Text2": "VANGUARD",
        }
        matched_texts = tuple(
            item
            for item in ui_state.texts
            if item.path in exact_texts
            and item.text.strip() == exact_texts[item.path]
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        numeric_paths = (
            start_path + "/cost_container/popup/Text",
            root + "/adapt/middle/gear_score/main/Text",
            root + "/adapt/middle/gear_score/vanguard/Text",
        )
        numeric_texts = tuple(
            item
            for item in ui_state.texts
            if item.path in numeric_paths
            and re.fullmatch(r"[0-9]+", item.text.strip()) is not None
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        ordinary_paths = {
            start_path + "/bonus/title",
            start_path + "/bonus/Text",
        }
        ordinary_texts = tuple(
            item
            for item in ui_state.texts
            if item.path in ordinary_paths
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        ordinary_complete = (
            len(ordinary_texts) == 2
            and {item.path for item in ordinary_texts} == ordinary_paths
            and next(
                item.text.strip()
                for item in ordinary_texts
                if item.path == start_path + "/bonus/title"
            )
            == "额外收益次数："
            and re.fullmatch(
                r"[0-9]+",
                next(
                    item.text.strip()
                    for item in ordinary_texts
                    if item.path == start_path + "/bonus/Text"
                ),
            )
            is not None
        )
        ex_paths = {
            start_path + "/ticket/title",
            start_path + "/ticket/Text",
        }
        ex_texts = tuple(
            item
            for item in ui_state.texts
            if item.path in ex_paths
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        ex_image_sprites = {
            start_path + "/ticket/icon": "nvpu_ticket",
            start_path + "/ticket/checkbox": "check_frame_bg",
            start_path + "/ticket/bg": "frame_bg",
        }
        ex_images = tuple(
            image
            for image in ui_state.images
            if image.path in ex_image_sprites
            and image.sprite == ex_image_sprites[image.path]
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        ex_complete = (
            len(ex_texts) == 2
            and {item.path for item in ex_texts} == ex_paths
            and next(
                item.text.strip()
                for item in ex_texts
                if item.path == start_path + "/ticket/title"
            )
            == "使用"
            and re.fullmatch(
                r"[0-9]+/[0-9]+",
                next(
                    item.text.strip()
                    for item in ex_texts
                    if item.path == start_path + "/ticket/Text"
                ),
            )
            is not None
            and len(ex_images) == len(ex_image_sprites)
            and {image.path for image in ex_images} == set(ex_image_sprites)
        )
        heroes = tuple(
            button
            for button in button_state.buttons
            if button.path.startswith(root + "/adapt/middle/HeroContainer/info/")
            and button.path.endswith("_root/mouseChild")
            and button.name == "mouseChild"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.bounds is not None
        )
        start_images = tuple(
            image
            for image in ui_state.images
            if image.path == start_path
            and image.sprite == "btn_formation_sel"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        oil_images = tuple(
            image
            for image in ui_state.images
            if image.path == start_path + "/cost_container/popup/icon"
            and image.sprite == "res_oil"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if (
            len(matched_texts) != len(exact_texts)
            or {item.path for item in matched_texts} != set(exact_texts)
            or len(numeric_texts) != len(numeric_paths)
            or {item.path for item in numeric_texts} != set(numeric_paths)
            or ordinary_complete == ex_complete
            or (ordinary_complete and (ex_texts or ex_images))
            or (ex_complete and ordinary_texts)
            or len(heroes) != 6
            or len(start_images) != 1
            or len(oil_images) != 1
        ):
            raise SemanticGateClosed("Raid precombat identity is incomplete")
        assert target.bounds is not None
        assert start_images[0].bounds is not None
        button_area = (target.bounds.right - target.bounds.left) * (
            target.bounds.bottom - target.bounds.top
        )
        if (
            self._bounds_overlap(target.bounds, start_images[0].bounds)
            < button_area * 0.99
        ):
            raise SemanticGateClosed("Raid precombat image does not cover start")
        return button_state, ui_state, target

    def raid_precombat_visible(self, event: str) -> bool:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid precombat event is unsupported")
        candidate_state = self.read_state()
        precombat_start_paths = {
            "UICamera/Canvas/UIOrigin/ActivityBossPrecombatUI(Clone)/adapt/right/start",
            "OverlayCamera/Overlay/UIMain/ActivityBossPrecombatUI(Clone)/adapt/right/start",
        }
        if not any(
            button.path in precombat_start_paths
            and button.name == "start"
            and button.active_in_hierarchy
            and button.active_and_enabled
            for button in candidate_state.buttons
        ):
            # This is a passive recovery probe on every validation startup.
            # Do not read an independently advancing UI endpoint unless the
            # exact precombat start object makes this a real candidate.
            return False
        try:
            button_state, _ui_state, _target = self._amatsukaze_raid_precombat_state()
        except SemanticGateClosed as exc:
            if str(exc) in (
                "Raid precombat page is absent",
                "Raid precombat identity is incomplete",
                "Raid precombat image does not cover start",
            ):
                # ActivityBossPrecombatUI mounts its typed texts/images and
                # animates the start Button/Image over separate observer
                # generations. Presence polling may wait through either
                # harmless transient; the click path repeats the complete
                # identity and coverage proof and remains fail-closed.
                return False
            raise
        if (
            self._blocking_rules(button_state, "raid/precombat/start")
            and not self.raid_precombat_notice_visible(event)
        ):
            return False
        return True

    def _amatsukaze_raid_multiple_target(
        self,
    ) -> Tuple[OracleState, UiState, ButtonState]:
        """Prove the update's multiple-sortie entry on current Raid precombat."""

        button_state, ui_state, start = self._amatsukaze_raid_precombat_state()
        root = start.path.rsplit("/adapt/right/start", 1)[0]
        path = root + "/adapt/right/multiple"
        targets = tuple(
            button
            for button in button_state.buttons
            if button.path == path
            and button.name == "multiple"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top in (True, None)
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        labels = tuple(
            item
            for item in ui_state.texts
            if item.path == path + "/text_en"
            and item.text.strip() == "MULTIPLE SORTIES"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        images = tuple(
            image
            for image in ui_state.images
            if image.path == path
            and image.sprite == "btn_blue"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if len(targets) != 1 or len(labels) != 1 or len(images) != 1:
            raise SemanticGateClosed(
                "Raid multiple-sortie entry identity is absent or ambiguous"
            )
        target = targets[0]
        assert target.bounds is not None
        assert images[0].bounds is not None
        button_area = (target.bounds.right - target.bounds.left) * (
            target.bounds.bottom - target.bounds.top
        )
        if self._bounds_overlap(target.bounds, images[0].bounds) < button_area * 0.99:
            raise SemanticGateClosed(
                "Raid multiple-sortie image does not cover its entry"
            )
        return button_state, ui_state, target

    def raid_precombat_multiple_visible(self, event: str) -> bool:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid precombat event is unsupported")
        candidate = self.read_state()
        if not any(
            button.name == "multiple"
            and button.path.endswith("/ActivityBossPrecombatUI(Clone)/adapt/right/multiple")
            and button.active_in_hierarchy
            and button.active_and_enabled
            for button in candidate.buttons
        ):
            return False
        self._amatsukaze_raid_multiple_target()
        return True

    def click_raid_precombat_multiple(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid precombat event is unsupported")
        button_state, _ui_state, target = self._amatsukaze_raid_multiple_target()
        if self.raid_precombat_notice_visible(event):
            raise SemanticGateClosed("Raid multiple-sortie entry is obscured by notice")
        if self._blocking_rules(button_state, "raid/precombat/multiple"):
            raise SemanticGateClosed("Raid multiple-sortie entry is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.point is not None
        assert target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="raid/precombat/multiple",
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _amatsukaze_raid_multiple_back_target(
        self,
    ) -> Tuple[OracleState, UiState, ButtonState]:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if not (
            button_state.generation <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("Raid multiple-sortie snapshots are incoherent")
        root = "OverlayCamera/Overlay/UIMain/ContinuousOperationWindowUI(Clone)"
        back_path = root + "/window/top/btnBack"
        targets = tuple(
            button
            for button in button_state.buttons
            if button.path == back_path
            and button.name == "btnBack"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top in (True, None)
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        title_path = root + "/window/top/bg/title/title/title_en"
        titles = tuple(
            item
            for item in ui_state.texts
            if item.path == title_path
            and item.text.strip() == "MULTIPLE SORTIES"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        exact_texts = {
            root + "/window/panel/content/value_bg/value": r"[1-9][0-9]*",
            root + "/window/panel/ticket/Number": r"[0-9]+/[0-9]+",
            root + "/window/panel/bonus/Number": r"[0-9]+",
        }
        for path, pattern in exact_texts.items():
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path == path
                and re.fullmatch(pattern, item.text.strip()) is not None
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "Raid multiple-sortie panel identity is incomplete"
                )
        images = tuple(
            image
            for image in ui_state.images
            if image.path == back_path
            and image.sprite == "close_btn"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if len(targets) != 1 or len(titles) != 1 or len(images) != 1:
            raise SemanticGateClosed(
                "Raid multiple-sortie panel identity is incomplete"
            )
        target = targets[0]
        assert target.bounds is not None
        assert images[0].bounds is not None
        button_area = (target.bounds.right - target.bounds.left) * (
            target.bounds.bottom - target.bounds.top
        )
        if self._bounds_overlap(target.bounds, images[0].bounds) < button_area * 0.99:
            raise SemanticGateClosed(
                "Raid multiple-sortie close image does not cover its button"
            )
        return button_state, ui_state, target

    def raid_multiple_sortie_visible(self, event: str) -> bool:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid multiple-sortie event is unsupported")
        candidate = self.read_state()
        root = "OverlayCamera/Overlay/UIMain/ContinuousOperationWindowUI(Clone)"
        if not any(
            button.path == root + "/window/top/btnBack"
            and button.name == "btnBack"
            and button.active_in_hierarchy
            and button.active_and_enabled
            for button in candidate.buttons
        ):
            return False
        self._amatsukaze_raid_multiple_back_target()
        return True

    def raid_multiple_sortie_state(self, event: str) -> RaidMultipleSortieState:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid multiple-sortie event is unsupported")
        button_state, ui_state, _target = self._amatsukaze_raid_multiple_back_target()
        root = "OverlayCamera/Overlay/UIMain/ContinuousOperationWindowUI(Clone)"

        def exact_text(path: str, pattern: str) -> str:
            matches = tuple(
                item.text.strip()
                for item in ui_state.texts
                if item.path == path
                and re.fullmatch(pattern, item.text.strip()) is not None
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "Raid multiple-sortie value is absent or ambiguous"
                )
            return matches[0]

        sortie_count = int(
            exact_text(root + "/window/panel/content/value_bg/value", r"[1-9][0-9]*")
        )
        selected_text, owned_text = exact_text(
            root + "/window/panel/ticket/Number", r"[0-9]+/[0-9]+"
        ).split("/", 1)
        ticket_selected = int(selected_text)
        ticket_owned = int(owned_text)
        bonus_count = int(
            exact_text(root + "/window/panel/bonus/Number", r"[0-9]+")
        )
        if ticket_selected > ticket_owned:
            raise SemanticGateClosed(
                "Raid multiple-sortie ticket selection exceeds inventory"
            )

        disabled = tuple(
            image
            for image in ui_state.images
            if image.path.startswith(root + "/window/panel/ticket/")
            and image.sprite == "checkmark_ban"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if ticket_owned == 0:
            if ticket_selected != 0 or len(disabled) != 1:
                raise SemanticGateClosed(
                    "Raid multiple-sortie zero-ticket state is inconsistent"
                )
        elif disabled:
            raise SemanticGateClosed(
                "Raid multiple-sortie positive ticket state is disabled"
            )
        return RaidMultipleSortieState(
            generation=button_state.generation,
            event=event,
            sortie_count=sortie_count,
            ticket_selected=ticket_selected,
            ticket_owned=ticket_owned,
            bonus_count=bonus_count,
            zero_ticket_disabled=bool(disabled),
            root=root,
        )

    def click_raid_multiple_sortie_back(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid multiple-sortie event is unsupported")
        button_state, _ui_state, target = self._amatsukaze_raid_multiple_back_target()
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.point is not None
        assert target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="raid/multiple-sortie/back",
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def _amatsukaze_raid_notice_target(
        self,
    ) -> Tuple[OracleState, UiState, ButtonState]:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if not (
            button_state.generation <= ui_state.generation
            <= button_state.generation + 2
        ):
            raise SemanticGateClosed("Raid precombat notice snapshots are incoherent")
        root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window"
        path = root + "/button_container/custom_button_1(Clone)"
        targets = tuple(
            button
            for button in button_state.buttons
            if button.path == path
            and button.name == "custom_button_1(Clone)"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is True
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if not targets:
            raise SemanticGateClosed("Raid precombat notice is absent")
        texts = tuple(
            item
            for item in ui_state.texts
            if item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        exact = {
            path + "/pic": "知道了",
            root + "/top/bg/infomation/title": "信息",
            root + "/top/bg/infomation/title_en": "INFORMATION",
        }
        exact_matches = tuple(
            item
            for item in texts
            if item.path in exact and item.text.strip() == exact[item.path]
        )
        notices = tuple(
            item
            for item in texts
            if item.path == root + "/help_panel/list/help_tpl"
            and item.text.strip().startswith("注意，自律战斗时可能出现以下情况")
        )
        images = tuple(
            image
            for image in ui_state.images
            if image.path == path
            and image.sprite == "btn_big_blue"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if (
            len(targets) != 1
            or len(exact_matches) != len(exact)
            or {item.path for item in exact_matches} != set(exact)
            or len(notices) != 1
            or len(images) != 1
        ):
            raise SemanticGateClosed("Raid precombat notice identity is incomplete")
        target = targets[0]
        assert target.bounds is not None
        assert images[0].bounds is not None
        button_area = (target.bounds.right - target.bounds.left) * (
            target.bounds.bottom - target.bounds.top
        )
        if self._bounds_overlap(target.bounds, images[0].bounds) < button_area * 0.99:
            raise SemanticGateClosed("Raid precombat notice image does not cover button")
        return button_state, ui_state, target

    def raid_precombat_notice_visible(self, event: str) -> bool:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid precombat event is unsupported")
        try:
            self._amatsukaze_raid_notice_target()
        except SemanticGateClosed as exc:
            if str(exc) == "Raid precombat notice is absent":
                return False
            raise
        return True

    def click_raid_precombat_notice(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid precombat event is unsupported")
        button_state, _ui_state, target = self._amatsukaze_raid_notice_target()
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.point is not None
        assert target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="raid/precombat/notice/acknowledge",
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_raid_precombat_start(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid precombat event is unsupported")
        button_state, _ui_state, target = self._amatsukaze_raid_precombat_state()
        if self.raid_precombat_notice_visible(event):
            raise SemanticGateClosed("Raid precombat start is obscured by notice")
        if self._blocking_rules(button_state, "raid/precombat/start"):
            raise SemanticGateClosed("Raid precombat start input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.point is not None
        assert target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="raid/precombat/start",
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_raid_precombat_back(self, event: str) -> ActionReceipt:
        if event != "raid_20260827":
            raise SemanticGateClosed("Raid precombat event is unsupported")
        button_state, ui_state, start = self._amatsukaze_raid_precombat_state()
        if self.raid_precombat_notice_visible(event):
            raise SemanticGateClosed("Raid precombat back is obscured by notice")
        root = start.path.rsplit("/adapt/right/start", 1)[0]
        path = root + "/blur_panel/top/back_btn"
        targets = tuple(
            button
            for button in button_state.buttons
            if button.path == path
            and button.name == "back_btn"
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top in (True, None)
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        images = tuple(
            image
            for image in ui_state.images
            if image.path == path
            and image.sprite == "icon_bg_front_1920"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.color[3] >= 0.99
            and image.fill_amount >= 0.99
            and image.bounds is not None
        )
        if len(targets) != 1 or len(images) != 1:
            raise SemanticGateClosed("Raid precombat back identity is incomplete")
        target = targets[0]
        assert target.bounds is not None
        assert images[0].bounds is not None
        button_area = (target.bounds.right - target.bounds.left) * (
            target.bounds.bottom - target.bounds.top
        )
        if self._bounds_overlap(target.bounds, images[0].bounds) < button_area * 0.99:
            raise SemanticGateClosed("Raid precombat image does not cover back")
        if self._blocking_rules(button_state, "raid/precombat/back"):
            raise SemanticGateClosed("Raid precombat back input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before Raid input")
        assert target.point is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="raid/precombat/back",
            generation=button_state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def raid_remain(self, event: str, mode: str) -> int:
        return self.raid_remain_state(event=event, mode=mode).remaining
