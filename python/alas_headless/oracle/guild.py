"""Guild for the typed ALAS boundary."""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    GuildExchangeItemState,
    GuildFormationState,
    GuildLogisticsState,
    GuildOperationsState,
    OracleState,
    Point,
    ToggleState,
    UiState,
)
from .errors import SemanticGateClosed, SemanticTargetNotActionable, SemanticInputBlocked
from .input_outcome import input_result_scope


class GuildOracle:
    """Guild operations sharing the oracle frame and input boundary."""

    def _guild_operation_node_point_visible(self, node):
        return bool(node.active_in_hierarchy and node.active_and_enabled
                    and node.interactable and node.raycast_top is not False
                    and node.point is not None and node.bounds is not None
                    and node.bounds.contains(node.point)
                    and 0 <= round(node.point.x) < self.fingerprint.width
                    and 0 <= round(node.point.y) < self.fingerprint.height)

    def guild_operation_visible_nodes(self):
        state = self.guild_operations_state()
        nodes = (replace(node, point=Point((node.bounds.left + node.bounds.right) / 2,
                                           (node.bounds.top + node.bounds.bottom) / 2))
                 for node in state.active_nodes if node.bounds is not None)
        return tuple(sorted((node for node in nodes if self._guild_operation_node_point_visible(node)),
                            key=lambda node: (node.bounds.top, node.bounds.left, node.path)))

    def _guild_operation_scroll_nodes(self):
        state = self.read_state()
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('guild scroll snapshots are not coherent')
        if not (self._guild_page_visible_from_states(state, ui)
                and self._guild_selected_toggle(ui, 'battle')):
            raise SemanticGateClosed('guild scroll page identity is absent')
        semantic_id = 'guild/operations/scroll'
        blockers = self._blocking_rules(state, semantic_id)
        if blockers:
            raise SemanticInputBlocked(semantic_id, state.generation,
                                       [rule.blocker_id for rule in blockers])
        nodes = tuple(node for node in state.buttons
                      if 'GuildEventPage(Clone)/missionlist/path/' in node.path
                      and re.fullmatch(r'[0-9]+-[0-9]+', str(node.name))
                      and node.path.endswith('/' + str(node.name))
                      and node.active_in_hierarchy and node.active_and_enabled)
        if len({node.path for node in nodes}) != len(nodes):
            raise SemanticGateClosed('guild scroll node identity is ambiguous')
        nav_right = max(t.bounds.right for t in ui.toggles
                        if '/scroll_rect/tagRoot/' in t.path
                        and t.active_in_hierarchy and t.active_and_enabled
                        and t.bounds is not None)
        anchors = []
        for node in nodes:
            if node.bounds is None or node.bounds.left < nav_right:
                continue
            # Mission Buttons export a left-edge point. After scrolling that
            # point may lie beneath the navbar while their actual Rect remains
            # visible. Use its observed center, never clamp an offscreen point.
            point = Point((node.bounds.left + node.bounds.right) / 2,
                          (node.bounds.top + node.bounds.bottom) / 2)
            for point in (point, node.point):
                anchor = replace(node, point=point)
                if (self._guild_operation_node_point_visible(anchor)
                        and point.x > nav_right):
                    anchors.append(anchor)
                    break
        return state, tuple(anchors)

    def _guild_operation_scroll_plan(self, forward):
        state, nodes = self._guild_operation_scroll_nodes()
        # Both endpoints come from actual mission controls on the reviewed
        # missionlist ScrollRect. No old detection rectangle or clamping.
        pairs = [(left, right) for left in nodes for right in nodes
                 if left.point.x < right.point.x
                 and round(left.point.y) == round(right.point.y)
                 and left.path.rsplit('/', 1)[0] == right.path.rsplit('/', 1)[0]]
        if not pairs:
            raise SemanticTargetNotActionable('guild/operations/scroll', state.generation)
        left, right = max(pairs, key=lambda pair: pair[1].point.x - pair[0].point.x)
        first, last = (right, left) if forward else (left, right)
        return state, nodes, first, last

    def swipe_guild_operations(self, forward=True, *, postcondition_oracle=None):
        if self._swipe is None:
            raise SemanticGateClosed('guild scroll input backend is absent')
        state, nodes, first, last = self._retry_transition_read(
            lambda: self._guild_operation_scroll_plan(forward))
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed('game activity changed before guild scroll')
        start = (round(first.point.x), round(first.point.y))
        end = (round(last.point.x), round(last.point.y))
        self._swipe(*start, *end, 450)
        after_oracle = postcondition_oracle if postcondition_oracle is not None else self
        before = {node.path: node.point.x for node in nodes}
        deadline = self._monotonic() + 5.0
        while self._monotonic() < deadline:
            with input_result_scope():
                after_oracle._sleep(.2)
                after, moved = after_oracle._retry_transition_read(
                    after_oracle._guild_operation_scroll_nodes)
            if after.generation > state.generation and any(
                    node.path in before
                    and (node.point.x - before[node.path]) * (-1 if forward else 1) > 1
                    for node in moved):
                return dict(semantic_id='guild/operations/scroll',
                            pre_generation=state.generation, post_generation=after.generation,
                            start=start, end=end, start_path=first.path, end_path=last.path)
        # Do not let the native five-attempt loop repeat an ineffective input.
        raise SemanticTargetNotActionable('guild/operations/scroll', state.generation)

    @staticmethod
    def _guild_page_visible_from_states(
        button_state: OracleState,
        ui_state: UiState,
        *,
        require_back_raycast: bool = True,
    ) -> bool:
        back = tuple(
            button
            for button in button_state.buttons
            if button.name == "back"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/back"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and (not require_back_raycast or button.raycast_top is True)
            and button.bounds is not None
            and button.point is not None
            and button.bounds.contains(button.point)
        )
        nav_root = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/left_length/frame/"
            "scroll_rect/tagRoot/"
        )
        nav = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.path.startswith(nav_root)
            and toggle.path.count("/") == nav_root.count("/")
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
        )
        member_names = {"main", "member", "office", "technology", "battle"}
        known_names = member_names | {"apply"}
        selected = tuple(toggle for toggle in nav if toggle.checked)
        # Only the required tabs and current selection prove page ownership.
        # Inactive templates and details of unselected optional tabs do not.
        page_nav = tuple(
            toggle for toggle in nav if toggle.name in member_names or toggle.checked
        )
        names = {toggle.name for toggle in page_nav}
        return bool(
            len(back) == 1
            and member_names <= names
            and len(selected) == 1
            and selected[0].name in known_names
            and len(names) == len(page_nav)
            and all(
                toggle.path == nav_root + toggle.name
                and toggle.interactable
                and toggle.bounds is not None
                and toggle.point is not None
                and toggle.bounds.contains(toggle.point)
                for toggle in page_nav
            )
        )

    def guild_page_visible(self) -> bool:
        return self._guild_page_identity(require_back_raycast=True)

    def guild_page_mounted(self) -> bool:
        """Read page ownership for passive probes, without granting input."""
        return self._guild_page_identity(require_back_raycast=False)

    def _guild_page_identity(self, *, require_back_raycast: bool) -> bool:
        button_state = self.read_state()
        if not any(
            button.active_in_hierarchy and button.active_and_enabled
            for button in self._matches(button_state, "guild/page/back")
        ):
            # The same page sweep serves unrelated tasks. Read Guild's
            # optional toggles only after its mapped button owner is present.
            return False
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild page snapshots are not coherent")
        return self._guild_page_visible_from_states(
            button_state, ui_state, require_back_raycast=require_back_raycast
        )

    def guild_report_count(self) -> int:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild report snapshots are not coherent")
        roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildEventReportUI(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildEventReportUI(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        counts = tuple(
            text.text
            for text in ui_state.texts
            if text.path.endswith("GuildEventReportUI(Clone)/frame/cnt")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
        )
        if len(roots) != 1 or len(counts) != 1:
            raise SemanticGateClosed("guild report identity is absent or ambiguous")
        match = re.fullmatch(r"([0-9]+)/20", counts[0])
        if match is None:
            raise SemanticGateClosed("guild report count is malformed")
        return int(match.group(1))

    def _guild_nav_delegated_raycast_proven(
        self,
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        matches: Tuple[ToggleState, ...],
    ) -> bool:
        if not semantic_id.startswith("guild/nav/") or len(matches) != 1:
            return False
        if not self._guild_page_visible_from_states(button_state, ui_state):
            return False
        toggle = matches[0]
        if not (
            toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.interactable
            and toggle.raycast_top is None
            and toggle.point is not None
            and toggle.bounds is not None
            and toggle.bounds.contains(toggle.point)
        ):
            return False
        sprites = {
            "guild/nav/lobby": ("toggle_souye_sel", "toggle_souye_unsel"),
            "guild/nav/member": (
                "toggle_chengyuan_sel",
                "toggle_chengyuan_unsel",
            ),
            "guild/nav/logistics": ("toggle_office_sel", "toggle_office_unsel"),
            "guild/nav/technology": ("toggle_tech_sel", "toggle_tech_unsel"),
            "guild/nav/operations": ("toggle_battle_sel", "toggle_battle_unsel"),
        }
        expected = sprites[semantic_id][0 if toggle.checked else 1]
        images = tuple(
            image
            for image in ui_state.images
            if image.name == "Image"
            and image.path.startswith(toggle.path + "/")
            and image.sprite == expected
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
            and toggle.bounds.contains(
                Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                )
            )
        )
        return len(images) == 1

    @staticmethod
    def _guild_selected_toggle(
        ui_state: UiState,
        name: str,
    ) -> bool:
        matches = tuple(
            toggle
            for toggle in ui_state.toggles
            if toggle.name == name
            and toggle.path.endswith(
                "blur_panel/adapt/left_length/frame/scroll_rect/tagRoot/" + name
            )
            and toggle.active_in_hierarchy
            and toggle.active_and_enabled
            and toggle.checked
        )
        return len(matches) == 1

    def _guild_delegated_button_proven(
        self,
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        target: ButtonState,
    ) -> bool:
        contracts = {
            "guild/lobby/report": ("main", "text_report2"),
            "guild/logistics/supply": ("office", "get_btn"),
            "guild/logistics/mission": ("office", "accept_btn"),
            "guild/operations/formation": ("battle", "BUTTEN_2"),
            "guild/operations/report": ("battle", "BUTTEN_"),
            # Native ShowDesc sets this exact panel's sprite from GetIcon().
            # It varies with the mission (the current12-1 uses4_4).
            "guild/operations/dispatch/open": ("battle", None),
        }
        contract = contracts.get(semantic_id)
        if contract is None:
            return False
        selected_name, sprite = contract
        if not (
            self._guild_page_visible_from_states(button_state, ui_state)
            and self._guild_selected_toggle(ui_state, selected_name)
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and (target.raycast_top is None or
                 (semantic_id == 'guild/operations/dispatch/open'
                  and target.raycast_top is True))
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and (bool(image.sprite) if sprite is None else image.sprite == sprite)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(target.point)
        )
        return len(images) == 1

    @staticmethod
    def _guild_dispatch_detail_control_proven(
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        target: ButtonState,
    ) -> bool:
        sprites = {
            "guild/dispatch-detail/close": "close",
            "guild/dispatch-detail/formation": "BUTTEN",
        }
        sprite = sprites.get(semantic_id)
        if sprite is None:
            return False
        roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildMissionInfoPage(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildMissionInfoPage(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if not (
            len(roots) == 1
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
            and image.bounds.contains(target.point)
        )
        return len(images) == 1

    @staticmethod
    def _guild_report_control_proven(
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        target: ButtonState,
    ) -> bool:
        sprites = {
            "guild/report/close": "close",
            "guild/report/claim-all": "btn_di",
        }
        sprite = sprites.get(semantic_id)
        roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildEventReportUI(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildEventReportUI(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if sprite is None or not (
            len(roots) == 1
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        return len(images) == 1

    @staticmethod
    def _guild_formation_control_proven(
        button_state: OracleState,
        ui_state: UiState,
        semantic_id: str,
        target: ButtonState,
    ) -> bool:
        sprites = {
            "guild/formation/close": "close",
            "guild/formation/recommend": "btn_rec",
            "guild/formation/go": "btn",
        }
        sprite = sprites.get(semantic_id)
        roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildMissionFormationPage(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildMissionFormationPage(Clone)"
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
        )
        if sprite is None or not (
            len(roots) == 1
            and target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.point is not None
            and target.bounds is not None
            and target.bounds.contains(target.point)
        ):
            return False
        images = tuple(
            image
            for image in ui_state.images
            if image.path == target.path
            and image.sprite == sprite
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        return len(images) == 1

    def guild_formation_state(self) -> GuildFormationState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild formation snapshots are not coherent")
        root = "GuildMissionFormationPage(Clone)/frame/"
        page_roots = tuple(
            button
            for button in button_state.buttons
            if button.name == "GuildMissionFormationPage(Clone)"
            and button.path.endswith(
                "OverlayCamera/Overlay/UIMain/GuildMissionFormationPage(Clone)"
            )
        )
        if len(page_roots) != 1:
            raise SemanticGateClosed("guild formation page identity is absent")

        def numeric(suffix: str) -> int:
            values = tuple(
                text.text
                for text in ui_state.texts
                if text.path.endswith(root + suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(values) != 1:
                raise SemanticGateClosed("guild formation value is ambiguous")
            numbers = re.findall(r"-?[0-9]+", values[0])
            if len(numbers) != 1:
                raise SemanticGateClosed("guild formation value is malformed")
            return int(numbers[0])

        empty = tuple(
            image
            for image in ui_state.images
            if re.search(r"/frame/single/[1-4]/Image$", image.path)
            and re.fullmatch(r"[1-4]_2", image.sprite)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed('guild formation Image snapshot is incomplete')
        if len(empty) > 4:
            raise SemanticGateClosed("guild formation empty-slot count is invalid")
        doing = tuple(image for image in ui_state.images
            if image.path == page_roots[0].path + '/frame/bottom/doingBtn'
            and image.active_in_hierarchy and image.active_and_enabled)
        if len(doing) > 1 or any(image.truncated or image.sprite != 'doing' for image in doing):
            raise SemanticGateClosed('guild formation progress identity is ambiguous')
        if doing and any(b.active_in_hierarchy and b.active_and_enabled
                for b in self._matches(button_state, 'guild/formation/go')):
            raise SemanticGateClosed('guild formation dispatch and progress states conflict')
        return GuildFormationState(
            generation=max(button_state.generation, ui_state.generation),
            effect=numeric("bottom/effect/Text"),
            score_addition=numeric("bottom/score_addition/Text"),
            effect_addition=numeric("bottom/effect_addition/Text"),
            empty_slots=len(empty),
            in_progress=bool(doing),
        )

    def guild_dispatch_in_progress_generation(self):
        """Observe native dispatch progress on Formation or its returned Detail."""
        state = self.read_state()
        if any(b.name == 'GuildMissionFormationPage(Clone)'
               and b.active_in_hierarchy and b.active_and_enabled for b in state.buttons):
            formation = self.guild_formation_state()
            return formation.generation if formation.in_progress else None
        roots = tuple(b for b in state.buttons
                      if b.name == 'GuildMissionInfoPage(Clone)'
                      and b.path == 'OverlayCamera/Overlay/UIMain/GuildMissionInfoPage(Clone)'
                      and b.active_in_hierarchy and b.active_and_enabled)
        if not roots:
            return None
        if len(roots) != 1:
            raise SemanticGateClosed('guild dispatch progress page is ambiguous')
        ui = self.read_ui_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('guild dispatch progress snapshots are not coherent')
        close = self._matches(state, 'guild/dispatch-detail/close')
        if (len(close) != 1 or not self._guild_dispatch_detail_control_proven(
                state, ui, 'guild/dispatch-detail/close', close[0])
                or self._blocking_rules(state, 'guild/dispatch-detail/close')):
            raise SemanticGateClosed('guild dispatch progress page is obscured or incomplete')
        doing = tuple(i for i in ui.images
                      if i.path == roots[0].path + '/bottom/doing_btn'
                      and i.active_in_hierarchy and i.active_and_enabled)
        if len(doing) > 1 or any(i.truncated or not i.sprite for i in doing):
            raise SemanticGateClosed('guild dispatch progress graphic is ambiguous')
        if ui.image_truncated or ui.method_mask & 0x8 == 0:
            raise SemanticGateClosed('guild dispatch progress Image snapshot is incomplete')
        if not doing:
            return None
        if any(b.active_in_hierarchy and b.active_and_enabled
               for b in self._matches(state, 'guild/dispatch-detail/formation')):
            raise SemanticGateClosed('guild dispatch preparation and progress states conflict')
        return max(state.generation, ui.generation)

    def _guild_formation_footer(self, button_state, ui_state):
        """Read native fleet Toggle identities; choose nothing and submit no input."""
        from .errors import SemanticGuildFormationUnavailable
        if not button_state.generation <= ui_state.generation <= button_state.generation + 2:
            raise SemanticGateClosed('guild formation footer snapshots are not coherent')
        if ui_state.method_mask & 0x9 != 0x9 or ui_state.image_truncated:
            raise SemanticGateClosed('guild formation footer snapshot is incomplete')
        roots = tuple(b for b in button_state.buttons
            if b.name == 'GuildMissionFormationPage(Clone)'
            and b.path.endswith('OverlayCamera/Overlay/UIMain/GuildMissionFormationPage(Clone)')
            and b.active_in_hierarchy and b.active_and_enabled and b.bounds is not None)
        if not roots:
            raise SemanticGuildFormationUnavailable(ui_state.generation, 'fleet footer page is unavailable')
        if len(roots) != 1:
            raise SemanticGateClosed('guild formation footer page is ambiguous')
        prefix = roots[0].path + '/frame/single/dot/'
        toggles = tuple(t for t in ui_state.toggles if t.path.startswith(prefix)
            and re.fullmatch(r'(?:[1-9][0-9]*|add)', t.path[len(prefix):])
            and t.name == t.path[len(prefix):] and t.active_in_hierarchy and t.active_and_enabled)
        if not toggles:
            raise SemanticGuildFormationUnavailable(ui_state.generation, 'fleet footer controls are unavailable')
        if len({t.path for t in toggles}) != len(toggles) or sum(t.checked for t in toggles) != 1:
            raise SemanticGateClosed('guild formation fleet selection is ambiguous')
        for toggle in toggles:
            if toggle.bounds is None or toggle.point is None or not toggle.bounds.contains(toggle.point):
                raise SemanticGateClosed('guild formation fleet geometry is invalid')
        footer = tuple(sorted(toggles, key=lambda t: (t.bounds.left, t.bounds.right)))
        target = footer[-1]
        # Only the control selected by native ALAS needs a reviewed input
        # sprite. Cosmetic changes on another fleet cannot deny this action.
        images = tuple(i for i in ui_state.images if i.path == target.path
            and i.active_in_hierarchy and i.active_and_enabled and not i.truncated)
        if len(images) > 1:
            raise SemanticGateClosed('guild formation fleet image is ambiguous')
        if len(images) != 1 or images[0].sprite != ('dot5' if target.name == 'add' else 'dot1'):
            raise SemanticGuildFormationUnavailable(ui_state.generation, 'fleet footer sprite is unsupported')
        return ui_state.generation, footer

    def guild_formation_footer(self):
        return self._guild_formation_footer(self.read_state(), self.read_ui_state())

    def _guild_formation_fleet_control_proven(self, button_state, ui_state, semantic_id, matches):
        if not semantic_id.startswith('guild/formation/fleet/'):
            return False
        _, footer = self._guild_formation_footer(button_state, ui_state)
        target = footer[-1]
        return bool(len(matches) == 1 and matches[0].path == target.path
            and semantic_id.rsplit('/', 1)[-1] == target.name
            and target.interactable and target.raycast_top is not False
            and not any(other.bounds.contains(target.point) for other in footer[:-1]))

    @staticmethod
    def _guild_parse_amount(value: str) -> int:
        normalized = re.sub(r"<[^>]+>", "", value).strip().upper()
        match = re.fullmatch(r"([0-9]+)(K)?", normalized)
        if match is None:
            raise SemanticGateClosed("guild amount is malformed")
        amount = int(match.group(1))
        return amount * 1000 if match.group(2) else amount

    def guild_logistics_state(self) -> GuildLogisticsState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild logistics snapshots are not coherent")
        if not (
            self._guild_page_visible_from_states(button_state, ui_state)
            and self._guild_selected_toggle(ui_state, "office")
        ):
            raise SemanticGateClosed("guild logistics page identity is absent")

        def one_text(suffix: str) -> str:
            matches = tuple(
                text.text
                for text in ui_state.texts
                if text.path.endswith(suffix)
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("guild logistics text is absent or ambiguous")
            return matches[0]

        supply_match = re.fullmatch(
            r"([0-9]+)/([0-9]+)",
            one_text("TaskPanel/SupplyPanel/frame/open/Text"),
        )
        mission = self._matches(button_state, "guild/logistics/mission")
        mission_progress = tuple(
            text for text in ui_state.texts
            if text.path.endswith("TaskPanel/open/top/progress")
            and text.active_in_hierarchy and text.active_and_enabled
        )
        mission_current = mission_total = None
        if mission_progress or mission:
            # Weekly mission content can be absent while supply and exchange
            # are mounted. Keep its unknown counters explicit, without denying
            # those independent branches. A claim target still needs progress.
            mission_value = re.sub(
                r"<[^>]+>", "", one_text("TaskPanel/open/top/progress")
            )
            if len(mission_progress) != 1:
                raise SemanticGateClosed("guild logistics text is absent or ambiguous")
            mission_match = re.fullmatch(r"([0-9]+)/([0-9]+)", mission_value)
            if mission_match is None:
                raise SemanticGateClosed("guild logistics progress is malformed")
            mission_current, mission_total = map(int, mission_match.groups())
        if supply_match is None:
            raise SemanticGateClosed("guild logistics progress is malformed")
        remaining_text = one_text("TaskPanel/SubmitPanel/cnt/Text")
        remaining_numbers = re.findall(r"[0-9]+", remaining_text)
        if len(remaining_numbers) != 1:
            raise SemanticGateClosed("guild exchange remaining count is malformed")

        submits = sorted(
            (
                button
                for button in button_state.buttons
                if button.name == "submit"
                and "/TaskPanel/SubmitPanel/list/" in button.path
                and button.active_in_hierarchy
                and button.active_and_enabled
                and button.raycast_top is None
                and button.point is not None
                and button.bounds is not None
                and button.bounds.contains(button.point)
            ),
            key=lambda button: button.bounds.left if button.bounds else -1,
        )
        if len(submits) != 3:
            raise SemanticGateClosed("guild exchange buttons are absent or ambiguous")
        items = []
        for index, submit in enumerate(submits):
            assert submit.bounds is not None
            center_x = (submit.bounds.left + submit.bounds.right) / 2.0
            icon_matches = tuple(
                image
                for image in ui_state.images
                if image.name == "icon"
                and image.path.endswith("/item/icon_bg/icon")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and abs(
                    (image.bounds.left + image.bounds.right) / 2.0 - center_x
                ) < 15.0
            )
            count_matches = tuple(
                text.text
                for text in ui_state.texts
                if text.path.endswith("/item/Text")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and abs((text.bounds.left + text.bounds.right) / 2.0 - center_x) < 25.0
            )
            reward_matches = tuple(
                text.text
                for text in ui_state.texts
                if text.path.endswith("/award/Text")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and abs((text.bounds.left + text.bounds.right) / 2.0 - center_x) < 45.0
            )
            if len(icon_matches) != 1 or len(count_matches) != 1 or len(reward_matches) != 1:
                raise SemanticGateClosed("guild exchange row identity is ambiguous")
            # Native resource-shortage text wraps the owned amount in color
            # tags. Remove display markup before splitting on the quantity
            # separator; a closing tag contains a slash too.
            count_value = re.sub(r"<[^>]+>", "", count_matches[0])
            count = re.fullmatch(r"([^/]+)/([^/]+)", count_value)
            if count is None or not reward_matches[0].isdigit():
                raise SemanticGateClosed("guild exchange row values are malformed")
            items.append(
                GuildExchangeItemState(
                    index=index,
                    icon_sprite=icon_matches[0].sprite,
                    owned=self._guild_parse_amount(count.group(1)),
                    required=self._guild_parse_amount(count.group(2)),
                    contribution=int(reward_matches[0]),
                    button=submit,
                )
            )
        supply_current, supply_total = map(int, supply_match.groups())
        supply = self._matches(button_state, "guild/logistics/supply")
        finish_masks = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("TaskPanel/open/mask_all")
            and image.sprite == "finish_mask1"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        mission_finished = len(finish_masks) == 1
        return GuildLogisticsState(
            generation=max(button_state.generation, ui_state.generation),
            supply_remaining=supply_current,
            supply_total=supply_total,
            supply_claimable=bool(
                len(supply) == 1
                and self._guild_delegated_button_proven(
                    button_state, ui_state, "guild/logistics/supply", supply[0]
                )
            ),
            mission_current=mission_current,
            mission_total=mission_total,
            mission_claimable=bool(
                mission_current is not None
                and mission_total is not None
                and mission_current >= mission_total
                and not mission_finished
                and len(mission) == 1
                and self._guild_delegated_button_proven(
                    button_state, ui_state, "guild/logistics/mission", mission[0]
                )
            ),
            mission_finished=mission_finished,
            exchange_remaining=int(remaining_numbers[0]),
            exchange_items=tuple(items),
        )

    def guild_operations_state(self) -> GuildOperationsState:
        # Live operation admission can cross Button/UI publication boundaries.
        # Re-read the complete view before any input using the existing bounded
        # helper. Immutable screenshot leases remain a single attempt, and the
        # chosen node is still rechecked for actionability immediately at input.
        return self._retry_transition_read(self._guild_operations_state_once)

    def _guild_operations_state_once(self) -> GuildOperationsState:
        button_state = self.read_state()
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("guild operations snapshots are not coherent")
        if not (
            self._guild_page_visible_from_states(button_state, ui_state)
            and self._guild_selected_toggle(ui_state, "battle")
        ):
            raise SemanticGateClosed("guild operations page identity is absent")
        if any(image.path == 'OverlayCamera/Overlay/UIOverlay/Loading(Clone)'
               and image.active_in_hierarchy and image.active_and_enabled
               for image in ui_state.images):
            # The nav toggle can settle before its asynchronously loaded page.
            # Empty observations during that exact loading layer are not an
            # inactive operation. Native admission already retries this error.
            raise SemanticGateClosed("guild operations page identity is absent")
        root = "GuildEventPage(Clone)/missionlist/path/"
        candidates = []
        for button in button_state.buttons:
            if (root not in button.path or button.bounds is None
                    or not button.active_in_hierarchy or not button.active_and_enabled):
                continue
            tips = tuple(
                image
                for image in ui_state.images
                if image.path == button.path + "/tip"
                and image.sprite == "exclamation_mark"
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
            )
            if len(tips) == 1:
                candidates.append(button)
            elif len(tips) > 1:
                raise SemanticGateClosed("guild active operation marker is ambiguous")
        if len({button.path for button in candidates}) != len(candidates):
            raise SemanticGateClosed("guild active operation node is ambiguous")
        boss = tuple(
            button
            for button in button_state.buttons
            if button.name in ("enter", "start")
            and "Guild" in button.path
            and button.bounds is not None
        )
        chain_present = any(root in button.path
                            and re.fullmatch(r'[0-9]+-[0-9]+', button.name)
                            and button.active_in_hierarchy and button.active_and_enabled
                            for button in button_state.buttons)
        # An active chain remains the original exit destination after its
        # last available mission has been dispatched and its tip disappears.
        mode = "boss" if boss else ("active" if candidates or chain_present else "inactive")
        reports = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("GuildEventPage(Clone)/report_btn/tip")
            and image.sprite in ("tip_1920", "tip")
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
        )
        # Several distinct missions can be available at once. Selection
        # belongs to ALAS; only duplicate identities make this read ambiguous.
        active = candidates[0] if len(candidates) == 1 else None
        return GuildOperationsState(
            generation=max(button_state.generation, ui_state.generation),
            mode=mode,
            active_node=active.name if active else None,
            active_node_path=active.path if active else None,
            report_available=len(reports) == 1,
            active_nodes=tuple(candidates),
        )

    def click_guild_exchange_item(
        self,
        index: int,
        expected_icon_sprite: str,
        expected_owned: int,
        expected_required: int,
    ) -> ActionReceipt:
        state = self.guild_logistics_state()
        if index not in range(len(state.exchange_items)):
            raise SemanticGateClosed("guild exchange index is invalid")
        item = state.exchange_items[index]
        if (
            state.exchange_remaining <= 0
            or item.icon_sprite != expected_icon_sprite
            or item.owned != expected_owned
            or item.required != expected_required
            or not item.enough
            or not item.button.interactable
        ):
            raise SemanticGateClosed("guild exchange item changed before input")
        target = item.button
        assert target.bounds is not None
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point) or not (
            0 <= point.x < self.fingerprint.width
            and 0 <= point.y < self.fingerprint.height
        ):
            raise SemanticGateClosed("guild exchange point is invalid")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before guild exchange input")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="guild/logistics/exchange/{0}".format(index),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_guild_active_operation(self, expected_path: str) -> ActionReceipt:
        state = self.guild_operations_state()
        selected = tuple(node for node in state.active_nodes if node.path == expected_path)
        if state.mode != "active" or len(selected) != 1:
            raise SemanticGateClosed("guild active operation node changed")
        button_state = self.read_state()
        matches = tuple(
            button
            for button in button_state.buttons
            if button.path == expected_path
            and button.name == selected[0].name
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.raycast_top is not False
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed("guild active operation node is not actionable")
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        point = Point((target.bounds.left + target.bounds.right) / 2,
                      (target.bounds.top + target.bounds.bottom) / 2)
        x, y = int(round(point.x)), int(round(point.y))
        semantic_id = 'guild/operations/node/' + str(target.name)
        if not (target.bounds.contains(Point(x, y))
                and 0 <= x < self.fingerprint.width and 0 <= y < self.fingerprint.height):
            # Active mission Buttons can remain exported beyond the scrolled
            # viewport. Being inside their own bounds does not make that
            # off-screen point usable by Android input. ALAS owns re-entry.
            raise SemanticTargetNotActionable(semantic_id, button_state.generation)
        blockers = self._blocking_rules(button_state, semantic_id)
        if blockers:
            raise SemanticInputBlocked(semantic_id, button_state.generation,
                                       [rule.blocker_id for rule in blockers])
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before guild operation input")
        self._tap(x, y)
        return ActionReceipt(
            semantic_id="guild/operations/node/" + str(target.name),
            generation=button_state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _guild_dispatch_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None or parts[1:] not in (("取消", "确定"), ("ȡ��", "ȷ��")):
            return False
        ui_state = self._stable_msgbox_ui_state(state)
        formation_roots = tuple(
            button
            for button in state.buttons
            if button.name == "GuildMissionFormationPage(Clone)"
            and button.path.endswith(
                ("UICamera/Canvas/UIOrigin/GuildMissionFormationPage(Clone)",
                 "OverlayCamera/Overlay/UIMain/GuildMissionFormationPage(Clone)")
            )
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        button_sprites = {
            image.sprite
            for image in ui_state.images
            if image.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_1(Clone)"
            )
            or image.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_2(Clone)"
            )
        }
        content = parts[0]
        text_shape = bool(
            content
            and (
                ("派遣" in content and "无法" in content and "确定" in content)
                or ("��ǲ" in content and "�޷�" in content and "ȷ��" in content)
            )
        )
        return bool(
            len(formation_roots) == 1
            and text_shape
            and button_sprites == {"btn_big_blue", "btn_big_grey"}
        )

    def _guild_exchange_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None or parts[1:] != ("取消", "确定"):
            return False
        ui_state = self._stable_msgbox_ui_state(state)
        logistics_roots = tuple(
            button
            for button in state.buttons
            if "/TaskPanel(Adapt)/TaskPanel/SubmitPanel/" in button.path
            and button.name == "submit"
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        button_sprites = {
            image.sprite
            for image in ui_state.images
            if image.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_1(Clone)"
            )
            or image.path.endswith(
                "Msgbox(Clone)/window/button_container/custom_button_2(Clone)"
            )
        }
        prompt = re.fullmatch(
            r"即将提交(.+?)([1-9][0-9]*)个\(目前拥有([1-9][0-9]*)个\)，"
            r"为大舰队提供后勤补给，是否确定？",
            parts[0],
        )
        return bool(
            len(logistics_roots) == 3
            and prompt is not None
            and int(prompt.group(3)) >= int(prompt.group(2))
            and button_sprites == {"btn_big_blue", "btn_big_grey"}
        )
