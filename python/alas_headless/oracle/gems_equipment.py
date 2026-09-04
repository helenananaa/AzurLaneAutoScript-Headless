"""Gems equipment for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple, Union
from .contracts import (
    ActionReceipt,
    Bounds,
    ButtonState,
    GemsFarmingEquipmentLoadout,
    GemsFarmingEquipmentSlot,
    ImageState,
    OracleState,
    Point,
    TextState,
    UiState,
)
from .errors import SemanticGateClosed


class GemsEquipmentOracle:
    """Gems equipment operations sharing the oracle frame and input boundary."""

    @staticmethod
    def _gems_equipment_center(bounds: Bounds) -> Point:
        return Point(
            (bounds.left + bounds.right) / 2.0,
            (bounds.top + bounds.bottom) / 2.0,
        )

    @staticmethod
    def _gems_equipment_in_bounds(
        item: Union[ImageState, TextState], bounds: Bounds
    ) -> bool:
        return item.bounds is not None and bounds.contains(
            GemsEquipmentOracle._gems_equipment_center(item.bounds)
        )

    def _gems_equipment_click_button(
        self,
        state: OracleState,
        button: ButtonState,
        semantic_id: str,
        *,
        require_raycast_top: bool = False,
    ) -> ActionReceipt:
        if (
            not button.active_in_hierarchy
            or not button.active_and_enabled
            or not button.interactable
            or button.point is None
            or button.bounds is None
            or not button.bounds.contains(button.point)
            or (require_raycast_top and button.raycast_top is not True)
        ):
            raise SemanticGateClosed(semantic_id + " is not safely actionable")
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed(semantic_id + " input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before equipment input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after equipment input")
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=button.point,
            bounds=button.bounds,
            path=button.path,
        )

    def _gems_equipment_open_ship_detail(self, role: str) -> ActionReceipt:
        """Enter ALAS's flagship or first-vanguard detail through typed Formation."""

        if role not in ("flagship", "vanguard"):
            raise ValueError("GemsFarming role must be flagship or vanguard")
        state = self.read_state()
        ui_state = self.read_ui_state()
        already_detail = tuple(
            item
            for item in ui_state.toggles
            if item.path.endswith("/bottom/toggle_list/detail_toggle")
            and item.name == "detail_toggle"
            and item.checked
            and item.active_in_hierarchy
            and item.active_and_enabled
        )
        if len(already_detail) > 1:
            raise SemanticGateClosed("GemsFarming Formation detail state is ambiguous")
        if not already_detail:
            state, ui_state, _ = self._gems_farming_formation_records()
        toggles = tuple(
            item
            for item in ui_state.toggles
            if item.path.endswith("/bottom/toggle_list/detail_toggle")
            and item.name == "detail_toggle"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.point is not None
            and item.bounds is not None
            and item.bounds.contains(item.point)
        )
        if len(toggles) != 1:
            raise SemanticGateClosed("GemsFarming Formation detail toggle is incomplete")
        if not toggles[0].checked:
            if self._blocking_rules(state, "gems-farming/equipment/detail-toggle"):
                raise SemanticGateClosed("GemsFarming Formation detail toggle is blocked")
            self._tap(
                int(round(toggles[0].point.x)), int(round(toggles[0].point.y))
            )
            self._sleep(0.2)

        def detail_card() -> Tuple[OracleState, ImageState]:
            current = self.read_state()
            current_ui = self.read_ui_state()
            group = "main" if role == "flagship" else "vanguard"
            suffix = "/attr_frame/{0}/list/RectShipCardTpl(Clone)/content/detail".format(
                group
            )
            cards = tuple(
                item
                for item in current_ui.images
                if item.path.endswith(suffix)
                and item.sprite == "rect_bg"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            cards = tuple(sorted(cards, key=lambda item: item.bounds.left))
            if not cards:
                raise SemanticGateClosed("GemsFarming Formation detail cards are absent")
            target = cards[0]
            if role == "flagship":
                flags = tuple(
                    item
                    for item in current_ui.images
                    if item.path.endswith(
                        "/attr_frame/main/list/RectShipCardTpl(Clone)/content/front/flag"
                    )
                    and item.sprite == "flag_icon"
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and item.bounds is not None
                    and self._bounds_overlap(item.bounds, target.bounds) > 0
                )
                if len(flags) != 1:
                    raise SemanticGateClosed(
                        "GemsFarming flagship detail identity is incomplete"
                    )
            if current.generation > current_ui.generation:
                raise SemanticGateClosed("GemsFarming detail snapshots are incoherent")
            return current, target

        card_state, card = self._retry_transition_read(
            detail_card, attempts=120, interval_seconds=0.1
        )
        assert card.bounds is not None
        point = self._gems_equipment_center(card.bounds)
        semantic_id = "gems-farming/equipment/{0}/detail".format(role)
        if self._blocking_rules(card_state, semantic_id):
            raise SemanticGateClosed("GemsFarming detail card input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before equipment detail")
        self._tap(int(round(point.x)), int(round(point.y)))
        receipt = ActionReceipt(
            semantic_id=semantic_id,
            generation=card_state.generation,
            point=point,
            bounds=card.bounds,
            path=card.path,
        )
        self._gems_equipment_stable_detail_loadout()
        return receipt

    def _gems_equipment_read_loadout(
        self,
    ) -> Tuple[OracleState, UiState, Tuple[GemsFarmingEquipmentSlot, ...]]:
        state = self.read_state()
        ui_state = self.read_ui_state()
        regular_path = (
            "/ShipDetailView(Clone)/equipments/"
            "equipments/equipment_tpl(Clone)"
        )
        empty_path = (
            "/ShipDetailView(Clone)/equipments/equipments/empty_tpl(Clone)"
        )
        regular = tuple(
            sorted(
                (
                    item
                    for item in state.buttons
                    if item.path.endswith((regular_path, empty_path))
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and item.interactable
                    and item.point is not None
                    and item.bounds is not None
                ),
                key=lambda item: item.bounds.left,
            )
        )
        special_path = "/ShipDetailView(Clone)/equipments/SpSlot"
        special = tuple(
            item
            for item in state.buttons
            if item.path.endswith(special_path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.point is not None
            and item.bounds is not None
        )
        if len(regular) != 5 or len(special) != 1:
            raise SemanticGateClosed("GemsFarming ship equipment slots are incomplete")
        slots = []
        for position, button in enumerate(regular, start=1):
            assert button.bounds is not None
            icon_path = button.path + "/IconTpl/icon_bg/icon"
            level_path = button.path + "/IconTpl/icon_bg/slv/Text"
            icons = tuple(
                item
                for item in ui_state.images
                if item.path == icon_path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.sprite
                and self._gems_equipment_in_bounds(item, button.bounds)
            )
            levels = tuple(
                item
                for item in ui_state.texts
                if item.path == level_path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and re.fullmatch(r"(?:[0-9]|1[0-5])", item.text)
                and self._gems_equipment_in_bounds(item, button.bounds)
            )
            if not icons and not levels:
                continue
            if len(icons) != 1 or len(levels) > 1:
                raise SemanticGateClosed("GemsFarming regular equipment is ambiguous")
            slots.append(
                GemsFarmingEquipmentSlot(
                    position=position,
                    equipment_id=icons[0].sprite,
                    enhancement=int(levels[0].text) if levels else 0,
                    special=False,
                )
            )
        special_button = special[0]
        assert special_button.bounds is not None
        special_icons = tuple(
            item
            for item in ui_state.images
            if item.path.endswith(special_path + "/Icon/Mask/icon_bg/icon")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.sprite
            and self._gems_equipment_in_bounds(item, special_button.bounds)
        )
        special_levels = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(special_path + "/Icon/LV/Text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and re.fullmatch(r"(?:[0-9]|1[0-5])", item.text)
            and self._gems_equipment_in_bounds(item, special_button.bounds)
        )
        if special_icons or special_levels:
            if len(special_icons) != 1 or len(special_levels) > 1:
                raise SemanticGateClosed("GemsFarming special equipment is ambiguous")
            slots.append(
                GemsFarmingEquipmentSlot(
                    position=6,
                    equipment_id=special_icons[0].sprite,
                    enhancement=(
                        int(special_levels[0].text) if special_levels else 0
                    ),
                    special=True,
                )
            )
        if state.generation > ui_state.generation:
            raise SemanticGateClosed("GemsFarming equipment snapshots are incoherent")
        return state, ui_state, tuple(slots)

    def _gems_equipment_stable_detail_loadout(
        self,
    ) -> Tuple[OracleState, UiState, Tuple[GemsFarmingEquipmentSlot, ...]]:
        """Require five identical typed detail reads before branching on emptiness."""

        previous: Optional[Tuple[GemsFarmingEquipmentSlot, ...]] = None
        stable_reads = 0
        observed: Optional[
            Tuple[OracleState, UiState, Tuple[GemsFarmingEquipmentSlot, ...]]
        ] = None
        last_error: Optional[SemanticGateClosed] = None
        for _ in range(50):
            try:
                observed = self._gems_equipment_read_loadout()
            except SemanticGateClosed as exc:
                last_error = exc
                previous = None
                stable_reads = 0
                self._sleep(0.1)
                continue
            current = observed[2]
            if current == previous:
                stable_reads += 1
            else:
                previous = current
                stable_reads = 1
            if stable_reads >= 5:
                return observed
            self._sleep(0.1)
        raise SemanticGateClosed(
            "GemsFarming detail loadout did not stabilize"
        ) from last_error

    def _gems_equipment_unload_detail_slot(
        self, slot: GemsFarmingEquipmentSlot
    ) -> None:
        if slot.special or not 1 <= slot.position <= 5:
            raise SemanticGateClosed(
                "GemsFarming only unloads the five ALAS equipment-code slots"
            )
        state, _, current = self._gems_equipment_stable_detail_loadout()
        if tuple(item for item in current if item.position == slot.position) != (slot,):
            raise SemanticGateClosed("GemsFarming unload equipment identity changed")
        suffixes = (
            "/ShipDetailView(Clone)/equipments/equipments/equipment_tpl(Clone)",
            "/ShipDetailView(Clone)/equipments/equipments/empty_tpl(Clone)",
        )
        buttons = tuple(
            sorted(
                (
                    item
                    for item in state.buttons
                    if item.path.endswith(suffixes)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and item.interactable
                    and item.bounds is not None
                    and item.point is not None
                ),
                key=lambda item: item.bounds.left,
            )
        )
        if len(buttons) != 5:
            raise SemanticGateClosed("GemsFarming ship equipment slots are incomplete")
        self._gems_equipment_click_button(
            state,
            buttons[slot.position - 1],
            "gems-farming/equipment/slot/{0}/unload-open".format(slot.position),
        )
        action_path = (
            "OverlayCamera/Overlay/UIMain/EquipmentInfoUI(Clone)/default/"
            "actions/action_button_4"
        )

        def require_unload() -> Tuple[OracleState, ButtonState]:
            current_state = self.read_state()
            text_state = self.read_text_state()
            actions = tuple(
                item for item in current_state.buttons if item.path == action_path
            )
            labels = tuple(
                item
                for item in text_state.texts
                if item.path == action_path + "/change"
                and item.text == "卸 下"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(actions) != 1 or len(labels) != 1:
                raise SemanticGateClosed(
                    "GemsFarming unload equipment action is incomplete"
                )
            return current_state, actions[0]

        action_state, action = self._retry_transition_read(
            require_unload, attempts=30, interval_seconds=0.1
        )
        self._gems_equipment_click_button(
            action_state,
            action,
            "gems-farming/equipment/slot/{0}/unload".format(slot.position),
        )
        _, _, after = self._gems_equipment_stable_detail_loadout()
        if any(item.position == slot.position for item in after):
            raise SemanticGateClosed("GemsFarming equipment slot did not unload")

    def _gems_equipment_back_to_formation(self) -> ActionReceipt:
        receipt: Optional[ActionReceipt] = None
        for depth in range(4):
            try:
                self._gems_farming_formation_records()
                if receipt is None:
                    raise SemanticGateClosed(
                        "GemsFarming equipment return performed no navigation"
                    )
                return receipt
            except SemanticGateClosed:
                pass

            state = self.read_state()
            ui_state = self.read_ui_state()
            toggles = tuple(
                item
                for item in ui_state.toggles
                if item.path.endswith("/bottom/toggle_list/formation_toggle")
                and item.name == "formation_toggle"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.interactable
                and item.point is not None
                and item.bounds is not None
                and item.bounds.contains(item.point)
            )
            if len(toggles) > 1:
                raise SemanticGateClosed(
                    "GemsFarming Formation view toggle is ambiguous"
                )
            if len(toggles) == 1:
                toggle = toggles[0]
                if not toggle.checked:
                    semantic_id = "gems-farming/equipment/formation-toggle"
                    if self._blocking_rules(state, semantic_id):
                        self._sleep(0.1)
                        continue
                    assert toggle.point is not None and toggle.bounds is not None
                    self._tap(
                        int(round(toggle.point.x)), int(round(toggle.point.y))
                    )
                    if receipt is None:
                        receipt = ActionReceipt(
                            semantic_id=semantic_id,
                            generation=state.generation,
                            point=toggle.point,
                            bounds=toggle.bounds,
                            path=toggle.path,
                        )
                self._sleep(0.5)
                continue

            suffix = "/blur_panel/adapt/top/back_btn"
            buttons = tuple(
                item
                for item in state.buttons
                if item.name == "back_btn" and item.path.endswith(suffix)
            )
            if len(buttons) != 1:
                raise SemanticGateClosed(
                    "GemsFarming equipment back control is incomplete"
                )
            current_receipt = self._gems_equipment_click_button(
                state,
                buttons[0],
                "gems-farming/equipment/back/{0}".format(depth + 1),
            )
            if receipt is None:
                receipt = current_receipt
            self._sleep(0.2)
        raise SemanticGateClosed("GemsFarming equipment return did not settle")

    def gems_farming_equipment_take_off(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        """Capture and unload ALAS's five equipment-code slots."""

        if role in self._gems_farming_equipment_loadouts:
            raise SemanticGateClosed(
                "GemsFarming equipment transfer is already pending for " + role
            )
        self._gems_equipment_open_ship_detail(role)
        _, _, observed = self._gems_equipment_stable_detail_loadout()
        slots = tuple(item for item in observed if not item.special)
        special = tuple(item for item in observed if item.special)
        for slot in slots:
            self._gems_equipment_unload_detail_slot(slot)
        _, _, after = self._gems_equipment_stable_detail_loadout()
        if tuple(item for item in after if not item.special):
            raise SemanticGateClosed("GemsFarming equipment did not unload")
        if tuple(item for item in after if item.special) != special:
            raise SemanticGateClosed("GemsFarming special equipment changed")
        loadout = GemsFarmingEquipmentLoadout(role=role, slots=slots)
        self._gems_farming_equipment_loadouts[role] = loadout
        self._gems_equipment_back_to_formation()
        return loadout

    @staticmethod
    def _gems_equipment_overview_path(position: int) -> str:
        paths = {
            1: "OverlayCamera/Overlay/UIMain/equipment_r_container(Adapt)/equipment_r_container/equipment_r/equipment/equipment_r1",
            2: "OverlayCamera/Overlay/UIMain/equipment_r_container(Adapt)/equipment_r_container/equipment_r/equipment/equipment_r2",
            3: "OverlayCamera/Overlay/UIMain/equipment_r_container(Adapt)/equipment_r_container/equipment_r/equipment/equipment_r3",
            4: "OverlayCamera/Overlay/UIMain/equipment_l_container(Adapt)/equipment_l_container/equipment_l/equipment/equipment_l1",
            5: "OverlayCamera/Overlay/UIMain/equipment_l_container(Adapt)/equipment_l_container/equipment_l/equipment/equipment_l2",
            6: "OverlayCamera/Overlay/UIMain/equipment_b_container(Adapt)/equipment_b_container/equipment_b/equipment",
        }
        try:
            return paths[position]
        except KeyError as exc:
            raise ValueError("GemsFarming equipment position is invalid") from exc

    def _gems_equipment_overview_loadout(
        self,
    ) -> Tuple[OracleState, UiState, Tuple[GemsFarmingEquipmentSlot, ...]]:
        state = self.read_state()
        ui_state = self.read_ui_state()
        slots = []
        for position in range(1, 7):
            root = self._gems_equipment_overview_path(position)
            buttons = tuple(
                item
                for item in state.buttons
                if item.path == root
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.interactable
                and item.point is not None
                and item.bounds is not None
            )
            if position == 6 and not buttons:
                continue
            if len(buttons) != 1:
                raise SemanticGateClosed(
                    "GemsFarming equipment overview slot is incomplete"
                )
            icon_suffix = (
                "/info/Icon/Mask/icon_bg/icon"
                if position == 6
                else "/info/IconTpl/icon_bg/icon"
            )
            level_suffix = (
                "/info/Icon/LV/Text"
                if position == 6
                else "/info/IconTpl/icon_bg/slv/Text"
            )
            icons = tuple(
                item
                for item in ui_state.images
                if item.path == root + icon_suffix
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.sprite
            )
            levels = tuple(
                item
                for item in ui_state.texts
                if item.path == root + level_suffix
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and re.fullmatch(r"(?:[0-9]|1[0-5])", item.text)
            )
            if not icons and not levels:
                continue
            if len(icons) != 1 or len(levels) > 1:
                raise SemanticGateClosed(
                    "GemsFarming equipment overview identity is ambiguous"
                )
            slots.append(
                GemsFarmingEquipmentSlot(
                    position=position,
                    equipment_id=icons[0].sprite,
                    enhancement=int(levels[0].text) if levels else 0,
                    special=position == 6,
                )
            )
        if state.generation > ui_state.generation:
            raise SemanticGateClosed("GemsFarming overview snapshots are incoherent")
        return state, ui_state, tuple(slots)

    def _gems_equipment_open_detail_store(
        self, slot: GemsFarmingEquipmentSlot
    ) -> None:
        state, _, current = self._gems_equipment_stable_detail_loadout()
        mounted = tuple(item for item in current if item.position == slot.position)
        if len(mounted) > 1:
            raise SemanticGateClosed(
                "GemsFarming occupied equipment slot is not uniquely mounted"
            )
        regular_suffixes = (
            "/ShipDetailView(Clone)/equipments/equipments/equipment_tpl(Clone)",
            "/ShipDetailView(Clone)/equipments/equipments/empty_tpl(Clone)",
        )
        regular = tuple(
            sorted(
                (
                    item
                    for item in state.buttons
                    if item.path.endswith(regular_suffixes)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and item.interactable
                    and item.bounds is not None
                    and item.point is not None
                ),
                key=lambda item: item.bounds.left,
            )
        )
        special = tuple(
            item
            for item in state.buttons
            if item.path.endswith("/ShipDetailView(Clone)/equipments/SpSlot")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.interactable
            and item.bounds is not None
            and item.point is not None
        )
        if len(regular) != 5 or len(special) != 1:
            raise SemanticGateClosed("GemsFarming ship equipment slots are incomplete")
        button = special[0] if slot.special else regular[slot.position - 1]
        self._gems_equipment_click_button(
            state,
            button,
            "gems-farming/equipment/slot/{0}/occupied".format(slot.position),
        )
        page = "SpWeaponStoreHouseUI(Clone)" if slot.special else "StoreHouseUI(Clone)"
        if not mounted:
            def require_empty_destination() -> str:
                current_state = self.read_state()
                if any(page in item.path for item in current_state.buttons):
                    return "store"
                try:
                    self._gems_equipment_overview_loadout()
                except SemanticGateClosed as exc:
                    raise SemanticGateClosed(
                        "GemsFarming empty equipment destination is incomplete"
                    ) from exc
                return "overview"

            destination = self._retry_transition_read(
                require_empty_destination, attempts=50, interval_seconds=0.1
            )
            if destination == "overview":
                self._gems_equipment_open_store(slot)
            return

        dialog = "SpWeaponInfoUI(Clone)" if slot.special else "EquipmentInfoUI(Clone)"
        action_path = (
            "OverlayCamera/Overlay/UIMain/{0}/default/actions/action_button_3".format(
                dialog
            )
        )

        def require_change() -> Tuple[OracleState, ButtonState]:
            current_state = self.read_state()
            text_state = self.read_text_state()
            buttons = tuple(
                item for item in current_state.buttons if item.path == action_path
            )
            texts = tuple(
                item
                for item in text_state.texts
                if item.path == action_path + "/change"
                and item.text == "更 换"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(buttons) != 1 or len(texts) != 1:
                raise SemanticGateClosed(
                    "GemsFarming occupied equipment action is incomplete"
                )
            return current_state, buttons[0]

        action_state, change = self._retry_transition_read(
            require_change, attempts=30, interval_seconds=0.1
        )
        self._gems_equipment_click_button(
            action_state,
            change,
            "gems-farming/equipment/slot/{0}/change".format(slot.position),
        )
        def require_store() -> bool:
            current_state = self.read_state()
            if not any(page in item.path for item in current_state.buttons):
                raise SemanticGateClosed("GemsFarming equipment store did not open")
            return True

        self._retry_transition_read(require_store, attempts=50, interval_seconds=0.1)

    def _gems_equipment_open_store(self, slot: GemsFarmingEquipmentSlot) -> None:
        state, _, _ = self._retry_transition_read(
            self._gems_equipment_overview_loadout,
            attempts=30,
            interval_seconds=0.1,
        )
        path = self._gems_equipment_overview_path(slot.position)
        buttons = tuple(item for item in state.buttons if item.path == path)
        if len(buttons) != 1:
            raise SemanticGateClosed("GemsFarming equipment slot control changed")
        self._gems_equipment_click_button(
            state,
            buttons[0],
            "gems-farming/equipment/slot/{0}/store".format(slot.position),
        )
        page = "SpWeaponStoreHouseUI(Clone)" if slot.special else "StoreHouseUI(Clone)"

        def require_store() -> bool:
            current = self.read_state()
            if not any(page in item.path for item in current.buttons):
                raise SemanticGateClosed("GemsFarming equipment store did not open")
            return True

        self._retry_transition_read(require_store, attempts=50, interval_seconds=0.1)

    def _gems_equipment_store_candidate(
        self, slot: GemsFarmingEquipmentSlot
    ) -> Tuple[OracleState, ButtonState, Point]:
        state = self.read_state()
        ui_state = self.read_ui_state()
        candidates = []
        if slot.special:
            prefix = (
                "UICamera/Canvas/UIMain/SpWeaponStoreHouseUI(Clone)/adapt/"
                "ScrollView/Viewport/Content/StoreHouse/Grid/Template(Clone)"
            )
            cards = tuple(
                item
                for item in state.buttons
                if item.path == prefix
                and item.active_in_hierarchy
                and item.active_and_enabled
                and item.interactable
                and item.bounds is not None
                and item.point is not None
            )
            for card in cards:
                assert card.bounds is not None
                icons = tuple(
                    item
                    for item in ui_state.images
                    if item.path == prefix + "/frame/bg/icon_bg/icon"
                    and item.sprite == slot.equipment_id
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and self._gems_equipment_in_bounds(item, card.bounds)
                )
                levels = tuple(
                    item
                    for item in ui_state.texts
                    if item.path == prefix + "/frame/bg/icon_bg/slv/Text"
                    and re.fullmatch(r"(?:[0-9]|1[0-5])", item.text)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and self._gems_equipment_in_bounds(item, card.bounds)
                )
                assigned = tuple(
                    item
                    for item in ui_state.images
                    if item.path.startswith(prefix + "/frame/bg/equip_flag")
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                    and self._gems_equipment_in_bounds(item, card.bounds)
                )
                observed_enhancement = (
                    int(levels[0].text) if len(levels) == 1 else 0
                )
                if (
                    len(icons) == 1
                    and len(levels) <= 1
                    and observed_enhancement == slot.enhancement
                    and not assigned
                ):
                    assert icons[0].bounds is not None
                    candidates.append(
                        (card, self._gems_equipment_center(icons[0].bounds))
                    )
        else:
            prefix = (
                "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/"
                "equipment_scrollview/equipment_grid/"
            )
            for card in state.buttons:
                match = re.fullmatch(re.escape(prefix) + r"([0-9]+)", card.path)
                if (
                    match is None
                    or not card.active_in_hierarchy
                    or not card.active_and_enabled
                    or not card.interactable
                    or card.bounds is None
                    or card.point is None
                ):
                    continue
                root = card.path
                icons = tuple(
                    item
                    for item in ui_state.images
                    if item.path == root + "/frame/bg/icon_bg/icon"
                    and item.sprite == slot.equipment_id
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                levels = tuple(
                    item
                    for item in ui_state.texts
                    if item.path == root + "/frame/bg/icon_bg/slv/Text"
                    and re.fullmatch(r"(?:[0-9]|1[0-5])", item.text)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                assigned = tuple(
                    item
                    for item in ui_state.images
                    if item.path.startswith(root + "/frame/bg/equip_flag")
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                observed_enhancement = (
                    int(levels[0].text) if len(levels) == 1 else 0
                )
                if (
                    len(icons) == 1
                    and len(levels) <= 1
                    and observed_enhancement == slot.enhancement
                    and not assigned
                ):
                    assert icons[0].bounds is not None
                    candidates.append(
                        (card, self._gems_equipment_center(icons[0].bounds))
                    )
        visible = tuple(
            item
            for item in candidates
            if item[0].bounds is not None
            and item[0].bounds.contains(item[1])
            and item[0].bounds.top >= 40.0
            and item[0].bounds.bottom <= 680.0
        )
        visible = tuple(
            sorted(
                visible,
                key=lambda item: (
                    item[0].bounds.top,
                    item[0].bounds.left,
                    item[0].path,
                ),
            )
        )
        if not visible:
            raise SemanticGateClosed("GemsFarming equipment is not visible in store")
        if state.generation > ui_state.generation:
            raise SemanticGateClosed("GemsFarming store snapshots are incoherent")
        return state, visible[0][0], visible[0][1]

    def _gems_equipment_reset_store(self, special: bool) -> None:
        if self._swipe is None:
            raise SemanticGateClosed("GemsFarming equipment store requires typed swipe")
        previous_regular_top: Optional[Tuple[int, int]] = None
        for _ in range(12):
            state = self.read_state()
            ui_state = self.read_ui_state()
            if special:
                banner = tuple(
                    item
                    for item in ui_state.texts
                    if item.path.endswith(
                        "/SpWeaponStoreHouseUI(Clone)/adapt/ScrollView/Viewport/Content/StoreHouse/Banner/Text"
                    )
                    and item.bounds is not None
                )
                at_top = len(banner) == 1 and banner[0].bounds.top >= 0.0
            else:
                prefix = (
                    "UICamera/Canvas/UIMain/StoreHouseUI(Clone)/adapt/"
                    "equipment_scrollview/equipment_grid/"
                )
                visible_indices = tuple(
                    (
                        int(item.path[len(prefix) :]),
                        int(round(item.bounds.top)),
                    )
                    for item in state.buttons
                    if item.path.startswith(prefix)
                    and item.path[len(prefix) :].isdigit()
                    and item.bounds is not None
                    and item.bounds.bottom >= 0.0
                    and item.bounds.top <= 680.0
                )
                # A partially scrolled first page can still expose an index
                # below 7. Treating that as the top made the subsequent
                # downward-only search miss equipment immediately above the
                # viewport. Prove the upper boundary by one unchanged upward
                # swipe instead of assuming a particular grid index origin.
                regular_top = min(visible_indices) if visible_indices else None
                at_top = (
                    regular_top is not None
                    and regular_top == previous_regular_top
                )
                previous_regular_top = regular_top
            if at_top:
                return
            if self._blocking_rules(state, "gems-farming/equipment/store/reset"):
                raise SemanticGateClosed("GemsFarming equipment store swipe is blocked")
            self._swipe(640, 160, 640, 600, 400)
            self._sleep(0.15)
        raise SemanticGateClosed("GemsFarming equipment store did not reset")

    def _gems_equipment_select_from_store(
        self, slot: GemsFarmingEquipmentSlot
    ) -> str:
        self._gems_equipment_reset_store(slot.special)
        candidate: Optional[Tuple[OracleState, ButtonState, Point]] = None
        previous_signature: Optional[Tuple[str, int, int]] = None
        stable_reads = 0
        for attempt in range(120):
            try:
                observed = self._gems_equipment_store_candidate(slot)
            except SemanticGateClosed as exc:
                if "not visible in store" not in str(exc):
                    raise
                observed = None
            if observed is not None:
                _, button, point = observed
                signature = (button.path, round(point.x), round(point.y))
                if signature == previous_signature:
                    stable_reads += 1
                else:
                    previous_signature = signature
                    stable_reads = 1
                if stable_reads >= 3:
                    candidate = observed
                    break
                self._sleep(0.25)
                continue
            previous_signature = None
            stable_reads = 0
            if self._swipe is None:
                raise SemanticGateClosed("GemsFarming equipment store requires typed swipe")
            current = self.read_state()
            if self._blocking_rules(current, "gems-farming/equipment/store/search"):
                raise SemanticGateClosed("GemsFarming equipment store swipe is blocked")
            self._swipe(640, 600, 640, 350, 300)
            self._sleep(0.15)
        if candidate is None:
            raise SemanticGateClosed(
                "GemsFarming equipment is unavailable: {0} +{1}".format(
                    slot.equipment_id, slot.enhancement
                )
            )
        state, button, point = candidate
        semantic_id = "gems-farming/equipment/slot/{0}/candidate/{1}".format(
            slot.position, slot.equipment_id
        )
        if button.bounds is None or not button.bounds.contains(point):
            raise SemanticGateClosed("GemsFarming equipment candidate moved")
        if self._blocking_rules(state, semantic_id):
            raise SemanticGateClosed("GemsFarming equipment candidate is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before equipment selection")
        self._tap(int(round(point.x)), int(round(point.y)))
        dialog = "SpWeaponInfoUI(Clone)" if slot.special else "EquipmentInfoUI(Clone)"
        prefix = "OverlayCamera/Overlay/UIMain/{0}/replace".format(dialog)

        def selection() -> Tuple[OracleState, ButtonState]:
            current = self.read_state()
            current_ui = self.read_ui_state()
            buttons = tuple(
                item
                for item in current.buttons
                if item.path == prefix + "/actions/action_button_2"
            )
            icons = tuple(
                item
                for item in current_ui.images
                if item.path == prefix + "/equipment_on_ship/info/equip/icon_bg/icon"
                and item.sprite == slot.equipment_id
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            levels = tuple(
                item
                for item in current_ui.texts
                if item.path == prefix + "/equipment_on_ship/info/equip/slv/Text"
                and item.text == str(slot.enhancement)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            observed_enhancement = int(levels[0].text) if len(levels) == 1 else 0
            if (
                len(buttons) != 1
                or len(icons) != 1
                or len(levels) > 1
                or observed_enhancement != slot.enhancement
            ):
                raise SemanticGateClosed("GemsFarming equipment selection changed")
            return current, buttons[0]

        selected_state, confirm = self._retry_transition_read(
            selection, attempts=30, interval_seconds=0.1
        )
        self._gems_equipment_click_button(
            selected_state,
            confirm,
            "gems-farming/equipment/slot/{0}/confirm".format(slot.position),
        )

        def require_mounted() -> str:
            for page, reader in (
                ("overview", self._gems_equipment_overview_loadout),
                ("detail", self._gems_equipment_read_loadout),
            ):
                try:
                    _, _, mounted = reader()
                except SemanticGateClosed:
                    continue
                matches = tuple(
                    item for item in mounted if item.position == slot.position
                )
                if matches == (slot,):
                    return page
            raise SemanticGateClosed("GemsFarming equipment mount was not proven")

        return self._retry_transition_read(
            require_mounted, attempts=50, interval_seconds=0.1
        )

    def gems_farming_equipment_take_on(
        self, role: str
    ) -> GemsFarmingEquipmentLoadout:
        """Mount the pending typed loadout on ALAS's current Formation ship."""

        try:
            loadout = self._gems_farming_equipment_loadouts[role]
        except KeyError as exc:
            raise SemanticGateClosed(
                "GemsFarming equipment transfer is not pending for " + role
            ) from exc
        if any(slot.special for slot in loadout.slots):
            raise SemanticGateClosed(
                "GemsFarming pending loadout exceeds ALAS's five equipment-code slots"
            )
        self._gems_equipment_open_ship_detail(role)
        _, _, current = self._gems_equipment_stable_detail_loadout()
        current_by_position = {
            slot.position: slot for slot in current if not slot.special
        }
        desired_by_position = {slot.position: slot for slot in loadout.slots}
        for position in tuple(sorted(current_by_position)):
            if position not in desired_by_position:
                self._gems_equipment_unload_detail_slot(
                    current_by_position[position]
                )
                del current_by_position[position]
        page = "detail"
        for slot in loadout.slots:
            if current_by_position.get(slot.position) == slot:
                continue
            if page == "detail":
                self._gems_equipment_open_detail_store(slot)
            else:
                self._gems_equipment_open_store(slot)
            page = self._gems_equipment_select_from_store(slot)
            reader = (
                self._gems_equipment_overview_loadout
                if page == "overview"
                else self._gems_equipment_stable_detail_loadout
            )
            _, _, observed = self._retry_transition_read(
                reader, attempts=30, interval_seconds=0.1
            )
            current_by_position = {
                item.position: item for item in observed if not item.special
            }
        reader = (
            self._gems_equipment_overview_loadout
            if page == "overview"
            else self._gems_equipment_stable_detail_loadout
        )
        _, _, mounted = self._retry_transition_read(
            reader, attempts=30, interval_seconds=0.1
        )
        mounted_regular = tuple(item for item in mounted if not item.special)
        if mounted_regular != loadout.slots:
            raise SemanticGateClosed("GemsFarming equipment loadout did not restore")
        self._gems_equipment_back_to_formation()
        del self._gems_farming_equipment_loadouts[role]
        return loadout
