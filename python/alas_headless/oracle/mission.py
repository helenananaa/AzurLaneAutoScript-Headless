"""Mission for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    ButtonState,
    MissionDisposition,
    MissionPageState,
    OracleState,
    Point,
)
from .errors import SemanticGateClosed, SemanticOracleError


class MissionOracle:
    """Mission operations sharing the oracle frame and input boundary."""

    @staticmethod
    def _mission_rows(state: OracleState, button_name: str) -> Tuple[ButtonState, ...]:
        pattern = re.compile(
            r"(?:^|/)TaskScene\(Clone\)/pages/TaskListPage\(Clone\)/"
            r"right_panel/content/([0-9]+)/frame/" + re.escape(button_name) + r"$"
        )
        rows = []
        indexes = set()
        for button in state.buttons:
            if button.name != button_name:
                continue
            match = pattern.search(button.path)
            if match is None:
                continue
            index = int(match.group(1))
            if index in indexes:
                raise SemanticGateClosed(
                    "mission row Button index is ambiguous: {0}".format(index)
                )
            indexes.add(index)
            rows.append((index, button))
        rows.sort(key=lambda item: item[0])
        return tuple(button for _, button in rows)

    def mission_page_state(self) -> MissionPageState:
        """Classify the reviewed TaskScene without treating absence as empty."""

        return self._retry_transition_read(self._mission_page_state_once)

    def _mission_page_state_once(self) -> MissionPageState:
        state = self.read_state()
        back = self._unique(state, "task/page/back")
        if not back.actionable or self._blocking_rules(state, "task/page/back"):
            raise SemanticGateClosed("mission page identity is not safely actionable")

        claim_all_matches = self._matches(state, "task/claim/all")
        if len(claim_all_matches) > 1:
            raise SemanticGateClosed("mission claim-all target is ambiguous")
        claim_all = claim_all_matches[0] if claim_all_matches else None
        claim_rows = self._mission_rows(state, "get_btn")
        unfinished_rows = self._mission_rows(state, "go_btn")

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed(
                "button and mission text snapshots are not coherent"
            )
        empty_markers = tuple(
            item
            for item in ui_state.texts
            if item.name == "Text"
            and item.path.endswith("TaskScene(Clone)/TaskEmptyListUI(Clone)/Text")
            and item.text == "没有进行中的任务"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and item.bounds.right > 0
            and item.bounds.bottom > 0
            and item.bounds.left < self.fingerprint.width
            and item.bounds.top < self.fingerprint.height
        )
        if len(empty_markers) > 1:
            raise SemanticGateClosed("mission empty marker is ambiguous")

        actionable_claim_rows = tuple(
            button for button in claim_rows if button.actionable
        )
        actionable_unfinished_rows = tuple(
            button for button in unfinished_rows if button.actionable
        )
        if claim_all is not None and claim_all.actionable:
            disposition = MissionDisposition.CLAIMABLE_ALL
        elif actionable_claim_rows:
            disposition = MissionDisposition.CLAIMABLE_ROW
        elif claim_all is not None or claim_rows:
            # A claim object hidden by clipping or an overlay is not evidence of
            # a safe click, and it must not be misreported as no work.
            disposition = MissionDisposition.UNKNOWN
        elif actionable_unfinished_rows:
            disposition = MissionDisposition.UNFINISHED
        elif empty_markers:
            disposition = MissionDisposition.EMPTY
        else:
            # Never infer EMPTY from mere absence while a page may still load.
            disposition = MissionDisposition.UNKNOWN

        return MissionPageState(
            disposition=disposition,
            generation=state.generation,
            back=back,
            claim_all=claim_all,
            claim_rows=actionable_claim_rows,
            unfinished_rows=actionable_unfinished_rows,
        )

    def mission_weekly_reward_available(self) -> bool:
        """Read the exact weekly-task badge on the current TaskScene."""

        return self._retry_transition_read(self._mission_weekly_reward_available_once)

    def _mission_weekly_reward_available_once(self) -> bool:
        state = self.read_state()
        back = self._unique(state, "task/page/back")
        if not back.actionable or self._blocking_rules(state, "task/page/back"):
            raise SemanticGateClosed("mission page identity is not safely actionable")
        ui_state = self.read_ui_state()
        matches = tuple(
            image
            for image in ui_state.images
            if image.name == "tip"
            and image.path.endswith(
                "TaskScene(Clone)/blur_panel/adapt/left_length/frame/"
                "tagRoot/weekly/tip"
            )
            and image.sprite == "exclamation_mark"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if len(matches) > 1:
            raise SemanticGateClosed("mission weekly badge is ambiguous")
        return bool(matches)

    def weekly_mission_progress_claim_available(self) -> bool:
        """Return whether the selected weekly tab exposes its progress reward."""

        return self._retry_transition_read(
            lambda: self._weekly_mission_progress_claim_target_once() is not None
        )

    def _weekly_mission_progress_claim_target_once(
        self,
    ) -> Optional[ButtonState]:
        state = self.read_state()
        back = self._unique(state, "task/page/back")
        if not back.actionable or self._blocking_rules(state, "task/page/back"):
            raise SemanticGateClosed("mission page identity is not safely actionable")
        path = (
            "TaskScene(Clone)/pages/TaskListForWeekPage(Clone)/task_progress/"
            "get_btn"
        )
        matches = tuple(
            button
            for button in state.buttons
            if button.name == "get_btn" and button.path.endswith(path)
        )
        if len(matches) > 1:
            raise SemanticGateClosed("weekly mission progress claim is ambiguous")
        if not matches:
            return None
        target = matches[0]
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.bounds is None
            or self._blocking_rules(state, "task/weekly-progress/claim")
        ):
            return None

        ui_state = self.read_ui_state()
        if (
            ui_state.generation < state.generation
            or ui_state.generation > state.generation + 2
        ):
            raise SemanticGateClosed(
                "weekly mission button and UI snapshots are not coherent"
            )
        weekly_selected = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(
                "TaskScene(Clone)/blur_panel/adapt/left_length/frame/"
                "tagRoot/weekly/selected/Image"
            )
            and image.sprite == "icon_week_sel"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        button_images = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(path)
            and image.sprite == "get_btn"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds == target.bounds
        )
        enabled_images = tuple(
            image
            for image in ui_state.images
            if image.path.endswith(path + "/enable")
            and image.sprite == "finish_btn_tran_1"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
            and target.bounds.contains(
                Point(
                    (image.bounds.left + image.bounds.right) / 2.0,
                    (image.bounds.top + image.bounds.bottom) / 2.0,
                )
            )
        )
        if len(weekly_selected) != 1:
            raise SemanticGateClosed("weekly mission tab identity is absent or ambiguous")
        if len(button_images) != 1 or len(enabled_images) != 1:
            return None
        return target

    def click_weekly_mission_progress_claim(self) -> ActionReceipt:
        """Claim the unique currently enabled weekly progress reward once."""

        target = self._retry_transition_read(
            self._weekly_mission_progress_claim_target_once
        )
        if target is None or target.bounds is None:
            raise SemanticGateClosed("weekly mission progress claim is absent")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before weekly mission claim")
        point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(point):
            raise SemanticGateClosed("weekly mission claim point is invalid")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="task/weekly-progress/claim",
            generation=self._last_generation or 0,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def wait_for_mission_state(
        self,
        timeout_seconds: float,
        interval_seconds: float = 0.5,
        required_generations: int = 2,
    ) -> MissionPageState:
        if required_generations < 2:
            raise ValueError("mission state requires at least two generations")
        deadline = self._monotonic() + timeout_seconds
        last_state: Optional[MissionPageState] = None
        stable_generations = 0
        last_error: Optional[SemanticOracleError] = None
        while self._monotonic() < deadline:
            try:
                candidate = self.mission_page_state()
                if candidate.disposition == MissionDisposition.UNKNOWN:
                    last_state = None
                    stable_generations = 0
                elif last_state is None or candidate.signature != last_state.signature:
                    last_state = candidate
                    stable_generations = 1
                elif candidate.generation > last_state.generation:
                    last_state = candidate
                    stable_generations += 1
                if (
                    last_state is not None
                    and stable_generations >= required_generations
                ):
                    return last_state
            except SemanticOracleError as exc:
                last_error = exc
                last_state = None
                stable_generations = 0
            self._sleep(interval_seconds)
        if last_error is not None:
            raise SemanticGateClosed(
                "stable mission-state wait timed out"
            ) from last_error
        raise SemanticGateClosed("stable mission-state wait timed out")

    def click_mission_claim_row(self, expected_path: str) -> ActionReceipt:
        """Claim one uniquely actionable task row by its current typed path."""

        if not isinstance(expected_path, str) or not expected_path:
            raise ValueError("mission claim row path must be non-empty")
        page = self.mission_page_state()
        if page.disposition != MissionDisposition.CLAIMABLE_ROW:
            raise SemanticGateClosed("mission page is not row-claimable")
        matches = tuple(
            row for row in page.claim_rows if row.path == expected_path
        )
        if len(page.claim_rows) != 1 or len(matches) != 1:
            raise SemanticGateClosed("mission claim row is absent or ambiguous")
        target = matches[0]
        match = re.search(r"/content/([0-9]+)/frame/get_btn$", target.path)
        if match is None:
            raise SemanticGateClosed("mission claim row path is malformed")
        if not target.actionable or target.point is None or target.bounds is None:
            raise SemanticGateClosed("mission claim row is not actionable")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("foreground changed before mission row claim")
        click_point = Point(
            (target.bounds.left + target.bounds.right) / 2.0,
            (target.bounds.top + target.bounds.bottom) / 2.0,
        )
        if not target.bounds.contains(click_point):
            raise SemanticGateClosed("mission claim row click point is invalid")
        self._tap(int(round(click_point.x)), int(round(click_point.y)))
        return ActionReceipt(
            semantic_id="task/claim/row/" + match.group(1),
            generation=page.generation,
            point=click_point,
            bounds=target.bounds,
            path=target.path,
        )
