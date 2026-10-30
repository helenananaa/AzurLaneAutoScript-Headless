"""Opsi navigation for the typed ALAS boundary."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Optional, Tuple
from .contracts import (
    ActionReceipt,
    ImageState,
    OperationSirenDaemonTarget,
    OperationSirenGlobeSwipeReceipt,
    Point,
    UiState,
)
from .errors import SemanticGateClosed


def _native_grid_projection_point(item):
    raw = item.raw.get("adb_point")
    if not isinstance(raw, Mapping):
        raise SemanticGateClosed("operation siren native grid projection is absent")
    values = (raw.get("x"), raw.get("y"))
    if any(type(v) not in (int, float) or not math.isfinite(v) for v in values):
        raise SemanticGateClosed("operation siren native grid projection is malformed")
    point = Point(*values)
    if item.bounds is None or not item.bounds.contains(point):
        raise SemanticGateClosed("operation siren native grid projection is outside bounds")
    return point


class OpsiNavigationOracle:
    """Opsi navigation operations sharing the oracle frame and input boundary."""

    def operation_siren_radar_targets(
        self, target_kind: str
    ) -> Tuple[Tuple[int, int], ...]:
        """Read exact relative grid positions from the Operation Siren radar."""

        if target_kind not in {
            "port",
            "task",
            "guidepost",
            "question",
            "switch",
            "boss",
        }:
            raise SemanticGateClosed(
                "operation siren radar target kind is not reviewed"
            )
        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        state = self.read_ui_state()
        # Local maps routinely exceed the observer's bounded Image slice.
        # These radar targets are positive, exact hierarchy/sprite matches;
        # truncation may make an absent target unknowable, but it does not
        # invalidate a target that is present in the typed slice.
        radar_root = (
            "top/adapt/right_stage/compass_panel/ring/compass/range/"
        )
        path = radar_root + "mark"
        sprite_kind = (
            "guidepost" if target_kind in {"question", "switch"} else target_kind
        )
        join_event_ids = None
        if target_kind in {"question", "switch"}:
            # Original RadarGrid.predict_question() is a white ``?`` on the
            # radar, not a world-model classifier.  The observer groups those
            # white radar icons as sprite ``guidepost``.  The monthly-boss
            # compass can show two: the upper wormhole is the same entrance
            # normal uses, and the right buoy is not.  Join radar ids to the
            # world model ALAS actually walks onto.  Taban plates remain the
            # adjacent hard-room switch, not a second question class.
            # Identity join does not need clickable bounds; a truncated
            # wormhole still names the radar icon that is the entrance.
            if target_kind == "question":
                model_pattern = re.compile(
                    r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    r"cell_[0-9]+_[0-9]+/attachments/event_([0-9]+)/icon/model/"
                    r"chongdong02\(Clone\)$"
                )
                model_name = "chongdong02(Clone)"
                model_sprite = "chongdong42"
            else:
                model_pattern = re.compile(
                    r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                    r"cell_[0-9]+_[0-9]+/attachments/event_([0-9]+)/icon/model/"
                    r"taban_jinzhi\(Clone\)/taban$"
                )
                model_name = "taban"
                model_sprite = "taban01"
            join_event_ids = {
                match.group(1)
                for item in state.images
                if (match := model_pattern.fullmatch(item.path)) is not None
                and item.name == model_name
                and item.sprite == model_sprite
                and item.active_in_hierarchy
                and item.active_and_enabled
            }
            # Inside the monthly-boss room there is no wormhole.  Original
            # ALAS still walks the remaining white ``?`` waypoints, so fall
            # back to every radar guidepost when no chongdong join exists.
            if target_kind == "question" and not join_event_ids:
                join_event_ids = None
        if target_kind in {"guidepost", "question", "switch", "task", "boss"}:
            event_pattern = re.compile(r"[0-9]+$")
            matches = tuple(
                item
                for item in state.images
                if (
                    (
                        item.path.endswith(radar_root + item.name)
                        and event_pattern.fullmatch(item.name)
                    )
                    or (target_kind == "task" and item.path.endswith(path))
                )
                and item.sprite == sprite_kind
                and (
                    join_event_ids is None
                    or item.name in join_event_ids
                )
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
        else:
            matches = tuple(
                item
                for item in state.images
                if item.name == "mark"
                and item.path.endswith(path)
                and item.sprite == target_kind
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
        targets = []
        for item in matches:
            assert item.bounds is not None
            center_x = (item.bounds.left + item.bounds.right) / 2.0
            center_y = (item.bounds.top + item.bounds.bottom) / 2.0
            raw_x = (center_x - 1140.0) / 11.7
            raw_y = (center_y - 226.0) / 11.7
            grid_x = int(round(raw_x))
            grid_y = int(round(raw_y))
            if (
                abs(raw_x - grid_x) > 0.35
                or abs(raw_y - grid_y) > 0.35
                or max(abs(grid_x), abs(grid_y)) > 7
            ):
                raise SemanticGateClosed(
                    "operation siren radar target is not grid-aligned"
                )
            targets.append((grid_x, grid_y))
        if len(set(targets)) != len(targets):
            raise SemanticGateClosed("operation siren radar targets are ambiguous")
        # Radar.select() iterates its x-major grid dictionary.  Preserve that
        # ordering because original task code deliberately addresses index 0
        # and index 1 for multi-waypoint rooms.
        return tuple(sorted(targets))

    def operation_siren_nearest_daemon_target(
        self,
    ) -> Optional[OperationSirenDaemonTarget]:
        """Select the nearest reviewed non-port radar object without pixels.

        Original ``Radar.nearest_object()`` considers enemies, resources,
        meowfficers, exclamation marks, questions, and archives.  Current
        semantic evidence has exact Unity sprite identities for enemies,
        resource boxes, exclamation marks, and questions. Any other direct
        radar-object
        sprite therefore closes the gate instead of being guessed.  Targets
        farther than the original three-step radius also close the gate until
        the EMP one-step condition has a typed observation.
        """

        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        state = self.read_ui_state()
        radar_root = (
            "top/adapt/right_stage/compass_panel/ring/compass/range/"
        )
        event_name = re.compile(r"(?:mark|[0-9]+)$")
        reviewed = {
            "battle": "enemy",
            "boss": "enemy",
            "task": "event",
            "guidepost": "question",
            "exp": "resource",
        }
        objects = []
        ports = set()
        for item in state.images:
            if not (
                item.path.endswith(radar_root + item.name)
                and event_name.fullmatch(item.name)
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            ):
                continue
            assert item.bounds is not None
            center_x = (item.bounds.left + item.bounds.right) / 2.0
            center_y = (item.bounds.top + item.bounds.bottom) / 2.0
            raw_x = (center_x - 1140.0) / 11.7
            raw_y = (center_y - 226.0) / 11.7
            grid_x = int(round(raw_x))
            grid_y = int(round(raw_y))
            if (
                abs(raw_x - grid_x) > 0.35
                or abs(raw_y - grid_y) > 0.35
                or math.hypot(grid_x, grid_y) > 5.15
            ):
                raise SemanticGateClosed(
                    "operation siren daemon radar target is not grid-aligned"
                )
            position = (grid_x, grid_y)
            # RadarGrid.predict() skips is_fleet before classifying pixels.
            # Unity can retain the consumed event's icon beneath the fleet;
            # it is not a zero-distance target for the original daemon.
            if position == (0, 0):
                continue
            if item.sprite == "port":
                ports.add(position)
                continue
            kind = reviewed.get(item.sprite)
            if kind is None:
                raise SemanticGateClosed(
                    "operation siren daemon radar target kind is not reviewed: "
                    + item.sprite
                )
            objects.append((position, kind))

        # Mirror Radar.predict(): a white question directly beside a port is
        # the port glyph's edge, not an independent object.
        objects = [
            (position, kind)
            for position, kind in objects
            if not (
                kind == "question"
                and any(
                    abs(position[0] - port[0])
                    + abs(position[1] - port[1])
                    == 1
                    for port in ports
                )
            )
        ]
        positions = [position for position, _ in objects]
        if len(set(positions)) != len(positions):
            raise SemanticGateClosed(
                "operation siren daemon radar targets are ambiguous"
            )
        if not objects:
            if state.image_truncated:
                raise SemanticGateClosed(
                    "operation siren daemon radar absence is not observable"
                )
            return None

        distance = min(abs(x) + abs(y) for (x, y), _ in objects)
        nearest = [
            (position, kind)
            for position, kind in objects
            if abs(position[0]) + abs(position[1]) == distance
        ]
        if len(nearest) != 1:
            raise SemanticGateClosed(
                "operation siren nearest daemon target is ambiguous"
            )
        source_position, target_kind = nearest[0]
        # point_limit(camera_sight=(-4, -3, 3, 3)) from Radar.nearest_object.
        relative_position = (
            max(-4, min(3, source_position[0])),
            max(-3, min(3, source_position[1])),
        )
        if math.hypot(*relative_position) > 3.0:
            raise SemanticGateClosed(
                "operation siren daemon move requires typed EMP step state"
            )
        return OperationSirenDaemonTarget(
            generation=state.generation,
            target_kind=target_kind,
            source_position=source_position,
            relative_position=relative_position,
        )

    def click_operation_siren_daemon_target(
        self, expected: OperationSirenDaemonTarget
    ) -> ActionReceipt:
        """Recheck one daemon target identity immediately before its click."""

        if not isinstance(expected, OperationSirenDaemonTarget):
            raise TypeError("operation siren daemon target is not typed")
        current = self.operation_siren_nearest_daemon_target()
        if current is None or (
            current.target_kind != expected.target_kind
            or current.source_position != expected.source_position
            or current.relative_position != expected.relative_position
            or current.generation < expected.generation
        ):
            raise SemanticGateClosed(
                "operation siren daemon target changed before input"
            )
        # Match native convert_radar_to_local(), including an off-center
        # camera. A missing fleet origin cannot authorize a camera fallback.
        return self.click_operation_siren_relative_grid(
            expected.relative_position, fleet_relative=True
        )

    def operation_siren_obscure_exit_passage_position(
        self,
    ) -> Optional[Tuple[int, int]]:
        """Return the exact absolute grid of an obscure-zone exit passage."""

        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        state = self.read_ui_state()
        titles = tuple(
            item
            for item in state.texts
            if item.path.endswith("top/adapt/top_stage/title/name")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and item.text.endswith("-隐秘海域")
        )
        tips = tuple(
            item
            for item in state.texts
            if item.path.endswith("top/adapt/right_stage/tip_word/Text")
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
            and item.text == "从塞壬特殊通行装置离开隐秘海域"
        )
        portal_pattern = re.compile(
            r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            r"cell_([0-9]+)_([0-9]+)/attachments/event_1000034/icon/model/"
            r"chuansong01\(Clone\)/Xyz/Ring01/01$"
        )
        portals = tuple(
            item
            for item in state.images
            if portal_pattern.fullmatch(item.path)
            and item.name == "01"
            and item.sprite == "chuansong01"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        # The title and exit hint are present throughout an uncleared obscure
        # zone. The passage model itself is the transition-ready marker.
        if not portals:
            return None
        evidence = (titles, tips, portals)
        if any(len(items) != 1 for items in evidence):
            raise SemanticGateClosed(
                "operation siren obscure exit passage is incomplete or ambiguous"
            )
        match = portal_pattern.fullmatch(portals[0].path)
        assert match is not None
        return (int(match.group(1)), int(match.group(2)))

    def operation_siren_post_search_loot_visible(self) -> bool:
        """Recognize the loot inventory that can cover a cleared special map."""

        state = self.read_state()
        ui_state = self.read_ui_state()
        back_suffix = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/title/"
            "back_button"
        )
        backs = tuple(
            button
            for button in state.buttons
            if button.name == "back_button"
            and button.path.endswith(back_suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        item_pattern = re.compile(
            r".*OverlayCamera/Overlay/UIMain/blur_panel/adapt/shop/frame/"
            r"scrollview/view/item_tpl(?:\(Clone\))?$"
        )
        items = tuple(
            button
            for button in state.buttons
            if item_pattern.fullmatch(button.path)
            and button.name in {"item_tpl", "item_tpl(Clone)"}
            and button.active_in_hierarchy
            and button.active_and_enabled
        )
        titles = tuple(
            text
            for text in ui_state.texts
            if text.path.endswith("top/adapt/top_stage/title/name")
            and text.active_in_hierarchy
            and text.active_and_enabled
            and not text.truncated
            and text.bounds is not None
            and text.text.endswith(
                ("-隐秘海域", "-深渊海域", "-塞壬要塞海域")
            )
        )
        return len(backs) == 1 and bool(items) and len(titles) == 1

    def click_operation_siren_post_search_loot_back(self) -> ActionReceipt:
        """Dismiss the exact post-search loot inventory through its back button."""

        if not self.operation_siren_post_search_loot_visible():
            raise SemanticGateClosed(
                "operation siren post-search loot overlay is absent"
            )
        state = self.read_state()
        suffix = (
            "OverlayCamera/Overlay/UIMain/blur_panel/adapt/top/title/"
            "back_button"
        )
        matches = tuple(
            button
            for button in state.buttons
            if button.name == "back_button"
            and button.path.endswith(suffix)
            and button.active_in_hierarchy
            and button.active_and_enabled
            and button.interactable
            and button.point is not None
            and button.bounds is not None
            and button.bounds.contains(button.point)
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "operation siren post-search loot back is ambiguous"
            )
        target = matches[0]
        assert target.point is not None and target.bounds is not None
        if self._foreground_component() != self.fingerprint.component:
            raise SemanticGateClosed(
                "foreground changed before post-search loot dismissal"
            )
        self._tap(int(round(target.point.x)), int(round(target.point.y)))
        return ActionReceipt(
            semantic_id="os/auto-search/loot/back",
            generation=state.generation,
            point=target.point,
            bounds=target.bounds,
            path=target.path,
        )

    def operation_siren_obscure_exit_camera_swipe(
        self,
    ) -> OperationSirenGlobeSwipeReceipt:
        """Move the proven obscure exit object toward the safe viewport."""

        if self._swipe is None:
            raise SemanticGateClosed("operation siren swipe backend is absent")
        if self.operation_siren_obscure_exit_passage_position() is None:
            raise SemanticGateClosed("operation siren obscure exit passage is absent")
        pattern = re.compile(
            r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            r"cell_[0-9]+_[0-9]+/attachments/event_1000034/icon/model/"
            r"chuansong01\(Clone\)/Xyz/Ring01/01$"
        )

        def portal(state: UiState) -> ImageState:
            matches = tuple(
                item
                for item in state.images
                if pattern.fullmatch(item.path)
                and item.name == "01"
                and item.sprite == "chuansong01"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(matches) != 1:
                raise SemanticGateClosed(
                    "operation siren obscure exit object is ambiguous"
                )
            return matches[0]

        state = self.read_ui_state()
        target = portal(state)
        bounds = target.bounds
        assert bounds is not None
        center = Point(
            (bounds.left + bounds.right) / 2.0,
            (bounds.top + bounds.bottom) / 2.0,
        )
        delta_x = max(-280, min(280, int(round(640.0 - center.x))))
        delta_y = max(-240, min(240, int(round(360.0 - center.y))))
        if abs(delta_x) < 24 and abs(delta_y) < 24:
            raise SemanticGateClosed(
                "operation siren obscure exit object is already in view"
            )
        # Keep the gesture origin away from the selected fleet chibi and leave
        # enough room in the requested direction for the bounded drag.
        start = (
            360 if delta_x >= 0 else 640,
            300 if delta_y >= 0 else 500,
        )
        end = (start[0] + delta_x, start[1] + delta_y)
        if not (
            160 <= end[0] <= 840
            and 140 <= end[1] <= 620
            and self._foreground_component() == self.fingerprint.component
        ):
            raise SemanticGateClosed(
                "operation siren obscure exit camera swipe is not safe"
            )
        before_distance = math.hypot(center.x - 640.0, center.y - 360.0)
        pre_generation = state.generation
        self._swipe(start[0], start[1], end[0], end[1], 450)
        post_generation = None
        last_center = center
        for _ in range(80):
            self._sleep(0.25)
            candidate = self.read_ui_state()
            moved = portal(candidate)
            moved_bounds = moved.bounds
            assert moved_bounds is not None
            moved_center = Point(
                (moved_bounds.left + moved_bounds.right) / 2.0,
                (moved_bounds.top + moved_bounds.bottom) / 2.0,
            )
            last_center = moved_center
            if (
                candidate.generation > pre_generation
                and math.hypot(
                    moved_center.x - 640.0, moved_center.y - 360.0
                )
                < before_distance - 20.0
            ):
                post_generation = candidate.generation
                break
        if post_generation is None:
            raise SemanticGateClosed(
                "operation siren obscure exit camera did not approach passage "
                f"({center.x:.1f},{center.y:.1f})->"
                f"({last_center.x:.1f},{last_center.y:.1f})"
            )
        return OperationSirenGlobeSwipeReceipt(
            semantic_id="os/map/obscure-exit/swipe",
            pre_generation=pre_generation,
            post_generation=post_generation,
            start=start,
            end=end,
            duration_ms=450,
        )

    def click_operation_siren_obscure_exit_passage(self) -> ActionReceipt:
        """Click the exact obscure exit object after it enters safe view."""

        if self.operation_siren_obscure_exit_passage_position() is None:
            raise SemanticGateClosed("operation siren obscure exit passage is absent")
        state = self.read_ui_state()
        pattern = re.compile(
            r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            r"cell_[0-9]+_[0-9]+/attachments/event_1000034/icon/model/"
            r"chuansong01\(Clone\)/Xyz/Ring01/01$"
        )
        matches = tuple(
            item
            for item in state.images
            if pattern.fullmatch(item.path)
            and item.name == "01"
            and item.sprite == "chuansong01"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(matches) != 1:
            raise SemanticGateClosed(
                "operation siren obscure exit object is ambiguous"
            )
        bounds = matches[0].bounds
        assert bounds is not None
        point = Point(
            (bounds.left + bounds.right) / 2.0,
            (bounds.top + bounds.bottom) / 2.0,
        )
        if (
            not 80.0 <= point.x <= 960.0
            or not 100.0 <= point.y <= 620.0
            or self._foreground_component() != self.fingerprint.component
        ):
            raise SemanticGateClosed(
                "operation siren obscure exit object is outside safe view"
            )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id="os/map/obscure-exit/passage",
            generation=state.generation,
            point=point,
            bounds=bounds,
            path=matches[0].path,
        )

    def click_operation_siren_relative_grid(
        self,
        relative_position: Tuple[int, int],
        *,
        prefer_adjacent_event: bool = False,
        expected_path: Optional[str] = None,
        fleet_relative: bool = False,
    ) -> ActionReceipt:
        """Click a typed world grid in the caller's explicit reference frame."""

        if (
            not isinstance(relative_position, tuple)
            or len(relative_position) != 2
            or any(type(value) is not int for value in relative_position)
            or any(abs(value) > 4 for value in relative_position)
        ):
            raise SemanticGateClosed(
                "operation siren relative grid position is malformed"
            )
        if not self.operation_siren_local_map_visible():
            raise SemanticGateClosed("operation siren local-map identity is absent")
        state = self.read_ui_state()
        # As above, world-grid navigation relies only on positive exact paths.
        # The map Image slice can be truncated while the center and requested
        # grid are both fully represented.
        pattern = re.compile(
            r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/quads/"
            r"world_quad_([0-9]+)_([0-9]+)/walk_quad$"
        )
        grids = []
        for item in state.images:
            match = pattern.fullmatch(item.path)
            if (
                match is None
                or item.name != "walk_quad"
                or item.sprite != "cell_white"
                or not item.active_in_hierarchy
                or not item.active_and_enabled
                or item.truncated
                or item.bounds is None
            ):
                continue
            grids.append((int(match.group(1)), int(match.group(2)), item))
        if fleet_relative:
            fleet = self._operation_siren_current_fleet_from_ui_state(state)
            fleet_path = f'/LevelGrid/DragLayer/plane/cells/fleet_{fleet}/shadow'
            fleet_anchors = [item for item in state.images
                if item.path.endswith(fleet_path) and item.name == 'shadow'
                and item.sprite == 'shadow' and item.active_in_hierarchy
                and item.active_and_enabled and not item.truncated
                and item.bounds is not None]
            if len(fleet_anchors) > 1:
                raise SemanticGateClosed('operation siren relative-grid fleet anchor is absent or ambiguous')
            if fleet_anchors:
                fleet_point = _native_grid_projection_point(fleet_anchors[0])
                centers = tuple((row, column, item) for row, column, item in grids
                    if item.bounds.contains(fleet_point)
                    and math.hypot(_native_grid_projection_point(item).x-fleet_point.x,
                                  _native_grid_projection_point(item).y-fleet_point.y) <= .05)
            else:
                model = self._operation_siren_selected_fleet_model(state)
                if model is None:
                    raise SemanticGateClosed('operation siren relative-grid fleet anchor is absent or ambiguous')
                if model.get('moving_known') is True and model.get('moving') is not False:
                    raise SemanticGateClosed('operation siren selected fleet model is moving')
                centers = tuple((row, column, item) for row, column, item in grids
                                if (row, column) == (model['row'], model['column']))
        else:
            centers = tuple(
                (row, column, item)
                for row, column, item in grids
                if item.bounds is not None
                and item.bounds.contains(Point(640.0, 360.0))
            )
        if not centers and not fleet_relative:
            occupied_center_pattern = re.compile(
                r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                r"cell_([0-9]+)_([0-9]+)/attachments/event_[0-9]+/"
                r"icon/model/taban\(Clone\)/taban$"
            )
            centers = tuple(
                (int(match.group(1)), int(match.group(2)), item)
                for item in state.images
                if (match := occupied_center_pattern.fullmatch(item.path)) is not None
                and item.name == "taban"
                and item.sprite == "taban01"
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
                and item.bounds.contains(Point(640.0, 360.0))
            )
        if len(centers) != 1:
            raise SemanticGateClosed(
                "operation siren camera center grid is absent or ambiguous"
            )
        center_row, center_column, _ = centers[0]
        target_row = center_row + relative_position[1]
        target_column = center_column + relative_position[0]
        targets = tuple(
            item
            for row, column, item in grids
            if row == target_row and column == target_column
        )
        click_bounds = None
        click_path = None
        if len(targets) == 1 and targets[0].bounds is not None:
            click_bounds = targets[0].bounds
            click_path = targets[0].path
        if prefer_adjacent_event and abs(relative_position[0]) + abs(relative_position[1]) <= 3:
            event_pattern = re.compile(
                r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
                rf"cell_{target_row}_{target_column}/attachments/event_[0-9]+/"
                r"(?:icon/model/(?:fubiao3|taban_jinzhi|chongdong02)\(Clone\)"
                r"(?:/taban)?|"
                r"char/shadow)$"
            )
            events = tuple(
                item
                for item in state.images
                if event_pattern.fullmatch(item.path)
                and (
                    (item.name == "fubiao3(Clone)" and item.sprite == "fubiao3")
                    or (
                        item.name == "chongdong02(Clone)"
                        and item.sprite == "chongdong42"
                    )
                    or (item.name == "taban" and item.sprite == "taban01")
                    or (item.name == "shadow" and item.sprite == "shadow")
                )
                and item.active_in_hierarchy
                and item.active_and_enabled
                and not item.truncated
                and item.bounds is not None
            )
            if len(events) > 1:
                raise SemanticGateClosed(
                    "operation siren adjacent event target is ambiguous"
                )
            if len(events) == 1:
                assert events[0].bounds is not None
                click_bounds = events[0].bounds
                click_path = events[0].path
        if click_bounds is None or click_path is None:
            raise SemanticGateClosed(
                "operation siren relative target grid is absent or ambiguous"
            )
        if expected_path is not None and click_path != expected_path:
            raise SemanticGateClosed('operation siren camera target changed before input')
        button_state = self.read_state()
        if (not state.generation <= button_state.generation <= state.generation + 2
                or self._blocking_rules(button_state, 'os/map/guidepost/relative')):
            raise SemanticGateClosed('operation siren relative grid is incoherent or covered')
        point = Point(
            (click_bounds.left + click_bounds.right) / 2.0,
            (click_bounds.top + click_bounds.bottom) / 2.0,
        )
        if (
            not click_bounds.contains(point)
            or not 80.0 <= point.x <= 960.0
            or not 100.0 <= point.y <= 620.0
            or self._foreground_component() != self.fingerprint.component
        ):
            raise SemanticGateClosed(
                "operation siren relative target click is not safe"
            )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=(
                "os/map/grid/relative/"
                f"{relative_position[0]}/{relative_position[1]}"
            ),
            generation=state.generation,
            point=point,
            bounds=click_bounds,
            path=click_path,
        )

    def click_operation_siren_radar_guidepost(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        """Click an adjacent guidepost from exact radar and fleet anchors."""

        if (
            not isinstance(relative_position, tuple)
            or len(relative_position) != 2
            or any(type(value) is not int for value in relative_position)
            or relative_position not in {
                (0, 1), (-1, 0), (1, 0), (0, -1), (0, -2), (0, -3)
            }
        ):
            raise SemanticGateClosed(
                "operation siren guidepost position is malformed"
            )
        if relative_position not in self.operation_siren_radar_targets("guidepost"):
            raise SemanticGateClosed(
                "operation siren guidepost changed before input"
            )
        before = self.read_state()
        state = self.read_ui_state()
        if not before.generation <= state.generation <= before.generation + 2:
            raise SemanticGateClosed("operation siren guidepost frame is incoherent")
        fleet = self._operation_siren_current_fleet_from_ui_state(state)
        fleet_path = (
            f"/LevelGrid/DragLayer/plane/cells/fleet_{fleet}/shadow"
        )
        fleet_anchors = tuple(
            item
            for item in state.images
            if item.name == "shadow"
            and item.sprite == "shadow"
            and item.path.endswith(fleet_path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(fleet_anchors) != 1:
            raise SemanticGateClosed(
                "operation siren selected-fleet guidepost anchor is ambiguous"
            )
        native_point = _native_grid_projection_point

        # Unity's own grid projections join the selected fleet to one cell.
        # WSMapCell hides attachment models in fog; a positive radar target
        # still identifies the adjacent native walk cell used by ALAS.
        fleet_point = native_point(fleet_anchors[0])
        grid_pattern = re.compile(
            r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/quads/"
            r"world_quad_([0-9]+)_([0-9]+)/walk_quad$"
        )
        grids = []
        for item in state.images:
            match = grid_pattern.fullmatch(item.path)
            if (match is not None and item.name == "walk_quad"
                    and item.sprite == "cell_white" and item.active_in_hierarchy
                    and item.active_and_enabled and not item.truncated
                    and item.bounds is not None):
                grids.append((int(match[1]), int(match[2]), item, native_point(item)))
        anchors = [(r, c) for r, c, _, p in grids
                   if math.hypot(p.x-fleet_point.x, p.y-fleet_point.y) <= 0.05]
        if len(anchors) != 1:
            raise SemanticGateClosed("operation siren guidepost fleet cell is absent or ambiguous")
        row = anchors[0][0] + relative_position[1]
        column = anchors[0][1] + relative_position[0]
        cells = [(item, p) for r, c, item, p in grids if (r, c) == (row, column)]
        if len(cells) != 1:
            raise SemanticGateClosed("operation siren guidepost target cell is absent or ambiguous")
        guidepost_pattern = re.compile(
            r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            rf"cell_{row}_{column}/attachments/event_[0-9]+/char/shadow$"
        )
        candidates = [item for item in state.images
                      if guidepost_pattern.fullmatch(item.path)
                      and item.name == "shadow" and item.sprite == "shadow"
                      and item.active_in_hierarchy and item.active_and_enabled
                      and not item.truncated and item.bounds is not None]
        if len(candidates) > 1:
            raise SemanticGateClosed("operation siren adjacent guidepost is absent or ambiguous")
        target, point = (candidates[0], native_point(candidates[0])) if candidates else cells[0]
        assert target.bounds is not None
        if self._blocking_rules(self.read_state(), "os/map/guidepost/relative"):
            raise SemanticGateClosed("operation siren guidepost is obscured before input")
        if (
            not target.bounds.contains(point)
            or not 80.0 <= point.x <= 960.0
            or not 100.0 <= point.y <= 620.0
            or self._foreground_component() != self.fingerprint.component
        ):
            raise SemanticGateClosed(
                "operation siren adjacent guidepost click is not safe"
            )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=(
                "os/map/guidepost/relative/"
                f"{relative_position[0]}/{relative_position[1]}"
            ),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )

    def click_operation_siren_radar_boss(
        self, relative_position: Tuple[int, int]
    ) -> ActionReceipt:
        """Click the exact boss shadow relative to the selected fleet anchor."""

        if (
            not isinstance(relative_position, tuple)
            or len(relative_position) != 2
            or any(type(value) is not int for value in relative_position)
            or max(abs(value) for value in relative_position) > 4
        ):
            raise SemanticGateClosed(
                "operation siren boss position is malformed"
            )
        if relative_position not in self.operation_siren_radar_targets("boss"):
            raise SemanticGateClosed(
                "operation siren boss target changed before input"
            )
        state = self.read_ui_state()
        fleet = self._operation_siren_current_fleet_from_ui_state(state)
        fleet_path = f"/LevelGrid/DragLayer/plane/cells/fleet_{fleet}/shadow"
        anchors = tuple(
            item
            for item in state.images
            if item.name == "shadow"
            and item.sprite == "shadow"
            and item.path.endswith(fleet_path)
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        )
        if len(anchors) > 1 or (not anchors and relative_position != (0, 0)):
            raise SemanticGateClosed(
                "operation siren selected-fleet boss anchor is ambiguous"
            )
        expected_x = None
        expected_y = None
        if anchors:
            fleet_bounds = anchors[0].bounds
            assert fleet_bounds is not None
            fleet_x = (fleet_bounds.left + fleet_bounds.right) / 2.0
            fleet_y = (fleet_bounds.top + fleet_bounds.bottom) / 2.0
            expected_x = fleet_x + relative_position[0] * 99.0
            expected_y = fleet_y + relative_position[1] * 70.0
        enemy_pattern = re.compile(
            r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            r"cell_[0-9]+_[0-9]+/attachments/enemy_[0-9]+/live/char/shadow$"
        )
        event_pattern = re.compile(
            r"LevelCamera/Canvas/UIMain/LevelGrid/DragLayer/plane/cells/"
            r"cell_[0-9]+_[0-9]+/attachments/event_([0-9]+)/char/shadow$"
        )
        radar_root = "top/adapt/right_stage/compass_panel/ring/compass/range/"
        exact_boss_event_ids = {
            item.name
            for item in state.images
            if item.path.endswith(radar_root + item.name)
            and re.fullmatch(r"[0-9]+", item.name)
            and item.sprite == "boss"
            and item.active_in_hierarchy
            and item.active_and_enabled
            and not item.truncated
            and item.bounds is not None
        }
        candidates = []
        for item in state.images:
            event_match = event_pattern.fullmatch(item.path)
            exact_event = (
                event_match is not None
                and event_match.group(1) in exact_boss_event_ids
            )
            if (
                not (
                    enemy_pattern.fullmatch(item.path)
                    or exact_event
                )
                or item.name != "shadow"
                or item.sprite != "shadow"
                or not item.active_in_hierarchy
                or not item.active_and_enabled
                or item.truncated
                or item.bounds is None
            ):
                continue
            point = Point(
                (item.bounds.left + item.bounds.right) / 2.0,
                (item.bounds.top + item.bounds.bottom) / 2.0,
            )
            if exact_event or expected_x is None or (
                abs(point.x - expected_x) <= 24.0
                and abs(point.y - expected_y) <= 24.0
            ):
                candidates.append((item, point))
        if len(candidates) != 1:
            raise SemanticGateClosed(
                "operation siren exact boss shadow is absent or ambiguous"
            )
        target, point = candidates[0]
        assert target.bounds is not None
        if (
            not target.bounds.contains(point)
            or not 80.0 <= point.x <= 960.0
            or not 100.0 <= point.y <= 620.0
            or self._foreground_component() != self.fingerprint.component
        ):
            raise SemanticGateClosed(
                "operation siren exact boss click is not safe"
            )
        self._tap(int(round(point.x)), int(round(point.y)))
        return ActionReceipt(
            semantic_id=(
                "os/map/boss/relative/"
                f"{relative_position[0]}/{relative_position[1]}"
            ),
            generation=state.generation,
            point=point,
            bounds=target.bounds,
            path=target.path,
        )
