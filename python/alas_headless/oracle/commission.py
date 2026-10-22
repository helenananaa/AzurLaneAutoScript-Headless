"""Commission for the typed ALAS boundary."""

from __future__ import annotations

import re
from typing import Dict, Optional, Sequence, Tuple, Union
from .contracts import (
    ActionReceipt,
    Bounds,
    ButtonState,
    CommissionDetailState,
    CommissionRowState,
    CommissionScrollProof,
    CommissionScrollState,
    CommissionStartProof,
    CommissionStatus,
    ImageState,
    Point,
    TextState,
)
from .errors import (SemanticCommissionRowIncomplete, SemanticGateClosed,
                     SemanticNavigationPending)


class CommissionOracle:
    """Commission operations sharing the oracle frame and input boundary."""

    def commission_reward_oil_maxed(self) -> bool:
        """Expose the client's exact commission rejection to native ALAS."""
        state = self.read_state()
        targets = self._matches(state, 'reward/commission/finish')
        if not targets:
            return False
        if len(targets) != 1:
            raise SemanticGateClosed('commission finish owner is ambiguous')
        if (not targets[0].active_in_hierarchy or not targets[0].active_and_enabled
                or self._blocking_rules(state, 'reward/commission/finish')):
            return False
        ui = self._paired_ui_after_state()
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('commission oil rejection snapshots are incoherent')
        tips = [t for t in ui.texts if t.path.endswith(
            'UIOverlay/TipPanel(Clone)/Grid/toolTip(Clone)/Text')
            and t.active_in_hierarchy and t.active_and_enabled]
        if any(t.truncated for t in tips):
            raise SemanticGateClosed('commission oil rejection text is incomplete')
        messages = [re.sub(r'\s+', '', re.sub(r'<[^>]*>', '', t.text))
                    for t in tips if t.bounds is not None]
        return '石油已经达到上限无法领取委托奖励' in messages

    def commission_rows(self) -> Tuple[CommissionRowState, ...]:
        """Read visible commission rows without inferring hidden or unknown state.

        This deliberately exposes only rows whose exact row Button is currently
        top-raycastable on screen.  It is therefore a viewport read, not a claim
        that the scrollable commission list has been exhausted.
        """

        return self._retry_transition_read(self._commission_rows_once)

    def _commission_rows_once(self) -> Tuple[CommissionRowState, ...]:
        """Read one exact commission-list generation."""

        button_state = self.read_state()
        page_back = self._unique(button_state, "commission/page/back")
        if not page_back.actionable or self._blocking_rules(
            button_state, "commission/page/back"
        ):
            raise SemanticGateClosed("commission page identity is not proven")

        row_pattern = re.compile(
            r"(?:^|/)EventUI\(Clone\)/scrollRect\$/content/([0-9]+)/(?:bgNormal|bgEmergence)\$$"
        )
        indexed_buttons: Dict[int, ButtonState] = {}
        row_roots: Dict[int, str] = {}
        for button in button_state.buttons:
            if button.name not in ("bgNormal$", "bgEmergence$"):
                continue
            match = row_pattern.search(button.path)
            if (match is None or not button.path.endswith("/" + button.name)
                    or not button.active_in_hierarchy):
                continue
            index = int(match.group(1))
            if index in indexed_buttons:
                raise SemanticGateClosed(
                    "commission row Button index is ambiguous: {0}".format(index)
                )
            indexed_buttons[index] = button
            row_roots[index] = button.path[: -(len(button.name) + 1)]

        if not indexed_buttons:
            if self.commission_is_empty():
                return ()
            raise SemanticGateClosed(
                "commission page has neither indexed rows nor the exact empty marker"
            )

        ui_state = self._paired_ui_after_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed("typed commission Image snapshot is incomplete")
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission snapshots are not coherent")

        def exact_text(path: str) -> TextState:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path == path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "commission row text is absent or ambiguous: " + path
                )
            return matches[0]

        def exact_image(path: str) -> ImageState:
            matches = tuple(
                item
                for item in ui_state.images
                if item.path == path
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                if not matches and path.endswith('/iconType$'):
                    raise SemanticCommissionRowIncomplete(path, ui_state.generation)
                raise SemanticGateClosed(
                    "commission row image is absent or ambiguous: " + path
                )
            return matches[0]

        status_sprites = {
            # These are the exact pending/running row markers observed and
            # exercised on the pinned CN 9.7.10 build. New sprites remain closed.
            "kongxian_bg": CommissionStatus.PENDING,
            "tag_ongoing": CommissionStatus.RUNNING,
            "tag_finish": CommissionStatus.FINISHED,
        }
        rows = []
        for index in sorted(indexed_buttons):
            button = indexed_buttons[index]
            if (
                not button.actionable
                or button.point is None
                or not 0 <= button.point.x < self.fingerprint.width
                or not 0 <= button.point.y < self.fingerprint.height
            ):
                continue
            root = row_roots[index]
            name = exact_text(root + "/labelName$").text.strip()
            level_text = exact_text(root + "/level/labelLv$").text.strip()
            status_matches = tuple(
                item
                for item in ui_state.images
                if item.path
                in (
                    root + "/iconState$/0",
                    root + "/iconState$/1",
                    root + "/iconState$/2",
                )
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(status_matches) != 1:
                raise SemanticGateClosed(
                    "commission row status image is absent or ambiguous: " + root
                )
            status_image = status_matches[0]
            if not name or re.fullmatch(r"[0-9]{1,3}", level_text) is None:
                raise SemanticGateClosed("commission row identity is malformed")
            level = int(level_text)
            if level <= 0:
                raise SemanticGateClosed("commission row level is invalid")
            try:
                status = status_sprites[status_image.sprite]
            except KeyError as exc:
                raise SemanticGateClosed(
                    "commission row status sprite is not reviewed: "
                    + status_image.sprite
                ) from exc
            # A completed row replaces its countdown with tag_finish. That
            # exact status proves zero remaining time; ALAS filters finished
            # rows and retains ownership of reward collection and scheduling.
            duration_seconds = (0 if status == CommissionStatus.FINISHED else
                self.parse_countdown_seconds(
                    exact_text(root + "/labelTime$/Text").text.strip()))
            try:
                type_image = exact_image(root + "/iconType$")
            except SemanticCommissionRowIncomplete:
                # Preserve this row and its known occupancy for native ALAS.
                # None is an unavailable field, never an inferred genre or an
                # input authority. Native invalid-row filtering owns exclusion.
                type_sprite = None
            else:
                if not type_image.sprite:
                    raise SemanticGateClosed("commission row type sprite is empty")
                type_sprite = type_image.sprite
            rows.append(
                CommissionRowState(
                    index=index,
                    name=name,
                    level=level,
                    duration_seconds=duration_seconds,
                    status=status,
                    type_sprite=type_sprite,
                    button=button,
                )
            )
        if not rows:
            raise SemanticGateClosed("commission viewport has no actionable typed rows")
        return tuple(rows)

    def commission_scroll_state(self) -> CommissionScrollState:
        """Read the exact commission scrollbar geometry from typed Images."""

        return self._retry_transition_read(self._commission_scroll_state_once)

    def _commission_scroll_state_once(self) -> CommissionScrollState:
        button_state = self.read_state()
        page_back = self._unique(button_state, "commission/page/back")
        if not page_back.actionable or self._blocking_rules(
            button_state, "commission/scroll"
        ):
            raise SemanticGateClosed("commission scroll page identity is not proven")
        ui_state = self._paired_ui_after_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed(
                "typed commission scroll Image snapshot is incomplete"
            )
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission scroll snapshots are not coherent")

        track_suffix = "EventUI(Clone)/blur_panel/adapt/scroll_bar"
        handle_suffix = track_suffix + "/Image"
        tracks = tuple(
            image
            for image in ui_state.images
            if image.name == "scroll_bar"
            and image.path.endswith(track_suffix)
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        handles = tuple(
            image
            for image in ui_state.images
            if image.name == "Image"
            and image.path.endswith(handle_suffix)
            and image.sprite == "scroll_bar"
            and image.active_in_hierarchy
            and image.active_and_enabled
            and not image.truncated
            and image.bounds is not None
        )
        if not tracks and not handles:
            # Lists that fit in one viewport do not instantiate this optional
            # scrollbar at all.  A complete Image snapshot proves that exact
            # absence; a partial track/handle pair remains invalid below.
            empty_bounds = Bounds(0.0, 0.0, 0.0, 0.0)
            return CommissionScrollState(
                generation=ui_state.generation,
                position=0.0,
                page_fraction=1.0,
                track_bounds=empty_bounds,
                handle_bounds=empty_bounds,
                handle_path="",
                handle_raycast_top=None,
            )
        if len(tracks) != 1 or len(handles) != 1:
            raise SemanticGateClosed(
                "commission scrollbar track or handle is absent or ambiguous"
            )
        track = tracks[0]
        handle = handles[0]
        assert track.bounds is not None
        assert handle.bounds is not None
        track_height = track.bounds.bottom - track.bounds.top
        handle_height = handle.bounds.bottom - handle.bounds.top
        track_center_x = (track.bounds.left + track.bounds.right) / 2.0
        handle_center_x = (handle.bounds.left + handle.bounds.right) / 2.0
        if (
            track_height <= 0
            or handle_height <= 0
            or handle_height > track_height + 20.0
            or abs(track_center_x - handle_center_x) > 20.0
        ):
            raise SemanticGateClosed("commission scrollbar geometry is invalid")
        travel = max(0.0, track_height - handle_height)
        if travel <= 1.0:
            position = 0.0
        else:
            raw_position = (handle.bounds.top - track.bounds.top) / travel
            if raw_position < -0.15 or raw_position > 1.15:
                raise SemanticGateClosed("commission scrollbar position is invalid")
            position = min(1.0, max(0.0, raw_position))
        return CommissionScrollState(
            generation=ui_state.generation,
            position=position,
            page_fraction=min(1.0, handle_height / track_height),
            track_bounds=track.bounds,
            handle_bounds=handle.bounds,
            handle_path=handle.path,
            handle_raycast_top=handle.raycast_top,
        )

    @staticmethod
    def _commission_row_signatures(
        rows: Sequence[CommissionRowState],
    ) -> Tuple[Tuple[Union[int, str, None], ...], ...]:
        # Countdown and lifecycle status can change independently of a
        # gesture.  Neither is evidence that a different row entered the
        # actionable viewport.
        return tuple(
            (
                row.index,
                row.name,
                row.level,
                row.type_sprite,
            )
            for row in rows
        )

    def _commission_scroll_to(
        self,
        target_position: float,
        direction: str,
        timeout_seconds: float = 12.0,
        *,
        precondition_oracle=None,
    ) -> Optional[CommissionScrollProof]:
        if direction not in ("top", "next"):
            raise ValueError("commission scroll direction is not supported")
        if not 0.0 <= target_position <= 1.0:
            raise ValueError("commission scroll target must be within [0, 1]")
        if self._swipe is None:
            raise SemanticGateClosed("semantic commission swipe backend is unavailable")
        source = precondition_oracle if precondition_oracle is not None else self
        before = source.commission_scroll_state()
        before_rows = source.commission_rows()
        before_signatures = self._commission_row_signatures(before_rows)
        if not before.scrollable:
            return None
        if direction == "top" and before.at_top:
            return None
        if direction == "next" and before.at_bottom:
            return None
        if before.handle_raycast_top is not True:
            raise SemanticGateClosed(
                "commission scrollbar handle is not top-raycastable"
            )

        handle_height = before.handle_bounds.bottom - before.handle_bounds.top
        track_height = before.track_bounds.bottom - before.track_bounds.top
        travel = track_height - handle_height
        if travel <= 1.0:
            return None
        start = Point(
            (before.handle_bounds.left + before.handle_bounds.right) / 2.0,
            (before.handle_bounds.top + before.handle_bounds.bottom) / 2.0,
        )
        end = Point(
            start.x,
            before.track_bounds.top + target_position * travel + handle_height / 2.0,
        )
        if not (
            0 <= start.x < self.fingerprint.width
            and 0 <= start.y < self.fingerprint.height
            and 0 <= end.x < self.fingerprint.width
            and 0 <= end.y < self.fingerprint.height
        ):
            raise SemanticGateClosed(
                "commission scrollbar gesture is outside the screen"
            )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before commission scroll")
        # Short drags have returned a fresh unchanged owning list on the
        # contended headless client. Allow more Unity input frames without
        # adding another gesture or relaxing the movement postcondition.
        duration_ms = 1500
        self._swipe(
            int(round(start.x)),
            int(round(start.y)),
            int(round(end.x)),
            int(round(end.y)),
            duration_ms,
        )
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed after commission scroll")

        deadline = self._monotonic() + timeout_seconds
        last_error: Optional[SemanticGateClosed] = None
        after = None
        while self._monotonic() < deadline:
            self._sleep(0.25)
            try:
                after = self.commission_scroll_state()
                after_rows = self.commission_rows()
                after_signatures = self._commission_row_signatures(after_rows)
            except SemanticGateClosed as exc:
                last_error = exc
                continue
            moved = (
                after.position < before.position - 0.03
                if direction == "top"
                else after.position > before.position + 0.03
            )
            if after.generation > before.generation and moved:
                return CommissionScrollProof(
                    direction=direction,
                    before_position=before.position,
                    after_position=after.position,
                    before_generation=before.generation,
                    after_generation=after.generation,
                    before_row_signatures=before_signatures,
                    after_row_signatures=after_signatures,
                )
        if last_error is not None:
            raise last_error
        if (after is not None and after.generation > before.generation
                and after.handle_path == before.handle_path
                and abs(after.position - before.position) <= 0.03
                and len(after_signatures) == len(before_signatures)
                and all(old[:3] == new[:3]
                        and (old[3] is None or new[3] is None or old[3] == new[3])
                        for old, new in zip(before_signatures, after_signatures))):
            # A missed scrollbar drag must not imply list exhaustion or shut
            # down unrelated tasks. The existing complete page/row reads prove
            # the same fresh source; a type Image mounting/unmounting alone is
            # not a changed viewport. ALAS owns its failure interval/re-entry.
            raise SemanticNavigationPending(
                "commission/scroll", {
                    "direction": direction,
                    "before_generation": before.generation,
                    "before_position": before.position,
                    "after_position": after.position,
                    "points": (int(round(start.x)), int(round(start.y)),
                               int(round(end.x)), int(round(end.y)), duration_ms),
                }, after.generation,
                "commission scrollbar did not move on the fresh owning list")
        raise SemanticGateClosed("commission scrollbar transition was not proven")

    def commission_scroll_next(self, *, precondition_oracle=None) -> Optional[CommissionScrollProof]:
        source = precondition_oracle if precondition_oracle is not None else self
        state = source.commission_scroll_state()
        target = min(1.0, state.position + max(0.25, state.page_fraction * 0.8))
        proof = self._commission_scroll_to(target, "next", precondition_oracle=source)
        if (
            proof is not None
            and proof.before_row_signatures == proof.after_row_signatures
        ):
            # The exact handle moved, but no new stable row identity entered
            # the actionable viewport.  For ALAS list scanning this is list
            # exhaustion, not another page to process.
            return None
        return proof

    def commission_scroll_to_top(self, *, precondition_oracle_factory=None) -> Optional[CommissionScrollProof]:
        source = precondition_oracle_factory() if precondition_oracle_factory is not None else self
        before = source.commission_scroll_state()
        before_signatures = self._commission_row_signatures(source.commission_rows())
        if not before.scrollable or before.at_top:
            return None

        after = before
        after_signatures = before_signatures
        for _ in range(6):
            step = self._commission_scroll_to(0.0, "top", precondition_oracle=source)
            if step is None:
                break
            after = self.commission_scroll_state()
            after_signatures = self._commission_row_signatures(self.commission_rows())
            if after.at_top:
                return CommissionScrollProof(
                    direction="top",
                    before_position=before.position,
                    after_position=after.position,
                    before_generation=before.generation,
                    after_generation=after.generation,
                    before_row_signatures=before_signatures,
                    after_row_signatures=after_signatures,
                )
            source = precondition_oracle_factory() if precondition_oracle_factory is not None else self
        raise SemanticGateClosed("commission scrollbar did not reach the exact top")

    def commission_is_empty(self) -> bool:
        """Return true only for the pinned commission page's explicit empty text."""

        button_state = self.read_state()
        page_back = self._unique(button_state, "commission/page/back")
        if not page_back.actionable or self._blocking_rules(
            button_state, "commission/page/back"
        ):
            raise SemanticGateClosed("commission page identity is not proven")
        ui_state = self._paired_ui_after_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission empty snapshots are not coherent")
        matches = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith("EventUI(Clone)/empty/Text")
            and item.text == "暂无可以进行的委托"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and item.bounds.right > 0
            and item.bounds.bottom > 0
            and item.bounds.left < self.fingerprint.width
            and item.bounds.top < self.fingerprint.height
        )
        if len(matches) > 1:
            raise SemanticGateClosed("commission empty marker is ambiguous")
        if matches:
            row_pattern = re.compile(
                r"(?:^|/)EventUI\(Clone\)/scrollRect\$/content/([0-9]+)/"
                r"(?:bgNormal|bgEmergence)\$$"
            )
            visible_rows = tuple(
                button
                for button in button_state.buttons
                if button.name in ("bgNormal$", "bgEmergence$")
                and row_pattern.search(button.path) is not None
                and button.actionable
                and button.point is not None
                and 0 <= button.point.x < self.fingerprint.width
                and 0 <= button.point.y < self.fingerprint.height
            )
            if visible_rows:
                raise SemanticGateClosed(
                    "commission page reports rows and empty together"
                )
        return bool(matches)

    def click_commission_row(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> ActionReceipt:
        """Select one exact visible pending row after re-reading typed state."""

        expected = tuple(expected_signature)
        if len(expected) != 6:
            raise SemanticGateClosed("commission row signature is malformed")
        if not isinstance(expected[5], str) or not expected[5]:
            raise SemanticGateClosed("commission row type is unavailable for input")
        rows = self.commission_rows()
        matches = tuple(row for row in rows if row.signature == expected)
        if len(matches) != 1:
            raise SemanticGateClosed("commission row identity is absent or ambiguous")
        row = matches[0]
        if row.status != CommissionStatus.PENDING:
            raise SemanticGateClosed("commission row is not pending")
        state = self.read_state()
        current = tuple(
            button for button in state.buttons if button.path == row.button.path
        )
        if len(current) != 1:
            raise SemanticGateClosed("commission row Button changed before input")
        button = current[0]
        if not button.actionable or button.point is None or button.bounds is None:
            raise SemanticGateClosed("commission row is not actionable")
        if self._blocking_rules(state, "commission/page/back"):
            raise SemanticGateClosed("commission row action is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before commission input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        return ActionReceipt(
            semantic_id="commission/row/{0}".format(row.index),
            generation=state.generation,
            point=button.point,
            bounds=button.bounds,
            path=button.path,
        )

    def click_commission_running_row(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> ActionReceipt:
        """Open an exact running row while allowing its countdown to advance."""

        expected = tuple(expected_signature)
        if len(expected) != 6 or expected[4] != CommissionStatus.RUNNING.value:
            raise SemanticGateClosed("running commission signature is malformed")
        if not isinstance(expected[5], str) or not expected[5]:
            raise SemanticGateClosed("commission row type is unavailable for input")
        rows = self.commission_rows()
        matches = tuple(
            row
            for row in rows
            if row.index == expected[0]
            and row.name == expected[1]
            and row.level == expected[2]
            and row.status == CommissionStatus.RUNNING
            and row.type_sprite == expected[5]
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "running commission row identity is absent or ambiguous"
            )
        row = matches[0]
        state = self.read_state()
        current = tuple(button for button in state.buttons if button.path == row.button.path)
        if len(current) != 1 or not current[0].actionable:
            raise SemanticGateClosed("running commission row is not actionable")
        button = current[0]
        if button.point is None or button.bounds is None:
            raise SemanticGateClosed("running commission row geometry is absent")
        if self._blocking_rules(state, "commission/page/back"):
            raise SemanticGateClosed("running commission row action is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before commission input")
        self._tap(int(round(button.point.x)), int(round(button.point.y)))
        return ActionReceipt(
            semantic_id="commission/running/{0}".format(row.index),
            generation=state.generation,
            point=button.point,
            bounds=button.bounds,
            path=button.path,
        )

    def click_commission_cancel(self) -> ActionReceipt:
        """Click the exact visible cancel image on a coherent running detail."""

        state = self.read_state()
        back = self._unique(state, "commission/detail/back")
        if not back.actionable:
            raise SemanticGateClosed("running commission detail is not actionable")
        ui_state = self._paired_ui_after_state()
        if not state.generation <= ui_state.generation <= state.generation + 2:
            raise SemanticGateClosed("running commission detail snapshots are incoherent")
        suffix = "/maskDetail/detailPanel/btn/giveup"
        labels = tuple(
            item
            for item in ui_state.texts
            if item.path.endswith(suffix + "/text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.text.strip() == "取消"
        )
        images = tuple(
            item
            for item in ui_state.images
            if item.path.endswith(suffix)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and item.sprite == "btn_sel"
            and item.bounds is not None
        )
        if len(labels) != 1 or len(images) != 1:
            raise SemanticGateClosed("running commission cancel identity is incomplete")
        bounds = images[0].bounds
        assert bounds is not None
        point = Point((bounds.left + bounds.right) / 2, (bounds.top + bounds.bottom) / 2)
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed("game activity changed before commission cancel")
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="commission/detail/cancel",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=images[0].path,
        )

    def commission_detail_state(self) -> CommissionDetailState:
        """Read the exact selected commission and ship-assignment state."""

        return self._retry_transition_read(self._commission_detail_state_once)

    def _commission_detail_state_once(self) -> CommissionDetailState:
        button_state = self.read_state()
        back = self._unique(button_state, "commission/detail/back")
        recommend = self._unique(button_state, "commission/detail/recommend")
        start = self._unique(button_state, "commission/detail/start")
        if not back.actionable:
            raise SemanticGateClosed("commission detail page identity is not proven")
        for target in (recommend, start):
            if (
                not target.active_in_hierarchy
                or not target.active_and_enabled
                or not target.interactable
                or target.point is None
                or target.bounds is None
                or target.raycast_top is False
            ):
                raise SemanticGateClosed(
                    "commission detail input is not structurally valid"
                )

        ui_state = self._paired_ui_after_state()
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed("commission detail snapshots are not coherent")

        base = "Overlay/UIMain/blur_panel/scrollItem/"

        def exact_text(suffix: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(base + suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "commission detail text is absent or ambiguous: " + suffix
                )
            return re.sub(r"<[^<>]{1,128}>", "", matches[0].text).strip()

        name = exact_text("labelName$")
        level_text = exact_text("level/labelLv$")
        duration_text = exact_text("labelTime$/Text")
        oil_text = exact_text("maskDetail/detailPanel/consume/Text")
        if (
            not name
            or re.fullmatch(r"[0-9]{1,3}", level_text) is None
            or re.fullmatch(r"[0-9]+", oil_text) is None
        ):
            raise SemanticGateClosed("commission detail identity is malformed")

        empty_pattern = re.compile(
            r"(?:^|/)maskDetail/detailPanel/frame/ship_contain_(?:left|right)/"
            r"ship_[1-3]/emptytpl$"
        )
        empty_paths = {
            button.path
            for button in button_state.buttons
            if empty_pattern.search(button.path) is not None
            and button.active_in_hierarchy
            and button.active_and_enabled
        }
        if len(empty_paths) > 6:
            raise SemanticGateClosed("commission detail empty ship slots are malformed")
        empty_count = len(empty_paths)
        selected_count = 6 - empty_count
        return CommissionDetailState(
            name=name,
            level=int(level_text),
            duration_seconds=self.parse_countdown_seconds(duration_text),
            oil_cost=int(oil_text),
            selected_ship_count=selected_count,
            empty_ship_count=empty_count,
        )

    def _click_commission_detail(
        self,
        semantic_id: str,
        expected_signature: Sequence[Union[int, str]],
        require_assigned_ships: bool,
    ) -> ActionReceipt:
        expected = tuple(expected_signature)
        if len(expected) != 6:
            raise SemanticGateClosed("commission row signature is malformed")
        detail = self.commission_detail_state()
        if detail.signature != (expected[1], expected[2], expected[3]):
            raise SemanticGateClosed("selected commission detail identity changed")
        if require_assigned_ships and detail.selected_ship_count < 3:
            raise SemanticGateClosed(
                "commission start requires at least three assigned ships"
            )
        state = self.read_state()
        target = self._unique(state, semantic_id)
        if (
            not target.active_in_hierarchy
            or not target.active_and_enabled
            or not target.interactable
            or target.point is None
            or target.bounds is None
            or target.raycast_top is False
            or self._blocking_rules(state, semantic_id)
        ):
            raise SemanticGateClosed("commission detail action is blocked")
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "game activity changed before commission detail input"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id=semantic_id,
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_commission_recommend(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> ActionReceipt:
        return self._click_commission_detail(
            "commission/detail/recommend",
            expected_signature,
            require_assigned_ships=False,
        )

    def click_commission_start(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> ActionReceipt:
        return self._click_commission_detail(
            "commission/detail/start",
            expected_signature,
            require_assigned_ships=True,
        )

    def commission_start_oil_rejection_generation(
        self, expected_signature, expected_oil_cost, input_generation
    ):
        """Classify a fresh client rejection without authorizing recovery input."""
        state = self.read_state()
        ui = self._paired_ui_after_state()
        tips = tuple(t for t in ui.texts if t.path.endswith(
            'UIOverlay/TipPanel(Clone)/Grid/toolTip(Clone)/Text')
            and t.active_in_hierarchy and t.active_and_enabled)
        messages = tuple(re.sub(r'\s+', '', re.sub(r'<[^>]*>', '', t.text))
                         for t in tips)
        if '石油已经达到上限无法接受委托' not in messages:
            return None
        if len(tips) != 1 or tips[0].truncated:
            raise SemanticGateClosed('commission start rejection text is incomplete or ambiguous')
        if not state.generation <= ui.generation <= state.generation + 2:
            raise SemanticGateClosed('commission start rejection snapshots are incoherent')
        if min(state.generation, ui.generation) <= input_generation:
            return None
        pending = self.commission_start_pending_generation(expected_signature, expected_oil_cost)
        return pending if pending is not None and pending > input_generation else None

    def commission_start_pending_generation(self, expected_signature, expected_oil_cost):
        """Read the exact healthy pending owner after an unproven start.

        This permits only task-local failure, never success or another input.
        A missing or changed owner keeps the original uncertainty fatal.
        """
        expected = tuple(expected_signature)
        if len(expected) != 6 or expected[4] != CommissionStatus.PENDING.value:
            raise SemanticGateClosed('commission pending signature is malformed')
        state = self.read_state()
        if self._matches(state, 'commission/page/back'):
            return None
        back = self._unique(state, 'commission/detail/back')
        start = self._unique(state, 'commission/detail/start')
        if (not back.actionable
                or not start.active_in_hierarchy or not start.active_and_enabled
                or not start.interactable or start.point is None or start.bounds is None
                or start.raycast_top is False
                or self._blocking_rules(state, 'commission/detail/back')
                or self._blocking_rules(state, 'commission/detail/start')):
            raise SemanticGateClosed('pending commission detail is blocked')
        ui = self._paired_ui_after_state()
        if (ui.image_truncated or ui.method_mask & 0x8 == 0
                or not state.generation <= ui.generation <= state.generation + 2):
            raise SemanticGateClosed('pending commission detail snapshot is incomplete or incoherent')
        root = 'Overlay/UIMain/blur_panel/scrollItem'

        def active(records, suffix):
            matches = tuple(item for item in records
                            if item.path.endswith(root + suffix)
                            and item.active_in_hierarchy and item.active_and_enabled)
            if any(item.truncated for item in matches):
                raise SemanticGateClosed('pending commission detail field is truncated')
            return matches

        def text(suffix):
            matches = active(ui.texts, suffix)
            if len(matches) != 1:
                raise SemanticGateClosed('pending commission detail text is absent or ambiguous')
            return re.sub(r'<[^<>]{1,128}>', '', matches[0].text).strip()

        types = active(ui.images, '/iconType$')
        pending = active(ui.images, '/iconState$/0')
        if len(types) != 1 or len(pending) != 1:
            return None
        if (active(ui.images, '/iconState$/1')
                or active(ui.texts, '/maskDetail/detailPanel/btn/giveup/text')):
            return None
        if (text('/labelName$') != expected[1]
                or text('/level/labelLv$') != str(expected[2])
                or self.parse_countdown_seconds(text('/labelTime$/Text')) != expected[3]
                or types[0].sprite != expected[5]
                or pending[0].sprite != 'kongxian_bg'
                or text('/maskDetail/detailPanel/btn/start/text') != '开始'
                or text('/maskDetail/detailPanel/consume/Text') != str(expected_oil_cost)):
            raise SemanticGateClosed('pending commission detail identity changed')
        return state.generation

    def commission_start_transition(
        self, expected_signature: Sequence[Union[int, str]]
    ) -> CommissionStartProof:
        """Prove that the exact pending row returned with a live countdown."""

        expected = tuple(expected_signature)
        if len(expected) != 6 or expected[4] != CommissionStatus.PENDING.value:
            raise SemanticGateClosed("commission start proof signature is malformed")
        index, name, level, before_duration, _, type_sprite = expected
        if not isinstance(index, int):
            raise SemanticGateClosed("commission start proof index is malformed")

        button_state = self.read_state()
        page_back_matches = self._matches(button_state, "commission/page/back")
        detail_back_matches = self._matches(button_state, "commission/detail/back")
        if not page_back_matches and len(detail_back_matches) == 1:
            detail_back = detail_back_matches[0]
            if not detail_back.actionable or self._blocking_rules(
                button_state, "commission/detail/back"
            ):
                raise SemanticGateClosed(
                    "running commission detail identity is not proven"
                )
            ui_state = self._paired_ui_after_state()
            if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
                raise SemanticGateClosed(
                    "running commission detail Image snapshot is incomplete"
                )
            if (
                ui_state.generation < button_state.generation
                or ui_state.generation > button_state.generation + 2
            ):
                raise SemanticGateClosed(
                    "running commission detail snapshots are not coherent"
                )
            root = "Overlay/UIMain/blur_panel/scrollItem"

            def detail_text(suffix: str) -> str:
                matches = tuple(
                    item
                    for item in ui_state.texts
                    if item.path.endswith(root + suffix)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "running commission detail text is ambiguous"
                    )
                return re.sub(r"<[^<>]{1,128}>", "", matches[0].text).strip()

            def detail_image(suffix: str) -> ImageState:
                matches = tuple(
                    item
                    for item in ui_state.images
                    if item.path.endswith(root + suffix)
                    and item.active_in_hierarchy
                    and item.active_and_enabled
                    and not item.truncated
                )
                if len(matches) != 1:
                    raise SemanticGateClosed(
                        "running commission detail image is ambiguous"
                    )
                return matches[0]

            actual_name = detail_text("/labelName$")
            actual_level = detail_text("/level/labelLv$")
            after_duration = self.parse_countdown_seconds(
                detail_text("/labelTime$/Text")
            )
            cancel_label = detail_text("/maskDetail/detailPanel/btn/giveup/text")
            actual_type = detail_image("/iconType$").sprite
            after_status = detail_image("/iconState$/1").sprite
            if (
                actual_name != name
                or actual_level != str(level)
                or actual_type != type_sprite
                or cancel_label != "取消"
                or after_status != "tag_ongoing"
            ):
                raise SemanticGateClosed("running commission detail identity changed")
            if not 0 < after_duration <= int(before_duration):
                raise SemanticGateClosed(
                    "running commission detail countdown is invalid"
                )
            return CommissionStartProof(
                index=index,
                name=actual_name,
                level=int(actual_level),
                type_sprite=actual_type,
                before_duration_seconds=int(before_duration),
                after_duration_seconds=after_duration,
                before_status_sprite="kongxian_bg",
                after_status_sprite=after_status,
                generation=button_state.generation,
            )
        if len(page_back_matches) != 1 or detail_back_matches:
            raise SemanticGateClosed(
                "commission start transition surface is absent or ambiguous"
            )
        page_back = page_back_matches[0]
        if not page_back.actionable or self._blocking_rules(
            button_state, "commission/page/back"
        ):
            raise SemanticGateClosed("commission page identity is not proven")
        root = "EventUI(Clone)/scrollRect$/content/{0}".format(index)
        row_buttons = tuple(
            button
            for button in button_state.buttons
            if button.name in ("bgNormal$", "bgEmergence$")
            and button.path.endswith(root + "/" + button.name)
            and button.active_in_hierarchy
        )
        if len(row_buttons) != 1:
            raise SemanticGateClosed("started commission row is absent or ambiguous")

        ui_state = self._paired_ui_after_state()
        if ui_state.image_truncated or ui_state.method_mask & 0x8 == 0:
            raise SemanticGateClosed(
                "commission start proof Image snapshot is incomplete"
            )
        if (
            ui_state.generation < button_state.generation
            or ui_state.generation > button_state.generation + 2
        ):
            raise SemanticGateClosed(
                "commission start proof snapshots are not coherent"
            )

        def exact_text(suffix: str) -> str:
            matches = tuple(
                item
                for item in ui_state.texts
                if item.path.endswith(root + suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("commission start proof text is ambiguous")
            return item_text(matches[0])

        def item_text(item: TextState) -> str:
            return re.sub(r"<[^<>]{1,128}>", "", item.text).strip()

        def exact_image(suffix: str) -> ImageState:
            matches = tuple(
                item
                for item in ui_state.images
                if item.path.endswith(root + suffix)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
            )
            if len(matches) != 1:
                raise SemanticGateClosed("commission start proof image is ambiguous")
            return matches[0]

        actual_name = exact_text("/labelName$")
        actual_level = exact_text("/level/labelLv$")
        after_duration = self.parse_countdown_seconds(exact_text("/labelTime$/Text"))
        after_status = exact_image("/iconState$/1").sprite
        actual_type = exact_image("/iconType$").sprite
        if (
            actual_name != name
            or actual_level != str(level)
            or actual_type != type_sprite
        ):
            raise SemanticGateClosed("started commission row identity changed")
        if not 0 < after_duration <= int(before_duration):
            raise SemanticGateClosed("started commission countdown is invalid")
        if after_status != "tag_ongoing":
            raise SemanticGateClosed("commission row did not leave pending state")
        return CommissionStartProof(
            index=index,
            name=actual_name,
            level=int(actual_level),
            type_sprite=actual_type,
            before_duration_seconds=int(before_duration),
            after_duration_seconds=after_duration,
            before_status_sprite="kongxian_bg",
            after_status_sprite=after_status,
            generation=button_state.generation,
        )

    def commission_start_prompt_cost(self) -> Optional[int]:
        # Rebind the whole button/text sandwich after an opening animation;
        # its original snapshot may have different modal button geometry.
        return self._retry_transition_read(self._commission_start_prompt_cost_once)

    def _commission_start_prompt_cost_once(self) -> Optional[int]:
        state = self.read_state()
        parts = self._msgbox_prompt_parts(state)
        if parts is None:
            return None
        plain, cancel, confirm = parts
        match = re.fullmatch(r"本次委托需要花费([1-9][0-9]*)石油", plain)
        if match is None or cancel != "取消" or confirm != "确定":
            return None
        return int(match.group(1))
