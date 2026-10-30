"""Gems farming for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, FrozenSet, Iterable, Optional, Tuple, Union
from .contracts import (
    ActionReceipt,
    Bounds,
    GemsFarmingDockCandidate,
    ImageState,
    OracleState,
    Point,
    TextState,
    UiState,
)
from .errors import SemanticGateClosed


class GemsFarmingOracle:
    """Gems farming operations sharing the oracle frame and input boundary."""

    @staticmethod
    def _gems_farming_one_ship_selected(ui_state: UiState) -> bool:
        """Recognize the same selection count through its layout wrapper."""
        count_paths = {
            "OverlayCamera/Overlay/UIMain/blur_panel/" + panel
            + "/bottom_info/bg_input/count"
            for panel in ("select_panel", "select_panel_adapt/select_panel")
        }
        counts = tuple(
            item for item in ui_state.texts
            if item.path in count_paths
            and item.active_in_hierarchy and item.active_and_enabled
        )
        return (
            len(counts) == 1 and not counts[0].truncated
            and re.fullmatch(r"<color=#[0-9A-Fa-f]{8}>1</color>/1", counts[0].text)
            is not None
        )

    def gems_farming_formation_visible(self) -> bool:
        """Identify the normal Formation owner for ALAS page discovery."""
        state = self.read_state()
        path = 'UICamera/Canvas/UIMain/FormationUI(Clone)/blur_panel/top/back_btn'
        backs = [b for b in state.buttons if b.path == path and b.name == 'back_btn'
                 and b.active_in_hierarchy and b.active_and_enabled and b.interactable
                 and b.point is not None and b.bounds is not None and b.bounds.contains(b.point)]
        if not backs:
            return False
        if len(backs) != 1:
            raise SemanticGateClosed('GemsFarming Formation back owner is ambiguous')
        if self._blocking_rules(state, 'gems-farming/formation/check'):
            return False
        self._gems_farming_formation_records()
        return True

    def click_gems_farming_formation_back(self) -> ActionReceipt:
        """Leave the proved Formation page through its existing native back."""
        if not self.gems_farming_formation_visible():
            raise SemanticGateClosed('GemsFarming Formation page is absent or blocked')
        state = self.read_state()
        path = 'UICamera/Canvas/UIMain/FormationUI(Clone)/blur_panel/top/back_btn'
        backs = [b for b in state.buttons if b.path == path and b.name == 'back_btn']
        if len(backs) != 1:
            raise SemanticGateClosed('GemsFarming Formation back owner changed')
        return self._gems_equipment_click_button(state, backs[0], 'gems-farming/formation/back')

    def _gems_farming_formation_records(self) -> Tuple[OracleState, UiState, int]:
        """Read the exact normal Formation page and selected fleet index."""

        last_error: Optional[SemanticGateClosed] = None
        number_path = (
            "UICamera/Canvas/UIMain/FormationUI(Clone)/blur_panel/"
            "fleet_info/fleet_number"
        )
        slot_root = "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/GridFrame/"
        slot_names = tuple(
            "{0}_{1}".format(role, index)
            for role in ("main", "vanguard") for index in (1, 2, 3)
        )
        for attempt in range(8):
            try:
                state = self.read_state()
                ui_state = self.read_ui_state()
                numbers = tuple(
                    item
                    for item in ui_state.texts
                    if item.path == number_path
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and re.fullmatch(r"[1-6]", item.text)
                )
                # Occupied slots expose a shadow; empty slots expose their
                # native add icon. Page identity must not require a full fleet.
                slots_complete = all(
                    sum(
                        item.path == slot_root + slot + "/" + kind
                        and item.sprite == sprite
                        and item.active_in_hierarchy and item.active_and_enabled
                        and not item.truncated and item.bounds is not None
                        for item in ui_state.images
                        for kind, sprite in (("shadow", "shadow"), ("tip", "add_icon"))
                    ) == 1
                    for slot in slot_names
                )
                if (
                    state.generation <= ui_state.generation <= state.generation + 2
                    and len(numbers) == 1
                    and slots_complete
                ):
                    return state, ui_state, int(numbers[0].text)
                last_error = SemanticGateClosed(
                    "GemsFarming formation identity is incomplete"
                )
            except SemanticGateClosed as exc:
                last_error = exc
            if attempt < 7:
                self._sleep(0.05)
        raise SemanticGateClosed(
            "GemsFarming formation snapshots did not stabilize"
        ) from last_error

    def gems_farming_select_fleet_index(self, fleet_index: int) -> int:
        """Select ALAS's attacking 1-6 fleet on the normal Formation page."""

        if isinstance(fleet_index, bool) or not isinstance(fleet_index, int):
            raise TypeError("GemsFarming fleet index must be an integer")
        if not 1 <= fleet_index <= 6:
            raise SemanticGateClosed("GemsFarming fleet index is outside 1 through 6")
        for _ in range(6):
            state, ui_state, current = self._gems_farming_formation_records()
            if current == fleet_index:
                return current
            direction = "nextPage" if current < fleet_index else "prevPage"
            pages = tuple(
                item
                for item in ui_state.images
                if item.path
                == "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/" + direction
                and item.name == direction
                and item.sprite == "arr"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.raycast_target
                and item.bounds is not None
            )
            if len(pages) != 1:
                raise SemanticGateClosed(
                    "GemsFarming formation fleet navigation is incomplete"
                )
            before = current
            self._click_exact_image(
                state,
                pages[0],
                "gems-farming/formation/fleet/{0}".format(
                    "next" if current < fleet_index else "previous"
                ),
            )
            expected = before + 1 if before < fleet_index else before - 1
            for _ in range(30):
                self._sleep(0.05)
                _, _, after = self._gems_farming_formation_records()
                if after == expected:
                    break
            else:
                raise SemanticGateClosed(
                    "GemsFarming formation fleet index did not advance"
                )
        raise SemanticGateClosed("GemsFarming formation fleet selection did not settle")

    def gems_farming_open_slot(self, role: str) -> ActionReceipt:
        """Open the exact flagship or first-vanguard replacement slot."""

        slot_names = {"flagship": "main_1", "vanguard": "vanguard_1"}
        if role not in slot_names:
            raise ValueError("GemsFarming role must be flagship or vanguard")
        slot_path = (
            "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/GridFrame/"
            + slot_names[role]
            + "/shadow"
        )
        semantic_id = "gems-farming/formation/{0}/open".format(role)
        for _ in range(20):
            state, ui_state, fleet_index = self._gems_farming_formation_records()
            slots = tuple(item for item in ui_state.images if item.path == slot_path)
            if len(slots) != 1 or slots[0].bounds is None:
                raise SemanticGateClosed("GemsFarming formation slot is incomplete")
            slot_center_x = (
                slots[0].bounds.left + slots[0].bounds.right
            ) / 2.0
            ships = tuple(
                item
                for item in ui_state.images
                if item.path.startswith(
                    "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/"
                    "HeroContainer/heroInfo(Clone)/"
                )
                and item.path.endswith("_root/mouseChild")
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.raycast_target
                and not item.truncated
                and item.bounds is not None
                and abs(
                    (item.bounds.left + item.bounds.right) / 2.0 - slot_center_x
                )
                <= 2.0
            )
            if len(ships) != 1:
                raise SemanticGateClosed(
                    "GemsFarming formation ship identity is absent or ambiguous"
                )
            ship_match = re.search(r"/([^/]+)_root/mouseChild$", ships[0].path)
            if ship_match is None:
                raise SemanticGateClosed(
                    "GemsFarming formation ship sprite is incomplete"
                )
            current_ship_sprite = ship_match.group(1)
            if not self._blocking_rules(state, semantic_id):
                break
            self._sleep(0.05)
        else:
            raise SemanticGateClosed("GemsFarming formation slot stayed blocked")
        receipt = self._click_exact_image(state, ships[0], semantic_id)
        self._retry_transition_read(
            self._enhancement_dock_records,
            attempts=50,
            interval_seconds=0.1,
        )
        self._gems_farming_open_slot_context = (
            role,
            current_ship_sprite,
            fleet_index,
        )
        return receipt

    @staticmethod
    def _gems_farming_hard_role_name(role: str) -> str:
        if role == "flagship":
            return "main"
        if role == "vanguard":
            return "vanguard"
        raise ValueError("GemsFarming role must be flagship or vanguard")

    def _gems_farming_hard_role_cards(
        self, stage_code: str, fleet_index: int, role: str
    ) -> Tuple[OracleState, UiState, Tuple[ImageState, ...], Tuple[str, ...]]:
        """Read the compacted hard-fleet role row and exact ship sprites."""

        if stage_code.upper() not in ("11-4", "12-1"):
            raise SemanticGateClosed(
                "GemsFarming hard replacement is qualified only for reviewed hard stages"
            )
        if fleet_index not in (1, 2):
            raise SemanticGateClosed("GemsFarming hard fleet must be 1 or 2")
        group = self._gems_farming_hard_role_name(role)
        preparation = self.campaign_fleet_selection_state(stage_code)
        if not preparation.hard_mode:
            raise SemanticGateClosed("GemsFarming hard fleet preparation is absent")
        state = self.read_state()
        ui_state = self.read_ui_state()
        path = (
            "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
            "ShipList/fleet/{0}/{1}/shiptpl(Clone)/icon_bg"
        ).format(fleet_index, group)
        cards = tuple(
            sorted(
                (
                    item
                    for item in ui_state.images
                    if item.path == path
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and item.raycast_target
                    and item.bounds is not None
                ),
                key=lambda item: item.bounds.left,
            )
        )
        if len(cards) not in (2, 3):
            raise SemanticGateClosed(
                "GemsFarming hard role row must contain two or three ships"
            )
        sprites = []
        for card in cards:
            assert card.bounds is not None
            icons = tuple(
                item
                for item in ui_state.images
                if item.path == path + "/icon"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.sprite
                and self._gems_equipment_in_bounds(item, card.bounds)
            )
            if len(icons) != 1:
                raise SemanticGateClosed(
                    "GemsFarming hard fleet ship identity is incomplete"
                )
            sprites.append(icons[0].sprite)
        if state.generation > ui_state.generation:
            raise SemanticGateClosed(
                "GemsFarming hard fleet snapshots are incoherent"
            )
        return state, ui_state, cards, tuple(sprites)

    def gems_farming_hard_slot_occupied(
        self, stage_code: str, fleet_index: int, role: str
    ) -> bool:
        """Return whether ALAS's compacted first hard-fleet role slot is filled."""

        _, _, cards, _ = self._gems_farming_hard_role_cards(
            stage_code, fleet_index, role
        )
        return len(cards) == 3

    def cancel_campaign_hard_recommend_prompt(self) -> ActionReceipt:
        """Cancel the exact official-recommend prompt left by hard recovery."""

        return self._campaign_hard_recommend_prompt_action(confirm=False)

    def confirm_campaign_hard_recommend_prompt(self) -> ActionReceipt:
        """Confirm the exact official-recommend prompt after ALAS requested it."""

        return self._campaign_hard_recommend_prompt_action(confirm=True)

    def campaign_hard_recommend_prompt_present(self) -> bool:
        """Detect a modal before choosing whether confirmation is needed."""

        root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        return any(
            item.path.startswith(root)
            and item.active_in_hierarchy
            and item.active_and_enabled
            for item in self.read_state().buttons
        )

    def _campaign_hard_recommend_prompt_action(
        self, *, confirm: bool
    ) -> ActionReceipt:

        state = self.read_state()
        ui_state = self.read_ui_state()
        if not any(
            "LevelFleetSelectView(Clone)" in item.path
            and item.active_in_hierarchy
            and item.active_and_enabled
            for item in state.buttons
        ):
            raise SemanticGateClosed(
                "hard fleet recommendation prompt has no fleet owner"
            )
        root = "OverlayCamera/Overlay/UIMain/Msgbox(Clone)/window/"
        texts = {
            item.path: item.text.strip()
            for item in ui_state.texts
            if item.path in {
                root + "msg_panel/content",
                root + "button_container/custom_button_1(Clone)/pic",
                root + "button_container/custom_button_2(Clone)/pic",
            }
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        }
        content = texts.get(root + "msg_panel/content")
        confirm_label = "".join(
            texts.get(
                root + "button_container/custom_button_1(Clone)/pic", ""
            ).split()
        )
        cancel_label = "".join(
            texts.get(
                root + "button_container/custom_button_2(Clone)/pic", ""
            ).split()
        )
        if (
            content
            not in (
                "是否采用推荐配置补齐空余位置?",
                "是否使用推荐编队来填充空位?",
                "是否使用推荐编队填充空位?",
                "�Ƿ�����Ƽ����ò������λ��?",
            )
            or (cancel_label, confirm_label) not in (("取消", "确定"), ("ȡ��", "ȷ��"))
        ):
            raise SemanticGateClosed(
                "hard fleet recommendation prompt text is not reviewed"
            )
        button_name = (
            "custom_button_1(Clone)" if confirm else "custom_button_2(Clone)"
        )
        path = root + "button_container/" + button_name
        buttons = tuple(
            item
            for item in state.buttons
            if item.path == path
            and item.name == button_name
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.raycast_top is True
            and item.point is not None
            and item.bounds is not None
            and item.bounds.contains(item.point)
        )
        images = tuple(
            item
            for item in ui_state.images
            if item.path == path
            and item.sprite == ("btn_big_blue" if confirm else "btn_big_grey")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(buttons) != 1 or len(images) != 1:
            raise SemanticGateClosed(
                "hard fleet recommendation response is absent or ambiguous"
            )
        target = buttons[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "foreground changed before hard recommendation response"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=(
                "campaign/hard/recommend/confirm" if confirm
                else "campaign/hard/recommend/cancel"
            ),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def gems_farming_hard_unmount(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        """Unmount the compacted first hard-fleet ship and prove one-card removal."""

        state, _, cards, before = self._gems_farming_hard_role_cards(
            stage_code, fleet_index, role
        )
        if len(cards) != 3:
            raise SemanticGateClosed("GemsFarming hard source slot is already empty")
        open_receipt = self._click_exact_image(
            state,
            cards[0],
            "campaign/fleet-preparation/fleet/{0}/select".format(fleet_index),
        )
        dock_state, _ = self._retry_transition_read(
            self._enhancement_dock_records, attempts=50, interval_seconds=0.1
        )
        current = tuple(
            item
            for item in dock_state.buttons
            if item.path
            == "UICamera/Canvas/UIMain/DockyardUI(Clone)/main/ship_container/ships/0"
            and item.name == "0"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.point is not None
            and item.bounds is not None
        )
        if len(current) != 1:
            raise SemanticGateClosed(
                "GemsFarming hard current-ship placeholder is absent or ambiguous"
            )
        receipt = self._gems_equipment_click_button(
            dock_state, current[0], "tactical/dock/confirm"
        )
        for _ in range(60):
            self._sleep(0.1)
            try:
                _, _, after_cards, after = self._gems_farming_hard_role_cards(
                    stage_code, fleet_index, role
                )
            except SemanticGateClosed:
                continue
            if len(after_cards) == 2 and after == before[1:]:
                self._gems_farming_hard_open_slot_context = None
                return receipt
        raise SemanticGateClosed(
            "GemsFarming hard unmount postcondition was not proven; open receipt "
            + open_receipt.semantic_id
        )

    def gems_farming_hard_open_slot(
        self, stage_code: str, fleet_index: int, role: str
    ) -> ActionReceipt:
        """Open the unique third compacted hard-fleet slot after unmount."""

        state, ui_state, cards, before = self._gems_farming_hard_role_cards(
            stage_code, fleet_index, role
        )
        if len(cards) != 2:
            raise SemanticGateClosed(
                "GemsFarming hard target slot requires exactly two remaining ships"
            )
        group = self._gems_farming_hard_role_name(role)
        path = (
            "OverlayCamera/Overlay/UIMain/LevelFleetSelectView(Clone)/panel/"
            "ShipList/fleet/{0}/{1}/emptytpl(Clone)/icon_bg"
        ).format(fleet_index, group)
        blanks = tuple(
            item
            for item in ui_state.images
            if item.path == path
            and item.name == "icon_bg"
            and item.sprite == "tianjia_icon"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.raycast_target
            and item.bounds is not None
        )
        if len(blanks) != 1:
            raise SemanticGateClosed(
                "GemsFarming hard target blank is absent or ambiguous"
            )
        receipt = self._click_exact_image(
            state,
            blanks[0],
            "campaign/fleet-preparation/fleet/{0}/select".format(fleet_index),
        )
        self._retry_transition_read(
            self._enhancement_dock_records, attempts=50, interval_seconds=0.1
        )
        self._gems_farming_hard_open_slot_context = (
            stage_code,
            fleet_index,
            role,
            before,
        )
        return receipt

    def set_gems_farming_dock_sort(self, descending: bool) -> Optional[ActionReceipt]:
        """Set the Dock result direction through its exact typed arrow."""

        if not isinstance(descending, bool):
            raise TypeError("GemsFarming Dock sort direction must be boolean")
        state, ui_state = self._enhancement_dock_records()
        root = "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/sort_button/"
        directions = {
            "desc": tuple(
                item
                for item in ui_state.images
                if item.path == root + "desc"
                and item.sprite == "down"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.raycast_target
                and not item.truncated
                and item.bounds is not None
            ),
            "asc": tuple(
                item
                for item in ui_state.images
                if item.path == root + "asc"
                and item.sprite == "up"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.raycast_target
                and not item.truncated
                and item.bounds is not None
            ),
        }
        if len(directions["desc"]) > 1 or len(directions["asc"]) > 1:
            raise SemanticGateClosed("GemsFarming Dock sort direction is ambiguous")
        current_descending = bool(directions["desc"])
        if current_descending == descending:
            return None
        current_name = "desc" if current_descending else "asc"
        if len(directions[current_name]) != 1:
            raise SemanticGateClosed("GemsFarming Dock sort direction is incomplete")
        parents = tuple(
            item
            for item in ui_state.images
            if item.path == root[:-1]
            and item.name == "sort_button"
            and item.sprite == "shaixuan01"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.raycast_target
            and not item.truncated
            and item.bounds is not None
        )
        if len(parents) != 1:
            raise SemanticGateClosed("GemsFarming Dock sort control is incomplete")
        target = parents[0]
        for _ in range(20):
            if not self._blocking_rules(state, "gems-farming/dock/sort"):
                break
            self._sleep(0.05)
            state, refreshed = self._enhancement_dock_records()
            matches = tuple(
                item
                for item in refreshed.images
                if item.path == root[:-1]
                and item.name == "sort_button"
                and item.sprite == "shaixuan01"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.raycast_target
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "GemsFarming Dock sort direction changed while blocked"
                )
            target = matches[0]
        else:
            raise SemanticGateClosed("GemsFarming Dock sort input stayed blocked")
        receipt = self._click_exact_image(
            state,
            target,
            "gems-farming/dock/sort/" + ("descending" if descending else "ascending"),
        )
        for _ in range(30):
            self._sleep(0.05)
            _, after = self._enhancement_dock_records()
            expected = tuple(
                item
                for item in after.images
                if item.path == root + ("desc" if descending else "asc")
                and item.active_in_hierarchy
                and item.active_and_enabled
            )
            if len(expected) == 1:
                return receipt
        raise SemanticGateClosed("GemsFarming Dock sort direction did not change")

    def set_gems_farming_dock_filter(
        self,
        role: str,
        factions: Tuple[str, ...],
        *,
        enhanceable_only: bool = True,
    ) -> Tuple[ActionReceipt, ...]:
        """Apply the exact ALAS GemsFarming Dock filter for one ship role."""

        role_options = {
            "flagship": ("7", "航母", "3", "可强化"),
            "vanguard": ("3", "驱逐", "4", "可突破"),
        }
        faction_options = {
            "all": ("tpl", "全阵营"),
            "eagle": ("1", "白鹰"),
            "iron": ("4", "铁血"),
        }
        if role not in role_options:
            raise ValueError("GemsFarming role must be flagship or vanguard")
        if not isinstance(enhanceable_only, bool):
            raise TypeError("GemsFarming enhanceable_only must be boolean")
        if (
            not isinstance(factions, tuple)
            or not factions
            or any(item not in faction_options for item in factions)
            or ("all" in factions and len(factions) != 1)
        ):
            raise SemanticGateClosed("GemsFarming Dock faction scope is invalid")
        state, ui_state = self._enhancement_dock_records()
        opener = tuple(
            item
            for item in ui_state.images
            if item.path
            == "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/index_button"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.raycast_target
            and not item.truncated
            and item.bounds is not None
        )
        if len(opener) != 1:
            raise SemanticGateClosed("GemsFarming Dock filter opener is incomplete")
        receipts = [
            self._click_exact_image(
                state, opener[0], "gems-farming/dock/filter/open"
            )
        ]
        self._sleep(0.1)
        index_option, index_label, extra_option, extra_label = role_options[role]
        if not enhanceable_only:
            extra_option, extra_label = "tpl", "无限制"
        # Match upstream ``Setting.reset_first``: selecting each group's
        # default clears stale multi-select state before applying the task
        # filter. Merely proving the desired option selected is insufficient;
        # an old incompatible option can remain selected and produce an empty
        # Dock while every desired label still looks correct.
        choices = [
            ("sort", "1", "等级", "btn_index_yellow"),
            ("index", "tpl", "全部", "btn_index_blue"),
            ("camp", "tpl", "全阵营", "btn_index_blue"),
            ("rarity", "tpl", "全部", "btn_index_blue"),
            ("extraindex", "tpl", "无限制", "btn_index_blue"),
            ("sort", "2", "综合性能", "btn_index_yellow"),
            ("index", index_option, index_label, "btn_index_blue"),
        ]
        choices.extend(
            ("camp", faction_options[item][0], faction_options[item][1], "btn_index_blue")
            for item in factions
        )
        choices.extend(
            (
                ("rarity", "1", "普通", "btn_index_blue"),
                ("extraindex", extra_option, extra_label, "btn_index_blue"),
            )
        )
        for group, option, label, selected_sprite in choices:
            semantic_id = "gems-farming/dock/filter/{0}/{1}".format(
                group, option
            )
            for click_attempt in range(3):
                state, _, image = self._wait_enhancement_filter_option(
                    group, option, label
                )
                if image.sprite == selected_sprite:
                    break
                if image.sprite != "btn_index_grey":
                    raise SemanticGateClosed(
                        "GemsFarming Dock filter state is unknown"
                    )
                for _ in range(20):
                    if not self._blocking_rules(state, semantic_id):
                        break
                    self._sleep(0.05)
                    state, _, image = self._wait_enhancement_filter_option(
                        group, option, label
                    )
                    if image.sprite == selected_sprite:
                        break
                    if image.sprite != "btn_index_grey":
                        raise SemanticGateClosed(
                            "GemsFarming Dock filter state became unknown"
                        )
                else:
                    raise SemanticGateClosed(
                        "GemsFarming Dock filter input stayed blocked"
                    )
                if image.sprite == selected_sprite:
                    break
                receipts.append(
                    self._click_exact_image(state, image, semantic_id)
                )
                for _ in range(30):
                    self._sleep(0.05)
                    _, _, verified = self._wait_enhancement_filter_option(
                        group, option, label
                    )
                    if verified.sprite == selected_sprite:
                        break
                    if verified.sprite != "btn_index_grey":
                        raise SemanticGateClosed(
                            "GemsFarming Dock filter selection became unknown"
                        )
                else:
                    if click_attempt == 2:
                        raise SemanticGateClosed(
                            "GemsFarming Dock filter option did not select"
                        )
                    continue
                break
            else:
                raise SemanticGateClosed(
                    "GemsFarming Dock filter option did not select"
                )
        expected_selected = {
            "sort": {"2"},
            "index": {index_option},
            "camp": {faction_options[item][0] for item in factions},
            "rarity": {"1"},
            "extraindex": {extra_option},
        }
        option_pattern = re.compile(
            r"OverlayCamera/Overlay/UIMain/CustomIndexUI\(Clone\)/index_panel/"
            r"layout/container/indexsort_(sort|index|camp|rarity|extraindex)/"
            r"bg/([^/]+)"
        )

        def selected_options(
            current: UiState,
        ) -> Dict[str, Dict[str, ImageState]]:
            selected: Dict[str, Dict[str, ImageState]] = {
                group: {} for group in expected_selected
            }
            for image in current.images:
                match = option_pattern.fullmatch(image.path)
                if (
                    match is None
                    or image.sprite not in ("btn_index_blue", "btn_index_yellow")
                    or not image.active_in_hierarchy
                    or not image.active_and_enabled
                    or image.truncated
                    or image.bounds is None
                ):
                    continue
                selected[match.group(1)][match.group(2)] = image
            return selected

        # These groups are multi-select in the live client.  Selecting the
        # requested item does not necessarily clear prior selections, so
        # explicitly deselect every observed extra option and prove the exact
        # final set before confirming.
        for _ in range(40):
            state, ui_state = self._retirement_records()
            selected = selected_options(ui_state)
            unexpected = [
                (group, option, image)
                for group, options in selected.items()
                for option, image in options.items()
                if option not in expected_selected[group]
            ]
            if not unexpected:
                if all(
                    set(selected[group]) == expected
                    for group, expected in expected_selected.items()
                ):
                    break
                raise SemanticGateClosed(
                    "GemsFarming Dock filter selected set is incomplete"
                )
            group, option, image = unexpected[0]
            semantic_id = "gems-farming/dock/filter/{0}/{1}/deselect".format(
                group, option
            )
            if self._blocking_rules(state, semantic_id):
                self._sleep(0.05)
                continue
            receipts.append(self._click_exact_image(state, image, semantic_id))
            self._sleep(0.05)
        else:
            raise SemanticGateClosed(
                "GemsFarming Dock filter extras did not clear"
            )
        for _ in range(20):
            state, ui_state = self._retirement_records()
            if not self._blocking_rules(
                state, "gems-farming/dock/filter/confirm"
            ):
                break
            self._sleep(0.05)
        else:
            raise SemanticGateClosed(
                "GemsFarming Dock filter confirm stayed blocked"
            )
        confirm_path = (
            "OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/"
            "layout/btns/ok"
        )
        confirm = tuple(
            item
            for item in ui_state.images
            if item.path == confirm_path
            and item.sprite == "btn_big_blue"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.raycast_target
            and not item.truncated
            and item.bounds is not None
        )
        confirm_text = tuple(
            item
            for item in ui_state.texts
            if item.path == confirm_path + "/Image"
            and item.text == "确 定"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
        )
        if len(confirm) != 1 or len(confirm_text) != 1:
            raise SemanticGateClosed("GemsFarming Dock filter confirm is incomplete")
        receipts.append(
            self._click_exact_image(
                state, confirm[0], "gems-farming/dock/filter/confirm"
            )
        )
        self._retry_transition_read(
            self._enhancement_dock_records,
            attempts=30,
            interval_seconds=0.1,
        )
        return tuple(receipts)

    def cancel_gems_farming_dock_filter_if_visible(
        self,
    ) -> Optional[ActionReceipt]:
        """Cancel only the exact open CustomIndexUI and prove Dock recovery."""

        state, ui_state = self._retirement_records()
        cancel_path = (
            "OverlayCamera/Overlay/UIMain/CustomIndexUI(Clone)/index_panel/"
            "layout/btns/cancel"
        )
        controls = tuple(
            item
            for item in ui_state.images
            if item.path == cancel_path
            and item.name == "cancel"
            and item.sprite == "btn_big_red"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.raycast_target
            and not item.truncated
            and item.bounds is not None
        )
        if not controls:
            return None
        if len(controls) != 1:
            raise SemanticGateClosed(
                "GemsFarming Dock filter cancel is ambiguous"
            )
        semantic_id = "gems-farming/dock/filter/cancel"
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("GemsFarming Dock filter cancel is blocked")
        receipt = self._click_exact_image(state, controls[0], semantic_id)
        self._retry_transition_read(
            self._enhancement_dock_records,
            attempts=30,
            interval_seconds=0.1,
        )
        return receipt

    def _gems_farming_dock_candidates_once(
        self,
        *,
        ship_ids: Optional[FrozenSet[int]] = None,
        require_emotion: bool = True,
    ) -> Tuple[GemsFarmingDockCandidate, ...]:
        """Read one candidate snapshot after a Dock filter or scroll update."""

        state, ui_state = self._enhancement_dock_records()
        base = self.enhancement_dock_candidates()
        rarity_names = {
            "1": "common",
            "2": "rare",
            "3": "elite",
            "4": "super_rare",
            "4_0": "super_rare",
            "5": "ultra",
            # Research/PR ships use the rainbow frame variant while keeping
            # the same Dock card contract.  It may coexist with ordinary
            # GemsFarming candidates in a broad recovery view.
            "5_0": "ultra",
            "prop": "special",
            # META carriers can share a broad recovery page with the exact
            # target ship.  Classify their observed frame locally so an
            # unrelated card does not invalidate every typed candidate; it
            # still cannot satisfy GemsFarming's required common rarity.
            "3_1": "special",
            "4_1": "special",
            "prop4_1": "special",
        }
        type_names = {
            "hangmu": "cv",
            "quzhu": "dd",
            "zhongxun": "ca",
            "zhanlie": "bb",
        }
        result = []
        for candidate in base:
            if ship_ids is not None and candidate.ship_id not in ship_ids:
                continue
            root = candidate.button.path + "/content/"
            if candidate.button.bounds is None:
                raise SemanticGateClosed("GemsFarming Dock card bounds are absent")
            card_bounds = candidate.button.bounds

            def belongs_to_card(item: Union[ImageState, TextState]) -> bool:
                if item.bounds is None:
                    return False
                center = Point(
                    (item.bounds.left + item.bounds.right) / 2.0,
                    (item.bounds.top + item.bounds.bottom) / 2.0,
                )
                return card_bounds.contains(center)

            def images(suffix: str) -> Tuple[ImageState, ...]:
                return tuple(
                    item
                    for item in ui_state.images
                    if item.path == root + suffix
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and belongs_to_card(item)
                )
            emotion = tuple(
                item
                for item in ui_state.texts
                if item.path == root + "energy/Text"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and re.fullmatch(r"(?:[0-9]|[1-9][0-9]|1[0-4][0-9]|150)", item.text)
                and belongs_to_card(item)
            )
            ship_icon = images("ship_icon")
            ship_type = images("info/top/type")
            frame = images("front/frame")
            status = images("dockyard/status")
            if (
                (len(emotion) > 1 or (require_emotion and len(emotion) != 1))
                or len(ship_icon) != 1
                or len(ship_type) != 1
                or len(frame) != 1
                or len(status) > 1
                or ship_type[0].sprite not in type_names
                or frame[0].sprite not in rarity_names
                or not ship_icon[0].sprite
            ):
                raise SemanticGateClosed(
                    "GemsFarming Dock card semantics are incomplete"
                )
            status_sprite = status[0].sprite if status else ""
            fleet_match = re.fullmatch(r"biandui0?([1-6])", status_sprite)
            if fleet_match is not None:
                fleet_index = int(fleet_match.group(1))
                context = self._gems_farming_open_slot_context
                availability = (
                    "current"
                    if context is not None
                    and context[1] == ship_icon[0].sprite
                    and context[2] == fleet_index
                    else "free"
                )
            elif not status_sprite:
                fleet_index = 0
                availability = "free"
            else:
                fleet_index = 0
                availability = status_sprite
            result.append(
                GemsFarmingDockCandidate(
                    position=candidate.position,
                    ship_id=candidate.ship_id,
                    ship_name=candidate.ship_name,
                    ship_sprite=ship_icon[0].sprite,
                    ship_type=type_names[ship_type[0].sprite],
                    rarity=rarity_names[frame[0].sprite],
                    level=candidate.level,
                    emotion=int(emotion[0].text) if emotion else None,
                    fleet_index=fleet_index,
                    status=availability,
                    button=candidate.button,
                )
            )
        if state.generation > ui_state.generation:
            raise SemanticGateClosed("GemsFarming Dock candidate snapshots are incoherent")
        return tuple(result)

    def gems_farming_dock_candidates(
        self, *, ship_ids: Optional[Iterable[int]] = None, require_emotion: bool = True
    ) -> Tuple[GemsFarmingDockCandidate, ...]:
        """Return a stable typed Dock view without OCR or templates."""

        if not isinstance(require_emotion, bool):
            raise TypeError("Dock require_emotion must be boolean")
        exact_ship_ids: Optional[FrozenSet[int]] = None
        if ship_ids is not None:
            exact_ship_ids = frozenset(ship_ids)
            if (
                not exact_ship_ids
                or any(
                    isinstance(ship_id, bool)
                    or not isinstance(ship_id, int)
                    or ship_id <= 0
                    for ship_id in exact_ship_ids
                )
            ):
                raise ValueError("GemsFarming exact ship IDs are invalid")

        retryable = (
            "enhancement Dock card identity is incomplete",
            "GemsFarming Dock card semantics are incomplete",
            "GemsFarming Dock candidate snapshots are incoherent",
        )
        last_error: Optional[SemanticGateClosed] = None
        last_result: Tuple[GemsFarmingDockCandidate, ...] = ()
        # The live Dock replaces its virtualized cards with off-screen ``-1``
        # placeholders while a new filter is loading.  Upstream deliberately
        # waits about 1.2 seconds before treating that view as empty.  Preserve
        # that timing boundary here: a non-empty typed view may return early,
        # while a genuinely empty filter still returns after the bounded wait.
        for attempt in range(13):
            try:
                if exact_ship_ids is None:
                    last_result = (self._gems_farming_dock_candidates_once() if require_emotion
                                   else self._gems_farming_dock_candidates_once(require_emotion=False))
                else:
                    last_result = self._gems_farming_dock_candidates_once(
                        ship_ids=exact_ship_ids, **({} if require_emotion else {"require_emotion": False})
                    )
            except SemanticGateClosed as exc:
                if str(exc) not in retryable:
                    raise
                last_error = exc
            else:
                if last_result:
                    return last_result
                last_error = None
            if attempt < 12:
                self._sleep(0.1)
        if last_error is not None:
            raise SemanticGateClosed(
                "GemsFarming Dock candidate snapshots did not stabilize"
            ) from last_error
        return last_result

    def click_gems_farming_candidate(
        self, candidate: GemsFarmingDockCandidate
    ) -> ActionReceipt:
        """Select one unchanged typed candidate and prove the 1/1 counter."""

        if not isinstance(candidate, GemsFarmingDockCandidate):
            raise TypeError("GemsFarming candidate is invalid")
        identity = (
            candidate.ship_id,
            candidate.ship_name,
            candidate.ship_sprite,
            candidate.ship_type,
            candidate.rarity,
            candidate.level,
            candidate.emotion,
            candidate.fleet_index,
            candidate.status,
        )
        stable_signature: Optional[Tuple[str, Bounds, Point]] = None
        stable_reads = 0
        for attempt in range(20):
            # A broad recovery filter may contain unrelated cards whose
            # optional semantics are incomplete. Re-prove only the selected
            # immutable ship identity here; duplicate cards with the same ID
            # remain visible and must still resolve uniquely by full identity
            # and bounds below.
            current = self.gems_farming_dock_candidates(
                ship_ids=(candidate.ship_id,)
            )
            matches = tuple(item for item in current if item == candidate)
            if len(matches) != 1:
                matches = tuple(
                    item
                    for item in current
                    if (
                        item.ship_id,
                        item.ship_name,
                        item.ship_sprite,
                        item.ship_type,
                        item.rarity,
                        item.level,
                        item.emotion,
                        item.fleet_index,
                        item.status,
                    )
                    == identity
                )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "GemsFarming Dock candidate changed or became ambiguous"
                )
            target = matches[0].button
            state = self.read_state()
            buttons = tuple(
                item
                for item in state.buttons
                if item.path == target.path
                and item.name == target.name
                and item.actionable
                and item.bounds == target.bounds
            )
            if (
                len(buttons) == 1
                and target.point is not None
                and target.bounds is not None
            ):
                signature = (target.path, target.bounds, target.point)
                if signature == stable_signature:
                    stable_reads += 1
                else:
                    stable_signature = signature
                    stable_reads = 1
                if stable_reads >= 3:
                    break
            else:
                stable_signature = None
                stable_reads = 0
            if attempt < 19:
                self._sleep(0.05)
        else:
            raise SemanticGateClosed("GemsFarming Dock candidate is not actionable")
        if self._blocking_rules(state, "gems-farming/dock/candidate"):
            raise SemanticGateClosed("GemsFarming Dock candidate input is blocked")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        receipt = ActionReceipt(
            semantic_id="gems-farming/dock/ship/{0}".format(candidate.ship_id),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )
        for _ in range(40):
            self._sleep(0.05)
            # The selected-count postcondition owns only this exact Text.
            # Large Dock views may truncate unrelated Toggle records.
            ui_state = self.read_text_state()
            if self._gems_farming_one_ship_selected(ui_state):
                return receipt
        raise SemanticGateClosed("GemsFarming Dock candidate did not select")

    def cancel_gems_farming_candidate_selection(self) -> ActionReceipt:
        hard_context = self._gems_farming_hard_open_slot_context
        if hard_context is not None:
            state = self.read_state()
            controls = tuple(
                item
                for item in state.buttons
                if item.path.endswith("/select_panel/cancel_button")
                and item.name == "cancel_button"
            )
            if len(controls) != 1:
                raise SemanticGateClosed(
                    "GemsFarming hard Dock cancel is absent or ambiguous"
                )
            receipt = self._gems_equipment_click_button(
                state, controls[0], "tactical/dock/cancel"
            )
            stage_code, _, _, _ = hard_context
            self._retry_transition_read(
                lambda: self.campaign_fleet_selection_state(stage_code),
                attempts=50,
                interval_seconds=0.1,
            )
            self._gems_farming_hard_open_slot_context = None
            return receipt
        receipt = self.click("tactical/dock/cancel")
        self._retry_transition_read(
            self._gems_farming_formation_records,
            attempts=50,
            interval_seconds=0.1,
        )
        return receipt

    def confirm_gems_farming_candidate_selection(
        self, candidate: GemsFarmingDockCandidate, role: str
    ) -> ActionReceipt:
        """Confirm exactly one selected ship and prove it mounted in formation."""

        if not isinstance(candidate, GemsFarmingDockCandidate):
            raise TypeError("GemsFarming candidate is invalid")
        slot_names = {"flagship": "main_1", "vanguard": "vanguard_1"}
        if role not in slot_names:
            raise ValueError("GemsFarming role must be flagship or vanguard")
        # A large unfiltered Dock can exhaust the unrelated Toggle slice.
        # Confirmation owns only the exact 1/1 Text record; keep that slice
        # complete and fail closed without making Toggle completeness global.
        ui_state = self.read_text_state()
        if not self._gems_farming_one_ship_selected(ui_state):
            raise SemanticGateClosed("GemsFarming Dock selection count changed")
        hard_context = self._gems_farming_hard_open_slot_context
        if hard_context is not None:
            state = self.read_state()
            controls = tuple(
                item
                for item in state.buttons
                if item.path.endswith("/select_panel/confirm_button")
                and item.name == "confirm_button"
            )
            if len(controls) != 1:
                raise SemanticGateClosed(
                    "GemsFarming hard Dock confirm is absent or ambiguous"
                )
            receipt = self._gems_equipment_click_button(
                state, controls[0], "tactical/dock/confirm"
            )
            stage_code, fleet_index, hard_role, before = hard_context
            if role != hard_role:
                raise SemanticGateClosed(
                    "GemsFarming hard replacement role changed before confirmation"
                )
            for _ in range(60):
                self._sleep(0.1)
                try:
                    _, _, cards, after = self._gems_farming_hard_role_cards(
                        stage_code, fleet_index, role
                    )
                except SemanticGateClosed:
                    continue
                if len(cards) == 3 and after == before + (candidate.ship_sprite,):
                    self._gems_farming_hard_open_slot_context = None
                    return receipt
            raise SemanticGateClosed(
                "GemsFarming hard replacement postcondition was not proven"
            )
        receipt = self.click("tactical/dock/confirm")
        expected_suffix = "/{0}_root/mouseChild".format(candidate.ship_sprite)
        for _ in range(60):
            self._sleep(0.1)
            try:
                _, after, _ = self._gems_farming_formation_records()
            except SemanticGateClosed:
                continue
            slot_path = (
                "UICamera/Canvas/UIMain/FormationUI(Clone)/adapt/GridFrame/"
                + slot_names[role]
                + "/shadow"
            )
            slots = tuple(item for item in after.images if item.path == slot_path)
            if len(slots) != 1 or slots[0].bounds is None:
                continue
            slot_center_x = (slots[0].bounds.left + slots[0].bounds.right) / 2.0
            mounted = tuple(
                item
                for item in after.images
                if item.path.endswith(expected_suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.bounds is not None
                and abs(
                    (item.bounds.left + item.bounds.right) / 2.0 - slot_center_x
                )
                <= 2.0
            )
            if len(mounted) == 1:
                return receipt
        raise SemanticGateClosed("GemsFarming replacement postcondition was not proven")
