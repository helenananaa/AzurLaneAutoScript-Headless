"""Opsi mission for the typed ALAS boundary."""

from __future__ import annotations

import math
import re
from typing import Optional, Sequence, Tuple
from .contracts import ActionReceipt, ButtonState, OracleState, Point, UiState
from .errors import SemanticGateClosed


class OpsiMissionOracle:
    """Opsi mission operations sharing the oracle frame and input boundary."""

    def operation_siren_month_boss_room_difficulty(self) -> str:
        """Return the exact difficulty encoded in a retained Arbiter room."""

        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        state = self.read_ui_state()
        titles = tuple(
            text.text.strip()
            for text in state.texts
            if text.path.endswith("top/adapt/top_stage/title/name")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and re.fullmatch(r"(?:普通|困难)难度[：:].+", text.text.strip())
        )
        if len(titles) != 1:
            raise SemanticGateClosed(
                "operation siren month boss room title is absent or ambiguous"
            )
        return "normal" if titles[0].startswith("普通难度") else "hard"

    def click_operation_siren_mission_overview(self) -> ActionReceipt:
        """Open the daily-mission overview from the proven world-map footer."""

        # The overview is a globe-level action and remains available while no
        # zone detail panel is pinned.  Require the exact globe surface and
        # entrance target, but do not fabricate a selected-zone prerequisite.
        if not self.operation_siren_globe_visible():
            raise SemanticGateClosed("operation siren globe is not visible")
        state = self.read_state()
        target = self._unique(state, "os/globe/mission-overview")
        if not (
            target.active_in_hierarchy
            and target.active_and_enabled
            and target.interactable
            and target.raycast_top is None
            and target.bounds is not None
            and 0 <= target.bounds.left < target.bounds.right <= self.fingerprint.width
            and 0 <= target.bounds.top < target.bounds.bottom <= self.fingerprint.height
            and not self._blocking_rules(state, "os/globe/mission-overview")
        ):
            raise SemanticGateClosed(
                "operation siren mission-overview entrance is not actionable"
            )
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/globe/mission-overview",
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def _operation_siren_mission_overview_state(
        self,
    ) -> Tuple[
        OracleState, ButtonState, Tuple[ButtonState, ...], Tuple[ButtonState, ...], UiState
    ]:
        """Read the pinned WorldDailyTaskUI without inferring from pixels."""

        state = self.read_state()
        back = self._unique(state, "os/mission-overview/back")
        if (
            not back.active_in_hierarchy
            or not back.active_and_enabled
            or not back.interactable
            or back.raycast_top is not None
            or back.point is None
            or back.bounds is None
            or not back.bounds.contains(back.point)
            or self._blocking_rules(state, "os/mission-overview/back")
        ):
            raise SemanticGateClosed(
                "operation siren mission overview is not actionable"
            )

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
            or ui_state.image_truncated
            or ui_state.method_mask & 0x8 == 0
        ):
            raise SemanticGateClosed(
                "operation siren mission overview snapshots are incomplete"
            )
        titles = tuple(
            image
            for image in ui_state.images
            if image.path.endswith("Overlay/UIMain/blur_panel/adapt/top/title/title")
            and image.name == "title"
            and image.sprite == "task_daily_task"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(titles) != 1:
            raise SemanticGateClosed(
                "operation siren mission overview title is absent or ambiguous"
            )

        row_pattern = re.compile(
            r"(?:^|/)Overlay/UIMain/blur_panel/adapt/tasks/frame/viewport/"
            r"content/task_tpl(?:\(Clone\))?/button/(active|inactive)$"
        )
        active_rows = []
        inactive_rows = []
        for candidate in state.buttons:
            match = row_pattern.search(candidate.path)
            if match is None or candidate.name != match.group(1):
                continue
            if not candidate.active_in_hierarchy or not candidate.active_and_enabled:
                continue
            (active_rows if match.group(1) == "active" else inactive_rows).append(
                candidate
            )
        return state, back, tuple(active_rows), tuple(inactive_rows), ui_state

    def operation_siren_mission_overview_visible(self) -> bool:
        try:
            self._operation_siren_mission_overview_state()
        except SemanticGateClosed:
            return False
        return True

    def operation_siren_mission_overview_empty(self) -> bool:
        """Prove that the complete mounted list has no unaccepted task row."""

        state, _, active_rows, inactive_rows, ui_state = (
            self._operation_siren_mission_overview_state()
        )
        if active_rows:
            return False
        if not inactive_rows:
            if (state.generation <= ui_state.generation <= state.generation + 2
                    and ui_state.snapshot.get('text_truncated') is False):
                empty = tuple(text for text in ui_state.texts
                    if text.path.endswith('Overlay/UIMain/blur_panel/adapt/tasks/frame/empty/Text')
                    and text.active_in_hierarchy and text.active_and_enabled
                    and not text.truncated and text.text.strip())
                if len(empty) == 1:
                    # The client explicitly renders its empty-list marker.
                    # No rows alone is insufficient, but this existing page
                    # and coherent typed marker prove the zero-task branch.
                    return True
            raise SemanticGateClosed(
                "operation siren mission overview has no typed task rows"
            )
        return True

    def operation_siren_mission_overview_accept_available(self) -> bool:
        _, _, active_rows, _, _ = self._operation_siren_mission_overview_state()
        return any(
            row.actionable
            and row.point is not None
            and 0 <= row.point.x < self.fingerprint.width
            and 0 <= row.point.y < self.fingerprint.height
            for row in active_rows
        )

    def click_operation_siren_mission_overview_accept(self) -> ActionReceipt:
        state, _, active_rows, _, _ = self._operation_siren_mission_overview_state()
        actionable = tuple(
            row
            for row in active_rows
            if row.actionable
            and row.point is not None
            and row.bounds is not None
            and 0 <= row.point.x < self.fingerprint.width
            and 0 <= row.point.y < self.fingerprint.height
        )
        if len(actionable) != 1:
            raise SemanticGateClosed(
                "operation siren mission overview accept row is absent or ambiguous"
            )
        target = actionable[0]
        assert target.point is not None
        assert target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "game activity changed before mission overview input"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/mission-overview/accept",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_mission_overview_back(self) -> ActionReceipt:
        if not self.operation_siren_mission_overview_visible():
            raise SemanticGateClosed("operation siren mission overview is absent")
        return self.click("os/mission-overview/back")

    def _operation_siren_mission_list_state(
        self,
    ) -> Tuple[
        OracleState,
        UiState,
        ButtonState,
        Tuple[ButtonState, ...],
        Tuple[ButtonState, ...],
    ]:
        state = self.read_state()
        close = self._unique(state, "os/mission-list/close")
        if (
            not close.active_in_hierarchy
            or not close.active_and_enabled
            or not close.interactable
            or close.raycast_top is not None
            or close.point is None
            or close.bounds is None
            or not close.bounds.contains(close.point)
            or self._blocking_rules(state, "os/mission-list/close")
        ):
            raise SemanticGateClosed("operation siren mission list is not actionable")
        ui_state = self.read_text_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed(
                "operation siren mission list snapshots are not coherent"
            )
        titles = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith(
                "WorldInformationUI(Clone)/adapt/right_panel/title/task_all"
            )
            and text.text == "任务总汇"
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        if len(titles) != 1:
            raise SemanticGateClosed(
                "operation siren mission list title is absent or ambiguous"
            )
        row_pattern = re.compile(
            r"(?:^|/)WorldInformationUI\(Clone\)/adapt/right_panel/main/"
            r"viewport/content/task_tpl(?:\(Clone\))?/base_panel/(btn_go|btn_get)$"
        )
        go_rows = []
        finish_rows = []
        for button in state.buttons:
            match = row_pattern.search(button.path)
            if match is None or button.name != match.group(1):
                continue
            if not button.active_in_hierarchy or not button.active_and_enabled:
                continue
            (go_rows if button.name == "btn_go" else finish_rows).append(button)
        key = lambda item: (
            item.bounds.top if item.bounds is not None else math.inf,
            item.path,
        )
        return (
            state,
            ui_state,
            close,
            tuple(sorted(go_rows, key=key)),
            tuple(sorted(finish_rows, key=key)),
        )

    def operation_siren_mission_list_visible(self) -> bool:
        try:
            self._operation_siren_mission_list_state()
        except SemanticGateClosed:
            return False
        return True

    @staticmethod
    def _operation_siren_monthly_boss_rows(
        ui_state: UiState, rows: Sequence[ButtonState]
    ) -> Tuple[ButtonState, ...]:
        title_suffix = "/base_panel/base_show/title/Text"
        titles = tuple(
            text
            for text in ui_state.texts
            if "WorldInformationUI(Clone)/adapt/right_panel/main/viewport/content/"
            in text.path
            and text.path.endswith(title_suffix)
            and "仲裁机关" in re.sub(r"<[^>]*>", "", text.text)
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        monthly_rows = []
        for title in titles:
            assert title.bounds is not None
            candidates = tuple(
                row
                for row in rows
                if row.bounds is not None
                and row.bounds.bottom >= title.bounds.top
                and row.bounds.top <= title.bounds.bottom
            )
            if len(candidates) != 1:
                raise SemanticGateClosed(
                    "operation siren monthly boss row is absent or ambiguous"
                )
            if candidates[0] not in monthly_rows:
                monthly_rows.append(candidates[0])
        return tuple(monthly_rows)

    def operation_siren_mission_checkout_available(
        self, *, exclude_monthly_boss: bool = False
    ) -> bool:
        _, ui_state, _, rows, _ = self._operation_siren_mission_list_state()
        if exclude_monthly_boss:
            monthly_rows = self._operation_siren_monthly_boss_rows(ui_state, rows)
            rows = tuple(row for row in rows if row not in monthly_rows)
        return bool(
            self._operation_siren_actionable_rows(
                rows, self.fingerprint.width, self.fingerprint.height
            )
        )

    def operation_siren_mission_finish_available(self) -> bool:
        _, _, _, _, rows = self._operation_siren_mission_list_state()
        return bool(
            self._operation_siren_actionable_rows(
                rows, self.fingerprint.width, self.fingerprint.height
            )
        )

    def operation_siren_month_boss_difficulty(self) -> Optional[str]:
        """Read the monthly Arbiter task title from the mounted mission list."""

        _, ui_state, _, _, _ = self._operation_siren_mission_list_state()
        title_suffix = "/base_panel/base_show/title/Text"
        titles = tuple(
            re.sub(r"<[^>]*>", "", text.text).strip()
            for text in ui_state.texts
            if "WorldInformationUI(Clone)/adapt/right_panel/main/viewport/content/"
            in text.path
            and text.path.endswith(title_suffix)
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
        )
        matches = tuple(title for title in titles if "仲裁机关" in title)
        if not matches:
            return None
        if len(matches) != 1:
            raise SemanticGateClosed("operation siren monthly boss task is ambiguous")
        title = matches[0]
        if title.startswith("普通作战"):
            return "normal"
        if title.startswith("困难作战"):
            return "hard"
        raise SemanticGateClosed("operation siren monthly boss difficulty is unknown")

    def _click_operation_siren_mission_row(
        self, action: str, *, exclude_monthly_boss: bool = False
    ) -> ActionReceipt:
        if action not in ("checkout", "finish"):
            raise ValueError("operation siren mission action is unsupported")
        state, ui_state, _, go_rows, finish_rows = (
            self._operation_siren_mission_list_state()
        )
        rows = go_rows if action == "checkout" else finish_rows
        if action == "checkout" and exclude_monthly_boss:
            monthly_rows = self._operation_siren_monthly_boss_rows(ui_state, rows)
            rows = tuple(row for row in rows if row not in monthly_rows)
        actionable = self._operation_siren_actionable_rows(
            rows, self.fingerprint.width, self.fingerprint.height
        )
        if not actionable:
            raise SemanticGateClosed("operation siren mission row is absent")
        target = actionable[0]
        assert target.point is not None
        assert target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before mission row input")
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/mission-list/" + action,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_mission_checkout(
        self, *, exclude_monthly_boss: bool = False
    ) -> ActionReceipt:
        return self._click_operation_siren_mission_row(
            "checkout", exclude_monthly_boss=exclude_monthly_boss
        )

    def click_operation_siren_mission_finish(self) -> ActionReceipt:
        return self._click_operation_siren_mission_row("finish")
