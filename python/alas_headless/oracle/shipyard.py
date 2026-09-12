"""Shipyard for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional
from .contracts import ActionReceipt, ShipyardState
from .errors import SemanticGateClosed


class ShipyardOracle:
    """Shipyard operations sharing the oracle frame and input boundary."""

    def shipyard_page_visible(self) -> bool:
        """Prove the top-level ShipBluePrintUI page without pixel matching."""

        state = self.read_state()
        roots = self._matches(state, "shipyard/page/root")
        backs = self._matches(state, "shipyard/page/back")
        series_choices = self._matches(state, "shipyard/series/1")
        return bool(
            len(roots) == 1
            and roots[0].active_in_hierarchy
            and (
                (len(backs) == 1 and backs[0].actionable)
                or (
                    len(series_choices) == 1
                    and series_choices[0].active_in_hierarchy
                    and series_choices[0].active_and_enabled
                )
            )
        )

    def shipyard_state(self, index: int) -> ShipyardState:
        """Read the selected ship's exact blueprint, phase, and progress state."""

        if not 1 <= index <= 6:
            raise ValueError("shipyard index must be in [1, 6]")
        state = self.read_state()
        ui_state = self.read_ui_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("shipyard state frames are incoherent")
        if not self.shipyard_page_visible():
            raise SemanticGateClosed("shipyard page identity is absent")

        toggles = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and "/bottom_panel/ships/bg/content/ship_tpl" in toggle.path
            and toggle.bounds is not None
        )
        toggles = tuple(sorted(toggles, key=lambda item: item.bounds.left))
        if len(toggles) not in (5, 6):
            raise SemanticGateClosed("shipyard ship navbar is incomplete")
        selected = tuple(i + 1 for i, item in enumerate(toggles) if item.checked)
        if selected != (index,):
            raise SemanticGateClosed("shipyard selected ship identity changed")

        def exact_text(suffix: str) -> Optional[str]:
            matches = tuple(
                text.text.strip()
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
            )
            if len(matches) > 1:
                raise SemanticGateClosed("shipyard text is ambiguous")
            return matches[0] if matches else None

        name = exact_text(
            "ShipBluePrintUI(Clone)/main/center_panel/name/name_mask/Text"
        )
        if not name:
            raise SemanticGateClosed("shipyard ship name is absent")

        selected_toggle = toggles[index - 1]
        def belongs_to_selected(item):
            return (item.bounds is not None and selected_toggle.bounds.left <=
                    (item.bounds.left + item.bounds.right) / 2 < selected_toggle.bounds.right)

        counts = tuple(text for text in ui_state.texts
                       if text.path == selected_toggle.path + '/count'
                       and text.active_in_hierarchy and text.active_and_enabled
                       and not text.truncated and belongs_to_selected(text))
        if len(counts) != 1 or re.fullmatch(r"\d+", counts[0].text.strip()) is None:
            raise SemanticGateClosed("shipyard selected blueprint count is absent or ambiguous")
        blueprint_count = int(counts[0].text.strip())
        status_text = exact_text(
            "ShipBluePrintUI(Clone)/main/center_panel/state_info/progress/label")
        if status_text == "研究进行中...":
            markers = [image for image in ui_state.images
                       if image.path == selected_toggle.path + '/state/research/1'
                       and image.active_in_hierarchy and image.active_and_enabled
                       and not image.truncated and image.sprite == 'sel_dev'
                       and belongs_to_selected(image)]
            if len(markers) != 1:
                raise SemanticGateClosed("shipyard research identity is absent or ambiguous")
            return ShipyardState(ui_state.generation, index, name, blueprint_count,
                                 'research', None, None, 'in-progress')

        level_text = exact_text(
            "blur_panel/adapt/right_panel/mod_panel/title/level_bg/Text"
        )
        level_match = re.fullmatch(
            r"<size=45>(\d+)</size>/<size=27>(\d+)</size>", level_text or ""
        )
        if level_match is None:
            raise SemanticGateClosed("shipyard development level is absent")
        level, level_max = map(int, level_match.groups())

        selected_toggle = toggles[index - 1]
        phase_images = tuple(
            image
            for image in ui_state.images
            if image.active_in_hierarchy
            and image.active_and_enabled
            and image.bounds is not None
            and image.path.startswith(selected_toggle.path + "/state/")
            and belongs_to_selected(image)
            and not image.truncated
            and image.name in ("dev", "fate")
        )
        if len(phase_images) != 1:
            raise SemanticGateClosed("shipyard phase identity is ambiguous")
        phase = phase_images[0].name

        status_text = exact_text(
            "ShipBluePrintUI(Clone)/main/center_panel/state_info/progress/label"
        )
        if status_text == "研究进行中...":
            research_status = "in-progress"
        elif status_text:
            research_status = "incomplete"
        else:
            research_status = "complete"
        return ShipyardState(
            generation=max(state.generation, ui_state.generation),
            ship_index=index,
            ship_name=name,
            blueprint_count=blueprint_count,
            phase=phase,
            level=level,
            level_max=level_max,
            research_status=research_status,
        )

    def click_shipyard_ship(self, index: int) -> ActionReceipt:
        if not 1 <= index <= 6:
            raise ValueError("shipyard index must be in [1, 6]")
        if not self.shipyard_page_visible():
            raise SemanticGateClosed("shipyard page identity is absent")
        state = self.read_state()
        ui_state = self.read_ui_state()
        toggles = tuple(
            sorted(
                (
                    item
                    for item in ui_state.toggles
                    if item.active_in_hierarchy
                    and item.active_and_enabled
                    and "/bottom_panel/ships/bg/content/ship_tpl" in item.path
                    and item.bounds is not None
                    and item.point is not None
                ),
                key=lambda item: item.bounds.left,
            )
        )
        if len(toggles) not in (5, 6) or index > len(toggles):
            raise SemanticGateClosed("shipyard ship navbar is incomplete")
        target = toggles[index - 1]
        if target.checked:
            return ActionReceipt(
                "shipyard/ship/{0}/already".format(index),
                max(state.generation, ui_state.generation),
                target.point,
                target.bounds,
                target.path,
            )
        if not target.interactable or target.raycast_top is not None:
            raise SemanticGateClosed("shipyard ship toggle is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            "shipyard/ship/{0}".format(index),
            max(state.generation, ui_state.generation),
            target.point,
            target.bounds,
            target.path,
        )
