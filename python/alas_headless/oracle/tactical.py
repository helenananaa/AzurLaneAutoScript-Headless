"""Tactical for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, List, Mapping, Optional, Tuple
from .contracts import (
    ActionReceipt,
    Bounds,
    ButtonState,
    OracleState,
    Point,
    TacticalBookState,
    TacticalCandidateShipState,
    TacticalSkillState,
    TacticalSlotState,
    TacticalSlotStatus,
    UiState,
)
from .errors import SemanticGateClosed, SemanticInputBlocked, SemanticTargetNotActionable


class TacticalOracle:
    """Tactical operations sharing the oracle frame and input boundary."""

    def _tactical_completion_prompt_matches(self, state: OracleState) -> bool:
        choices = tuple(b for b in state.buttons
                        if b.active_in_hierarchy and b.active_and_enabled
                        and '/Msgbox(Clone)/window/button_container/' in b.path)
        suffix = 'Msgbox(Clone)/window/button_container/custom_button_1(Clone)'
        if len(choices) != 1 or not choices[0].path.endswith(suffix):
            return False
        ui = self._stable_msgbox_ui_state(state)
        def texts(suffix):
            return tuple(t for t in ui.texts if t.path.endswith(suffix)
                         and t.active_in_hierarchy and t.active_and_enabled)
        content = texts('Msgbox(Clone)/window/msg_panel/content')
        label = texts(suffix + '/pic')
        if len(content) != 1 or len(label) != 1:
            return False
        if any(t.truncated or t.bounds is None for t in (*content, *label)):
            return False
        # The original Tactical handler owns this one-button max-level notice.
        # Its underlying student page distinguishes it from unrelated notices.
        students = any(t.active_in_hierarchy and t.active_and_enabled
                       and '/NewNavalTacticsStudentsPage(Clone)/' in t.path
                       for t in ui.texts)
        plain = re.sub(r'<[^>]*>', '', content[0].text).strip()
        return bool(students and ''.join(label[0].text.split()) == '确定'
                    and re.fullmatch(
                        r'「[^」\n]+」学习完成，「[^」\n]+」技能获得[1-9][0-9]*点经验'
                        r'[(（]技能等级提升:[1-9]→10[)）]！', plain))

    def click_tactical_completion_ack(self) -> ActionReceipt:
        receipt = self.click('tactical/completion/ack')
        for _ in range(16):
            self._sleep(.25)
            after = self.read_state()
            if (after.generation > receipt.generation
                    and not any(b.active_in_hierarchy and '/Msgbox(Clone)/' in b.path
                                for b in after.buttons)):
                return receipt
        raise SemanticGateClosed('tactical completion prompt did not close after input')

    def click_tactical_empty_slot(self, slot: int) -> ActionReceipt:
        """Click one visually ordered empty tactical slot after exact revalidation."""

        if slot not in range(1, 5):
            raise ValueError("tactical slot must be 1 through 4")
        state = self.read_state()
        targets = self._tactical_empty_slot_targets(state)
        try:
            target = targets[slot]
        except KeyError as exc:
            raise SemanticGateClosed("tactical slot is not empty") from exc
        if self._blocking_rules(state, "tactical/slot/{0}".format(slot)):
            raise SemanticGateClosed("tactical slot input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="tactical/slot/{0}".format(slot),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_tactical_first_empty_slot(self) -> ActionReceipt:
        """Click the leftmost current tactical empty slot."""

        semantic_id = 'tactical/slot/first-empty'
        def read_target():
            state = self.read_state()
            blockers = self._blocking_rules(state, semantic_id)
            if blockers:
                raise SemanticInputBlocked(semantic_id, state.generation,
                                           (rule.blocker_id for rule in blockers))
            target = self._tactical_first_empty_slot_target(state)
            if target is None:
                raise SemanticGateClosed("tactical class has no empty slot")
            if (not target.actionable
                    or not (0 <= target.point.x < self.fingerprint.width
                            and 0 <= target.point.y < self.fingerprint.height)):
                raise SemanticTargetNotActionable(semantic_id, state.generation)
            return state, target
        # A positive empty control may still be mounting in ALAS's frozen
        # screenshot. Re-observe only before input using the existing bounded
        # transition helper; never retry the tap or its accepted result.
        state, target = self._retry_transition_read(read_target)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        assert target.point is not None and target.bounds is not None
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        # Return the accepted input immediately. The adapter retains it while
        # ALAS' screenshot loop observes the select-Dock destination.
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    @staticmethod
    def _tactical_first_empty_slot_target(state: OracleState) -> Optional[ButtonState]:
        """Select a positive empty control without inventing a numbered slot."""
        prefix = 'NewNavalTacticsUI(Clone)/adpter/NewNavalTacticsStudentsPage(Clone)/'
        targets = tuple(button for button in state.buttons
                        if button.name in ('add', 'add(Clone)')
                        and button.path.endswith(prefix + button.name)
                        and button.active_in_hierarchy and button.active_and_enabled
                        and button.interactable and button.point is not None
                        and button.bounds is not None and button.bounds.contains(button.point))
        if not targets:
            return None
        left = min(button.point.x for button in targets)
        first = tuple(button for button in targets if button.point.x == left)
        if len(first) != 1:
            raise SemanticGateClosed('tactical first empty slot is ambiguous')
        return first[0]

    def _tactical_empty_slot_targets(
        self, state: UiState
    ) -> Mapping[int, ButtonState]:
        """Return current empty slots keyed by their physical left-to-right index."""

        prefix = "NewNavalTacticsUI(Clone)/adpter/NewNavalTacticsStudentsPage(Clone)/"
        empty = tuple(
            button
            for button in state.buttons
            if button.name in ("add", "add(Clone)")
            and button.path.endswith(prefix + button.name)
            and button.actionable
            and button.point is not None
        )
        occupied = tuple(
            button
            for button in state.buttons
            if re.fullmatch(r"[1-9][0-9]{5,7}", button.name) is not None
            and prefix in button.path
            and button.path.endswith("/" + button.name)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.point is not None
        )
        columns = tuple(sorted((*empty, *occupied), key=lambda button: button.point.x))
        if len(columns) != 4 or len({button.point.x for button in columns}) != 4:
            raise SemanticGateClosed("tactical slot controls are incomplete")
        return {
            index: button
            for index, button in enumerate(columns, start=1)
            if button in empty
        }

    def tactical_empty_slots_ready(self) -> bool:
        """Observe a positive empty control; actual input proves actionability."""

        state = self.read_state()
        try:
            if self._blocking_rules(state, 'tactical/slot/first-empty'):
                return False
            return self._tactical_first_empty_slot_target(state) is not None
        except SemanticGateClosed:
            return False

    def tactical_candidate_ships(self) -> Tuple[TacticalCandidateShipState, ...]:
        """Read visible tactical Dock candidates in ALAS grid order."""

        button_state = self.read_state()
        back = self._unique(button_state, "tactical/dock/back")
        confirm = self._unique(button_state, "tactical/dock/confirm")
        if not back.active_and_enabled or not confirm.active_and_enabled:
            raise SemanticGateClosed("tactical Dock identity is not proven")
        prefix = "DockyardUI(Clone)/main/ship_container/ships/"
        buttons = tuple(
            button
            for button in button_state.buttons
            if re.fullmatch(r"[1-9][0-9]{5,7}", button.name) is not None
            and button.path.endswith(prefix + button.name)
            and button.bounds is not None
            and button.bounds.right > 0
            and button.bounds.bottom > 0
            and button.bounds.left < self.fingerprint.width
            and button.bounds.top < 500
        )
        if not buttons or len({button.name for button in buttons}) != len(buttons):
            raise SemanticGateClosed("tactical Dock candidates are absent or ambiguous")
        buttons = tuple(
            sorted(
                buttons,
                key=lambda button: (
                    round(button.bounds.top / 50.0),
                    button.bounds.left,
                ),
            )
        )
        ui_state = self.read_text_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical Dock snapshots are not coherent")

        candidates = []
        for position, button in enumerate(buttons):
            root = button.path + "/content/"

            def exact_text(suffix: str) -> str:
                matches = tuple(
                    text
                    for text in ui_state.texts
                    if text.path == root + suffix
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                    and text.bounds is not None
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "tactical Dock text is absent or ambiguous: " + suffix
                    )
                return re.sub(r"<[^>]*>", "", matches[0].text).strip()

            name = exact_text("info/name_mask/name")
            level_text = exact_text("dockyard/lv/Text")
            if not name or re.fullmatch(r"[1-9][0-9]{0,2}", level_text) is None:
                raise SemanticGateClosed("tactical Dock candidate is malformed")
            candidates.append(
                TacticalCandidateShipState(
                    position=position,
                    ship_id=int(button.name),
                    ship_name=name,
                    level=int(level_text),
                    button=button,
                )
            )
        return tuple(candidates)

    def click_tactical_ship(self, ship_id: int) -> ActionReceipt:
        candidates = self.tactical_candidate_ships()
        matches = tuple(
            candidate for candidate in candidates if candidate.ship_id == ship_id
        )
        if len(matches) != 1:
            raise SemanticGateClosed("tactical Dock ship identity changed")
        target = matches[0].button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("tactical Dock ship is not safely actionable")
        state = self.read_state()
        current = tuple(
            button for button in state.buttons if button.path == target.path
        )
        if len(current) != 1 or not current[0].actionable:
            raise SemanticGateClosed("tactical Dock ship changed before input")
        target = current[0]
        assert target.point is not None and target.bounds is not None
        if self._blocking_rules(state, "tactical/dock/ship"):
            raise SemanticGateClosed("tactical Dock ship input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="tactical/dock/ship/{0}".format(ship_id),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def tactical_skills(self) -> Tuple[TacticalSkillState, ...]:
        """Read visible skill rows in the tactical skill-selection dialog."""

        button_state = self.read_state()
        confirm = self._unique(button_state, "tactical/skill/confirm")
        if not confirm.active_and_enabled:
            raise SemanticGateClosed("tactical skill dialog identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical skill snapshots are not coherent")
        rows_path_fragment = (
            "NewNavalTacticsSkillsPage(Clone)/frame/skill_container/content/"
        )
        rows = tuple(
            image
            for image in ui_state.images
            if image.name in ("skill", "skill(Clone)")
            and image.path.endswith(rows_path_fragment + image.name)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and not image.truncated
            and image.bounds is not None
            and image.bounds.bottom > 0
            and image.bounds.top < self.fingerprint.height
        )
        rows = tuple(sorted(rows, key=lambda image: image.bounds.top))
        if not rows or len(rows) > 4:
            raise SemanticGateClosed("tactical skill rows are absent or ambiguous")

        result = []
        for position, row in enumerate(rows):
            assert row.bounds is not None

            def text_with_suffix(suffix: str) -> str:
                matches = tuple(
                    text
                    for text in ui_state.texts
                    if rows_path_fragment in text.path
                    and text.path.endswith(suffix)
                    and text.active_in_hierarchy
                    and text.active_and_enabled
                    and not text.truncated
                    and text.bounds is not None
                    and row.bounds.contains(
                        Point(
                            (text.bounds.left + text.bounds.right) / 2.0,
                            (text.bounds.top + text.bounds.bottom) / 2.0,
                        )
                    )
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "tactical skill text is absent or ambiguous: " + suffix
                    )
                return re.sub(r"<[^>]*>", "", matches[0].text).strip()

            name = text_with_suffix("/name/Text/subText")
            level = text_with_suffix("/name/level")
            next_value = text_with_suffix("/next")
            if not name or re.fullmatch(r"Lv\.[1-9][0-9]?", level) is None:
                raise SemanticGateClosed("tactical skill row is malformed")
            result.append(
                TacticalSkillState(
                    position=position,
                    name=name,
                    level_text=next_value,
                    max_level=next_value.upper() == "MAX",
                    button=ButtonState(
                        name=row.name,
                        path=row.path,
                        active_in_hierarchy=row.active_in_hierarchy,
                        active_and_enabled=row.active_and_enabled,
                        interactable=True,
                        raycast_top=row.raycast_top,
                        point=Point(
                            (row.bounds.left + row.bounds.right) / 2.0,
                            (row.bounds.top + row.bounds.bottom) / 2.0,
                        ),
                        bounds=row.bounds,
                        raw=row.raw,
                    ),
                )
            )
        return tuple(result)

    def click_tactical_skill(self, position: int) -> ActionReceipt:
        skills = self.tactical_skills()
        matches = tuple(skill for skill in skills if skill.position == position)
        if len(matches) != 1 or matches[0].max_level:
            raise SemanticGateClosed("tactical skill is absent or already maxed")
        target = matches[0].button
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("tactical skill is not safely actionable")
        state = self.read_state()
        if self._blocking_rules(state, "tactical/skill/item"):
            raise SemanticGateClosed("tactical skill input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="tactical/skill/{0}".format(position),
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def tactical_books(self) -> Tuple[TacticalBookState, ...]:
        """Read visible tactical books in the same order as ALAS BOOKS_GRID."""

        # Native book selection uses a live read outside an ALAS screenshot
        # lease. Sequential Button/Image projections can straddle publication;
        # re-read the complete view with the existing bounded read-only helper.
        # Leased frames still get one immutable attempt and every check below
        # must pass before a book can be clicked.
        return self._retry_transition_read(self._tactical_books_once)

    def _tactical_books_once(self) -> Tuple[TacticalBookState, ...]:

        button_state = self.read_state()
        start = self._unique(button_state, "tactical/book/start")
        cancel = self._unique(button_state, "tactical/book/cancel")
        if not start.active_and_enabled or not cancel.active_and_enabled:
            raise SemanticGateClosed("tactical book dialog identity is not proven")
        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical book snapshots are not coherent")

        root = "NewNavalTacticsLessonPage(Clone)/items/scorll/content/"
        items = tuple(
            image
            for image in ui_state.images
            if image.name in ("item", "item(Clone)")
            and image.path.endswith(root + image.name)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and image.raycast_target
            and image.raycast_top is True
            and not image.truncated
            and image.bounds is not None
            and image.bounds.right > 0
            and image.bounds.bottom > 0
            and image.bounds.left < self.fingerprint.width
            and image.bounds.top < self.fingerprint.height
        )
        items = tuple(
            sorted(
                items,
                key=lambda image: (
                    round(image.bounds.top / 50.0),
                    image.bounds.left,
                ),
            )
        )
        if not items or len(items) > 12:
            raise SemanticGateClosed("tactical book items are absent or ambiguous")

        def center(bounds: Bounds) -> Point:
            return Point(
                (bounds.left + bounds.right) / 2.0,
                (bounds.top + bounds.bottom) / 2.0,
            )

        books = []
        seen_ids = set()
        for position, item in enumerate(items):
            assert item.bounds is not None
            icon_matches = tuple(
                image
                for image in ui_state.images
                if image.name == "icon"
                and image.path.startswith(item.path + "/icon_bg/")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and item.bounds.contains(center(image.bounds))
                and re.fullmatch(r"160[012][1-4]", image.sprite) is not None
            )
            count_matches = tuple(
                text
                for text in ui_state.texts
                if text.name == "count"
                and text.path.startswith(item.path + "/icon_bg/")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and item.bounds.contains(center(text.bounds))
                and re.fullmatch(r"[0-9]+", text.text.strip()) is not None
            )
            addition_matches = tuple(
                text
                for text in ui_state.texts
                if text.name == "addition"
                and text.path.startswith(item.path + "/")
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and item.bounds.left <= center(text.bounds).x <= item.bounds.right
                and item.bounds.top - 10 <= center(text.bounds).y <= item.bounds.bottom
            )
            if (
                len(icon_matches) != 1
                or len(count_matches) != 1
                or len(addition_matches) != 1
            ):
                raise SemanticGateClosed(
                    "tactical book identity text is absent or ambiguous"
                )
            item_id = icon_matches[0].sprite
            if item_id in seen_ids:
                raise SemanticGateClosed("tactical book item ID is duplicated")
            seen_ids.add(item_id)
            addition = addition_matches[0].text.strip()
            if addition not in ("", "EXP150%", "EXP200%"):
                raise SemanticGateClosed("tactical book EXP bonus is malformed")
            selected = any(
                image.name == "selected"
                and image.path.startswith(item.path + "/selected")
                and image.active_in_hierarchy
                and image.active_and_enabled
                and not image.truncated
                and image.bounds is not None
                and item.bounds.contains(center(image.bounds))
                for image in ui_state.images
            )
            books.append(
                TacticalBookState(
                    position=position,
                    item_id=item_id,
                    genre=int(item_id[-2]) + 1,
                    tier=int(item_id[-1]),
                    exp_bonus=bool(addition),
                    count=int(count_matches[0].text.strip()),
                    selected=selected,
                    image=item,
                )
            )
        if sum(book.selected for book in books) != 1:
            raise SemanticGateClosed("tactical selected book is absent or ambiguous")
        return tuple(books)

    def tactical_book_skill_progress(self) -> str:
        """Return the selected skill's pre-book progress as ``current/total``."""

        button_state = self.read_state()
        start = self._unique(button_state, "tactical/book/start")
        cancel = self._unique(button_state, "tactical/book/cancel")
        if not start.active_and_enabled or not cancel.active_and_enabled:
            raise SemanticGateClosed("tactical book progress page identity is not proven")
        text_state = self.read_text_state()
        if (
            text_state.generation < button_state.generation
            or text_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical book progress snapshots are not coherent")
        root = "NewNavalTacticsLessonPage(Clone)/skill/info/next"
        labels = tuple(
            text
            for text in text_state.texts
            if text.path.endswith(root + "/label")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        progress = tuple(
            text
            for text in text_state.texts
            if text.path.endswith(root)
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(labels) != 1 or labels[0].text.strip() != "NEXT:" or len(progress) != 1:
            raise SemanticGateClosed("tactical book progress text is absent or ambiguous")
        match = re.fullmatch(
            r"([0-9]+)\+<color=#A9F548FF>[0-9]+</color>/([0-9]+)",
            progress[0].text.strip(),
        )
        if match is None:
            raise SemanticGateClosed("tactical book progress text is malformed")
        current, total = (int(value) for value in match.groups())
        if total not in (100, 200, 400, 800, 1400, 2200, 3200, 4400, 5800) or not 0 <= current <= total:
            raise SemanticGateClosed("tactical book progress values are invalid")
        return "{0}/{1}".format(current, total)

    def click_tactical_book(self, position: int) -> ActionReceipt:
        books = self.tactical_books()
        matches = tuple(book for book in books if book.position == position)
        if len(matches) != 1 or matches[0].count <= 0:
            raise SemanticGateClosed("tactical book is absent or exhausted")
        target = matches[0].image
        if target.raycast_top is not True or target.bounds is None:
            raise SemanticGateClosed("tactical book is not safely actionable")
        state = self.read_state()
        if self._blocking_rules(state, "tactical/book/item"):
            raise SemanticGateClosed("tactical book input is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed immediately before input")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="tactical/book/{0}".format(position),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def tactical_slots(self) -> Tuple[TacticalSlotState, ...]:
        """Read populated tactical-class slots from typed Unity controls."""

        button_state = self.read_state()
        page = self._unique(button_state, "tactical/page/back")
        if not page.active_in_hierarchy or not page.active_and_enabled:
            raise SemanticGateClosed("tactical page identity is not proven")

        prefix = "NewNavalTacticsUI(Clone)/adpter/NewNavalTacticsStudentsPage(Clone)/"
        raw_ship_buttons = tuple(
            button
            for button in button_state.buttons
            if re.fullmatch(r"[1-9][0-9]{5,7}", button.name) is not None
            and prefix in button.path
            and button.path.endswith("/" + button.name)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.bounds is not None
            and button.bounds.right > 0
            and button.bounds.bottom > 0
            and button.bounds.left < self.fingerprint.width
            and button.bounds.top < self.fingerprint.height
        )
        slot_groups: Dict[Tuple[str, float, float, float, float], List[ButtonState]] = {}
        for button in raw_ship_buttons:
            assert button.bounds is not None
            bounds = button.bounds
            slot_key = (
                button.path.rsplit("/", 1)[0],
                bounds.left,
                bounds.top,
                bounds.right,
                bounds.bottom,
            )
            slot_groups.setdefault(slot_key, []).append(button)
        ship_buttons = []
        for candidates in slot_groups.values():
            # After a course confirmation, the live client can retain the
            # previous ship button on the current physical card while
            # publishing the current identity first.  One ``info(Clone)``
            # root can also host more than one independently positioned card.
            ship_buttons.append(candidates[0])
        if len(ship_buttons) > 4 or len(
            {button.name for button in ship_buttons}
        ) != len(ship_buttons):
            raise SemanticGateClosed("tactical slot identity is ambiguous")
        ship_buttons = tuple(
            sorted(ship_buttons, key=lambda button: button.bounds.left)
        )

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("tactical snapshots are not coherent")

        def text_in_slot(
            button: ButtonState, suffix: str, *, identity_scoped: bool
        ) -> str:
            assert button.bounds is not None
            slot_root = button.path.rsplit("/", 1)[0]
            path_root = button.path if identity_scoped else slot_root
            matches = tuple(
                text
                for text in ui_state.texts
                if text.path == path_root + suffix
                and text.active_in_hierarchy
                and text.active_and_enabled
                and not text.truncated
                and text.bounds is not None
                and button.bounds.left
                <= (text.bounds.left + text.bounds.right) / 2.0
                <= button.bounds.right
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "tactical slot text is absent or ambiguous: " + suffix
                )
            return matches[0].text.strip()

        slots = []
        for slot, button in enumerate(ship_buttons, start=1):
            ship_name = text_in_slot(
                button, "/content/info/name_mask/name", identity_scoped=True
            )
            ship_level_text = text_in_slot(
                button, "/content/dockyard/lv/Text", identity_scoped=True
            )
            skill_name = text_in_slot(
                button, "/skill/name_Text", identity_scoped=False
            )
            skill_level_text = text_in_slot(
                button, "/skill/level", identity_scoped=False
            )
            progress_text = text_in_slot(
                button, "/skill/next", identity_scoped=False
            )
            timer_text = text_in_slot(
                button, "/timer_Text", identity_scoped=False
            )
            progress = re.fullmatch(r"([0-9]+)/([1-9][0-9]*)", progress_text)
            if (
                not ship_name
                or not skill_name
                or re.fullmatch(r"[1-9][0-9]{0,2}", ship_level_text) is None
                or re.fullmatch(r"[1-9][0-9]?", skill_level_text) is None
                or progress is None
            ):
                raise SemanticGateClosed("tactical slot summary is malformed")
            exp_current, exp_total = map(int, progress.groups())
            if exp_current > exp_total:
                raise SemanticGateClosed("tactical skill progress is inconsistent")
            if timer_text:
                status = TacticalSlotStatus.RUNNING
                remaining_seconds: Optional[int] = self.parse_countdown_seconds(
                    timer_text
                )
            else:
                # On the reviewed page a populated slot retains its cancel
                # control and publishes an empty timer only after completion.
                cancel_buttons = tuple(
                    candidate
                    for candidate in button_state.buttons
                    if candidate.name == "cancel_btn"
                    and candidate.path.startswith(button.path.rsplit("/", 1)[0] + "/")
                    and candidate.active_in_hierarchy
                    and candidate.active_and_enabled
                    and candidate.bounds is not None
                    and button.bounds.left
                    <= (candidate.bounds.left + candidate.bounds.right) / 2.0
                    <= button.bounds.right
                )
                if len(cancel_buttons) != 1:
                    raise SemanticGateClosed(
                        "finished tactical slot marker is absent or ambiguous"
                    )
                status = TacticalSlotStatus.FINISHED
                remaining_seconds = None
            slots.append(
                TacticalSlotState(
                    slot=slot,
                    ship_id=int(button.name),
                    ship_name=ship_name,
                    ship_level=int(ship_level_text),
                    skill_name=skill_name,
                    skill_level=int(skill_level_text),
                    exp_current=exp_current,
                    exp_total=exp_total,
                    status=status,
                    remaining_seconds=remaining_seconds,
                    button=button,
                )
            )
        return tuple(slots)

    def tactical_remaining_seconds(self) -> Tuple[int, ...]:
        return tuple(
            slot.remaining_seconds
            for slot in self.tactical_slots()
            if slot.status == TacticalSlotStatus.RUNNING
            and slot.remaining_seconds is not None
        )

    def _tactical_continue_prompt_text(self, state: OracleState) -> Optional[str]:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return None
        plain, cancel, confirm = parts
        if (
            re.fullmatch(
                r"「[^」]+」学习完成，「[^」]+」技能获得[1-9][0-9]*点经验"
                r"(?:[(（]技能等级提升:[1-9][0-9]?→[1-9][0-9]?[)）]！)?"
                r"是否继续学习该(?:角色)?技能？",
                plain,
            )
            and cancel == "取消"
            and confirm == "确定"
        ):
            return plain
        return None

    def _tactical_course_prompt_matches(self, state: OracleState) -> bool:
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return False
        plain, cancel, confirm = parts
        return bool(
            re.fullmatch(
                r"是否消耗1本「舰艇(?:攻击|防御|辅助)教材T[1-4]」，"
                r"训练「[^」]+」的[^「」]+技能？",
                plain,
            )
            and cancel == "取消"
            and confirm == "确定"
        )

    def _tactical_continue_prompt_matches(self, state: OracleState) -> bool:
        return self._tactical_continue_prompt_text(state) is not None

    def tactical_continue_prompt_text(self) -> Optional[str]:
        state = self.read_state()
        matches = self._matches(state, "tactical/continue/cancel")
        if len(matches) > 1:
            raise SemanticGateClosed("tactical prompt cancel target is ambiguous")
        if (
            not matches
            or not matches[0].actionable
            or self._blocking_rules(state, "tactical/continue/cancel")
        ):
            return None
        return self._tactical_continue_prompt_text(state)
